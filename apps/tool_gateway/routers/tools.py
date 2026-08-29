import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.tool_gateway.services.tool_policy import FORBIDDEN_TOOL_TOKENS
from apps.composition import AppContainer, get_container_dependency
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.plugin import ToolDefinition
from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.security.auth import AuthContext
from packages.tool_registry.registry import (
    CapabilityToolManifest,
    ToolExecutionContext,
    ToolNotFoundError,
    ToolNotVisibleError,
)


http_router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class ToolExecuteRequest(BaseModel):
    name: str
    input: dict = Field(default_factory=dict)
    task_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    model_name: str | None = None


@http_router.get("")
async def list_tools(container: AppContainer = Depends(get_container_dependency)) -> dict:
    return api_success(
        {
            "tools": [
                _manifest_projection(item)
                for item in container.capability_registry.list_manifests()
            ]
        }
    )


@http_router.get("/readable")
async def list_readable_tools(container: AppContainer = Depends(get_container_dependency)) -> dict:
    return await list_tools(container)


@http_router.post("/execute")
async def execute_tool(
    payload: ToolExecuteRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    container: AppContainer = Depends(get_container_dependency),
) -> dict:
    auth: AuthContext = container.tool_guard.authenticate(authorization)
    if payload.run_id or payload.trace_id:
        raise HTTPException(status_code=400, detail="tool_context_not_client_settable")
    lowered = payload.name.lower()
    if any(token in lowered for token in FORBIDDEN_TOOL_TOKENS):
        raise HTTPException(status_code=403, detail="tool_policy_rejected")
    container.tool_guard.authorize_tool_call(auth, tool_id=payload.name, payload=payload.input)
    try:
        manifest = container.capability_registry.get_manifest(payload.name)
        _validate_required_input(manifest, payload.input)
        run_id = f"tool_{uuid4().hex}"
        trace_id = f"trace_{uuid4().hex}"
        run = _direct_execution_run(payload, manifest, run_id)
        result = container.capability_registry.execute_for_model(
            manifest.tool_id,
            payload.input,
            ToolExecutionContext(
                run=run,
                registry=container.capability_registry,
                user={
                    "user_id": auth.user_id,
                    "role": auth.role,
                    "tenant_id": auth.tenant_id,
                },
                services=_capability_services(container),
            ),
        )
        observation = container.observation_service.capture_tool_observation(
            tool=_tool_definition(manifest),
            raw_observation={"result": result.model_dump(mode="json")},
            task_id=payload.task_id,
            run_id=run_id,
            trace_id=trace_id,
            model_name=payload.model_name,
            source_ref=manifest.tool_id,
        )
        response = {
            "tool_id": manifest.tool_id,
            "version": manifest.version,
            "result": result.model_dump(mode="json"),
            "observation_id": observation.observation_id,
            "raw_snapshot_ref": observation.raw_snapshot_ref,
            "redacted_fields": observation.redacted_fields,
        }
        if observation.evidence_id:
            response["evidence_id"] = observation.evidence_id
        return api_success(response, meta={"user_id": auth.user_id})
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail="tool_not_registered") from exc
    except ToolNotVisibleError as exc:
        raise HTTPException(status_code=409, detail="tool_not_readable") from exc


def _manifest_projection(manifest: CapabilityToolManifest) -> dict[str, Any]:
    return {
        "tool_id": manifest.tool_id,
        "version": manifest.version,
        "capability": manifest.capability,
        "description": manifest.description,
        "input_schema": manifest.input_schema,
        "output_schema": manifest.output_schema,
        "risk_level": manifest.risk_level,
        "classification": manifest.classification,
        "readable": manifest.readable,
        "reason": manifest.unavailable_reason,
        "dependencies": manifest.dependencies,
    }


def _validate_required_input(
    manifest: CapabilityToolManifest,
    payload: dict[str, Any],
) -> None:
    missing = [
        name
        for name in manifest.input_schema.get("required", [])
        if name not in payload
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"missing_tool_input:{missing[0]}",
        )


def _direct_execution_run(
    payload: ToolExecuteRequest,
    manifest: CapabilityToolManifest,
    run_id: str,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        session_id=f"tool_session_{uuid4().hex}",
        task_type="tool.execute",
        status=RunStatus.RUNNING,
        workflow_id="capability_registry_direct_execution",
        workflow_version="p2",
        runtime_context={
            "selected_asset_id": payload.input.get("asset_id")
            or payload.input.get("device_id"),
            "environment": os.getenv("AGENT_HARNESS_PROFILE", "dev"),
            "policy": {"visible_tool_ids": [manifest.tool_id]},
        },
        model_id=payload.model_name or "direct-tool-api",
    )


def _capability_services(container: AppContainer) -> dict[str, Any]:
    return {
        "skill_meta_tools": container.skill_meta_tools,
        "memory_service": container.memory_service,
        "rag_search_service": container.rag_search_service,
        "session_search": container.session_search,
        "evidence_repo": container.evidence,
        "durable_workflows": container.durable_workflows,
        "station_api": container.station_api_client,
        "workspace_root": (
            Path(os.environ["AGENT_HARNESS_WORKSPACE_ROOT"])
            if os.getenv("AGENT_HARNESS_WORKSPACE_ROOT")
            else None
        ),
    }


def _tool_definition(manifest: CapabilityToolManifest) -> ToolDefinition:
    return ToolDefinition(
        name=manifest.tool_id,
        version=manifest.version,
        description=manifest.description,
        input_schema=manifest.input_schema,
        output_schema=manifest.output_schema,
        risk_level=manifest.risk_level,
        plugin_id=manifest.capability,
        plugin_version=manifest.version,
    )
