from typing import Any

from packages.harness_common.schemas.plugin import PluginInstallation, PluginRuntimeStatus
from packages.plugins.opcua_connector.host import OpcUaPluginHost


def health_check(plugin: PluginInstallation) -> PluginInstallation:
    healthy = plugin.package_hash.startswith("sha256:")
    status = PluginRuntimeStatus.READY if healthy else PluginRuntimeStatus.FAILED
    return plugin.model_copy(update={"runtime_status": status, "health": {"healthy": healthy}})


class PluginProcessSupervisor:
    """Own plugin child processes without imposing a sandbox."""

    def __init__(self) -> None:
        self._hosts: dict[tuple[str, str], OpcUaPluginHost] = {}

    def activate(self, plugin: PluginInstallation) -> PluginInstallation:
        key = (plugin.plugin_id, plugin.version)
        host = self._hosts.get(key)
        if host is None:
            if plugin.plugin_id != "opcua_connector":
                raise ValueError("plugin_process_host_unavailable")
            host = OpcUaPluginHost(plugin.version)
            self._hosts[key] = host
        health = host.start()
        return plugin.model_copy(
            update={
                "runtime_status": PluginRuntimeStatus.ACTIVE,
                "runtime_pid": health["pid"],
                "process_isolation": "process",
                "sandboxed": False,
                "health": health,
            }
        )

    def health(self, plugin: PluginInstallation) -> PluginInstallation:
        host = self._hosts.get((plugin.plugin_id, plugin.version))
        health = host.health() if host is not None else {
            "healthy": False,
            "pid": None,
            "isolation": "process",
            "sandboxed": False,
        }
        status = (
            plugin.runtime_status
            if health["healthy"]
            else PluginRuntimeStatus.FAILED
        )
        return plugin.model_copy(
            update={
                "runtime_status": status,
                "runtime_pid": health.get("pid"),
                "health": health,
            }
        )

    def execute(
        self,
        plugin_id: str,
        version: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        host = self._hosts.get((plugin_id, version))
        if host is None:
            raise RuntimeError("plugin_process_not_active")
        return host.execute(tool_name, payload)

    def stop(self, plugin_id: str, version: str) -> None:
        host = self._hosts.pop((plugin_id, version), None)
        if host is not None:
            host.close()

    def close_all(self) -> None:
        for host in self._hosts.values():
            host.close()
        self._hosts.clear()
