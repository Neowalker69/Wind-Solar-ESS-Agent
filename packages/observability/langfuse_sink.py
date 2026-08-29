import os
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable

from packages.harness_common.schemas.trace import TraceEvent


FORMAL_RUNTIME_TRACE_SOURCE = "agent_runtime"
FORMAL_RUNTIME_VERSION = "p2"


@dataclass(frozen=True)
class LangfuseTraceResult:
    enabled: bool
    status: str
    trace_id: str | None = None
    trace_url: str | None = None
    error: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "status": self.status,
            "trace_id": self.trace_id,
            "trace_url": self.trace_url,
            "error": self.error,
        }


def _observability_mode() -> str:
    return os.getenv("AGENT_HARNESS_OBSERVABILITY", "local").lower()


def _langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _usage_details(usage: dict[str, Any]) -> dict[str, int]:
    mapping = {
        "input": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "output": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total": usage.get("total_tokens"),
    }
    return {key: int(value) for key, value in mapping.items() if value is not None}


class _LangfuseSinkBase:
    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] | None = None,
        attribute_context_factory: Callable[..., Any] | None = None,
        enabled: bool | None = None,
    ) -> None:
        mode = _observability_mode()
        self.enabled = enabled if enabled is not None else mode in {"langfuse", "dual"} and _langfuse_configured()
        self.client_factory = client_factory
        self.attribute_context_factory = attribute_context_factory

    def _load_client(self) -> tuple[Any, Callable[..., Any]]:
        if self.client_factory is not None:
            return self.client_factory(), self.attribute_context_factory or (lambda **kwargs: nullcontext())
        from langfuse import get_client, propagate_attributes

        return get_client(), propagate_attributes

    def _trace_url(self, client: Any, trace_id: str) -> str:
        if hasattr(client, "get_trace_url"):
            return client.get_trace_url(trace_id=trace_id)
        host = os.getenv("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")
        template = os.getenv("LANGFUSE_TRACE_URL_TEMPLATE")
        if template:
            return template.format(host=host, trace_id=trace_id, project_id=os.getenv("LANGFUSE_PROJECT_ID", ""))
        project_id = os.getenv("LANGFUSE_PROJECT_ID")
        if project_id:
            return f"{host}/project/{project_id}/traces/{trace_id}"
        return host


