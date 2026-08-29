import logging
from uuid import uuid4

from packages.harness_common.schemas.routing import RoutingDecision
from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.harness_common.schemas.trace import TraceEvent
from packages.events.bus import EventBus, InMemoryEventBus
from packages.observability.metrics import GLOBAL_METRICS
from packages.storage.repositories.runs import RunRepository
from packages.storage.repositories.traces import TraceRepository
from packages.wal.service import InMemoryWriteAheadLog, WriteAheadLog
from packages.workflow.durable import DbosDurableWorkflowAdapter, DurableWorkflowPort


logger = logging.getLogger(__name__)


DURABLE_TASKS = {
    "report_generation",
    "work_order_draft",
    "sop_ingest",
    "skill_draft",
    "replay_eval",
}


class RunDispatcher:
    def __init__(
        self,
        runs: RunRepository | None = None,
        traces: TraceRepository | None = None,
        durable_workflows: DurableWorkflowPort | None = None,
        event_bus: EventBus | None = None,
        state_wal: WriteAheadLog | None = None,
    ) -> None:
        self.runs = runs or RunRepository()
        self.traces = traces or TraceRepository()
        self.durable_workflows = durable_workflows or DbosDurableWorkflowAdapter()
        self.event_bus = event_bus or InMemoryEventBus()
        self.state_wal = state_wal or InMemoryWriteAheadLog()

    def dispatch(self, route: RoutingDecision) -> RunRecord:
        if route.idempotency_key:
            existing = self.runs.get_by_idempotency_key(route.idempotency_key)
            if existing is not None:
                return existing
        run_id = route.run_id or f"run_{uuid4().hex}"
        workflow_run_ids = []
        workflow_runtime = None
        workflow_adapter_type = None
        status = RunStatus.RUNNING
        if route.workflow_id in DURABLE_TASKS:
            # 持久化工作流通过 Port 层接入；Run 只记录中立的工作流运行 ID 和当前适配器标识。
            durable_run = self.durable_workflows.submit(
                route.workflow_id,
                run_id=run_id,
                normalized_input=route.normalized_input,
                idempotency_key=route.idempotency_key,
            )
            workflow_run_ids = [durable_run.workflow_run_id]
            workflow_runtime = durable_run.runtime
            workflow_adapter_type = durable_run.adapter_type
            status = RunStatus.PENDING
        run = RunRecord(
            run_id=run_id,
            session_id=route.session_id,
            task_type=route.task_type,
            status=status,
            workflow_id=route.workflow_id,
            workflow_version=route.workflow_version,
            workflow_run_ids=workflow_run_ids,
            workflow_runtime=workflow_runtime,
            workflow_adapter_type=workflow_adapter_type,
            idempotency_key=route.idempotency_key,
        )
        # 这里以幂等键为准返回既有 Run，重复投递在方法开头短路，避免重复写 trace/event/WAL。
        created = self.runs.upsert_by_idempotency_key(run)
        wal_record = self.state_wal.append(
            request_id=route.trace_id,
            scope="state_transition",
            source="run_dispatcher",
            action="run.dispatch",
            payload={"run_id": created.run_id, "status": str(created.status), "workflow_id": created.workflow_id},
        )
        GLOBAL_METRICS.inc("runs_total", (str(created.status),))
        event = {"event_type": "RunStart", "run_id": created.run_id, "workflow_id": created.workflow_id}
        self.traces.create(
            TraceEvent(
                trace_id=route.trace_id,
                run_id=created.run_id,
                session_id=created.session_id,
                event_type="RunStart",
                idempotency_key=route.idempotency_key,
                wal_record_id=wal_record.wal_record_id,
                payload={**event, "task_type": created.task_type, "workflow_run_ids": created.workflow_run_ids, "workflow_runtime": created.workflow_runtime},
            )
        )
        try:
            self.event_bus.publish(created.run_id, event)
        except Exception:
            logger.warning(
                "run_start_event_publish_failed run_id=%s trace_id=%s",
                created.run_id,
                route.trace_id,
                exc_info=True,
            )
        return created
