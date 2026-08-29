import json
from typing import Any

from psycopg.types.json import Jsonb

from packages.harness_common.schemas.skill import SkillRecord
from packages.storage.postgres_connection import ConnectionFactory


class PostgresSkillRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    def create(self, record: SkillRecord) -> SkillRecord:
        with self.connection_factory() as connection:
            connection.execute(
                """
                INSERT INTO skill_records (
                    skill_id, version, status, idempotency_key, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (skill_id, version) DO UPDATE SET
                    status = EXCLUDED.status,
                    idempotency_key = EXCLUDED.idempotency_key,
                    payload = EXCLUDED.payload
                """,
                (
                    record.skill_id,
                    record.version,
                    str(record.status),
                    record.idempotency_key,
                    Jsonb(record.model_dump(mode="json")),
                    record.created_at,
                ),
            )
        return record

    def get(self, row_id: str) -> SkillRecord | None:
        skill_id, version = row_id.rsplit(":", 1)
        return self.get_version(skill_id, version)

    def get_version(self, skill_id: str, version: str) -> SkillRecord | None:
        with self.connection_factory() as connection:
            row = connection.execute(
                "SELECT payload FROM skill_records WHERE skill_id = %s AND version = %s",
                (skill_id, version),
            ).fetchone()
        return self._record(row)

    def list_all(self) -> list[SkillRecord]:
        with self.connection_factory() as connection:
            rows = connection.execute(
                "SELECT payload FROM skill_records ORDER BY created_at, skill_id, version"
            ).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]

    @staticmethod
    def _record(row: dict[str, Any] | None) -> SkillRecord | None:
        if not row:
            return None
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return SkillRecord.model_validate(payload)
