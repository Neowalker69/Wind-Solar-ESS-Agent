from typing import Any

from packages.capabilities.industrial_context import require_station_api, selected_asset_id
from packages.harness_common.schemas.tool_result import (
    ToolResult,
    ToolResultQuality,
    ToolResultStatus,
)
from packages.tool_registry.registry import ToolExecutionContext


def get_asset(payload: dict[str, Any], context: ToolExecutionContext) -> ToolResult | dict[str, Any]:
    station_api = require_station_api(context)
    device_id = selected_asset_id(payload, context)
    resolved = station_api.get_device(device_id, request_id=context.run.run_id)
    if resolved is None:
        return ToolResult(
            status=ToolResultStatus.NO_DATA,
            data={"device_id": device_id},
            quality=ToolResultQuality.MISSING,
            source_refs=[
                _device_source_ref(device_id, trace_id=None, fact_time=None)
            ],
        )
    device, trace_id = resolved
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        data=device,
        quality=ToolResultQuality.GOOD,
        source_refs=[
            _device_source_ref(
                str(device["device_id"]),
                trace_id=trace_id,
                fact_time=device.get("updated_at"),
            )
        ],
    )


def list_assets(_payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    station_api = require_station_api(context)
    devices, _trace_id = station_api.search_devices(
        "",
        request_id=context.run.run_id,
    )
    return devices


def resolve_asset_alias(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").lower()
    station_api = require_station_api(context)
    devices, _trace_id = station_api.search_devices(
        query,
        request_id=context.run.run_id,
    )
    for asset in devices:
        candidates = [
            asset.get("device_id", ""),
            asset.get("code", ""),
            asset.get("name", ""),
        ]
        if any(query in str(candidate).lower() for candidate in candidates):
            return {
                "query": query,
                "asset_id": asset["device_id"],
                "resolved": True,
            }
    return {"query": query, "asset_id": None, "resolved": False}


def get_asset_topology(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:asset_topology")


def get_asset_components(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:asset_components")


def get_asset_status(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    result = get_asset(payload, context)
    if isinstance(result, ToolResult) and result.status == ToolResultStatus.SUCCESS:
        return result.model_copy(
            update={
                "data": {
                    "device_id": result.data["device_id"],
                    "status": result.data.get("status"),
                    "fact_time": result.data.get("updated_at"),
                }
            }
        )
    return result


def get_asset_criticality(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:asset_criticality")


def get_related_assets(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:related_assets")


def get_asset_manual_refs(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:asset_manual_refs")


def _device_source_ref(
    device_id: str,
    *,
    trace_id: str | None,
    fact_time: str | None,
) -> dict[str, Any]:
    return {
        "source_system": "station_api",
        "source_resource_type": "device",
        "source_ref": f"device:{device_id}",
        "fact_time": fact_time,
        "upstream_trace_id": trace_id,
    }
