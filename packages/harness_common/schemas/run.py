from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunRecord(BaseModel):
    run_id: str
    session_id: str
    parent_run_id: str | None = None
    task_type: str
    status: RunStatus = RunStatus.PENDING
    workflow_id: str
    workflow_version: str
    graph_runtime: str = "langgraph"
    graph_checkpoint_ref: str | None = None
    workflow_run_ids: list[str] = Field(default_factory=list)
    workflow_runtime: str | None = None
    workflow_adapter_type: str | None = None
    model_id: str = "mock"
    model_version: str = "0"
    plugin_version_snapshot: dict[str, str] = Field(default_factory=dict)
    skill_version_snapshot: dict[str, str] = Field(default_factory=dict)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    data_model_version: str = "p0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: dict[str, Any] | None = None
    idempotency_key: str | None = None
