from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JsonRpcRequest:
    id: str
    method: str
    params: dict[str, Any]


@dataclass(frozen=True)
class JsonRpcResponse:
    id: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
