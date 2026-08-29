from packages.harness_common.schemas.intent import IntentDecision


class IntentCache:
    def __init__(self) -> None:
        self._cache: dict[str, IntentDecision] = {}

    def get(self, key: str) -> IntentDecision | None:
        return self._cache.get(key)

    def set(self, key: str, decision: IntentDecision) -> None:
        self._cache[key] = decision
