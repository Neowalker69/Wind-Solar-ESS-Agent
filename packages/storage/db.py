from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InMemoryDatabase:
    tables: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    idempotency: dict[str, dict[str, str]] = field(default_factory=dict)

    def table(self, name: str) -> dict[str, dict[str, Any]]:
        return self.tables.setdefault(name, {})

    def keys(self, name: str) -> Iterable[str]:
        return self.table(name).keys()


DEFAULT_DB = InMemoryDatabase()
