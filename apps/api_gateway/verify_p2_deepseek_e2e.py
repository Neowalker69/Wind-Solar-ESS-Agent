import asyncio
import json
import os
import re
import secrets
from uuid import uuid4

from apps.composition import build_container
from packages.agent_runtime_rpc.generated.agent_runtime.v1 import runtime_pb2
from packages.agent_runtime_rpc.service import AgentRuntimeServicer


SCENARIO_ID = "p2-authoritative-overtemperature-v1"
DEVICE_CODE = "A-31"
DEVICE_ID = "A-31"
ALARM_ID = "00000000-0000-4000-8000-00000000f201"
EXPECTED_CAUSE = "cooling_fan_degradation"
EXPECTED_MODEL_PROVIDER = os.getenv("VERIFY_MODEL_PROVIDER", "deepseek")
EXPECTED_MODEL_ID = os.getenv("VERIFY_MODEL_ID", "deepseek-v4-flash")

PROMPTS = {
    "telemetry.get_latest_value": [
        "请核对 A-31 当前温度，必须调用实时遥测工具并依据权威返回作答。",
        "A-31 此刻温度是多少？请读取 temperature，不要用常识估计。",
        "随机核验 A-31 最新温度和数据质量，只能引用工具事实。",
    ],
    "alarm.get_active_alarms": [
        "调查 A-31 当前是否存在活动告警，并返回权威告警编号。",
        "请从场站事实库检查 A-31 的 active alarms，不要根据设备状态猜测。",
        "随机核验 A-31 当前告警，结论必须包含实际告警编号或明确 no_data。",
    ],
    "diagnosis.rank_root_causes": [
        "请先查 A-31 的活动告警和最新温度形成 Evidence，再调用诊断能力给出根因候选。",
        "对 A-31 做根因排序：先读取告警与 temperature 事实，再执行诊断，不能凭模型常识推断。",
        "随机验证 A-31 的完整诊断链，按告警、温度、根因排序的顺序调用工具并引用 Evidence。",
    ],
}


