from collections import OrderedDict
import json
import os
from typing import Literal
from uuid import uuid4

from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from packages.harness_common.schemas.api import api_success
from packages.security.auth import AuthContext, Hs256JwtVerifier


http_router = APIRouter(prefix="/api/v1/digital-twin", tags=["digital-twin"])

_RUN_SNAPSHOTS: OrderedDict[str, list[dict]] = OrderedDict()
_MAX_RUN_SNAPSHOTS = 100


class DigitalTwinDeviceContext(BaseModel):
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    soc: float = Field(ge=0, le=100)
    soh: float = Field(ge=0, le=100)
    power_kw: float = Field(ge=-1_000_000, le=1_000_000)
    temperature_c: float = Field(ge=-100, le=300)
    charge_state: Literal["charging", "discharging", "standby"]
    alarm_level: Literal["normal", "warning", "critical", "offline"]
    alarm_ids: list[str] = Field(default_factory=list, max_length=50)
    timestamp: str = Field(min_length=1, max_length=64)


class DigitalTwinContext(BaseModel):
    site_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    site_name: str = Field(min_length=1, max_length=120)
    time_range: Literal["realtime", "6h", "24h", "7d", "30d"]
    selected_device: DigitalTwinDeviceContext | None = None


class DigitalTwinAgentMessageRequest(BaseModel):
    run_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    client_message_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    user_input: str = Field(min_length=1, max_length=500)
    node_id: str = Field(min_length=1, max_length=240)
    context: DigitalTwinContext


class DigitalTwinActionConfirmRequest(BaseModel):
    client_action_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=300)


def _remember_run_snapshot(run_id: str, events: list[dict]) -> None:
    _RUN_SNAPSHOTS[run_id] = events[-500:]
    _RUN_SNAPSHOTS.move_to_end(run_id)
    while len(_RUN_SNAPSHOTS) > _MAX_RUN_SNAPSHOTS:
        _RUN_SNAPSHOTS.popitem(last=False)


async def _run_projected_message(
    payload: DigitalTwinAgentMessageRequest,
    container: AppContainer,
    auth: AuthContext,
) -> dict:
    # 兼容旧 Digital Twin URL，但执行链只进入正式 Agent Runtime。
    from apps.api_gateway.routers.agent import _execute_p1_capability_turn

    events = await _execute_p1_capability_turn(
        payload,
        container,
        session_id=f"legacy_{payload.client_message_id}",
        run_id=payload.run_id or "",
        trusted_identity={
            "tenant_id": auth.tenant_id,
            "user_id": auth.user_id,
            "role": auth.role,
        },
        trusted_site_id=payload.context.site_id,
    )
    completed = next((fields for event_type, fields in reversed(events) if event_type == "response.completed"), {})
    run_completed = next((fields for event_type, fields in reversed(events) if event_type == "run.completed"), {})
    tool_events = [fields for event_type, fields in events if event_type == "tool.completed"]
    first_tool = tool_events[0] if tool_events else {}
    first_payload = first_tool.get("payload") or {}
    trace_id = completed.get("traceId") or run_completed.get("traceId")
    trace_children = [
        {
            "id": item.get("observationId") or (item.get("payload") or {}).get("observationId"),
            "kind": "tool",
            "title": (item.get("payload") or {}).get("toolLabel") or (item.get("payload") or {}).get("toolId"),
            "summary": (item.get("payload") or {}).get("summary") or "",
            "status": item.get("status") or "completed",
            "metrics": {},
            "children": [],
        }
        for item in tool_events
    ]
    return api_success({
        "runtime": "formal_agent_runtime",
        "output": {
            "summary": (completed.get("payload") or {}).get("content") or "",
            "reasoning_summary": (completed.get("payload") or {}).get("reasoningSummary") or "",
            "context_device_id": payload.context.selected_device.device_id if payload.context.selected_device else None,
            "user_id": auth.user_id,
        },
        "llm_decision": {"model_id": None, "model_version": None, "content": None, "structured": {}, "finish_reason": "stop", "usage": {}},
        "tool_call": {"name": first_payload.get("toolId")},
        "observation": {"observation_id": first_payload.get("observationId"), "evidence_id": first_payload.get("evidenceId")},
        "trace_tree": {"trace_id": trace_id, "run_id": payload.run_id, "root": {"id": trace_id or "formal-runtime", "kind": "run", "title": "Formal Agent Runtime", "summary": "正式 Agent Runtime 执行链", "status": "completed", "metrics": {}, "children": trace_children}},
        "events": [{"type": event_type, **fields} for event_type, fields in events],
        "external_observability": run_completed.get("externalObservability") or {},
    })


