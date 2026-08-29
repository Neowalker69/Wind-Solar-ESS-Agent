from apps.composition import AppContainer, get_container_dependency
from fastapi import APIRouter, Depends, HTTPException
from packages.harness_common.schemas.api import api_success


http_router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@http_router.get("/{evidence_id}")
async def get_evidence_detail(
    evidence_id: str,
    container: AppContainer = Depends(get_container_dependency),
) -> dict:
    evidence = container.evidence.get(evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    data = evidence.data
    return api_success(
        {
            **evidence.model_dump(mode="json"),
            "snapshot": data.get("snapshot"),
            "content_hash": data.get("content_hash"),
            "fact_time": data.get("fact_time"),
            "observed_at": data.get("observed_at")
            or evidence.recorded_at.isoformat(),
            "query_window": data.get("query_window"),
            "aggregation": data.get("aggregation"),
            "source_locator": {
                "source_system": data.get("source_system"),
                "source_resource_type": data.get("source_resource_type")
                or evidence.source_type,
                "source_ref": evidence.source_ref,
                "upstream_trace_id": data.get("upstream_trace_id"),
            },
        }
    )
