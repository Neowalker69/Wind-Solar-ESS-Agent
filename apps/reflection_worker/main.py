import os
import time

from apps.composition import AppContainer, build_container


def run_once(container: AppContainer, *, limit: int = 20) -> list[str]:
    return container.reflection_service.run_pending(limit=limit)


def main() -> None:
    container = build_container()
    poll_seconds = max(
        0.2,
        float(os.getenv("AGENT_HARNESS_REFLECTION_POLL_SECONDS", "2")),
    )
    batch_size = max(
        1,
        int(os.getenv("AGENT_HARNESS_REFLECTION_BATCH_SIZE", "20")),
    )
    while True:
        run_once(container, limit=batch_size)
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
