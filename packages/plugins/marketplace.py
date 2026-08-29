from packages.harness_common.schemas.plugin import PluginInstallation
from packages.plugins.opcua_connector.tools import tool_definitions


def catalog() -> list[PluginInstallation]:
    return [
        PluginInstallation(
            plugin_id="opcua_connector",
            version="0.1.0",
            package_hash="sha256:dev",
            capabilities=["opcua.read", "opcua.browse"],
            tools=tool_definitions("0.1.0"),
        )
    ]
