from datetime import datetime, timezone
import os
from typing import Any

from packages.capabilities.industrial_context import require_station_api, selected_asset_id
from packages.harness_common.schemas.tool_result import (
    ToolResult,
    ToolResultQuality,
    ToolResultStatus,
)
from packages.tool_registry.registry import ToolExecutionContext


def get_latest_value(payload: dict[str, Any], context: ToolExecutionContext) -> ToolResult | dict[str, Any]:
    station_api = require_station_api(context)
    asset_id = selected_asset_id(payload, context)
    metric = str(payload.get("metric") or "")
    if not metric:
        raise ValueError("metric_required")
    points, trace_id = station_api.realtime(
        asset_id,
        metric,
        request_id=context.run.run_id,
    )
    source_ref = {
        "source_system": "station_api",
        "source_resource_type": "telemetry",
        "source_ref": f"telemetry:{asset_id}:{metric}",
        "fact_time": points[0].get("time") if points else None,
        "upstream_trace_id": trace_id,
    }
    if not points:
        return ToolResult(
            status=ToolResultStatus.NO_DATA,
            data={"device_id": asset_id, "metric": metric, "items": []},
            quality=ToolResultQuality.MISSING,
            source_refs=[source_ref],
        )
    point = points[0]
    quality = _quality(point.get("quality"))
    reported_metric = str(point.get("metric_key") or metric)
    freshness = _freshness(point.get("time"), context, reported_metric)
    if freshness["stale"]:
        quality = ToolResultQuality.UNCERTAIN
    return ToolResult(
        status=(
            ToolResultStatus.PARTIAL
            if freshness["stale"]
            else ToolResultStatus.SUCCESS
        ),
        data={
            "device_id": asset_id,
            "metric": reported_metric,
            "value": point.get("value"),
            "quality": quality.value,
            "fact_time": point.get("time"),
            **freshness,
        },
        quality=quality,
        source_refs=[source_ref],
    )


def get_latest_telemetry(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:telemetry_metric_catalog")


def get_timeseries(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    station_api = require_station_api(context)
    asset_id = selected_asset_id(payload, context)
    metric = str(payload.get("metric") or "")
    start = str(payload.get("start") or "")
    end = str(payload.get("end") or "")
    if not metric:
        raise ValueError("metric_required")
    if not start or not end:
        raise ValueError("time_window_required")
    interval = str(payload.get("interval") or "5m")
    aggregation = str(payload.get("aggregation") or "avg")
    points, trace_id = station_api.history(
        asset_id,
        metric,
        start=start,
        end=end,
        interval=interval,
        aggregation=aggregation,
        request_id=context.run.run_id,
    )
    source_ref = {
        "source_system": "station_api",
        "source_resource_type": "telemetry",
        "source_ref": f"telemetry:{asset_id}:{metric}",
        "fact_time": points[-1].get("time") if points else None,
        "upstream_trace_id": trace_id,
        "query_window": {"start": start, "end": end},
        "aggregation": {"interval": interval, "function": aggregation},
    }
    return ToolResult(
        status=(
            ToolResultStatus.SUCCESS if points else ToolResultStatus.NO_DATA
        ),
        data={
            "device_id": asset_id,
            "metric": metric,
            "points": points,
            "query_window": {"start": start, "end": end},
            "aggregation": aggregation,
        },
        quality=(
            ToolResultQuality.GOOD if points else ToolResultQuality.MISSING
        ),
        source_refs=[source_ref],
    )


def list_available_metrics(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:telemetry_metric_catalog")


def get_point_mapping(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:point_mapping")


def compare_baseline(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:telemetry_baseline")


def compute_trend(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:telemetry_trend")


def validate_data_quality(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:data_quality")


def detect_missing_data(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:missing_data_detection")


def _quality(value: Any) -> ToolResultQuality:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return ToolResultQuality.UNCERTAIN
    if numeric >= 192:
        return ToolResultQuality.GOOD
    if numeric > 0:
        return ToolResultQuality.UNCERTAIN
    return ToolResultQuality.BAD


def _freshness(
    fact_time: Any,
    context: ToolExecutionContext,
    metric: str,
) -> dict[str, Any]:
    normalized_metric = metric.strip().casefold()
    ttl_env = (
        "AGENT_HARNESS_TELEMETRY_SOH_TTL_SECONDS"
        if normalized_metric in {"soh", "soh_pct", "state_of_health"}
        else "AGENT_HARNESS_TELEMETRY_TTL_SECONDS"
    )
    ttl_default = "604800" if ttl_env.endswith("SOH_TTL_SECONDS") else "30"
    ttl_seconds = max(1, int(os.getenv(ttl_env, ttl_default)))
    try:
        observed_at = datetime.fromisoformat(
            str(fact_time).replace("Z", "+00:00")
        )
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        clock = context.services.get("clock")
        now = clock() if callable(clock) else datetime.now(timezone.utc)
        age_seconds = max(0, int((now - observed_at).total_seconds()))
    except (TypeError, ValueError):
        return {
            "stale": True,
            "age_seconds": None,
            "ttl_seconds": ttl_seconds,
        }
    return {
        "stale": age_seconds > ttl_seconds,
        "age_seconds": age_seconds,
        "ttl_seconds": ttl_seconds,
    }
