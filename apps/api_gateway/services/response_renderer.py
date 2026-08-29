from typing import Any


def render_text_response(*, run_id: str | None, status: str, summary: str) -> dict[str, Any]:
    return {"type": "text", "run_id": run_id, "status": status, "summary": summary}


def render_card_response(*, run_id: str | None, status: str, summary: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "card", "run_id": run_id, "status": status, "summary": summary, "fields": fields or {}}
