from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from packages.storage.db import DEFAULT_DB, InMemoryDatabase

T = TypeVar("T", bound=BaseModel)


class InMemoryRepository(Generic[T]):
    table_name: str
    id_field: str
    model_type: type[T]

    def __init__(self, db: InMemoryDatabase | None = None) -> None:
        self.db = db or DEFAULT_DB

    def create(self, record: T) -> T:
        row_id = str(getattr(record, self.id_field))
        self.db.table(self.table_name)[row_id] = record.model_dump(mode="json")
        return record

    def get(self, row_id: str) -> T | None:
        data = self.db.table(self.table_name).get(row_id)
        return self.model_type.model_validate(data) if data else None

    def list_by_run_id(self, run_id: str) -> list[T]:
        return [
            self.model_type.model_validate(row)
            for row in self.db.table(self.table_name).values()
            if row.get("run_id") == run_id
        ]

    def list_all(self) -> list[T]:
        return [self.model_type.model_validate(row) for row in self.db.table(self.table_name).values()]

    def upsert_by_idempotency_key(self, record: T, idempotency_key: str | None = None) -> T:
        key = idempotency_key or getattr(record, "idempotency_key", None)
        if not key:
            return self.create(record)
        index = self.db.idempotency.setdefault(self.table_name, {})
        if key in index:
            existing = self.get(index[key])
            if existing is None:
                raise RuntimeError("idempotency index points to missing row")
            return existing
        created = self.create(record)
        index[key] = str(getattr(record, self.id_field))
        return created

    def get_by_idempotency_key(self, idempotency_key: str) -> T | None:
        row_id = self.db.idempotency.get(self.table_name, {}).get(idempotency_key)
        if row_id:
            return self.get(row_id)
        matches = self.find_by(idempotency_key=idempotency_key)
        return matches[0] if matches else None

    def delete(self, row_id: str) -> bool:
        table = self.db.table(self.table_name)
        if row_id not in table:
            return False
        del table[row_id]
        index = self.db.idempotency.get(self.table_name, {})
        stale_keys = [key for key, indexed_row_id in index.items() if indexed_row_id == row_id]
        for key in stale_keys:
            del index[key]
        return True

    def find_by(self, **filters: Any) -> list[T]:
        rows = []
        for row in self.db.table(self.table_name).values():
            if all(row.get(name) == value for name, value in filters.items()):
                rows.append(self.model_type.model_validate(row))
        return rows
