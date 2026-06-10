#!/usr/bin/env python3
"""
s08_context_compact.py - Context Compact

Four-layer compaction pipeline inserted before LLM calls:

    L1: snip_compact      — trim middle messages when count > 50
    L2: micro_compact     — replace old tool_results with placeholders
    L3: tool_result_budget — persist large results to disk
    L4: compact_history   — LLM full summary (1 API call)

    Emergency: reactive_compact — when API still returns prompt_too_long

    ┌─────────────────────────────────────────────────────────────┐
    │  messages[]                                                 │
    │    ↓                                                        │
    │  L3 budget ─→ L1 snip ─→ L2 micro ─→ [token > threshold?]  │
    │                                      ├─ No  → LLM          │
    │                                      └─ Yes → L4 summary   │
    │                                              ↓              │
    │                                          LLM call           │
    │                                    [prompt_too_long?]        │
    │                                      └─ Yes → reactive      │
    └─────────────────────────────────────────────────────────────┘

Core principle: cheap first, expensive last.
Execution order matches CC source: budget → snip → micro → auto.

Builds on s07 (skill loading). Usage:

    python s08_context_compact/code.py
    Needs: pip install anthropic python-dotenv + ANTHROPIC_API_KEY in .env
"""

import os, subprocess, json, time
from pathlib import Path

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
except ImportError:
    pass

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"): os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"
TRANSCRIPT_DIR = WORKDIR / ".transcripts"
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]
CURRENT_TODOS: list[dict] = []

# s07: Skill catalog scan (inherited from s07)
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, parts[2].strip()

SKILL_REGISTRY: dict[str, dict] = {}

def _scan_skills():
    if not SKILLS_DIR.exists():
        return
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "SKILL.md"
        if manifest.exists():
            raw = manifest.read_text()
            meta, body = _parse_frontmatter(raw)
            name = meta.get("name", d.name)
            desc = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
            SKILL_REGISTRY[name] = {"name": name, "description": desc, "content": raw}

_scan_skills()

def list_skills() -> str:
    if not SKILL_REGISTRY:
        return "(no skills found)"
    return "\n".join(f"- **{s['name']}**: {s['description']}" for s in SKILL_REGISTRY.values())

def load_skill(name: str) -> str:
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return f"Skill not found: {name}"
    return skill["content"]

# s08: SYSTEM includes skill catalog (inherited from s07 build_system)
def build_system() -> str:
    catalog = list_skills()
    return (
        f"You are a coding agent at {WORKDIR}. "
        f"Skills available:\n{catalog}\n"
        "Use load_skill to get full details when needed."
    )

SYSTEM = build_system()

# s08: subagent gets its own system prompt — no compact, no skill loading
SUB_SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Complete the task you were given, then return a concise summary. "
    "Do not delegate further."
)


# ═══════════════════════════════════════════════════════════
#  FROM s02-s07 (unchanged): Basic Tools
# ═══════════════════════════════════════════════════════════

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR): raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR, capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired: return "Error: Timeout (120s)"

def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines): lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as e: return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path); file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content); return f"Wrote {len(content)} bytes to {path}"
    except Exception as e: return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text()
        if old_text not in text: return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e: return f"Error: {e}"

def run_glob(pattern: str) -> str:
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as e: return f"Error: {e}"

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
    if not isinstance(content, list): return str(content)
    return "\n".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")


# ═══════════════════════════════════════════════════════════
#  FROM s06-s07 (unchanged): Subagent
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
SUB_HANDLERS = {"bash": run_bash, "read_file": run_read, "write_file": run_write,
                "edit_file": run_edit, "glob": run_glob}

def spawn_subagent(description: str) -> str:
    print(f"\n\033[35m[Subagent spawned]\033[0m")
    messages = [{"role": "user", "content": description}]
    for _ in range(30):
        response = client.messages.create(model=MODEL, system=SUB_SYSTEM,
            messages=messages, tools=SUB_TOOLS, max_tokens=8000)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                blocked = trigger_hooks("PreToolUse", block)
                if blocked:
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": str(blocked)})
                    continue
                handler = SUB_HANDLERS.get(block.name)
                output = handler(**block.input) if handler else f"Unknown: {block.name}"
                trigger_hooks("PostToolUse", block, output)
                print(f"  \033[90m[sub] {block.name}: {str(output)[:100]}\033[0m")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})
    result = extract_text(messages[-1]["content"])
    if not result:
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                result = extract_text(msg["content"])
                if result:
                    break
        if not result:
            result = "Subagent stopped after 30 turns without final answer."
    print(f"\033[35m[Subagent done]\033[0m")
    return result


