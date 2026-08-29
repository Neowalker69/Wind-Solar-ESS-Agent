from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from packages.harness_common.schemas.api import api_success
from packages.security.auth import AuthContext
from packages.harness_common.schemas.learning import ReflectionTrigger


http_router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class SessionSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    session_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SessionEndRequest(BaseModel):
    reason: str = Field(default="session_closed", min_length=1, max_length=300)


@http_router.post("/search")
async def search_sessions(
    payload: SessionSearchRequest,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("sessions:read", endpoint_id="sessions.search")),
) -> dict:
    results = [
        result.__dict__
        for result in container.session_search.search(payload.query, session_id=payload.session_id, limit=payload.limit)
    ]
    return api_success({"results": results}, meta={"index": "postgresql_fts_zhparser"})


@http_router.post("/{session_id}/end")
async def end_session(
    session_id: str,
    payload: SessionEndRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("reflections:write")),
) -> dict:
    runs = [
        run
        for run in container.runs.list_all()
        if run.session_id == session_id
        and run.runtime_context.get("attributes", {}).get("trusted_tenant_id")
        == auth.tenant_id
    ]
    if not runs:
        raise HTTPException(status_code=404, detail="session_not_found")
    run_ids = {run.run_id for run in runs}
    traces = sorted(
        (
            event
            for event in container.traces.list_all()
            if event.session_id == session_id and event.run_id in run_ids
        ),
        key=lambda event: event.timestamp,
    )
    if not traces:
        raise HTTPException(status_code=404, detail="session_trace_not_found")
    latest_run = max(runs, key=lambda run: run.created_at)
    attributes = latest_run.runtime_context.get("attributes", {})
    job = container.reflection_service.enqueue(
        trigger=ReflectionTrigger.SESSION_END,
        run_id=latest_run.run_id,
        session_id=session_id,
        trace_ids=list(dict.fromkeys(event.trace_id for event in traces)),
        tenant_id=auth.tenant_id,
        site_id=attributes.get("trusted_site_id"),
        user_id=auth.user_id,
        project_id=attributes.get("trusted_project_id"),
        payload={"reason": payload.reason},
        idempotency_key=f"reflection:session:{session_id}:end",
    )
    return api_success(job.model_dump(mode="json"))
