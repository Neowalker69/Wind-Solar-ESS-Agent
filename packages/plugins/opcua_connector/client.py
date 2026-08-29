from typing import Any, Protocol


class OpcUaReadClient(Protocol):
    async def browse_nodes(self, node_id: str = "Root") -> list[dict[str, Any]]: ...

    async def read_node(self, node_id: str) -> dict[str, Any]: ...

    async def read_many(self, node_ids: list[str]) -> list[dict[str, Any]]: ...


class AsyncuaReadOnlyClient:
    """Read-only asyncua client.

    The asyncua import is lazy so local unit tests do not need a server or
    package import side effects. No write/call/ack methods are exposed.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    async def browse_nodes(self, node_id: str = "Root") -> list[dict[str, Any]]:
        from asyncua import Client

        async with Client(url=self.endpoint) as client:
            node = client.get_root_node() if node_id == "Root" else client.get_node(node_id)
            children = await node.get_children()
            return [{"node_id": child.nodeid.to_string(), "browse_name": str(await child.read_browse_name())} for child in children]

    async def read_node(self, node_id: str) -> dict[str, Any]:
        from asyncua import Client

        async with Client(url=self.endpoint) as client:
            node = client.get_node(node_id)
            # 坏状态仍需作为只读观测返回给 Agent，而不是被客户端异常吞没。
            data_value = await node.read_data_value(raise_on_bad_status=False)
            return {
                "node_id": node_id,
                "value": data_value.Value.Value,
                "quality": data_value.StatusCode.name,
            }

    async def read_many(self, node_ids: list[str]) -> list[dict[str, Any]]:
        return [await self.read_node(node_id) for node_id in node_ids]


class FakeOpcUaReadOnlyClient:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = values or {}

    async def browse_nodes(self, node_id: str = "Root") -> list[dict[str, Any]]:
        return [{"node_id": key, "browse_name": key.rsplit(";", 1)[-1]} for key in self.values]

    async def read_node(self, node_id: str) -> dict[str, Any]:
        return {"node_id": node_id, "value": self.values.get(node_id), "quality": "Good" if node_id in self.values else "Bad"}

    async def read_many(self, node_ids: list[str]) -> list[dict[str, Any]]:
        return [await self.read_node(node_id) for node_id in node_ids]
