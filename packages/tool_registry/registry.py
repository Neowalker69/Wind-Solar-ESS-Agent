from dataclasses import dataclass, field
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field

from packages.harness_common.schemas.run import RunRecord
from packages.harness_common.schemas.tool_result import ToolResult


class ToolNotFoundError(KeyError):
    pass


class ToolNotVisibleError(PermissionError):
    pass


class ToolClassification(StrEnum):
    AUTHORITATIVE = "authoritative"
    DERIVED = "derived"
    RUNTIME = "runtime"
    ACTION_RECEIPT = "action_receipt"
    UNAVAILABLE = "unavailable"


class CapabilityToolManifest(BaseModel):
    tool_id: str
    version: str = "0.1.0"
    capability: str
    description: str
    handler: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "L0"
    disclosure: str = "core"
    classification: ToolClassification
    readable: bool
    unavailable_reason: str | None = None
    dependencies: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolExecutionContext:
    run: RunRecord
    registry: "CapabilityRegistry"
    user: dict[str, str] = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[dict[str, Any], ToolExecutionContext], dict[str, Any] | list[dict[str, Any]]]


class CapabilityRegistry:
    def __init__(self, manifests: list[CapabilityToolManifest]) -> None:
        self._manifests = {manifest.tool_id: manifest for manifest in manifests}
        self._handlers = {manifest.tool_id: self._load_handler(manifest.handler) for manifest in manifests}

    @classmethod
    def from_builtin_manifests(cls) -> "CapabilityRegistry":
        manifest_dir = Path(__file__).parent / "manifests"
        manifests: list[CapabilityToolManifest] = []
        for path in sorted(manifest_dir.glob("*.yaml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            manifests.extend(CapabilityToolManifest.model_validate(item) for item in document.get("tools", []))
        return cls(manifests)

    def list_manifests(self) -> list[CapabilityToolManifest]:
        return sorted(self._manifests.values(), key=lambda item: item.tool_id)

    def get_manifest(self, tool_id: str) -> CapabilityToolManifest:
        try:
            return self._manifests[tool_id]
        except KeyError as exc:
            raise ToolNotFoundError(tool_id) from exc

    def is_readable(
        self,
        tool_id: str,
        context: ToolExecutionContext,
    ) -> bool:
        return self._is_readable(self.get_manifest(tool_id), context)

    def visible_manifests(self, context: ToolExecutionContext) -> list[CapabilityToolManifest]:
        policy = context.run.runtime_context.get("policy", {})
        visible_ids = set(policy.get("visible_tool_ids", []))
        return [
            manifest
            for manifest in self.list_manifests()
            if self._is_readable(manifest, context) and manifest.tool_id in visible_ids
        ]

    def invoke(self, tool_id: str, payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any] | list[dict[str, Any]]:
        manifest = self.get_manifest(tool_id)
        policy = context.run.runtime_context.get("policy", {})
        policy_visible_ids = set(policy.get("visible_tool_ids", []))
        if manifest.capability != "capability_discovery" and tool_id not in policy_visible_ids:
            raise ToolNotVisibleError(tool_id)
        return self._handlers[tool_id](payload, context)

    def execute_for_model(
        self,
        tool_id: str,
        payload: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        manifest = self.get_manifest(tool_id)
        if not self._is_readable(manifest, context):
            raise ToolNotVisibleError(tool_id)
        try:
            output = self.invoke(tool_id, payload, context)
        except (ToolNotFoundError, ToolNotVisibleError):
            raise
        except Exception as exc:
            # 模型只接收稳定错误码，具体异常仍由服务端日志和 Trace 负责记录。
            return ToolResult.failed(
                str(getattr(exc, "error_code", "tool_execution_failed"))
            )
        return ToolResult.from_handler_output(output)

    @staticmethod
    def _is_readable(
        manifest: CapabilityToolManifest,
        context: ToolExecutionContext,
    ) -> bool:
        return manifest.readable

    @staticmethod
    def _load_handler(reference: str) -> Handler:
        module_name, function_name = reference.split(":", 1)
        handler = getattr(import_module(module_name), function_name)
        return handler
