import json
from datetime import datetime
from threading import RLock

from packages.harness_common.schemas.trace import TraceEvent
from packages.session_search.base import ResourceSearchResult


class InMemoryResourceSearch:
    """仅供无 PostgreSQL 的本地测试配置使用。"""

    def __init__(self) -> None:
        self._events: dict[str, TraceEvent] = {}
        self._lock = RLock()

    def index_trace_event(self, event_key: str, event: TraceEvent) -> None:
        if not event.session_id:
            return
        with self._lock:
            self._events[event_key] = event.model_copy(deep=True)

    def search(
        self,
        query: str | None = None,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        model_id: str | None = None,
        tool_id: str | None = None,
        status: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        limit: int = 10,
        **_filters,
    ) -> list[ResourceSearchResult]:
        if not any(
            (
                query,
                session_id,
                run_id,
                model_id,
                tool_id,
                status,
                occurred_from,
                occurred_to,
            )
        ):
            return []
        query_text = (query or "").casefold()
        matches: list[ResourceSearchResult] = []
        with self._lock:
            events = list(self._events.items())
        for event_key, event in events:
            content = self._event_content(event)
            if query_text and query_text not in content.casefold():
                continue
            if session_id and event.session_id != session_id:
                continue
            if run_id and event.run_id != run_id:
                continue
            if model_id and event.model_id != model_id:
                continue
            if tool_id and event.tool_name != tool_id:
                continue
            if status and event.status != status:
                continue
            if occurred_from and event.timestamp < occurred_from:
                continue
            if occurred_to and event.timestamp > occurred_to:
                continue
            matches.append(
                ResourceSearchResult(
                    resource_type="trace_event",
                    resource_id=event_key,
                    session_id=event.session_id,
                    run_id=event.run_id,
                    snippet=content[:320],
                    occurred_at=event.timestamp,
                    score=1.0 if query_text else 0.0,
                )
            )
        matches.sort(key=lambda hit: hit.occurred_at, reverse=True)
        return matches[: max(1, min(limit, 50))]

    @staticmethod
    def _event_content(event: TraceEvent) -> str:
        fields = [
            event.event_type,
            event.node_name,
            event.model_id,
            event.tool_name,
            event.plugin_id,
            event.skill_id,
            json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
        ]
        return " ".join(str(field) for field in fields if field)
