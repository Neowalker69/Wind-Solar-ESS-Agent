from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceQuality(StrEnum):
    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"


class EvidenceRecord(BaseModel):
    evidence_id: str
    run_id: str
    trace_id: str
    source_type: str
    source_ref: str
    plugin_id: str | None = None
    plugin_version: str | None = None
    tool_name: str | None = None
    quality: EvidenceQuality = EvidenceQuality.GOOD
    data: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
