from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    trace_id: str
    run_id: str | None = None
    session_id: str | None = None
    event_type: str
    node_name: str | None = None
    model_id: str | None = None
    model_version: str | None = None
    tool_name: str | None = None
    tool_version: str | None = None
    plugin_id: str | None = None
    plugin_version: str | None = None
    skill_id: str | None = None
    skill_version: str | None = None
    data_model_version: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    idempotency_key: str | None = None
    wal_record_id: str | None = None
    observation_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int | None = None
    status: str = "ok"
    error: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