# ═══════════════════════════════════════════════════════════
#  NEW in s08: Four-Layer Compaction Pipeline
# ═══════════════════════════════════════════════════════════

CONTEXT_LIMIT = 50000
KEEP_RECENT = 3
PERSIST_THRESHOLD = 30000

def estimate_size(msgs): return len(str(msgs))


# L1: snipCompact — trim middle messages
def snip_compact(messages, max_messages=50):
    """
    裁剪中间消息以压缩上下文长度。
    保留开头和结尾的最近消息，将中间部分替换为占位符。
    :param messages: 消息历史列表
    :param max_messages: 允许的最大消息数量，默认为 50
    :return: 裁剪后的消息列表
    """
    # 如果消息总数未超过限制，直接返回原列表
    if len(messages) <= max_messages:
        return messages

    # 保留开头 3 条和结尾剩余条数（总共 max_messages 条）
    keep_head, keep_tail = 3, max_messages - 3
    snipped = len(messages) - keep_head - keep_tail

    # 拼接保留的头部消息、占位符提示、以及保留的尾部消息
    return (
        messages[:keep_head]
        + [{"role": "user", "content": f"[snipped {snipped} messages]"}]
        + messages[-keep_tail:]
    )


# L2: microCompact — 将旧的工具结果替换为占位符
def collect_tool_results(messages):
    """
    收集消息历史中所有的 tool_result 块
    :param messages: 消息历史列表
    :return: 包含 (消息索引, 块索引, 块内容) 的元组列表
    """
    blocks = []
    for mi, msg in enumerate(messages):
        # 只处理角色为 user 且内容为列表的消息
        if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
            continue
        for bi, block in enumerate(msg["content"]):
            # 筛选类型为 tool_result 的块
            if isinstance(block, dict) and block.get("type") == "tool_result":
                blocks.append((mi, bi, block))
    return blocks


def micro_compact(messages):
    """
    将较旧的工具结果替换为占位符，保留最近的 KEEP_RECENT 个结果
    :param messages: 消息历史列表
    :return: 处理后的消息列表
    """
    tool_results = collect_tool_results(messages)
    # 如果工具结果数量未超过保留阈值，直接返回
    if len(tool_results) <= KEEP_RECENT:
        return messages
    # 遍历除了最近 KEEP_RECENT 个之外的所有工具结果
    for _, _, block in tool_results[:-KEEP_RECENT]:
        # 只压缩内容长度大于 120 字符的结果
        if len(block.get("content", "")) > 120:
            block["content"] = "[Earlier tool result compacted. Re-run if needed.]"
    return messages


# L3: toolResultBudget — persist large results to disk
# 当工具调用返回的输出过大时，将其保存到磁盘文件中，
# 在消息中只保留文件路径和预览内容，减少上下文占用

def persist_large_output(tool_use_id, output):
    """
    将大型工具输出持久化到磁盘
    :param tool_use_id: 工具使用的唯一标识符
    :param output: 工具返回的输出内容
    :return: 如果输出较小则原样返回，否则返回包含文件路径和预览的占位符
    """
    # 如果输出未超过阈值，直接返回原始内容
    if len(output) <= PERSIST_THRESHOLD:
        return output

    # 确保输出目录存在
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 生成持久化文件路径
    path = TOOL_RESULTS_DIR / f"{tool_use_id}.txt"

    # 如果文件不存在，写入完整输出内容
    if not path.exists():
        path.write_text(output)

    # 返回包含文件路径和预览的标记内容
    return f"<persisted-output>\nFull output: {path}\nPreview:\n{output[:2000]}\n</persisted-output>"


