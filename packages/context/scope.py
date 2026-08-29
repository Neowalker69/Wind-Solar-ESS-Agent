from typing import Any

from packages.harness_common.schemas.context import ContextScope


class ContextScopeResolver:
    """只从已验证身份和服务端 Session 派生本轮作用域。"""

    def resolve(
        self,
        *,
        trusted_identity: dict[str, str],
        session: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> ContextScope:
        user_id = str(trusted_identity["user_id"])
        if str(session.get("userId") or "") != user_id:
            raise PermissionError("context_session_user_mismatch")
        policy = dict(runtime_context.get("policy") or {})
        return ContextScope(
            tenant_id=str(trusted_identity.get("tenant_id") or "tenant_lab"),
            site_id=str(session["siteId"]),
            user_id=user_id,
            role=str(trusted_identity.get("role") or "operator"),
            asset_id=(
                str(runtime_context["selected_asset_id"])
                if runtime_context.get("selected_asset_id")
                else None
            ),
            scene_node_id=(
                str(runtime_context["selected_scene_node_id"])
                if runtime_context.get("selected_scene_node_id")
                else None
            ),
            workflow_id=(
                str(runtime_context["workflow_id"])
                if runtime_context.get("workflow_id")
                else None
            ),
            workflow_stage=(
                str(policy.get("workflow_stage"))
                if policy.get("workflow_stage")
                else None
            ),
            risk_ceiling=str(policy.get("risk_ceiling") or "L1"),
        )
