from typing import Any

from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.learning import ReflectionTrigger
from packages.security.auth import AuthContext


http_router = APIRouter(prefix="/api/v1/reflections", tags=["reflections"])


class ReflectionRequest(BaseModel):
    trigger: ReflectionTrigger
    run_id: str = Field(min_length=1, max_length=160)
    session_id: str | None = Field(default=None, max_length=160)
    trace_ids: list[str] = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class CandidateReviewRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _owned_run(container: AppContainer, run_id: str, auth: AuthContext):
    run = container.runs.get(run_id)
    attributes = (run.runtime_context.get("attributes") if run else None) or {}
    if run is None or attributes.get("trusted_tenant_id") != auth.tenant_id:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run, attributes


@http_router.post("")
async def create_reflection(
    payload: ReflectionRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("reflections:write")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    run, attributes = _owned_run(container, payload.run_id, auth)
    owned_trace_ids = {
        event.trace_id
        for event in container.traces.list_by_run_id(payload.run_id)
        if event.session_id == run.session_id
    }
    if payload.session_id not in {None, run.session_id} or not set(
        payload.trace_ids
    ).issubset(owned_trace_ids):
        raise HTTPException(status_code=404, detail="trace_not_found")
    job = container.reflection_service.enqueue(
        trigger=payload.trigger,
        run_id=payload.run_id,
        session_id=run.session_id,
        trace_ids=payload.trace_ids,
        tenant_id=auth.tenant_id,
        site_id=attributes.get("trusted_site_id"),
        user_id=auth.user_id,
        project_id=attributes.get("trusted_project_id"),
        payload=payload.payload,
        idempotency_key=idempotency_key
        or f"reflection:{payload.run_id}:{payload.trigger.value}:manual",
    )
    return api_success(job.model_dump(mode="json"))


@http_router.get("/jobs/{job_id}")
async def get_reflection_job(
    job_id: str,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("reflections:read")),
) -> dict:
    job = container.reflection_service.jobs.get(job_id)
    if job is None or job.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="reflection_job_not_found")
    return api_success(job.model_dump(mode="json"))


@http_router.get("/candidates")
async def list_learning_candidates(
    job_id: str | None = Query(default=None),
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("reflections:read")),
) -> dict:
    candidates = [
        candidate
        for candidate in container.reflection_service.candidates.list_all()
        if candidate.tenant_id == auth.tenant_id
        and (job_id is None or candidate.job_id == job_id)
    ]
    return api_success(
        {"candidates": [candidate.model_dump(mode="json") for candidate in candidates]}
    )


async def _review_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    approved: bool,
    container: AppContainer,
    auth: AuthContext,
) -> dict:
    existing = container.reflection_service.candidates.get(candidate_id)
    if existing is None or existing.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="learning_candidate_not_found")
    candidate = container.reflection_service.review_candidate(
        candidate_id,
        approved=approved,
        reviewed_by=auth.user_id,
        reason=payload.reason,
    )
    return api_success(candidate.model_dump(mode="json"))


@http_router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("reflections:write")),
) -> dict:
    return await _review_candidate(candidate_id, payload, True, container, auth)


@http_router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: str,
    payload: CandidateReviewRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("reflections:write")),
) -> dict:
    return await _review_candidate(candidate_id, payload, False, container, auth)
