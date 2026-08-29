from typing import Any

from packages.capabilities.industrial_context import require_station_api, resolve_query_scope
from packages.harness_common.schemas.tool_result import (
    ToolResult,
    ToolResultQuality,
    ToolResultStatus,
)
from packages.tool_registry.registry import ToolExecutionContext


def get_active_alarms(
    payload: dict[str, Any],
    context: ToolExecutionContext,
) -> ToolResult | list[dict[str, Any]]:
    scope = resolve_query_scope(payload, context)
    station_api = require_station_api(context)
    alarms, trace_id = station_api.list_alarms(
        request_id=context.run.run_id,
        status="active",
        device_id=scope.asset_id,
        station_id=scope.station_id,
    )
    source_ref = {
        "source_system": "station_api",
        "source_resource_type": "alarm",
        "source_ref": f"alarms:active:device={scope.asset_id or '*'}:station={scope.station_id or '*'}",
        "fact_time": max(
            (str(alarm.get("triggered_at") or "") for alarm in alarms),
            default=None,
        ),
        "upstream_trace_id": trace_id,
    }
    return ToolResult(
        status=(ToolResultStatus.SUCCESS if alarms else ToolResultStatus.NO_DATA),
        data={
            "items": alarms,
            "query": {
                "device_id": scope.asset_id,
                "station_id": scope.station_id,
                "status": "active",
            },
        },
        quality=(ToolResultQuality.GOOD if alarms else ToolResultQuality.MISSING),
        source_refs=[source_ref],
    )


def get_alarm_detail(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    station_api = require_station_api(context)
    alarm_id = str(payload.get("alarm_id") or "")
    if not alarm_id:
        raise ValueError("alarm_id_required")
    resolved = station_api.get_alarm(alarm_id, request_id=context.run.run_id)
    if resolved is None:
        return ToolResult(
            status=ToolResultStatus.NO_DATA,
            data={"alarm_id": alarm_id},
            quality=ToolResultQuality.MISSING,
            source_refs=[_alarm_source_ref(alarm_id, None, None)],
        )
    alarm, trace_id = resolved
    return ToolResult(
            status=ToolResultStatus.SUCCESS,
            data=alarm,
            quality=ToolResultQuality.GOOD,
            source_refs=[
                _alarm_source_ref(
                    str(alarm.get("alarm_uuid") or alarm_id),
                    trace_id,
                    alarm.get("triggered_at"),
                )
            ],
    )


def get_alarm_history(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    scope = resolve_query_scope(payload, context)
    station_api = require_station_api(context)
    alarms, trace_id = station_api.list_alarms(
        request_id=context.run.run_id,
        device_id=scope.asset_id,
        station_id=scope.station_id,
    )
    return ToolResult(
            status=ToolResultStatus.SUCCESS if alarms else ToolResultStatus.NO_DATA,
            data={"items": alarms, "query": {"device_id": scope.asset_id, "station_id": scope.station_id}},
            quality=ToolResultQuality.GOOD if alarms else ToolResultQuality.MISSING,
            source_refs=[
                {
                    "source_system": "station_api",
                    "source_resource_type": "alarm",
                    "source_ref": f"alarms:device={scope.asset_id or '*'}:station={scope.station_id or '*'}",
                    "fact_time": max(
                        (str(item.get("triggered_at") or "") for item in alarms),
                        default=None,
                    ),
                    "upstream_trace_id": trace_id,
                }
            ],
    )


def get_alarms_correlate(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:alarm_correlation")


def get_event_timeline(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    station_api = require_station_api(context)
    scope = resolve_query_scope(payload, context)
    events, trace_id = station_api.events(
        request_id=context.run.run_id,
        device_id=scope.asset_id,
        start=payload.get("start"),
        end=payload.get("end"),
    )
    return ToolResult(
            status=ToolResultStatus.SUCCESS if events else ToolResultStatus.NO_DATA,
            data={"items": events},
            quality=ToolResultQuality.GOOD if events else ToolResultQuality.MISSING,
            source_refs=[
                {
                    "source_system": "station_api",
                    "source_resource_type": "event",
                    "source_ref": f"events:device={scope.asset_id or '*'}",
                    "fact_time": max(
                        (str(item.get("time") or "") for item in events),
                        default=None,
                    ),
                    "upstream_trace_id": trace_id,
                    "query_window": {
                        "start": payload.get("start"),
                        "end": payload.get("end"),
                    },
                }
            ],
    )


def ack_alarm_draft(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    alarm_id = str(payload.get("alarm_id") or "")
    if not alarm_id:
        raise ValueError("alarm_id_required")
    return {"alarm_id": alarm_id, "comment": str(payload.get("comment") or ""), "status": "draft", "requires_manual_execution": True}


def ack_alarm(_payload: dict[str, Any], _context: ToolExecutionContext) -> dict[str, Any]:
    raise PermissionError("production_alarm_ack_disabled")


def _alarm_source_ref(
    alarm_id: str,
    trace_id: str | None,
    fact_time: str | None,
) -> dict[str, Any]:
    return {
        "source_system": "station_api",
        "source_resource_type": "alarm",
        "source_ref": f"alarm:{alarm_id}",
        "fact_time": fact_time,
        "upstream_trace_id": trace_id,
    }
