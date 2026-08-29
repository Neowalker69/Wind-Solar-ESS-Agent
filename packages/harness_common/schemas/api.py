from typing import Any

from pydantic import BaseModel, Field


class ApiErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: Any = Field(default_factory=dict)
    trace_id: str | None = None


class ApiEnvelope(BaseModel):
    data: Any | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    error: ApiErrorPayload | None = None


def api_success(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return ApiEnvelope(data=data, meta=meta or {}, error=None).model_dump(mode="json")


def api_error(
    *,
    code: str,
    message: str,
    status_code: int | None = None,
    retryable: bool = False,
    details: Any = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    meta = {"status_code": status_code} if status_code is not None else {}
    return ApiEnvelope(
        data=None,
        meta=meta,
        error=ApiErrorPayload(
            code=code,
            message=message,
            retryable=retryable,
            details=details if details is not None else {},
            trace_id=trace_id,
        ),
    ).model_dump(mode="json")
