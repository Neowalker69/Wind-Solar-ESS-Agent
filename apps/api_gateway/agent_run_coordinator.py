import asyncio
import json
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Awaitable, Callable, Protocol
from uuid import uuid4

from psycopg.types.json import Jsonb


TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})


class AgentRunStore(Protocol):
    def save_session(self, session: dict) -> None: ...

    def get_session(self, session_id: str) -> dict | None: ...

    def save_run(self, run: dict) -> None: ...

    def get_run(self, run_id: str) -> dict | None: ...

    def save_client_run(self, session_id: str, client_message_id: str, run_id: str) -> None: ...

    def get_client_run(self, session_id: str, client_message_id: str) -> str | None: ...


class InMemoryAgentRunStore:
    def __init__(self, *, max_sessions: int = 500, max_runs: int = 500) -> None:
        self.max_sessions = max_sessions
        self.max_runs = max_runs
        self.sessions: OrderedDict[str, dict] = OrderedDict()
        self.runs: OrderedDict[str, dict] = OrderedDict()
        self.client_runs: dict[str, str] = {}

    def save_session(self, session: dict) -> None:
        self.sessions[session["sessionId"]] = deepcopy(session)
        self._trim(self.sessions, self.max_sessions)

    def get_session(self, session_id: str) -> dict | None:
        session = self.sessions.get(session_id)
        return deepcopy(session) if session else None

    def save_run(self, run: dict) -> None:
        self.runs[run["runId"]] = deepcopy(run)
        self._trim(self.runs, self.max_runs)

    def get_run(self, run_id: str) -> dict | None:
        run = self.runs.get(run_id)
        return deepcopy(run) if run else None

    def save_client_run(self, session_id: str, client_message_id: str, run_id: str) -> None:
        self.client_runs[f"{session_id}:{client_message_id}"] = run_id

    def get_client_run(self, session_id: str, client_message_id: str) -> str | None:
        return self.client_runs.get(f"{session_id}:{client_message_id}")

    @staticmethod
    def _trim(collection: OrderedDict, limit: int) -> None:
        while len(collection) > limit:
            collection.popitem(last=False)


class RedisAgentRunStore:
    def __init__(
        self,
        redis_client: Any,
        *,
        prefix: str = "agent-harness:canonical",
        session_ttl_seconds: int = 86_400,
        run_ttl_seconds: int = 604_800,
    ) -> None:
        self.redis = redis_client
        self.prefix = prefix
        self.session_ttl_seconds = session_ttl_seconds
        self.run_ttl_seconds = run_ttl_seconds

    def save_session(self, session: dict) -> None:
        self.redis.set(
            self._session_key(session["sessionId"]),
            json.dumps(session, ensure_ascii=False),
            ex=self.session_ttl_seconds,
        )

    def get_session(self, session_id: str) -> dict | None:
        return self._load(self._session_key(session_id))

    def save_run(self, run: dict) -> None:
        self.redis.set(
            self._run_key(run["runId"]),
            json.dumps(run, ensure_ascii=False),
            ex=self.run_ttl_seconds,
        )

    def get_run(self, run_id: str) -> dict | None:
        return self._load(self._run_key(run_id))

    def save_client_run(self, session_id: str, client_message_id: str, run_id: str) -> None:
        self.redis.set(
            self._client_key(session_id, client_message_id),
            run_id,
            ex=self.run_ttl_seconds,
        )

    def get_client_run(self, session_id: str, client_message_id: str) -> str | None:
        value = self.redis.get(self._client_key(session_id, client_message_id))
        return value.decode("utf-8") if isinstance(value, bytes) else value

    def _load(self, key: str) -> dict | None:
        value = self.redis.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    def _session_key(self, session_id: str) -> str:
        return f"{self.prefix}:sessions:{session_id}"

    def _run_key(self, run_id: str) -> str:
        return f"{self.prefix}:runs:{run_id}"

    def _client_key(self, session_id: str, client_message_id: str) -> str:
        return f"{self.prefix}:client-runs:{session_id}:{client_message_id}"


