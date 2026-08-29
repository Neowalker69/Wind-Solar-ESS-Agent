import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from langfuse import get_client


HARNESS_API_BASE_URL = os.getenv(
    "HARNESS_API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")
VERIFY_PROMPT = os.getenv(
    "VERIFY_PROMPT",
    "列出当前可用技能，并仅基于技能注册表工具返回结果。",
)
VERIFY_EXPECTED_TOOL = os.getenv("VERIFY_EXPECTED_TOOL", "skill.skill_list")


def _request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"{HARNESS_API_BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise AssertionError(
            f"HTTP {exc.code} for {method} {path}: {response_body}"
        ) from exc


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _wait_for_runtime_run(
    run_id: str,
    token: str,
    *,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        snapshot = _request_json(
            "GET",
            f"/api/v1/agent/runs/{run_id}",
            token=token,
        )["data"]
        if snapshot["status"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.25)
    raise AssertionError(f"runtime run did not finish within {timeout_seconds}s")


def _wait_for_langfuse_trace(
    trace_id: str,
    *,
    timeout_seconds: float = 60,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    client = get_client()
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return client.api.trace.get(trace_id)
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise AssertionError(
        f"Langfuse trace {trace_id} was not queryable: {last_error}"
    )


def main() -> None:
    bootstrap = _request_json("GET", "/api/v1/agent/bootstrap")["data"]
    token = str(bootstrap.get("bearer_token") or "")
    assert token, "agent bootstrap did not issue a development bearer token"

    session = _request_json(
        "POST",
        "/api/v1/agent/sessions",
        token=token,
        payload={"site_id": "ess-station-01"},
    )["data"]
    session_id = str(session["sessionId"])
    message_id = f"verify-langfuse-{uuid4().hex}"
    accepted = _request_json(
        "POST",
        f"/api/v1/agent/sessions/{session_id}/messages",
        token=token,
        payload={
            "client_message_id": message_id,
            "user_input": VERIFY_PROMPT,
            "node_id": "ns=2;s=Runtime.SkillRegistry",
            "context": {
                "site_id": "ess-station-01",
                "site_name": "P2 权威场站",
                "time_range": "realtime",
                "selected_device": None,
            },
        },
    )["data"]
    run_id = str(accepted["runId"])
    snapshot = _wait_for_runtime_run(run_id, token)
    assert snapshot["status"] == "completed", snapshot

    run_completed = next(
        event
        for event in reversed(snapshot["events"])
        if event["type"] == "run.completed"
    )
    langfuse_export = run_completed["externalObservability"]["langfuse"]
    assert langfuse_export["status"] == "exported", langfuse_export
    assert langfuse_export["source"] == "agent_runtime", langfuse_export
    assert langfuse_export["runtime_version"] == "p2", langfuse_export
    assert langfuse_export["event_counts"]["model.completed"] >= 2
    assert langfuse_export["event_counts"]["tool.completed"] >= 1
    assert langfuse_export["event_counts"]["assistant.completed"] == 1

    langfuse_trace_id = str(langfuse_export["langfuse_trace_id"])
    trace = _wait_for_langfuse_trace(langfuse_trace_id)
    observations = list(_field(trace, "observations", []) or [])
    observation_names = [str(_field(item, "name", "")) for item in observations]
    observation_types = [str(_field(item, "type", "")) for item in observations]
    assert _field(trace, "name") == "p2-agent-runtime"
    assert {"p2", "agent-runtime", "formal-loop"}.issubset(
        set(_field(trace, "tags", []) or [])
    )
    assert any(name.startswith("model.completed:planning") for name in observation_names)
    assert VERIFY_EXPECTED_TOOL in observation_names
    assert "model.completed:summary" in observation_names
    assert "assistant.completed" in observation_names

    harness_trace_id = next(
        str(event["traceId"])
        for event in snapshot["events"]
        if event.get("traceId")
    )
    print(
        json.dumps(
            {
                "accepted": True,
                "demoLoopUsed": False,
                "requestPath": "/api/v1/agent/sessions/{session_id}/messages",
                "modelProvider": os.getenv("AGENT_HARNESS_MODEL_PROVIDER"),
                "expectedTool": VERIFY_EXPECTED_TOOL,
                "sessionId": session_id,
                "runId": run_id,
                "harnessTraceId": harness_trace_id,
                "langfuseTraceId": langfuse_trace_id,
                "langfuseTraceName": _field(trace, "name"),
                "langfuseTags": _field(trace, "tags", []),
                "eventCounts": langfuse_export["event_counts"],
                "observationNames": observation_names,
                "observationTypes": observation_types,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
