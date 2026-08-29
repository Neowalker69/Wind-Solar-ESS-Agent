from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    NO_DATA = "no_data"
    PARTIAL = "partial"
    FAILED = "failed"


class ToolResultQuality(StrEnum):
    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"
    MISSING = "missing"


class ToolResult(BaseModel):
    status: ToolResultStatus
    data: Any = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    quality: ToolResultQuality
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: dict[str, Any] | None = None

    @classmethod
    def from_handler_output(cls, output: Any) -> "ToolResult":
        if isinstance(output, cls):
            return output
        if isinstance(output, dict) and {"status", "data", "quality"} <= output.keys():
            return cls.model_validate(output)
        if output is None or output == {} or output == []:
            return cls(
                status=ToolResultStatus.NO_DATA,
                data=output,
                quality=ToolResultQuality.MISSING,
            )
        quality = ToolResultQuality.GOOD
        if isinstance(output, dict):
            raw_quality = str(output.get("quality") or "").lower()
            if raw_quality in {item.value for item in ToolResultQuality}:
                quality = ToolResultQuality(raw_quality)
        return cls(
            status=ToolResultStatus.SUCCESS,
            data=output,
            quality=quality,
        )

    @classmethod
    def failed(cls, code: str = "tool_execution_failed") -> "ToolResult":
        return cls(
            status=ToolResultStatus.FAILED,
            data=None,
            quality=ToolResultQuality.MISSING,
            error={"code": code},
        )
