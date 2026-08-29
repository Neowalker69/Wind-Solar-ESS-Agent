from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ContextKind(StrEnum):
    INSTRUCTION = "instruction"
    USER_PROFILE = "user_profile"
    SESSION = "session"
    TASK_STATE = "task_state"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    TOOL_RESULT = "tool_result"
    ARTIFACT = "artifact"
    POLICY = "policy"
    TOOL_DEFINITION = "tool_definition"
    SCENE = "scene"
    WORKFLOW_STAGE = "workflow_stage"
    TELEMETRY = "telemetry"
    ALARM = "alarm"
    SKILL = "skill"
    RETRIEVAL = "retrieval"


class ContextScope(BaseModel):
    tenant_id: str
    site_id: str
    user_id: str
    role: str
    area_id: str | None = None
    line_id: str | None = None
    asset_id: str | None = None
    component_id: str | None = None
    scene_node_id: str | None = None
    workflow_id: str | None = None
    workflow_stage: str | None = None
    incident_id: str | None = None
    risk_ceiling: str = "L1"


class ContextRequest(BaseModel):
    query: str
    intent: str
    scope: ContextScope
    context_window: int = Field(default=32_768, gt=0)
    reserved_output_tokens: int = Field(default=4_096, ge=0)
    tool_schema_tokens: int = Field(default=0, ge=0)
    protocol_overhead_tokens: int = Field(default=512, ge=0)
    allowed_tool_ids: list[str] = Field(default_factory=list)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sliding_window_items: int = Field(default=8, ge=1)
    hierarchical_compaction_items: int = Field(default=24, ge=2)
    summary_token_limit: int = Field(default=1_500, ge=64, le=4_096)

    @property
    def token_budget(self) -> int:
        reserved = (
            self.reserved_output_tokens
            + self.tool_schema_tokens
            + self.protocol_overhead_tokens
        )
        return max(1, self.context_window - reserved)


class ContextItem(BaseModel):
    id: str
    kind: ContextKind
    content: str | dict[str, Any]
    summary: str | None = None
    source: str
    source_ref: str | None = None
    created_at: datetime
    source_timestamp: datetime | None = None
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: datetime | None = None
    version: str | None = None
    relevance: float = Field(default=0.5, ge=0, le=1)
    authority: float = Field(default=0.5, ge=0, le=1)
    freshness: float = Field(default=1.0, ge=0, le=1)
    utility: float = Field(default=0.5, ge=0, le=1)
    data_quality: float = Field(default=1.0, ge=0, le=1)
    token_estimate: int = Field(default=0, ge=0)
    pinned: bool = False
    mutable: bool = False
    sensitive: bool = False
    model_visible: bool = True
    tool_visible: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_traceable_source(self):
        traceable_kinds = {
            ContextKind.MEMORY,
            ContextKind.KNOWLEDGE,
            ContextKind.TOOL_RESULT,
            ContextKind.ARTIFACT,
            ContextKind.SCENE,
            ContextKind.WORKFLOW_STAGE,
            ContextKind.POLICY,
            ContextKind.TELEMETRY,
            ContextKind.ALARM,
            ContextKind.SKILL,
            ContextKind.RETRIEVAL,
        }
        if self.kind in traceable_kinds and not self.source_ref:
            raise ValueError("context_source_ref_required")
        return self


class ContextPlan(BaseModel):
    required: list[ContextKind] = Field(default_factory=list)
    optional: list[ContextKind] = Field(default_factory=list)
    excluded: list[ContextKind] = Field(default_factory=list)
    time_window: str | None = None
    provider_queries: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class ContextConflict(BaseModel):
    field: str
    candidate_ids: list[str]
    selected_id: str | None = None
    resolution_reason: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class ContextProviderFailure(BaseModel):
    provider: str
    code: str
    message: str
    required_types: list[ContextKind] = Field(default_factory=list)


class ContextBundle(BaseModel):
    snapshot_id: str
    scope: ContextScope
    plan: ContextPlan
    model_items: list[ContextItem]
    tool_items: list[ContextItem]
    excluded_ids: list[str] = Field(default_factory=list)
    missing_context: list[ContextKind] = Field(default_factory=list)
    conflicts: list[ContextConflict] = Field(default_factory=list)
    provider_failures: list[ContextProviderFailure] = Field(default_factory=list)
    cache_hits: list[str] = Field(default_factory=list)
    token_budget: int
    tokens_used: int
    utilization: float
    compression_level: str = "none"
    compaction_steps: list[str] = Field(default_factory=list)
    allow_tool_calls: bool = True
    warnings: list[str] = Field(default_factory=list)
    model_context: str
    lifecycle_runtime: str = "compiler"
