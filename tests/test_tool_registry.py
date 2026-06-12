import asyncio

from agent_flow.core import Tool, ToolCall, ToolRegistry, ToolResult


def test_registry_registers_lists_schema_and_executes_sync_tool() -> None:
    def greet(arguments: dict[str, object]) -> str:
        return f"hello {arguments['name']}"

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="greet",
            description="Greet a person.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=greet,
        )
    )

    assert registry.get("greet").description == "Greet a person."
    assert [tool.name for tool in registry.list_tools()] == ["greet"]
    assert registry.list_schemas() == [
        {
            "name": "greet",
            "description": "Greet a person.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }
    ]

    result = asyncio.run(registry.execute(ToolCall(id="call_1", name="greet", arguments={"name": "Ada"})))

    assert result == ToolResult(tool_call_id="call_1", name="greet", content="hello Ada")


def test_registry_executes_async_tool_returning_tool_result() -> None:
    async def remember(arguments: dict[str, object]) -> ToolResult:
        return ToolResult(
            tool_call_id="custom",
            name="remember",
            content=str(arguments["value"]),
            metadata={"source": "memory"},
        )

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="remember",
            description="Remember a value.",
            input_schema={"type": "object"},
            handler=remember,
        )
    )

    result = asyncio.run(registry.execute(ToolCall(id="call_1", name="remember", arguments={"value": 42})))

    assert result == ToolResult(
        tool_call_id="call_1",
        name="remember",
        content="42",
        metadata={"source": "memory"},
    )


def test_disabled_tool_is_hidden_from_active_lists_and_not_executable() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="Echo input.",
            input_schema={"type": "object"},
            handler=lambda arguments: str(arguments),
            enabled=False,
        )
    )

    assert registry.list_tools() == []
    assert registry.list_schemas() == []

    disabled_result = asyncio.run(registry.execute(ToolCall(id="call_1", name="echo", arguments={})))
    assert disabled_result.is_error is True
    assert disabled_result.metadata["code"] == "tool_disabled"

    registry.enable("echo")
    assert [tool.name for tool in registry.list_tools()] == ["echo"]

    registry.disable("echo")
    assert registry.list_tools() == []


def test_unknown_tool_returns_clear_error_result() -> None:
    registry = ToolRegistry()

    result = asyncio.run(registry.execute(ToolCall(id="call_1", name="missing", arguments={})))

    assert result == ToolResult(
        tool_call_id="call_1",
        name="missing",
        content="Tool 'missing' is not registered.",
        is_error=True,
        metadata={"code": "tool_not_found"},
    )


def test_tool_exception_becomes_error_result() -> None:
    def explode(arguments: dict[str, object]) -> str:
        raise RuntimeError("boom")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="explode",
            description="Raise an error.",
            input_schema={"type": "object"},
            handler=explode,
        )
    )

    result = asyncio.run(registry.execute(ToolCall(id="call_1", name="explode", arguments={})))

    assert result.tool_call_id == "call_1"
    assert result.name == "explode"
    assert result.content == "Tool 'explode' failed: boom"
    assert result.is_error is True
    assert result.metadata == {"code": "tool_error", "error_type": "RuntimeError"}
