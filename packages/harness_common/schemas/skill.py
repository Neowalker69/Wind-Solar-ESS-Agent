from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SkillStatus(StrEnum):
    DRAFT = "draft"
    TESTING = "testing"
    FAILED = "failed"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUSPENDED = "suspended"
    VALIDATING = "validating"
    STALE = "stale"
    ARCHIVED = "archived"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class SkillRecord(BaseModel):
    skill_id: str
    version: str
    status: SkillStatus = SkillStatus.DRAFT
    manifest: dict[str, Any]
    package_hash: str
    base_version: str | None = None
    created_by_tool_call_id: str | None = None
    source_trace_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    compatible_plugin_ranges: dict[str, str] = Field(default_factory=dict)
    evaluation_result_id: str | None = None
    approval_request_id: str | None = None
    approval_status: str | None = None
    owner: str = "agent-harness"
    tenant_id: str | None = None
    project_id: str | None = None
    risk_level: str = "L0"
    source_candidate_ids: list[str] = Field(default_factory=list)
    test_result: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    lifecycle_history: list[dict[str, Any]] = Field(default_factory=list)
    usage_count: int = Field(default=0, ge=0)
    last_used_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: datetime | None = None
