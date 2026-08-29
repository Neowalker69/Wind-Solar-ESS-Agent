from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb


WalScope = Literal["rpc_delivery", "state_transition"]


class WalRecord(BaseModel):
    wal_record_id: str
    request_id: str
    scope: WalScope
    source: str
    action: str
    status: str = "pending"
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_request_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WriteAheadLog(Protocol):
    def append(
        self,
        *,
        request_id: str,
        scope: WalScope,
        source: str,
        action: str,
        payload: dict[str, Any] | None = None,
        parent_request_id: str | None = None,
    ) -> WalRecord: ...

    def list_by_request_id(self, request_id: str) -> list[WalRecord]: ...


class InMemoryWriteAheadLog:
    def __init__(self) -> None:
        self.records: dict[str, WalRecord] = {}

    def append(
        self,
        *,
        request_id: str,
        scope: WalScope,
        source: str,
        action: str,
        payload: dict[str, Any] | None = None,
        parent_request_id: str | None = None,
    ) -> WalRecord:
        record = WalRecord(
            wal_record_id=f"wal_{uuid4().hex}",
            request_id=request_id,
            scope=scope,
            source=source,
            action=action,
            payload=payload or {},
            parent_request_id=parent_request_id,
        )
        self.records[record.wal_record_id] = record
        return record

    def list_by_request_id(self, request_id: str) -> list[WalRecord]:
        return [record for record in self.records.values() if record.request_id == request_id]


class PostgresWriteAheadLog:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def append(
        self,
        *,
        request_id: str,
        scope: WalScope,
        source: str,
        action: str,
        payload: dict[str, Any] | None = None,
        parent_request_id: str | None = None,
    ) -> WalRecord:
        record = WalRecord(
            wal_record_id=f"wal_{uuid4().hex}",
            request_id=request_id,
            scope=scope,
            source=source,
            action=action,
            payload=payload or {},
            parent_request_id=parent_request_id,
        )
        query = (
            "INSERT INTO wal_records "
            "(wal_record_id, request_id, scope, source, action, status, parent_request_id, payload, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (wal_record_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload"
        )
        params = (
            record.wal_record_id,
            record.request_id,
            record.scope,
            record.source,
            record.action,
            record.status,
            record.parent_request_id,
            Jsonb(record.payload),
            record.created_at,
        )
        with self.connection_factory() as connection:
            connection.execute(query, params)
        return record

    def list_by_request_id(self, request_id: str) -> list[WalRecord]:
        query = (
            "SELECT wal_record_id, request_id, scope, source, action, status, "
            "parent_request_id, payload, created_at FROM wal_records "
            "WHERE request_id = %s ORDER BY created_at, wal_record_id"
        )
        with self.connection_factory() as connection:
            rows = connection.execute(query, (request_id,)).fetchall()
        return [WalRecord.model_validate(row) for row in rows]
