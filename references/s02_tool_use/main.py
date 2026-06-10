#!/usr/bin/env python3
"""
s02: Tool Use — 在 s01 基础上新增 4 个工具 + 分发映射。

运行: python s02_tool_use/code.py
需要: pip install anthropic python-dotenv + .env 中配置 ANTHROPIC_API_KEY

本文件 = s01 的全部代码 + 以下新增:
  + run_read / run_write / run_edit / run_glob 四个工具实现
  + TOOL_HANDLERS 分发映射（替代 s01 中硬编码的 run_bash 调用）
  + safe_path 路径安全校验

循环本身（agent_loop）与 s01 完全一致。
"""

import os, subprocess
from pathlib import Path

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]

SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks. Act, don't explain."


# ═══════════════════════════════════════════════════════════
#  FROM s01 (unchanged)
# ═══════════════════════════════════════════════════════════

def run_bash(command: str) -> str:
    """执行 Bash 命令并捕获输出。

    该函数负责在指定的工作目录中运行 shell 命令。包含安全检查、超时控制
    以及输出长度截断机制。

    Args:
        command: 需要执行的 shell 命令字符串。

    Returns:
        str: 命令的 stdout/stderr 输出内容，若发生异常则返回错误信息。
    """
    # 安全检查：拦截可能危害系统的危险命令
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    
    # 执行命令：设置工作目录、超时限制，并捕获标准输出和错误输出
    try:
        r = subprocess.run(
            command, 
            shell=True, 
            cwd=WORKDIR,
            capture_output=True, 
            text=True,
            encoding="utf-8", 
            errors="replace", 
            timeout=120
        )
        
        # 处理输出：合并 stdout 和 stderr，去除首尾空白，并截断过长的内容（50000 字符）
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    
    # 异常处理：捕获超时异常
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    
    # 异常处理：捕获文件未找到或操作系统相关错误
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
#  NEW in s02: 4 个新工具
# ═══════════════════════════════════════════════════════════

def safe_path(p: str) -> Path:
    """校验并解析安全路径。

    将输入路径与 WORKDIR 拼接并解析为绝对路径，同时校验其是否仍在工作目录内，
    以防止路径穿越（Directory Traversal）攻击。

    Args:
        p: 需要校验的相对或绝对路径字符串。

    Returns:
        Path: 校验通过后的绝对路径对象。

    Raises:
        ValueError: 当解析后的路径超出工作目录范围时抛出。
    """
    # 拼接工作目录并解析为绝对路径
    path = (WORKDIR / p).resolve()

    # 安全检查：确保路径没有逃逸出 WORKDIR
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")

    return path


def run_read(path: str, limit: int | None = None) -> str:
    """读取文件内容。

    读取指定路径的文件内容并按行处理。如果提供了 limit 参数且文件总行数超过该限制，
    则截断输出并附加剩余行数的提示信息。

    Args:
        path: 需要读取的文件路径。
        limit: 可选参数，限制返回的最大行数。

    Returns:
        str: 文件的文本内容，若超出限制则包含截断提示，发生异常则返回错误信息。
    """
    try:
        # 解析安全路径并读取文本内容，按行分割
        lines = safe_path(path).read_text().splitlines()
        
        # 如果设置了行数限制，且文件行数超过限制，进行截断并添加提示
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        
        # 将行重新拼接为字符串返回
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    """编辑文件内容。

    将文件中首次出现的指定旧文本替换为新文本。包含路径安全校验、存在性检查
    以及单次替换逻辑，以防止误替换。

    Args:
        path: 需要编辑的文件路径。
        old_text: 需要被替换的原始文本。
        new_text: 用于替换的新文本。

    Returns:
        str: 替换成功则返回提示信息，未找到文本或发生异常则返回错误信息。
    """
    try:
        # 解析安全路径并读取文件内容
        file_path = safe_path(path)
        text = file_path.read_text()
        
        # 检查旧文本是否存在于文件中
        if old_text not in text:
            return f"Error: text not found in {path}"
        
        # 执行替换（仅替换第一次出现的匹配项）并写回文件
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_glob(pattern: str) -> str:
    """查找匹配模式的文件路径。

    在工作目录下搜索匹配给定 glob 模式的文件，并进行路径安全校验，
    确保返回的文件路径没有逃逸出工作目录。

    Args:
        pattern: Glob 匹配模式字符串（例如 "*.py"）。

    Returns:
        str: 匹配的文件路径列表（用换行符分隔），若无匹配则返回提示信息，
             发生异常则返回错误信息。
    """
    import glob as g
    try:
        # 使用 glob 模块在 WORKDIR 下搜索匹配的文件
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            # 安全校验：确保解析后的路径仍在 WORKDIR 范围内
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        
        # 返回结果
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
#  NEW in s02: 工具定义（s01 只有一个 bash，现在扩展到 5 个）
# ═══════════════════════════════════════════════════════════

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

# ═══════════════════════════════════════════════════════════
#  NEW in s02: 工具分发映射（s01 是硬编码 run_bash，现在改为查表）
# ═══════════════════════════════════════════════════════════

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob,
}


# ═══════════════════════════════════════════════════════════
#  agent_loop — 与 s01 结构完全一致，只改了工具执行那部分
#  s01: output = run_bash(block.input["command"])
#  s02: output = TOOL_HANDLERS[block.name](**block.input)
# ═══════════════════════════════════════════════════════════

def agent_loop(messages: list):
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return

        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"\033[33m> {block.name}\033[0m")
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**block.input) if handler else f"Unknown: {block.name}"
                print(str(output)[:200])
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})

        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    print("s02: Tool Use — 在 s01 基础上加了 4 个工具")
    print("输入问题，回车发送。输入 q 退出。\n")

    history = []
    while True:
        try:
            query = input("\033[36ms02 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
