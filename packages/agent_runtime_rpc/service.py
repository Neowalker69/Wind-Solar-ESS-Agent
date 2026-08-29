import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any, AsyncIterator
from uuid import uuid4

import grpc
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct
from google.protobuf.timestamp_pb2 import Timestamp

from apps.api_gateway.routers.front_router import route_intent
from apps.composition import AppContainer
from packages.agent_runtime_rpc.generated.agent_runtime.v1 import runtime_pb2, runtime_pb2_grpc
from packages.capabilities.industrial_context import (
    effective_target_asset_id,
    explicit_asset_reference,
)
from packages.context.compiler import ContextCompiler, estimate_tokens
from packages.context.lifecycle import ContextLifecycle
from packages.context.providers import (
    CapabilityContextToolGateway,
    RuntimeContextProvider,
    build_tool_gateway_context_providers,
)
from packages.context.scope import ContextScopeResolver
from packages.events.hooks import WorkflowHooks
from packages.harness_common.schemas.context import ContextBundle, ContextRequest
from packages.harness_common.schemas.learning import ReflectionTrigger
from packages.harness_common.schemas.plugin import ToolDefinition
from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.harness_common.schemas.tool_result import ToolResult, ToolResultStatus
from packages.harness_common.schemas.trace import TraceEvent
from packages.intent_router.router import IntentRouter
from packages.observability.langfuse_sink import (
    FORMAL_RUNTIME_TRACE_SOURCE,
    FORMAL_RUNTIME_VERSION,
)
from packages.rag.authoritative_corpus import default_corpus_root
from packages.tool_registry.registry import ToolExecutionContext
from packages.workflow.langgraph_runtime import AgentMainGraph


logger = logging.getLogger(__name__)


def _workspace_root_for_tool(tool_id: str) -> Path:
    return default_corpus_root() if tool_id == "search.search_sop" else Path.cwd()


_SELECTED_ASSET_TOOL_IDS = frozenset(
    {
        "asset.get_asset",
        "asset.get_asset_status",
        "asset.get_asset_criticality",
        "telemetry.get_latest_value",
        "telemetry.get_timeseries",
        "alarm.get_active_alarms",
        "alarm.get_alarm_history",
        "alarm.get_event_timeline",
        "scene.locate_asset_in_scene",
        "scene.highlight_asset",
    }
)


