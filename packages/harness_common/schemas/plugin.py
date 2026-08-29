from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PluginRuntimeStatus(StrEnum):
    INSTALLED = "installed"
    READY = "ready"
    ACTIVE = "active"
    DISABLED = "disabled"
    FAILED = "failed"


class ToolDefinition(BaseModel):
    name: str
    version: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "L0"
    allowed_roles: list[str] = Field(default_factory=lambda: ["admin"])
    read_only: bool = True
    timeout: int = 10
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    plugin_id: str
    plugin_version: str


class PluginInstallation(BaseModel):
    plugin_id: str
    version: str
    package_hash: str
    signature_status: str = "unsigned-dev"
    install_status: str = "installed"
    runtime_status: PluginRuntimeStatus = PluginRuntimeStatus.INSTALLED
    capabilities: list[str] = Field(default_factory=list)
    core_api_range: str = ">=0.1,<1"
    tools: list[ToolDefinition] = Field(default_factory=list)
    installed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: datetime | None = None
    health: dict[str, Any] = Field(default_factory=dict)
    process_isolation: str = "process"
    sandboxed: bool = False
    runtime_pid: int | None = None
    idempotency_key: str | None = None
