from datetime import datetime, timedelta, timezone

from packages.harness_common.schemas.memory import MemoryRecord, MemoryType


def mine_episodic_candidate(run_id: str, trace_id: str, evidence_ids: list[str]) -> MemoryRecord:
    return MemoryRecord(
        memory_id=f"memory_{run_id}",
        memory_type=MemoryType.EPISODIC,
        version="1",
        content={"run_id": run_id, "summary": "run completed"},
        source_trace_ids=[trace_id],
        evidence_ids=evidence_ids,
        confidence=0.75,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
