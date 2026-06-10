#!/usr/bin/env python3
"""
s06: Subagent — spawn sub-agents with fresh messages[] for context isolation.

  Parent Agent                           Subagent
  +------------------+                  +------------------+
  | messages=[...]   |                  | messages=[task]  | <-- fresh
  |                  |   dispatch       |                  |
  | tool: task       | ---------------> | own while loop   |
  |   prompt="..."   |                  |   bash/read/...  |
  |                  |   summary only   |   (max 30 turns) |
  | result = "..."   | <--------------- | return last text |
  +------------------+                  +------------------+
        ^                                      |
        |       intermediate results DISCARDED  |
        +--------------------------------------+

  Subagent tools: bash, read, write, edit, glob (NO task — no recursion)

Changes from s05:
  + task tool + spawn_subagent() with fresh messages[]
  + Safety limit: max 30 turns per subagent
  + extract_text() helper
  Subagent cannot spawn sub-subagents (no task tool in sub_tools).
  Main loop unchanged: task auto-dispatches via TOOL_HANDLERS.

Run: python s06_subagent/code.py
Needs: pip install anthropic python-dotenv + ANTHROPIC_API_KEY in .env
"""

import os, subprocess
from pathlib import Path

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
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
CURRENT_TODOS: list[dict] = []

SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "For complex sub-problems, use the task tool to spawn a subagent."
)

# s06: subagent gets its own system prompt — no task, no recursion
SUB_SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Complete the task you were given, then return a concise summary. "
    "Do not delegate further."
)


# ═══════════════════════════════════════════════════════════
#  FROM s02-s05 (unchanged): Tool Implementations
# ═══════════════════════════════════════════════════════════

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
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
    try:
        file_path = safe_path(path)
        text = file_path.read_text()
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

def run_glob(pattern: str) -> str:
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"

def run_todo_write(todos: list) -> str:
    global CURRENT_TODOS
    for i, t in enumerate(todos):
        if "content" not in t or "status" not in t:
            return f"Error: todos[{i}] missing 'content' or 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return f"Error: todos[{i}] has invalid status '{t['status']}'"
    CURRENT_TODOS = todos
    lines = ["\n\033[33m## Current Tasks\033[0m"]
    for t in CURRENT_TODOS:
        icon = {"pending": " ", "in_progress": "\033[36m▸\033[0m", "completed": "\033[32m✓\033[0m"}[t["status"]]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))
    return f"Updated {len(CURRENT_TODOS)} tasks"

def extract_text(content) -> str:
    """Extract text from message content blocks."""
    if not isinstance(content, list):
        return str(content)
    return "\n".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")

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
    {"name": "todo_write", "description": "Create and manage a task list for your current coding session.",
     "input_schema": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
]

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob, "todo_write": run_todo_write,
}


# ═══════════════════════════════════════════════════════════
#  NEW in s06: Subagent — fresh messages[], summary only
# ═══════════════════════════════════════════════════════════

SUB_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]
# NO "task" tool — prevent recursive spawning

SUB_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob,
}

