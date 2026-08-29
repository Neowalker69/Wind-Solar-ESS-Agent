import hashlib
import hmac
import os
import time

from fastapi import Request

from packages.security.auth import AuthError


FEISHU_SIGNATURE_WINDOW_SECONDS = 300


def fixtures_enabled() -> bool:
    return os.getenv("AGENT_HARNESS_PROFILE", "dev") in {"dev", "test", "local"}


async def verify_feishu_webhook(request: Request) -> None:
    secret = os.getenv("FEISHU_WEBHOOK_SECRET")
    if not secret:
        raise AuthError(503, "feishu_secret_missing", "Feishu webhook secret is required")
    token = os.getenv("FEISHU_EVENT_TOKEN")
    if token and request.headers.get("X-Feishu-Event-Token") != token:
        raise AuthError(401, "feishu_token_invalid", "Feishu event token is invalid")
    timestamp = request.headers.get("X-Feishu-Timestamp")
    signature = request.headers.get("X-Feishu-Signature")
    if not timestamp or not signature:
        raise AuthError(401, "feishu_signature_missing", "Feishu signature headers are required")
    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise AuthError(401, "feishu_timestamp_invalid", "Feishu timestamp is invalid") from exc
    if abs(int(time.time()) - timestamp_int) > FEISHU_SIGNATURE_WINDOW_SECONDS:
        raise AuthError(401, "feishu_signature_expired", "Feishu signature is expired")
    body = await request.body()
    message = timestamp.encode("utf-8") + b"." + body
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AuthError(401, "feishu_signature_invalid", "Feishu signature is invalid")
