from pathlib import Path
from typing import Any

from packages.tool_registry.registry import ToolExecutionContext
from packages.harness_common.schemas.tool_result import ToolResult, ToolResultQuality, ToolResultStatus


IGNORED_WORKSPACE_DIRECTORIES = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}


def _root(context: ToolExecutionContext) -> Path:
    root = context.services.get("workspace_root")
    if not isinstance(root, Path):
        raise RuntimeError("capability_service_unavailable:workspace_root")
    return root.resolve()


def _path(payload: dict[str, Any], context: ToolExecutionContext) -> Path:
    candidate = (_root(context) / str(payload["path"])).resolve()
    if _root(context) not in candidate.parents and candidate != _root(context):
        raise ValueError("path_outside_workspace")
    return candidate


def list_files(_payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, str]]:
    root = _root(context)
    return [
        {"path": str(path.relative_to(root))}
        for path in sorted(root.rglob("*"))
        if path.is_file() and not any(part in IGNORED_WORKSPACE_DIRECTORIES for part in path.relative_to(root).parts)
    ]


def search_files(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    query = str(payload.get("query") or "")
    matches: list[dict[str, Any]] = []
    for item in list_files({}, context):
        path = _path(item, context)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            if query in line:
                matches.append({"path": item["path"], "line": number, "text": line})
    return matches


def read_file(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    path = _path(payload, context)
    return {"path": str(path.relative_to(_root(context))), "content": path.read_text(encoding="utf-8")}


def search_sop(payload: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    service = context.services.get("rag_search_service")
    if service is None:
        raise RuntimeError("capability_service_unavailable:rag_search_service")
    response = service.search(
        str(payload.get("query") or ""),
        limit=int(payload.get("limit") or 8),
        include_superseded=bool(payload.get("include_superseded", False)),
    )
    hits = [
        {
            **hit.model_dump(mode="json"),
            "index_version": response.index_version,
            "embedding_model": response.embedding_model,
            "relevance_score": round(1.0 / max(1, hit.rank), 6),
        }
        for hit in response.results
    ]
    return ToolResult(
        status=ToolResultStatus.SUCCESS if hits else ToolResultStatus.NO_DATA,
        data=hits,
        quality=ToolResultQuality.GOOD if hits else ToolResultQuality.MISSING,
        source_refs=[
            {
                key: hit[key]
                for key in (
                    "source_ref",
                    "version",
                    "content_hash",
                    "document_id",
                    "chunk_id",
                )
            }
            | {
                "source_system": "authoritative_rag",
                "source_resource_type": "document_chunk",
                "index_version": response.index_version,
                "embedding_model": response.embedding_model,
            }
            for hit in hits
        ],
    )


def request_human_input(payload: dict[str, Any], _context: ToolExecutionContext) -> dict[str, Any]:
    return {"question": str(payload["question"]), "status": "pending_input"}


def send_message_draft(payload: dict[str, Any], _context: ToolExecutionContext) -> dict[str, Any]:
    return {"content": str(payload["content"]), "status": "draft"}


def todo(_payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    return list(context.run.runtime_context.get("todos", []))


def get_workflow_status(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {"workflow_id": context.run.workflow_id, "status": str(context.run.status)}
