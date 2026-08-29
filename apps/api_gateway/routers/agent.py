import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic
from typing import Callable, Literal

from google.protobuf.json_format import MessageToDict
from apps.api_gateway.agent_run_coordinator import TERMINAL_RUN_STATUSES, agent_run_coordinator
from apps.api_gateway.routers.digital_twin import (
    DigitalTwinActionConfirmRequest,
    DigitalTwinAgentMessageRequest,
    _sse,
    confirm_digital_twin_action,
    digital_twin_bootstrap,
)
from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi import Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from packages.harness_common.schemas.api import api_success
from packages.agent_runtime_rpc.generated.agent_runtime.v1 import runtime_pb2
from packages.agent_runtime_rpc.service import AgentRuntimeServicer
from packages.intent_router.router import IntentRouter
from packages.security.auth import AuthContext, Hs256JwtVerifier
from packages.tool_registry.registry import ToolExecutionContext


http_router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# Intent Router 只收窄当前 Turn 的候选工具，最终选择和顺序由模型规划。
INTENT_TO_CAPABILITIES = {
    "data.query": ("asset.get_asset_status", "telemetry.get_latest_value"),
    "diagnosis.alarm": ("alarm.get_active_alarms", "asset.get_asset_status"),
    "workorder.draft": ("workorder.create_work_order_draft",),
    "skill.create": ("skill.skill_list",),
    "memory.search": ("memory.session_search",),
    "sop.ingest": ("search.search_sop",),
    "sop.search": ("search.search_sop",),
    "messaging.draft": ("messaging.send_message_draft",),
    "task.status": ("task.get_workflow_status",),
}

# 这是当前 MVP 已注册且可由模型自主组合的公开工具集，不表示固定执行顺序。
MVP_AGENT_CAPABILITIES = (
    "runtime_context.get_selected_asset_context",
    "runtime_context.get_active_workflow_state",
    "runtime_context.get_policy_context",
    "asset.get_asset",
    "asset.list_assets",
    "asset.get_asset_status",
    "asset.get_asset_criticality",
    "telemetry.get_latest_value",
    "telemetry.get_timeseries",
    "alarm.get_active_alarms",
    "alarm.get_alarm_history",
    "scene.locate_asset_in_scene",
    "diagnosis.generate_evidence_bundle",
    "diagnosis.validate_evidence_completeness",
    "diagnosis.rank_root_causes",
    "workorder.create_work_order_draft",
    "skill.skill_list",
    "skill.search_skill",
    "memory.session_search",
    "memory.memory_search",
    "search.search_sop",
    "messaging.send_message_draft",
    "task.get_workflow_status",
)

_DEVICE_SCOPED_CAPABILITIES = {
    "asset.get_asset",
    "asset.get_asset_status",
    "asset.get_asset_criticality",
    "telemetry.get_latest_value",
    "telemetry.get_timeseries",
    "alarm.get_alarm_detail",
    "scene.locate_asset_in_scene",
}
_ASSET_REFERENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:A[-_ ]?0?(?:[1-9]|[12]\d|3[0-2])|(?:PCS|PACK|CELL|STK|CLU)[-_ ]?\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_CHINESE_CONTAINER_REFERENCE_PATTERN = re.compile(
    r"(?<!\d)([1-9]|[12]\d|3[0-2])\s*号\s*(?:储能)?(?:集装箱|舱|设备)"
)


class CreateAgentSessionRequest(BaseModel):
    site_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")


