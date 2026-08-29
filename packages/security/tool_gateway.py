from typing import Any

from packages.security.auth import AuthContext, AuthError, Hs256JwtVerifier
from packages.security.rate_limit import InMemoryRateLimiter


SUSPICIOUS_TEXT_TOKENS = ("../", "..\\", ";--", "DROP TABLE", "INSERT INTO", "DELETE FROM", "UPDATE ")


class ToolGatewayGuard:
    def __init__(self, jwt_verifier: Hs256JwtVerifier, rate_limiter: InMemoryRateLimiter) -> None:
        self.jwt_verifier = jwt_verifier
        self.rate_limiter = rate_limiter

    def authenticate(self, authorization: str | None) -> AuthContext:
        return self.jwt_verifier.verify_authorization(authorization)

    def require_scope(self, auth: AuthContext, scope: str) -> None:
        if scope not in auth.scopes:
            raise AuthError(403, "scope_forbidden", f"Scope '{scope}' is required")

    def authorize_tool_call(self, auth: AuthContext, *, tool_id: str, payload: dict[str, Any]) -> None:
        self.require_scope(auth, "tools:execute")
        self._reject_unsafe_payload(payload)
        allowed, remaining = self.rate_limiter.check(f"{auth.user_id}:{tool_id}")
        if not allowed:
            raise AuthError(429, "rate_limit_exceeded", "Tool call rate limit exceeded", details={"remaining": remaining})

    def authorize_endpoint(self, auth: AuthContext, *, endpoint_id: str, scope: str) -> None:
        self.require_scope(auth, scope)
        allowed, remaining = self.rate_limiter.check(f"{auth.user_id}:{endpoint_id}")
        if not allowed:
            raise AuthError(429, "rate_limit_exceeded", "Mutating endpoint rate limit exceeded", details={"remaining": remaining})

    def _reject_unsafe_payload(self, payload: Any, path: str = "$") -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                self._reject_unsafe_payload(value, f"{path}.{key}")
            return
        if isinstance(payload, list):
            for index, value in enumerate(payload):
                self._reject_unsafe_payload(value, f"{path}[{index}]")
            return
        if isinstance(payload, str):
            upper = payload.upper()
            if any(token in payload or token in upper for token in SUSPICIOUS_TEXT_TOKENS):
                raise AuthError(400, "unsafe_tool_input", "Tool input failed safety checks", details={"field": path})
