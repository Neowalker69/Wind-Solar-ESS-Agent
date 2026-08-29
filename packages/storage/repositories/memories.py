from datetime import datetime
import json
import re

from packages.harness_common.schemas.memory import MemoryRecord, MemoryStatus
from packages.storage.repositories.base import InMemoryRepository


class MemoryRepository(InMemoryRepository[MemoryRecord]):
    table_name = "memory_records"
    id_field = "memory_id"
    model_type = MemoryRecord

    def retrieve(self, query_embedding: list[float], limit: int = 5) -> list[tuple[MemoryRecord, float]]:
        scored: list[tuple[MemoryRecord, float]] = []
        for memory in self.list_all():
            if not memory.embedding:
                continue
            score = sum(a * b for a, b in zip(query_embedding, memory.embedding, strict=False))
            scored.append((memory, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    def search(
        self,
        *,
        query: str,
        query_embedding: list[float],
        tenant_id: str,
        site_id: str | None,
        user_id: str | None,
        asset_id: str | None,
        now: datetime,
        project_id: str | None = None,
        limit: int = 5,
    ) -> list[tuple[MemoryRecord, float]]:
        query_terms = set(re.findall(r"[a-z0-9_.:-]+|[\u3400-\u9fff]", query.lower()))
        scored: list[tuple[MemoryRecord, float]] = []
        for memory in self.list_all():
            if memory.status != MemoryStatus.ACTIVE:
                continue
            if memory.expires_at is not None and memory.expires_at <= now:
                continue
            if memory.valid_from is not None and memory.valid_from > now:
                continue
            if memory.valid_to is not None and memory.valid_to <= now:
                continue
            if memory.tenant_id != tenant_id:
                continue
            if site_id and memory.site_id not in (None, site_id):
                continue
            if user_id and memory.user_id not in (None, user_id):
                continue
            if asset_id and memory.asset_id not in (None, asset_id):
                continue
            if project_id and memory.project_id not in (None, project_id):
                continue
            content_text = json.dumps(memory.content, ensure_ascii=False, sort_keys=True)
            terms = set(re.findall(r"[a-z0-9_.:-]+|[\u3400-\u9fff]", content_text.lower()))
            lexical = len(query_terms & terms) / max(1, len(query_terms))
            vector = (
                sum(a * b for a, b in zip(query_embedding, memory.embedding, strict=False))
                if memory.embedding
                else 0.0
            )
            score = 0.45 * lexical + 0.40 * max(0.0, vector) + 0.15 * memory.importance
            if score > 0:
                scored.append((memory, score))
        return sorted(scored, key=lambda item: (-item[1], item[0].memory_id))[: max(1, min(limit, 50))]
