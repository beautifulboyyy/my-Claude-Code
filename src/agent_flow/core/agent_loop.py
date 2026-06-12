"""Minimal single-agent runtime loop."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from agent_flow.core.events import (
    AnyEvent,
    ErrorEvent,
    MessageCreatedEvent,
    MessageDeltaEvent,
    RunFinishedEvent,
    RunStartedEvent,
    RunStatus,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    TurnFinishedEvent,
    TurnStartedEvent,
)
from agent_flow.core.messages import AnyMessage, AssistantMessage, SystemMessage, ToolCall, ToolMessage, ToolResult, UserMessage
from agent_flow.core.providers import LLMProvider, ProviderError, ProviderFinalResponse, ProviderTextDelta, ProviderToolCall
from agent_flow.core.tools import ToolRegistry


@dataclass(slots=True)
class AgentLoop:
    """Run one user request through provider turns and tool-call feedback."""

    provider: LLMProvider
    tools: ToolRegistry
    run_id: str = "run_1"
    max_turns: int = 16

    async def run(
        self,
        user_input: str,
        *,
        system_messages: Sequence[SystemMessage] = (),
    ) -> AsyncIterator[AnyEvent]:
        event_builder = _EventBuilder(self.run_id)
        messages: list[AnyMessage] = list(system_messages)
        messages.append(UserMessage(id="msg_user_1", content=user_input))

        yield event_builder.run_started()
        yield event_builder.message_created(messages[-1])

        for turn_index in range(self.max_turns):
            turn_id = f"turn_{turn_index + 1}"
            yield event_builder.turn_started(turn_id, turn_index)

            turn = _ProviderTurn(turn_id=turn_id, assistant_message_id=f"msg_assistant_{turn_index + 1}")
            try:
                async for chunk in self.provider.stream(messages, tools=self.tools.list_schemas()):
                    if isinstance(chunk, ProviderTextDelta):
                        for event in turn.accept_text_delta(chunk.delta, event_builder):
                            yield event
                    elif isinstance(chunk, ProviderToolCall):
                        turn.tool_calls.append(chunk.tool_call)
                        yield event_builder.tool_call_started(turn_id, chunk.tool_call)
                    elif isinstance(chunk, ProviderFinalResponse):
                        final_message = chunk.message
                        if not turn.message_created:
                            yield event_builder.message_created(final_message, turn_id=turn_id)
                        messages.append(final_message)
                        yield event_builder.turn_finished(turn_id, turn_index)
                        yield event_builder.run_finished()
                        return
            except ProviderError as exc:
                yield event_builder.error(str(exc), code=exc.code, recoverable=False, turn_id=turn_id)
                yield event_builder.run_finished(status="failed")
                return

            if turn.tool_calls:
                messages.append(turn.to_assistant_message())
                for tool_call in turn.tool_calls:
                    result = await self.tools.execute(tool_call)
                    yield event_builder.tool_call_finished(turn_id, result)
                    messages.append(
                        ToolMessage(
                            id=f"msg_tool_{len([message for message in messages if isinstance(message, ToolMessage)]) + 1}",
                            content=result.content,
                            tool_call_id=result.tool_call_id,
                        )
                    )
                yield event_builder.turn_finished(turn_id, turn_index)
                continue

            yield event_builder.turn_finished(turn_id, turn_index)
            yield event_builder.run_finished()
            return

        yield event_builder.error("Agent loop exceeded max_turns.", code="max_turns_exceeded", recoverable=False)
        yield event_builder.run_finished(status="failed")


@dataclass(slots=True)
class _ProviderTurn:
    turn_id: str
    assistant_message_id: str
    content: str = ""
    message_created: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)

    def accept_text_delta(self, delta: str, event_builder: "_EventBuilder") -> list[AnyEvent]:
        events: list[AnyEvent] = []
        if not self.message_created:
            events.append(
                event_builder.message_created(
                    AssistantMessage(id=self.assistant_message_id, content=""),
                    turn_id=self.turn_id,
                )
            )
            self.message_created = True
        self.content += delta
        events.append(event_builder.message_delta(self.turn_id, self.assistant_message_id, delta))
        return events

    def to_assistant_message(self) -> AssistantMessage:
        return AssistantMessage(
            id=self.assistant_message_id,
            content=self.content,
            tool_calls=tuple(self.tool_calls),
        )


class _EventBuilder:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._sequence = 0

    def run_started(self) -> RunStartedEvent:
        return RunStartedEvent(id=self._next_id(), run_id=self._run_id, sequence=self._sequence)

    def run_finished(self, *, status: RunStatus = "completed") -> RunFinishedEvent:
        return RunFinishedEvent(id=self._next_id(), run_id=self._run_id, sequence=self._sequence, status=status)

    def turn_started(self, turn_id: str, index: int) -> TurnStartedEvent:
        return TurnStartedEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            index=index,
        )

    def turn_finished(self, turn_id: str, index: int) -> TurnFinishedEvent:
        return TurnFinishedEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            index=index,
        )

    def message_created(self, message: AnyMessage, *, turn_id: str | None = None) -> MessageCreatedEvent:
        return MessageCreatedEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            message=message,
        )

    def message_delta(self, turn_id: str, message_id: str, delta: str) -> MessageDeltaEvent:
        return MessageDeltaEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            message_id=message_id,
            delta=delta,
        )

    def tool_call_started(self, turn_id: str, tool_call: ToolCall) -> ToolCallStartedEvent:
        return ToolCallStartedEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            tool_call=tool_call,
        )

    def tool_call_finished(self, turn_id: str, result: ToolResult) -> ToolCallFinishedEvent:
        return ToolCallFinishedEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            result=result,
        )

    def error(
        self,
        message: str,
        *,
        code: str,
        recoverable: bool,
        turn_id: str | None = None,
    ) -> ErrorEvent:
        return ErrorEvent(
            id=self._next_id(),
            run_id=self._run_id,
            turn_id=turn_id,
            sequence=self._sequence,
            message=message,
            code=code,
            recoverable=recoverable,
        )

    def _next_id(self) -> str:
        self._sequence += 1
        return f"evt_{self._sequence}"
