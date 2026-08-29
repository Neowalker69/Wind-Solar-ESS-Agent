from typing import Any, Callable, Iterable
import json
import os

import httpx

from packages.model.errors import ModelProviderError

DEFAULT_MODEL_PROVIDER_TIMEOUT_SECONDS = 90
DEFAULT_MODEL_PROVIDER_STREAM_TIMEOUT_SECONDS = 120


DEEPSEEK_JSON_OUTPUT_INSTRUCTION = "Return a valid JSON object. Do not wrap it in markdown."


class OpenAICompatibleAdapter:
    """OpenAI-compatible HTTP adapter with injectable transport.

    This contains request/response shaping only. It does not download models and
    tests inject a local transport instead of making network calls.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        transport: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model
        self.model_version = "openai-compatible"
        self.transport = transport

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model_id, "messages": messages}
        if response_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": response_schema}
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return self.transport(payload)


class DeepSeekAdapter(OpenAICompatibleAdapter):
    provider = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        thinking: str | None = "disabled",
        reasoning_effort: str | None = None,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        stream_transport: Callable[[dict[str, Any]], Iterable[dict[str, Any]]] | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            transport=transport or self._http_transport,
        )
        self.provider = "deepseek"
        self.model_version = "deepseek-openai-compatible"
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort
        self.stream_transport = stream_transport or self._http_stream_transport

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_messages = self._messages_with_json_instruction(messages) if response_schema is not None else messages
        payload: dict[str, Any] = {"model": self.model_id, "messages": payload_messages, "stream": False}
        if self.thinking and self.model_id.startswith("deepseek-v4"):
            payload["thinking"] = {"type": self.thinking}
        if self.reasoning_effort and self.model_id.startswith("deepseek-v4"):
            payload["reasoning_effort"] = self.reasoning_effort
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return self.transport(payload)

    def complete_stream(
        self,
        *,
        messages: list[dict[str, str]],
        on_delta: Callable[[str], None],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """转发模型原始文本增量，同时聚合出与 complete 一致的审计结果。"""
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "stream": True,
        }
        if self.thinking and self.model_id.startswith("deepseek-v4"):
            payload["thinking"] = {"type": self.thinking}
        if self.reasoning_effort and self.model_id.startswith("deepseek-v4"):
            payload["reasoning_effort"] = self.reasoning_effort
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        finish_reason = None
        usage: dict[str, Any] = {}
        response_id = None
        for chunk in self.stream_transport(payload):
            response_id = chunk.get("id") or response_id
            if chunk.get("usage"):
                usage = chunk["usage"]
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content_delta = str(delta.get("content") or "")
            reasoning_delta = str(delta.get("reasoning_content") or "")
            if content_delta:
                content_parts.append(content_delta)
                on_delta(content_delta)
            if reasoning_delta:
                reasoning_parts.append(reasoning_delta)
            finish_reason = choice.get("finish_reason") or finish_reason
        return {
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts) or None,
            "tool_calls": [],
            "finish_reason": finish_reason,
            "usage": usage,
            "response_id": response_id,
        }

    def _messages_with_json_instruction(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if any("json" in message.get("content", "").lower() for message in messages):
            return messages
        if messages and messages[0].get("role") == "system":
            return [
                {**messages[0], "content": f"{messages[0].get('content', '')}\n\n{DEEPSEEK_JSON_OUTPUT_INSTRUCTION}"},
                *messages[1:],
            ]
        return [{"role": "system", "content": DEEPSEEK_JSON_OUTPUT_INSTRUCTION}, *messages]

    def _http_transport(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=_model_timeout("MODEL_PROVIDER_TIMEOUT_SECONDS", DEFAULT_MODEL_PROVIDER_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise ModelProviderError(
                provider=self.provider,
                message=f"{self.provider} request failed with HTTP {status_code}",
                status_code=status_code,
                retryable=status_code == 429 or status_code >= 500,
                details={
                    "provider": self.provider,
                    "upstream_status_code": status_code,
                    "upstream_body": exc.response.text[:500],
                },
            ) from exc
        except httpx.RequestError as exc:
            raise ModelProviderError(
                provider=self.provider,
                message=f"{self.provider} request failed before receiving a response: {type(exc).__name__}",
                retryable=True,
                details={
                    "provider": self.provider,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ModelProviderError(
                provider=self.provider,
                message=f"{self.provider} returned a non-JSON response",
                status_code=response.status_code,
                retryable=True,
                details={"provider": self.provider, "upstream_body": response.text[:500]},
            ) from exc
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        return {
            "content": message.get("content", ""),
            "reasoning_content": message.get("reasoning_content"),
            "tool_calls": message.get("tool_calls", []),
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage", {}),
            "response_id": data.get("id"),
            "raw": data,
        }

    def _http_stream_transport(
        self,
        payload: dict[str, Any],
    ) -> Iterable[dict[str, Any]]:
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=_model_timeout(
                    "MODEL_PROVIDER_STREAM_TIMEOUT_SECONDS",
                    DEFAULT_MODEL_PROVIDER_STREAM_TIMEOUT_SECONDS,
                ),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ModelProviderError(
                            provider=self.provider,
                            message=f"{self.provider} returned an invalid streaming frame",
                            status_code=response.status_code,
                            retryable=True,
                            details={"provider": self.provider},
                        ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise ModelProviderError(
                provider=self.provider,
                message=f"{self.provider} request failed with HTTP {status_code}",
                status_code=status_code,
                retryable=status_code == 429 or status_code >= 500,
                details={
                    "provider": self.provider,
                    "upstream_status_code": status_code,
                    "upstream_body": exc.response.text[:500],
                },
            ) from exc
        except httpx.RequestError as exc:
            raise ModelProviderError(
                provider=self.provider,
                message=f"{self.provider} stream failed before completion: {type(exc).__name__}",
                retryable=True,
                details={
                    "provider": self.provider,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc


class BailianAdapter(DeepSeekAdapter):
    """阿里云百炼 OpenAI-compatible Chat/Completions 适配器。"""

    provider = "bailian"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen3.7-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        stream_transport: Callable[[dict[str, Any]], Iterable[dict[str, Any]]] | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            thinking=None,
            transport=transport,
            stream_transport=stream_transport,
        )
        self.provider = "bailian"
        self.model_version = "bailian-openai-compatible"


def _model_timeout(environment_key: str, default: int) -> int:
    raw_value = os.getenv(environment_key, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(1, min(value, 300))
