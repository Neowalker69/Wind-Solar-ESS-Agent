from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from packages.harness_common.schemas.trace import TraceEvent


@dataclass(frozen=True)
class ResourceSearchResult:
    resource_type: str
    resource_id: str
    session_id: str | None
    run_id: str | None
    snippet: str
    occurred_at: datetime
    score: float


class ResourceSearch(Protocol):
    def search(self, query: str | None = None, **filters) -> list[ResourceSearchResult]: ...


class TraceEventIndexer(Protocol):
    def index_trace_event(self, event_key: str, event: TraceEvent) -> None: ...