class CachedAgentRunStore:
    def __init__(
        self,
        *,
        authoritative: AgentRunStore,
        cache: AgentRunStore,
    ) -> None:
        self.authoritative = authoritative
        self.cache = cache

    def save_session(self, session: dict) -> None:
        self.authoritative.save_session(session)
        self._cache_write(self.cache.save_session, session)

    def get_session(self, session_id: str) -> dict | None:
        cached = self._cache_read(self.cache.get_session, session_id)
        if cached is not None:
            return cached
        session = self.authoritative.get_session(session_id)
        if session is not None:
            self._cache_write(self.cache.save_session, session)
        return session

    def save_run(self, run: dict) -> None:
        self.authoritative.save_run(run)
        self._cache_write(self.cache.save_run, run)

    def get_run(self, run_id: str) -> dict | None:
        cached = self._cache_read(self.cache.get_run, run_id)
        if cached is not None:
            return cached
        run = self.authoritative.get_run(run_id)
        if run is not None:
            self._cache_write(self.cache.save_run, run)
        return run

    def save_client_run(
        self,
        session_id: str,
        client_message_id: str,
        run_id: str,
    ) -> None:
        self.authoritative.save_client_run(session_id, client_message_id, run_id)
        self._cache_write(
            self.cache.save_client_run,
            session_id,
            client_message_id,
            run_id,
        )

    def get_client_run(
        self,
        session_id: str,
        client_message_id: str,
    ) -> str | None:
        cached = self._cache_read(
            self.cache.get_client_run,
            session_id,
            client_message_id,
        )
        if cached is not None:
            return cached
        run_id = self.authoritative.get_client_run(session_id, client_message_id)
        if run_id is not None:
            self._cache_write(
                self.cache.save_client_run,
                session_id,
                client_message_id,
                run_id,
            )
        return run_id

    @staticmethod
    def _cache_read(callback, *args):
        try:
            return callback(*args)
        except Exception:
            # Redis 是可丢失缓存，读取异常必须回退到权威 Store。
            return None

    @staticmethod
    def _cache_write(callback, *args) -> None:
        try:
            callback(*args)
        except Exception:
            # 权威写已成功时，缓存回填失败不能使业务写入回滚。
            return None


