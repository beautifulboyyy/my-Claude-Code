"""Serializable message, tool call, and tool result models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Self

from agent_flow.core.types import JsonObject, JsonValue

MessageRole = Literal["system", "user", "assistant", "tool"]


def _require_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected {key!r} to be a string")
    return value


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected {key!r} to be a string or null")
    return value


def _json_object(value: object, key: str) -> JsonObject:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected {key!r} to be an object")
    return dict(value)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model-requested tool invocation."""

    id: str
    name: str
    arguments: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            id=_require_str(payload, "id"),
            name=_require_str(payload, "name"),
            arguments=_json_object(payload.get("arguments"), "arguments"),
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A tool execution result ready to feed back into the agent loop."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": self.content,
            "is_error": self.is_error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        is_error = payload.get("is_error", False)
        if not isinstance(is_error, bool):
            raise ValueError("Expected 'is_error' to be a boolean")
        return cls(
            tool_call_id=_require_str(payload, "tool_call_id"),
            name=_require_str(payload, "name"),
            content=_require_str(payload, "content"),
            is_error=is_error,
            metadata=_json_object(payload.get("metadata"), "metadata"),
        )


@dataclass(frozen=True, slots=True)
class Message:
    """A chat message in the serializable run transcript."""

    id: str
    content: str
    role: ClassVar[MessageRole]

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class SystemMessage(Message):
    role: ClassVar[Literal["system"]] = "system"


@dataclass(frozen=True, slots=True)
class UserMessage(Message):
    role: ClassVar[Literal["user"]] = "user"


@dataclass(frozen=True, slots=True)
class AssistantMessage(Message):
    role: ClassVar[Literal["assistant"]] = "assistant"
    tool_calls: tuple[ToolCall, ...] = ()

    def to_dict(self) -> JsonObject:
        payload = Message.to_dict(self)
        payload["tool_calls"] = [tool_call.to_dict() for tool_call in self.tool_calls]
        return payload


@dataclass(frozen=True, slots=True)
class ToolMessage(Message):
    role: ClassVar[Literal["tool"]] = "tool"
    tool_call_id: str

    def to_dict(self) -> JsonObject:
        payload = Message.to_dict(self)
        payload["tool_call_id"] = self.tool_call_id
        return payload


AnyMessage = SystemMessage | UserMessage | AssistantMessage | ToolMessage


def message_from_dict(payload: Mapping[str, object]) -> AnyMessage:
    role = _require_str(payload, "role")
    common: dict[str, Any] = {
        "id": _require_str(payload, "id"),
        "content": _require_str(payload, "content"),
    }

    if role == "system":
        return SystemMessage(**common)
    if role == "user":
        return UserMessage(**common)
    if role == "assistant":
        raw_tool_calls = payload.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raise ValueError("Expected 'tool_calls' to be a list")
        return AssistantMessage(
            **common,
            tool_calls=tuple(ToolCall.from_dict(tool_call) for tool_call in raw_tool_calls),
        )
    if role == "tool":
        return ToolMessage(**common, tool_call_id=_require_str(payload, "tool_call_id"))
    raise ValueError(f"Unknown message role: {role}")


def ensure_json_object(value: Mapping[str, JsonValue]) -> JsonObject:
    return dict(value)
