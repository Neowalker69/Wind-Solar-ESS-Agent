from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.memory import MemoryRecord, MemoryStatus
from packages.security.auth import AuthContext


http_router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


class MemoryReviewRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class MemoryConflictResolutionRequest(MemoryReviewRequest):
    supersede_memory_id: str = Field(min_length=1, max_length=160)


@http_router.get("")
async def list_memories(container: AppContainer = Depends(get_container_dependency)) -> dict:
    return api_success({"memories": [memory.model_dump(mode="json") for memory in container.memory_service.repo.list_all()]})


@http_router.get("/candidates")
async def list_candidates(container: AppContainer = Depends(get_container_dependency)) -> dict:
    return api_success({
        "memories": [
            memory.model_dump(mode="json")
            for memory in container.memory_service.repo.list_all()
            if memory.status == MemoryStatus.CANDIDATE
        ]
    })


@http_router.post("")
async def create_memory(
    memory: MemoryRecord,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("memories:write")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    candidate = memory.model_copy(
        update={
            "tenant_id": auth.tenant_id,
            "idempotency_key": memory.idempotency_key or idempotency_key,
        }
    )
    return api_success(
        container.memory_service.create_candidate(candidate).model_dump(mode="json")
    )


@http_router.post("/{memory_id}/validate")
async def validate_memory(
    memory_id: str,
    payload: MemoryReviewRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    try:
        memory = container.memory_service.validate(
            memory_id,
            validated_by=auth.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return api_success(memory.model_dump(mode="json"))


@http_router.post("/{memory_id}/promote")
async def promote_memory(
    memory_id: str,
    payload: MemoryReviewRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    try:
        memory = container.memory_service.promote(
            memory_id,
            promoted_by=auth.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return api_success(memory.model_dump(mode="json"))


@http_router.post("/{memory_id}/resolve-conflict")
async def resolve_memory_conflict(
    memory_id: str,
    payload: MemoryConflictResolutionRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    try:
        memory = container.memory_service.resolve_conflict(
            memory_id,
            supersede_memory_id=payload.supersede_memory_id,
            resolved_by=auth.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return api_success(memory.model_dump(mode="json"))


@http_router.post("/{memory_id}/rollback")
async def rollback_memory(
    memory_id: str,
    payload: MemoryReviewRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    try:
        memory = container.memory_service.rollback(
            memory_id,
            rolled_back_by=auth.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return api_success(memory.model_dump(mode="json"))


@http_router.post("/{memory_id}/activate")
async def activate_memory(
    memory_id: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    try:
        return api_success(container.memory_service.activate(memory_id).model_dump(mode="json"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory_not_found") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="memory_activation_requires_validated_candidate",
        ) from exc


@http_router.post("/{memory_id}/reject")
async def reject_memory(
    memory_id: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    memory = container.memory_service.repo.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory_not_found")
    rejected = memory.model_copy(update={"status": MemoryStatus.REJECTED})
    container.memory_service.repo.create(rejected)
    return api_success(rejected.model_dump(mode="json"))


@http_router.post("/{memory_id}/expire")
async def expire_memory(
    memory_id: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    try:
        return api_success(
            container.memory_service.expire(memory_id).model_dump(mode="json")
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory_not_found") from exc


@http_router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("memories:write")),
) -> dict:
    if not container.memory_service.delete(memory_id):
        raise HTTPException(status_code=404, detail="memory_not_found")
    return api_success({"memory_id": memory_id, "deleted": True})