def tool_result_budget(messages, max_bytes=200_000):
    """
    管理工具结果的上下文预算
    当最后一个用户消息中的工具结果总大小超过限制时，
    将大型结果按大小降序持久化到磁盘，直到总大小符合预算
    :param messages: 消息历史列表
    :param max_bytes: 最大允许的字节数，默认200KB
    :return: 处理后的消息列表
    """
    # 获取最后一条消息
    last = messages[-1] if messages else None

    # 检查最后一条消息是否为有效的用户消息且包含列表类型的内容
    if not last or last.get("role") != "user" or not isinstance(last.get("content"), list):
        return messages

    # 收集所有工具结果块
    blocks = [(i, b) for i, b in enumerate(last["content"]) if isinstance(b, dict) and b.get("type") == "tool_result"]

    # 计算所有工具结果的总大小
    total = sum(len(str(b.get("content", ""))) for _, b in blocks)

    # 如果总大小未超过限制，直接返回
    if total <= max_bytes:
        return messages

    # 按内容大小降序排序，优先处理最大的结果
    ranked = sorted(blocks, key=lambda p: len(str(p[1].get("content", ""))), reverse=True)

    # 遍历排序后的工具结果，逐个持久化直到总大小符合预算
    for _, block in ranked:
        if total <= max_bytes:
            break
        content = str(block.get("content", ""))

        # 跳过小于阈值的内容
        if len(content) <= PERSIST_THRESHOLD:
            continue

        # 获取工具使用ID并持久化内容
        tid = block.get("tool_use_id", "unknown")
        block["content"] = persist_large_output(tid, content)

        # 重新计算总大小
        total = sum(len(str(b.get("content", ""))) for _, b in blocks)

    return messages


# L4: autoCompact — LLM full summary
def write_transcript(messages):
    """
    将消息历史保存为 JSONL 格式的记录文件
    :param messages: 消息历史列表
    :return: 保存的文件路径
    """
    # 确保记录目录存在
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    # 生成带时间戳的文件路径
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    # 将每条消息序列化为 JSON 并逐行写入文件
    with path.open("w") as f:
        for msg in messages: f.write(json.dumps(msg, default=str) + "\n")
    return path

def summarize_history(messages):
    """
    调用 LLM 对对话历史进行摘要
    :param messages: 消息历史列表
    :return: 摘要文本
    """
    # 截取前 80000 字符作为对话内容，避免过长
    conversation = json.dumps(messages, default=str)[:80000]
    # 构造提示词，要求保留关键信息
    prompt = ("Summarize this coding-agent conversation so work can continue.\n"
              "Preserve: 1. current goal, 2. key findings/decisions, 3. files read/changed, "
              "4. remaining work, 5. user constraints.\nBe compact but concrete.\n\n" + conversation)
    # 调用 LLM 生成摘要
    response = client.messages.create(model=MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=2000)
    # 提取文本类型的响应内容并拼接
    return "\n".join(
        getattr(block, "text", "")
        for block in response.content
        if getattr(block, "type", None) == "text").strip() or "(empty summary)"

def compact_history(messages):
    """
    执行完整的上下文压缩流程：保存记录 + 生成摘要
    :param messages: 消息历史列表
    :return: 包含摘要的单条消息列表
    """
    # 保存当前对话历史到文件
    transcript_path = write_transcript(messages)
    print(f"[transcript saved: {transcript_path}]")
    # 调用 LLM 生成摘要
    summary = summarize_history(messages)
    # 返回包含压缩标记和摘要的新消息列表
    return [{"role": "user", "content": f"[Compacted]\n\n{summary}"}]


# Emergency: reactiveCompact — on API error
def reactive_compact(messages):
    """
    紧急上下文压缩：当 API 返回 prompt_too_long 错误时触发。
    保存当前对话记录，生成摘要，并保留最近的几条消息以保持上下文连贯性。
    :param messages: 消息历史列表
    :return: 包含摘要和最近消息的新消息列表
    """
    # 保存当前对话历史到文件
    transcript = write_transcript(messages)
    # 调用 LLM 生成摘要
    summary = summarize_history(messages)
    # 返回包含压缩标记、摘要以及最近 5 条消息的新列表
    return [{"role": "user", "content": f"[Reactive compact]\n\n{summary}"}, *messages[-5:]]


