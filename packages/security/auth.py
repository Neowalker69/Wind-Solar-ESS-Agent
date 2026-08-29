import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any


STATION_ROLE_SCOPES: dict[str, frozenset[str]] = {
    "admin": frozenset({"agent:read", "agent:write", "tools:execute", "approvals:write", "traces:read"}),
    "operator": frozenset({"agent:read", "agent:write", "tools:execute", "approvals:write"}),
    "engineer": frozenset({"agent:read", "agent:write", "tools:execute", "approvals:write"}),
    "guest": frozenset({"agent:read"}),
}


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    scopes: frozenset[str]
    token_id: str | None = None
    role: str = "operator"
    tenant_id: str = "tenant_lab"


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class Hs256JwtVerifier:
    def __init__(self, secret: str | None = None) -> None:
        resolved_secret = secret or os.getenv("TOOL_GATEWAY_JWT_SECRET")
        if not resolved_secret:
            raise RuntimeError("TOOL_GATEWAY_JWT_SECRET is required")
        self.secret = resolved_secret.encode("utf-8")

    def verify_authorization(self, authorization: str | None) -> AuthContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthError(401, "auth_missing", "Bearer token is required")
        return self.verify_token(authorization.removeprefix("Bearer ").strip())

    def verify_token(self, token: str) -> AuthContext:
        try:
            header_segment, payload_segment, signature_segment = token.split(".")
            header = json.loads(_b64url_decode(header_segment))
            payload = json.loads(_b64url_decode(payload_segment))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AuthError(401, "auth_invalid", "JWT is malformed") from exc
        if header.get("alg") != "HS256":
            raise AuthError(401, "auth_invalid", "JWT alg must be HS256")
        expected = hmac.new(self.secret, f"{header_segment}.{payload_segment}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected), signature_segment):
            raise AuthError(401, "auth_invalid", "JWT signature is invalid")
        exp = payload.get("exp")
        if exp is not None and int(exp) < int(time.time()):
            raise AuthError(401, "auth_expired", "JWT is expired")
        expected_issuer = os.getenv("TOOL_GATEWAY_JWT_ISSUER")
        if expected_issuer and payload.get("iss") != expected_issuer:
            raise AuthError(401, "auth_invalid", "JWT issuer is invalid")
        if expected_issuer and payload.get("typ") != "access":
            raise AuthError(401, "auth_invalid", "JWT token type is invalid")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthError(401, "auth_invalid", "JWT subject is required")
        scopes = payload.get("scopes", payload.get("scope", []))
        if isinstance(scopes, str):
            scopes = scopes.split()
        resolved_scopes = frozenset(str(scope) for scope in scopes)
        raw_role = payload.get("role")
        role = str(raw_role or "operator")
        role_scopes = STATION_ROLE_SCOPES.get(str(raw_role or ""), frozenset())
        return AuthContext(
            user_id=str(user_id),
            scopes=resolved_scopes | role_scopes,
            token_id=payload.get("jti"),
            role=role,
            tenant_id=str(payload.get("tenant_id") or "tenant_lab"),
        )

    def issue_dev_token(
        self,
        *,
        user_id: str,
        scopes: list[str],
        expires_in_seconds: int = 3600,
        role: str | None = None,
        issuer: str | None = None,
        token_type: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": user_id, "scopes": scopes, "exp": int(time.time()) + expires_in_seconds}
        if role:
            payload["role"] = role
        if issuer:
            payload["iss"] = issuer
        if token_type:
            payload["typ"] = token_type
        if tenant_id:
            payload["tenant_id"] = tenant_id
        header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(self.secret, f"{header_segment}.{payload_segment}".encode("ascii"), hashlib.sha256).digest()
        return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"
