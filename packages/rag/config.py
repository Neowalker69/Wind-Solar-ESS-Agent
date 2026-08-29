from __future__ import annotations

from dataclasses import dataclass
import os

from packages.rag.embedding import (
    BailianEmbeddingEncoder,
    LocalQwenEmbeddingEncoder,
    RagEmbeddingEncoder,
    RagEmbeddingError,
)
from packages.rag.reranker import RagReranker, RagRerankerError, TeiReranker


DEFAULT_RAG_EMBEDDING_PROVIDER = "bailian"
DEFAULT_RAG_EMBEDDING_MODEL = "qwen3.7-text-embedding"
DEFAULT_RAG_EMBEDDING_DIMENSIONS = 1024
DEFAULT_BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LOCAL_QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_RAG_RERANKER_PROVIDER = "tei"
DEFAULT_RAG_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_RAG_RERANKER_BASE_URL = "http://harness-reranker:80"


@dataclass(frozen=True)
class RagEmbeddingConfig:
    provider: str = DEFAULT_RAG_EMBEDDING_PROVIDER
    model: str = DEFAULT_RAG_EMBEDDING_MODEL
    dimensions: int = DEFAULT_RAG_EMBEDDING_DIMENSIONS
    api_key: str | None = None
    base_url: str = DEFAULT_BAILIAN_BASE_URL
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class RagRerankerConfig:
    provider: str = DEFAULT_RAG_RERANKER_PROVIDER
    model: str = DEFAULT_RAG_RERANKER_MODEL
    base_url: str = DEFAULT_RAG_RERANKER_BASE_URL
    timeout_seconds: float = 15.0
    candidate_k: int = 20


def load_rag_embedding_config() -> RagEmbeddingConfig:
    provider = os.getenv("RAG_EMBEDDING_PROVIDER", DEFAULT_RAG_EMBEDDING_PROVIDER).strip().lower()
    default_model = DEFAULT_LOCAL_QWEN_MODEL if provider == "local" else DEFAULT_RAG_EMBEDDING_MODEL
    return RagEmbeddingConfig(
        provider=provider,
        model=os.getenv("RAG_EMBEDDING_MODEL", default_model),
        dimensions=int(
            os.getenv("RAG_EMBEDDING_DIMENSIONS", str(DEFAULT_RAG_EMBEDDING_DIMENSIONS))
        ),
        api_key=(
            os.getenv("RAG_EMBEDDING_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("BAILIAN_API_KEY")
        ),
        base_url=os.getenv("RAG_EMBEDDING_BASE_URL", DEFAULT_BAILIAN_BASE_URL),
        timeout_seconds=float(os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "30")),
    )


def load_rag_reranker_config() -> RagRerankerConfig:
    return RagRerankerConfig(
        provider=os.getenv(
            "RAG_RERANKER_PROVIDER", DEFAULT_RAG_RERANKER_PROVIDER
        ).strip().lower(),
        model=os.getenv("RAG_RERANKER_MODEL", DEFAULT_RAG_RERANKER_MODEL),
        base_url=os.getenv("RAG_RERANKER_BASE_URL", DEFAULT_RAG_RERANKER_BASE_URL),
        timeout_seconds=float(os.getenv("RAG_RERANKER_TIMEOUT_SECONDS", "15")),
        candidate_k=max(1, int(os.getenv("RAG_RERANKER_CANDIDATE_K", "20"))),
    )


def build_rag_embedding_encoder(
    config: RagEmbeddingConfig | None = None,
) -> RagEmbeddingEncoder:
    selected = config or load_rag_embedding_config()
    if selected.provider == "bailian":
        return BailianEmbeddingEncoder(
            api_key=selected.api_key or "",
            model=selected.model,
            dimensions=selected.dimensions,
            base_url=selected.base_url,
            timeout_seconds=selected.timeout_seconds,
        )
    if selected.provider == "local":
        return LocalQwenEmbeddingEncoder(
            model_name_or_path=selected.model,
            dimensions=selected.dimensions,
        )
    raise RagEmbeddingError(f"rag_embedding_provider_unsupported:{selected.provider}")


def build_rag_reranker(config: RagRerankerConfig | None = None) -> RagReranker:
    selected = config or load_rag_reranker_config()
    if selected.provider == "tei":
        return TeiReranker(
            base_url=selected.base_url,
            model=selected.model,
            timeout_seconds=selected.timeout_seconds,
        )
    raise RagRerankerError(f"rag_reranker_provider_unsupported:{selected.provider}")
