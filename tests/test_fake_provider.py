import asyncio
import json

import pytest

from agent_flow.core import AssistantMessage, ToolCall, UserMessage
from agent_flow.core.providers import (
    FakeProvider,
    ProviderError,
    ProviderFinalResponse,
    ProviderTextDelta,
    ProviderToolCall,
    provider_chunk_from_dict,
)


async def _collect(provider: FakeProvider) -> list[object]:
    return [chunk async for chunk in provider.stream([UserMessage(id="msg_user_1", content="hello")])]


def test_fake_provider_streams_text_deltas() -> None:
    provider = FakeProvider([FakeProvider.text("hel"), FakeProvider.text("lo")])

    chunks = asyncio.run(_collect(provider))

    assert chunks == [ProviderTextDelta(delta="hel"), ProviderTextDelta(delta="lo")]
    assert provider.requests == ((UserMessage(id="msg_user_1", content="hello"),),)


def test_fake_provider_streams_tool_call() -> None:
    tool_call = ToolCall(id="call_1", name="read_file", arguments={"path": "README.md"})
    provider = FakeProvider([FakeProvider.tool_call(tool_call)])

    chunks = asyncio.run(_collect(provider))

    assert chunks == [ProviderToolCall(tool_call=tool_call)]


def test_fake_provider_streams_final_response() -> None:
    message = AssistantMessage(id="msg_assistant_1", content="done")
    provider = FakeProvider([FakeProvider.final(message)])

    chunks = asyncio.run(_collect(provider))

    assert chunks == [ProviderFinalResponse(message=message)]


def test_fake_provider_raises_scripted_error() -> None:
    provider = FakeProvider([FakeProvider.text("before"), FakeProvider.error("boom", code="fake_boom")])

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(_collect(provider))

    assert str(exc_info.value) == "boom"
    assert exc_info.value.code == "fake_boom"


def test_provider_chunks_round_trip_through_json() -> None:
    chunks = [
        ProviderTextDelta(delta="hello"),
        ProviderToolCall(tool_call=ToolCall(id="call_1", name="grep", arguments={"pattern": "TODO"})),
        ProviderFinalResponse(
            message=AssistantMessage(
                id="msg_1",
                content="I need a tool.",
                tool_calls=(ToolCall(id="call_2", name="read_file", arguments={"path": "pyproject.toml"}),),
            )
        ),
    ]

    for chunk in chunks:
        payload = json.loads(json.dumps(chunk.to_dict()))
        assert provider_chunk_from_dict(payload) == chunk


def test_fake_provider_accepts_json_script_items_and_message_dicts() -> None:
    provider = FakeProvider(
        [
            {"type": "text_delta", "delta": "hi"},
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "write_file", "arguments": {"path": "out.txt", "content": "hi"}},
            },
            {"type": "final_response", "message": {"id": "msg_1", "role": "assistant", "content": "ok"}},
        ]
    )

    chunks = asyncio.run(_collect(provider))

    assert chunks == [
        ProviderTextDelta(delta="hi"),
        ProviderToolCall(
            tool_call=ToolCall(id="call_1", name="write_file", arguments={"path": "out.txt", "content": "hi"})
        ),
        ProviderFinalResponse(message=AssistantMessage(id="msg_1", content="ok")),
    ]
