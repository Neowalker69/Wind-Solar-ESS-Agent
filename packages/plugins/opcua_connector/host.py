from __future__ import annotations

import multiprocessing
import os
from multiprocessing.connection import Connection
from threading import Lock
from typing import Any
from uuid import uuid4

from packages.plugins.opcua_connector.tools import read_node, tool_definitions


class PluginProcessUnavailable(RuntimeError):
    pass


class PluginExecutionError(RuntimeError):
    pass


def _plugin_process_main(connection: Connection, version: str) -> None:
    """Run the plugin in an independent process without applying a sandbox."""
    tools = {tool.name: tool for tool in tool_definitions(version)}
    connection.send({"type": "ready", "pid": os.getpid(), "version": version})
    try:
        while True:
            message = connection.recv()
            operation = message.get("operation")
            request_id = message.get("request_id")
            if operation == "shutdown":
                connection.send({"type": "shutdown", "request_id": request_id})
                return
            if operation == "health":
                connection.send({
                    "type": "health",
                    "request_id": request_id,
                    "healthy": True,
                    "pid": os.getpid(),
                    "version": version,
                })
                continue
            if operation != "execute":
                connection.send({
                    "type": "error",
                    "request_id": request_id,
                    "code": "plugin_operation_unknown",
                })
                continue
            tool_name = str(message.get("tool_name") or "")
            try:
                if tool_name not in tools:
                    raise KeyError("tool_not_registered")
                if tool_name != "opcua_read_node":
                    raise NotImplementedError("tool_not_implemented")
                result = read_node(dict(message.get("payload") or {}))
                connection.send({
                    "type": "result",
                    "request_id": request_id,
                    "result": {**result, "plugin_pid": os.getpid()},
                })
            except Exception as exc:
                connection.send({
                    "type": "error",
                    "request_id": request_id,
                    "code": str(exc) or type(exc).__name__,
                })
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


class OpcUaPluginHost:
    def __init__(self, version: str = "0.1.0", *, timeout_seconds: float = 5.0) -> None:
        self.version = version
        self.timeout_seconds = timeout_seconds
        self.tools = {tool.name: tool for tool in tool_definitions(version)}
        self._context = multiprocessing.get_context("spawn")
        self._connection: Connection | None = None
        self._process: multiprocessing.Process | None = None
        self._lock = Lock()

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    @property
    def is_alive(self) -> bool:
        return bool(self._process is not None and self._process.is_alive())

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.is_alive:
                return self._request_locked("health")
            self._dispose_dead_process_locked()
            parent_connection, child_connection = self._context.Pipe()
            process = self._context.Process(
                target=_plugin_process_main,
                args=(child_connection, self.version),
                name=f"opcua-plugin-{self.version}",
                daemon=True,
            )
            process.start()
            child_connection.close()
            self._connection = parent_connection
            self._process = process
            if not parent_connection.poll(self.timeout_seconds):
                self._terminate_locked()
                raise PluginProcessUnavailable("plugin_process_start_timeout")
            ready = parent_connection.recv()
            if ready.get("type") != "ready":
                self._terminate_locked()
                raise PluginProcessUnavailable("plugin_process_start_failed")
            return {
                "healthy": True,
                "pid": ready["pid"],
                "version": ready["version"],
                "isolation": "process",
                "sandboxed": False,
            }

    def execute(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._process is None:
                return self._start_and_execute_locked(tool_name, payload)
            if not self.is_alive:
                raise PluginProcessUnavailable("plugin_process_unavailable")
            response = self._request_locked(
                "execute", tool_name=tool_name, payload=payload
            )
            if response.get("type") == "error":
                raise PluginExecutionError(
                    str(response.get("code") or "plugin_execution_failed")
                )
            return dict(response["result"])

    def health(self) -> dict[str, Any]:
        with self._lock:
            if not self.is_alive:
                return {
                    "healthy": False,
                    "pid": self.pid,
                    "version": self.version,
                    "isolation": "process",
                    "sandboxed": False,
                }
            response = self._request_locked("health")
            return {
                "healthy": bool(response.get("healthy")),
                "pid": response.get("pid"),
                "version": response.get("version", self.version),
                "isolation": "process",
                "sandboxed": False,
            }

    def wait(self, timeout: float | None = None) -> None:
        if self._process is not None:
            self._process.join(timeout)

    def close(self) -> None:
        with self._lock:
            if self.is_alive:
                try:
                    self._request_locked("shutdown")
                except PluginProcessUnavailable:
                    pass
            if self._process is not None:
                self._process.join(timeout=1)
            self._terminate_locked()

    def _start_and_execute_locked(
        self, tool_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        # start() also takes the lock, so perform the startup inline here.
        self._dispose_dead_process_locked()
        parent_connection, child_connection = self._context.Pipe()
        process = self._context.Process(
            target=_plugin_process_main,
            args=(child_connection, self.version),
            name=f"opcua-plugin-{self.version}",
            daemon=True,
        )
        process.start()
        child_connection.close()
        self._connection = parent_connection
        self._process = process
        if not parent_connection.poll(self.timeout_seconds):
            self._terminate_locked()
            raise PluginProcessUnavailable("plugin_process_start_timeout")
        parent_connection.recv()
        response = self._request_locked(
            "execute", tool_name=tool_name, payload=payload
        )
        if response.get("type") == "error":
            raise PluginExecutionError(
                str(response.get("code") or "plugin_execution_failed")
            )
        return dict(response["result"])

    def _request_locked(self, operation: str, **payload: Any) -> dict[str, Any]:
        connection = self._connection
        if connection is None or not self.is_alive:
            raise PluginProcessUnavailable("plugin_process_unavailable")
        request_id = uuid4().hex
        try:
            connection.send({"operation": operation, "request_id": request_id, **payload})
            if not connection.poll(self.timeout_seconds):
                raise PluginProcessUnavailable("plugin_process_timeout")
            response = connection.recv()
        except (BrokenPipeError, EOFError, OSError) as exc:
            raise PluginProcessUnavailable("plugin_process_unavailable") from exc
        if response.get("request_id") != request_id:
            raise PluginProcessUnavailable("plugin_process_protocol_error")
        return dict(response)

    def _dispose_dead_process_locked(self) -> None:
        if self._process is not None:
            self._process.join(timeout=0)
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._process = None

    def _terminate_locked(self) -> None:
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1)
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._process = None
