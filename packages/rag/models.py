from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class RagDocument(BaseModel):
    corpus_id: str
    document_id: str
    source_path: str
    source_ref: str
    title: str
    version: str
    status: str
    media_type: str
    content_hash: str
    text: str = ""
    indexable: bool = True
    exclusion_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagChunk(BaseModel):
    chunk_id: str
    corpus_id: str
    document_id: str
    ordinal: int
    heading: str | None = None
    line_start: int
    line_end: int
    text: str
    content_hash: str
    token_count: int
    source_ref: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalCandidate(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    version: str
    status: str
    text: str
    source_ref: str
    content_hash: str
    heading: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    lexical_score: float = 0.0
    vector_score: float = 0.0


class RagSearchHit(RetrievalCandidate):
    rank: int
    fusion_score: float
    reranker_score: float | None = None
    citation: dict[str, Any] = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    query: str
    index_version: str
    embedding_model: str
    reranker_model: str | None = None
    results: list[RagSearchHit]
    lexical_candidate_count: int = 0
    vector_candidate_count: int = 0
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    warnings: list[str] = Field(default_factory=list)