class PostgresAgentRunStore:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def save_session(self, session: dict) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, tenant_id, site_id, user_id, control_projection
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    site_id = EXCLUDED.site_id,
                    user_id = EXCLUDED.user_id,
                    control_projection = EXCLUDED.control_projection
                """,
                (
                    session["sessionId"],
                    str(session.get("tenantId") or "default"),
                    session["siteId"],
                    session["userId"],
                    Jsonb(session),
                ),
            )

    def get_session(self, session_id: str) -> dict | None:
        with self.connection_factory() as connection:
            row = connection.execute(
                "SELECT control_projection FROM sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        return self._projection(row)

    def save_run(self, run: dict) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, session_id, task_type, status, workflow_id,
                    workflow_version, graph_runtime, model_id, model_version,
                    data_model_version, user_id, client_message_id,
                    control_projection, record
                )
                VALUES (
                    %s, %s, 'agent.turn', %s, 'pending', 'p2',
                    'langgraph', 'pending', '0', 'p2', %s, %s, %s, '{}'
                )
                ON CONFLICT (run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    user_id = EXCLUDED.user_id,
                    client_message_id = EXCLUDED.client_message_id,
                    control_projection = EXCLUDED.control_projection
                """,
                (
                    run["runId"],
                    run["sessionId"],
                    run["status"],
                    run["userId"],
                    run["clientMessageId"],
                    Jsonb(run),
                ),
            )

    def get_run(self, run_id: str) -> dict | None:
        with self.connection_factory() as connection:
            row = connection.execute(
                "SELECT control_projection FROM runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return self._projection(row)

    def save_client_run(
        self,
        session_id: str,
        client_message_id: str,
        run_id: str,
    ) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                UPDATE runs
                SET client_message_id = %s
                WHERE run_id = %s AND session_id = %s
                """,
                (client_message_id, run_id, session_id),
            )

    def get_client_run(
        self,
        session_id: str,
        client_message_id: str,
    ) -> str | None:
        with self.connection_factory() as connection:
            row = connection.execute(
                """
                SELECT run_id
                FROM runs
                WHERE session_id = %s AND client_message_id = %s
                """,
                (session_id, client_message_id),
            ).fetchone()
        return str(row["run_id"]) if row else None

    @staticmethod
    def _projection(row: dict[str, Any] | None) -> dict | None:
        if not row:
            return None
        projection = row["control_projection"]
        if isinstance(projection, str):
            return json.loads(projection)
        return dict(projection)


class AgentRunCoordinator:
    def __init__(
        self,
        *,
        store: AgentRunStore | None = None,
        max_sessions: int = 500,
        max_runs: int = 500,
        max_events: int = 2_000,
    ) -> None:
        self.max_events = max_events
        self.store = store or InMemoryAgentRunStore(max_sessions=max_sessions, max_runs=max_runs)
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-run")

    def create_session(self, *, site_id: str, user_id: str) -> dict:
        session_id = f"session_{uuid4().hex}"
        session = {"sessionId": session_id, "siteId": site_id, "userId": user_id, "status": "active"}
        with self._lock:
            self.store.save_session(session)
        return deepcopy(session)

    def get_session(self, session_id: str, user_id: str) -> dict:
        """读取当前用户拥有的服务端 Session，供 Runtime 派生可信作用域。"""
        with self._lock:
            session = self.store.get_session(session_id)
            if session is None or session["userId"] != user_id:
                raise KeyError("agent_session_not_found")
            return deepcopy(session)

    def start_run(
        self,
        *,
        session_id: str,
        user_id: str,
        client_message_id: str,
        execute_factory: Callable[[str], Awaitable[list[tuple[str, dict]]]],
    ) -> dict:
        with self._lock:
            session = self.store.get_session(session_id)
            if session is None or session["userId"] != user_id:
                raise KeyError("agent_session_not_found")
            existing_run_id = self.store.get_client_run(session_id, client_message_id)
            if existing_run_id:
                existing_run = self.store.get_run(existing_run_id)
                if existing_run:
                    return self._snapshot_record(existing_run)
            run_id = f"run_{uuid4().hex}"
            record = {
                "runId": run_id,
                "sessionId": session_id,
                "userId": user_id,
                "clientMessageId": client_message_id,
                "status": "queued",
                "cancelRequested": False,
                "events": [],
            }
            self._append_locked(
                record,
                "run.started",
                status="queued",
                payload={"status": "queued"},
            )
            self.store.save_run(record)
            self.store.save_client_run(session_id, client_message_id, run_id)
        self._executor.submit(self._execute, run_id, execute_factory)
        return self.snapshot(run_id)

    def _execute(self, run_id: str, execute_factory: Callable[[str], Awaitable[list[tuple[str, dict]]]]) -> None:
        self.append(
            run_id,
            "phase.changed",
            status="planning",
            label="正在理解任务",
            summary="正在确认设备、告警和时间范围上下文。",
            payload={
                "label": "正在理解任务",
                "summary": "正在确认设备、告警和时间范围上下文。",
                "status": "running",
                "stepId": "intent",
            },
        )
        try:
            projected_events = asyncio.run(execute_factory(run_id))
            for event_type, fields in projected_events:
                if self.cancel_requested(run_id):
                    return
                self.append(run_id, event_type, **fields)
        except Exception as exc:
            if self.cancel_requested(run_id):
                return
            error = {"message": str(exc)[:240], "retryable": False}
            self.append(
                run_id,
                "error",
                status="failed",
                error=error,
                payload=error,
            )

    def append(self, run_id: str, event_type: str, **fields) -> dict:
        with self._lock:
            record = self.store.get_run(run_id)
            if record is None:
                raise KeyError("agent_run_not_found")
            event = self._append_locked(record, event_type, **fields)
            self.store.save_run(record)
            return deepcopy(event)

    def _append_locked(self, record: dict, event_type: str, **fields) -> dict:
        sequence = (record["events"][-1]["eventSequence"] if record["events"] else 0) + 1
        event = {
            "eventId": f"{record['runId']}:{sequence}",
            "type": event_type,
            "runId": record["runId"],
            "conversationId": record["sessionId"],
            "messageId": record["clientMessageId"],
            "sequence": sequence,
            # 兼容现有前端与 Last-Event-ID 游标，后续统一迁移到 sequence。
            "eventSequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": fields.get("payload") or {},
            **fields,
        }
        record["events"].append(event)
        if len(record["events"]) > self.max_events:
            started = next(
                (
                    existing
                    for existing in record["events"]
                    if existing["type"] == "run.started"
                ),
                None,
            )
            if started is None:
                record["events"] = record["events"][-self.max_events :]
            elif self.max_events == 1:
                record["events"] = [started]
            else:
                recent = [
                    existing
                    for existing in record["events"][-self.max_events :]
                    if existing["eventSequence"] != started["eventSequence"]
                ]
                record["events"] = [
                    started,
                    *recent[-(self.max_events - 1) :],
                ]
        if fields.get("status") and (
            event_type.startswith("run.")
            or event_type == "phase.changed"
            or event_type.startswith("response.")
            or event_type == "error"
        ):
            record["status"] = fields["status"]
        return event

    def cancel(self, run_id: str, user_id: str) -> dict:
        with self._lock:
            record = self.store.get_run(run_id)
            if record is None or record["userId"] != user_id:
                raise KeyError("agent_run_not_found")
            if record["status"] not in TERMINAL_RUN_STATUSES:
                record["cancelRequested"] = True
                self._append_locked(
                    record,
                    "run.cancelled",
                    status="cancelled",
                    payload={"status": "cancelled"},
                )
                self.store.save_run(record)
            return self._snapshot_locked(record)

    def cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            record = self.store.get_run(run_id)
            return bool(record and record["cancelRequested"])

    def snapshot(self, run_id: str, user_id: str | None = None) -> dict:
        with self._lock:
            record = self.store.get_run(run_id)
            if record is None or (user_id is not None and record["userId"] != user_id):
                raise KeyError("agent_run_not_found")
            return self._snapshot_locked(record)

    def _snapshot_locked(self, record: dict) -> dict:
        return self._snapshot_record(record)

    @staticmethod
    def _snapshot_record(record: dict) -> dict:
        events = deepcopy(record["events"])
        return {
            "runId": record["runId"],
            "sessionId": record["sessionId"],
            "clientMessageId": record["clientMessageId"],
            "status": record["status"],
            "lastEventId": str(events[-1]["eventSequence"] if events else 0),
            "events": events,
        }


def build_agent_run_coordinator() -> AgentRunCoordinator:
    database_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL")
    authoritative: AgentRunStore | None = None
    if database_url:
        from packages.storage.postgres_connection import (
            build_postgres_connection_factory,
            ensure_repository_schema,
        )

        connection_factory = build_postgres_connection_factory(database_url)
        ensure_repository_schema(connection_factory)
        authoritative = PostgresAgentRunStore(connection_factory)
    if not redis_url:
        if authoritative is not None:
            return AgentRunCoordinator(store=authoritative)
        return AgentRunCoordinator()
    from redis import Redis

    redis_client = Redis.from_url(redis_url, decode_responses=True)
    redis_store = RedisAgentRunStore(redis_client)
    if authoritative is not None:
        return AgentRunCoordinator(
            store=CachedAgentRunStore(
                authoritative=authoritative,
                cache=redis_store,
            )
        )
    return AgentRunCoordinator(store=redis_store)


agent_run_coordinator = build_agent_run_coordinator()
