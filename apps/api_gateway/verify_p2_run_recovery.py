import asyncio
import os
import time
from uuid import uuid4

from redis import Redis

from apps.api_gateway.agent_run_coordinator import (
    AgentRunCoordinator,
    CachedAgentRunStore,
    PostgresAgentRunStore,
    RedisAgentRunStore,
)
from packages.storage.postgres_connection import (
    build_postgres_connection_factory,
    ensure_repository_schema,
)


def main() -> None:
    connection_factory = build_postgres_connection_factory(os.environ["DATABASE_URL"])
    ensure_repository_schema(connection_factory)
    redis_client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    test_id = uuid4().hex
    prefix = f"agent-harness:p2-recovery:{test_id}"
    session_id = ""
    run_id = ""

    async def execute(current_run_id: str):
        return [
            (
                "message.completed",
                {"message": {"content": f"authoritative:{current_run_id}"}},
            ),
            ("run.completed", {"status": "completed"}),
        ]

    try:
        first = _coordinator(connection_factory, redis_client, prefix)
        session = first.create_session(
            site_id=f"station-p2-{test_id}",
            user_id="p2-acceptance",
        )
        session_id = session["sessionId"]
        accepted = first.start_run(
            session_id=session_id,
            user_id="p2-acceptance",
            client_message_id=f"message-{test_id}",
            execute_factory=execute,
        )
        run_id = accepted["runId"]
        for _ in range(100):
            before_loss = first.snapshot(run_id, "p2-acceptance")
            if before_loss["status"] == "completed":
                break
            time.sleep(0.01)
        assert before_loss["status"] == "completed"

        cache_keys = list(redis_client.scan_iter(match=f"{prefix}:*"))
        assert cache_keys
        redis_client.delete(*cache_keys)
        assert list(redis_client.scan_iter(match=f"{prefix}:*")) == []

        restarted = _coordinator(connection_factory, redis_client, prefix)
        recovered = restarted.snapshot(run_id, "p2-acceptance")
        retried = restarted.start_run(
            session_id=session_id,
            user_id="p2-acceptance",
            client_message_id=f"message-{test_id}",
            execute_factory=execute,
        )

        assert recovered["status"] == "completed"
        assert recovered["events"][-1]["type"] == "run.completed"
        assert recovered["lastEventId"] == str(
            recovered["events"][-1]["eventSequence"]
        )
        assert retried["runId"] == run_id
        assert list(redis_client.scan_iter(match=f"{prefix}:*"))
        print(
            "P2 live recovery accepted:",
            {
                "status": recovered["status"],
                "lastEventId": recovered["lastEventId"],
                "idempotentRun": retried["runId"] == run_id,
                "cacheRewarmed": True,
            },
        )
    finally:
        cache_keys = list(redis_client.scan_iter(match=f"{prefix}:*"))
        if cache_keys:
            redis_client.delete(*cache_keys)
        with connection_factory() as connection:
            if run_id:
                connection.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            if session_id:
                connection.execute(
                    "DELETE FROM sessions WHERE session_id = %s",
                    (session_id,),
                )


def _coordinator(connection_factory, redis_client, prefix: str) -> AgentRunCoordinator:
    return AgentRunCoordinator(
        store=CachedAgentRunStore(
            authoritative=PostgresAgentRunStore(connection_factory),
            cache=RedisAgentRunStore(redis_client, prefix=prefix),
        )
    )


if __name__ == "__main__":
    asyncio.run(asyncio.to_thread(main))
