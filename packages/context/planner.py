from packages.harness_common.schemas.context import ContextKind, ContextPlan


class ContextPlanner:
    """用少量 Intent、工作流阶段和领域关键词声明最小上下文。"""

    def plan(
        self,
        intent: str,
        *,
        workflow_stage: str | None = None,
        query: str = "",
    ) -> ContextPlan:
        normalized = query.casefold()
        provider_queries = self._domain_queries(normalized)
        if intent == "sop.search":
            # SOP 查询必须由正式 Agent Tool Loop 调用 search.search_sop，
            # Context 阶段不旁路预取，确保 Observation/Evidence/Langfuse 链完整。
            return ContextPlan(required=[ContextKind.TASK_STATE])
        if intent == "diagnosis.alarm":
            provider_queries.setdefault(
                "telemetry",
                [
                    {
                        "tool_id": "telemetry.get_timeseries",
                        "metric": "temperature",
                    }
                ],
            )
            provider_queries.setdefault(
                "alarm", [{"tool_id": "alarm.get_active_alarms"}]
            )
            provider_queries.setdefault(
                "retrieval", [{"tool_id": "search.search_sop"}]
            )
            return ContextPlan(
                required=[
                    ContextKind.TASK_STATE,
                    ContextKind.WORKFLOW_STAGE,
                    ContextKind.TELEMETRY,
                    ContextKind.ALARM,
                ],
                optional=[
                    ContextKind.SCENE,
                    ContextKind.POLICY,
                    ContextKind.SKILL,
                    ContextKind.RETRIEVAL,
                    ContextKind.MEMORY,
                ],
                time_window="2h",
                provider_queries=provider_queries,
            )
        if intent == "memory.search":
            return ContextPlan(
                required=[ContextKind.TASK_STATE, ContextKind.MEMORY],
                optional=[ContextKind.POLICY],
                provider_queries={
                    "memory": [{"tool_id": "memory.memory_search"}]
                },
            )
        if intent == "sop.ingest":
            return ContextPlan(
                required=[ContextKind.TASK_STATE],
                optional=[ContextKind.RETRIEVAL, ContextKind.POLICY],
                provider_queries={
                    "retrieval": [{"tool_id": "search.search_sop"}]
                },
            )
        optional = [ContextKind.POLICY, ContextKind.MEMORY]
        stage = (workflow_stage or "").casefold()
        if provider_queries or any(
            value in stage for value in ("diagnos", "analysis", "调查", "诊断")
        ):
            optional = [
                ContextKind.WORKFLOW_STAGE,
                ContextKind.TELEMETRY,
                ContextKind.ALARM,
                ContextKind.RETRIEVAL,
                ContextKind.POLICY,
                ContextKind.MEMORY,
            ]
        return ContextPlan(
            required=[ContextKind.TASK_STATE],
            optional=optional,
            time_window="2h" if provider_queries.get("telemetry") else None,
            provider_queries=provider_queries,
        )

    @staticmethod
    def _domain_queries(query: str) -> dict[str, list[dict[str, str]]]:
        queries: dict[str, list[dict[str, str]]] = {}
        telemetry: list[dict[str, str]] = []
        if any(value in query for value in ("temperature", "温度")):
            telemetry.append(
                {"tool_id": "telemetry.get_timeseries", "metric": "temperature"}
            )
        if any(value in query for value in ("fan", "风扇", "风机", "转速")):
            telemetry.append(
                {"tool_id": "telemetry.get_timeseries", "metric": "fan_speed"}
            )
        if telemetry:
            queries["telemetry"] = telemetry
        if any(
            value in query
            for value in ("alarm history", "告警历史", "历史告警")
        ):
            queries["alarm"] = [{"tool_id": "alarm.get_alarm_history"}]
        elif any(value in query for value in ("alarm", "告警")):
            queries["alarm"] = [{"tool_id": "alarm.get_active_alarms"}]
        if any(value in query for value in ("sop", "规程", "作业指导", "处置流程")):
            queries["retrieval"] = [{"tool_id": "search.search_sop"}]
        return queries
