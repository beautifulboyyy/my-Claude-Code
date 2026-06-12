import json

from agent_flow.core import (
    AssistantMessage,
    ErrorEvent,
    MessageCreatedEvent,
    RunCancelledEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunStartedEvent,
    ToolCall,
    ToolCallStartedEvent,
    ToolMessage,
    ToolResult,
    TurnStartedEvent,
    UserMessage,
    event_from_dict,
    message_from_dict,
)


def test_message_with_tool_call_round_trips_through_json() -> None:
    message = AssistantMessage(
        id="msg_1",
        content="I will inspect the file.",
        tool_calls=(
            ToolCall(
                id="call_1",
                name="read_file",
                arguments={"path": "src/agent_flow/__init__.py"},
            ),
        ),
    )

    payload = json.loads(json.dumps(message.to_dict()))
    restored = message_from_dict(payload)

    assert restored == message


def test_tool_result_and_tool_message_round_trip_through_json() -> None:
    result = ToolResult(
        tool_call_id="call_1",
        name="read_file",
        content='{"ok": true}',
        is_error=False,
        metadata={"duration_ms": 12},
    )
    message = ToolMessage(id="msg_tool_1", content=result.content, tool_call_id=result.tool_call_id)

    result_payload = json.loads(json.dumps(result.to_dict()))
    message_payload = json.loads(json.dumps(message.to_dict()))

    assert ToolResult.from_dict(result_payload) == result
    assert message_from_dict(message_payload) == message


def test_run_turn_message_tool_and_error_events_round_trip() -> None:
    events = [
        RunStartedEvent(id="evt_1", run_id="run_1"),
        TurnStartedEvent(id="evt_2", run_id="run_1", turn_id="turn_1", index=0),
        MessageCreatedEvent(
            id="evt_3",
            run_id="run_1",
            turn_id="turn_1",
            message=UserMessage(id="msg_1", content="hello"),
        ),
        ToolCallStartedEvent(
            id="evt_4",
            run_id="run_1",
            turn_id="turn_1",
            tool_call=ToolCall(id="call_1", name="read_file", arguments={"path": "README.md"}),
        ),
        ErrorEvent(
            id="evt_5",
            run_id="run_1",
            message="provider failed",
            code="provider_error",
            recoverable=False,
        ),
        RunFailedEvent(id="evt_6", run_id="run_1", message="provider failed", code="provider_error"),
        RunCancelledEvent(id="evt_7", run_id="run_1", message="cancelled", code="run_cancelled"),
        RunFinishedEvent(id="evt_8", run_id="run_1", status="completed"),
    ]

    for event in events:
        payload = json.loads(json.dumps(event.to_dict()))
        assert event_from_dict(payload) == event


def test_unknown_event_type_is_rejected() -> None:
    payload = {"type": "something.unexpected", "id": "evt_1", "run_id": "run_1"}

    try:
        event_from_dict(payload)
    except ValueError as exc:
        assert "Unknown event type" in str(exc)
    else:
        raise AssertionError("event_from_dict should reject unknown event types")
