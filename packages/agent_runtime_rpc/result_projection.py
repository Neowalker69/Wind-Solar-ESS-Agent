import json
from typing import Any


MODEL_TOOL_RESULT_LIMIT = 6_000
RAG_COMPACT_TARGET = 5_600
RAG_HIT_TEXT_LIMIT = 900
RAG_MAX_HITS = 6


def bounded_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    serialized = _serialize(result)
    if len(serialized) <= MODEL_TOOL_RESULT_LIMIT:
        return result

    pointer = _result_pointer(result, original_characters=len(serialized))
    if result.get("tool_id") != "search.search_sop":
        return pointer

    compacted = _compact_rag_result(result, pointer)
    return compacted if compacted is not None else pointer


def _compact_rag_result(
    result: dict[str, Any],
    pointer: dict[str, Any],
) -> dict[str, Any] | None:
    tool_result = result.get("result")
    if not isinstance(tool_result, dict):
        return None
    hits = tool_result.get("data")
    if not isinstance(hits, list) or not hits:
        return None

    compacted = {
        **pointer,
        "compaction": "rag_chunks",
        "result": {
            "status": tool_result.get("status"),
            "quality": tool_result.get("quality"),
            "data": [],
            "original_hit_count": len(hits),
        },
    }
    projected_hits = compacted["result"]["data"]
    for hit in hits[:RAG_MAX_HITS]:
        if not isinstance(hit, dict):
            continue
        projected = _project_rag_hit(hit)
        projected_hits.append(projected)
        if len(_serialize(compacted)) <= RAG_COMPACT_TARGET:
            continue
        projected_hits.pop()
        break

    if not projected_hits:
        first = hits[0]
        if not isinstance(first, dict):
            return None
        projected_hits.append(_project_rag_hit(first, text_limit=240))

    compacted["result"]["returned_hit_count"] = len(projected_hits)
    while len(_serialize(compacted)) > RAG_COMPACT_TARGET and projected_hits:
        if len(projected_hits) > 1:
            projected_hits.pop()
            compacted["result"]["returned_hit_count"] = len(projected_hits)
            continue
        text = str(projected_hits[0].get("text") or "")
        if len(text) <= 120:
            return None
        projected_hits[0]["text"] = _clip(text, max(120, len(text) // 2))
    return compacted


def _project_rag_hit(hit: dict[str, Any], *, text_limit: int = RAG_HIT_TEXT_LIMIT) -> dict[str, Any]:
    projected = {
        key: hit.get(key)
        for key in (
            "rank",
            "title",
            "heading",
            "document_id",
            "chunk_id",
            "version",
            "status",
            "source_ref",
            "reranker_score",
            "relevance_score",
        )
        if hit.get(key) is not None
    }
    projected["text"] = _clip(str(hit.get("text") or ""), text_limit)
    citation = hit.get("citation")
    if isinstance(citation, dict):
        projected["citation"] = {
            key: citation.get(key)
            for key in (
                "document_id",
                "chunk_id",
                "source_ref",
                "version",
                "content_hash",
                "heading",
                "line_start",
                "line_end",
            )
            if citation.get(key) is not None
        }
    return projected


def _result_pointer(result: dict[str, Any], *, original_characters: int) -> dict[str, Any]:
    observation_id = result.get("observation_id")
    evidence_id = result.get("evidence_id")
    source_ref = (
        f"observation:{observation_id}"
        if observation_id
        else f"evidence:{evidence_id}"
        if evidence_id
        else "tool-result:unpersisted"
    )
    return {
        "tool_id": result.get("tool_id"),
        "status": result.get("status"),
        "observation_id": observation_id,
        "evidence_id": evidence_id,
        "truncated": True,
        "source_ref": source_ref,
        "original_characters": original_characters,
    }


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _serialize(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
