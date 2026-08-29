from dataclasses import dataclass
from typing import Any, Callable, Protocol

from packages.harness_common.schemas.plugin import ToolDefinition
from apps.tool_gateway.services.tool_policy import assert_tool_allowed
from packages.observations.service import ObservationService
from packages.observability.metrics import GLOBAL_METRICS
from packages.storage.repositories.evidence import EvidenceRepository


class ToolNotRegisteredError(KeyError):
    pass


class ToolInputError(ValueError):
    pass


class ToolUpstreamError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolExecutionContext:
    task_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    model_name: str | None = None


class ContextualToolHandler(Protocol):
    def execute_tool(self, payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]: ...


class ToolDispatcher:
    def __init__(self, evidence_repo: EvidenceRepository | None = None, observation_service: ObservationService | None = None) -> None:
        self._tools: dict[str, tuple[ToolDefinition, Callable[[dict[str, Any]], dict[str, Any]] | ContextualToolHandler]] = {}
        self.evidence_repo = evidence_repo or EvidenceRepository()
        self.observation_service = observation_service or ObservationService(self.evidence_repo)

    def register(self, tool: ToolDefinition, handler: Callable[[dict[str, Any]], dict[str, Any]] | ContextualToolHandler) -> None:
        assert_tool_allowed(tool)
        self._tools[tool.name] = (tool, handler)

    def execute(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if name not in self._tools:
            raise ToolNotRegisteredError("tool_not_registered")
        tool, handler = self._tools[name]
        # 执行前再次校验策略，覆盖插件热更新后保留旧 handler 但 tool 元数据被替换的集成风险。
        assert_tool_allowed(tool)
        GLOBAL_METRICS.inc("tool_calls_total", (tool.name, tool.plugin_version))
        try:
            context = ToolExecutionContext(
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                model_name=model_name,
            )
            contextual_execute = getattr(handler, "execute_tool", None)
            raw_observation = contextual_execute(payload, context) if contextual_execute else handler(payload)
        except KeyError as exc:
            raise ToolInputError(f"missing_tool_input:{exc.args[0]}") from exc
        except ValueError as exc:
            raise ToolInputError(str(exc)) from exc
        observation = self.observation_service.capture_tool_observation(
            tool=tool,
            raw_observation=raw_observation,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            model_name=model_name,
            source_ref=str(payload.get("node_id", tool.name)),
        )
        result = {
            "tool": tool.name,
            "plugin_version": tool.plugin_version,
            "observation_id": observation.observation_id,
            "observation": observation.extract_payload,
            "raw_snapshot_ref": observation.raw_snapshot_ref,
            "redacted_fields": observation.redacted_fields,
        }
        if observation.evidence_id:
            result["evidence_id"] = observation.evidence_id
        return result
