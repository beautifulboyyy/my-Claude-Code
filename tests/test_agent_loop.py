import asyncio

from agent_flow.core import (
    AgentLoop,
    AssistantMessage,
    ErrorEvent,
    FakeProvider,
    MessageCreatedEvent,
    MessageDeltaEvent,
    RunCancelledEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunStartedEvent,
    Tool,
    ToolCall,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    ToolMessage,
    ToolRegistry,
    UserMessage,
)


def test_agent_loop_runs_tool_call_and_continues_with_tool_result() -> None:
    tool_call = ToolCall(id="call_1", name="lookup", arguments={"key": "answer"})
    provider = FakeProvider.turns(
        [
            [FakeProvider.text("Let me check."), FakeProvider.tool_call(tool_call)],
            [FakeProvider.text(" The answer is 42."), FakeProvider.final(AssistantMessage(id="msg_final", content="The answer is 42."))],
        ]
    )
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="lookup",
            description="Look up a value.",
            input_schema={"type": "object", "properties": {"key": {"type": "string"}}},
            handler=lambda arguments: f"{arguments['key']}=42",
        )
    )
    loop = AgentLoop(provider=provider, tools=registry, run_id="run_test")

    events = asyncio.run(_collect(loop.run("What is the answer?")))

    assert [event.type for event in events] == [
        "run.started",
        "message.created",
        "turn.started",
        "message.created",
        "message.delta",
        "tool.call.started",
        "tool.call.finished",
        "turn.finished",
        "turn.started",
        "message.created",
        "message.delta",
        "turn.finished",
        "run.finished",
    ]
    assert isinstance(events[0], RunStartedEvent)
    assert events[0].run_id == "run_test"
    assert isinstance(events[1], MessageCreatedEvent)
    assert events[1].message == UserMessage(id="msg_user_1", content="What is the answer?")
    assert isinstance(events[4], MessageDeltaEvent)
    assert events[4].delta == "Let me check."
    assert isinstance(events[5], ToolCallStartedEvent)
    assert events[5].tool_call == tool_call
    assert isinstance(events[6], ToolCallFinishedEvent)
    assert events[6].result.content == "answer=42"
    assert isinstance(events[-1], RunFinishedEvent)
    assert events[-1].status == "completed"

    assert len(provider.requests) == 2
    assert provider.requests[0] == (UserMessage(id="msg_user_1", content="What is the answer?"),)
    assert provider.requests[1][-1] == ToolMessage(id="msg_tool_1", content="answer=42", tool_call_id="call_1")
    assert provider.tool_requests[0] == (
        {
            "name": "lookup",
            "description": "Look up a value.",
            "input_schema": {"type": "object", "properties": {"key": {"type": "string"}}},
        },
    )


def test_provider_that_never_finishes_times_out_with_failed_terminal_event() -> None:
    provider = FakeProvider([FakeProvider.text("partial"), FakeProvider.never()])
    loop = AgentLoop(
        provider=provider,
        tools=ToolRegistry(),
        run_id="run_timeout",
        provider_timeout=0.01,
    )

    events = asyncio.run(_collect(loop.run("hang?")))

    assert [event.type for event in events] == [
        "run.started",
        "message.created",
        "turn.started",
        "message.created",
        "message.delta",
        "error",
        "run.failed",
    ]
    assert isinstance(events[-2], ErrorEvent)
    assert events[-2].code == "provider_timeout"
    assert isinstance(events[-1], RunFailedEvent)
    assert events[-1].code == "provider_timeout"


def test_provider_ordinary_exception_fails_run_without_hanging() -> None:
    class ExplodingProvider:
        async def stream(self, messages: object, *, tools: object = ()) -> object:
            raise RuntimeError("plain boom")
            yield  # pragma: no cover

    loop = AgentLoop(provider=ExplodingProvider(), tools=ToolRegistry(), run_id="run_provider_error")

    events = asyncio.run(_collect(loop.run("explode")))

    assert isinstance(events[-2], ErrorEvent)
    assert events[-2].code == "provider_error"
    assert "plain boom" in events[-2].message
    assert isinstance(events[-1], RunFailedEvent)
    assert events[-1].code == "provider_error"


def test_tool_that_never_returns_times_out_with_failed_terminal_event() -> None:
    tool_call = ToolCall(id="call_1", name="slow")
    provider = FakeProvider([FakeProvider.tool_call(tool_call)])

    async def slow(arguments: dict[str, object]) -> str:
        await asyncio.Event().wait()
        return "unreachable"

    registry = ToolRegistry()
    registry.register(Tool(name="slow", description="Never returns.", input_schema={"type": "object"}, handler=slow))
    loop = AgentLoop(provider=provider, tools=registry, run_id="run_tool_timeout", tool_timeout=0.01)

    events = asyncio.run(_collect(loop.run("call slow")))

    assert [event.type for event in events] == [
        "run.started",
        "message.created",
        "turn.started",
        "tool.call.started",
        "error",
        "run.failed",
    ]
    assert isinstance(events[-2], ErrorEvent)
    assert events[-2].code == "tool_timeout"
    assert isinstance(events[-1], RunFailedEvent)
    assert events[-1].code == "tool_timeout"


def test_tool_exception_is_returned_to_provider_as_error_result() -> None:
    tool_call = ToolCall(id="call_1", name="explode")
    provider = FakeProvider.turns(
        [
            [FakeProvider.tool_call(tool_call)],
            [FakeProvider.final(AssistantMessage(id="msg_final", content="handled"))],
        ]
    )

    def explode(arguments: dict[str, object]) -> str:
        raise RuntimeError("tool boom")

    registry = ToolRegistry()
    registry.register(Tool(name="explode", description="Raises.", input_schema={"type": "object"}, handler=explode))
    loop = AgentLoop(provider=provider, tools=registry, run_id="run_tool_error")

    events = asyncio.run(_collect(loop.run("call explode")))

    tool_finished = next(event for event in events if isinstance(event, ToolCallFinishedEvent))
    assert tool_finished.result.is_error is True
    assert tool_finished.result.metadata["code"] == "tool_error"
    assert isinstance(events[-1], RunFinishedEvent)
    assert events[-1].status == "completed"


def test_run_can_be_cancelled_with_external_event() -> None:
    provider = FakeProvider([FakeProvider.never()])

    async def collect_with_cancel() -> list[object]:
        cancel_event = asyncio.Event()
        loop = AgentLoop(provider=provider, tools=ToolRegistry(), run_id="run_cancelled", provider_timeout=10)

        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            cancel_event.set()

        cancel_task = asyncio.create_task(cancel_soon())
        events = [event async for event in loop.run("cancel me", cancel_event=cancel_event)]
        await cancel_task
        return events

    events = asyncio.run(collect_with_cancel())

    assert isinstance(events[-2], ErrorEvent)
    assert events[-2].code == "run_cancelled"
    assert isinstance(events[-1], RunCancelledEvent)
    assert events[-1].code == "run_cancelled"


async def _collect(events: object) -> list[object]:
    return [event async for event in events]
