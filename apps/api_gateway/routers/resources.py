from datetime import datetime

from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, HTTPException, Query
from packages.harness_common.schemas.api import api_success
from packages.security.auth import AuthContext


http_router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


@http_router.get("/search")
async def search_resources(
    query: str | None = Query(default=None, min_length=1, max_length=300),
    site_id: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    asset_id: str | None = None,
    device_id: str | None = None,
    model_id: str | None = None,
    tool_id: str | None = None,
    workflow_id: str | None = None,
    status: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(
        require_scope("sessions:read", endpoint_id="resources.search")
    ),
) -> dict:
    filters = {
        "query": query,
        "site_id": site_id,
        "session_id": session_id,
        "run_id": run_id,
        "asset_id": asset_id,
        "device_id": device_id,
        "model_id": model_id,
        "tool_id": tool_id,
        "workflow_id": workflow_id,
        "status": status,
        "occurred_from": occurred_from,
        "occurred_to": occurred_to,
    }
    if not any(value is not None and value != "" for value in filters.values()):
        raise HTTPException(
            status_code=422,
            detail="至少需要 query 或一个资源筛选条件",
        )
    hits = [
        result.__dict__
        for result in container.session_search.search(**filters, limit=limit)
    ]
    return api_success(
        {"hits": hits},
        meta={"index": "postgresql_fts_zhparser"},
    )
