from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict = Field(default_factory=dict)
    trace_id: str


class ErrorResponse(BaseModel):
    error: ErrorPayload
