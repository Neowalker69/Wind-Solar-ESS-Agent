from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from packages.workflow.diagnosis_graph import run_diagnosis_graph


class DiagnosisState(TypedDict, total=False):
    run_id: str
    evidence_records: list[Any]
    result: dict[str, Any]


class AgentTurnState(TypedDict, total=False):
    run: Any
    request: Any
    intent_id: str
    trace_id: str
    execute: Callable[..., None]
    observe_node: Callable[[str], None]


class LangGraphRuntime:
    """Compiled LangGraph adapter for the deterministic diagnosis graph."""

    runtime = "langgraph"

    def __init__(self, executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.executor = executor or self._fallback_executor
        builder = StateGraph(DiagnosisState)
        builder.add_node("diagnose", self._diagnose)
        builder.add_edge(START, "diagnose")
        builder.add_edge("diagnose", END)
        self.graph = builder.compile()

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        completed = self.graph.invoke(state)
        return completed["result"]

    def _diagnose(self, state: DiagnosisState) -> dict[str, Any]:
        return {"result": self.executor(dict(state))}

    @staticmethod
    def _fallback_executor(state: dict[str, Any]) -> dict[str, Any]:
        return run_diagnosis_graph(state["run_id"], state.get("evidence_records", []))


class AgentMainGraph:
    """Formal Agent Runtime main graph; all capability turns pass through it."""

    runtime = "langgraph"

    def __init__(self) -> None:
        builder = StateGraph(AgentTurnState)
        builder.add_node("intake", self._intake)
        builder.add_node("agent_loop", self._agent_loop)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "intake")
        builder.add_edge("intake", "agent_loop")
        builder.add_edge("agent_loop", "finalize")
        builder.add_edge("finalize", END)
        self.graph = builder.compile()

    def invoke(
        self,
        *,
        run: Any,
        request: Any,
        intent_id: str,
        trace_id: str,
        execute: Callable[..., None],
        observe_node: Callable[[str], None],
    ) -> None:
        self.graph.invoke(
            {
                "run": run,
                "request": request,
                "intent_id": intent_id,
                "trace_id": trace_id,
                "execute": execute,
                "observe_node": observe_node,
            }
        )

    @staticmethod
    def _intake(state: AgentTurnState) -> dict[str, Any]:
        state["observe_node"]("intake")
        return {}

    @staticmethod
    def _agent_loop(state: AgentTurnState) -> dict[str, Any]:
        state["execute"](
            state["run"],
            state["request"],
            intent_id=state["intent_id"],
            trace_id=state["trace_id"],
        )
        state["observe_node"]("agent_loop")
        return {}

    @staticmethod
    def _finalize(state: AgentTurnState) -> dict[str, Any]:
        state["observe_node"]("finalize")
        return {}
