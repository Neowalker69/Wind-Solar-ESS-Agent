from apps.api_gateway.routers.front_router import route_intent
from apps.composition import AppContainer, get_container, get_container_dependency
from apps.api_gateway.services.channel_normalizer import normalize_feishu_fixture
from apps.api_gateway.services.conversation_binder import bind_session
from apps.api_gateway.services.feishu_security import fixtures_enabled, verify_feishu_webhook
from apps.api_gateway.services.response_renderer import render_text_response
from apps.api_gateway.services.run_dispatcher import RunDispatcher
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.trace import TraceEvent
from packages.intent_router.router import IntentRouter
from packages.observability.metrics import GLOBAL_METRICS


http_router = APIRouter(prefix="/api/v1/channels/feishu", tags=["feishu"])


class FeishuWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


def handle_feishu_fixture(
    payload: dict,
    *,
    intent_router: IntentRouter | None = None,
    dispatcher: RunDispatcher | None = None,
    container: AppContainer | None = None,
) -> dict:
    container = container or get_container()
    envelope = normalize_feishu_fixture(payload)
    GLOBAL_METRICS.inc("channel_events_total", ("feishu",))
    session_id = bind_session(envelope)
    container.traces.create(TraceEvent(trace_id=envelope.trace_id, session_id=session_id, event_type="UserTurnReceived", payload=envelope.model_dump(mode="json")))
    decision = (intent_router or IntentRouter()).classify(envelope.text, session_id=session_id, trace_id=envelope.trace_id)
    GLOBAL_METRICS.inc("intent_router_path_total", (str(decision.router_path),))
    container.traces.create(TraceEvent(trace_id=envelope.trace_id, session_id=session_id, event_type="IntentClassified", payload=decision.model_dump(mode="json")))
    if decision.rejection_reason:
        return {"accepted": False, "trace_id": envelope.trace_id, "session_id": session_id, "error": decision.rejection_reason}
    route = route_intent(decision, idempotency_key=envelope.idempotency_key)
    run = (dispatcher or container.run_dispatcher).dispatch(route) if route.rejection_reason is None else None
    return {
        "accepted": route.rejection_reason is None,
        "trace_id": envelope.trace_id,
        "session_id": session_id,
        "run_id": run.run_id if run else None,
        "channel_envelope": envelope.model_dump(mode="json"),
        "intent_decision": decision.model_dump(mode="json"),
        "routing_decision": route.model_dump(mode="json"),
        "response": render_text_response(run_id=run.run_id if run else None, status="accepted", summary="fixture accepted"),
    }


@http_router.post("/fixtures", status_code=status.HTTP_202_ACCEPTED)
async def post_fixture(payload: FeishuWebhookPayload, container: AppContainer = Depends(get_container_dependency)) -> dict:
    if not fixtures_enabled():
        raise HTTPException(status_code=404, detail="fixture_endpoint_disabled")
    return api_success(handle_feishu_fixture(payload.model_dump(mode="json"), container=container))


@http_router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def post_event(request: Request, payload: FeishuWebhookPayload, container: AppContainer = Depends(get_container_dependency)) -> dict:
    await verify_feishu_webhook(request)
    return api_success(handle_feishu_fixture(payload.model_dump(mode="json"), container=container))
