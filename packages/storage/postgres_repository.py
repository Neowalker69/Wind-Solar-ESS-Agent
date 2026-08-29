import json
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from packages.harness_common.schemas.evidence import EvidenceRecord
from packages.harness_common.schemas.observation import ObservationRecord
from packages.harness_common.schemas.plugin import PluginInstallation
from packages.harness_common.schemas.run import RunRecord
from packages.harness_common.schemas.trace import TraceEvent
from packages.storage.postgres_connection import ConnectionFactory


T = TypeVar("T", bound=BaseModel)


class PostgresRepository(Generic[T]):
    table_name: str
    id_field: str
    id_columns: tuple[str, ...]
    model_type: type[T]
    run_id_column: str | None = None
    idempotency_column: str | None = None
    order_column: str = "created_at"

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    def create(self, record: T) -> T:
        row_id = self._row_id(record)
        values = self._persistence_values(record, row_id)
        columns = tuple(values)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_target = ", ".join(self.id_columns)
        update_columns = [column for column in columns if column not in self.id_columns]
        updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
        query = (
            f"INSERT INTO {self.table_name} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) ON CONFLICT ({conflict_target}) DO UPDATE SET {updates}"
        )
        with self.connection_factory() as connection:
            connection.execute(query, tuple(values.values()))
        self._after_create(row_id, record)
        return record

    def get(self, row_id: str) -> T | None:
        filters = self._identity_from_row_id(row_id)
        where = " AND ".join(f"{column} = %s" for column in filters)
        query = f"SELECT record FROM {self.table_name} WHERE {where}"
        with self.connection_factory() as connection:
            row = connection.execute(query, tuple(filters.values())).fetchone()
        return self._model_from_row(row)

    def list_by_run_id(self, run_id: str) -> list[T]:
        if self.run_id_column:
            query = f"SELECT record FROM {self.table_name} WHERE {self.run_id_column} = %s ORDER BY {self.order_column}"
            params = (run_id,)
        else:
            query = f"SELECT record FROM {self.table_name} WHERE record->>'run_id' = %s"
            params = (run_id,)
        with self.connection_factory() as connection:
            rows = connection.execute(query, params).fetchall()
        return [model for row in rows if (model := self._model_from_row(row)) is not None]

    def list_all(self) -> list[T]:
        query = f"SELECT record FROM {self.table_name} ORDER BY {self.order_column}"
        with self.connection_factory() as connection:
            rows = connection.execute(query).fetchall()
        return [model for row in rows if (model := self._model_from_row(row)) is not None]

    def upsert_by_idempotency_key(self, record: T, idempotency_key: str | None = None) -> T:
        key = idempotency_key or getattr(record, "idempotency_key", None)
        if not key:
            return self.create(record)
        existing = self.get_by_idempotency_key(key)
        if existing is not None:
            return existing
        try:
            return self.create(record)
        except UniqueViolation:
            existing = self.get_by_idempotency_key(key)
            if existing is None:
                raise
            return existing

    def get_by_idempotency_key(self, idempotency_key: str) -> T | None:
        if self.idempotency_column:
            query = f"SELECT record FROM {self.table_name} WHERE {self.idempotency_column} = %s"
        else:
            query = f"SELECT record FROM {self.table_name} WHERE record->>'idempotency_key' = %s"
        with self.connection_factory() as connection:
            row = connection.execute(query, (idempotency_key,)).fetchone()
        return self._model_from_row(row)

    def delete(self, row_id: str) -> bool:
        filters = self._identity_from_row_id(row_id)
        where = " AND ".join(f"{column} = %s" for column in filters)
        query = f"DELETE FROM {self.table_name} WHERE {where} RETURNING 1"
        with self.connection_factory() as connection:
            row = connection.execute(query, tuple(filters.values())).fetchone()
        return row is not None

    def find_by(self, **filters: Any) -> list[T]:
        query = f"SELECT record FROM {self.table_name} WHERE record @> %s"
        with self.connection_factory() as connection:
            rows = connection.execute(query, (Jsonb(filters),)).fetchall()
        return [model for row in rows if (model := self._model_from_row(row)) is not None]

    def _row_id(self, record: T) -> str:
        return str(getattr(record, self.id_field))

    def _identity_from_row_id(self, row_id: str) -> dict[str, str]:
        return {self.id_columns[0]: row_id}

    def _persistence_values(self, record: T, row_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def _after_create(self, row_id: str, record: T) -> None:
        return None

    def _model_from_row(self, row: dict[str, Any] | None) -> T | None:
        if not row:
            return None
        value = row["record"]
        if isinstance(value, str):
            value = json.loads(value)
        return self.model_type.model_validate(value)


class PostgresRunRepository(PostgresRepository[RunRecord]):
    table_name = "runs"
    id_field = "run_id"
    id_columns = ("run_id",)
    model_type = RunRecord
    run_id_column = "run_id"
    idempotency_column = "idempotency_key"

    def _persistence_values(self, record: RunRecord, row_id: str) -> dict[str, Any]:
        return {
            "run_id": row_id,
            "session_id": record.session_id,
            "parent_run_id": record.parent_run_id,
            "task_type": record.task_type,
            "status": str(record.status),
            "workflow_id": record.workflow_id,
            "workflow_version": record.workflow_version,
            "graph_runtime": record.graph_runtime,
            "graph_checkpoint_ref": record.graph_checkpoint_ref,
            "workflow_run_ids": Jsonb(record.workflow_run_ids),
            "workflow_runtime": record.workflow_runtime,
            "workflow_adapter_type": record.workflow_adapter_type,
            "model_id": record.model_id,
            "model_version": record.model_version,
            "plugin_version_snapshot": Jsonb(record.plugin_version_snapshot),
            "skill_version_snapshot": Jsonb(record.skill_version_snapshot),
            "data_model_version": record.data_model_version,
            "idempotency_key": record.idempotency_key,
            "created_at": record.created_at,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "error": Jsonb(record.error) if record.error is not None else None,
            "record": Jsonb(record.model_dump(mode="json")),
        }


class PostgresTraceRepository(PostgresRepository[TraceEvent]):
    table_name = "trace_events"
    id_field = "_event_row_id"
    id_columns = ("record_id",)
    model_type = TraceEvent
    run_id_column = "run_id"
    order_column = "timestamp"

    def _row_id(self, record: TraceEvent) -> str:
        return str(uuid4())

    def get_context_snapshot(self, snapshot_id: str) -> TraceEvent | None:
        query = (
            "SELECT record FROM trace_events "
            "WHERE event_type = 'context.compiled' "
            "AND payload->>'snapshot_id' = %s ORDER BY timestamp DESC LIMIT 1"
        )
        with self.connection_factory() as connection:
            row = connection.execute(query, (snapshot_id,)).fetchone()
        return self._model_from_row(row)

    def _persistence_values(self, record: TraceEvent, row_id: str) -> dict[str, Any]:
        return {
            "record_id": row_id,
            "trace_id": record.trace_id,
            "run_id": record.run_id,
            "session_id": record.session_id,
            "event_type": record.event_type,
            "idempotency_key": record.idempotency_key,
            "wal_record_id": record.wal_record_id,
            "observation_id": record.observation_id,
            "payload": Jsonb(record.payload),
            "timestamp": record.timestamp,
            "record": Jsonb(record.model_dump(mode="json")),
        }


class PostgresEvidenceRepository(PostgresRepository[EvidenceRecord]):
    table_name = "evidence_records"
    id_field = "evidence_id"
    id_columns = ("evidence_id",)
    model_type = EvidenceRecord
    run_id_column = "run_id"
    order_column = "recorded_at"

    def _persistence_values(self, record: EvidenceRecord, row_id: str) -> dict[str, Any]:
        return {
            "evidence_id": row_id,
            "run_id": record.run_id,
            "trace_id": record.trace_id,
            "source_type": record.source_type,
            "quality": str(record.quality),
            "payload": Jsonb(record.data),
            "recorded_at": record.recorded_at,
            "record": Jsonb(record.model_dump(mode="json")),
        }


class PostgresObservationRepository(PostgresRepository[ObservationRecord]):
    table_name = "observation_records"
    id_field = "observation_id"
    id_columns = ("observation_id",)
    model_type = ObservationRecord
    run_id_column = "run_id"
    order_column = "observed_at"

    def _persistence_values(
        self,
        record: ObservationRecord,
        row_id: str,
    ) -> dict[str, Any]:
        return {
            "observation_id": row_id,
            "run_id": record.run_id,
            "trace_id": record.trace_id,
            "task_id": record.task_id,
            "model_name": record.model_name,
            "tool_name": record.tool_name,
            "plugin_id": record.plugin_id,
            "plugin_version": record.plugin_version,
            "raw_snapshot_ref": record.raw_snapshot_ref,
            "payload": Jsonb(record.extract_payload),
            "observed_at": record.observed_at,
            "record": Jsonb(record.model_dump(mode="json")),
        }


class PostgresPluginRepository(PostgresRepository[PluginInstallation]):
    table_name = "plugin_installations"
    id_field = "compound_id"
    id_columns = ("plugin_id", "version")
    model_type = PluginInstallation
    idempotency_column = "idempotency_key"
    order_column = "installed_at"

    def _row_id(self, record: PluginInstallation) -> str:
        return f"{record.plugin_id}:{record.version}"

    def _identity_from_row_id(self, row_id: str) -> dict[str, str]:
        plugin_id, version = row_id.rsplit(":", 1)
        return {"plugin_id": plugin_id, "version": version}

    def _persistence_values(self, record: PluginInstallation, row_id: str) -> dict[str, Any]:
        return {
            "plugin_id": record.plugin_id,
            "version": record.version,
            "runtime_status": str(record.runtime_status),
            "idempotency_key": record.idempotency_key,
            "payload": Jsonb(record.model_dump(mode="json")),
            "installed_at": record.installed_at,
            "record": Jsonb(record.model_dump(mode="json")),
        }

    def get_version(self, plugin_id: str, version: str) -> PluginInstallation | None:
        return self.get(f"{plugin_id}:{version}")