def _trace_observation_events(root: dict, run_id: str, sequence: int) -> tuple[list[dict], int]:
    events: list[dict] = []

    def visit(node: dict, parent_id: str | None = None) -> None:
        nonlocal sequence
        sequence += 1
        node_id = str(node.get("id") or f"observation-{sequence}")
        events.append(
            {
                "type": "observation.upsert",
                "runId": run_id,
                "eventSequence": sequence,
                "observation": {
                    "observationId": node_id,
                    "parentObservationId": parent_id,
                    "kind": node.get("kind") or "event",
                    "name": node.get("title") or "执行步骤",
                    "status": "success" if node.get("status") == "ok" else node.get("status") or "success",
                    "summary": node.get("summary") or "",
                    "durationMs": (node.get("metrics") or {}).get("duration_ms"),
                    "totalTokens": (node.get("metrics") or {}).get("total_tokens"),
                },
            }
        )
        for child in node.get("children") or []:
            visit(child, node_id)

    visit(root)
    return events, sequence


def _sse(event: dict) -> str:
    payload = json.dumps(event, ensure_ascii=False)
    return f"id: {event['eventSequence']}\nevent: {event['type']}\ndata: {payload}\n\n"


@http_router.get("/bootstrap")
async def digital_twin_bootstrap() -> dict:
    token = ""
    profile = os.getenv("AGENT_HARNESS_PROFILE", "dev").lower()
    if profile in {"dev", "local", "test"}:
        issuer = os.getenv("TOOL_GATEWAY_JWT_ISSUER")
        token = Hs256JwtVerifier().issue_dev_token(
            user_id="local_operator",
            scopes=["tools:execute"],
            issuer=issuer,
            token_type="access" if issuer else None,
        )
    return api_success(
        {
            "bearer_token": token,
            "auth_mode": "local_jwt" if token else "external_login_required",
            "capabilities": {
                "agent_messages": True,
                "trace_projection": True,
                "langfuse_trace_link": True,
                "ot_write": False,
            },
        },
        meta={"credential_storage": "runtime_memory_only"},
    )


@http_router.post("/agent/messages")
async def send_digital_twin_agent_message(
    payload: DigitalTwinAgentMessageRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("tools:execute", endpoint_id="digital_twin.agent_messages")),
) -> dict:
    # 上下文通过结构化模型校验后再交给运行时，避免前端透传任意内部字段。
    return await _run_projected_message(payload, container, auth)


@http_router.post("/agent/runs/stream")
async def stream_digital_twin_agent_run(
    payload: DigitalTwinAgentMessageRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("tools:execute", endpoint_id="digital_twin.agent_stream")),
):
    run_id = payload.run_id or f"run_{uuid4().hex}"

    async def stream():
        events: list[dict] = []

        def append(event_type: str, **fields) -> dict:
            event = {"type": event_type, "runId": run_id, "eventSequence": len(events) + 1, **fields}
            events.append(event)
            _remember_run_snapshot(run_id, list(events))
            return event

        yield _sse(append("run.queued", status="queued"))
        yield _sse(append("run.planning", status="planning", summary="正在确认设备、告警和时间范围上下文。"))
        try:
            response = await _run_projected_message(payload, container, auth)
            data = response["data"]
            yield _sse(append("run.running", status="running"))
            observation_events, _ = _trace_observation_events(data["trace_tree"]["root"], run_id, len(events))
            for event in observation_events:
                events.append(event)
                _remember_run_snapshot(run_id, list(events))
                yield _sse(event)
            yield _sse(
                append(
                    "message.completed",
                    message={
                        "content": data.get("output", {}).get("summary") or "Agent 已完成本次分析。",
                        "reasoningSummary": "已依据当前场站上下文完成模型判断、只读工具查询与证据记录。",
                    },
                )
            )
            yield _sse(
                append(
                    "run.completed",
                    status="completed",
                    externalObservability=data.get("external_observability") or {},
                )
            )
        except Exception as exc:
            yield _sse(append("run.failed", status="failed", error={"message": str(exc)[:240], "retryable": False}))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@http_router.get("/agent/runs/{run_id}")
async def get_digital_twin_agent_run_snapshot(
    run_id: str,
    _auth: AuthContext = Depends(require_scope("tools:execute", endpoint_id="digital_twin.agent_snapshot")),
) -> dict:
    events = _RUN_SNAPSHOTS.get(run_id)
    if events is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    return api_success({"runId": run_id, "lastEventId": str(events[-1]["eventSequence"]), "events": events})


@http_router.post("/agent/actions/{action_id}/confirm")
async def confirm_digital_twin_action(
    action_id: Literal["create_work_order_draft"],
    payload: DigitalTwinActionConfirmRequest,
    request: Request,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("tools:execute", endpoint_id="digital_twin.action_confirm")),
) -> dict:
    audit_id = f"audit_{uuid4().hex}"
    wal_record = container.state_wal.append(
        request_id=request.state.request_id,
        scope="state_transition",
        source="digital_twin_router",
        action=f"digital_twin.{action_id}.{payload.decision}",
        payload={
            "audit_id": audit_id,
            "client_action_id": payload.client_action_id,
            "device_id": payload.device_id,
            "user_id": auth.user_id,
            "note": payload.note,
        },
    )
    return api_success(
        {
            "action_id": action_id,
            "status": "draft_created" if payload.decision == "approve" else "rejected",
            "device_id": payload.device_id,
            "audit_id": audit_id,
            "wal_record_id": wal_record.wal_record_id,
            "ot_write": False,
        }
    )