async def _run_case(
    servicer: AgentRuntimeServicer,
    container,
    *,
    expected_tool_id: str,
    allowed_tool_ids: list[str],
) -> dict:
    prompt = secrets.choice(PROMPTS[expected_tool_id])
    run_id = f"run-p2-deepseek-{uuid4().hex}"
    started = await servicer.start_turn(
        runtime_pb2.StartTurnRequest(
            run_id=run_id,
            session_id=f"session-{run_id}",
            text=prompt,
            context=runtime_pb2.ContextSnapshot(
                selected_asset_id=DEVICE_ID,
                environment="dev",
                attributes={
                    "scenario_id": SCENARIO_ID,
                    "scenario_data_class": "synthetic_postgresql",
                },
            ),
            tool_refs=[
                runtime_pb2.ToolReference(tool_id=tool_id, version="0.1.0")
                for tool_id in allowed_tool_ids
            ],
            policy=runtime_pb2.PolicySnapshot(
                visible_tool_ids=allowed_tool_ids,
                workflow_stage="p2.authoritative_fault_acceptance",
            ),
        )
    )
    assert started.run_id == run_id

    traces = container.traces.list_by_run_id(run_id)
    model_calls = [
        event for event in traces if event.event_type == "model.completed"
    ]
    model_stages = [event.node_name for event in model_calls]
    assert model_stages[0] == "planning"
    assert model_stages[-1] == "summary"
    assert all(
        stage == "planning" or stage.startswith("planning.")
        for stage in model_stages[:-1]
    )
    assert all(event.payload["provider"] == EXPECTED_MODEL_PROVIDER for event in model_calls)
    assert all(event.model_id == EXPECTED_MODEL_ID for event in model_calls)
    selected_tool_ids = [
        tool_id
        for event in model_calls[:-1]
        for tool_id in event.payload["selected_tool_ids"]
    ]
    assert expected_tool_id in selected_tool_ids
    assert expected_tool_id != allowed_tool_ids[0]
    assert "reasoning_content" not in str(
        [event.model_dump(mode="json") for event in model_calls]
    )

    observations = container.observations.list_by_run_id(run_id)
    observation_by_tool = {
        item.tool_name: item
        for item in observations
    }
    final_event = next(
        event for event in traces if event.event_type == "assistant.completed"
    )
    final = str(final_event.payload["content"])

    if expected_tool_id == "telemetry.get_latest_value":
        observation = observation_by_tool[expected_tool_id]
        result = observation.extract_payload["result"]
        assert result["status"] == "success"
        assert result["quality"] == "good"
        assert result["data"]["value"] == 62.5
        answer_values = [
            float(item)
            for item in re.findall(r"-?\d+(?:\.\d+)?", final)
        ]
        assert any(abs(item - 62.5) < 0.001 for item in answer_values)
        assert observation.evidence_id
        evidence_ids = [observation.evidence_id]
        status = result["status"]
    elif expected_tool_id == "alarm.get_active_alarms":
        observation = observation_by_tool[expected_tool_id]
        result = observation.extract_payload["result"]
        assert result["status"] == "success"
        alarm = next(
            item
            for item in result["data"]["items"]
            if item.get("alarm_uuid") == ALARM_ID
        )
        assert alarm["snapshot"]["scenario_id"] == SCENARIO_ID
        assert alarm["snapshot"]["cause"] == EXPECTED_CAUSE
        assert ALARM_ID in final or str(alarm["message"]) in final
        assert observation.evidence_id
        evidence_ids = [observation.evidence_id]
        status = result["status"]
    else:
        assert {
            "alarm.get_active_alarms",
            "telemetry.get_latest_value",
            "diagnosis.rank_root_causes",
        }.issubset(selected_tool_ids)
        diagnosis_index = selected_tool_ids.index("diagnosis.rank_root_causes")
        assert selected_tool_ids.index("alarm.get_active_alarms") < diagnosis_index
        assert selected_tool_ids.index("telemetry.get_latest_value") < diagnosis_index

        alarm_observation = observation_by_tool["alarm.get_active_alarms"]
        telemetry_observation = observation_by_tool["telemetry.get_latest_value"]
        diagnosis_observation = observation_by_tool[expected_tool_id]
        result = diagnosis_observation.extract_payload["result"]
        assert result["status"] == "success"
        candidate = next(
            item
            for item in result["data"]["candidates"]
            if item["cause"] == EXPECTED_CAUSE
        )
        assert candidate["alarm_ids"] == [ALARM_ID]
        assert candidate["scenario_ids"] == [SCENARIO_ID]
        assert candidate["supporting_evidence_ids"] == [
            alarm_observation.evidence_id
        ]
        assert alarm_observation.evidence_id
        assert telemetry_observation.evidence_id
        assert diagnosis_observation.evidence_id is None
        assert EXPECTED_CAUSE in final or "冷却风机" in final
        evidence_ids = [
            alarm_observation.evidence_id,
            telemetry_observation.evidence_id,
        ]
        status = result["status"]

    evidence = container.evidence.list_by_run_id(run_id)
    assert {item.evidence_id for item in evidence}.issuperset(evidence_ids)
    assert all(item.data.get("source_system") == "station_api" for item in evidence)
    assert all(item.data.get("upstream_trace_id") for item in evidence)
    assert set(final_event.evidence_ids).issuperset(evidence_ids)

    return {
        "runId": run_id,
        "prompt": prompt,
        "expectedTool": expected_tool_id,
        "selectedTools": selected_tool_ids,
        "toolStatus": status,
        "evidenceIds": evidence_ids,
        "modelStages": model_stages,
        "final": final,
    }


async def main() -> None:
    container = build_container()
    model = container.model_router.resolve()
    assert model.model_id == EXPECTED_MODEL_ID
    assert container.station_api_client is not None

    devices, search_trace_id = container.station_api_client.search_devices(
        DEVICE_CODE,
        request_id="p2-deepseek-device-search",
    )
    device = next(
        (item for item in devices if item.get("code") == DEVICE_CODE),
        None,
    )
    assert device is not None, "p2_fault_device_not_found"
    assert device["device_id"] == DEVICE_ID
    assert device["metadata"]["scenario_id"] == SCENARIO_ID
    assert search_trace_id

    servicer = AgentRuntimeServicer(container)
    results = [
        await _run_case(
            servicer,
            container,
            expected_tool_id="telemetry.get_latest_value",
            allowed_tool_ids=[
                "alarm.get_active_alarms",
                "asset.get_asset_status",
                "telemetry.get_latest_value",
            ],
        ),
        await _run_case(
            servicer,
            container,
            expected_tool_id="alarm.get_active_alarms",
            allowed_tool_ids=[
                "asset.get_asset_status",
                "telemetry.get_latest_value",
                "alarm.get_active_alarms",
            ],
        ),
        await _run_case(
            servicer,
            container,
            expected_tool_id="diagnosis.rank_root_causes",
            allowed_tool_ids=[
                "asset.get_asset_status",
                "alarm.get_active_alarms",
                "telemetry.get_latest_value",
                "diagnosis.rank_root_causes",
            ],
        ),
    ]
    print(
        json.dumps(
            {
                "accepted": True,
                "model": model.model_id,
                "scenarioId": SCENARIO_ID,
                "deviceId": DEVICE_ID,
                "cases": results,
                "promptSelection": "random_per_case",
                "dataMode": "postgresql_station_api",
                "fixtureFree": True,
                "factGrounded": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
