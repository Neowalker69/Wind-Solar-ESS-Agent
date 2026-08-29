from __future__ import annotations

import re
from typing import Any, Protocol

from packages.rag.embedding import RagEmbeddingEncoder
from packages.rag.models import (
    RagSearchHit,
    RagSearchResponse,
    RetrievalCandidate,
)
from packages.rag.reranker import RagReranker, RagRerankerError


class RagSearchRepository(Protocol):
    index_version: str

    def search_lexical(self, **kwargs: Any) -> list[RetrievalCandidate]: ...

    def search_vector(self, **kwargs: Any) -> list[RetrievalCandidate]: ...


class HybridRagSearchService:
    def __init__(
        self,
        repository: RagSearchRepository,
        encoder: RagEmbeddingEncoder,
        *,
        reranker: RagReranker | None = None,
        candidate_k: int = 40,
        rerank_candidate_k: int = 20,
        rrf_constant: int = 60,
    ) -> None:
        self.repository = repository
        self.encoder = encoder
        self.reranker = reranker
        self.candidate_k = candidate_k
        self.rerank_candidate_k = max(1, rerank_candidate_k)
        self.rrf_constant = rrf_constant

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        include_superseded: bool = False,
        corpus_id: str | None = None,
    ) -> RagSearchResponse:
        normalized = query.strip()
        if not normalized:
            return RagSearchResponse(
                query=query,
                index_version=self.repository.index_version,
                embedding_model=self.encoder.model_id,
                results=[],
                warnings=["empty_query"],
            )
        requested_limit = max(1, min(limit, 20))
        candidate_limit = max(requested_limit, self.candidate_k)
        lexical = self.repository.search_lexical(
            query=normalized,
            limit=candidate_limit,
            include_superseded=include_superseded,
            corpus_id=corpus_id,
        )
        vector = self.repository.search_vector(
            query_embedding=self.encoder.encode_query(normalized),
            limit=candidate_limit,
            include_superseded=include_superseded,
            corpus_id=corpus_id,
        )
        merged: dict[str, dict[str, Any]] = {}
        for channel, candidates in (("lexical", lexical), ("vector", vector)):
            for position, candidate in enumerate(candidates, start=1):
                if candidate.status == "superseded" and not include_superseded:
                    continue
                entry = merged.setdefault(
                    candidate.chunk_id,
                    {"candidate": candidate, "fusion": 0.0},
                )
                entry["fusion"] += 1.0 / (self.rrf_constant + position)
                current = entry["candidate"]
                update = {
                    "lexical_score": max(current.lexical_score, candidate.lexical_score),
                    "vector_score": max(current.vector_score, candidate.vector_score),
                }
                entry["candidate"] = current.model_copy(update=update)
                if channel == "lexical":
                    entry["lexical_rank"] = position
                else:
                    entry["vector_rank"] = position
        exact_terms = _exact_terms(normalized)
        for entry in merged.values():
            haystack = entry["candidate"].text.casefold()
            entry["fusion"] += 0.02 * sum(
                1 for term in exact_terms if term.casefold() in haystack
            )
            entry["fusion"] += min(
                0.04,
                0.004 * _cjk_phrase_overlap(normalized, entry["candidate"].text),
            )
        fusion_ranked = sorted(
            merged.values(),
            key=lambda entry: (
                -float(entry["fusion"]),
                entry["candidate"].document_id,
                entry["candidate"].chunk_id,
            ),
        )
        warnings: list[str] = []
        ranked = fusion_ranked
        if self.reranker and fusion_ranked:
            rerank_pool = fusion_ranked[: self.rerank_candidate_k]
            try:
                scores = self.reranker.rerank(
                    normalized,
                    [entry["candidate"].text for entry in rerank_pool],
                )
                for entry, score in zip(rerank_pool, scores, strict=True):
                    entry["reranker_score"] = score
                ranked = sorted(
                    rerank_pool,
                    key=lambda entry: (
                        -float(entry["reranker_score"]),
                        -float(entry["fusion"]),
                        entry["candidate"].document_id,
                        entry["candidate"].chunk_id,
                    ),
                )
            except RagRerankerError:
                warnings.append("reranker_unavailable_fusion_fallback")
                ranked = fusion_ranked
        ranked = ranked[:requested_limit]
        results = []
        for rank, entry in enumerate(ranked, start=1):
            candidate: RetrievalCandidate = entry["candidate"]
            results.append(
                RagSearchHit(
                    **candidate.model_dump(),
                    rank=rank,
                    fusion_score=round(float(entry["fusion"]), 8),
                    reranker_score=(
                        round(float(entry["reranker_score"]), 8)
                        if "reranker_score" in entry
                        else None
                    ),
                    citation={
                        "document_id": candidate.document_id,
                        "chunk_id": candidate.chunk_id,
                        "source_ref": candidate.source_ref,
                        "version": candidate.version,
                        "content_hash": candidate.content_hash,
                        "heading": candidate.heading,
                        "line_start": candidate.line_start,
                        "line_end": candidate.line_end,
                    },
                )
            )
        return RagSearchResponse(
            query=normalized,
            index_version=self.repository.index_version,
            embedding_model=self.encoder.model_id,
            reranker_model=self.reranker.model_id if self.reranker else None,
            results=results,
            lexical_candidate_count=len(lexical),
            vector_candidate_count=len(vector),
            warnings=warnings,
        )


class EmptyTestRagSearchService:
    """仅供无 PostgreSQL 的确定性测试配置使用。"""

    def search(self, query: str, **_kwargs: Any) -> RagSearchResponse:
        return RagSearchResponse(
            query=query,
            index_version="test-unindexed",
            embedding_model="test-none",
            results=[],
            warnings=["rag_index_unavailable_in_test_profile"],
        )


def _exact_terms(query: str) -> set[str]:
    return {
        *re.findall(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b", query.upper()),
        *re.findall(r"\b\d+(?:\.\d+)?\s*(?:ppm|°?C|MΩ|kΩ|bar|Hz/s|A|V|kW)\b", query, re.I),
    }


def _cjk_phrase_overlap(query: str, text: str) -> int:
    """Reward answer chunks that preserve multi-character Chinese query phrases.

    zhparser can produce no useful lexical score for some mixed Chinese/Latin
    queries. Character trigrams provide a small deterministic tie-breaker while
    keeping vector similarity as the primary rank signal.
    """

    query_runs = re.findall(r"[\u4e00-\u9fff]{3,}", query)
    text_value = text.casefold()
    phrases = {
        run[index : index + 3]
        for run in query_runs
        for index in range(len(run) - 2)
        if run[index : index + 3] not in {"最新偏", "是多少", "扭矩是"}
    }
    return sum(phrase in text_value for phrase in phrases)
