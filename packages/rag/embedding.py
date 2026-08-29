from __future__ import annotations

from collections.abc import Callable, Sequence
import math
from typing import Any, Protocol


class RagEmbeddingError(RuntimeError):
    pass


class RagEmbeddingEncoder(Protocol):
    provider: str
    model_id: str
    dimensions: int

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def encode_query(self, text: str) -> list[float]: ...


EmbeddingTransport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class BailianEmbeddingEncoder:
    provider = "bailian"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen3.7-text-embedding",
        dimensions: int = 1024,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout_seconds: float = 30.0,
        transport: EmbeddingTransport | None = None,
    ) -> None:
        if not api_key:
            raise RagEmbeddingError("rag_embedding_api_key_missing:bailian")
        if dimensions <= 0:
            raise RagEmbeddingError("embedding_dimensions_invalid")
        self.api_key = api_key
        self.model_id = model
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._http_transport

    def encode_query(self, text: str) -> list[float]:
        return self.encode_documents([text])[0]

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        normalized = [str(text).strip() for text in texts]
        if not normalized or any(not text for text in normalized):
            raise RagEmbeddingError("embedding_input_empty")
        payload = {
            "model": self.model_id,
            "input": normalized,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }
        try:
            response = self.transport(
                f"{self.base_url}/embeddings",
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                payload,
                self.timeout_seconds,
            )
        except RagEmbeddingError:
            raise
        except Exception as exc:
            raise RagEmbeddingError("embedding_provider_request_failed") from exc
        rows = response.get("data") if isinstance(response, dict) else None
        if not isinstance(rows, list) or len(rows) != len(normalized):
            raise RagEmbeddingError("embedding_response_invalid")
        ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
        vectors: list[list[float]] = []
        for row in ordered:
            vector = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise RagEmbeddingError("embedding_dimensions_mismatch")
            values = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in values):
                raise RagEmbeddingError("embedding_values_invalid")
            vectors.append(values)
        return vectors

    @staticmethod
    def _http_transport(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        import httpx

        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RagEmbeddingError(
                f"embedding_provider_http_error:{response.status_code}"
            ) from exc
        value = response.json()
        if not isinstance(value, dict):
            raise RagEmbeddingError("embedding_response_invalid")
        return value


class LocalQwenEmbeddingEncoder:
    provider = "local"

    def __init__(
        self,
        *,
        model_name_or_path: str = "Qwen/Qwen3-Embedding-0.6B",
        dimensions: int = 1024,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.model_id = model_name_or_path
        self.dimensions = dimensions
        self.loader = loader or self._default_loader
        self._model: Any | None = None

    def encode_query(self, text: str) -> list[float]:
        return self.encode_documents([text])[0]

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        normalized = [str(text).strip() for text in texts]
        if not normalized or any(not text for text in normalized):
            raise RagEmbeddingError("embedding_input_empty")
        if self._model is None:
            self._model = self.loader(self.model_id)
        encoded = self._model.encode(
            normalized,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        vectors = [
            [float(value) for value in (row.tolist() if hasattr(row, "tolist") else row)]
            for row in encoded
        ]
        if len(vectors) != len(normalized) or any(
            len(vector) != self.dimensions for vector in vectors
        ):
            raise RagEmbeddingError("embedding_dimensions_mismatch")
        return vectors

    @staticmethod
    def _default_loader(model_name: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RagEmbeddingError("local_embedding_dependency_missing") from exc
        return SentenceTransformer(model_name, trust_remote_code=True)