def _runtime_request_for_message(
    payload: DigitalTwinAgentMessageRequest,
    session_id: str,
    *,
    run_id: str = "",
    trusted_identity: dict[str, str] | None = None,
    trusted_site_id: str | None = None,
) -> object:
    intent = IntentRouter().classify(
        payload.user_input,
        session_id=session_id,
        trace_id=f"http_{session_id}",
    )
    preferred_tool_ids = INTENT_TO_CAPABILITIES.get(
        intent.intent_id,
        ("capability_discovery.search_tool",),
    )
    authoritative_site_id = trusted_site_id or payload.context.site_id
    device = payload.context.selected_device
    selected_device_id = device.device_id if device else ""
    query_asset_references = _asset_references(payload.user_input)
    selected_asset_scope = _query_inherits_selected_asset(
        payload.user_input,
        selected_device_id,
    )
    asset_query_scope = bool(query_asset_references) or selected_asset_scope
    asset_id = selected_device_id if selected_asset_scope else ""
    tool_ids = tuple(dict.fromkeys((*preferred_tool_ids, *MVP_AGENT_CAPABILITIES)))
    if not asset_query_scope:
        tool_ids = tuple(
            tool_id for tool_id in tool_ids if tool_id not in _DEVICE_SCOPED_CAPABILITIES
        )
    identity = trusted_identity or {}
    attributes = {
        "site_name": payload.context.site_name,
        "time_range": payload.context.time_range,
        "trusted_tenant_id": str(identity.get("tenant_id") or "tenant_lab"),
        "trusted_site_id": authoritative_site_id,
        "trusted_user_id": str(identity.get("user_id") or "runtime-system"),
        "trusted_role": str(identity.get("role") or "operator"),
    }
    visible_tool_ids = list(tool_ids)
    if asset_query_scope and "alarm.get_active_alarms" in tool_ids:
        visible_tool_ids.append("scene.highlight_asset")
    return runtime_pb2.StartTurnRequest(
        run_id=run_id,
        session_id=session_id,
        text=payload.user_input,
        context=runtime_pb2.ContextSnapshot(
            selected_asset_id=asset_id,
            environment="digital_twin",
            attributes=attributes,
        ),
        tool_refs=[
            runtime_pb2.ToolReference(tool_id=tool_id, version="0.1.0")
            for tool_id in tool_ids
        ],
        policy=runtime_pb2.PolicySnapshot(
            visible_tool_ids=visible_tool_ids,
            workflow_stage=intent.intent_id,
        ),
        approval=runtime_pb2.ApprovalSnapshot(
            status=runtime_pb2.APPROVAL_STATUS_NOT_REQUIRED
        ),
    )


def _query_mentions_selected_asset(query: str, selected_device_id: str) -> bool:
    if not selected_device_id:
        return False
    if selected_device_id.casefold() in query.casefold():
        return True
    return bool(_asset_references(query) & _asset_references(selected_device_id))


def _query_inherits_selected_asset(query: str, selected_device_id: str) -> bool:
    if not selected_device_id:
        return False
    references = _asset_references(query)
    if references:
        return _query_mentions_selected_asset(query, selected_device_id)
    return not _is_broad_asset_query(query)


def _is_broad_asset_query(query: str) -> bool:
    normalized = query.casefold()
    return any(
        marker in normalized
        for marker in (
            "总体",
            "整体",
            "全场",
            "全站",
            "整个场站",
            "所有设备",
            "全部设备",
            "设备清单",
            "系统概况",
            "overall",
            "all devices",
            "all assets",
            "site-wide",
        )
    )


def _asset_references(value: str) -> set[str]:
    references = {
        _normalize_asset_reference(match.group(0))
        for match in _ASSET_REFERENCE_PATTERN.finditer(value)
    }
    references.update(
        f"A-{int(match.group(1)):02d}"
        for match in _CHINESE_CONTAINER_REFERENCE_PATTERN.finditer(value)
    )
    return references


def _normalize_asset_reference(reference: str) -> str:
    compact = re.sub(r"[-_ ]", "", reference).upper()
    if compact.startswith("A"):
        return f"A-{int(compact[1:]):02d}"
    prefix = next(
        candidate
        for candidate in ("PACK", "CELL", "PCS", "STK", "CLU")
        if compact.startswith(candidate)
    )
    return f"{prefix}_{int(compact[len(prefix):]):02d}"


