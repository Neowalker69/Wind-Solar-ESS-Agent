"""复用 P0 Skill、Memory 与会话检索服务的只读 Capability。"""

from typing import Any

from packages.tool_registry.registry import ToolExecutionContext


def _service(context: ToolExecutionContext, name: str) -> Any:
    service = context.services.get(name)
    if service is None:
        raise RuntimeError(f"capability_service_unavailable:{name}")
    return service


def skill_list(_payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    service = _service(context, "skill_meta_tools")
    return [skill.model_dump(mode="json") for skill in service.service.registry.repo.list_all()]


def skill_view(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    skill = _service(context, "skill_meta_tools").skill_view(str(payload["skill_id"]), str(payload["version"]))
    return skill.model_dump(mode="json")


def search_skill(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    return _service(context, "skill_meta_tools").skill_search(str(payload.get("query") or ""))


def session_search(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    results = _service(context, "session_search").search(str(payload.get("query") or ""), session_id=payload.get("session_id"), limit=int(payload.get("limit", 10)))
    return [result.__dict__ for result in results]


def memory_get(payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any] | None:
    memory = _service(context, "memory_service").repo.get(str(payload["memory_id"]))
    return memory.model_dump(mode="json") if memory else None


def memory_search(payload: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    runtime_context = context.run.runtime_context
    attributes = dict(runtime_context.get("attributes") or {})
    return _service(context, "memory_service").search(
        str(payload.get("query") or ""),
        tenant_id=str(context.user.get("tenant_id") or attributes.get("tenant_id") or "tenant_lab"),
        site_id=context.user.get("site_id") or attributes.get("site_id"),
        user_id=context.user.get("user_id") or attributes.get("user_id"),
        asset_id=(
            str(runtime_context["selected_asset_id"])
            if runtime_context.get("selected_asset_id")
            else None
        ),
        project_id=(
            str(attributes["project_id"])
            if attributes.get("project_id")
            else None
        ),
        limit=int(payload.get("limit", 5)),
    )
