from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Protocol

from packages.harness_common.schemas.context import (
    ContextBundle,
    ContextConflict,
    ContextItem,
    ContextKind,
    ContextPlan,
    ContextProviderFailure,
    ContextRequest,
)


_KIND_ORDER = {
    ContextKind.INSTRUCTION: 0,
    ContextKind.POLICY: 1,
    ContextKind.TASK_STATE: 2,
    ContextKind.USER_PROFILE: 3,
    ContextKind.SESSION: 4,
    ContextKind.MEMORY: 5,
    ContextKind.KNOWLEDGE: 6,
    ContextKind.TOOL_RESULT: 7,
    ContextKind.ARTIFACT: 8,
    ContextKind.TOOL_DEFINITION: 9,
    ContextKind.WORKFLOW_STAGE: 3,
    ContextKind.SCENE: 4,
    ContextKind.TELEMETRY: 5,
    ContextKind.ALARM: 6,
    ContextKind.SKILL: 7,
    ContextKind.RETRIEVAL: 8,
}

_SECTION_NAMES = {
    ContextKind.INSTRUCTION: "System Instructions",
    ContextKind.POLICY: "Constraints",
    ContextKind.TASK_STATE: "Current Task",
    ContextKind.USER_PROFILE: "Runtime Scope",
    ContextKind.SESSION: "Recent Session",
    ContextKind.MEMORY: "Relevant Memory",
    ContextKind.KNOWLEDGE: "Retrieved Knowledge",
    ContextKind.TOOL_RESULT: "Tool Observations",
    ContextKind.ARTIFACT: "Artifacts",
    ContextKind.WORKFLOW_STAGE: "Workflow Stage",
    ContextKind.SCENE: "Scene Context",
    ContextKind.TELEMETRY: "Telemetry",
    ContextKind.ALARM: "Alarms",
    ContextKind.SKILL: "Relevant Skills",
    ContextKind.RETRIEVAL: "Retrieved Knowledge",
}

_COMPACTABLE_KINDS = {
    ContextKind.SESSION,
    ContextKind.MEMORY,
    ContextKind.KNOWLEDGE,
    ContextKind.TOOL_RESULT,
    ContextKind.ARTIFACT,
    ContextKind.SCENE,
    ContextKind.TELEMETRY,
    ContextKind.ALARM,
    ContextKind.SKILL,
    ContextKind.RETRIEVAL,
}


class ContextSummarizer(Protocol):
    def summarize(
        self,
        items: list[ContextItem],
        *,
        max_tokens: int,
        level: str,
    ) -> str: ...


class DeterministicContextSummarizer:
    """无模型或模型失败时生成可回放的带来源摘要。"""

    def summarize(
        self,
        items: list[ContextItem],
        *,
        max_tokens: int,
        level: str,
    ) -> str:
        fragments: list[str] = []
        for item in sorted(items, key=lambda value: value.id):
            content = (
                item.summary
                if item.summary
                else item.content
                if isinstance(item.content, str)
                else json.dumps(item.content, ensure_ascii=False, sort_keys=True)
            )
            fragments.append(f"[{item.source_ref or item.id}] {content}")
        return f"{level}: " + "\n".join(fragments)[: max_tokens * 4]


class ModelContextSummarizer:
    """在 60% 阈值后用当前模型压缩，失败时保持确定性降级。"""

    def __init__(self, model: Any) -> None:
        self.model = model
        self.fallback = DeterministicContextSummarizer()

    def summarize(
        self,
        items: list[ContextItem],
        *,
        max_tokens: int,
        level: str,
    ) -> str:
        source_text = self.fallback.summarize(
            items,
            max_tokens=max_tokens,
            level=level,
        )
        try:
            result = self.model.complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "压缩上下文，保留事实、时间、冲突和每个 source_ref；"
                            f"不得推导新事实，输出不超过 {max_tokens} tokens。"
                        ),
                    },
                    {"role": "user", "content": source_text},
                ]
            )
            content = str(result.get("content") or "").strip()
            if content:
                return _limit_summary(content, max_tokens)
        except Exception:
            # Compaction 不能因为外部模型暂时不可用而阻断正式 Agent Runtime。
            pass
        return source_text


