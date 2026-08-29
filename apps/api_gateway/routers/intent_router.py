from packages.intent_router.router import IntentRouter
from fastapi import APIRouter
from pydantic import BaseModel
from packages.harness_common.schemas.api import api_success


router = IntentRouter()
http_router = APIRouter(prefix="/api/v1/router/intents", tags=["intent-router"])


class IntentPreviewRequest(BaseModel):
    text: str
    session_id: str = "preview_session"
    trace_id: str = "preview_trace"


def preview_intent(text: str, *, session_id: str, trace_id: str):
    return router.classify(text, session_id=session_id, trace_id=trace_id)


@http_router.post("/preview")
async def post_intent_preview(request: IntentPreviewRequest) -> dict:
    return api_success(preview_intent(request.text, session_id=request.session_id, trace_id=request.trace_id).model_dump(mode="json"))