def spawn_subagent(description: str) -> str:
    """
    启动一个子代理（subagent）并返回其最终总结。
    子代理拥有独立的上下文（fresh messages[]），无法访问父代理的历史消息，
    且其执行结果仅保留最终返回的文本，中间过程被丢弃。
    """
    # 打印子代理启动提示（紫色）
    print(f"\n\033[35m[Subagent spawned]\033[0m")
    
    # 初始化独立的消息上下文，仅包含当前任务描述
    messages = [{"role": "user", "content": description}]  # fresh context

    # 设置安全循环限制，防止子代理无限运行或消耗过多 token
    # 注意：代码注释中提到 max 30 turns，此处设为 40 以提供一定缓冲
    for _ in range(40):
        # 调用 LLM API，使用子代理专用的系统提示 (SUB_SYSTEM) 和工具集 (SUB_TOOLS)
        response = client.messages.create(
            model=MODEL, system=SUB_SYSTEM,
            messages=messages, tools=SUB_TOOLS, max_tokens=8000,
        )
        
        # 将助手响应加入上下文
        messages.append({"role": "assistant", "content": response.content})
        
        # 如果模型没有请求使用工具（即完成了任务或停止生成），则退出循环
        if response.stop_reason != "tool_use":
            break
        
        # 收集所有工具调用的结果
        results = []
        for block in response.content:
            if block.type == "tool_use":
                # 子代理同样受父代理的钩子（Hooks）约束，例如权限检查 (PreToolUse)
                blocked = trigger_hooks("PreToolUse", block)
                if blocked:
                    # 如果工具调用被钩子拦截，记录错误信息
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": str(blocked)})
                    continue
                
                # 获取并执行对应的工具处理函数
                handler = SUB_HANDLERS.get(block.name)
                output = handler(**block.input) if handler else f"Unknown: {block.name}"
                
                # 触发工具使用后的钩子 (PostToolUse)，例如日志记录
                trigger_hooks("PostToolUse", block, output)
                
                # 打印子代理工具执行的简要日志（灰色）
                print(f"  \033[90m[sub] {block.name}: {str(output)[:100]}\033[0m")
                
                # 将工具执行结果存入 results 列表
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": output})
        
        # 将工具执行结果作为新的用户消息加入上下文，供模型下一轮参考
        messages.append({"role": "user", "content": results})

    # --- 结果提取逻辑 ---
    # 尝试从最后一条消息中提取文本内容
    result = extract_text(messages[-1]["content"])
    
    # 如果最后一条消息没有文本（例如最后一条是 tool_result），则向前查找最近的 assistant 文本
    if not result:
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                result = extract_text(msg["content"])
                if result:
                    break
        
        # 如果仍未找到文本，说明可能触发了安全限制且模型未给出总结
        if not result:
            result = "Subagent stopped after max turns without final answer."

    # 打印子代理完成提示（紫色）
    print(f"\033[35m[Subagent done]\033[0m")
    
    # 仅返回提取到的文本总结，整个 messages 历史随后将被丢弃
    return result

# Add task tool to parent's tools
TOOLS.append({
    "name": "task",
    "description": "Launch a subagent to handle a complex subtask. Returns only the final conclusion.",
    "input_schema": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]},
})
TOOL_HANDLERS["task"] = spawn_subagent


# ═══════════════════════════════════════════════════════════
#  FROM s04 (unchanged): Hook System
# ═══════════════════════════════════════════════════════════

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None

DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]

def permission_hook(block):
    """PreToolUse: deny list check."""
    if block.name == "bash":
        for p in DENY_LIST:
            if p in block.input.get("command", ""):
                print(f"\n\033[31m⛔ Blocked: '{p}'\033[0m")
                return "Permission denied"
    return None

def log_hook(block):
    """PreToolUse: log tool calls."""
    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None

def context_inject_hook(query: str):
    """UserPromptSubmit: log working directory."""
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None

def summary_hook(messages: list):
    """Stop: print tool call count."""
    tool_count = sum(1 for m in messages
                     for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("Stop", summary_hook)


# ═══════════════════════════════════════════════════════════
#  agent_loop — same as s05 + nag reminder, task auto-dispatches
# ═══════════════════════════════════════════════════════════

rounds_since_todo = 0

def agent_loop(messages: list):
    global rounds_since_todo
    while True:
        # s05: nag reminder
        if rounds_since_todo >= 3 and messages:
            messages.append({"role": "user",
                             "content": "<reminder>Update your todos.</reminder>"})
            rounds_since_todo = 0

        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return

        rounds_since_todo += 1
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": str(blocked)})
                continue

            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"

            trigger_hooks("PostToolUse", block, output)

            if block.name == "todo_write":
                rounds_since_todo = 0

            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": output})

        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    print("s06: Subagent — spawn sub-agents with fresh context, summary only")
    print("Type a question, press Enter. Type q to quit.\n")

    history = []
    while True:
        try:
            query = input("\033[36ms06 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history)
        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
