from __future__ import annotations

import json
import os

from packages.rag.authoritative_corpus import default_corpus_root
from packages.rag.config import build_rag_embedding_encoder
from packages.rag.indexer import CorpusIndexer
from packages.rag.postgres import PostgresRagRepository
from packages.storage.postgres_connection import (
    build_postgres_connection_factory,
    ensure_repository_schema,
)


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("rag_index_database_url_missing")
    connection_factory = build_postgres_connection_factory(database_url)
    ensure_repository_schema(connection_factory)
    encoder = build_rag_embedding_encoder()
    report = CorpusIndexer(
        PostgresRagRepository(connection_factory),
        encoder,
        batch_size=int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "10")),
    ).index_root(
        default_corpus_root(),
        corpus_id=os.getenv("RAG_CORPUS_ID", "wind-sun-storage-authoritative"),
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
