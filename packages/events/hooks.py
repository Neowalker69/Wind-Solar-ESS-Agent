from typing import Any

from packages.events.bus import EventBus


class WorkflowHooks:
    """MVP 只保留 Agent Loop 所需的四个可观察 Hook。"""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def before_tool_discovery(self, run_id: str, payload: dict[str, Any]) -> None:
        self._publish(run_id, "BeforeToolDiscovery", payload)

    def before_tool_call(self, run_id: str, payload: dict[str, Any]) -> None:
        self._publish(run_id, "BeforeToolCall", payload)

    def after_tool_call(self, run_id: str, payload: dict[str, Any]) -> None:
        self._publish(run_id, "AfterToolCall", payload)

    def tool_call_failure(self, run_id: str, payload: dict[str, Any]) -> None:
        self._publish(run_id, "ToolCallFailure", payload)

    def _publish(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.event_bus.publish(run_id, {"event_type": event_type, **payload})
