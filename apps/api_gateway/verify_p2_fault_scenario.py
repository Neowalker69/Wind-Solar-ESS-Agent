import json
from datetime import datetime, timedelta, timezone

from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.plugins.station_api import build_station_api_tool_adapter
from packages.tool_registry.registry import CapabilityRegistry, ToolExecutionContext


SCENARIO_ID = "p2-authoritative-overtemperature-v1"
DEVICE_CODE = "A-31"
DEVICE_ID = "A-31"
ALARM_ID = "00000000-0000-4000-8000-00000000f201"
EXPECTED_CAUSE = "cooling_fan_degradation"


def main() -> None:
    adapter = build_station_api_tool_adapter()
    assert adapter is not None
    devices, search_trace_id = adapter.client.search_devices(
        DEVICE_CODE,
        request_id="p2-fault-device-search",
    )
    device = next(
        (item for item in devices if item.get("code") == DEVICE_CODE),
        None,
    )
    assert device is not None, "p2_fault_device_not_found"
    assert device["device_id"] == DEVICE_ID
    assert device["status"] == "critical"
    assert device["metadata"]["scenario_id"] == SCENARIO_ID
    assert device["metadata"]["synthetic"] is True

    registry = CapabilityRegistry.from_builtin_manifests()
    visible_tool_ids = [
        "telemetry.get_latest_value",
        "telemetry.get_timeseries",
        "alarm.get_active_alarms",
        "alarm.get_alarm_detail",
        "alarm.get_event_timeline",
    ]
    run = RunRecord(
        run_id="run-p2-fault-scenario-acceptance",
        session_id="session-p2-fault-scenario-acceptance",
        task_type="diagnosis.alarm",
        status=RunStatus.RUNNING,
        workflow_id="alarm_diagnosis_graph",
        workflow_version="p2",
        runtime_context={
            "selected_asset_id": DEVICE_ID,
            "policy": {"visible_tool_ids": visible_tool_ids},
        },
    )
    context = ToolExecutionContext(
        run=run,
        registry=registry,
        services={"station_api": adapter.client},
    )

    latest = registry.execute_for_model(
        "telemetry.get_latest_value",
        {"metric": "temperature"},
        context,
    )
    active_alarms = registry.execute_for_model(
        "alarm.get_active_alarms",
        {},
        context,
    )
    now = datetime.now(timezone.utc)
    history = registry.execute_for_model(
        "telemetry.get_timeseries",
        {
            "metric": "temperature",
            "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(minutes=1)).isoformat(),
            "interval": "5m",
            "aggregation": "avg",
        },
        context,
    )
    alarm_detail = registry.execute_for_model(
        "alarm.get_alarm_detail",
        {"alarm_id": ALARM_ID},
        context,
    )
    events = registry.execute_for_model(
        "alarm.get_event_timeline",
        {
            "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(minutes=1)).isoformat(),
        },
        context,
    )

    assert latest.status == "success"
    assert latest.quality == "good"
    assert latest.data["value"] == 62.5
    assert latest.data["metric"] == "temperature"

    assert active_alarms.status == "success"
    alarm = next(
        (
            item
            for item in active_alarms.data["items"]
            if item.get("alarm_uuid") == ALARM_ID
        ),
        None,
    )
    assert alarm is not None
    assert alarm["severity"] == "critical"
    assert alarm["status"] == "active"
    assert alarm["snapshot"]["scenario_id"] == SCENARIO_ID
    assert alarm["snapshot"]["cause"] == EXPECTED_CAUSE

    assert history.status == "success"
    assert len(history.data["points"]) >= 5
    assert max(float(item["value"]) for item in history.data["points"]) == 62.5

    assert alarm_detail.status == "success"
    assert alarm_detail.data["alarm_uuid"] == ALARM_ID
    assert alarm_detail.data["snapshot"]["cause"] == EXPECTED_CAUSE

    assert events.status == "success"
    scenario_events = [
        item
        for item in events.data["items"]
        if item.get("details", {}).get("scenario_id") == SCENARIO_ID
    ]
    assert len(scenario_events) == 2
    assert all(
        item["details"]["cause"] == EXPECTED_CAUSE
        for item in scenario_events
    )

    results = [latest, active_alarms, history, alarm_detail, events]
    assert search_trace_id
    assert all(
        result.source_refs[0]["source_system"] == "station_api"
        for result in results
    )
    assert all(
        result.source_refs[0]["upstream_trace_id"]
        for result in results
    )
    serialized = "".join(result.model_dump_json() for result in results)
    assert '"source":"fixture"' not in serialized
    assert "industrial_fixture" not in serialized

    print(
        json.dumps(
            {
                "accepted": True,
                "scenarioId": SCENARIO_ID,
                "deviceId": DEVICE_ID,
                "latestTemperature": latest.data["value"],
                "telemetryQuality": latest.quality,
                "historyPoints": len(history.data["points"]),
                "activeAlarmId": ALARM_ID,
                "rootCauseFact": EXPECTED_CAUSE,
                "scenarioEvents": len(scenario_events),
                "sourceSystem": "station_api",
                "upstreamTracePreserved": True,
                "fixtureFreeToolPath": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
