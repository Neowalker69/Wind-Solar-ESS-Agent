from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChannelEnvelope(BaseModel):
    channel: Literal["feishu"] = "feishu"
    event_id: str
    message_id: str
    chat_id: str
    thread_id: str | None = None
    sender_id: str
    tenant_id: str
    site_id: str
    session_key: str
    content_type: str = "text"
    text: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    locale: str = "zh-CN"
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str
    idempotency_key: str
    raw_event_ref: str | None = None