async def _execute_p1_capability_turn(
    payload: DigitalTwinAgentMessageRequest,
    container: AppContainer,
    session_id: str,
    *,
    run_id: str = "",
    emit: Callable[[str, dict], None] | None = None,
    trusted_identity: dict[str, str] | None = None,
    trusted_site_id: str | None = None,
) -> list[tuple[str, dict]]:
    request = _runtime_request_for_message(
        payload,
        session_id,
        run_id=run_id,
        trusted_identity=trusted_identity,
        trusted_site_id=trusted_site_id,
    )
    live_state = {"response_started": False}
    if emit is not None:
        emit(
            "phase.changed",
            {
                "status": "executing",
                "payload": {
                    "label": "正在执行分析任务",
                    "summary": "模型正在规划并调用完成任务所需的工具。",
                    "status": "running",
                    "stepId": "execution",
                },
            },
        )
    runtime_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="agent-runtime-turn",
    )
    runtime_future = runtime_executor.submit(
        lambda: asyncio.run(AgentRuntimeServicer(container).start_turn(request))
    )
    runtime_cursor = 0
    try:
        while not runtime_future.done():
            if emit is not None:
                runtime_cursor = _forward_runtime_events(
                    container,
                    run_id,
                    runtime_cursor,
                    emit,
                    live_state,
                )
            await asyncio.sleep(0.02)
        started = runtime_future.result()
    finally:
        runtime_executor.shutdown(wait=False)
    if emit is not None:
        _forward_runtime_events(
            container,
            started.run_id,
            runtime_cursor,
            emit,
            live_state,
        )
    # Coordinator Run 用于 SSE 恢复，Runtime Run 用于 Redis Streams；通过事件关联而不是新增映射实体。
    trace_events = container.traces.list_by_run_id(started.run_id)
    trace_id = next(
        (event.trace_id for event in trace_events if event.trace_id),
        None,
    )
    langfuse_export = next(
        (
            event
            for event in reversed(trace_events)
            if event.event_type == "langfuse.export.completed"
        ),
        None,
    )
    common = {"traceId": trace_id} if trace_id else {}
    events: list[tuple[str, dict]] = []
    if emit is None:
        events.append(
            (
                "phase.changed",
                {
                    **common,
                    "status": "executing",
                    "payload": {
                        "label": "正在执行分析任务",
                        "summary": "模型已完成任务规划，正在调用所需工具。",
                        "status": "running",
                        "stepId": "execution",
                    },
                },
            )
        )
    completed_tools: list[tuple[str, object, bool]] = []
    final_message: dict | None = None
    for event in started.initial_events:
        projection = MessageToDict(event.payload, preserving_proto_field_name=True)
        event_type = projection.get("event_type")
        if event_type == "assistant.completed":
            final_message = {
                "content": projection.get("content") or "",
                "reasoningSummary": projection.get("reasoning_summary") or "",
            }
            continue
        if event_type != "tool.completed":
            continue
        selected_tool_id = str(projection.get("tool_id") or "")
        result = projection.get("result")
        result_status, _result_data, should_highlight = _project_tool_result(
            selected_tool_id,
            result,
        )
        completed_tools.append((selected_tool_id, result, should_highlight))
        tool_label = _tool_label(selected_tool_id)
        tool_payload = {
            "label": tool_label,
            "summary": f"{tool_label}已完成，结果状态为 {result_status}。",
            "status": "completed",
            "stepId": f"tool:{selected_tool_id}",
            "toolLabel": tool_label,
        }
        if emit is None:
            events.append(
                (
                    "tool.started",
                    {
                        **common,
                        "observationId": projection.get("observation_id"),
                        "status": "executing",
                        "payload": {
                            **tool_payload,
                            "summary": f"正在执行{tool_label}。",
                            "status": "running",
                        },
                    },
                )
            )
            events.append(
                (
                    "tool.completed",
                    {
                        **common,
                        "observationId": projection.get("observation_id"),
                        "status": result_status,
                        "payload": {
                            **tool_payload,
                            "toolId": selected_tool_id,
                            "evidenceId": projection.get("evidence_id"),
                            "observationId": projection.get("observation_id"),
                        },
                    },
                )
            )
    if (
        request.context.selected_asset_id
        and "scene.highlight_asset" in request.policy.visible_tool_ids
        and any(should_highlight for _, _, should_highlight in completed_tools)
    ):
        runtime_run = container.runs.get(started.run_id)
        if runtime_run is None:
            raise RuntimeError("runtime_run_not_found")
        scene_action = container.capability_registry.invoke(
            "scene.highlight_asset",
            {},
            ToolExecutionContext(run=runtime_run, registry=container.capability_registry),
        )
        events.append(
            (
                "scene.action",
                {
                    "action": {
                        "command": scene_action["command"],
                        "assetId": scene_action["asset_id"],
                        "sceneNodeId": scene_action["scene_node_id"],
                    }
                },
            )
        )
    final_message = final_message or {
        "content": "本轮未产生可用模型摘要。",
        "reasoningSummary": "Agent Loop 未返回 assistant.completed 事件。",
    }
    reasoning_summary = str(final_message.get("reasoningSummary") or "")
    if reasoning_summary:
        events.append(
            (
                "reasoning.summary",
                {
                    **common,
                    "payload": {
                        "label": "正在生成诊断结论",
                        "summary": reasoning_summary[:80],
                        "status": "completed",
                        "stepId": "summary",
                    },
                },
            )
        )
    content = str(final_message.get("content") or "")
    if not live_state["response_started"]:
        events.append(
            (
                "response.started",
                {
                    **common,
                    "status": "streaming",
                    "payload": {},
                },
            )
        )
        for delta in _response_chunks(content):
            events.append(
                (
                    "response.delta",
                    {
                        **common,
                        "status": "streaming",
                        "payload": {"delta": delta},
                    },
                )
            )
    events.append(
        (
            "response.completed",
            {
                **common,
                "status": "streaming",
                "payload": {
                    "content": content,
                    "reasoningSummary": reasoning_summary,
                },
            },
        )
    )
    completed_at = datetime.now(timezone.utc).isoformat()
    events.append(
        (
            "run.completed",
            {
                **common,
                "status": "completed",
                "completedAt": completed_at,
                "externalObservability": (
                    {"langfuse": langfuse_export.payload}
                    if langfuse_export is not None
                    else None
                ),
                "payload": {"status": "completed", "completedAt": completed_at},
            },
        )
    )
    return events


