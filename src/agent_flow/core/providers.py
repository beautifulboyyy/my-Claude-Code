"""LLM provider interface and provider implementations."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent_flow.core.messages import AnyMessage, AssistantMessage, ToolCall, ToolMessage, _require_str, message_from_dict
from agent_flow.core.types import JsonObject


def _chunk_type(payload: Mapping[str, object]) -> str:
    return _require_str(payload, "type")


@dataclass(frozen=True, slots=True)
class ProviderTextDelta:
    """A streamed assistant text delta."""

    type: ClassVar[Literal["text_delta"]] = "text_delta"
    delta: str

    def to_dict(self) -> JsonObject:
        return {"type": self.type, "delta": self.delta}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(delta=_require_str(payload, "delta"))


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    """A complete tool call emitted by a provider."""

    type: ClassVar[Literal["tool_call"]] = "tool_call"
    tool_call: ToolCall

    def to_dict(self) -> JsonObject:
        return {"type": self.type, "tool_call": self.tool_call.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        tool_call = payload.get("tool_call")
        if not isinstance(tool_call, dict):
            raise ValueError("Expected 'tool_call' to be an object")
        return cls(tool_call=ToolCall.from_dict(tool_call))


@dataclass(frozen=True, slots=True)
class ProviderFinalResponse:
    """The final assistant message for a provider turn."""

    type: ClassVar[Literal["final_response"]] = "final_response"
    message: AssistantMessage

    def to_dict(self) -> JsonObject:
        return {"type": self.type, "message": self.message.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Expected 'message' to be an object")
        restored = message_from_dict(message)
        if not isinstance(restored, AssistantMessage):
            raise ValueError("Expected 'message' to be an assistant message")
        return cls(message=restored)


@dataclass(frozen=True, slots=True)
class ProviderErrorStep:
    """A fake-provider script step that raises a provider error."""

    type: ClassVar[Literal["error"]] = "error"
    message: str
    code: str = "provider_error"

    def to_dict(self) -> JsonObject:
        return {"type": self.type, "message": self.message, "code": self.code}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(message=_require_str(payload, "message"), code=_require_str(payload, "code"))


@dataclass(frozen=True, slots=True)
class ProviderNeverStep:
    """A fake-provider script step that never yields another chunk."""

    type: ClassVar[Literal["never"]] = "never"


AnyProviderChunk = ProviderTextDelta | ProviderToolCall | ProviderFinalResponse
ProviderScriptItem = AnyProviderChunk | ProviderErrorStep | ProviderNeverStep | Mapping[str, object]
PostJson = Callable[[str, Mapping[str, object], Mapping[str, str], float], Mapping[str, object]]


class ProviderError(RuntimeError):
    """Raised when an LLM provider cannot continue streaming."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class LLMProvider(Protocol):
    """Minimal async streaming interface consumed by the future agent loop."""

    def stream(
        self,
        messages: Sequence[AnyMessage],
        *,
        tools: Sequence[JsonObject] = (),
    ) -> AsyncIterator[AnyProviderChunk]:
        """Stream provider chunks for one assistant turn."""
        ...


