from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Protocol

from packages.harness_common.schemas.context import (
    ContextItem,
    ContextKind,
    ContextRequest,
    ContextScope,
    ContextPlan,
)
from packages.harness_common.schemas.tool_result import ToolResult, ToolResultStatus
from packages.tool_registry.registry import (
    CapabilityRegistry,
    ToolExecutionContext,
)


class ContextToolGateway(Protocol):
    def execute(self, tool_id: str, payload: dict[str, Any]) -> ToolResult: ...


class CapabilityContextToolGateway:
    """把 Context Engine 接到正式 Capability Registry 执行边界。"""

    def __init__(
        self,
        registry: CapabilityRegistry,
        execution_context: ToolExecutionContext,
    ) -> None:
        self.registry = registry
        self.execution_context = execution_context

    def execute(self, tool_id: str, payload: dict[str, Any]) -> ToolResult:
        services = dict(self.execution_context.services)
        services["workspace_root"] = (
            Path(os.getenv("AGENT_HARNESS_RAG_ROOT", str(Path.cwd() / "rag_dataset_20docs")))
            if tool_id == "search.search_sop" else Path.cwd()
        )
        context = ToolExecutionContext(
            run=self.execution_context.run,
            registry=self.registry,
            user=dict(self.execution_context.user),
            services=services,
        )
        return self.registry.execute_for_model(tool_id, payload, context)


_DEFAULT_TOOLS = {
    "scene": "runtime_context.get_selected_asset_context",
    "workflow_stage": "runtime_context.get_active_workflow_state",
    "policy": "runtime_context.get_policy_context",
    "telemetry": "telemetry.get_timeseries",
    "alarm": "alarm.get_active_alarms",
    "skill": "skill.search_skill",
    "retrieval": "search.search_sop",
    "memory": "memory.memory_search",
}


class ToolGatewayContextProvider:
    """把 Context Provider 统一约束为只读 Tool Gateway 调用。"""

    def __init__(
        self,
        *,
        name: str,
        kind: ContextKind,
        gateway: ContextToolGateway,
    ) -> None:
        self.name = name
        self.kind = kind
        self.gateway = gateway

    def fetch(
        self,
        request: ContextRequest,
        scope: ContextScope,
        required_types: set[str],
    ) -> list[ContextItem]:
        if str(self.kind) not in required_types:
            return []
        plan = ContextPlan.model_validate(
            request.runtime_context.get("context_plan") or {}
        )
        queries = list(plan.provider_queries.get(self.name) or [])
        if not queries:
            queries = [{"tool_id": _DEFAULT_TOOLS[self.name]}]
        items: list[ContextItem] = []
        for position, query in enumerate(queries):
            tool_id = str(query.get("tool_id") or _DEFAULT_TOOLS[self.name])
            payload = self._payload(
                request=request,
                scope=scope,
                plan=plan,
                query=query,
                tool_id=tool_id,
            )
            result = self.gateway.execute(tool_id, payload)
            if result.status is ToolResultStatus.FAILED:
                code = str((result.error or {}).get("code") or "tool_execution_failed")
                raise RuntimeError(f"context_tool_failed:{tool_id}:{code}")
            if result.status is ToolResultStatus.NO_DATA:
                continue
            records = result.data if isinstance(result.data, list) else [result.data]
            items.extend(
                self._item(
                    request=request,
                    scope=scope,
                    result=result,
                    data=data,
                    tool_id=tool_id,
                    position=position * 1_000 + record_position,
                )
                for record_position, data in enumerate(records)
            )
        return items
    @staticmethod
    def _payload(
        *,
        request: ContextRequest,
        scope: ContextScope,
        plan: ContextPlan,
        query: dict[str, Any],
        tool_id: str,
    ) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in query.items()
            if key != "tool_id" and value is not None
        }
        if scope.site_id:
            payload.setdefault("site_id", scope.site_id)
        if scope.asset_id:
            payload.setdefault("asset_id", scope.asset_id)
        if tool_id in {
            "skill.search_skill",
            "search.search_sop",
            "memory.memory_search",
        }:
            payload.setdefault("query", request.query)
        if tool_id == "memory.memory_search":
            payload.setdefault("limit", 8)
        if tool_id == "telemetry.get_timeseries":
            hours = _window_hours(plan.time_window)
            start = request.now - timedelta(hours=hours)
            payload.setdefault("start", _iso_z(start))
            payload.setdefault("end", _iso_z(request.now))
            payload.setdefault("interval", "5m")
            payload.setdefault("aggregation", "avg")
        return payload

    def _item(
        self,
        *,
        request: ContextRequest,
        scope: ContextScope,
        result: ToolResult,
        data: Any,
        tool_id: str,
        position: int,
    ) -> ContextItem:
        primary = (
            dict(result.source_refs[min(position, len(result.source_refs) - 1)])
            if result.source_refs
            else {}
        )
        inferred = data if isinstance(data, dict) else {}
        source_ref = str(
            primary.get("source_ref")
            or inferred.get("source_ref")
            or _record_source_ref(self.kind, inferred)
            or f"tool:{tool_id}:{_content_digest(data)}"
        )
        source_timestamp = _datetime_or_none(
            primary.get("fact_time")
            or primary.get("observed_at")
            or inferred.get("source_timestamp")
            or inferred.get("created_at")
            or (result.observed_at if result.source_refs else request.now)
        )
        version = str(
            primary.get("version")
            or primary.get("source_version")
            or inferred.get("version")
            or "current"
        )
        item_id = str(
            inferred.get("memory_id")
            or inferred.get("skill_id")
            or f"{self.name}:{_content_digest([source_ref, version, data, position])}"
        )
        return ContextItem(
            id=item_id,
            kind=self.kind,
            content=data,
            summary=inferred.get("summary"),
            source="tool_gateway",
            source_ref=source_ref,
            created_at=source_timestamp or request.now,
            source_timestamp=source_timestamp,
            retrieved_at=request.now,
            version=version,
            relevance=max(0.0, min(1.0, float(inferred.get("relevance_score", 0.9)))),
            authority=(
                1.0
                if inferred.get("status") == "active" and result.quality.value == "good"
                else (0.65 if result.quality.value == "good" else 0.5)
            ),
            freshness=1.0 if inferred.get("status") != "superseded" else 0.0,
            utility=0.85,
            data_quality=1.0 if result.quality.value == "good" else 0.5,
            pinned=self.kind in {ContextKind.POLICY, ContextKind.WORKFLOW_STAGE},
            metadata={
                "provider": self.name,
                "tool_id": tool_id,
                "source_refs": result.source_refs,
                "tenant_id": scope.tenant_id,
                "site_id": scope.site_id,
                "user_id": scope.user_id,
                "asset_id": scope.asset_id,
                "retrieval_rank": inferred.get("rank"),
                "fusion_score": inferred.get("fusion_score"),
                "lexical_score": inferred.get("lexical_score"),
                "vector_score": inferred.get("vector_score"),
                "index_version": inferred.get("index_version"),
                "embedding_model": inferred.get("embedding_model"),
            },
        )