def estimate_tokens(value: Any) -> int:
    if not isinstance(value, str):
        value = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", value))
    non_cjk = re.sub(r"[\u3400-\u9fff]", "", value)
    return max(1, cjk_count + (len(non_cjk) + 3) // 4)


def context_score(item: ContextItem) -> float:
    if item.pinned:
        return 10_000.0
    value = (
        0.35 * item.relevance
        + 0.25 * item.authority
        + 0.20 * item.freshness
        + 0.20 * item.utility
    )
    token_estimate = item.token_estimate or estimate_tokens(item.content)
    cost_penalty = min(token_estimate / 4_000, 1.0) * 0.15
    return value - cost_penalty


class ContextCompiler:
    """将统一 Context IR 编译为确定、可回放的模型与工具视图。"""

    def __init__(self, summarizer: ContextSummarizer | None = None) -> None:
        self.summarizer = summarizer or DeterministicContextSummarizer()

    def compile(
        self,
        *,
        request: ContextRequest,
        plan: ContextPlan,
        items: list[ContextItem],
        provider_failures: list[ContextProviderFailure] | None = None,
        cache_hits: list[str] | None = None,
        lifecycle_runtime: str = "compiler",
    ) -> ContextBundle:
        failures = provider_failures or []
        resolved_cache_hits = sorted(set(cache_hits or []))
        candidates, excluded_ids = self._filter(request, plan, items)
        candidates, deduplicated_ids = self._deduplicate(candidates)
        excluded_ids.extend(deduplicated_ids)
        conflicts = self._conflicts(candidates)
        tool_candidates = list(candidates)
        candidates, sliding_excluded, compaction_steps = self._sliding_window(
            request,
            candidates,
        )
        excluded_ids.extend(sliding_excluded)
        candidates, hierarchy_excluded, hierarchy_steps = self._hierarchical(
            request,
            candidates,
        )
        excluded_ids.extend(hierarchy_excluded)
        compaction_steps.extend(hierarchy_steps)
        ordered = sorted(
            (item for item in candidates if item.model_visible),
            key=self._sort_key,
        )

        selected: list[ContextItem] = []
        used = 0
        compression_level = "none"
        for item in ordered:
            token_estimate = item.token_estimate or estimate_tokens(item.content)
            normalized = item.model_copy(update={"token_estimate": token_estimate})
            if item.pinned:
                selected.append(normalized)
                used += token_estimate
                continue
            if (used + token_estimate) / request.token_budget >= 0.6:
                compressed = self._compress(request, normalized)
                if (
                    compressed is not None
                    and compressed.token_estimate < token_estimate
                    and used + compressed.token_estimate <= request.token_budget
                ):
                    selected.append(compressed)
                    used += compressed.token_estimate
                    compression_level = "summarized"
                    if "summarization" not in compaction_steps:
                        compaction_steps.append("summarization")
                    continue
            if used + token_estimate <= request.token_budget:
                selected.append(normalized)
                used += token_estimate
                continue
            compressed = self._compress(request, normalized)
            if compressed is not None and used + compressed.token_estimate <= request.token_budget:
                selected.append(compressed)
                used += compressed.token_estimate
                compression_level = "summarized"
                if "summarization" not in compaction_steps:
                    compaction_steps.append("summarization")
                continue
            excluded_ids.append(item.id)
            if "selective_recall" not in compaction_steps:
                compaction_steps.append("selective_recall")

        selected_kinds = {item.kind for item in selected}
        missing = sorted(
            (kind for kind in plan.required if kind not in selected_kinds),
            key=str,
        )
        utilization = used / request.token_budget
        warnings = [f"missing_context:{kind}" for kind in missing]
        if conflicts:
            warnings.extend(f"context_conflict:{item.field}" for item in conflicts)
        warnings.extend(
            f"stale_context:{item.id}"
            for item in selected
            if item.freshness < 0.4 or item.metadata.get("stale") is True
        )
        allow_tool_calls = utilization < 0.95
        if utilization >= 0.8 and compression_level == "none":
            compression_level = "forced"
        if not allow_tool_calls:
            warnings.append("context_budget_exhausted")

        tool_items = [
            item
            for item in sorted(tool_candidates, key=self._sort_key)
            if item.tool_visible
        ]
        model_context = self._render(selected)
        snapshot_payload = {
            "scope": request.scope.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "model_items": [item.model_dump(mode="json") for item in selected],
            "tool_item_ids": [item.id for item in tool_items],
            "excluded_ids": sorted(set(excluded_ids)),
            "missing_context": [str(kind) for kind in missing],
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
            "provider_failures": [
                item.model_dump(mode="json") for item in failures
            ],
            "cache_hits": resolved_cache_hits,
            "token_budget": request.token_budget,
            "tokens_used": used,
            "compression_level": compression_level,
            "compaction_steps": compaction_steps,
            "allow_tool_calls": allow_tool_calls,
            "warnings": warnings,
            "model_context": model_context,
            "lifecycle_runtime": lifecycle_runtime,
        }
        snapshot_id = "ctx_" + sha256(
            json.dumps(
                snapshot_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        return ContextBundle(
            snapshot_id=snapshot_id,
            scope=request.scope,
            plan=plan,
            model_items=selected,
            tool_items=tool_items,
            excluded_ids=sorted(set(excluded_ids)),
            missing_context=missing,
            conflicts=conflicts,
            provider_failures=failures,
            cache_hits=resolved_cache_hits,
            token_budget=request.token_budget,
            tokens_used=used,
            utilization=utilization,
            compression_level=compression_level,
            compaction_steps=compaction_steps,
            allow_tool_calls=allow_tool_calls,
            warnings=warnings,
            model_context=model_context,
            lifecycle_runtime=lifecycle_runtime,
        )

    @staticmethod
    def _filter(
        request: ContextRequest,
        plan: ContextPlan,
        items: list[ContextItem],
    ) -> tuple[list[ContextItem], list[str]]:
        candidates: list[ContextItem] = []
        excluded: list[str] = []
        excluded_kinds = set(plan.excluded)
        scope = request.scope
        for item in items:
            metadata = item.metadata
            allowed_roles = {
                str(role) for role in metadata.get("allowed_roles", [])
            }
            allowed_users = {
                str(user_id) for user_id in metadata.get("allowed_user_ids", [])
            }
            scope_mismatch = any(
                metadata.get(field) not in (None, "", expected)
                for field, expected in (
                    ("tenant_id", scope.tenant_id),
                    ("site_id", scope.site_id),
                    ("user_id", scope.user_id),
                    ("asset_id", scope.asset_id),
                )
            )
            if (
                item.kind in excluded_kinds
                or item.sensitive
                or allowed_roles
                and scope.role not in allowed_roles
                or allowed_users
                and scope.user_id not in allowed_users
                or item.expires_at is not None
                and item.expires_at <= request.now
                or scope_mismatch
            ):
                excluded.append(item.id)
                continue
            if not item.model_visible:
                excluded.append(item.id)
            candidates.append(item)
        return candidates, excluded

    @staticmethod
    def _deduplicate(
        items: list[ContextItem],
    ) -> tuple[list[ContextItem], list[str]]:
        primary: dict[tuple[str, str], list[ContextItem]] = {}
        without_primary: list[ContextItem] = []
        for item in items:
            if item.source_ref and item.version:
                primary.setdefault((item.source_ref, item.version), []).append(item)
            else:
                without_primary.append(item)

        primary_resolved: list[ContextItem] = []
        excluded: list[str] = []
        for grouped in primary.values():
            by_content: dict[str, ContextItem] = {}
            for item in grouped:
                digest = _content_hash(item.content)
                existing = by_content.get(digest)
                if existing is None:
                    by_content[digest] = item
                    continue
                winner = max(
                    (existing, item),
                    key=lambda value: (context_score(value), value.id),
                )
                loser = item if winner is existing else existing
                by_content[digest] = winner
                excluded.append(loser.id)
            primary_resolved.extend(by_content.values())

        by_hash: dict[str, ContextItem] = {}
        for item in sorted(
            [*primary_resolved, *without_primary], key=lambda value: value.id
        ):
            digest = _content_hash(item.content)
            existing = by_hash.get(digest)
            if existing is None:
                by_hash[digest] = item
                continue
            winner = max(
                (existing, item),
                key=lambda value: (context_score(value), value.id),
            )
            loser = item if winner is existing else existing
            by_hash[digest] = winner
            excluded.append(loser.id)
        return list(by_hash.values()), excluded

    @staticmethod
    def _conflicts(items: list[ContextItem]) -> list[ContextConflict]:
        grouped: dict[str, list[tuple[ContextItem, Any]]] = {}
        for item in items:
            key, value = _fact(item)
            if key:
                grouped.setdefault(key, []).append((item, value))
        return [
            ContextConflict(
                field=key,
                candidate_ids=sorted(item.id for item, _ in candidates),
                selected_id=None,
                resolution_reason="conflicting sources retained for model disclosure",
                candidates=[
                    {
                        "id": item.id,
                        "source": item.source,
                        "source_ref": item.source_ref,
                        "version": item.version,
                        "source_timestamp": item.source_timestamp,
                        "value": value,
                    }
                    for item, value in sorted(candidates, key=lambda value: value[0].id)
                ],
            )
            for key, candidates in sorted(grouped.items())
            if len(
                {
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                    for _, value in candidates
                }
            )
            > 1
        ]

    @staticmethod
    def _sort_key(item: ContextItem) -> tuple[Any, ...]:
        return (
            0 if item.pinned else 1,
            _KIND_ORDER.get(item.kind, 99),
            -context_score(item),
            item.source_ref or "",
            item.id,
        )

    def _compress(
        self,
        request: ContextRequest,
        item: ContextItem,
    ) -> ContextItem | None:
        if item.kind not in _COMPACTABLE_KINDS:
            return None
        summary = item.summary or self.summarizer.summarize(
            [item],
            max_tokens=request.summary_token_limit,
            level="item",
        )
        summary = _limit_summary(summary, request.summary_token_limit)
        return item.model_copy(
            update={
                "content": summary,
                "token_estimate": estimate_tokens(summary),
                "metadata": {
                    **item.metadata,
                    "compressed": True,
                    "compaction": "summarization",
                },
            }
        )

    def _sliding_window(
        self,
        request: ContextRequest,
        items: list[ContextItem],
    ) -> tuple[list[ContextItem], list[str], list[str]]:
        sessions = sorted(
            (item for item in items if item.kind is ContextKind.SESSION),
            key=lambda item: (item.source_timestamp or item.created_at, item.id),
        )
        if len(sessions) <= request.sliding_window_items:
            return items, [], []
        older = sessions[: -request.sliding_window_items]
        retained_ids = {item.id for item in sessions[-request.sliding_window_items :]}
        summary = _limit_summary(
            self.summarizer.summarize(
                older,
                max_tokens=request.summary_token_limit,
                level="sliding_window",
            ),
            request.summary_token_limit,
        )
        digest = sha256("|".join(item.id for item in older).encode()).hexdigest()[:16]
        summary_item = ContextItem(
            id=f"session-window:{digest}",
            kind=ContextKind.SESSION,
            content=summary,
            source="context_compaction",
            source_ref=f"compaction:sliding-window:{digest}",
            created_at=max(item.created_at for item in older),
            source_timestamp=max(
                item.source_timestamp or item.created_at for item in older
            ),
            retrieved_at=request.now,
            relevance=max(item.relevance for item in older),
            authority=max(item.authority for item in older),
            freshness=max(item.freshness for item in older),
            utility=max(item.utility for item in older),
            token_estimate=estimate_tokens(summary),
            metadata={
                "compaction": "sliding_window",
                "source_ids": [item.id for item in older],
            },
        )
        retained = [
            item
            for item in items
            if item.kind is not ContextKind.SESSION or item.id in retained_ids
        ]
        return [*retained, summary_item], [item.id for item in older], ["sliding_window"]

    def _hierarchical(
        self,
        request: ContextRequest,
        items: list[ContextItem],
    ) -> tuple[list[ContextItem], list[str], list[str]]:
        candidates = [
            item
            for item in items
            if not item.pinned and item.kind in _COMPACTABLE_KINDS
        ]
        total_tokens = sum(
            item.token_estimate or estimate_tokens(item.content) for item in candidates
        )
        if (
            len(candidates) < request.hierarchical_compaction_items
            or total_tokens <= request.token_budget
        ):
            return items, [], []
        chunk_size = max(2, request.hierarchical_compaction_items // 2)
        paragraphs: list[ContextItem] = []
        for offset in range(0, len(candidates), chunk_size):
            chunk = candidates[offset : offset + chunk_size]
            text = self.summarizer.summarize(
                chunk,
                max_tokens=request.summary_token_limit,
                level="paragraph",
            )
            paragraphs.append(
                ContextItem(
                    id=f"paragraph:{offset // chunk_size}",
                    kind=ContextKind.RETRIEVAL,
                    content=_limit_summary(text, request.summary_token_limit),
                    source="context_compaction",
                    source_ref=f"compaction:paragraph:{offset // chunk_size}",
                    created_at=request.now,
                    metadata={"source_ids": [item.id for item in chunk]},
                )
            )
        global_summary = _limit_summary(
            self.summarizer.summarize(
                paragraphs,
                max_tokens=request.summary_token_limit,
                level="global",
            ),
            request.summary_token_limit,
        )
        digest = sha256("|".join(item.id for item in candidates).encode()).hexdigest()[:16]
        global_item = ContextItem(
            id=f"hierarchy:{digest}",
            kind=ContextKind.RETRIEVAL,
            content=global_summary,
            source="context_compaction",
            source_ref=f"compaction:hierarchical:{digest}",
            created_at=request.now,
            retrieved_at=request.now,
            relevance=max(item.relevance for item in candidates),
            authority=max(item.authority for item in candidates),
            freshness=max(item.freshness for item in candidates),
            utility=max(item.utility for item in candidates),
            token_estimate=estimate_tokens(global_summary),
            metadata={
                "compaction": "hierarchical",
                "source_ids": [item.id for item in candidates],
            },
        )
        most_relevant = max(candidates, key=context_score)
        candidate_ids = {item.id for item in candidates}
        retained = [item for item in items if item.id not in candidate_ids]
        return (
            [*retained, most_relevant, global_item],
            [item.id for item in candidates if item.id != most_relevant.id],
            ["hierarchical", "selective_recall"],
        )

    @staticmethod
    def _render(items: list[ContextItem]) -> str:
        sections: list[str] = []
        grouped: dict[ContextKind, list[ContextItem]] = {}
        for item in items:
            if not item.model_visible or item.kind == ContextKind.TOOL_DEFINITION:
                continue
            grouped.setdefault(item.kind, []).append(item)
        for kind in sorted(grouped, key=lambda value: _KIND_ORDER.get(value, 99)):
            title = _SECTION_NAMES.get(kind, str(kind).replace("_", " ").title())
            lines = [f"<{title}>"]
            for item in grouped[kind]:
                content = (
                    item.content
                    if isinstance(item.content, str)
                    else json.dumps(item.content, ensure_ascii=False, sort_keys=True)
                )
                source = f" source_ref={item.source_ref}" if item.source_ref else ""
                lines.append(f"[{item.id}{source}] {content}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)


def _content_hash(content: Any) -> str:
    return sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _fact(item: ContextItem) -> tuple[str, Any]:
    explicit_key = str(
        item.metadata.get("conflict_key") or item.metadata.get("fact_key") or ""
    )
    if explicit_key:
        return explicit_key, item.metadata.get("fact_value", item.content)
    if isinstance(item.content, dict):
        asset_id = item.content.get("device_id") or item.content.get("asset_id")
        metric = item.content.get("metric")
        if asset_id and metric:
            value = item.content.get("value")
            points = item.content.get("points")
            if value is None and isinstance(points, list) and points:
                value = points[-1].get("value")
            return f"{asset_id}.{metric}", value
    if item.source_ref and item.version:
        return f"{item.source_ref}@{item.version}", item.content
    return "", None


def _limit_summary(summary: str, max_tokens: int) -> str:
    if estimate_tokens(summary) <= max_tokens:
        return summary
    return summary[: max_tokens * 4]