def _post_json(
    url: str,
    payload: Mapping[str, object],
    headers: Mapping[str, str],
    timeout: float,
) -> Mapping[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise ProviderError(f"MiMo API request failed: HTTP {exc.code}", code="mimo_http_error") from exc
    except URLError as exc:
        raise ProviderError(f"MiMo API request failed: {exc.reason}", code="mimo_network_error") from exc

    try:
        decoded = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ProviderError("MiMo API returned invalid JSON.", code="mimo_invalid_json") from exc
    if not isinstance(decoded, dict):
        raise ProviderError("MiMo API returned a non-object response.", code="mimo_invalid_response")
    return cast(Mapping[str, object], decoded)


@dataclass(frozen=True, slots=True)
class MiMoProvider:
    """MiMo OpenAI-compatible chat completions provider.

    The first version adapts one non-streaming OpenAI-compatible response into
    provider chunks. Keeping that mapping explicit leaves room for native SSE
    streaming later without changing AgentLoop.
    """

    api_key: str
    model: str = "mimo-v2.5-pro"
    endpoint: str = "https://api.xiaomimimo.com/v1/chat/completions"
    timeout: float = 60.0
    api_key_source: Literal["explicit", "environment", "user_config"] = "explicit"
    post_json: PostJson = _post_json

    @classmethod
    def from_default_config(cls, *, config_path: Path | None = None) -> "MiMoProvider":
        env_key = os.environ.get("MIMO_API_KEY")
        if env_key:
            return cls(api_key=env_key, api_key_source="environment")

        resolved_config_path = config_path or Path.home() / ".agent-flow" / "settings.json"
        config = _read_user_config(resolved_config_path)
        api_key = config.get("mimo_api_key")
        if isinstance(api_key, str) and api_key:
            model = config.get("mimo_model")
            if not isinstance(model, str) or not model:
                model = "mimo-v2.5-pro"
            return cls(api_key=api_key, model=model, api_key_source="user_config")

        raise ProviderError(
            "MiMo API key is required. Set MIMO_API_KEY or configure ~/.agent-flow/settings.json.",
            code="mimo_api_key_missing",
        )

    async def stream(
        self,
        messages: Sequence[AnyMessage],
        *,
        tools: Sequence[JsonObject] = (),
    ) -> AsyncIterator[AnyProviderChunk]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [_message_to_openai(message) for message in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = [_tool_schema_to_openai(tool) for tool in tools]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = await asyncio.to_thread(self.post_json, self.endpoint, payload, headers, self.timeout)
        for chunk in _chunks_from_openai_response(response):
            yield chunk


def _read_user_config(config_path: Path) -> Mapping[str, object]:
    if not config_path.exists():
        return {}
    try:
        decoded = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProviderError(f"Could not read MiMo config file: {config_path}", code="mimo_config_error") from exc
    except json.JSONDecodeError as exc:
        raise ProviderError(f"MiMo config file is not valid JSON: {config_path}", code="mimo_config_error") from exc
    if not isinstance(decoded, dict):
        raise ProviderError(f"MiMo config file must contain a JSON object: {config_path}", code="mimo_config_error")
    return cast(Mapping[str, object], decoded)


def _message_to_openai(message: AnyMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if isinstance(message, AssistantMessage) and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments),
                },
            }
            for tool_call in message.tool_calls
        ]
    if isinstance(message, ToolMessage):
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _tool_schema_to_openai(tool: Mapping[str, object]) -> dict[str, object]:
    name = _require_str(tool, "name")
    description = _require_str(tool, "description")
    input_schema = tool.get("input_schema", {"type": "object"})
    if not isinstance(input_schema, dict):
        raise ProviderError(f"Tool schema for {name!r} must contain an object input_schema.", code="mimo_tool_schema_error")
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema,
        },
    }


def _chunks_from_openai_response(response: Mapping[str, object]) -> list[AnyProviderChunk]:
    message = _first_choice_message(response)
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    raw_tool_calls = message.get("tool_calls", [])
    if raw_tool_calls is None:
        raw_tool_calls = []
    if not isinstance(raw_tool_calls, list):
        raise ProviderError("MiMo API returned malformed tool_calls.", code="mimo_invalid_response")

    chunks: list[AnyProviderChunk] = []
    if text:
        chunks.append(ProviderTextDelta(delta=text))
    for raw_tool_call in raw_tool_calls:
        chunks.append(ProviderToolCall(tool_call=_tool_call_from_openai(raw_tool_call)))

    if chunks and any(isinstance(chunk, ProviderToolCall) for chunk in chunks):
        return chunks

    message_id = response.get("id")
    if not isinstance(message_id, str) or not message_id:
        message_id = "mimo_assistant"
    chunks.append(ProviderFinalResponse(message=AssistantMessage(id=message_id, content=text)))
    return chunks


def _first_choice_message(response: Mapping[str, object]) -> Mapping[str, object]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("MiMo API response did not include choices.", code="mimo_invalid_response")
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise ProviderError("MiMo API returned malformed choices.", code="mimo_invalid_response")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise ProviderError("MiMo API choice did not include a message.", code="mimo_invalid_response")
    return cast(Mapping[str, object], message)


