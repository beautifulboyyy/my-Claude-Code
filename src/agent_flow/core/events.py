"""Serializable event stream models for Agent Flow core."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar, Literal, cast

from agent_flow.core.messages import (
    AnyMessage,
    ToolCall,
    ToolResult,
    _json_object,
    _optional_str,
    _require_str,
    message_from_dict,
)
from agent_flow.core.types import JsonObject

RunStatus = Literal["completed", "failed", "cancelled"]


def _optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"Expected {key!r} to be an integer or null")
    return value


def _require_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Expected {key!r} to be an integer")
    return value


def _optional_bool(payload: Mapping[str, object], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Expected {key!r} to be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class Event:
    """Base fields shared by every event emitted by the core."""

    id: str
    run_id: str
    turn_id: str | None = None
    sequence: int | None = None
    timestamp: str | None = None
    type: ClassVar[str]

    def _base_dict(self) -> JsonObject:
        payload: JsonObject = {
            "type": self.type,
            "id": self.id,
            "run_id": self.run_id,
        }
        if self.turn_id is not None:
            payload["turn_id"] = self.turn_id
        if self.sequence is not None:
            payload["sequence"] = self.sequence
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        return payload

    def to_dict(self) -> JsonObject:
        return self._base_dict()


@dataclass(frozen=True, slots=True)
class RunStartedEvent(Event):
    type: ClassVar[Literal["run.started"]] = "run.started"


@dataclass(frozen=True, slots=True)
class RunFinishedEvent(Event):
    type: ClassVar[Literal["run.finished"]] = "run.finished"
    status: RunStatus = "completed"

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["status"] = self.status
        return payload


@dataclass(frozen=True, slots=True)
class RunFailedEvent(Event):
    type: ClassVar[Literal["run.failed"]] = "run.failed"
    message: str = ""
    code: str | None = None

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["message"] = self.message
        if self.code is not None:
            payload["code"] = self.code
        return payload


@dataclass(frozen=True, slots=True)
class RunCancelledEvent(Event):
    type: ClassVar[Literal["run.cancelled"]] = "run.cancelled"
    message: str = ""
    code: str | None = None

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["message"] = self.message
        if self.code is not None:
            payload["code"] = self.code
        return payload


@dataclass(frozen=True, slots=True)
class TurnStartedEvent(Event):
    type: ClassVar[Literal["turn.started"]] = "turn.started"
    index: int = 0

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["index"] = self.index
        return payload


@dataclass(frozen=True, slots=True)
class TurnFinishedEvent(Event):
    type: ClassVar[Literal["turn.finished"]] = "turn.finished"
    index: int = 0

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["index"] = self.index
        return payload


@dataclass(frozen=True, slots=True)
class MessageCreatedEvent(Event):
    type: ClassVar[Literal["message.created"]] = "message.created"
    message: AnyMessage = field(default_factory=lambda: message_from_dict({"id": "", "role": "user", "content": ""}))

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["message"] = self.message.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class MessageDeltaEvent(Event):
    type: ClassVar[Literal["message.delta"]] = "message.delta"
    message_id: str = ""
    delta: str = ""

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["message_id"] = self.message_id
        payload["delta"] = self.delta
        return payload


@dataclass(frozen=True, slots=True)
class ToolCallStartedEvent(Event):
    type: ClassVar[Literal["tool.call.started"]] = "tool.call.started"
    tool_call: ToolCall = field(default_factory=lambda: ToolCall(id="", name=""))

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["tool_call"] = self.tool_call.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ToolCallFinishedEvent(Event):
    type: ClassVar[Literal["tool.call.finished"]] = "tool.call.finished"
    result: ToolResult = field(default_factory=lambda: ToolResult(tool_call_id="", name="", content=""))

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["result"] = self.result.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ErrorEvent(Event):
    type: ClassVar[Literal["error"]] = "error"
    message: str = ""
    code: str | None = None
    recoverable: bool = True
    details: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        payload = self._base_dict()
        payload["message"] = self.message
        payload["recoverable"] = self.recoverable
        if self.code is not None:
            payload["code"] = self.code
        if self.details:
            payload["details"] = self.details
        return payload


AnyEvent = (
    RunStartedEvent
    | RunFinishedEvent
    | RunFailedEvent
    | RunCancelledEvent
    | TurnStartedEvent
    | TurnFinishedEvent
    | MessageCreatedEvent
    | MessageDeltaEvent
    | ToolCallStartedEvent
    | ToolCallFinishedEvent
    | ErrorEvent
)


def _event_base(payload: Mapping[str, object]) -> tuple[str, str, str | None, int | None, str | None]:
    return (
        _require_str(payload, "id"),
        _require_str(payload, "run_id"),
        _optional_str(payload, "turn_id"),
        _optional_int(payload, "sequence"),
        _optional_str(payload, "timestamp"),
    )


def _run_status(payload: Mapping[str, object]) -> RunStatus:
    status = _require_str(payload, "status")
    if status not in {"completed", "failed", "cancelled"}:
        raise ValueError(f"Unknown run status: {status}")
    return cast(RunStatus, status)


def event_from_dict(payload: Mapping[str, object]) -> AnyEvent:
    event_type = _require_str(payload, "type")
    event_id, run_id, turn_id, sequence, timestamp = _event_base(payload)

    if event_type == "run.started":
        return RunStartedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
        )
    if event_type == "run.finished":
        return RunFinishedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            status=_run_status(payload),
        )
    if event_type == "run.failed":
        return RunFailedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            message=_require_str(payload, "message"),
            code=_optional_str(payload, "code"),
        )
    if event_type == "run.cancelled":
        return RunCancelledEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            message=_require_str(payload, "message"),
            code=_optional_str(payload, "code"),
        )
    if event_type == "turn.started":
        return TurnStartedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            index=_require_int(payload, "index"),
        )
    if event_type == "turn.finished":
        return TurnFinishedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            index=_require_int(payload, "index"),
        )
    if event_type == "message.created":
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Expected 'message' to be an object")
        return MessageCreatedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            message=message_from_dict(message),
        )
    if event_type == "message.delta":
        return MessageDeltaEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            message_id=_require_str(payload, "message_id"),
            delta=_require_str(payload, "delta"),
        )
    if event_type == "tool.call.started":
        tool_call = payload.get("tool_call")
        if not isinstance(tool_call, dict):
            raise ValueError("Expected 'tool_call' to be an object")
        return ToolCallStartedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            tool_call=ToolCall.from_dict(tool_call),
        )
    if event_type == "tool.call.finished":
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Expected 'result' to be an object")
        return ToolCallFinishedEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            result=ToolResult.from_dict(result),
        )
    if event_type == "error":
        return ErrorEvent(
            id=event_id,
            run_id=run_id,
            turn_id=turn_id,
            sequence=sequence,
            timestamp=timestamp,
            message=_require_str(payload, "message"),
            code=_optional_str(payload, "code"),
            recoverable=_optional_bool(payload, "recoverable", True),
            details=_json_object(payload.get("details"), "details"),
        )
    raise ValueError(f"Unknown event type: {event_type}")
