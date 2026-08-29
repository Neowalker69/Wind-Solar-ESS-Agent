from typing import Any

from apps.composition import AppContainer, get_container_dependency
from fastapi import APIRouter, Depends, HTTPException
from packages.harness_common.schemas.api import api_success


http_router = APIRouter(prefix="/api/v1/context/snapshots", tags=["context"])


def _lookup(snapshot_id: str, container: AppContainer):
    return container.traces.get_context_snapshot(snapshot_id)


@http_router.get("/{snapshot_id}")
async def get_context_snapshot(snapshot_id: str, container: AppContainer = Depends(get_container_dependency)) -> dict[str, Any]:
    event = _lookup(snapshot_id, container)
    if event is None:
        raise HTTPException(status_code=404, detail="context_snapshot_not_found")
    return api_success({"snapshot_id": snapshot_id, "run_id": event.run_id, "session_id": event.session_id, "trace_id": event.trace_id, "compiled_at": event.timestamp.isoformat(), "snapshot": event.payload})


@http_router.get("/{snapshot_id}/explain")
async def explain_context_snapshot(snapshot_id: str, container: AppContainer = Depends(get_container_dependency)) -> dict[str, Any]:
    event = _lookup(snapshot_id, container)
    if event is None:
        raise HTTPException(status_code=404, detail="context_snapshot_not_found")
    payload = event.payload
    return api_success({
        "snapshot_id": snapshot_id, "run_id": event.run_id,
        "selected_ids": [str(item.get("id")) for item in payload.get("model_items", [])],
        "excluded_ids": payload.get("excluded_ids", []), "missing_context": payload.get("missing_context", []),
        "conflicts": payload.get("conflicts", []), "provider_failures": payload.get("provider_failures", []),
        "warnings": payload.get("warnings", []), "compaction_steps": payload.get("compaction_steps", []),
        "tokens_used": payload.get("tokens_used"), "token_budget": payload.get("token_budget"),
    })