class AgentRuntimeServicer(runtime_pb2_grpc.AgentRuntimeServicer):
    """将现有 P0 Runtime 适配为版本化 gRPC 服务。"""

    def __init__(
        self,
        container: AppContainer,
        intent_router: IntentRouter | None = None,
        required_transport_secret: str | None = None,
    ) -> None:
        self.container = container
        self.intent_router = intent_router or IntentRouter()
        self.main_graph = AgentMainGraph()
        self.required_transport_secret = required_transport_secret
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def StartTurn(self, request, context):
        await self._authenticate_transport(context)
        try:
            run, intent_id, trace_id = self._prepare_turn(request)
            request_copy = runtime_pb2.StartTurnRequest()
            request_copy.CopyFrom(request)
            task = asyncio.create_task(
                asyncio.to_thread(
                    self._execute_prepared_turn,
                    run,
                    request_copy,
                    intent_id=intent_id,
                    trace_id=trace_id,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_task_finished)
            return self._start_turn_response(run)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except LookupError as exc:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))

    async def start_turn(self, request):
        """同步执行一轮 Capability Loop，供内部适配器和确定性测试复用。"""
        run, intent_id, trace_id = self._prepare_turn(request)
        self._execute_prepared_turn(
            run,
            request,
            intent_id=intent_id,
            trace_id=trace_id,
        )
        run = self.container.runs.get(run.run_id) or run
        return self._start_turn_response(run)

    def _prepare_turn(self, request) -> tuple[RunRecord, str, str]:
        if not request.session_id or not request.text.strip():
            raise ValueError("session_id_and_text_required")
        if not self._references_are_registered(request):
            raise LookupError("tool_or_skill_reference_unavailable")

        trace_nonce = request.run_id or uuid4().hex
        trace_id = f"grpc_{sha256(f'{request.session_id}:{trace_nonce}:{request.text}'.encode('utf-8')).hexdigest()[:24]}"
        intent = self.intent_router.classify(request.text, session_id=request.session_id, trace_id=trace_id)
        runtime_idempotency_key = (
            f"grpc:run:{request.run_id}"
            if request.run_id
            else f"grpc:{request.session_id}:{intent.user_turn_hash}"
        )
        route = route_intent(
            intent,
            idempotency_key=runtime_idempotency_key,
        )
        if request.run_id:
            route = route.model_copy(update={"run_id": request.run_id})
        runtime_context = self._runtime_context_from_request(request)
        requested_workflow_stage = str(
            runtime_context.get("policy", {}).get("workflow_stage") or ""
        )
        runtime_context["policy"] = {
            **dict(runtime_context.get("policy") or {}),
            "workflow_stage": intent.intent_id,
            "requested_workflow_stage": requested_workflow_stage,
        }
        route = route.model_copy(
            update={
                "normalized_input": {
                    **route.normalized_input,
                    "context": runtime_context,
                    "tool_refs": [self._tool_reference_to_dict(item) for item in request.tool_refs],
                    "skill_refs": [self._skill_reference_to_dict(item) for item in request.skill_refs],
                    "policy": self._policy_to_dict(request.policy),
                    "approval": self._approval_to_dict(request.approval),
                }
            }
        )
        run = self.container.run_dispatcher.dispatch(route)
        run = run.model_copy(update={"runtime_context": runtime_context})
        self.container.runs.create(run)
        self.container.traces.create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run.run_id,
                session_id=run.session_id,
                event_type="IntentClassified",
                node_name="intent",
                payload=intent.model_dump(mode="json"),
            )
        )
        self.container.event_bus.publish(
            run.run_id,
            {
                "event_type": "IntentClassified",
                "intent_id": intent.intent_id,
                "normalized_user_turn": intent.normalized_user_turn,
            },
        )
        return run, intent.intent_id, trace_id

    def _execute_prepared_turn(
        self,
        run: RunRecord,
        request,
        *,
        intent_id: str,
        trace_id: str,
    ) -> None:
        try:
            self.main_graph.invoke(
                run=run,
                request=request,
                intent_id=intent_id,
                trace_id=trace_id,
                execute=self._execute_capability_turn,
                observe_node=lambda node_name: self._record_langgraph_node(
                    run,
                    trace_id,
                    node_name,
                ),
            )
        except Exception as exc:
            # 后台学习入队失败或处理失败都不能覆盖主链路的原始异常。
            self._enqueue_reflection(
                run=run,
                request=request,
                trace_id=trace_id,
                trigger=ReflectionTrigger.RUN_FAILED,
                payload={"error": str(exc)[:300]},
            )
            self.container.runs.create(
                run.model_copy(
                    update={
                        "status": RunStatus.FAILED,
                        "completed_at": datetime.now(timezone.utc),
                        "error": {"code": "agent_turn_failed"},
                    }
                )
            )
            self.container.event_bus.publish(
                run.run_id,
                {
                    "event_type": "RunFailed",
                    "error_code": "agent_turn_failed",
                },
            )
            raise

    def _start_turn_response(self, run: RunRecord) -> runtime_pb2.StartTurnResponse:
        run = self.container.runs.get(run.run_id) or run
        initial_events = self._runtime_events_for_run(run)
        return runtime_pb2.StartTurnResponse(
            run_id=run.run_id,
            session_id=run.session_id,
            status=self._to_proto_run_status(run.status),
            initial_events=initial_events,
        )

    def _background_task_finished(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("agent_runtime_background_turn_failed")

    def _record_langgraph_node(
        self,
        run: RunRecord,
        trace_id: str,
        node_name: str,
    ) -> None:
        self.container.traces.create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run.run_id,
                session_id=run.session_id,
                event_type="langgraph.node.completed",
                node_name=node_name,
                status="completed",
                payload={"runtime": "langgraph", "node": node_name},
            )
        )

    async def StreamRunEvents(self, request, context) -> AsyncIterator[runtime_pb2.RuntimeEvent]:
        await self._authenticate_transport(context)
        run = self.container.runs.get(request.run_id)
        if run is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "run_not_found")
        cursor = int(request.after_sequence)
        next_heartbeat = monotonic() + 12
        terminal_statuses = {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
        while True:
            run = self.container.runs.get(request.run_id) or run
            events = self.container.event_bus.history(run.run_id)
            for index, event in enumerate(events, start=1):
                if index <= cursor:
                    continue
                cursor = index
                yield self._event_to_proto(run, event, index)

            run = self.container.runs.get(request.run_id) or run
            if run.status in terminal_statuses and cursor >= len(events):
                return
            if monotonic() >= next_heartbeat:
                yield self._heartbeat_event(run, cursor)
                next_heartbeat = monotonic() + 12
            await asyncio.sleep(0.05)

    async def GetRuntimeSnapshot(self, request, context):
        await self._authenticate_transport(context)
        run = self.container.runs.get(request.run_id)
        if run is None or run.session_id != request.session_id:
            await context.abort(grpc.StatusCode.NOT_FOUND, "runtime_snapshot_not_found")
        return runtime_pb2.GetRuntimeSnapshotResponse(
            session_id=run.session_id,
            run_id=run.run_id,
            context=self._context_to_proto(run.runtime_context),
            tools=[
                self._manifest_to_projection(manifest)
                for manifest in self.container.capability_registry.visible_manifests(
                    ToolExecutionContext(run=run, registry=self.container.capability_registry)
                )
            ],
            skills=[self._skill_to_projection(skill) for skill in self.container.skill_meta_tools.service.registry.repo.list_all()],
            run_status=self._to_proto_run_status(run.status),
        )

    async def _authenticate_transport(self, context) -> None:
        if not self.required_transport_secret:
            return
        metadata = dict(context.invocation_metadata())
        expected = f"Bearer {self.required_transport_secret}"
        if metadata.get("authorization") != expected:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "control_runtime_auth_required",
            )

    def _runtime_events_for_run(self, run: RunRecord) -> list[runtime_pb2.RuntimeEvent]:
        events = self.container.event_bus.history(run.run_id)
        return [self._event_to_proto(run, event, index) for index, event in enumerate(events, start=1)]

    @staticmethod
    def _heartbeat_event(run: RunRecord, sequence: int) -> runtime_pb2.RuntimeEvent:
        timestamp = Timestamp()
        timestamp.FromDatetime(datetime.now(timezone.utc))
        payload = Struct()
        ParseDict({"event_type": "Heartbeat"}, payload)
        return runtime_pb2.RuntimeEvent(
            event_id=f"{run.run_id}:heartbeat:{sequence}",
            event_type=runtime_pb2.RUNTIME_EVENT_TYPE_UNSPECIFIED,
            session_id=run.session_id,
            run_id=run.run_id,
            occurred_at=timestamp,
            payload=payload,
            sequence=sequence,
        )

    def _execute_capability_turn(self, run: RunRecord, request, *, intent_id: str, trace_id: str) -> None:
        """执行一次可审计 Agent Loop：模型规划、工具执行、证据落库和模型总结。"""
        manifests = {
            manifest.tool_id: manifest for manifest in self.container.capability_registry.list_manifests()
        }
        readability_context = ToolExecutionContext(
            run=run,
            registry=self.container.capability_registry,
        )
        allowed_tool_ids = [
            reference.tool_id
            for reference in request.tool_refs
            if reference.tool_id in manifests
            and self.container.capability_registry.is_readable(
                reference.tool_id,
                readability_context,
            )
        ]
        allowed_tool_ids = self._scope_tools_for_request(request, allowed_tool_ids)
        context_bundle = self._compile_runtime_context(
            run=run,
            request=request,
            intent_id=intent_id,
            trace_id=trace_id,
            allowed_tool_ids=allowed_tool_ids,
        )
        run = self.container.runs.get(run.run_id) or run
        if not context_bundle.allow_tool_calls:
            allowed_tool_ids = []
        if not allowed_tool_ids:
            return
        hooks = WorkflowHooks(self.container.event_bus)
        hooks.before_tool_discovery(run.run_id, {"tool_ids": allowed_tool_ids})
        model = self.container.model_router.resolve()
        planning_messages = self._planning_messages(
            request=request,
            intent_id=intent_id,
            allowed_tool_ids=allowed_tool_ids,
            context_bundle=context_bundle,
        )
        execution_context = ToolExecutionContext(
            run=run,
            registry=self.container.capability_registry,
            services={
                "skill_meta_tools": self.container.skill_meta_tools,
                "memory_service": self.container.memory_service,
                "rag_search_service": self.container.rag_search_service,
                "session_search": self.container.session_search,
                "evidence_repo": self.container.evidence,
                "durable_workflows": self.container.durable_workflows,
                "station_api": self.container.station_api_client,
            },
        )
        tool_results: list[dict[str, Any]] = []
        model_tools = [
            self._manifest_to_model_tool(manifests[tool_id])
            for tool_id in allowed_tool_ids
        ]
        required_tool_id = self._required_tool_for_intent(
            intent_id,
            allowed_tool_ids,
        )
        for planning_iteration in range(1, 7):
            planning_started = perf_counter()
            completed_tool_ids = {
                str(item.get("tool_id") or "") for item in tool_results
            }
            tool_choice: str | dict[str, Any] = "auto"
            if required_tool_id and required_tool_id not in completed_tool_ids:
                tool_choice = {
                    "type": "function",
                    "function": {"name": required_tool_id.replace(".", "__")},
                }
            planning_result = model.complete(
                messages=planning_messages,
                tools=model_tools,
                tool_choice=tool_choice,
            )
            planning_duration_ms = max(
                0,
                round((perf_counter() - planning_started) * 1000),
            )
            selected_calls = self._selected_tool_calls(
                planning_result,
                allowed_tool_ids,
                planning_iteration=planning_iteration,
            )
            tool_selection_source = "model"
            effective_tool_calls = list(planning_result.get("tool_calls") or [])
            if required_tool_id:
                required_already_selected = required_tool_id in completed_tool_ids
                fresh_calls: list[tuple[str, dict[str, Any], str]] = []
                for call in selected_calls:
                    if call[0] == required_tool_id:
                        if required_already_selected:
                            continue
                        required_already_selected = True
                    fresh_calls.append(call)
                if len(fresh_calls) != len(selected_calls):
                    selected_calls = fresh_calls
                    effective_tool_calls = [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_id.replace(".", "__"),
                                "arguments": json.dumps(
                                    arguments,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                        }
                        for tool_id, arguments, tool_call_id in selected_calls
                    ]
                    tool_selection_source = "model_duplicate_ignored"
            if (
                not selected_calls
                and required_tool_id
                and required_tool_id not in completed_tool_ids
            ):
                tool_call_id = f"intent-required-{planning_iteration}"
                selected_calls = [(required_tool_id, {}, tool_call_id)]
                effective_tool_calls = [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": required_tool_id.replace(".", "__"),
                            "arguments": "{}",
                        },
                    }
                ]
                tool_selection_source = "intent_router_required"
            selected_tool_ids = [
                tool_id for tool_id, _, _ in selected_calls
            ]
            planning_stage = (
                "planning"
                if planning_iteration == 1
                else f"planning.{planning_iteration}"
            )
            self.container.event_bus.publish(
                run.run_id,
                {
                    "event_type": "model.completed",
                    "stage": planning_stage,
                    "model_id": model.model_id,
                    "selected_tool_ids": selected_tool_ids,
                    "tool_selection_source": tool_selection_source,
                },
            )
            self._record_model_completion(
                run=run,
                trace_id=trace_id,
                stage=planning_stage,
                model=model,
                messages=planning_messages,
                result=planning_result,
                duration_ms=planning_duration_ms,
                extra_payload={
                    "allowed_tool_ids": allowed_tool_ids,
                    "selected_tool_ids": selected_tool_ids,
                    "tool_selection_source": tool_selection_source,
                    "context_snapshot_id": context_bundle.snapshot_id,
                    "context_utilization": context_bundle.utilization,
                    "context_compression_level": context_bundle.compression_level,
                    "context_cache_hits": context_bundle.cache_hits,
                },
            )
            if not selected_calls:
                break

            planning_messages.append(
                {
                    "role": "assistant",
                    "content": str(planning_result.get("content") or ""),
                    "tool_calls": effective_tool_calls,
                }
            )
            for selected, model_arguments, tool_call_id in selected_calls:
                # SOP 仅检索既有 docs 边界，避免把运行依赖和代码仓库误当作操作规程扫描。
                execution_context.services["workspace_root"] = _workspace_root_for_tool(selected)
                if selected == "workorder.create_work_order_draft":
                    self._capture_selected_asset_context(run, trace_id)
                hooks.before_tool_call(run.run_id, {"tool_id": selected})
                # 模型参数优先；通用字段只补充缺省值，避免覆盖模型明确提取出的业务参数。
                invocation_payload = self._tool_invocation_payload(
                    request,
                    selected,
                    model_arguments,
                )
                tool_started = perf_counter()
                failure_message = ""
                try:
                    tool_result = (
                        self.container.capability_registry.execute_for_model(
                            selected,
                            invocation_payload,
                            execution_context,
                        )
                    )
                except Exception as exc:
                    # 将未归一化异常转成稳定的失败结果，后续仍走 Observation/Trace 链路。
                    tool_result = ToolResult.failed("tool_call_failed")
                    failure_message = str(exc)[:240]
                result = tool_result.model_dump(mode="json")
                manifest = manifests[selected]
                failed = tool_result.status == ToolResultStatus.FAILED
                failure_code = str((tool_result.error or {}).get("code") or "tool_execution_failed")
                if failed:
                    # 原始异常只留在服务端 hook；对事件和模型仅暴露稳定错误码。
                    hooks.tool_call_failure(
                        run.run_id,
                        {
                            "tool_id": selected,
                            "error_code": failure_code,
                            **({"message": failure_message} if failure_message else {}),
                        },
                    )
                observation = (
                    self.container.observation_service.capture_tool_observation(
                        tool=ToolDefinition(
                            name=manifest.tool_id,
                            version=manifest.version,
                            description=manifest.description,
                            input_schema=manifest.input_schema,
                            output_schema=manifest.output_schema,
                            risk_level=manifest.risk_level,
                            plugin_id=manifest.capability,
                            plugin_version=manifest.version,
                        ),
                        raw_observation={
                            "tool_id": selected,
                            "result": result,
                        },
                        run_id=run.run_id,
                        trace_id=trace_id,
                    )
                )
                completed = {
                    "tool_id": selected,
                    "status": tool_result.status,
                    "result": result,
                    "observation_id": observation.observation_id,
                    "evidence_id": observation.evidence_id,
                    **({"error_code": failure_code} if failed else {}),
                }
                tool_duration_ms = max(
                    0,
                    round((perf_counter() - tool_started) * 1000),
                )
                tool_results.append(completed)
                planning_messages.append(
                    self._tool_result_message(
                        tool_call_id,
                        selected,
                        completed,
                    )
                )
                self.container.event_bus.publish(
                    run.run_id,
                    {"event_type": "tool.completed", **completed},
                )
                self.container.traces.create(
                    TraceEvent(
                        trace_id=trace_id,
                        run_id=run.run_id,
                        session_id=run.session_id,
                        event_type="tool.completed",
                        node_name=selected,
                        tool_name=selected,
                        tool_version=manifest.version,
                        plugin_id=manifest.capability,
                        plugin_version=manifest.version,
                        observation_id=observation.observation_id,
                        evidence_ids=(
                            [observation.evidence_id]
                            if observation.evidence_id
                            else []
                        ),
                        duration_ms=tool_duration_ms,
                        status=tool_result.status.value,
                        payload={
                            "input": invocation_payload,
                            "result": result,
                            "observation_id": observation.observation_id,
                            "evidence_id": observation.evidence_id,
                        },
                    )
                )
                if failed:
                    continue
                hooks.after_tool_call(
                    run.run_id,
                    {"tool_id": selected, "status": "ok"},
                )

        streaming_summary = callable(getattr(model, "complete_stream", None))
        summary_messages = self._summary_messages(
            request=request,
            intent_id=intent_id,
            tool_results=tool_results,
            context_bundle=context_bundle,
            structured=not streaming_summary,
        )
        self.container.event_bus.publish(
            run.run_id,
            {"event_type": "assistant.started"},
        )
        summary_started = perf_counter()
        if streaming_summary:
            summary_result = model.complete_stream(
                messages=summary_messages,
                on_delta=lambda delta: self.container.event_bus.publish(
                    run.run_id,
                    {"event_type": "assistant.delta", "delta": delta},
                ),
            )
        else:
            summary_result = model.complete(
                messages=summary_messages,
                response_schema={
                    "name": "AgentTurnSummary",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "reasoning_summary": {"type": "string"},
                        },
                        "required": ["summary", "reasoning_summary"],
                        "additionalProperties": False,
                    },
                },
            )
        summary_duration_ms = max(0, round((perf_counter() - summary_started) * 1000))
        content, reasoning_summary = self._summary_from_model(
            summary_result,
            intent_id=intent_id,
            tool_results=tool_results,
        )
        self.container.event_bus.publish(
            run.run_id,
            {
                "event_type": "assistant.completed",
                "content": content,
                "reasoning_summary": reasoning_summary,
                "model_id": model.model_id,
            },
        )
        self._record_model_completion(
            run=run,
            trace_id=trace_id,
            stage="summary",
            model=model,
            messages=summary_messages,
            result=summary_result,
            duration_ms=summary_duration_ms,
            extra_payload={
                "evidence_ids": [
                    item.get("evidence_id")
                    for item in tool_results
                    if item.get("evidence_id")
                ],
                "context_snapshot_id": context_bundle.snapshot_id,
                "context_utilization": context_bundle.utilization,
                "context_compression_level": context_bundle.compression_level,
                "context_cache_hits": context_bundle.cache_hits,
            },
        )
        final_evidence_ids = [
            item["evidence_id"]
            for item in tool_results
            if item.get("evidence_id")
        ]
        self.container.traces.create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run.run_id,
                session_id=run.session_id,
                event_type="assistant.completed",
                node_name="final",
                model_id=model.model_id,
                model_version=model.model_version,
                evidence_ids=final_evidence_ids,
                payload={
                    "content": content,
                    "reasoning_summary": reasoning_summary,
                    "evidence_ids": final_evidence_ids,
                },
            )
        )
        self._enqueue_reflection(
            run=run,
            request=request,
            trace_id=trace_id,
            trigger=ReflectionTrigger.RUN_COMPLETED,
            payload={
                "intent": intent_id,
                "user_turn": request.text,
                "asset_id": request.context.selected_asset_id or None,
                "evidence_ids": final_evidence_ids,
                "workflow_stage": request.policy.workflow_stage or intent_id,
            },
        )

        self.container.runs.create(
            run.model_copy(
                update={
                    "status": RunStatus.COMPLETED,
                    "model_id": model.model_id,
                    "model_version": model.model_version,
                    "completed_at": datetime.now(timezone.utc),
                }
            )
        )
        self.container.event_bus.publish(
            run.run_id,
            {
                "event_type": "RunStop",
                "status": "completed",
                "content": content,
                "reasoning_summary": reasoning_summary,
            },
        )
        self._export_runtime_trace(run, trace_id, request)

    @staticmethod
    def _required_tool_for_intent(
        intent_id: str,
        allowed_tool_ids: list[str],
    ) -> str | None:
        required_by_intent = {
            "sop.search": "search.search_sop",
        }
        tool_id = required_by_intent.get(intent_id)
        return tool_id if tool_id in allowed_tool_ids else None

    @staticmethod
    def _tool_invocation_payload(request, selected: str, model_arguments: dict[str, Any]) -> dict[str, Any]:
        """补齐模型不应负责猜测的运行时字段，同时保留模型显式参数。"""
        payload: dict[str, Any] = {
            "query": request.text,
            "content": request.text,
            "question": request.text,
            **model_arguments,
        }
        selected_asset_id = str(request.context.selected_asset_id or "")
        explicit_asset_id = explicit_asset_reference(request.text)
        target_asset_id = effective_target_asset_id(
            request.text,
            selected_asset_id,
        )
        if selected in _SELECTED_ASSET_TOOL_IDS and target_asset_id:
            if explicit_asset_id:
                # The entity named by the user is authoritative over model arguments.
                payload["asset_id"] = explicit_asset_id
            else:
                payload.setdefault("asset_id", target_asset_id)
        if selected != "telemetry.get_timeseries":
            return payload

        time_range = str(request.context.attributes.get("time_range") or "24h").lower()
        windows = {
            "realtime": (timedelta(hours=1), "1m"),
            "6h": (timedelta(hours=6), "5m"),
            "24h": (timedelta(hours=24), "5m"),
            "7d": (timedelta(days=7), "1h"),
            "30d": (timedelta(days=30), "1h"),
        }
        window, default_interval = windows.get(time_range, windows["24h"])
        end = datetime.now(timezone.utc)
        payload.setdefault("start", (end - window).isoformat().replace("+00:00", "Z"))
        payload.setdefault("end", end.isoformat().replace("+00:00", "Z"))
        payload.setdefault("interval", default_interval)
        payload.setdefault("aggregation", "avg")
        return payload

    @staticmethod
    def _scope_tools_for_request(
        request,
        allowed_tool_ids: list[str],
    ) -> list[str]:
        target_asset_id = effective_target_asset_id(
            request.text,
            str(request.context.selected_asset_id or ""),
        )
        if not target_asset_id:
            return list(allowed_tool_ids)
        return [
            tool_id
            for tool_id in allowed_tool_ids
            if tool_id != "asset.list_assets"
        ]

    def _enqueue_reflection(
        self,
        *,
        run: RunRecord,
        request: Any,
        trace_id: str,
        trigger: ReflectionTrigger,
        payload: dict[str, Any],
    ) -> None:
        attributes = dict(request.context.attributes)
        try:
            self.container.reflection_service.enqueue(
                trigger=trigger,
                run_id=run.run_id,
                session_id=run.session_id,
                trace_ids=[trace_id],
                tenant_id=str(attributes.get("trusted_tenant_id") or "tenant_lab"),
                site_id=str(attributes.get("trusted_site_id") or "site-unresolved"),
                user_id=str(attributes.get("trusted_user_id") or "runtime-system"),
                project_id=(
                    str(attributes["trusted_project_id"])
                    if attributes.get("trusted_project_id")
                    else None
                ),
                payload=payload,
                idempotency_key=f"reflection:{run.run_id}:{trigger.value}",
            )
        except Exception as exc:
            # Redis 或 Job Store 短暂故障只记录 Trace，不影响已完成的用户响应。
            self.container.traces.create(
                TraceEvent(
                    trace_id=trace_id,
                    run_id=run.run_id,
                    session_id=run.session_id,
                    event_type="reflection.enqueue_failed",
                    node_name="reflection",
                    payload={
                        "trigger": trigger.value,
                        "error": str(exc)[:300],
                    },
                )
            )

    def _compile_runtime_context(
        self,
        *,
        run: RunRecord,
        request: Any,
        intent_id: str,
        trace_id: str,
        allowed_tool_ids: list[str],
    ) -> ContextBundle:
        attributes = dict(request.context.attributes)
        trusted_identity = {
            "tenant_id": str(attributes.get("trusted_tenant_id") or "tenant_lab"),
            "user_id": str(attributes.get("trusted_user_id") or "runtime-system"),
            "role": str(attributes.get("trusted_role") or "operator"),
        }
        session = {
            "sessionId": run.session_id,
            "siteId": str(attributes.get("trusted_site_id") or "site-unresolved"),
            "userId": trusted_identity["user_id"],
        }
        scope = ContextScopeResolver().resolve(
            trusted_identity=trusted_identity,
            session=session,
            runtime_context=run.runtime_context,
        )
        tool_schema_tokens = sum(
            estimate_tokens(
                self.container.capability_registry.get_manifest(tool_id).input_schema
            )
            for tool_id in allowed_tool_ids
        )
        context_request = ContextRequest(
            query=request.text,
            intent=intent_id,
            scope=scope,
            context_window=int(os.getenv("AGENT_HARNESS_CONTEXT_WINDOW", "32768")),
            reserved_output_tokens=int(
                os.getenv("AGENT_HARNESS_RESERVED_OUTPUT_TOKENS", "4096")
            ),
            tool_schema_tokens=tool_schema_tokens,
            allowed_tool_ids=allowed_tool_ids,
            runtime_context={
                **run.runtime_context,
                "run_id": run.run_id,
                "session_id": run.session_id,
            },
        )
        lifecycle = ContextLifecycle(
            providers=[
                RuntimeContextProvider(),
                *build_tool_gateway_context_providers(
                    CapabilityContextToolGateway(
                        self.container.capability_registry,
                        ToolExecutionContext(
                            run=run,
                            registry=self.container.capability_registry,
                            user={
                                **trusted_identity,
                                "site_id": scope.site_id,
                            },
                            services={
                                "skill_meta_tools": self.container.skill_meta_tools,
                                "memory_service": self.container.memory_service,
                                "rag_search_service": self.container.rag_search_service,
                                "session_search": self.container.session_search,
                                "evidence_repo": self.container.evidence,
                                "durable_workflows": self.container.durable_workflows,
                                "station_api": self.container.station_api_client,
                            },
                        ),
                    )
                ),
            ],
            compiler=ContextCompiler(),
            provider_cache=self.container.context_provider_cache,
        )
        bundle = lifecycle.compile(context_request)
        snapshot = bundle.model_dump(mode="json")
        updated_context = {**run.runtime_context, "context_bundle": snapshot}
        self.container.runs.create(
            run.model_copy(update={"runtime_context": updated_context})
        )
        self.container.traces.create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run.run_id,
                session_id=run.session_id,
                event_type="context.compiled",
                node_name="context",
                status="completed",
                payload={
                    "snapshot_id": bundle.snapshot_id,
                    "scope": bundle.scope.model_dump(mode="json"),
                    "model_items": [
                        item.model_dump(mode="json") for item in bundle.model_items
                    ],
                    "excluded_ids": bundle.excluded_ids,
                    "missing_context": [str(kind) for kind in bundle.missing_context],
                    "conflicts": [
                        conflict.model_dump(mode="json")
                        for conflict in bundle.conflicts
                    ],
                    "provider_failures": [
                        failure.model_dump(mode="json")
                        for failure in bundle.provider_failures
                    ],
                    "cache_hits": bundle.cache_hits,
                    "tokens_used": bundle.tokens_used,
                    "token_budget": bundle.token_budget,
                    "utilization": bundle.utilization,
                    "compression_level": bundle.compression_level,
                    "compaction_steps": bundle.compaction_steps,
                    "allow_tool_calls": bundle.allow_tool_calls,
                    "warnings": bundle.warnings,
                    "lifecycle_runtime": bundle.lifecycle_runtime,
                },
            )
        )
        return bundle

    def _export_runtime_trace(self, run: RunRecord, trace_id: str, request: Any) -> None:
        runtime_events = [
            event
            for event in self.container.traces.list_by_run_id(run.run_id)
            if event.trace_id == trace_id
            and event.event_type
            in {"model.completed", "tool.completed", "assistant.completed"}
        ]
        user_id = str(request.context.attributes.get("user_id") or "") or None
        result = self.container.langfuse_runtime_sink.record_runtime_events(
            events=runtime_events,
            user_id=user_id,
        )
        event_counts = {
            event_type: sum(
                event.event_type == event_type for event in runtime_events
            )
            for event_type in (
                "model.completed",
                "tool.completed",
                "assistant.completed",
            )
        }
        self.container.traces.create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run.run_id,
                session_id=run.session_id,
                event_type="langfuse.export.completed",
                node_name="observability",
                status=result.status,
                error={"message": result.error} if result.error else None,
                payload={
                    "enabled": result.enabled,
                    "status": result.status,
                    "error": result.error,
                    "langfuse_trace_id": result.trace_id,
                    "trace_url": result.trace_url,
                    "source": FORMAL_RUNTIME_TRACE_SOURCE,
                    "runtime_version": FORMAL_RUNTIME_VERSION,
                    "event_counts": event_counts,
                },
            )
        )

    def _record_model_completion(
        self,
        *,
        run: RunRecord,
        trace_id: str,
        stage: str,
        model: Any,
        messages: list[dict[str, str]],
        result: dict[str, Any],
        duration_ms: int,
        extra_payload: dict[str, Any],
    ) -> None:
        audited_output = {
            key: value
            for key, value in result.items()
            if key not in {"raw", "reasoning_content"}
        }
        provider = str(getattr(model, "provider", "unknown"))
        self.container.traces.create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run.run_id,
                session_id=run.session_id,
                event_type="model.completed",
                node_name=stage,
                model_id=model.model_id,
                model_version=model.model_version,
                input_hash=self._stable_hash(messages),
                output_hash=self._stable_hash(audited_output),
                duration_ms=duration_ms,
                payload={
                    "stage": stage,
                    "provider": provider,
                    "input": messages,
                    "response_id": result.get("response_id"),
                    "finish_reason": result.get("finish_reason"),
                    "usage": result.get("usage") or {},
                    "output": audited_output,
                    **extra_payload,
                },
            )
        )

    @staticmethod
    def _stable_hash(value: Any) -> str:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    def _capture_selected_asset_context(self, run: RunRecord, trace_id: str) -> None:
        context_manifest = self.container.capability_registry.get_manifest(
            "runtime_context.get_selected_asset_context"
        )
        self.container.observation_service.capture_tool_observation(
            tool=ToolDefinition(
                name=context_manifest.tool_id,
                version=context_manifest.version,
                description=context_manifest.description,
                input_schema=context_manifest.input_schema,
                output_schema=context_manifest.output_schema,
                risk_level=context_manifest.risk_level,
                plugin_id=context_manifest.capability,
                plugin_version=context_manifest.version,
            ),
            raw_observation={"selected_asset_id": run.runtime_context.get("selected_asset_id")},
            run_id=run.run_id,
            trace_id=trace_id,
        )

    def _planning_messages(
        self,
        *,
        request,
        intent_id: str,
        allowed_tool_ids: list[str],
        context_bundle: ContextBundle | None = None,
    ) -> list[dict[str, str]]:
        context = {
            "selected_asset_id": request.context.selected_asset_id,
            "target_asset_id": effective_target_asset_id(
                request.text,
                str(request.context.selected_asset_id or ""),
            ),
            "environment": request.context.environment,
            "attributes": dict(request.context.attributes),
        }
        return [
            {
                "role": "system",
                "content": self.container.agent_context_prefill.system_prompt(
                    "根据用户当前 turn 和已识别意图选择完成任务所需的最少工具。"
                    "只调用提供的工具；每次工具结果返回后继续规划，直到任务完成或无法继续。"
                    "规划阶段输出仅为内部草稿，不得冒充最终回答；没有更多工具时停止调用，"
                    "最终答案由独立 summary 阶段依据 Evidence 生成。"
                    "用户未明确点名场站或设备时，必须按总体查询处理，不得自行套用界面选中设备；"
                    "总体查询优先使用资产列表和不带实体过滤的告警工具，只有明确设备查询才调用单设备资产或遥测工具。"
                    "当 context.target_asset_id 非空时，所有设备查询工具必须使用该 asset_id，且不得调用资产全量列表。"
                    "诊断、根因分析或根因排序意图必须包含可用的诊断工具；"
                    "如需设备、遥测或告警事实，可在同一次规划中同时调用对应事实工具；"
                    "事实工具必须排在诊断工具之前，确保派生结论只能消费本轮已记录的 Evidence。"
                    + (
                        "\n\n以下是本轮 Context Engine 编译的唯一上下文快照：\n"
                        + context_bundle.model_context
                        if context_bundle is not None
                        else ""
                    )
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_turn": request.text,
                        "intent_id": intent_id,
                        "context": context,
                        "allowed_tool_ids": allowed_tool_ids,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _summary_messages(
        self,
        *,
        request,
        intent_id: str,
        tool_results: list[dict[str, Any]],
        context_bundle: ContextBundle | None = None,
        structured: bool = True,
    ) -> list[dict[str, str]]:
        output_contract = (
            "必须返回 JSON 对象，且只使用两个顶层字段："
            'summary（面向用户的最终答案）和 reasoning_summary（简短的证据说明）。'
            if structured
            else "只返回面向用户的中文最终答案正文，不要输出 JSON、隐藏思维链或额外协议标记。"
        )
        return [
            {
                "role": "system",
                "content": self.container.agent_context_prefill.system_prompt(
                    "仅依据本轮工具 Observation 生成中文事实摘要。"
                    "必须回答用户问题中的对象、状态、编号和数值；证据不足时明确说明不确定。"
                    "告警编号优先使用 alarm_uuid，不得用数据库内部数值 id 替代。"
                    "不得输出隐藏思维链，不得编造工具结果中不存在的事实。"
                    "RAG Observation 的 truncated 表示已按模型预算压缩；只要 result.data 中仍有正文，"
                    "必须使用保留的 chunk 与 citation 作答，不得仅因 truncated 判定为无数据。"
                    "遥测必须按指标分别判断 stale；存在新鲜与过期混合指标时，保留新鲜指标的当前值，"
                    "只把 stale=true 的具体指标标记为过期，不得将整组遥测概括为全部过期。"
                    + (
                        "上下文缺失与冲突必须按快照 warnings 明确披露，不得自行补全。"
                        if context_bundle is not None
                        else ""
                    )
                    + output_contract
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_turn": request.text,
                        "intent_id": intent_id,
                        "context_snapshot_id": (
                            context_bundle.snapshot_id
                            if context_bundle is not None
                            else None
                        ),
                        "context_warnings": (
                            context_bundle.warnings
                            if context_bundle is not None
                            else []
                        ),
                        "tool_observations": [
                            self._bounded_tool_result(result)
                            for result in tool_results
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    @staticmethod
    def _manifest_to_model_tool(manifest) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                # OpenAI-compatible function name 不接受点号，描述中保留真实 Capability ID。
                "name": manifest.tool_id.replace(".", "__"),
                "description": f"[{manifest.tool_id}] {manifest.description}",
                "parameters": manifest.input_schema or {"type": "object", "properties": {}},
            },
        }

    @staticmethod
    def _selected_tool_calls(
        planning_result: dict[str, Any],
        allowed_tool_ids: list[str],
        *,
        planning_iteration: int = 1,
    ) -> list[tuple[str, dict[str, Any], str]]:
        selected: list[tuple[str, dict[str, Any], str]] = []
        for call_index, call in enumerate(
            planning_result.get("tool_calls") or [],
            start=1,
        ):
            function = call.get("function") or {}
            model_tool_name = str(function.get("name") or "")
            tool_id = model_tool_name if model_tool_name in allowed_tool_ids else model_tool_name.replace("__", ".")
            if tool_id not in allowed_tool_ids:
                continue
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_call_id = str(
                call.get("id")
                or f"tool_call_{planning_iteration}_{call_index}"
            )
            selected.append((tool_id, arguments, tool_call_id))
        return selected

    @staticmethod
    def _tool_result_message(
        tool_call_id: str,
        tool_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        bounded = AgentRuntimeServicer._bounded_tool_result(result)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_id.replace(".", "__"),
            "content": json.dumps(
                bounded,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ),
        }

    @staticmethod
    def _bounded_tool_result(result: dict[str, Any]) -> dict[str, Any]:
        from packages.agent_runtime_rpc.result_projection import bounded_tool_result

        return bounded_tool_result(result)

    @classmethod
    def _summary_from_model(
        cls,
        summary_result: dict[str, Any],
        *,
        intent_id: str,
        tool_results: list[dict[str, Any]],
    ) -> tuple[str, str]:
        structured = summary_result.get("structured")
        if not isinstance(structured, dict):
            structured = {}
        content = summary_result.get("content")
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                structured = {**parsed, **structured}
        summary = str(structured.get("summary") or "").strip()
        reasoning_summary = str(structured.get("reasoning_summary") or "").strip()
        if not summary and structured:
            # DeepSeek JSON mode不强制 Schema；保留模型生成的非标准字段内容，不误判成空响应。
            summary = "；".join(
                f"{key}：{value}"
                for key, value in structured.items()
                if key not in {"reasoning_summary"} and value not in (None, "", [], {})
            )
        if not summary and isinstance(content, str) and content.strip() and not content.startswith("mock:"):
            summary = content.strip()
        if tool_results and not any(
            item.get("status") in {"success", "partial"}
            for item in tool_results
        ):
            # 没有成功事实时，模型文本不能把 no_data/failed 改写成正常状态或确定性根因。
            summary = cls._grounded_fallback_summary(tool_results)
        if not summary or summary.startswith("{"):
            summary = cls._grounded_fallback_summary(tool_results)
        telemetry_facts = [
            item
            for item in tool_results
            if item.get("tool_id") == "telemetry.get_latest_value"
            if isinstance(item.get("result"), dict)
            and isinstance(item["result"].get("data"), dict)
            and isinstance(item["result"]["data"].get("stale"), bool)
        ]
        stale_facts = [
            item
            for item in telemetry_facts
            if item["result"]["data"]["stale"] is True
        ]
        fresh_facts = [
            item
            for item in telemetry_facts
            if item["result"]["data"]["stale"] is False
        ]
        if stale_facts and any(label in summary for label in ("当前", "实时", "最新")):
            if fresh_facts:
                stale_details = []
                metric_labels = {
                    "power_kw": "功率",
                    "temperature": "温度",
                    "soc": "SOC",
                    "soh": "SOH",
                }
                for item in stale_facts:
                    data = item["result"]["data"]
                    metric = str(data.get("metric") or "未知指标")
                    label = metric_labels.get(metric.casefold(), metric)
                    stale_details.append(
                        f"{label}（事实时间：{data.get('fact_time') or '未知'}）"
                    )
                summary = (
                    summary.rstrip()
                    + "\n\n时效性校正：仅 "
                    + "、".join(stale_details)
                    + " 已过期，不能作为当前或实时值使用；其他 freshness 标记正常的遥测仍可作为当前值。"
                )
            else:
                fact_times = sorted(
                    {
                        str(item["result"]["data"].get("fact_time") or "未知")
                        for item in stale_facts
                    }
                )
                summary = (
                    f"遥测数据已过期（事实时间：{', '.join(fact_times)}），"
                    "不能作为当前或实时值使用。"
                )
        if not reasoning_summary:
            used_tools = [item["tool_id"] for item in tool_results]
            reasoning_summary = f"意图识别为 {intent_id}；已依据工具结果完成汇总：{', '.join(used_tools)}。"
        return summary, reasoning_summary

    @staticmethod
    def _grounded_fallback_summary(tool_results: list[dict[str, Any]]) -> str:
        successful = [
            item
            for item in tool_results
            if item.get("status") in {"success", "partial"}
        ]
        if not successful:
            no_data = [
                item["tool_id"]
                for item in tool_results
                if item.get("status") == "no_data"
            ]
            failed = [
                f"{item['tool_id']}（{item.get('error_code', 'tool_execution_failed')}）"
                for item in tool_results
                if item.get("status") == "failed"
            ]
            messages = []
            no_data_messages = {
                "skill.skill_list": "当前没有已注册的可用技能；本轮已调用 skill.skill_list",
                "memory.session_search": "当前会话范围内没有匹配的历史记录；本轮已调用 memory.session_search",
                "memory.memory_search": "当前作用域内没有匹配的已激活记忆；本轮已调用 memory.memory_search",
                "search.search_sop": "当前知识库没有匹配的操作规程；本轮已调用 search.search_sop",
                "task.get_workflow_status": "当前没有匹配的任务状态；本轮已调用 task.get_workflow_status",
            }
            specific_no_data = [
                no_data_messages[tool_id]
                for tool_id in no_data
                if tool_id in no_data_messages
            ]
            messages.extend(specific_no_data)
            generic_no_data = [
                tool_id for tool_id in no_data if tool_id not in no_data_messages
            ]
            if generic_no_data:
                messages.append(
                    f"权威数据源未返回 {', '.join(generic_no_data)} 的符合条件数据，"
                    "不能据此判断设备正常"
                )
            if failed:
                messages.append(f"工具调用失败：{', '.join(failed)}")
            if not messages:
                messages.append("本轮模型未选择可执行工具")
            if generic_no_data or failed or not no_data:
                return "；".join(messages) + "，暂时无法形成可靠结论。"
            return "；".join(messages) + "。"
        facts: list[str] = []
        for item in successful:
            tool_id = item["tool_id"]
            result = item.get("result")
            data = result.get("data") if isinstance(result, dict) else result
            if tool_id == "alarm.get_active_alarms" and isinstance(data, dict):
                alarms = data.get("items")
                if isinstance(alarms, list) and alarms:
                    alarms = "；".join(
                        f"{alarm.get('device_id', '未知设备')} 的 "
                        f"{alarm.get('alarm_uuid', '未知告警')}"
                        f"（{alarm.get('severity', '未知等级')}）"
                        for alarm in alarms
                    )
                    facts.append(f"发现活动告警：{alarms}")
            elif tool_id == "asset.get_asset_status" and isinstance(data, dict):
                facts.append(
                    f"{data.get('device_id', '未知设备')} 当前状态为 "
                    f"{data.get('status', 'unknown')}"
                )
            else:
                facts.append(
                    f"{tool_id} 返回 "
                    f"{json.dumps(data, ensure_ascii=False, separators=(',', ':'))}"
                )
        return "；".join(facts) + "。"

    def _references_are_registered(self, request) -> bool:
        tools = {
            manifest.tool_id: manifest.version
            for manifest in self.container.capability_registry.list_manifests()
        }
        if any(tools.get(reference.tool_id) != reference.version for reference in request.tool_refs):
            return False
        skills = {
            (skill.skill_id, skill.version)
            for skill in self.container.skill_meta_tools.service.registry.repo.list_all()
        }
        return all((reference.skill_id, reference.version) in skills for reference in request.skill_refs)

    @staticmethod
    def _event_to_proto(run: RunRecord, event: dict[str, Any], index: int) -> runtime_pb2.RuntimeEvent:
        timestamp = Timestamp()
        timestamp.FromDatetime(datetime.now(timezone.utc))
        payload = Struct()
        ParseDict(event, payload)
        event_type = {
            "RunStart": runtime_pb2.RUNTIME_EVENT_TYPE_RUN_ACCEPTED,
            "IntentClassified": runtime_pb2.RUNTIME_EVENT_TYPE_INTENT_RESOLVED,
            "BeforeToolDiscovery": runtime_pb2.RUNTIME_EVENT_TYPE_PLAN_UPDATED,
            "model.completed": runtime_pb2.RUNTIME_EVENT_TYPE_PLAN_UPDATED,
            "BeforeToolCall": runtime_pb2.RUNTIME_EVENT_TYPE_TOOL_SELECTED,
            "ObservationCaptured": runtime_pb2.RUNTIME_EVENT_TYPE_EVIDENCE_UPDATED,
            "tool.completed": runtime_pb2.RUNTIME_EVENT_TYPE_TOOL_COMPLETED,
            "AfterToolCall": runtime_pb2.RUNTIME_EVENT_TYPE_TOOL_COMPLETED,
            "assistant.delta": runtime_pb2.RUNTIME_EVENT_TYPE_PLAN_UPDATED,
            "assistant.started": runtime_pb2.RUNTIME_EVENT_TYPE_PLAN_UPDATED,
            "assistant.completed": runtime_pb2.RUNTIME_EVENT_TYPE_PLAN_UPDATED,
            "RunStop": runtime_pb2.RUNTIME_EVENT_TYPE_RUN_COMPLETED,
            "RunFailed": runtime_pb2.RUNTIME_EVENT_TYPE_RUN_FAILED,
        }.get(
            str(event.get("event_type")),
            runtime_pb2.RUNTIME_EVENT_TYPE_UNSPECIFIED,
        )
        return runtime_pb2.RuntimeEvent(
            event_id=f"{run.run_id}:{index}",
            event_type=event_type,
            session_id=run.session_id,
            run_id=run.run_id,
            occurred_at=timestamp,
            payload=payload,
            sequence=index,
        )

    @staticmethod
    def _runtime_context_from_request(request) -> dict[str, Any]:
        attributes = dict(request.context.attributes)
        if attributes.pop("industrial_fixture_json", ""):
            raise ValueError("industrial_fixture_not_supported")
        return {
            "selected_asset_id": request.context.selected_asset_id,
            "environment": request.context.environment,
            "attributes": attributes,
            "policy": AgentRuntimeServicer._policy_to_dict(request.policy),
        }

    @staticmethod
    def _context_to_proto(snapshot: dict[str, Any]) -> runtime_pb2.ContextSnapshot:
        return runtime_pb2.ContextSnapshot(
            selected_asset_id=str(snapshot.get("selected_asset_id") or ""),
            environment=str(snapshot.get("environment") or ""),
            attributes={str(key): str(value) for key, value in snapshot.get("attributes", {}).items()},
        )

    @staticmethod
    def _tool_reference_to_dict(reference) -> dict[str, str]:
        return {"tool_id": reference.tool_id, "version": reference.version}

    @staticmethod
    def _skill_reference_to_dict(reference) -> dict[str, str]:
        return {"skill_id": reference.skill_id, "version": reference.version}

    @staticmethod
    def _policy_to_dict(policy) -> dict[str, Any]:
        return {"visible_tool_ids": list(policy.visible_tool_ids), "workflow_stage": policy.workflow_stage}

    @staticmethod
    def _approval_to_dict(approval) -> dict[str, Any]:
        return {"status": runtime_pb2.ApprovalStatus.Name(approval.status), "approval_id": approval.approval_id, "comment": approval.comment}

    @staticmethod
    def _to_proto_run_status(status: RunStatus) -> int:
        mapping = {
            RunStatus.PENDING: runtime_pb2.RUN_STATUS_ACCEPTED,
            RunStatus.RUNNING: runtime_pb2.RUN_STATUS_RUNNING,
            RunStatus.WAITING: runtime_pb2.RUN_STATUS_WAITING,
            RunStatus.COMPLETED: runtime_pb2.RUN_STATUS_COMPLETED,
            RunStatus.FAILED: runtime_pb2.RUN_STATUS_FAILED,
            RunStatus.CANCELLED: runtime_pb2.RUN_STATUS_CANCELLED,
        }
        return mapping[status]

    @staticmethod
    def _tool_to_projection(tool) -> runtime_pb2.ToolProjection:
        input_schema = Struct()
        output_schema = Struct()
        ParseDict(tool.input_schema, input_schema)
        ParseDict(tool.output_schema, output_schema)
        return runtime_pb2.ToolProjection(
            tool_id=tool.name,
            version=tool.version,
            display_name=tool.name,
            description=tool.description,
            input_schema=input_schema,
            output_schema=output_schema,
        )

    @staticmethod
    def _manifest_to_projection(manifest) -> runtime_pb2.ToolProjection:
        input_schema = Struct()
        output_schema = Struct()
        ParseDict(manifest.input_schema, input_schema)
        ParseDict(manifest.output_schema, output_schema)
        return runtime_pb2.ToolProjection(
            tool_id=manifest.tool_id,
            version=manifest.version,
            display_name=manifest.tool_id,
            description=manifest.description,
            input_schema=input_schema,
            output_schema=output_schema,
        )

    @staticmethod
    def _skill_to_projection(skill) -> runtime_pb2.SkillProjection:
        return runtime_pb2.SkillProjection(
            skill_id=skill.skill_id,
            version=skill.version,
            display_name=str(skill.manifest.get("name", skill.skill_id)),
            description=str(skill.manifest.get("description", "")),
        )