# ═══════════════════════════════════════════════════════════
#  FROM s07: Tool Definitions
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
    {"name": "todo_write", "description": "Create and manage a task list for your current coding session.",
     "input_schema": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
    {"name": "task", "description": "Launch a subagent to handle a complex subtask. Returns only the final conclusion.",
     "input_schema": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}},
    {"name": "load_skill", "description": "Load the full content of a skill by name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    # s08 change: new compact tool — triggers compact_history, not a no-op
    {"name": "compact", "description": "Summarize earlier conversation to free context space.",
     "input_schema": {"type": "object", "properties": {"focus": {"type": "string"}}}},
]

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob, "todo_write": run_todo_write,
    "task": spawn_subagent, "load_skill": load_skill,
}

# FROM s04 (unchanged): Hooks
HOOKS = {"PreToolUse": [], "PostToolUse": []}
def trigger_hooks(event, *args):
    for cb in HOOKS[event]:
        r = cb(*args)
        if r is not None: return r
    return None

DENY_LIST = ["rm -rf /", "sudo", "shutdown"]
def permission_hook(block):
    if block.name == "bash":
        for p in DENY_LIST:
            if p in block.input.get("command", ""): return "Permission denied"
    return None
def log_hook(block):
    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None

HOOKS["PreToolUse"].append(permission_hook)
HOOKS["PreToolUse"].append(log_hook)


# ═══════════════════════════════════════════════════════════
#  agent_loop — s08 core: run compaction pipeline before LLM
# ═══════════════════════════════════════════════════════════

MAX_REACTIVE_RETRIES = 1  # retry limit for reactive compact

def agent_loop(messages: list):
    reactive_retries = 0
    while True:
        # s08 change: three preprocessors (0 API calls, cheap first)
        # Order matches CC source: budget → snip → micro
        messages[:] = tool_result_budget(messages)    # L3: persist large results first
        messages[:] = snip_compact(messages)          # L1: trim middle
        messages[:] = micro_compact(messages)         # L2: old result placeholders

        # s08 change: tokens still over threshold → LLM summary (1 API call)
        if estimate_size(messages) > CONTEXT_LIMIT:
            print("[auto compact]")
            messages[:] = compact_history(messages)

        try:
            response = client.messages.create(model=MODEL, system=SYSTEM, messages=messages, tools=TOOLS, max_tokens=8000)
            reactive_retries = 0  # reset on successful API call
        except Exception as e:
            if ("prompt_too_long" in str(e).lower() or "too many tokens" in str(e).lower()) and reactive_retries < MAX_REACTIVE_RETRIES:
                print("[reactive compact]")
                messages[:] = reactive_compact(messages)
                reactive_retries += 1
                continue
            raise

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use": return

        results = []
        for block in response.content:
            if block.type != "tool_use": continue
            print(f"\033[36m> {block.name}\033[0m")

            # s08: compact tool triggers compact_history, not a no-op string
            # 当 LLM 调用 compact 工具时，执行完整的历史摘要压缩流程
            if block.name == "compact":
                # 执行 L4: 调用 LLM 对整个对话历史进行摘要
                messages[:] = compact_history(messages)
                # 将 compact 工具的执行结果添加到结果列表
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": "[Compacted. Conversation history has been summarized.]"})
                # 立即将结果追加到消息列表，然后 break 跳出 for 循环
                # 这样可以跳过 for...else 的 else 分支（正常工具处理路径）
                # 直接进入下方的 continue，以压缩后的上下文开始新的对话轮次
                messages.append({"role": "user", "content": results})
                break  # end current turn, start fresh with compacted context

            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(blocked)})
                continue
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"
            trigger_hooks("PostToolUse", block, output)
            print(str(output)[:200])
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
        else:
            # normal path: no compact was called
            messages.append({"role": "user", "content": results})
            continue
        # compact was called: results already appended above
        continue


if __name__ == "__main__":
    print("s08: Context Compact — four-layer compaction pipeline")
    print("输入问题，回车发送。输入 q 退出。\n")
    history = []
    while True:
        try: query = input("\033[36ms08 >> \033[0m")
        except (EOFError, KeyboardInterrupt): break
        if query.strip().lower() in ("q", "exit", ""): break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text": print(block.text)
        print()