def build_tool_gateway_context_providers(
    gateway: ContextToolGateway,
) -> list[ToolGatewayContextProvider]:
    return [
        ToolGatewayContextProvider(name="scene", kind=ContextKind.SCENE, gateway=gateway),
        ToolGatewayContextProvider(
            name="workflow_stage",
            kind=ContextKind.WORKFLOW_STAGE,
            gateway=gateway,
        ),
        ToolGatewayContextProvider(name="policy", kind=ContextKind.POLICY, gateway=gateway),
        ToolGatewayContextProvider(
            name="telemetry", kind=ContextKind.TELEMETRY, gateway=gateway
        ),
        ToolGatewayContextProvider(name="alarm", kind=ContextKind.ALARM, gateway=gateway),
        ToolGatewayContextProvider(name="skill", kind=ContextKind.SKILL, gateway=gateway),
        ToolGatewayContextProvider(
            name="retrieval", kind=ContextKind.RETRIEVAL, gateway=gateway
        ),
        ToolGatewayContextProvider(name="memory", kind=ContextKind.MEMORY, gateway=gateway),
    ]


def _window_hours(value: str | None) -> int:
    if value and value.endswith("h") and value[:-1].isdigit():
        return max(1, int(value[:-1]))
    return 2


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        resolved = value
    elif value:
        try:
            resolved = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=timezone.utc)
    return resolved


def _content_digest(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def _record_source_ref(kind: ContextKind, value: dict[str, Any]) -> str | None:
    if kind is ContextKind.SKILL and value.get("skill_id"):
        return f"skill:{value['skill_id']}"
    if kind is ContextKind.RETRIEVAL and value.get("path"):
        return f"sop:{value['path']}:{value.get('line', '*')}"
    return None


class RuntimeContextProvider:
    name = "runtime"

    def fetch(
        self,
        request: ContextRequest,
        scope: ContextScope,
        required_types: set[str],
    ) -> list[ContextItem]:
        items = [
            ContextItem(
                id=f"task:{request.runtime_context.get('run_id', 'current')}",
                kind=ContextKind.TASK_STATE,
                content={
                    "user_turn": request.query,
                    "intent": request.intent,
                    "asset_id": scope.asset_id,
                    "workflow_stage": scope.workflow_stage,
                },
                source="agent_runtime",
                created_at=request.now,
                retrieved_at=request.now,
                relevance=1.0,
                authority=1.0,
                freshness=1.0,
                utility=1.0,
                pinned=True,
                metadata={
                    "tenant_id": scope.tenant_id,
                    "site_id": scope.site_id,
                    "user_id": scope.user_id,
                    "asset_id": scope.asset_id,
                },
            )
        ]
        return items
