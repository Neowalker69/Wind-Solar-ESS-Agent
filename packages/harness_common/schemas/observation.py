from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ObservationRecord(BaseModel):
    observation_id: str
    task_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    model_name: str | None = None
    tool_name: str
    plugin_id: str
    plugin_version: str
    raw_snapshot_ref: str
    extract_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_id: str | None = None
    redacted_fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
