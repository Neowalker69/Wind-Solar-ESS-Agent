from hashlib import sha256
from typing import Any

from packages.harness_common.schemas.trace import TraceEvent
from packages.storage.repositories.traces import TraceRepository


class ReplayService:
    def __init__(self, traces: TraceRepository | None = None) -> None:
        self.traces = traces or TraceRepository()

    def record_replay(self, run_id: str, final_answer: dict[str, Any]) -> dict[str, Any]:
        events = self.traces.list_by_run_id(run_id)
        replay_hash = sha256(str(final_answer).encode("utf-8")).hexdigest()
        self.traces.create(
            TraceEvent(
                trace_id=f"trace_replay_{run_id}",
                run_id=run_id,
                event_type="ReplayCompleted",
                payload={"mode": "record", "event_count": len(events), "output_hash": replay_hash},
            )
        )
        return {
            "run_id": run_id,
            "mode": "record",
            "event_count": len(events),
            "output_hash": replay_hash,
            "final_answer": final_answer,
            "diverged": False,
        }