class LangfuseRuntimeSink(_LangfuseSinkBase):
    """将权威 Agent Runtime 完成事件导出到同一条 Langfuse trace。"""

    _TRACE_NAME = "p2-agent-runtime"
    _RUNTIME_VERSION = FORMAL_RUNTIME_VERSION

    _SUPPORTED_EVENT_TYPES = {
        "model.completed",
        "tool.completed",
        "assistant.completed",
    }

    def record_runtime_events(
        self,
        *,
        events: list[TraceEvent],
        user_id: str | None = None,
    ) -> LangfuseTraceResult:
        runtime_events = [
            event
            for event in events
            if event.event_type in self._SUPPORTED_EVENT_TYPES
        ]
        if not runtime_events:
            return LangfuseTraceResult(
                enabled=self.enabled,
                status="no_events",
            )
        runtime_identities = {
            (event.trace_id, event.run_id, event.session_id)
            for event in runtime_events
        }
        if len(runtime_identities) != 1:
            return LangfuseTraceResult(
                enabled=self.enabled,
                status="invalid_events",
                error="runtime events must share trace, run, and session identity",
            )
        if not self.enabled:
            return LangfuseTraceResult(enabled=False, status="disabled")

        first = runtime_events[0]
        event_counts = {
            event_type: sum(
                event.event_type == event_type for event in runtime_events
            )
            for event_type in sorted(self._SUPPORTED_EVENT_TYPES)
        }
        try:
            client, propagate_attributes = self._load_client()
            langfuse_trace_id = client.create_trace_id(seed=first.trace_id)
            trace_context = {"trace_id": langfuse_trace_id}
            with propagate_attributes(
                user_id=user_id,
                session_id=first.session_id,
                trace_name=self._TRACE_NAME,
                version=self._RUNTIME_VERSION,
                tags=["p2", "agent-runtime", "formal-loop"],
                metadata={
                    "component": "agent_runtime_rpc",
                    "source": FORMAL_RUNTIME_TRACE_SOURCE,
                },
            ):
                with client.start_as_current_observation(
                    trace_context=trace_context,
                    name=self._TRACE_NAME,
                    as_type="agent",
                    input={
                        "trace_id": first.trace_id,
                        "run_id": first.run_id,
                        "session_id": first.session_id,
                    },
                    metadata={
                        "agent_harness_trace_id": first.trace_id,
                        "agent_harness_run_id": first.run_id,
                        "source": FORMAL_RUNTIME_TRACE_SOURCE,
                        "runtime_version": self._RUNTIME_VERSION,
                        "event_counts": event_counts,
                    },
                ) as root_span:
                    for event in runtime_events:
                        self._record_runtime_event(client, event)
                    assistant = next(
                        (
                            event
                            for event in reversed(runtime_events)
                            if event.event_type == "assistant.completed"
                        ),
                        None,
                    )
                    root_span.update(
                        output=assistant.payload if assistant is not None else {}
                    )
            client.flush()
            return LangfuseTraceResult(
                enabled=True,
                status="exported",
                trace_id=langfuse_trace_id,
                trace_url=self._trace_url(client, langfuse_trace_id),
            )
        except ImportError:
            return LangfuseTraceResult(
                enabled=True,
                status="sdk_missing",
                error="langfuse package is not installed",
            )
        except Exception as exc:
            return LangfuseTraceResult(
                enabled=True,
                status="export_failed",
                error=str(exc),
            )

    @staticmethod
    def _record_runtime_event(client: Any, event: TraceEvent) -> None:
        metadata = {
            "agent_harness_event_type": event.event_type,
            "agent_harness_trace_id": event.trace_id,
            "agent_harness_run_id": event.run_id,
            "input_hash": event.input_hash,
            "output_hash": event.output_hash,
            "duration_ms": event.duration_ms,
            "observation_id": event.observation_id,
            "evidence_ids": event.evidence_ids,
        }
        metadata = {
            key: value
            for key, value in metadata.items()
            if value not in (None, [], {})
        }
        if event.event_type == "model.completed":
            with client.start_as_current_observation(
                name=f"model.completed:{event.node_name or 'unknown'}",
                as_type="generation",
                model=event.model_id,
                input=event.payload.get("input")
                or {"input_hash": event.input_hash},
                usage_details=_usage_details(event.payload.get("usage") or {}) or None,
                metadata={
                    **metadata,
                    "model_version": event.model_version,
                    "stage": event.payload.get("stage"),
                    "provider": event.payload.get("provider"),
                    "context_snapshot_id": event.payload.get(
                        "context_snapshot_id"
                    ),
                    "context_utilization": event.payload.get(
                        "context_utilization"
                    ),
                    "context_compression_level": event.payload.get(
                        "context_compression_level"
                    ),
                    "context_cache_hits": event.payload.get(
                        "context_cache_hits"
                    ),
                },
            ) as generation:
                generation.update(output=event.payload.get("output"))
            return
        if event.event_type == "tool.completed":
            with client.start_as_current_observation(
                name=event.tool_name or event.node_name or "tool.completed",
                as_type="tool",
                input=event.payload.get("input") or {},
                metadata={
                    **metadata,
                    "tool_version": event.tool_version,
                    "status": event.status,
                },
            ) as tool_span:
                tool_span.update(output=event.payload.get("result"))
            return
        with client.start_as_current_observation(
            name="assistant.completed",
            as_type="span",
            input={"evidence_ids": event.evidence_ids},
            metadata={**metadata, "model_id": event.model_id},
        ) as assistant_span:
            assistant_span.update(output=event.payload)
