from typing import Any

from packages.capabilities.industrial_context import selected_asset_id
from packages.tool_registry.registry import ToolExecutionContext


def locate_asset_in_scene(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    asset_id = selected_asset_id(payload, context)
    scene_node_id = str(
        payload.get("scene_node_id")
        or context.run.runtime_context.get("selected_scene_node_id")
        or asset_id
    )
    return {"asset_id": asset_id, "scene_node_id": scene_node_id}


def highlight_asset(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    location = locate_asset_in_scene(payload, context)
    return {"command": "highlight_asset", **location}


def clear_highlight(_payload: dict[str, Any], _context: ToolExecutionContext) -> dict[str, Any]:
    return {"command": "clear_highlight"}


def focus_camera_on_asset(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    location = locate_asset_in_scene(payload, context)
    return {"command": "focus_camera_on_asset", **location}


def get_selected_scene_node(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return locate_asset_in_scene({}, context)


def get_scene_node_metadata(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raise RuntimeError("capability_service_unavailable:scene_metadata")


def scene_snapshot(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    selected = get_selected_scene_node({}, context)
    return {"selected_scene_node_id": selected["scene_node_id"], "highlighted_asset_ids": [], "source": "projection"}
