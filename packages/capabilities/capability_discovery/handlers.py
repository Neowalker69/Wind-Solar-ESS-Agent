from typing import Any

from packages.tool_registry.registry import ToolExecutionContext, ToolNotVisibleError


def search_tool(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    query = str(payload.get("query", "")).lower()
    return [
        {"tool_id": manifest.tool_id, "description": manifest.description}
        for manifest in context.registry.visible_manifests(context)
        if query in manifest.tool_id.lower() or query in manifest.description.lower()
    ]


def tool_describe(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    manifest = context.registry.get_manifest(str(payload["tool_id"]))
    return manifest.model_dump(mode="json")


def tool_call(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any] | list[dict[str, Any]]:
    return context.registry.invoke(str(payload["tool_id"]), dict(payload.get("input", {})), context)


def list_visible_tools(_payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, str]]:
    return [
        {"tool_id": manifest.tool_id, "capability": manifest.capability}
        for manifest in context.registry.visible_manifests(context)
    ]


def explain_hidden_tool_reason(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    tool_id = str(payload["tool_id"])
    context.registry.get_manifest(tool_id)
    visible = any(manifest.tool_id == tool_id for manifest in context.registry.visible_manifests(context))
    return {"tool_id": tool_id, "visible": visible, "reason": None if visible else "not_in_current_toolset"}


def resolve_toolset_profile(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {"tool_ids": [manifest.tool_id for manifest in context.registry.visible_manifests(context)]}
