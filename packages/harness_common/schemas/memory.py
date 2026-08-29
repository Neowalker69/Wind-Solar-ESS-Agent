from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PROFILE = "profile"
    LESSON = "lesson"
    SUMMARY = "summary"
    PROCEDURAL_REFERENCE = "procedural_reference"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONFLICTED = "conflicted"
    VALIDATED = "validated"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MemoryRecord(BaseModel):
    memory_id: str
    memory_type: MemoryType
    version: str
    content: dict[str, Any]
    status: MemoryStatus = MemoryStatus.CANDIDATE
    source_trace_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    embedding: list[float] | None = None
    tenant_id: str = "tenant_lab"
    site_id: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    agent_id: str | None = None
    asset_id: str | None = None
    source_ref: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    idempotency_key: str | None = None
    authority: float = Field(default=0.5, ge=0, le=1)
    risk_level: str = "L0"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_memory_id: str | None = None
    lifecycle_history: list[dict[str, Any]] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0, le=1)
    model_visible: bool = True
    tool_visible: bool = True
    recall_count: int = Field(default=0, ge=0)
    last_recalled_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
