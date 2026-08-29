from __future__ import annotations

import json
import os
from pathlib import Path

from packages.rag.config import (
    build_rag_embedding_encoder,
    build_rag_reranker,
    load_rag_reranker_config,
)
from packages.rag.evaluation import evaluate_retrieval, load_eval_cases
from packages.rag.postgres import PostgresRagRepository
from packages.rag.search import HybridRagSearchService
from packages.storage.postgres_connection import build_postgres_connection_factory


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("rag_evaluation_database_url_missing")
    dataset = Path(
        os.getenv(
            "RAG_EVAL_DATASET",
            str(Path(__file__).parents[2] / "evals" / "rag_acceptance_v1.json"),
        )
    )
    k = int(os.getenv("RAG_EVAL_K", "5"))
    cases = load_eval_cases(dataset)
    reranker_config = load_rag_reranker_config()
    service = HybridRagSearchService(
        PostgresRagRepository(build_postgres_connection_factory(database_url)),
        build_rag_embedding_encoder(),
        reranker=build_rag_reranker(reranker_config),
        rerank_candidate_k=reranker_config.candidate_k,
    )
    corpus_id = os.getenv("RAG_CORPUS_ID", "wind-sun-storage-authoritative")
    results = {
        case.query_id: service.search(
            case.query,
            limit=k,
            corpus_id=corpus_id,
        ).results
        for case in cases
    }
    report = evaluate_retrieval(cases, results, k=k)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
