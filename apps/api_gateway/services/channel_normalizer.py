import os
from hashlib import sha256
from uuid import uuid4

from packages.harness_common.schemas.channel import ChannelEnvelope


def normalize_feishu_fixture(payload: dict) -> ChannelEnvelope:
    event = payload.get("event", payload)
    message = event.get("message", {})
    sender = event.get("sender", {})
    message_id = message.get("message_id", payload.get("message_id", f"msg_{uuid4().hex}"))
    event_id = payload.get("event_id", event.get("event_id", f"evt_{uuid4().hex}"))
    chat_id = message.get("chat_id", payload.get("chat_id", "chat_fixture"))
    text = message.get("text") or message.get("content") or payload.get("text", "")
    trace_id = payload.get("trace_id", f"trace_{uuid4().hex}")
    idempotency_key = sha256(f"{event_id}:{message_id}".encode("utf-8")).hexdigest()
    return ChannelEnvelope(
        event_id=event_id,
        message_id=message_id,
        chat_id=chat_id,
        thread_id=message.get("thread_id"),
        sender_id=sender.get("sender_id", {}).get("open_id", os.getenv("FIXED_ADMIN_USER_ID", "admin_p0")),
        tenant_id=os.getenv("FIXED_TENANT_ID", "tenant_lab"),
        site_id=os.getenv("FIXED_SITE_ID", "opcua_lab"),
        session_key=f"feishu:{chat_id}",
        text=text,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        raw_event_ref=event_id,
    )
