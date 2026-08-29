from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from packages.context.compiler import ContextCompiler
from packages.context.cache import ContextProviderCache
from packages.context.planner import ContextPlanner
from packages.harness_common.schemas.context import (
    ContextBundle,
    ContextItem,
    ContextPlan,
    ContextProviderFailure,
    ContextRequest,
    ContextScope,
)


class ContextProvider(Protocol):
    name: str

    def fetch(
        self,
        request: ContextRequest,
        scope: ContextScope,
        required_types: set[str],
    ) -> list[ContextItem]: ...


class ContextLifecycleState(TypedDict, total=False):
    request: ContextRequest
    scope: ContextScope
    plan: ContextPlan
    items: list[ContextItem]
    provider_failures: list[ContextProviderFailure]
    cache_hits: list[str]
    bundle: ContextBundle


class ContextLifecycle:
    """使用 LangGraph 编排 Context 的规划、收集和编译生命周期。"""

    def __init__(
        self,
        *,
        planner: ContextPlanner | None = None,
        providers: list[ContextProvider] | None = None,
        compiler: ContextCompiler | None = None,
        provider_cache: ContextProviderCache | None = None,
    ) -> None:
        self.planner = planner or ContextPlanner()
        self.providers = providers or []
        self.compiler = compiler or ContextCompiler()
        self.provider_cache = provider_cache
        graph = StateGraph(ContextLifecycleState)
        graph.add_node("resolve_scope", self._resolve_scope)
        graph.add_node("plan", self._plan)
        graph.add_node("gather", self._gather)
        graph.add_node("compile", self._compile)
        graph.add_edge(START, "resolve_scope")
        graph.add_edge("resolve_scope", "plan")
        graph.add_edge("plan", "gather")
        graph.add_edge("gather", "compile")
        graph.add_edge("compile", END)
        self.graph = graph.compile()

    def compile(self, request: ContextRequest) -> ContextBundle:
        result = self.graph.invoke({"request": request})
        return result["bundle"]

    @staticmethod
    def _resolve_scope(state: ContextLifecycleState) -> dict[str, Any]:
        return {"scope": state["request"].scope}

    def _plan(self, state: ContextLifecycleState) -> dict[str, Any]:
        request = state["request"]
        return {
            "plan": self.planner.plan(
                request.intent,
                workflow_stage=request.scope.workflow_stage,
                query=request.query,
            )
        }

    def _gather(self, state: ContextLifecycleState) -> dict[str, Any]:
        plan = state["plan"]
        required_types = {
            str(kind) for kind in (*plan.required, *plan.optional)
        }
        items: list[ContextItem] = []
        failures: list[ContextProviderFailure] = []
        provider_request = state["request"].model_copy(
            update={
                "runtime_context": {
                    **state["request"].runtime_context,
                    "context_plan": plan.model_dump(mode="json"),
                }
            }
        )
        def fetch(provider):
            cache_key = None
            if self.provider_cache is not None:
                cache_key = self.provider_cache.key(
                    provider.name,
                    provider_request,
                    required_types,
                )
                cached = self.provider_cache.get(cache_key)
                if cached is not None:
                    return provider, cached, None, True
            try:
                fetched = provider.fetch(
                    provider_request,
                    state["scope"],
                    required_types,
                )
                if self.provider_cache is not None and cache_key is not None:
                    self.provider_cache.set(cache_key, fetched)
                return provider, fetched, None, False
            except Exception as exc:
                return provider, [], exc, False

        max_workers = max(1, min(len(self.providers), 8))
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="context-provider",
        ) as executor:
            results = list(executor.map(fetch, self.providers))
        cache_hits: list[str] = []
        for provider, fetched, error, cache_hit in results:
            items.extend(fetched)
            if cache_hit:
                cache_hits.append(provider.name)
            if error is not None:
                failures.append(
                    ContextProviderFailure(
                        provider=provider.name,
                        code="provider_unavailable",
                        message=str(error)[:160],
                        required_types=plan.required,
                    )
                )
        return {
            "items": items,
            "provider_failures": failures,
            "cache_hits": sorted(cache_hits),
        }

    def _compile(self, state: ContextLifecycleState) -> dict[str, Any]:
        bundle = self.compiler.compile(
            request=state["request"],
            plan=state["plan"],
            items=state.get("items", []),
            provider_failures=state.get("provider_failures", []),
            cache_hits=state.get("cache_hits", []),
            lifecycle_runtime="langgraph",
        )
        return {"bundle": bundle}
