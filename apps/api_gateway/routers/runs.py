from datetime import datetime, timezone
import json

from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.evidence import EvidenceRecord
from packages.harness_common.schemas.routing import RoutingDecision
from packages.harness_common.schemas.run import RunStatus
from packages.harness_common.schemas.trace import TraceEvent
from packages.memory.miner import mine_episodic_candidate
from packages.replay.service import ReplayService
from packages.security.auth import AuthContext
from packages.workflow.data_quality import RequiredEvidenceMissing, supporting_evidence_ids, validate_requested_evidence_ids
from packages.workflow.diagnosis_graph import run_diagnosis_graph


http_router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


class CompleteRunRequest(BaseModel):
    evidence_ids: list[str] = Field(default_factory=list)


@http_router.post("")
async def create_run(
    route: RoutingDecision,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("runs:write")),
) -> dict:
    return api_success(container.run_dispatcher.dispatch(route).model_dump(mode="json"))


@http_router.get("/{run_id}")
async def get_run(run_id: str, container: AppContainer = Depends(get_container_dependency)) -> dict:
    run = container.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return api_success(run.model_dump(mode="json"))


@http_router.get("/{run_id}/audit")
async def get_run_audit(
    run_id: str,
    container: AppContainer = Depends(get_container_dependency),
) -> dict:
    """从持久化仓储拼装审计投影，不依赖 Redis 短期事件。"""
    run = container.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    traces = container.traces.list_by_run_id(run_id)
    observations = container.observations.list_by_run_id(run_id)
    evidence = container.evidence.list_by_run_id(run_id)
    workflows = [
        state.model_dump(mode="json")
        for workflow_run_id in run.workflow_run_ids
        if (state := container.durable_workflows.get_state(workflow_run_id))
        is not None
    ]
    model_calls = [
        _without_hidden_reasoning(
            {
                **event.model_dump(mode="json"),
                "stage": event.node_name or event.payload.get("stage"),
                "provider": event.payload.get("provider"),
            }
        )
        for event in traces
        if event.event_type == "model.completed"
    ]
    tool_calls = [
        {
            "observation_id": item.observation_id,
            "tool_id": item.tool_name,
            "tool_version": item.plugin_version,
            "status": _tool_result_field(item.extract_payload, "status", "failed"),
            "quality": _tool_result_field(item.extract_payload, "quality", "missing"),
            "result": _tool_result(item.extract_payload),
            "evidence_id": item.evidence_id,
            "occurred_at": item.observed_at.isoformat(),
        }
        for item in observations
    ]
    final_event = next(
        (
            event
            for event in reversed(traces)
            if event.event_type == "assistant.completed"
        ),
        None,
    )
    final = (
        {
            **_without_hidden_reasoning(final_event.payload),
            "evidence_ids": final_event.evidence_ids,
            "occurred_at": final_event.timestamp.isoformat(),
        }
        if final_event is not None
        else None
    )
    context_event = next(
        (
            event
            for event in reversed(traces)
            if event.event_type == "context.compiled"
        ),
        None,
    )
    context_projection = (
        _without_hidden_reasoning(context_event.payload)
        if context_event is not None
        else run.runtime_context.get("context_bundle")
    )
    return api_success(
        {
            "run": run.model_dump(mode="json"),
            "intent": next(
                (
                    _without_hidden_reasoning(event.payload)
                    for event in traces
                    if event.event_type == "IntentClassified"
                ),
                None,
            ),
            "context": context_projection,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "observations": [
                item.model_dump(mode="json") for item in observations
            ],
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "workflows": workflows,
            "final": final,
            "timeline": _audit_timeline(
                traces=traces,
                observations=observations,
                evidence=evidence,
                workflows=workflows,
            ),
        }
    )


@http_router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    request: Request,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("runs:write")),
) -> dict:
    run = container.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    cancelled = run.model_copy(update={"status": RunStatus.CANCELLED})
    container.runs.create(cancelled)
    wal_record = container.state_wal.append(
        request_id=request.state.request_id,
        scope="state_transition",
        source="runs_router",
        action="run.cancel",
        payload={"run_id": run_id, "status": str(RunStatus.CANCELLED)},
    )
    container.traces.create(
        TraceEvent(
            trace_id="trace_cancel",
            run_id=run_id,
            session_id=run.session_id,
            event_type="RunCancelled",
            wal_record_id=wal_record.wal_record_id,
            payload={"reason": "api_request"},
        )
    )
    container.event_bus.publish(run_id, {"event_type": "RunCancelled", "run_id": run_id, "reason": "api_request"})
    return api_success(cancelled.model_dump(mode="json"))


@http_router.get("/{run_id}/events")
async def run_events(run_id: str, container: AppContainer = Depends(get_container_dependency)) -> dict:
    trace_events = [event.model_dump(mode="json") for event in container.traces.list_by_run_id(run_id)]
    return api_success({"run_id": run_id, "events": trace_events, "bus_events": container.event_bus.history(run_id)})


