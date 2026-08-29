from collections.abc import Callable

from fastapi import Depends, Header, Request

from apps.composition import AppContainer, get_container_dependency
from packages.security.auth import AuthContext


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def require_scope(scope: str, *, endpoint_id: str | None = None) -> Callable:
    async def dependency(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        container: AppContainer = Depends(get_container_dependency),
    ) -> AuthContext:
        auth = container.tool_guard.authenticate(authorization)
        guard_endpoint_id = endpoint_id or f"{request.method} {request.url.path}"
        if request.method in MUTATING_METHODS:
            container.tool_guard.authorize_endpoint(
                auth,
                endpoint_id=guard_endpoint_id,
                scope=scope,
            )
        else:
            # Snapshot、SSE 和历史读取只校验 Scope，不能消耗写接口限流配额。
            container.tool_guard.require_scope(auth, scope)
        return auth

    return dependency
