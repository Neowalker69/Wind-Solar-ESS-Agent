from packages.harness_common.schemas.memory import MemoryRecord, MemoryStatus, MemoryType


def validate_provenance(memory: MemoryRecord) -> MemoryRecord:
    if memory.memory_type in {MemoryType.SEMANTIC, MemoryType.PROCEDURAL}:
        # 可复用知识和流程会影响后续决策，必须同时绑定 trace 和 evidence，防止无来源记忆被激活。
        if not memory.source_trace_ids or not memory.evidence_ids:
            raise ValueError("memory_provenance_required")
    return memory


def mark_conflict(memory: MemoryRecord) -> MemoryRecord:
    return memory.model_copy(update={"status": MemoryStatus.CONFLICTED})