def _tool_call_from_openai(raw_tool_call: object) -> ToolCall:
    if not isinstance(raw_tool_call, Mapping):
        raise ProviderError("MiMo API returned a malformed tool call.", code="mimo_invalid_response")
    tool_call_id = _require_str(raw_tool_call, "id")
    function = raw_tool_call.get("function")
    if not isinstance(function, Mapping):
        raise ProviderError("MiMo API returned a tool call without a function.", code="mimo_invalid_response")
    function_payload = cast(Mapping[str, object], function)
    name = _require_str(function_payload, "name")
    raw_arguments = function_payload.get("arguments", "{}")
    if isinstance(raw_arguments, str):
        try:
            decoded_arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError("MiMo API returned invalid tool call arguments JSON.", code="mimo_invalid_response") from exc
    elif isinstance(raw_arguments, Mapping):
        decoded_arguments = raw_arguments
    else:
        raise ProviderError("MiMo API returned unsupported tool call arguments.", code="mimo_invalid_response")
    if not isinstance(decoded_arguments, dict):
        raise ProviderError("MiMo API tool call arguments must decode to an object.", code="mimo_invalid_response")
    return ToolCall(id=tool_call_id, name=name, arguments=cast(JsonObject, decoded_arguments))


def provider_chunk_from_dict(payload: Mapping[str, object]) -> AnyProviderChunk:
    chunk_type = _chunk_type(payload)
    if chunk_type == "text_delta":
        return ProviderTextDelta.from_dict(payload)
    if chunk_type == "tool_call":
        return ProviderToolCall.from_dict(payload)
    if chunk_type == "final_response":
        return ProviderFinalResponse.from_dict(payload)
    raise ValueError(f"Unknown provider chunk type: {chunk_type}")


def _script_item_from_dict(payload: Mapping[str, object]) -> AnyProviderChunk | ProviderErrorStep:
    if _chunk_type(payload) == "error":
        return ProviderErrorStep.from_dict(payload)
    return provider_chunk_from_dict(payload)


class FakeProvider:
    """Deterministic provider for offline agent-loop tests."""

    def __init__(self, script: Iterable[ProviderScriptItem], *, step_delay: float = 0.0) -> None:
        self._scripts: tuple[tuple[AnyProviderChunk | ProviderErrorStep | ProviderNeverStep, ...], ...] = (
            tuple(self._coerce_script_item(item) for item in script),
        )
        self._step_delay = step_delay
        self._request_count = 0
        self.requests: tuple[tuple[AnyMessage, ...], ...] = ()
        self.tool_requests: tuple[tuple[JsonObject, ...], ...] = ()

    @classmethod
    def turns(cls, scripts: Iterable[Iterable[ProviderScriptItem]], *, step_delay: float = 0.0) -> "FakeProvider":
        provider = cls([], step_delay=step_delay)
        provider._scripts = tuple(
            tuple(cls._coerce_script_item(item) for item in script)
            for script in scripts
        )
        return provider

    @staticmethod
    def text(delta: str) -> ProviderTextDelta:
        return ProviderTextDelta(delta=delta)

    @staticmethod
    def tool_call(tool_call: ToolCall) -> ProviderToolCall:
        return ProviderToolCall(tool_call=tool_call)

    @staticmethod
    def final(message: AssistantMessage) -> ProviderFinalResponse:
        return ProviderFinalResponse(message=message)

    @staticmethod
    def error(message: str, *, code: str = "provider_error") -> ProviderErrorStep:
        return ProviderErrorStep(message=message, code=code)

    @staticmethod
    def never() -> ProviderNeverStep:
        return ProviderNeverStep()

    def stream(
        self,
        messages: Sequence[AnyMessage],
        *,
        tools: Sequence[JsonObject] = (),
    ) -> AsyncIterator[AnyProviderChunk]:
        self.requests = (*self.requests, tuple(messages))
        self.tool_requests = (*self.tool_requests, tuple(dict(tool) for tool in tools))
        script_index = min(self._request_count, len(self._scripts) - 1)
        self._request_count += 1
        return self._stream_script(self._scripts[script_index])

    async def _stream_script(
        self,
        script: Sequence[AnyProviderChunk | ProviderErrorStep | ProviderNeverStep],
    ) -> AsyncIterator[AnyProviderChunk]:
        for item in script:
            if self._step_delay:
                await asyncio.sleep(self._step_delay)
            else:
                await asyncio.sleep(0)
            if isinstance(item, ProviderErrorStep):
                raise ProviderError(item.message, code=item.code)
            if isinstance(item, ProviderNeverStep):
                await asyncio.Event().wait()
                continue
            yield item

    @staticmethod
    def _coerce_script_item(item: ProviderScriptItem) -> AnyProviderChunk | ProviderErrorStep | ProviderNeverStep:
        if isinstance(item, (ProviderTextDelta, ProviderToolCall, ProviderFinalResponse, ProviderErrorStep, ProviderNeverStep)):
            return item
        return _script_item_from_dict(item)