def _forward_runtime_events(
    container: AppContainer,
    run_id: str,
    cursor: int,
    emit: Callable[[str, dict], None],
    state: dict[str, bool],
) -> int:
    """把 Runtime/Redis Streams 中的新事件安全投影到浏览器 SSE。"""
    history = container.event_bus.history(run_id)
    for runtime_event in history[cursor:]:
        event_type = str(runtime_event.get("event_type") or "")
        if event_type == "BeforeToolCall":
            tool_id = str(runtime_event.get("tool_id") or "")
            tool_label = _tool_label(tool_id)
            emit(
                "tool.started",
                {
                    "status": "executing",
                    "payload": {
                        "label": tool_label,
                        "summary": f"正在执行{tool_label}。",
                        "status": "running",
                        "stepId": f"tool:{tool_id}",
                        "toolId": tool_id,
                        "toolLabel": tool_label,
                    },
                },
            )
        elif event_type == "tool.completed":
            tool_id = str(runtime_event.get("tool_id") or "")
            result_status, _result_data, _should_highlight = _project_tool_result(
                tool_id,
                runtime_event.get("result"),
            )
            tool_label = _tool_label(tool_id)
            observation_id = runtime_event.get("observation_id")
            emit(
                "tool.completed",
                {
                    "status": result_status,
                    "observationId": observation_id,
                    "payload": {
                        "label": tool_label,
                        "summary": f"{tool_label}已完成，结果状态为 {result_status}。",
                        "status": "completed",
                        "stepId": f"tool:{tool_id}",
                        "toolId": tool_id,
                        "toolLabel": tool_label,
                        "evidenceId": runtime_event.get("evidence_id"),
                        "observationId": observation_id,
                    },
                },
            )
        elif event_type == "assistant.delta":
            delta = str(runtime_event.get("delta") or "")
            if not delta:
                continue
            if not state["response_started"]:
                emit(
                    "response.started",
                    {"status": "streaming", "payload": {}},
                )
                state["response_started"] = True
            emit(
                "response.delta",
                {"status": "streaming", "payload": {"delta": delta}},
            )
    return len(history)


def _response_chunks(content: str, chunk_size: int = 24) -> list[str]:
    """仅供不支持流式接口的本地/测试模型维持统一响应协议。"""
    if not content:
        return []
    return [content[index : index + chunk_size] for index in range(0, len(content), chunk_size)]


def _tool_label(tool_id: str) -> str:
    labels = {
        "asset.get_asset_status": "读取设备运行状态",
        "telemetry.get_latest_value": "读取设备实时遥测",
        "alarm.get_active_alarms": "查询设备活动告警",
        "workorder.create_work_order_draft": "生成待审核工单草稿",
        "skill.skill_list": "查询当前可用技能",
        "memory.session_search": "检索历史会话记录",
        "search.search_sop": "检索设备操作规程",
        "messaging.send_message_draft": "生成消息发送草稿",
        "task.get_workflow_status": "查询任务执行状态",
    }
    return labels.get(tool_id, "执行 Agent 工具")


def _project_tool_result(
    tool_id: str,
    result: object,
) -> tuple[str, object, bool]:
    """保留工具事实状态，只有成功且非空的活动告警才联动场景。"""
    if not isinstance(result, dict):
        return "failed", None, False
    status = str(result.get("status") or "failed")
    data = result.get("data")
    items = data.get("items") if isinstance(data, dict) else data
    should_highlight = (
        tool_id == "alarm.get_active_alarms"
        and status == "success"
        and isinstance(items, list)
        and bool(items)
    )
    return status, data, should_highlight


@http_router.get("/bootstrap")
async def agent_bootstrap() -> dict:
    response = await digital_twin_bootstrap()
    if response["data"]["bearer_token"]:
        response["data"]["bearer_token"] = Hs256JwtVerifier().issue_dev_token(
            user_id="0",
            scopes=[
                "agent:read",
                "agent:write",
                "tools:execute",
                "approvals:write",
                "sessions:read",
            ],
            role="operator",
            issuer=os.getenv("TOOL_GATEWAY_JWT_ISSUER"),
            token_type="access" if os.getenv("TOOL_GATEWAY_JWT_ISSUER") else None,
        )
    return response


