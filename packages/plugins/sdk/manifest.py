from pydantic import BaseModel, Field

from packages.harness_common.schemas.plugin import ToolDefinition


class PluginManifest(BaseModel):
    plugin_id: str
    version: str
    capabilities: list[str]
    core_api_range: str
    package_hash: str
    signature: str | None = None
    tools: list[ToolDefinition] = Field(default_factory=list)

    def validate_readonly(self) -> None:
        for tool in self.tools:
            if not tool.read_only:
                raise ValueError("plugin_manifest_contains_write_tool")
