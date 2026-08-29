from typing import Any, Literal

from pydantic import BaseModel


class RoutingDecision(BaseModel):
    route_id: str
    channel: Literal["feishu"] = "feishu"
    intent_decision_id: str
    workflow_id: str
    workflow_version: str
    task_type: str
    normalized_input: dict[str, Any]
    response_mode: str = "text"
    priority: int = 5
    session_id: str
    run_id: str | None = None
    trace_id: str
    idempotency_key: str
    rejection_reason: str | None = None
