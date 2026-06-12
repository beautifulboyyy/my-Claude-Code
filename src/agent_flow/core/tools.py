"""Tool registration and execution primitives."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias, cast

from agent_flow.core.messages import ToolCall, ToolResult
from agent_flow.core.types import JsonObject, JsonValue

ToolHandlerResult: TypeAlias = str | ToolResult
ToolHandler: TypeAlias = Callable[[JsonObject], ToolHandlerResult | Awaitable[ToolHandlerResult]]


@dataclass(frozen=True, slots=True)
class Tool:
    """A callable tool exposed to an agent provider."""

    name: str
    description: str
    input_schema: JsonObject
    handler: ToolHandler
    enabled: bool = True

    def schema(self) -> JsonObject:
        """Return a provider-facing, JSON-serializable tool schema."""
        payload: JsonObject = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        _ensure_json_serializable(payload, f"tool schema for {self.name!r}")
        return payload

    def with_enabled(self, enabled: bool) -> "Tool":
        return Tool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            handler=self.handler,
            enabled=enabled,
        )


class ToolRegistry:
    """Registry for named tools and their execution dispatch."""

    def __init__(self, tools: Mapping[str, Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        if tools is not None:
            for tool in tools.values():
                self.register(tool)

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("Tool name must not be empty")
        _ensure_json_serializable(tool.input_schema, f"input_schema for {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool {name!r} is not registered") from exc

    def list_tools(self, *, active_only: bool = True) -> list[Tool]:
        return [
            tool
            for tool in self._tools.values()
            if not active_only or tool.enabled
        ]

    def list_schemas(self, *, active_only: bool = True) -> list[JsonObject]:
        return [tool.schema() for tool in self.list_tools(active_only=active_only)]

    def enable(self, name: str) -> None:
        self._set_enabled(name, True)

    def disable(self, name: str) -> None:
        self._set_enabled(name, False)

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Tool {tool_call.name!r} is not registered.",
                is_error=True,
                metadata={"code": "tool_not_found"},
            )
        if not tool.enabled:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Tool {tool_call.name!r} is disabled.",
                is_error=True,
                metadata={"code": "tool_disabled"},
            )

        try:
            raw_result = tool.handler(dict(tool_call.arguments))
            if inspect.isawaitable(raw_result):
                raw_result = await raw_result
            return self._coerce_result(tool_call, tool.name, raw_result)
        except Exception as exc:  # noqa: BLE001 - tool boundaries must convert failures into data.
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool.name,
                content=f"Tool {tool.name!r} failed: {exc}",
                is_error=True,
                metadata={"code": "tool_error", "error_type": type(exc).__name__},
            )

    def _set_enabled(self, name: str, enabled: bool) -> None:
        tool = self.get(name)
        self._tools[name] = tool.with_enabled(enabled)

    @staticmethod
    def _coerce_result(tool_call: ToolCall, tool_name: str, result: ToolHandlerResult) -> ToolResult:
        if isinstance(result, ToolResult):
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_name,
                content=result.content,
                is_error=result.is_error,
                metadata=result.metadata,
            )
        return ToolResult(tool_call_id=tool_call.id, name=tool_name, content=result)


def _ensure_json_serializable(value: Mapping[str, JsonValue], label: str) -> None:
    try:
        json.dumps(value)
    except TypeError as exc:
        raise ValueError(f"{label} must be JSON-serializable") from exc

    # Preserve the JsonObject alias at the boundary without leaking Mapping variance into callers.
    cast(JsonObject, value)
