from typing import Any


class ModelProviderError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        message: str,
        status_code: int | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}
