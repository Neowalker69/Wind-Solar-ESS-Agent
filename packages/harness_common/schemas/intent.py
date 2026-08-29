from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RouterPath(StrEnum):
    RULE = "rule"
    CACHE = "cache"
    SEMANTIC_ROUTER = "semantic_router"
    CLASSIFIER = "classifier"
    LLM_FALLBACK = "llm_fallback"


class SubIntent(BaseModel):
    intent_id: str
    confidence: float = 1.0
    normalized_user_turn: str


class IntentDecision(BaseModel):
    intent_decision_id: str
    channel: Literal["feishu"] = "feishu"
    session_id: str
    trace_id: str
    user_turn_hash: str
    intent_id: str
    intent_label: str
    intent_family: str
    confidence: float
    router_path: RouterPath
    is_composite: bool = False
    sub_intents: list[SubIntent] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    normalized_user_turn: str
    matched_examples: list[dict[str, Any]] = Field(default_factory=list)
    cache_key: str | None = None
    structured_output_schema_version: str = "intent_decision.v1"
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
