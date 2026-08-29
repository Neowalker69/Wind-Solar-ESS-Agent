from typing import Any

from packages.tool_registry.registry import ToolExecutionContext


def get_current_user_context(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return dict(context.user)


def get_session_context(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {
        "run_id": context.run.run_id,
        "session_id": context.run.session_id,
        "workflow_stage": context.run.task_type,
    }


def get_selected_asset_context(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {"asset_id": context.run.runtime_context.get("selected_asset_id")}


def get_environment_context(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {"environment": context.run.runtime_context.get("environment")}


def get_policy_context(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return dict(context.run.runtime_context.get("policy", {}))


def get_active_workflow_state(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {"workflow_id": context.run.workflow_id, "status": str(context.run.status)}
