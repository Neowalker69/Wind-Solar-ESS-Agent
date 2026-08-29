from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from packages.harness_common.schemas.memory import MemoryRecord, MemoryStatus
from packages.memory.embedding import HashingMemoryEncoder, MemoryEncoder
from packages.memory.filters import mark_conflict, validate_provenance
from packages.storage.repositories.memories import MemoryRepository


class MemoryService:
    def __init__(
        self,
        repo: MemoryRepository | None = None,
        encoder: MemoryEncoder | None = None,
    ) -> None:
        self.repo = repo or MemoryRepository()
        self.encoder = encoder or HashingMemoryEncoder()

    def create_candidate(self, memory: MemoryRecord) -> MemoryRecord:
        memory = validate_provenance(memory)
        for existing in self.repo.list_all():
            if (
                memory.idempotency_key
                and existing.idempotency_key == memory.idempotency_key
                and existing.tenant_id == memory.tenant_id
            ):
                return existing
        content_text = json.dumps(memory.content, ensure_ascii=False, sort_keys=True)
        content_hash = memory.content_hash or sha256(content_text.encode("utf-8")).hexdigest()
        memory = memory.model_copy(
            update={
                "content_hash": content_hash,
                "embedding": memory.embedding or self.encoder.encode(content_text),
                "summary": memory.summary or str(memory.content.get("summary") or content_text[:320]),
                "updated_at": datetime.now(timezone.utc),
                "status": MemoryStatus.CANDIDATE,
            }
        )
        duplicate = next(
            (
                existing
                for existing in self.repo.list_all()
                if existing.content_hash == content_hash
                and existing.tenant_id == memory.tenant_id
                and existing.site_id == memory.site_id
                and existing.user_id == memory.user_id
                and existing.asset_id == memory.asset_id
                and existing.project_id == memory.project_id
                and existing.agent_id == memory.agent_id
                and existing.memory_type == memory.memory_type
            ),
            None,
        )
        if duplicate is not None:
            return duplicate
        conflicts = [
            existing
            for existing in self.repo.list_all()
            if existing.status is MemoryStatus.ACTIVE
            and _same_scope(existing, memory)
            and _fact_key(existing) is not None
            and _fact_key(existing) == _fact_key(memory)
            and existing.content_hash != memory.content_hash
        ]
        history = [
            *memory.lifecycle_history,
            _lifecycle_event("candidate_created", "memory_runtime", "candidate_ingested"),
        ]
        if conflicts:
            memory = memory.model_copy(
                update={
                    "status": MemoryStatus.CONFLICTED,
                    "metadata": {
                        **memory.metadata,
                        "conflicts_with": sorted(
                            existing.memory_id for existing in conflicts
                        ),
                    },
                    "lifecycle_history": [
                        *history,
                        _lifecycle_event(
                            "conflict_detected",
                            "memory_runtime",
                            "active_fact_has_different_value",
                        ),
                    ],
                }
            )
        else:
            memory = memory.model_copy(update={"lifecycle_history": history})
        existing = self.repo.get(memory.memory_id)
        if existing and existing.content != memory.content:
            # 相同 memory_id 出现不同内容时先标记冲突，交由人工/评估流程处理，避免静默覆盖已激活知识。
            return self.repo.create(mark_conflict(memory))
        return self.repo.create(memory)

    def validate(
        self,
        memory_id: str,
        *,
        validated_by: str,
        reason: str,
    ) -> MemoryRecord:
        memory = self.repo.get(memory_id)
        if memory is None:
            raise KeyError("memory_not_found")
        if memory.status is not MemoryStatus.CANDIDATE:
            raise ValueError("memory_not_candidate")
        validated = memory.model_copy(
            update={
                "status": MemoryStatus.VALIDATED,
                "updated_at": datetime.now(timezone.utc),
                "lifecycle_history": [
                    *memory.lifecycle_history,
                    _lifecycle_event("validated", validated_by, reason),
                ],
            }
        )
        return self.repo.create(validated)

    def promote(
        self,
        memory_id: str,
        *,
        promoted_by: str,
        reason: str,
    ) -> MemoryRecord:
        memory = self.repo.get(memory_id)
        if memory is None:
            raise KeyError("memory_not_found")
        if memory.status is not MemoryStatus.VALIDATED:
            raise ValueError("memory_not_validated")
        now = datetime.now(timezone.utc)
        active_conflicts = [
            existing
            for existing in self.repo.list_all()
            if existing.status is MemoryStatus.ACTIVE
            and existing.memory_id != memory.memory_id
            and _same_scope(existing, memory)
            and _fact_key(existing) is not None
            and _fact_key(existing) == _fact_key(memory)
        ]
        if active_conflicts and not memory.supersedes_memory_id:
            raise ValueError("active_memory_conflict_requires_resolution")
        if memory.supersedes_memory_id:
            previous = self.repo.get(memory.supersedes_memory_id)
            if previous is None or previous.status is not MemoryStatus.ACTIVE:
                raise ValueError("superseded_memory_not_active")
            self.repo.create(
                previous.model_copy(
                    update={
                        "status": MemoryStatus.SUPERSEDED,
                        "valid_to": now,
                        "updated_at": now,
                        "lifecycle_history": [
                            *previous.lifecycle_history,
                            _lifecycle_event("superseded", promoted_by, reason),
                        ],
                    }
                )
            )
        promoted = memory.model_copy(
            update={
                "status": MemoryStatus.ACTIVE,
                "valid_from": memory.valid_from or memory.created_at,
                "valid_to": None,
                "updated_at": now,
                "lifecycle_history": [
                    *memory.lifecycle_history,
                    _lifecycle_event("promoted", promoted_by, reason),
                ],
            }
        )
        return self.repo.create(promoted)

    def activate(self, memory_id: str) -> MemoryRecord:
        return self.promote(
            memory_id,
            promoted_by="legacy_api",
            reason="validated_candidate_activation",
        )

    def resolve_conflict(
        self,
        memory_id: str,
        *,
        supersede_memory_id: str,
        resolved_by: str,
        reason: str,
    ) -> MemoryRecord:
        memory = self.repo.get(memory_id)
        previous = self.repo.get(supersede_memory_id)
        if memory is None or previous is None:
            raise KeyError("memory_not_found")
        conflicts_with = set(memory.metadata.get("conflicts_with") or [])
        if (
            memory.status is not MemoryStatus.CONFLICTED
            or supersede_memory_id not in conflicts_with
            or previous.status is not MemoryStatus.ACTIVE
        ):
            raise ValueError("memory_conflict_resolution_invalid")
        resolved = memory.model_copy(
            update={
                "status": MemoryStatus.VALIDATED,
                "supersedes_memory_id": supersede_memory_id,
                "updated_at": datetime.now(timezone.utc),
                "lifecycle_history": [
                    *memory.lifecycle_history,
                    _lifecycle_event("conflict_resolved", resolved_by, reason),
                ],
            }
        )
        return self.repo.create(resolved)

    def rollback(
        self,
        memory_id: str,
        *,
        rolled_back_by: str,
        reason: str,
    ) -> MemoryRecord:
        current = self.repo.get(memory_id)
        if (
            current is None
            or current.status is not MemoryStatus.ACTIVE
            or not current.supersedes_memory_id
        ):
            raise ValueError("memory_rollback_unavailable")
        previous = self.repo.get(current.supersedes_memory_id)
        if previous is None:
            raise KeyError("memory_not_found")
        now = datetime.now(timezone.utc)
        self.repo.create(
            current.model_copy(
                update={
                    "status": MemoryStatus.SUPERSEDED,
                    "valid_to": now,
                    "updated_at": now,
                    "lifecycle_history": [
                        *current.lifecycle_history,
                        _lifecycle_event("rolled_back", rolled_back_by, reason),
                    ],
                }
            )
        )
        restored = previous.model_copy(
            update={
                "status": MemoryStatus.ACTIVE,
                "valid_to": None,
                "updated_at": now,
                "lifecycle_history": [
                    *previous.lifecycle_history,
                    _lifecycle_event("restored", rolled_back_by, reason),
                ],
            }
        )
        return self.repo.create(restored)

    def expire(self, memory_id: str) -> MemoryRecord:
        memory = self.repo.get(memory_id)
        if memory is None:
            raise KeyError("memory_not_found")
        now = datetime.now(timezone.utc)
        expired = memory.model_copy(
            update={
                "status": MemoryStatus.EXPIRED,
                "expires_at": memory.expires_at or now,
                "updated_at": now,
            }
        )
        return self.repo.create(expired)

    def delete(self, memory_id: str) -> bool:
        return self.repo.delete(memory_id)

    def retrieve(self, embedding: list[float]) -> list[dict]:
        return [
            {"memory_id": memory.memory_id, "version": memory.version, "score": score, "provenance": memory.source_trace_ids}
            for memory, score in self.repo.retrieve(embedding)
        ]

    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        site_id: str | None = None,
        user_id: str | None = None,
        asset_id: str | None = None,
        project_id: str | None = None,
        now: datetime | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        results = self.repo.search(
            query=query,
            query_embedding=self.encoder.encode(query),
            tenant_id=tenant_id,
            site_id=site_id,
            user_id=user_id,
            asset_id=asset_id,
            project_id=project_id,
            now=now or datetime.now(timezone.utc),
            limit=limit,
        )
        recalled: list[tuple[MemoryRecord, float]] = []
        recalled_at = now or datetime.now(timezone.utc)
        for memory, score in results:
            updated = memory.model_copy(
                update={
                    "recall_count": memory.recall_count + 1,
                    "last_recalled_at": recalled_at,
                    "updated_at": recalled_at,
                }
            )
            self.repo.create(updated)
            recalled.append((updated, score))
        return [
            {
                **memory.model_dump(mode="json"),
                "score": round(float(score), 6),
            }
            for memory, score in recalled
        ]


def _fact_key(memory: MemoryRecord) -> str | None:
    value = memory.metadata.get("fact_key")
    return str(value) if value else None


def _same_scope(first: MemoryRecord, second: MemoryRecord) -> bool:
    return all(
        getattr(first, field) == getattr(second, field)
        for field in (
            "tenant_id",
            "site_id",
            "user_id",
            "project_id",
            "agent_id",
            "asset_id",
            "memory_type",
        )
    )


def _lifecycle_event(action: str, actor_id: str, reason: str) -> dict[str, str]:
    return {
        "action": action,
        "actor_id": actor_id,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
