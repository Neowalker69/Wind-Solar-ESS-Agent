from collections.abc import Callable
from pathlib import Path
from typing import Any


ConnectionFactory = Callable[[], Any]


def normalize_postgres_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def build_postgres_connection_factory(database_url: str) -> ConnectionFactory:
    import psycopg
    from psycopg.rows import dict_row

    dsn = normalize_postgres_dsn(database_url)
    return lambda: psycopg.connect(dsn, row_factory=dict_row)


def ensure_repository_schema(connection_factory: ConnectionFactory) -> None:
    migration_dir = Path(__file__).with_name("migrations")
    with connection_factory() as connection:
        for migration_path in sorted(migration_dir.glob("*.sql")):
            migration_sql = migration_path.read_text(encoding="utf-8")
            connection.execute(migration_sql, prepare=False)
