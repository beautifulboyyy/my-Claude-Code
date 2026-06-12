import asyncio
import shutil
from pathlib import Path

from agent_flow.core import ToolCall, ToolRegistry, register_builtin_tools


def _execute(registry: ToolRegistry, name: str, arguments: dict[str, object]) -> object:
    return asyncio.run(registry.execute(ToolCall(id=f"call_{name}", name=name, arguments=arguments)))


def test_register_builtin_tools_exposes_expected_tool_schemas(tmp_path: Path) -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry, workspace=tmp_path)

    assert [tool.name for tool in registry.list_tools()] == [
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "shell",
    ]
    assert [schema["name"] for schema in registry.list_schemas()] == [
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "shell",
    ]


def test_read_reads_text_file_and_reports_workspace_relative_path(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(registry, "read", {"path": "notes.txt"})

    assert result.content == "hello\n"
    assert result.is_error is False
    assert result.metadata == {"path": "notes.txt"}


def test_read_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(registry, "read", {"path": str(outside)})

    assert result.is_error is True
    assert result.metadata["code"] == "tool_error"
    assert "Path must stay inside workspace" in result.content


def test_write_writes_text_file_inside_existing_parent(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(registry, "write", {"path": "pkg/module.py", "content": "VALUE = 1\n"})

    assert result.is_error is False
    assert (tmp_path / "pkg" / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert result.metadata["path"] == "pkg/module.py"
    assert result.metadata["bytes"] == len("VALUE = 1\n".encode("utf-8"))


def test_edit_replaces_exactly_one_occurrence(tmp_path: Path) -> None:
    target = tmp_path / "story.txt"
    target.write_text("alpha beta gamma\n", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(
        registry,
        "edit",
        {"path": "story.txt", "old_text": "beta", "new_text": "BETA"},
    )

    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "alpha BETA gamma\n"
    assert result.metadata == {"path": "story.txt", "replacements": 1}


def test_edit_rejects_ambiguous_old_text(tmp_path: Path) -> None:
    target = tmp_path / "story.txt"
    target.write_text("repeat\nrepeat\n", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(
        registry,
        "edit",
        {"path": "story.txt", "old_text": "repeat", "new_text": "once"},
    )

    assert result.is_error is True
    assert result.metadata["code"] == "old_text_ambiguous"
    assert target.read_text(encoding="utf-8") == "repeat\nrepeat\n"


def test_glob_lists_workspace_relative_matches_with_limit(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.py").write_text("c", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(registry, "glob", {"pattern": "**/*.txt", "limit": 1})

    assert result.is_error is False
    assert result.content == "a.txt"
    assert result.metadata == {"count": 1, "truncated": True}


def test_grep_finds_literal_matches_case_insensitively(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.py").write_text("Alpha\nbeta\n", encoding="utf-8")
    (tmp_path / "src" / "two.txt").write_text("alphabet\n", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(
        registry,
        "grep",
        {"pattern": "alpha", "path": "src", "glob": "*.py", "case_sensitive": False},
    )

    assert result.is_error is False
    assert result.content == "src/one.py:1: Alpha"
    assert result.metadata == {"count": 1, "truncated": False}


def test_shell_runs_powershell_command_in_workspace(tmp_path: Path) -> None:
    if shutil.which("pwsh") is None and shutil.which("powershell") is None:
        msg = "PowerShell is required for the built-in shell tool"
        raise AssertionError(msg)
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=tmp_path)

    result = _execute(
        registry,
        "shell",
        {"command": "Write-Output (Get-Location).Path", "timeout_seconds": 5},
    )

    assert result.is_error is False
    assert result.metadata["exit_code"] == 0
    assert result.metadata["cwd"] == "."
    assert str(tmp_path) in result.content
