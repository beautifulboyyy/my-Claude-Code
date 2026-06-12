import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from agent_flow.core import AssistantMessage, ProviderFinalResponse, ProviderTextDelta, ProviderToolCall, ToolCall
from agent_flow.core.messages import SystemMessage, ToolMessage, UserMessage
from agent_flow.core.providers import MiMoProvider, ProviderError


def test_mimo_provider_posts_openai_compatible_payload_and_streams_text() -> None:
    seen: dict[str, object] = {}

    def post_json(url: str, payload: Mapping[str, object], headers: Mapping[str, str], timeout: float) -> Mapping[str, object]:
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = headers
        seen["timeout"] = timeout
        return {
            "id": "chatcmpl_1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "hello",
                    }
                }
            ],
        }

    provider = MiMoProvider(api_key="test_key", model="mimo-test", post_json=post_json)

    chunks = asyncio.run(
        _collect(
            provider.stream(
                [
                    SystemMessage(id="msg_system_1", content="be brief"),
                    UserMessage(id="msg_user_1", content="hi"),
                    AssistantMessage(
                        id="msg_assistant_1",
                        content="calling",
                        tool_calls=(ToolCall(id="call_1", name="lookup", arguments={"key": "answer"}),),
                    ),
                    ToolMessage(id="msg_tool_1", content="42", tool_call_id="call_1"),
                ],
                tools=[
                    {
                        "name": "lookup",
                        "description": "Look up a value.",
                        "input_schema": {"type": "object", "properties": {"key": {"type": "string"}}},
                    }
                ],
            )
        )
    )

    assert chunks == [
        ProviderTextDelta(delta="hello"),
        ProviderFinalResponse(message=AssistantMessage(id="chatcmpl_1", content="hello")),
    ]
    assert seen["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert seen["headers"] == {
        "Authorization": "Bearer test_key",
        "Content-Type": "application/json",
    }
    assert seen["timeout"] == 60.0
    assert seen["payload"] == {
        "model": "mimo-test",
        "messages": [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "calling",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": json.dumps({"key": "answer"})},
                    }
                ],
            },
            {"role": "tool", "content": "42", "tool_call_id": "call_1"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Look up a value.",
                    "parameters": {"type": "object", "properties": {"key": {"type": "string"}}},
                },
            }
        ],
        "stream": False,
    }


def test_mimo_provider_converts_tool_calls_without_final_response() -> None:
    def post_json(url: str, payload: Mapping[str, object], headers: Mapping[str, str], timeout: float) -> Mapping[str, object]:
        return {
            "id": "chatcmpl_2",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{\"key\":\"answer\"}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

    provider = MiMoProvider(api_key="test_key", post_json=post_json)

    chunks = asyncio.run(_collect(provider.stream([UserMessage(id="msg_user_1", content="use a tool")])))

    assert chunks == [ProviderToolCall(tool_call=ToolCall(id="call_2", name="lookup", arguments={"key": "answer"}))]


def test_mimo_provider_wraps_http_errors_as_provider_errors() -> None:
    def post_json(url: str, payload: Mapping[str, object], headers: Mapping[str, str], timeout: float) -> Mapping[str, object]:
        raise ProviderError("MiMo API request failed: 401 Unauthorized", code="mimo_http_error")

    provider = MiMoProvider(api_key="test_key", post_json=post_json)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(_collect(provider.stream([UserMessage(id="msg_user_1", content="hi")])))

    assert exc_info.value.code == "mimo_http_error"


def test_mimo_provider_can_read_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIMO_API_KEY", "env_key")

    provider = MiMoProvider.from_default_config()

    assert provider.api_key_source == "environment"


def test_mimo_provider_can_read_api_key_from_user_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"mimo_api_key": "config_key", "mimo_model": "mimo-custom"}), encoding="utf-8")

    provider = MiMoProvider.from_default_config(config_path=config_path)

    assert provider.api_key_source == "user_config"
    assert provider.model == "mimo-custom"


def test_mimo_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    with pytest.raises(ProviderError) as exc_info:
        MiMoProvider.from_default_config(config_path=tmp_path / "missing.json")

    assert exc_info.value.code == "mimo_api_key_missing"


@pytest.mark.skipif("MIMO_API_KEY" not in os.environ, reason="MIMO_API_KEY is not set")
def test_mimo_provider_real_api_smoke() -> None:
    provider = MiMoProvider.from_default_config()

    chunks = asyncio.run(_collect(provider.stream([UserMessage(id="msg_user_1", content="Reply with exactly: pong")])))

    assert chunks


async def _collect(stream: object) -> list[object]:
    return [chunk async for chunk in stream]
