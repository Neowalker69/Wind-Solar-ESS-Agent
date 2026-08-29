from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LearningCategory(StrEnum):
    FACT = "fact"
    EXPERIENCE = "experience"
    PROCEDURE = "procedure"
    NO_LEARNING = "no_learning"


class LearningCandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    MATERIALIZED = "materialized"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReflectionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    FAILED = "failed"


class ReflectionTrigger(StrEnum):
    SESSION_END = "session_end"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    USER_CORRECTION = "user_correction"
    EXPLICIT_FEEDBACK = "explicit_feedback"
    REPEATED_FAILURE_THRESHOLD = "repeated_failure_threshold"
    SCHEDULED_BACKGROUND_REVIEW = "scheduled_background_review"
    SKILL_USAGE_ANOMALY = "skill_usage_anomaly"


class LearningCandidate(BaseModel):
    candidate_id: str
    job_id: str
    trace_id: str
    run_id: str
    category: LearningCategory
    proposal: dict[str, Any]
    proposal_hash: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    repeat_count: int = Field(default=1, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    impact_scope: str = "task"
    risk_level: str = "L0"
    freshness: float = Field(default=1.0, ge=0, le=1)
    contradiction_score: float = Field(default=0.0, ge=0, le=1)
    conflicts_with: list[str] = Field(default_factory=list)
    tenant_id: str
    site_id: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    asset_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    materialized_ref: str | None = None
    review: dict[str, Any] | None = None
    status: LearningCandidateStatus = LearningCandidateStatus.CANDIDATE
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReflectionJob(BaseModel):
    job_id: str
    trigger: ReflectionTrigger
    trace_ids: list[str]
    run_id: str
    session_id: str | None = None
    tenant_id: str
    site_id: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ReflectionJobStatus = ReflectionJobStatus.PENDING
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    candidate_ids: list[str] = Field(default_factory=list)
    idempotency_key: str
    next_attempt_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
