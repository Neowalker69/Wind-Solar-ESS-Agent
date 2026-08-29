from packages.harness_common.schemas.plugin import ToolDefinition


READ_TOOLS = [
    "opcua_list_servers",
    "opcua_browse_nodes",
    "opcua_read_node",
    "opcua_read_many",
    "opcua_resolve_asset",
    "opcua_get_asset_status",
    "opcua_get_timeseries_snapshot",
    "opcua_subscribe_data_changes",
    "opcua_get_subscription_status",
]


def tool_definitions(version: str = "0.1.0") -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name=name,
            version=version,
            description=f"Read-only OPC UA tool: {name}",
            plugin_id="opcua_connector",
            plugin_version=version,
            risk_level="L0" if "read" in name or "list" in name or "browse" in name else "L1",
            read_only=True,
        )
        for name in READ_TOOLS
    ]


def read_node(payload: dict) -> dict:
    return {"node_id": payload["node_id"], "value": payload.get("mock_value", "OK"), "quality": payload.get("mock_quality", "Good")}
