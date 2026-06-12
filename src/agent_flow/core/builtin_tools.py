"""Built-in coding tools exposed through the core tool registry."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from agent_flow.core.messages import ToolResult
from agent_flow.core.tools import Tool, ToolRegistry
from agent_flow.core.types import JsonObject, JsonValue

DEFAULT_SHELL_TIMEOUT_SECONDS = 30.0
MAX_TEXT_BYTES = 1_000_000


def register_builtin_tools(registry: ToolRegistry, *, workspace: Path | str | None = None) -> None:
    """Register the built-in coding tools against a workspace root."""

    root = _workspace_root(workspace)
    for tool in builtin_tools(workspace=root):
        registry.register(tool)


def builtin_tools(*, workspace: Path | str | None = None) -> list[Tool]:
    """Return the built-in coding tools bound to a workspace root."""

    root = _workspace_root(workspace)
    return [
        Tool(
            name="read",
            description="Read a UTF-8 text file inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["path"],
            },
            handler=lambda arguments: _read(arguments, root),
        ),
        Tool(
            name="write",
            description="Write UTF-8 text to a file inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["path", "content"],
            },
            handler=lambda arguments: _write(arguments, root),
        ),
        Tool(
            name="edit",
            description="Replace one exact text occurrence in a workspace file.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["path", "old_text", "new_text"],
            },
            handler=lambda arguments: _edit(arguments, root),
        ),
        Tool(
            name="glob",
            description="List workspace paths matching a glob pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "default": 100},
                },
                "required": ["pattern"],
            },
            handler=lambda arguments: _glob(arguments, root),
        ),
        Tool(
            name="grep",
            description="Search text files inside the workspace for a literal pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "glob": {"type": "string", "default": "**/*"},
                    "case_sensitive": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "minimum": 1, "default": 100},
                },
                "required": ["pattern"],
            },
            handler=lambda arguments: _grep(arguments, root),
        ),
        Tool(
            name="shell",
            description="Run a PowerShell command in the workspace with a timeout.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "default": "."},
                    "timeout_seconds": {
                        "type": "number",
                        "minimum": 0.1,
                        "default": DEFAULT_SHELL_TIMEOUT_SECONDS,
                    },
                },
                "required": ["command"],
            },
            handler=lambda arguments: _shell(arguments, root),
        ),
    ]


def _read(arguments: JsonObject, workspace: Path) -> ToolResult:
    path = _resolve_workspace_path(_required_str(arguments, "path"), workspace)
    encoding = _optional_str(arguments, "encoding", "utf-8")
    if not path.is_file():
        return _error("read", "path_not_file", f"Path is not a file: {_display_path(path, workspace)}")
    try:
        content = path.read_text(encoding=encoding)
    except UnicodeDecodeError as exc:
        return _error("read", "decode_error", f"Could not decode file with {encoding}: {exc}")
    return ToolResult(
        tool_call_id="",
        name="read",
        content=content,
        metadata={"path": _display_path(path, workspace)},
    )


def _write(arguments: JsonObject, workspace: Path) -> ToolResult:
    path = _resolve_workspace_path(_required_str(arguments, "path"), workspace)
    content = _required_str(arguments, "content")
    encoding = _optional_str(arguments, "encoding", "utf-8")
    if not path.parent.exists():
        return _error("write", "parent_not_found", f"Parent directory does not exist: {_display_path(path.parent, workspace)}")
    if path.exists() and not path.is_file():
        return _error("write", "path_not_file", f"Path is not a file: {_display_path(path, workspace)}")
    path.write_text(content, encoding=encoding)
    return ToolResult(
        tool_call_id="",
        name="write",
        content=f"Wrote {len(content)} characters to {_display_path(path, workspace)}.",
        metadata={"path": _display_path(path, workspace), "bytes": len(content.encode(encoding))},
    )


def _edit(arguments: JsonObject, workspace: Path) -> ToolResult:
    path = _resolve_workspace_path(_required_str(arguments, "path"), workspace)
    old_text = _required_str(arguments, "old_text")
    new_text = _required_str(arguments, "new_text")
    encoding = _optional_str(arguments, "encoding", "utf-8")
    if old_text == "":
        return _error("edit", "empty_old_text", "old_text must not be empty.")
    if not path.is_file():
        return _error("edit", "path_not_file", f"Path is not a file: {_display_path(path, workspace)}")
    try:
        content = path.read_text(encoding=encoding)
    except UnicodeDecodeError as exc:
        return _error("edit", "decode_error", f"Could not decode file with {encoding}: {exc}")

    occurrences = content.count(old_text)
    if occurrences == 0:
        return _error("edit", "old_text_not_found", "old_text was not found.")
    if occurrences > 1:
        return _error("edit", "old_text_ambiguous", f"old_text appears {occurrences} times.")

    updated = content.replace(old_text, new_text, 1)
    path.write_text(updated, encoding=encoding)
    return ToolResult(
        tool_call_id="",
        name="edit",
        content=f"Edited {_display_path(path, workspace)}.",
        metadata={"path": _display_path(path, workspace), "replacements": 1},
    )


def _glob(arguments: JsonObject, workspace: Path) -> ToolResult:
    pattern = _required_str(arguments, "pattern")
    limit = _optional_positive_int(arguments, "limit", 100)
    if _looks_absolute_or_parent_relative(pattern):
        return _error("glob", "path_outside_workspace", "Glob pattern must stay inside the workspace.")

    matches: list[str] = []
    for match in sorted(workspace.glob(pattern), key=lambda item: _display_path(item, workspace)):
        resolved = _resolve_workspace_path(match, workspace)
        matches.append(_display_path(resolved, workspace))
        if len(matches) >= limit:
            break
    return ToolResult(
        tool_call_id="",
        name="glob",
        content="\n".join(matches),
        metadata={"count": len(matches), "truncated": len(matches) >= limit},
    )


def _grep(arguments: JsonObject, workspace: Path) -> ToolResult:
    needle = _required_str(arguments, "pattern")
    search_root = _resolve_workspace_path(_optional_str(arguments, "path", "."), workspace)
    file_glob = _optional_str(arguments, "glob", "**/*")
    limit = _optional_positive_int(arguments, "limit", 100)
    case_sensitive = _optional_bool(arguments, "case_sensitive", True)
    if _looks_absolute_or_parent_relative(file_glob):
        return _error("grep", "path_outside_workspace", "File glob must stay inside the selected path.")
    if not search_root.exists():
        return _error("grep", "path_not_found", f"Path does not exist: {_display_path(search_root, workspace)}")

    comparable_needle = needle if case_sensitive else needle.casefold()
    hits: list[str] = []
    candidates = [search_root] if search_root.is_file() else sorted(search_root.glob(file_glob), key=lambda item: str(item))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if _is_too_large(candidate):
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            haystack = line if case_sensitive else line.casefold()
            if comparable_needle in haystack:
                hits.append(f"{_display_path(candidate, workspace)}:{line_number}: {line}")
                if len(hits) >= limit:
                    return ToolResult(
                        tool_call_id="",
                        name="grep",
                        content="\n".join(hits),
                        metadata={"count": len(hits), "truncated": True},
                    )
    return ToolResult(
        tool_call_id="",
        name="grep",
        content="\n".join(hits),
        metadata={"count": len(hits), "truncated": False},
    )


async def _shell(arguments: JsonObject, workspace: Path) -> ToolResult:
    command = _required_str(arguments, "command")
    cwd = _resolve_workspace_path(_optional_str(arguments, "cwd", "."), workspace)
    timeout_seconds = _optional_positive_float(arguments, "timeout_seconds", DEFAULT_SHELL_TIMEOUT_SECONDS)
    if not cwd.is_dir():
        return _error("shell", "cwd_not_directory", f"cwd is not a directory: {_display_path(cwd, workspace)}")

    executable = _powershell_executable()
    if executable is None:
        return _error("shell", "powershell_not_found", "Could not find pwsh or powershell on PATH.")

    process = await asyncio.create_subprocess_exec(
        executable,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.communicate()
        return _error("shell", "timeout", f"Command timed out after {timeout_seconds:g} seconds.")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = process.returncode if process.returncode is not None else -1
    content = f"exit_code: {exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    return ToolResult(
        tool_call_id="",
        name="shell",
        content=content,
        is_error=exit_code != 0,
        metadata={
            "exit_code": exit_code,
            "shell": Path(executable).name,
            "cwd": _display_path(cwd, workspace),
        },
    )


def _workspace_root(workspace: Path | str | None) -> Path:
    return Path.cwd().resolve() if workspace is None else Path(workspace).resolve()


def _resolve_workspace_path(value: str | Path, workspace: Path) -> Path:
    path = Path(value)
    candidate = path if path.is_absolute() else workspace / path
    resolved = candidate.resolve(strict=False)
    if not _is_within_workspace(resolved, workspace):
        raise ValueError(f"Path must stay inside workspace: {value}")
    return resolved


def _is_within_workspace(path: Path, workspace: Path) -> bool:
    try:
        common = os.path.commonpath([os.path.normcase(str(path)), os.path.normcase(str(workspace))])
    except ValueError:
        return False
    return common == os.path.normcase(str(workspace))


def _display_path(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix()


def _required_str(arguments: JsonObject, key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected {key!r} to be a string")
    return value


def _optional_str(arguments: JsonObject, key: str, default: str) -> str:
    value = arguments.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Expected {key!r} to be a string")
    return value


def _optional_bool(arguments: JsonObject, key: str, default: bool) -> bool:
    value = arguments.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Expected {key!r} to be a boolean")
    return value


def _optional_positive_int(arguments: JsonObject, key: str, default: int) -> int:
    value = arguments.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"Expected {key!r} to be a positive integer")
    return value


def _optional_positive_float(arguments: JsonObject, key: str, default: float) -> float:
    value = arguments.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Expected {key!r} to be a positive number")
    return float(value)


def _looks_absolute_or_parent_relative(pattern: str) -> bool:
    return Path(pattern).is_absolute() or any(part == ".." for part in Path(pattern).parts)


def _is_too_large(path: Path) -> bool:
    try:
        return path.stat().st_size > MAX_TEXT_BYTES
    except OSError:
        return True


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _error(name: str, code: str, content: str, metadata: dict[str, JsonValue] | None = None) -> ToolResult:
    result_metadata: dict[str, JsonValue] = {"code": code}
    if metadata is not None:
        result_metadata.update(metadata)
    return ToolResult(tool_call_id="", name=name, content=content, is_error=True, metadata=result_metadata)
