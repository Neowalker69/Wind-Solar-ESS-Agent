from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.intent import IntentDecision
from packages.harness_common.schemas.routing import RoutingDecision

http_router = APIRouter(prefix="/api/v1/router/decisions", tags=["front-router"])


class RoutingPreviewRequest(BaseModel):
    intent_decision: IntentDecision
    idempotency_key: str | None = None


INTENT_TO_WORKFLOW = {
    "data.query": ("equipment_status_graph", "data.query"),
    "diagnosis.alarm": ("alarm_diagnosis_graph", "diagnosis.alarm"),
    "report.generate": ("report_generation", "report.generate"),
    "workorder.draft": ("work_order_draft", "workorder.draft"),
    "sop.ingest": ("sop_ingest", "sop.ingest"),
    "sop.search": ("sop_search_graph", "sop.search"),
    "skill.create": ("skill_draft", "skill.create"),
    "replay.eval": ("replay_eval", "replay.eval"),
}


def route_intent(decision: IntentDecision, *, idempotency_key: str) -> RoutingDecision:
    if decision.intent_id not in INTENT_TO_WORKFLOW:
        return RoutingDecision(
            route_id=f"route_{uuid4().hex}",
            intent_decision_id=decision.intent_decision_id,
            workflow_id="none",
            workflow_version="p0.1",
            task_type=decision.intent_id,
            normalized_input={"text": decision.normalized_user_turn},
            session_id=decision.session_id,
            trace_id=decision.trace_id,
            idempotency_key=idempotency_key,
            rejection_reason="route_not_found",
        )
    workflow_id, task_type = INTENT_TO_WORKFLOW[decision.intent_id]
    return RoutingDecision(
        route_id=f"route_{uuid4().hex}",
        intent_decision_id=decision.intent_decision_id,
        workflow_id=workflow_id,
        workflow_version="p0.1",
        task_type=task_type,
        normalized_input={"text": decision.normalized_user_turn, "intent_id": decision.intent_id},
        session_id=decision.session_id,
        trace_id=decision.trace_id,
        idempotency_key=idempotency_key,
    )


@http_router.post("/preview")
async def post_routing_preview(request: RoutingPreviewRequest) -> dict:
    route = route_intent(request.intent_decision, idempotency_key=request.idempotency_key or request.intent_decision.user_turn_hash)
    return api_success(route.model_dump(mode="json"))
