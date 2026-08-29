from typing import Any, Protocol

from pydantic import BaseModel


class AsyncConnection(Protocol):
    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None: ...

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]: ...


class PostgresJsonStore:
    """Small asyncpg-compatible JSONB repository.

    It keeps SQL construction centralized and testable without requiring a live
    PostgreSQL server. Callers pass Pydantic models and table metadata.
    """

    def __init__(self, connection: AsyncConnection, *, table: str, id_column: str, payload_column: str = "payload") -> None:
        self.connection = connection
        self.table = table
        self.id_column = id_column
        self.payload_column = payload_column

    async def create(self, record: BaseModel, row_id: str) -> dict[str, Any] | None:
        query = (
            f"INSERT INTO {self.table} ({self.id_column}, {self.payload_column}) "
            f"VALUES ($1, $2::jsonb) "
            f"ON CONFLICT ({self.id_column}) DO UPDATE SET {self.payload_column}=EXCLUDED.{self.payload_column} "
            f"RETURNING {self.id_column}, {self.payload_column}"
        )
        return await self.connection.fetchrow(query, row_id, record.model_dump_json())

    async def get(self, row_id: str) -> dict[str, Any] | None:
        query = f"SELECT {self.id_column}, {self.payload_column} FROM {self.table} WHERE {self.id_column}=$1"
        return await self.connection.fetchrow(query, row_id)

    async def list_by_run_id(self, run_id: str) -> list[dict[str, Any]]:
        query = f"SELECT {self.id_column}, {self.payload_column} FROM {self.table} WHERE {self.payload_column}->>'run_id'=$1"
        return await self.connection.fetch(query, run_id)
