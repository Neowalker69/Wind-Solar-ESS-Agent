from collections import defaultdict
from dataclasses import dataclass, field
import logging
from typing import Any, Protocol


logger = logging.getLogger(__name__)


class EventBus(Protocol):
    def publish(self, topic: str, event: dict[str, Any]) -> None: ...

    def history(self, topic: str) -> list[dict[str, Any]]: ...


@dataclass
class InMemoryEventBus:
    events: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        self.events[topic].append(event)

    def history(self, topic: str) -> list[dict[str, Any]]:
        return list(self.events.get(topic, []))


@dataclass
class FailOpenEventBus:
    """Mirror events locally and treat the remote bus as best-effort.

    The local mirror keeps runtime execution available during a transient Redis
    outage. Redis failures are logged so operators can still detect degraded
    durability without propagating the infrastructure exception to the Agent.
    """

    primary: EventBus
    fallback: EventBus = field(default_factory=InMemoryEventBus)

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        self.fallback.publish(topic, event)
        try:
            self.primary.publish(topic, event)
        except Exception:
            logger.warning("event_bus_primary_publish_failed topic=%s", topic, exc_info=True)

    def history(self, topic: str) -> list[dict[str, Any]]:
        fallback_events = self.fallback.history(topic)
        try:
            primary_events = self.primary.history(topic)
        except Exception:
            logger.warning("event_bus_primary_history_failed topic=%s", topic, exc_info=True)
            return fallback_events
        merged = list(primary_events)
        for event in fallback_events:
            if event not in merged:
                merged.append(event)
        return merged


class RedisEventBus:
    """Redis-backed event bus adapter.

    The adapter is intentionally lazy: importing it does not connect to Redis.
    Tests can inject a fake client with `rpush` and `lrange`.
    """

    def __init__(self, redis_client: Any, *, prefix: str = "agent-harness:events") -> None:
        self.redis = redis_client
        self.prefix = prefix

    def _key(self, topic: str) -> str:
        return f"{self.prefix}:{topic}"

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        import json

        self.redis.rpush(self._key(topic), json.dumps(event, ensure_ascii=False))

    def history(self, topic: str) -> list[dict[str, Any]]:
        import json

        return [json.loads(item) for item in self.redis.lrange(self._key(topic), 0, -1)]


class RedisStreamsEventBus:
    """用于可恢复 Hook 事件的 Redis Streams 适配器。"""

    def __init__(self, redis_client: Any, *, prefix: str = "agent-harness:streams") -> None:
        self.redis = redis_client
        self.prefix = prefix

    def _key(self, topic: str) -> str:
        return f"{self.prefix}:{topic}"

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        import json

        self.redis.xadd(self._key(topic), {"event": json.dumps(event, ensure_ascii=False)})

    def history(self, topic: str) -> list[dict[str, Any]]:
        import json

        return [json.loads(fields["event"]) for _, fields in self.redis.xrange(self._key(topic), "-", "+")]
