import asyncio
from uuid import uuid4

from google.protobuf.json_format import MessageToDict

from apps.composition import build_container
from packages.agent_runtime_rpc.generated.agent_runtime.v1 import runtime_pb2
from packages.agent_runtime_rpc.service import AgentRuntimeServicer
from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.harness_common.schemas.tool_result import ToolResultStatus
from packages.model.router import ModelRouter
from packages.storage.postgres_repository import (
    PostgresEvidenceRepository,
    PostgresRunRepository,
)
from packages.tool_registry.registry import ToolExecutionContext


def _event_payloads(started: runtime_pb2.StartTurnResponse) -> list[dict]:
    return [
        MessageToDict(event.payload, preserving_proto_field_name=True)
        for event in started.initial_events
    ]


async def main() -> None:
    container = build_container()
    assert isinstance(container.runs, PostgresRunRepository)
    assert isinstance(container.evidence, PostgresEvidenceRepository)
    assert container.station_api_client is not None
    # 验收只固定模型输出的可重复性；所有业务事实仍来自真实 Station API。
    container.model_router = ModelRouter()

    devices, _ = container.station_api_client.search_devices(
        "A-01",
        request_id="p2-r4-grounded-device-search",
    )
    device = next(item for item in devices if item.get("code") == "A-01")
    device_id = str(device["device_id"])
    run_id = f"run-p2-r4-{uuid4().hex}"
    servicer = AgentRuntimeServicer(container)
    started = await servicer.start_turn(
        runtime_pb2.StartTurnRequest(
            run_id=run_id,
            session_id=f"session-{run_id}",
            text="分析 A-01 当前告警",
            context=runtime_pb2.ContextSnapshot(
                selected_asset_id=device_id,
                environment="dev",
            ),
            tool_refs=[
                runtime_pb2.ToolReference(
                    tool_id="alarm.get_active_alarms",
                    version="0.1.0",
                )
            ],
            policy=runtime_pb2.PolicySnapshot(
                visible_tool_ids=["alarm.get_active_alarms"],
                workflow_stage="alarm.query",
            ),
        )
    )
    payloads = _event_payloads(started)
    completed = [
        payload
        for payload in payloads
        if payload.get("event_type") == "tool.completed"
    ]
    assert len(completed) == 1
    assert completed[0]["tool_id"] == "alarm.get_active_alarms"
    assert completed[0]["status"] == ToolResultStatus.SUCCESS
    assert completed[0]["result"]["data"]["items"]
    assert completed[0]["evidence_id"]
    assert "industrial_fixture" not in str(completed)
    authoritative_evidence = container.evidence.list_by_run_id(run_id)
    assert [item.evidence_id for item in authoritative_evidence] == [
        completed[0]["evidence_id"]
    ]
    assert authoritative_evidence[0].source_ref.startswith("alarms:active:")
    assert authoritative_evidence[0].data["source_system"] == "station_api"

    runtime_run = container.runs.get(run_id)
    assert runtime_run is not None
    workflow_run = runtime_run.model_copy(
        update={
            "runtime_context": {
                **runtime_run.runtime_context,
                "policy": {
                    "visible_tool_ids": [
                        "diagnosis.rank_root_causes",
                        "workorder.create_work_order_draft",
                    ]
                },
            }
        }
    )
    execution_context = ToolExecutionContext(
        run=workflow_run,
        registry=container.capability_registry,
        services={
            "evidence_repo": container.evidence,
            "durable_workflows": container.durable_workflows,
        },
    )
    diagnosis = container.capability_registry.execute_for_model(
        "diagnosis.rank_root_causes",
        {},
        execution_context,
    )
    assert diagnosis.status == ToolResultStatus.NO_DATA
    assert diagnosis.data["status"] == "insufficient_evidence"
    assert diagnosis.data["candidates"] == []

    work_order = container.capability_registry.execute_for_model(
        "workorder.create_work_order_draft",
        {"asset_id": device_id},
        execution_context,
    )
    assert work_order.status == ToolResultStatus.SUCCESS
    assert work_order.data["status"] == "completed"
    assert work_order.data["output"]["draft"]["tasks"]
    assert work_order.data["output"]["draft"]["evidence_ids"] == [
        authoritative_evidence[0].evidence_id
    ]

    report = container.durable_workflows.submit(
        "report_generation",
        run_id=run_id,
        normalized_input={
            "report_type": "alarm",
            "evidence_ids": [authoritative_evidence[0].evidence_id],
        },
        idempotency_key=f"p2-r4-report:{run_id}",
    )
    assert report.status == "completed"
    assert report.output["report"]["evidence_ids"] == [
        authoritative_evidence[0].evidence_id
    ]

    empty_run = RunRecord(
        run_id=f"run-p2-r4-empty-{uuid4().hex}",
        session_id="session-p2-r4-empty",
        task_type="workorder.create",
        status=RunStatus.RUNNING,
        workflow_id="work_order_draft",
        workflow_version="p2",
        runtime_context={
            "selected_asset_id": device_id,
            "policy": {
                "visible_tool_ids": ["workorder.create_work_order_draft"]
            },
        },
    )
    empty_context = ToolExecutionContext(
        run=empty_run,
        registry=container.capability_registry,
        services={
            "evidence_repo": container.evidence,
            "durable_workflows": container.durable_workflows,
        },
    )
    blocked_work_order = container.capability_registry.execute_for_model(
        "workorder.create_work_order_draft",
        {"asset_id": device_id},
        empty_context,
    )
    assert blocked_work_order.status == ToolResultStatus.NO_DATA
    assert blocked_work_order.data == {
        "status": "blocked",
        "missing": ["evidence"],
    }
    blocked_report = container.durable_workflows.submit(
        "report_generation",
        run_id=empty_run.run_id,
        normalized_input={"report_type": "alarm", "evidence_ids": []},
        idempotency_key=f"p2-r4-report:{empty_run.run_id}",
    )
    assert blocked_report.status == "blocked"
    assert blocked_report.output["report"] is None

    no_match_started = await servicer.start_turn(
        runtime_pb2.StartTurnRequest(
            run_id=f"run-p2-r4-no-match-{uuid4().hex}",
            session_id="session-p2-r4-no-match",
            text="你好",
            context=runtime_pb2.ContextSnapshot(
                selected_asset_id=device_id,
                environment="dev",
            ),
            tool_refs=[
                runtime_pb2.ToolReference(
                    tool_id="asset.get_asset_status",
                    version="0.1.0",
                )
            ],
            policy=runtime_pb2.PolicySnapshot(
                visible_tool_ids=["asset.get_asset_status"],
                workflow_stage="general.chat",
            ),
        )
    )
    no_match_payloads = _event_payloads(no_match_started)
    assert not any(
        payload.get("event_type") in {"BeforeToolCall", "tool.completed"}
        for payload in no_match_payloads
    )

    print(
        "P2 grounded workflows accepted:",
        {
            "runId": run_id,
            "deviceId": device_id,
            "authoritativeEvidenceId": authoritative_evidence[0].evidence_id,
            "alarmQuery": "success",
            "diagnosisWithoutCausalEvidence": "no_data",
            "workOrderWithEvidence": "completed",
            "workOrderWithoutEvidence": "blocked",
            "reportWithEvidence": "completed",
            "reportWithoutEvidence": "blocked",
            "unmatchedTurnToolCalls": 0,
            "fixtureFree": True,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
