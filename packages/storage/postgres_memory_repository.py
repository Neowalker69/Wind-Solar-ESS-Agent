from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from packages.harness_common.schemas.memory import MemoryRecord
from packages.storage.postgres_connection import ConnectionFactory


def _vector_literal(values: list[float] | None) -> str | None:
    if values is None:
        return None
    return "[" + ",".join(f"{value:.12g}" for value in values) + "]"


class PostgresMemoryRepository:
    """在现有 memory_records 表上实现权威持久化与混合召回。"""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    def create(self, record: MemoryRecord) -> MemoryRecord:
        content_text = json.dumps(record.content, ensure_ascii=False, sort_keys=True)
        sql = """
            INSERT INTO memory_records (
                memory_id, memory_type, version, status, source_trace_ids,
                evidence_ids, confidence, embedding, payload, created_at,
                expires_at, tenant_id, site_id, user_id, asset_id, source_ref,
                summary, metadata, content_hash, importance, model_visible,
                tool_visible, updated_at, content_text, project_id, agent_id,
                idempotency_key, authority, risk_level, valid_from, valid_to,
                supersedes_memory_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (memory_id) DO UPDATE SET
                version = EXCLUDED.version,
                status = EXCLUDED.status,
                confidence = EXCLUDED.confidence,
                embedding = EXCLUDED.embedding,
                payload = EXCLUDED.payload,
                expires_at = EXCLUDED.expires_at,
                source_ref = EXCLUDED.source_ref,
                summary = EXCLUDED.summary,
                metadata = EXCLUDED.metadata,
                content_hash = EXCLUDED.content_hash,
                importance = EXCLUDED.importance,
                model_visible = EXCLUDED.model_visible,
                tool_visible = EXCLUDED.tool_visible,
                updated_at = EXCLUDED.updated_at,
                content_text = EXCLUDED.content_text,
                project_id = EXCLUDED.project_id,
                agent_id = EXCLUDED.agent_id,
                idempotency_key = EXCLUDED.idempotency_key,
                authority = EXCLUDED.authority,
                risk_level = EXCLUDED.risk_level,
                valid_from = EXCLUDED.valid_from,
                valid_to = EXCLUDED.valid_to,
                supersedes_memory_id = EXCLUDED.supersedes_memory_id
        """
        params = (
            record.memory_id,
            str(record.memory_type),
            record.version,
            str(record.status),
            Jsonb(record.source_trace_ids),
            Jsonb(record.evidence_ids),
            record.confidence,
            _vector_literal(record.embedding),
            Jsonb(record.model_dump(mode="json")),
            record.created_at,
            record.expires_at,
            record.tenant_id,
            record.site_id,
            record.user_id,
            record.asset_id,
            record.source_ref,
            record.summary,
            Jsonb(record.metadata),
            record.content_hash,
            record.importance,
            record.model_visible,
            record.tool_visible,
            record.updated_at,
            content_text,
            record.project_id,
            record.agent_id,
            record.idempotency_key,
            record.authority,
            record.risk_level,
            record.valid_from,
            record.valid_to,
            record.supersedes_memory_id,
        )
        with self.connection_factory() as connection:
            connection.execute(sql, params)
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self.connection_factory() as connection:
            row = connection.execute(
                "SELECT payload FROM memory_records WHERE memory_id = %s",
                (memory_id,),
            ).fetchone()
        return self._record(row)

    def list_all(self) -> list[MemoryRecord]:
        with self.connection_factory() as connection:
            rows = connection.execute(
                "SELECT payload FROM memory_records ORDER BY created_at"
            ).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]

    def delete(self, memory_id: str) -> bool:
        with self.connection_factory() as connection:
            row = connection.execute(
                "DELETE FROM memory_records WHERE memory_id = %s RETURNING 1",
                (memory_id,),
            ).fetchone()
        return row is not None

    def retrieve(
        self,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[tuple[MemoryRecord, float]]:
        with self.connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT payload, 1 - (embedding <=> %(embedding)s::vector) AS score
                FROM memory_records
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %(embedding)s::vector
                LIMIT %(limit)s
                """,
                {"embedding": _vector_literal(query_embedding), "limit": max(1, min(limit, 50))},
            ).fetchall()
        return self._scored(rows)

    def search(
        self,
        *,
        query: str,
        query_embedding: list[float],
        tenant_id: str,
        site_id: str | None,
        user_id: str | None,
        asset_id: str | None,
        now,
        project_id: str | None = None,
        limit: int = 5,
    ) -> list[tuple[MemoryRecord, float]]:
        where = [
            "status = 'active'",
            "tenant_id = %(tenant_id)s",
            "(expires_at IS NULL OR expires_at > %(now)s)",
            "(valid_from IS NULL OR valid_from <= %(now)s)",
            "(valid_to IS NULL OR valid_to > %(now)s)",
            "model_visible = TRUE",
        ]
        params: dict[str, Any] = {
            "query": query,
            "embedding": _vector_literal(query_embedding),
            "tenant_id": tenant_id,
            "now": now,
            "limit": max(1, min(limit, 50)),
        }
        for field, value in (
            ("site_id", site_id),
            ("user_id", user_id),
            ("asset_id", asset_id),
            ("project_id", project_id),
        ):
            if value:
                where.append(f"({field} IS NULL OR {field} = %({field})s)")
                params[field] = value
        sql = f"""
            SELECT payload,
                0.45 * ts_rank_cd(
                    content_tsv,
                    plainto_tsquery('public.harness_zh', %(query)s)
                )
                + 0.40 * GREATEST(0, 1 - (embedding <=> %(embedding)s::vector))
                + 0.15 * importance AS score
            FROM memory_records
            WHERE {' AND '.join(where)}
              AND (
                content_tsv @@ plainto_tsquery('public.harness_zh', %(query)s)
                OR content_text ILIKE '%%' || %(query)s || '%%'
                OR embedding IS NOT NULL
              )
            ORDER BY score DESC, created_at DESC
            LIMIT %(limit)s
        """
        with self.connection_factory() as connection:
            rows = connection.execute(sql, params).fetchall()
        return self._scored(rows)

    @staticmethod
    def _record(row: dict[str, Any] | None) -> MemoryRecord | None:
        if not row:
            return None
        value = row["payload"]
        if isinstance(value, str):
            value = json.loads(value)
        return MemoryRecord.model_validate(value)

    @classmethod
    def _scored(cls, rows: list[dict[str, Any]]) -> list[tuple[MemoryRecord, float]]:
        return [
            (record, float(row["score"]))
            for row in rows
            if (record := cls._record(row)) is not None
        ]
