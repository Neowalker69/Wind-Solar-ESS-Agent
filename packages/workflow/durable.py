from typing import Any, Protocol

from pydantic import BaseModel

from packages.dbos_workflows.service import DBOSWorkflowService


class DurableWorkflowRun(BaseModel):
    workflow_run_id: str
    workflow_id: str
    runtime: str
    adapter_type: str
    provider_state_ref: str
    status: str
    current_step: str | None = None
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class DurableWorkflowPort(Protocol):
    runtime: str
    adapter_type: str

    def submit(self, workflow_id: str, *, run_id: str, normalized_input: dict[str, Any], idempotency_key: str) -> DurableWorkflowRun: ...

    def get_state(self, workflow_run_id: str) -> DurableWorkflowRun | None: ...

    def cancel(self, workflow_run_id: str, reason: str) -> DurableWorkflowRun: ...


class DbosDurableWorkflowAdapter:
    runtime = "dbos"
    adapter_type = "dbos_sdk"

    def __init__(self, service: DBOSWorkflowService | None = None) -> None:
        self.service = service or DBOSWorkflowService()

    def submit(self, workflow_id: str, *, run_id: str, normalized_input: dict[str, Any], idempotency_key: str) -> DurableWorkflowRun:
        return self._from_record(
            self.service.submit(workflow_id, run_id=run_id, normalized_input=normalized_input, idempotency_key=idempotency_key)
        )

    def get_state(self, workflow_run_id: str) -> DurableWorkflowRun | None:
        record = self.service.get_state(workflow_run_id)
        return self._from_record(record) if record else None

    def cancel(self, workflow_run_id: str, reason: str) -> DurableWorkflowRun:
        return self._from_record(self.service.cancel(workflow_run_id, reason))

    def _from_record(self, record: dict[str, Any]) -> DurableWorkflowRun:
        workflow_run_id = record.get("workflow_run_id") or record["dbos_workflow_id"]
        return DurableWorkflowRun(
            workflow_run_id=workflow_run_id,
            workflow_id=record["workflow_id"],
            runtime=record.get("runtime", self.runtime),
            adapter_type=record.get("adapter_type", self.adapter_type),
            provider_state_ref=record.get("provider_state_ref", workflow_run_id),
            status=record["status"],
            current_step=record.get("current_step"),
            output=record.get("output"),
            error=record.get("error"),
        )
