from uuid import uuid4

from packages.harness_common.schemas.trace import TraceEvent
from packages.session_search.base import TraceEventIndexer
from packages.storage.repositories.base import InMemoryRepository


class TraceRepository(InMemoryRepository[TraceEvent]):
    table_name = "trace_events"
    id_field = "_event_row_id"
    model_type = TraceEvent

    def __init__(self, db=None, session_search: TraceEventIndexer | None = None) -> None:
        super().__init__(db)
        self.session_search = session_search

    def create(self, record: TraceEvent) -> TraceEvent:
        row_id = str(uuid4())
        row = record.model_dump(mode="json")
        row["_event_row_id"] = row_id
        self.db.table(self.table_name)[row_id] = row
        if self.session_search is not None:
            self.session_search.index_trace_event(row_id, record)
        return record

    def get_context_snapshot(self, snapshot_id: str) -> TraceEvent | None:
        return next(
            (
                event
                for event in reversed(self.list_all())
                if event.event_type == "context.compiled"
                and event.payload.get("snapshot_id") == snapshot_id
            ),
            None,
        )