@http_router.post("/sessions")
async def create_agent_session(
    payload: CreateAgentSessionRequest,
    auth: AuthContext = Depends(require_scope("agent:write", endpoint_id="agent.sessions.create")),
):
    session = agent_run_coordinator.create_session(site_id=payload.site_id, user_id=auth.user_id)
    return JSONResponse(status_code=201, content=api_success(session))


@http_router.post("/sessions/{session_id}/messages")
async def create_agent_user_turn(
    session_id: str,
    payload: DigitalTwinAgentMessageRequest,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("tools:execute", endpoint_id="agent.messages.create")),
):
    try:
        trusted_session = agent_run_coordinator.get_session(
            session_id,
            auth.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def execute(run_id: str) -> list[tuple[str, dict]]:
        def emit(event_type: str, fields: dict) -> None:
            if agent_run_coordinator.cancel_requested(run_id):
                return
            agent_run_coordinator.append(run_id, event_type, **fields)

        return await _execute_p1_capability_turn(
            payload,
            container,
            session_id,
            run_id=run_id,
            emit=emit,
            trusted_identity={
                "tenant_id": auth.tenant_id,
                "user_id": auth.user_id,
                "role": auth.role,
            },
            trusted_site_id=str(trusted_session["siteId"]),
        )

    try:
        run = agent_run_coordinator.start_run(
            session_id=session_id,
            user_id=auth.user_id,
            client_message_id=payload.client_message_id,
            execute_factory=execute,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(
        status_code=202,
        content=api_success(
            {
                "runId": run["runId"],
                "sessionId": session_id,
                "messageId": payload.client_message_id,
                "status": run["status"],
                "streamUrl": f"/api/v1/agent/runs/{run['runId']}/stream",
            }
        ),
    )


@http_router.get("/runs/{run_id}")
async def get_agent_run(
    run_id: str,
    auth: AuthContext = Depends(require_scope("agent:read", endpoint_id="agent.runs.get")),
) -> dict:
    try:
        return api_success(agent_run_coordinator.snapshot(run_id, auth.user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc


@http_router.get("/runs/{run_id}/stream")
async def stream_agent_run(
    run_id: str,
    auth: AuthContext = Depends(require_scope("agent:read", endpoint_id="agent.runs.stream")),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after_sequence: int | None = Query(default=None, alias="afterSequence", ge=0),
):
    try:
        agent_run_coordinator.snapshot(run_id, auth.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc
    cursor = max(int(last_event_id or "0"), after_sequence or 0)

    async def stream():
        nonlocal cursor
        next_heartbeat = monotonic() + 12
        while True:
            snapshot = agent_run_coordinator.snapshot(run_id, auth.user_id)
            for event in snapshot["events"]:
                if event["eventSequence"] <= cursor:
                    continue
                cursor = event["eventSequence"]
                yield _sse(event)
            if snapshot["status"] in TERMINAL_RUN_STATUSES and cursor >= int(snapshot["lastEventId"]):
                break
            if monotonic() >= next_heartbeat:
                heartbeat = {
                    "eventId": f"{run_id}:heartbeat:{int(monotonic())}",
                    "type": "heartbeat",
                    "runId": run_id,
                    "conversationId": snapshot["sessionId"],
                    "messageId": snapshot["clientMessageId"],
                    "sequence": cursor,
                    "eventSequence": cursor,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {},
                }
                yield _sse(heartbeat)
                next_heartbeat = monotonic() + 12
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@http_router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(
    run_id: str,
    auth: AuthContext = Depends(require_scope("agent:write", endpoint_id="agent.runs.cancel")),
) -> dict:
    try:
        run = agent_run_coordinator.cancel(run_id, auth.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc
    return api_success({"runId": run_id, "status": run["status"], "cancelRequested": True})


@http_router.post("/runs/{run_id}/approvals/{approval_id}")
async def approve_agent_run_action(
    run_id: str,
    approval_id: Literal["create_work_order_draft"],
    payload: DigitalTwinActionConfirmRequest,
    request: Request,
    container: AppContainer = Depends(get_container_dependency),
    auth: AuthContext = Depends(require_scope("approvals:write", endpoint_id="agent.approvals.write")),
) -> dict:
    try:
        agent_run_coordinator.snapshot(run_id, auth.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_not_found") from exc
    return await confirm_digital_twin_action(approval_id, payload, request, container, auth)