@http_router.get("/{run_id}/events/stream")
async def run_events_stream(run_id: str, container: AppContainer = Depends(get_container_dependency)):
    async def stream():
        for event in container.event_bus.history(run_id):
            yield f"event: {event['event_type']}\n"
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@http_router.post("/{run_id}/replay")
async def replay_run(
    run_id: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("runs:write")),
) -> dict:
    container.traces.create(TraceEvent(trace_id="trace_replay", run_id=run_id, event_type="ReplayRequested", payload={"mode": "record"}))
    evidence_records = container.evidence.list_by_run_id(run_id)
    final_answer = run_diagnosis_graph(run_id, evidence_records)["final"]
    return api_success(ReplayService(container.traces).record_replay(run_id, final_answer))


@http_router.get("/{run_id}/workflow-runs")
async def run_workflow_runs(run_id: str, container: AppContainer = Depends(get_container_dependency)) -> dict:
    run = container.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return api_success({
        "run_id": run_id,
        "workflows": [
            state.model_dump(mode="json")
            for workflow_run_id in run.workflow_run_ids
            if (state := container.durable_workflows.get_state(workflow_run_id)) is not None
        ],
    })


@http_router.post("/{run_id}/complete")
async def complete_run(
    run_id: str,
    payload: CompleteRunRequest,
    request: Request,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("runs:write")),
) -> dict:
    run = container.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    evidence_ids = payload.evidence_ids
    evidence_records: list[EvidenceRecord] = container.evidence.list_by_run_id(run_id)
    try:
        supporting_ids = validate_requested_evidence_ids(evidence_records, evidence_ids) if evidence_ids else supporting_evidence_ids(evidence_records)
    except RequiredEvidenceMissing as exc:
        raise HTTPException(status_code=409, detail=str(exc) or "required_evidence_missing") from exc
    final_evidence_ids = supporting_ids
    selected_records = [record for record in evidence_records if record.evidence_id in final_evidence_ids]
    diagnosis = run_diagnosis_graph(run_id, selected_records)
    if diagnosis["status"] != "completed":
        raise HTTPException(status_code=409, detail=diagnosis["status"])
    final = diagnosis["final"]
    completed = run.model_copy(update={"status": RunStatus.COMPLETED, "completed_at": datetime.now(timezone.utc)})
    container.runs.create(completed)
    memory = container.memory_service.create_candidate(mine_episodic_candidate(run_id, run.graph_checkpoint_ref or f"trace_{run_id}", final_evidence_ids))
    wal_record = container.state_wal.append(
        request_id=request.state.request_id,
        scope="state_transition",
        source="runs_router",
        action="run.complete",
        payload={"run_id": run_id, "status": str(RunStatus.COMPLETED), "memory_id": memory.memory_id},
    )
    container.traces.create(
        TraceEvent(
            trace_id=f"trace_complete_{run_id}",
            run_id=run_id,
            event_type="RunStop",
            wal_record_id=wal_record.wal_record_id,
            payload={"memory_id": memory.memory_id},
        )
    )
    container.event_bus.publish(run_id, {"event_type": "RunStop", "run_id": run_id, "memory_id": memory.memory_id})
    return api_success({"run": completed.model_dump(mode="json"), "final": final, "memory_candidate": memory.model_dump(mode="json")})


def _tool_result(extract_payload: dict) -> dict:
    result = extract_payload.get("result")
    return result if isinstance(result, dict) else {}


def _tool_result_field(
    extract_payload: dict,
    field: str,
    default: str,
) -> str:
    return str(_tool_result(extract_payload).get(field) or default)


def _without_hidden_reasoning(value):
    if isinstance(value, dict):
        return {
            key: _without_hidden_reasoning(item)
            for key, item in value.items()
            if key not in {"reasoning_content", "raw_thought", "raw_prompt", "raw"}
        }
    if isinstance(value, list):
        return [_without_hidden_reasoning(item) for item in value]
    return value


def _audit_timeline(*, traces, observations, evidence, workflows) -> list[dict]:
    items: list[dict] = []
    trace_kinds = {
        "IntentClassified": "intent",
        "context.compiled": "context",
        "model.completed": "model",
        "assistant.completed": "final",
    }
    for event in traces:
        kind = trace_kinds.get(event.event_type)
        if kind is None:
            continue
        items.append(
            {
                "kind": kind,
                "name": event.node_name or event.event_type,
                "status": event.status,
                "occurred_at": event.timestamp.isoformat(),
                "ref_id": event.trace_id,
            }
        )
    for item in observations:
        items.append(
            {
                "kind": "tool",
                "name": item.tool_name,
                "status": _tool_result_field(
                    item.extract_payload,
                    "status",
                    "failed",
                ),
                "occurred_at": item.observed_at.isoformat(),
                "ref_id": item.observation_id,
            }
        )
    for item in evidence:
        items.append(
            {
                "kind": "evidence",
                "name": item.source_type,
                "status": str(item.quality),
                "occurred_at": item.recorded_at.isoformat(),
                "ref_id": item.evidence_id,
            }
        )
    for item in workflows:
        items.append(
            {
                "kind": "workflow",
                "name": item["workflow_id"],
                "status": item["status"],
                "occurred_at": None,
                "ref_id": item["workflow_run_id"],
            }
        )
    return sorted(
        items,
        key=lambda item: (item["occurred_at"] is None, item["occurred_at"] or ""),
    )
