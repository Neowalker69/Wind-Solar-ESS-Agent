from datetime import datetime, timedelta, timezone

from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.harness_common.schemas.tool_result import ToolResultStatus
from packages.plugins.station_api import build_station_api_tool_adapter
from packages.tool_registry.registry import CapabilityRegistry, ToolExecutionContext


def main() -> None:
    adapter = build_station_api_tool_adapter()
    assert adapter is not None
    devices, _ = adapter.client.search_devices(
        "A-01",
        request_id="p2-station-search",
    )
    device = next(item for item in devices if item.get("code") == "A-01")
    device_id = str(device["device_id"])
    registry = CapabilityRegistry.from_builtin_manifests()
    visible_tool_ids = [
        "asset.get_asset",
        "asset.get_asset_status",
        "telemetry.get_latest_value",
        "telemetry.get_timeseries",
        "alarm.get_active_alarms",
        "alarm.get_alarm_detail",
        "alarm.get_event_timeline",
    ]
    run = RunRecord(
        run_id="run-p2-station-acceptance",
        session_id="session-p2-station-acceptance",
        task_type="data.query",
        status=RunStatus.RUNNING,
        workflow_id="equipment_status_graph",
        workflow_version="p2",
        runtime_context={
            "selected_asset_id": device_id,
            "policy": {"visible_tool_ids": visible_tool_ids},
        },
    )
    context = ToolExecutionContext(
        run=run,
        registry=registry,
        services={"station_api": adapter.client},
    )

    asset = registry.execute_for_model("asset.get_asset", {}, context)
    telemetry = registry.execute_for_model(
        "telemetry.get_latest_value",
        {"metric": "temperature"},
        context,
    )
    alarms = registry.execute_for_model("alarm.get_active_alarms", {}, context)
    now = datetime.now(timezone.utc)
    timeseries = registry.execute_for_model(
        "telemetry.get_timeseries",
        {
            "metric": "temperature",
            "start": (now - timedelta(hours=24)).isoformat(),
            "end": now.isoformat(),
            "interval": "15m",
            "aggregation": "avg",
        },
        context,
    )
    alarm_detail = registry.execute_for_model(
        "alarm.get_alarm_detail",
        {"alarm_id": alarms.data["items"][0]["alarm_uuid"]},
        context,
    )
    events = registry.execute_for_model("alarm.get_event_timeline", {}, context)

    assert asset.status == ToolResultStatus.SUCCESS
    assert telemetry.status == ToolResultStatus.SUCCESS
    assert alarms.status in {ToolResultStatus.SUCCESS, ToolResultStatus.NO_DATA}
    assert timeseries.status in {ToolResultStatus.SUCCESS, ToolResultStatus.NO_DATA}
    assert alarm_detail.status == ToolResultStatus.SUCCESS
    assert events.status in {ToolResultStatus.SUCCESS, ToolResultStatus.NO_DATA}
    assert asset.source_refs[0]["upstream_trace_id"]
    assert telemetry.source_refs[0]["upstream_trace_id"]
    assert alarms.source_refs[0]["upstream_trace_id"]
    payload = "".join(
        item.model_dump_json()
        for item in (
            asset,
            telemetry,
            alarms,
            timeseries,
            alarm_detail,
            events,
        )
    )
    assert '"source":"fixture"' not in payload
    assert "industrial_fixture" not in payload
    print(
        "P2 station connector accepted:",
        {
            "deviceId": device_id,
            "assetStatus": asset.status,
            "telemetryStatus": telemetry.status,
            "alarmStatus": alarms.status,
            "timeseriesStatus": timeseries.status,
            "alarmDetailStatus": alarm_detail.status,
            "eventStatus": events.status,
            "upstreamTracePreserved": True,
            "fixtureFree": True,
        },
    )


if __name__ == "__main__":
    main()
