from typing import Any

from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.skill import SkillRecord
from packages.harness_common.schemas.skill import SkillStatus
from packages.security.auth import AuthContext


http_router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class SkillSearchRequest(BaseModel):
    query: str = ""


class SkillVersionRequest(BaseModel):
    version: str


class SkillApprovalDecision(BaseModel):
    approved: bool


class SkillUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str

    def patch_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


@http_router.get("")
async def list_skills(container: AppContainer = Depends(get_container_dependency)) -> dict:
    return api_success({"skills": [skill.model_dump(mode="json") for skill in container.skill_meta_tools.service.registry.repo.list_all()]})


@http_router.post("/search")
async def search_skills(payload: SkillSearchRequest, container: AppContainer = Depends(get_container_dependency)) -> dict:
    return api_success({"skills": container.skill_meta_tools.skill_search(payload.query)})


@http_router.get("/{skill_id}/{version}")
async def get_skill_version(skill_id: str, version: str, container: AppContainer = Depends(get_container_dependency)) -> dict:
    try:
        return api_success(container.skill_meta_tools.skill_view(skill_id, version).model_dump(mode="json"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="skill_not_found") from exc


@http_router.post("/drafts")
async def create_skill_draft(
    payload: SkillRecord,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    return api_success(container.skill_meta_tools.skill_create(payload.model_dump(mode="json")).model_dump(mode="json"))


@http_router.patch("/{skill_id}/drafts/{version}")
async def update_skill_draft(
    skill_id: str,
    version: str,
    payload: SkillUpdateRequest,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    return api_success(container.skill_meta_tools.skill_update(skill_id, version, payload.patch_payload()).model_dump(mode="json"))


@http_router.post("/{skill_id}/evaluate")
async def evaluate_skill(
    skill_id: str,
    payload: SkillVersionRequest,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    return api_success(container.skill_meta_tools.skill_evaluate(skill_id, payload.version).model_dump(mode="json"))


@http_router.post("/{skill_id}/{version}/propose-activation")
async def propose_activation(
    skill_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    return api_success(container.skill_meta_tools.skill_propose_activation(skill_id, version))


@http_router.post("/{skill_id}/{version}/activate")
async def activate_skill(
    skill_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    try:
        return api_success(container.skill_meta_tools.service.activate_admin(skill_id, version).model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="skill_not_candidate") from exc


@http_router.post("/{skill_id}/{version}/approval")
async def decide_skill_activation(
    skill_id: str,
    version: str,
    payload: SkillApprovalDecision,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("skills:approve")),
) -> dict:
    try:
        skill = container.skill_meta_tools.skill_approve_activation(
            skill_id,
            version,
            approved=payload.approved,
            approver=auth.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="skill_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return api_success(skill.model_dump(mode="json"))


@http_router.post("/{skill_id}/rollback")
async def rollback_skill(
    skill_id: str,
    payload: SkillVersionRequest,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    return api_success(container.skill_meta_tools.skill_rollback(skill_id, payload.version))


@http_router.post("/{skill_id}/{version}/suspend")
async def suspend_skill(
    skill_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("skills:write")),
) -> dict:
    return api_success(container.skill_meta_tools.skill_suspend(skill_id, version).model_dump(mode="json"))


@http_router.get("/{skill_id}")
async def get_skill_latest(skill_id: str, container: AppContainer = Depends(get_container_dependency)) -> dict:
    versions = [skill for skill in container.skill_meta_tools.service.registry.repo.list_all() if skill.skill_id == skill_id]
    if not versions:
        raise HTTPException(status_code=404, detail="skill_not_found")
    active = next((skill for skill in versions if skill.status == SkillStatus.ACTIVE), versions[-1])
    return api_success(active.model_dump(mode="json"))
