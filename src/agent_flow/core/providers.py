"""LLM provider interface and deterministic fake provider."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, Self

from agent_flow.core.messages import AnyMessage, AssistantMessage, ToolCall, _require_str, message_from_dict
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
