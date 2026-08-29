from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from time import monotonic
from typing import Callable

from packages.harness_common.schemas.context import ContextItem, ContextRequest


@dataclass
class _CacheEntry:
    expires_at: float
    items: list[ContextItem]


class ContextProviderCache:
    """仅缓存 Provider 读取结果的短 TTL 进程内副本，不承担权威持久化。"""

    def __init__(
        self,
        *,
        ttl_seconds: int = 15,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.ttl_seconds = max(1, ttl_seconds)
        self.clock = clock
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = RLock()

    def key(
        self,
        provider_name: str,
        request: ContextRequest,
        required_types: set[str],
    ) -> str:
        payload = {
            "provider": provider_name,
            "query": request.query,
            "intent": request.intent,
            "scope": request.scope.model_dump(mode="json"),
            "required_types": sorted(required_types),
        }
        return sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def get(self, key: str) -> list[ContextItem] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self.clock():
                self._entries.pop(key, None)
                return None
            return deepcopy(entry.items)

    def set(self, key: str, items: list[ContextItem]) -> None:
        with self._lock:
            self._entries[key] = _CacheEntry(
                expires_at=self.clock() + self.ttl_seconds,
                items=deepcopy(items),
            )
