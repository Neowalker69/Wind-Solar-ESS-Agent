from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from packages.rag.models import RagChunk, RagDocument, RetrievalCandidate
from packages.storage.postgres_connection import ConnectionFactory


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.12g}" for value in values) + "]"


class PostgresRagRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    @property
    def index_version(self) -> str:
        with self.connection_factory() as connection:
            row = connection.execute(
                """
                SELECT index_version
                FROM rag_index_runs
                WHERE status = 'completed'
                ORDER BY completed_at DESC NULLS LAST
                LIMIT 1
                """
            ).fetchone()
        return str(row["index_version"]) if row else "unindexed"

    def search_lexical(
        self,
        *,
        query: str,
        limit: int,
        include_superseded: bool,
        corpus_id: str | None,
    ) -> list[RetrievalCandidate]:
        where, params = self._filters(
            include_superseded=include_superseded,
            corpus_id=corpus_id,
        )
        params.update(query=query, limit=max(1, min(limit, 100)))
        sql = f"""
            SELECT
                c.chunk_id, c.document_id, d.title, d.version, d.status,
                c.content AS text, c.source_ref, c.content_hash,
                c.heading, c.line_start, c.line_end,
                ts_rank_cd(
                    c.content_tsv,
                    websearch_to_tsquery('public.harness_zh', %(query)s)
                ) AS lexical_score,
                0.0::double precision AS vector_score
            FROM rag_chunks c
            JOIN rag_documents d
              ON d.corpus_id = c.corpus_id AND d.document_id = c.document_id
            WHERE {' AND '.join(where)}
              AND (
                c.content_tsv @@ websearch_to_tsquery('public.harness_zh', %(query)s)
                OR c.content ILIKE '%%' || %(query)s || '%%'
              )
            ORDER BY lexical_score DESC, c.chunk_id
            LIMIT %(limit)s
        """
        with self.connection_factory() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [RetrievalCandidate.model_validate(row) for row in rows]

    def search_vector(
        self,
        *,
        query_embedding: list[float],
        limit: int,
        include_superseded: bool,
        corpus_id: str | None,
    ) -> list[RetrievalCandidate]:
        if len(query_embedding) != 1024:
            raise ValueError("embedding_dimensions_mismatch")
        where, params = self._filters(
            include_superseded=include_superseded,
            corpus_id=corpus_id,
        )
        params.update(
            embedding=_vector_literal(query_embedding),
            limit=max(1, min(limit, 100)),
        )
        sql = f"""
            SELECT
                c.chunk_id, c.document_id, d.title, d.version, d.status,
                c.content AS text, c.source_ref, c.content_hash,
                c.heading, c.line_start, c.line_end,
                0.0::double precision AS lexical_score,
                GREATEST(0, 1 - (c.embedding <=> %(embedding)s::vector)) AS vector_score
            FROM rag_chunks c
            JOIN rag_documents d
              ON d.corpus_id = c.corpus_id AND d.document_id = c.document_id
            WHERE {' AND '.join(where)}
              AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %(embedding)s::vector, c.chunk_id
            LIMIT %(limit)s
        """
        with self.connection_factory() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [RetrievalCandidate.model_validate(row) for row in rows]

    @staticmethod
    def _filters(
        *,
        include_superseded: bool,
        corpus_id: str | None,
    ) -> tuple[list[str], dict[str, Any]]:
        where = ["c.active = TRUE", "d.active = TRUE"]
        params: dict[str, Any] = {}
        if not include_superseded:
            where.append("d.status <> 'superseded'")
        if corpus_id:
            where.append("c.corpus_id = %(corpus_id)s")
            params["corpus_id"] = corpus_id
        return where, params

    def start_index_run(self, **values: Any) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                INSERT INTO rag_index_runs (
                    run_id, corpus_id, index_version, status,
                    embedding_provider, embedding_model, embedding_dimensions,
                    metadata, started_at, updated_at
                ) VALUES (
                    %(run_id)s, %(corpus_id)s, %(index_version)s, %(status)s,
                    %(embedding_provider)s, %(embedding_model)s,
                    %(embedding_dimensions)s, %(metadata)s, now(), now()
                )
                ON CONFLICT (corpus_id, index_version) DO UPDATE SET
                    status = EXCLUDED.status,
                    embedding_provider = EXCLUDED.embedding_provider,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dimensions = EXCLUDED.embedding_dimensions,
                    metadata = EXCLUDED.metadata,
                    error_code = NULL,
                    completed_at = NULL,
                    updated_at = now()
                """,
                {**values, "metadata": Jsonb(values.get("metadata") or {})},
            )

    def replace_document(
        self,
        document: RagDocument,
        chunks: list[RagChunk],
        *,
        index_version: str,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                INSERT INTO rag_documents (
                    corpus_id, document_id, source_path, source_ref, title,
                    version, status, media_type, content_hash, parser_version,
                    index_version, active, metadata, updated_at, indexed_at
                ) VALUES (
                    %(corpus_id)s, %(document_id)s, %(source_path)s,
                    %(source_ref)s, %(title)s, %(version)s, %(status)s,
                    %(media_type)s, %(content_hash)s, %(parser_version)s,
                    %(index_version)s, TRUE, %(metadata)s, now(), now()
                )
                ON CONFLICT (corpus_id, document_id) DO UPDATE SET
                    source_path = EXCLUDED.source_path,
                    source_ref = EXCLUDED.source_ref,
                    title = EXCLUDED.title,
                    version = EXCLUDED.version,
                    status = EXCLUDED.status,
                    media_type = EXCLUDED.media_type,
                    content_hash = EXCLUDED.content_hash,
                    parser_version = EXCLUDED.parser_version,
                    index_version = EXCLUDED.index_version,
                    active = TRUE,
                    metadata = EXCLUDED.metadata,
                    updated_at = now(),
                    indexed_at = now()
                """,
                {
                    **document.model_dump(exclude={"text", "indexable", "exclusion_reason"}),
                    "parser_version": "authoritative-loader-v1",
                    "index_version": index_version,
                    "metadata": Jsonb(document.metadata),
                },
            )
            connection.execute(
                """
                UPDATE rag_chunks
                SET active = FALSE, updated_at = now()
                WHERE corpus_id = %s AND document_id = %s
                """,
                (document.corpus_id, document.document_id),
            )
            for chunk in chunks:
                connection.execute(
                    """
                    INSERT INTO rag_chunks (
                        chunk_id, corpus_id, document_id, ordinal, heading,
                        line_start, line_end, content, content_hash, token_count,
                        source_ref, embedding, embedding_provider,
                        embedding_model, embedding_dimensions, index_version,
                        active, metadata, updated_at
                    ) VALUES (
                        %(chunk_id)s, %(corpus_id)s, %(document_id)s,
                        %(ordinal)s, %(heading)s, %(line_start)s, %(line_end)s,
                        %(text)s, %(content_hash)s, %(token_count)s,
                        %(source_ref)s, %(embedding)s::vector,
                        %(embedding_provider)s, %(embedding_model)s,
                        %(embedding_dimensions)s, %(index_version)s,
                        TRUE, %(metadata)s, now()
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        heading = EXCLUDED.heading,
                        line_start = EXCLUDED.line_start,
                        line_end = EXCLUDED.line_end,
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        token_count = EXCLUDED.token_count,
                        source_ref = EXCLUDED.source_ref,
                        embedding = EXCLUDED.embedding,
                        embedding_provider = EXCLUDED.embedding_provider,
                        embedding_model = EXCLUDED.embedding_model,
                        embedding_dimensions = EXCLUDED.embedding_dimensions,
                        index_version = EXCLUDED.index_version,
                        active = TRUE,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    {
                        **chunk.model_dump(exclude={"embedding", "metadata"}),
                        "embedding": _vector_literal(chunk.embedding or []),
                        "embedding_provider": embedding_provider,
                        "embedding_model": embedding_model,
                        "embedding_dimensions": embedding_dimensions,
                        "index_version": index_version,
                        "metadata": Jsonb(chunk.metadata),
                    },
                )

    def mark_missing_documents(
        self,
        *,
        corpus_id: str,
        source_paths: set[str],
        index_version: str,
    ) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                UPDATE rag_documents
                SET active = FALSE, updated_at = now()
                WHERE corpus_id = %(corpus_id)s
                  AND NOT (source_path = ANY(%(source_paths)s))
                """,
                {
                    "corpus_id": corpus_id,
                    "source_paths": sorted(source_paths),
                    "index_version": index_version,
                },
            )
            connection.execute(
                """
                UPDATE rag_chunks c
                SET active = FALSE, updated_at = now()
                FROM rag_documents d
                WHERE d.corpus_id = c.corpus_id
                  AND d.document_id = c.document_id
                  AND d.corpus_id = %(corpus_id)s
                  AND d.active = FALSE
                """,
                {"corpus_id": corpus_id},
            )

    def finish_index_run(self, **values: Any) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                UPDATE rag_index_runs
                SET status = %(status)s,
                    document_count = %(document_count)s,
                    chunk_count = %(chunk_count)s,
                    excluded_document_count = %(excluded_document_count)s,
                    error_code = %(error_code)s,
                    metadata = %(metadata)s,
                    completed_at = now(),
                    updated_at = now()
                WHERE run_id = %(run_id)s
                """,
                {**values, "metadata": Jsonb(values.get("metadata") or {})},
            )
