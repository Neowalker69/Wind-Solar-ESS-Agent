from typing import Any, Protocol


class ModelPort(Protocol):
    provider: str
    model_id: str
    model_version: str

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
