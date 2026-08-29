import os
from datetime import datetime, timezone
from uuid import uuid4

from packages.harness_common.schemas.run import RunRecord, RunStatus
from packages.harness_common.schemas.trace import TraceEvent
from packages.session_search.postgres import PostgresResourceSearch
from packages.storage.postgres_connection import (
    build_postgres_connection_factory,
    ensure_repository_schema,
)
from packages.storage.postgres_repository import (
    PostgresRunRepository,
    PostgresTraceRepository,
)


def main() -> None:
    connection_factory = build_postgres_connection_factory(os.environ["DATABASE_URL"])
    ensure_repository_schema(connection_factory)
    test_id = uuid4().hex
    session_id = f"session-search-{test_id}"
    run_id = f"run-search-{test_id}"
    trace_id = f"trace-search-{test_id}"
    occurred_at = datetime.now(timezone.utc)

    with connection_factory() as connection:
        connection.execute(
            """
            INSERT INTO sessions (session_id, tenant_id, site_id, user_id)
            VALUES (%s, 'p2-acceptance', 'station-demo', 'p2-acceptance')
            """,
            (session_id,),
        )
    try:
        PostgresRunRepository(connection_factory).create(
            RunRecord(
                run_id=run_id,
                session_id=session_id,
                task_type="diagnosis.alarm",
                status=RunStatus.COMPLETED,
                workflow_id="alarm_diagnosis_graph",
                workflow_version="p2",
                model_id="deepseek-v4-flash",
                model_version="p2",
                data_model_version="p2",
                completed_at=occurred_at,
            )
        )
        PostgresTraceRepository(connection_factory).create(
            TraceEvent(
                trace_id=trace_id,
                run_id=run_id,
                session_id=session_id,
                event_type="ToolCompleted",
                model_id="deepseek-v4-flash",
                tool_name="alarm.list",
                status="completed",
                timestamp=occurred_at,
                payload={
                    "device_id": "PCS_07",
                    "summary": "储能系统直流母线过压告警",
                },
            )
        )

        filters = {
            "query": "直流母线过压",
            "site_id": "station-demo",
            "run_id": run_id,
            "asset_id": "PCS_07",
            "model_id": "deepseek-v4-flash",
            "tool_id": "alarm.list",
            "workflow_id": "alarm_diagnosis_graph",
            "status": "completed",
            "occurred_from": occurred_at.replace(microsecond=0),
            "limit": 20,
        }
        first = PostgresResourceSearch(connection_factory).search(**filters)
        restarted = PostgresResourceSearch(connection_factory).search(**filters)

        assert len(first) == 1
        assert first[0].resource_type == "trace_event"
        assert first[0].run_id == run_id
        assert "<mark>" in first[0].snippet
        assert [hit.resource_id for hit in restarted] == [
            hit.resource_id for hit in first
        ]
        print(
            "P2 resource search accepted:",
            {
                "resourceType": first[0].resource_type,
                "runId": first[0].run_id,
                "chineseMatched": True,
                "composableFilters": 8,
                "restartConsistent": True,
            },
        )
    finally:
        with connection_factory() as connection:
            connection.execute("DELETE FROM trace_events WHERE run_id = %s", (run_id,))
            connection.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            connection.execute(
                "DELETE FROM sessions WHERE session_id = %s",
                (session_id,),
            )


if __name__ == "__main__":
    main()
