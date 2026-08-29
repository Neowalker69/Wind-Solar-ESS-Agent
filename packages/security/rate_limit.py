import time
from dataclasses import dataclass, field


@dataclass
class InMemoryRateLimiter:
    window_seconds: int = 60
    limit: int = 20
    _hits: dict[str, list[float]] = field(default_factory=dict)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.time()
        recent = [hit for hit in self._hits.get(key, []) if now - hit < self.window_seconds]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            return False, 0
        recent.append(now)
        self._hits[key] = recent
        return True, self.limit - len(recent)
