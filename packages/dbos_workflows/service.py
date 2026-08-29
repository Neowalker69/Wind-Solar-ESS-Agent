import asyncio
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
from threading import Lock
from typing import Any

from dbos import DBOS, SetWorkflowID

from packages.dbos_workflows.replay_eval import submit_replay_eval
from packages.dbos_workflows.report_generation import submit_report_generation
from packages.dbos_workflows.skill_draft import submit_skill_draft
from packages.dbos_workflows.sop_ingest import submit_sop_ingest
from packages.dbos_workflows.work_order_draft import submit_work_order_draft


class DBOSWorkflowService:
    """Durable background-workflow facade backed by the real DBOS SDK."""

    adapter_type = "dbos_sdk"

    _runtime_lock = Lock()
    _runtime_ready = False

    def __init__(self) -> None:
        self._ensure_runtime()

    def submit(self, workflow_id: str, *, run_id: str, normalized_input: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        return self._run_sync(
            self._submit,
            workflow_id,
            run_id,
            normalized_input,
            idempotency_key,
        )

    def _submit(
        self,
        workflow_id: str,
        run_id: str,
        normalized_input: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        workflow_id = workflow_id.removeprefix("dbos_")
        provider_id = self._provider_workflow_id(workflow_id, idempotency_key)
        with SetWorkflowID(provider_id):
            handle = DBOS.start_workflow(
                _execute_background_workflow,
                workflow_id,
                run_id,
                normalized_input,
                idempotency_key,
            )
        # The HTTP dispatch contract returns the initial durable state. Waiting for
        # this short pure workflow preserves that contract while DBOS remains the
        # source of truth for idempotency, result persistence, and recovery.
        handle.get_result()
        record = self._get_state(provider_id)
        if record is None:
            raise RuntimeError("dbos_workflow_state_missing")
        return record

    def get_state(self, dbos_workflow_id: str) -> dict[str, Any] | None:
        return self._run_sync(self._get_state, dbos_workflow_id)

    def _get_state(self, dbos_workflow_id: str) -> dict[str, Any] | None:
        status = DBOS.get_workflow_status(dbos_workflow_id)
        if status is None:
            return None
        args = tuple((status.input or {}).get("args") or ())
        workflow_id = str(args[0]) if args else self._workflow_name_from_id(dbos_workflow_id)
        run_id = str(args[1]) if len(args) > 1 else "unknown"
        output = status.output if isinstance(status.output, dict) else None
        normalized_status = self._normalized_status(status.status, output)
        return {
            "workflow_run_id": dbos_workflow_id,
            "dbos_workflow_id": dbos_workflow_id,
            "workflow_id": workflow_id,
            "runtime": "dbos",
            "adapter_type": self.adapter_type,
            "provider_state_ref": dbos_workflow_id,
            "run_id": run_id,
            "status": normalized_status,
            "current_step": self._current_step(normalized_status),
            "output": output,
            "error": (
                {"message": str(status.error)}
                if status.error is not None
                else None
            ),
            "provider_status": status.status,
            "recovery_attempts": status.recovery_attempts or 0,
        }

    def cancel(self, dbos_workflow_id: str, reason: str) -> dict[str, Any]:
        return self._run_sync(self._cancel, dbos_workflow_id, reason)

    def _cancel(self, dbos_workflow_id: str, reason: str) -> dict[str, Any]:
        if DBOS.get_workflow_status(dbos_workflow_id) is None:
            raise KeyError(dbos_workflow_id)
        DBOS.cancel_workflow(dbos_workflow_id, cancel_children=True)
        record = self._get_state(dbos_workflow_id)
        if record is None:
            raise RuntimeError("dbos_workflow_state_missing")
        record["error"] = {"reason": reason}
        return record

    @staticmethod
    def _run_sync(operation, *args):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return operation(*args)
        # DBOS intentionally separates sync and async SDK methods. The harness
        # durable Port is synchronous, so async HTTP/gRPC callers cross one
        # explicit worker-thread boundary instead of invoking sync SDK calls on
        # their event loop.
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(operation, *args).result()

    @classmethod
    def _ensure_runtime(cls) -> None:
        if cls._runtime_ready:
            return
        with cls._runtime_lock:
            if cls._runtime_ready:
                return
            DBOS(
                config={
                    "name": "agent-harness",
                    "system_database_url": _system_database_url(),
                    "application_version": os.getenv(
                        "DBOS_APPLICATION_VERSION",
                        "agent-harness-p2",
                    ),
                    "executor_id": os.getenv(
                        "DBOS_EXECUTOR_ID",
                        "agent-harness",
                    ),
                    "run_admin_server": False,
                    "enable_otlp": False,
                }
            )
            DBOS.launch()
            cls._runtime_ready = True

    @staticmethod
    def _provider_workflow_id(workflow_id: str, idempotency_key: str) -> str:
        digest = sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
        return f"wfr_dbos_{workflow_id}_{digest}"

    @staticmethod
    def _workflow_name_from_id(provider_id: str) -> str:
        remainder = provider_id.removeprefix("wfr_dbos_")
        return remainder.rsplit("_", 1)[0]

    @staticmethod
    def _normalized_status(
        provider_status: str,
        output: dict[str, Any] | None,
    ) -> str:
        if provider_status == "SUCCESS":
            return str((output or {}).get("outcome_status") or "completed")
        if provider_status == "CANCELLED":
            return "cancelled"
        if provider_status in {"ERROR", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"}:
            return "failed"
        return "pending"

    @staticmethod
    def _current_step(status: str) -> str:
        if status == "blocked":
            return "blocked"
        if status in {"completed", "cancelled", "failed"}:
            return "done"
        return "recovering"


@DBOS.workflow(
    name="agent_harness.background_workflow",
    max_recovery_attempts=100,
)
def _execute_background_workflow(
    workflow_id: str,
    run_id: str,
    normalized_input: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    workflow_id = workflow_id.removeprefix("dbos_")
    evidence_ids = normalized_input.get("evidence_ids", [])
    # Only the normalized allowlist is persisted in the durable workflow input.
    if workflow_id == "work_order_draft":
        return submit_work_order_draft(
            run_id,
            evidence_ids,
            idempotency_key,
            asset_id=str(normalized_input.get("asset_id") or "unknown"),
        )
    if workflow_id == "report_generation":
        return submit_report_generation(
            run_id,
            normalized_input.get("report_type", "diagnosis"),
            evidence_ids,
            idempotency_key,
        )
    if workflow_id == "sop_ingest":
        return submit_sop_ingest(
            normalized_input.get("source_uri", "memory://inline"),
            normalized_input.get("source_hash", "sha256:unknown"),
            idempotency_key,
        )
    if workflow_id == "skill_draft":
        return submit_skill_draft(
            normalized_input.get("source_trace_ids", []),
            normalized_input.get("evaluation_case_ids", []),
            idempotency_key,
        )
    if workflow_id == "replay_eval":
        return submit_replay_eval(
            run_id,
            normalized_input.get("replay_mode", "record"),
            normalized_input.get("evaluation_profile", "p0"),
            idempotency_key,
        )
    raise ValueError("unknown_dbos_workflow")


def _system_database_url() -> str:
    explicit = os.getenv("DBOS_SYSTEM_DATABASE_URL")
    if explicit:
        return _sync_database_url(explicit)
    application_url = os.getenv("DATABASE_URL")
    if application_url:
        return _sync_database_url(application_url)
    sqlite_path = Path(
        os.getenv(
            "AGENT_HARNESS_DBOS_SQLITE_PATH",
            f"/tmp/agent-harness-dbos-{os.getpid()}.sqlite",
        )
    )
    return f"sqlite:///{sqlite_path}"


def _sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace(
            "postgresql+asyncpg://",
            "postgresql+psycopg://",
            1,
        )
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url
