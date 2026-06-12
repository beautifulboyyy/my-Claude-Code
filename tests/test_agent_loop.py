import asyncio

from agent_flow.core import (
    AgentLoop,
    AssistantMessage,
    FakeProvider,
    MessageCreatedEvent,
    MessageDeltaEvent,
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


async def _collect(events: object) -> list[object]:
    return [event async for event in events]
