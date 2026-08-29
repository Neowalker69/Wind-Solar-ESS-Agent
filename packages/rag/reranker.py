from __future__ import annotations

from collections.abc import Callable, Sequence
import math
from typing import Any, Protocol


class RagRerankerError(RuntimeError):
    pass


class RagReranker(Protocol):
    model_id: str

    def rerank(self, query: str, texts: Sequence[str]) -> list[float]: ...


RerankerTransport = Callable[[str, dict[str, Any], float], Any]


class TeiReranker:
    """Synchronous client for Hugging Face TEI's `/rerank` endpoint."""

    provider = "tei"

    def __init__(
        self,
        *,
        base_url: str,
        model: str = "BAAI/bge-reranker-v2-m3",
        timeout_seconds: float = 15.0,
        transport: RerankerTransport | None = None,
    ) -> None:
        if not base_url.strip():
            raise RagRerankerError("reranker_base_url_missing")
        if timeout_seconds <= 0:
            raise RagRerankerError("reranker_timeout_invalid")
        self.base_url = base_url.rstrip("/")
        self.model_id = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._http_transport

    def rerank(self, query: str, texts: Sequence[str]) -> list[float]:
        normalized_query = str(query).strip()
        normalized_texts = [str(text).strip() for text in texts]
        if not normalized_query or not normalized_texts or any(
            not text for text in normalized_texts
        ):
            raise RagRerankerError("reranker_input_empty")
        try:
            response = self.transport(
                f"{self.base_url}/rerank",
                {"query": normalized_query, "texts": normalized_texts},
                self.timeout_seconds,
            )
        except RagRerankerError:
            raise
        except Exception as exc:
            raise RagRerankerError("reranker_provider_request_failed") from exc
        if not isinstance(response, list) or len(response) != len(normalized_texts):
            raise RagRerankerError("reranker_response_invalid")
        ordered: list[float | None] = [None] * len(normalized_texts)
        try:
            for row in response:
                if not isinstance(row, dict):
                    raise ValueError
                index = int(row["index"])
                score = float(row["score"])
                if (
                    index < 0
                    or index >= len(ordered)
                    or ordered[index] is not None
                    or not math.isfinite(score)
                ):
                    raise ValueError
                ordered[index] = score
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RagRerankerError("reranker_response_invalid") from exc
        if any(score is None for score in ordered):
            raise RagRerankerError("reranker_response_invalid")
        return [float(score) for score in ordered]

    @staticmethod
    def _http_transport(url: str, payload: dict[str, Any], timeout: float) -> Any:
        import httpx

        response = httpx.post(url, json=payload, timeout=timeout)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RagRerankerError(
                f"reranker_provider_http_error:{response.status_code}"
            ) from exc
        return response.json()
