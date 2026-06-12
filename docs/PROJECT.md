# Project: agent-flow

> 项目代号 `agent-flow`（曾用名候选 `cca`，2026-06-11 敲定）。
> 学习 / 实践项目 — 从零实现一个可扩展的 Agent Core，后续演进为 coding agent / multi-agent runtime。

---

## 愿景

做一个**稳定、简单、高效、可扩展的 Agent Core**，叫 `agent-flow`：

- **形态**：先做可嵌入、可测试的 single-agent core；Textual TUI 是 core 的薄前端
- **能力**：Core 能完成一个 Agent turn / run 的"读 → 改 → 跑 → 修"闭环，并以事件流暴露全过程
- **设计哲学**：参考 Pi 的 minimal harness / primitives-first 思路：core 提供稳定 primitives，不把 workflow、插件生态、多 Agent 编排做死在内核里
- **扩展方向**：Skill、MCP、插件、dynamic workflow、多 Agent、长程任务、并发运行都在 core primitives 上逐层扩展
- **质量目标**：**真正能用**（不是 demo 玩具）— 别人 clone 完按 README 5 分钟能跑起来
- **兼容性**：多 LLM provider 可换（Anthropic / OpenAI / Ollama 等），不被绑死

---

## 当前目标

**Agent Core v1 — 稳定可扩展的单 Agent 地基**：

| 模块 | v1 要做到 | 未来挂载 |
|------|----------|----------|
| **AgentLoop** | 单 Agent 多轮 tool-call loop；streaming；tool result 回灌；明确 finish / fail / cancel | workflow / sub-agent / long-running scheduler |
| **Event Stream** | 所有过程以事件输出：run、turn、message、tool、policy、error | TUI、日志、session、observability、多 Agent 调度 |
| **Tool Registry** | 内置工具统一注册、启用、执行；tool schema 清晰 | MCP tools、插件 tools、自定义 tools |
| **Context Builder** | 组装 system prompt、项目上下文、工具说明 | Skill、AGENTS.md、memory、dynamic workflow |
| **Policy Hook** | 工具执行前有统一 allow / deny / ask 接口；策略先最小 | 权限系统、沙箱、路径保护、审批 UI |
| **State / Session** | 事件与消息可序列化、可持久化、可恢复 | session tree、branch、Ralph fresh-context loop |
| **LLM Provider** | provider 抽象 + fake provider 测试桩；AgentLoop 稳定后尽早接 MiMo 兼容 API / LiteLLM 真实 provider | 多 provider、local model、路由 |
| **Thin TUI** | Textual TUI 作为 core 消费者验证闭环，不主导架构 | 更完整交互体验 |

**v1 完成判定**：

1. **离线确定性验收**：无 API key 时，fake provider 能稳定覆盖 streaming、tool call、tool result 回灌、provider 错误、provider 超时、tool 超时、取消、失败终态；测试套件可重复通过。
2. **真实 API 可用性验收**：用户本地提供 `MIMO_API_KEY` 后，通过 MiMo OpenAI/Anthropic 兼容 API（优先 OpenAI-compatible endpoint）在一个小 Python 项目里输入"修复 failing test"，Agent Core 能流式输出、读取文件、修改代码、运行测试、根据结果继续，最终明确完成或失败；全过程有事件记录并可保存/恢复。**没有"玩具感"**。

API key 只从环境变量或用户级本地配置读取，禁止写入仓库。测试默认环境变量名：`MIMO_API_KEY`。

**v1 明确不做**：Skill 系统、MCP client、插件市场、多 Agent、子 Agent、长程任务、并发调度、dynamic workflow、复杂 session tree。这些是 v1 core primitives 稳定后的后续 phase。

---

## 下一动作

1. 主线程已将第一版定位收敛为 Agent Core v1，并写入 `docs/tasks.json` Phase 1
2. 派 worker 从最高优先级 task 开始：读三件套 → 实施 → 质量门禁 → commit → 更新 task
3. Phase 1 完成后，Skill / MCP / 插件层一起扩展，不做二选一

---

## Decisions

> 按时间倒序：最新在上。

### 2026-06-12 — Python 开发环境默认使用项目 `.venv`

用户确认希望项目使用 `.venv` 而不是 Conda / Anaconda 全局环境：

- 后续 worker 跑 Python 测试、类型检查、安装依赖前，优先使用仓库根目录 `.venv`
- 若 `.venv` 不存在，worker 应先创建 `.venv`，再安装 `.[dev]`
- Anaconda 只作为系统里已有 Python 来源，不作为本项目依赖安装目标
- 原因：Textual / Rich 等 TUI 依赖可能与 Anaconda 全局包约束冲突，`.venv` 更可复现

### 2026-06-12 — 真实 API 验收纳入 Phase 1

用户确认本地有真实 API key，因此 Phase 1 不只做 fake provider：

- fake provider 仍是 core 稳定性与失败路径的确定性测试基础
- 真实 provider 使用 MiMo 兼容 API：OpenAI endpoint `https://api.xiaomimimo.com/v1/chat/completions`，Anthropic endpoint `https://api.xiaomimimo.com/anthropic/v1/messages`
- 默认模型候选：`mimo-v2.5-pro`
- API key 只允许来自 `MIMO_API_KEY` 环境变量或用户本地配置，不写入仓库
- 缺少 API key 时，离线测试套件必须照常通过

### 2026-06-12 — v1 前端先做 TUI

用户明确 v1 thin frontend 先做 TUI，不走 CLI 优先路线：

- Textual 仍作为默认 TUI 框架
- TUI 只是 core 的事件消费者和用户输入层，不允许把 AgentLoop 逻辑塞进 UI
- CLI 可作为测试/调试辅助，但不是 v1 用户验收主路径

### 2026-06-12 — 第一版收敛为 Agent Core v1

用户明确第一版目标不是完整 Claude Code 仿制品，而是一个基础可用、后续好扩展的 Agent Core：

- 首要目标：稳定、健壮、简单、高效、可扩展的 single-agent core
- 重点参考：Pi 的 minimal harness / primitives-first 架构哲学
- v1 先不做 Skill / MCP / 多 Agent / 长程任务；只把 ToolProvider、ContextProvider、PolicyProvider、EventSubscriber 等 core primitives 留稳
- 后续按层扩展：Skill + MCP + plugin 一起扩展 → dynamic workflow → multi-agent / long-running / concurrency
- Core 边界：只负责一个 Agent run/turn 的稳定执行；调度、持久编排、复杂 workflow 放在 core 之外

### 2026-06-11 — PRD 阶段对齐结果

经 4 轮讨论对齐所有维度决策：

| 维度 | 决策 | 备注 |
|------|------|------|
| **项目名** | `agent-flow` | 2026-06-11 敲定（曾候选 `cca`） |
| **核心形态** | 终端 TUI 应用 | `agent-flow` 命令 → 全屏对话框 |
| **启动流程** | 读 settings → 列/选 session → TUI 主界面 → 退出保存 | 跟 CC 一致 |
| **TUI 框架** | `textual` v4 | async-native + streaming markdown + terminal+browser 双模式。**用户待最后确认**（要自己看一下） |
| **语言** | Python | Aider / OpenHands / Open Interpreter 证明 Python 阵营完全可行；AI 生态（litellm / pydantic / textual）Python 最强 |
| **范围** | MVP 6 件 + reference 课程 s01-s20 全部覆盖 | s15-s20 作为后续 phase |
| **LLM provider** | **LiteLLM**（多 provider 统一接口） | 核心诉求 = 兼容性，避开 CC 把 web 绑死 Anthropic 的坑 |
| **内置工具** | **6 个**：bash / read / write / edit / glob / grep | 覆盖本地代码操作的最小集 |
| **Web 能力** | web_search / web_fetch **走 MCP，首版不内置** | 不绑死 web 搜索 provider；MCP 客户端是 Phase 6 |
| **架构** | **核心 + 插件协议**（Registry + MCP-compatible JSON Schema） | arXiv 70 个 harness 统计 Registry 占 34.3% 是主流；schema 按 MCP 规范设计，Phase 6 升级 MCP 零成本 |
| **权限系统** | TUI 弹确认框；多种权限模式可切（参考 CC + references 简化版） | Read/Glob/Grep 不弹 / Write/Edit 首次弹 / Bash 总是弹（除非白名单） |
| **权限模式** | TUI 内可切换 | 默认 / 严格 / 宽松 / 自定义（具体由 worker 调研 references 后细化） |
| **Session** | 一个对话 = 一个 session；启动可选 / 自动保存 / 可恢复 | 跟 CC 一致 |
| **Settings** | 用户级（`~/.agent-flow/`）+ 项目级（`./.agent-flow/`） | 优先级：项目级 > 环境变量 > 用户级 > 内置默认 |
| **模型 alias 映射** | settings 配 `model_aliases` dict；`/model` 切 alias | 跟 CC 一致；alias 命名跨工具复用；换底层模型不动用户命令 |
| **`/model` 命令** | 只切 alias（不动 model 字符串） | 团队统一 alias 命名（settings 可提交 git） |
| **沙箱 / 隔离** | 首版不做 | 后期（Phase 5+）评估 |
| **CI/CD** | 首版不做 | 后期（Phase 5+）评估 |

### 2026-06-10 — 工作流契约 v2 落地

- 取消完整 spec / plan 闭环
- 主线程：讨论需求 + 派发长程任务
- Worker：读三件套 → 选 task → 实施 → 质量门禁 → commit → 更新三件套 → 循环
- 详见 `CLAUDE.md`

---

## Progress

> 派活 / 收工流水，按时间倒序。

### 2026-06-12 — T001 初始化 Agent Core 包骨架

- 建立 `src/agent_flow/` Python 包与 `agent-flow` console script
- 建立最小 Textual TUI shell，保持 UI 为 thin frontend，不放 AgentLoop 逻辑
- 建立 pytest / mypy 门禁与 README 本地启动说明
- T001 已在 `docs/tasks.json` 标记为通过

### 2026-06-12 — Agent Core v1 方向对齐

- 讨论并放弃"第一版直接做完整 Skill/MCP/插件/多 Agent"的重目标
- 确认第一版先做 Agent Core primitives：AgentLoop、Event Stream、Tool Registry、Context Builder、Policy Hook、State/Session、LLM Provider 抽象
- 参考 Pi / Ralph：Pi 用于 core 架构哲学，Ralph 作为后续长程任务 / fresh-context loop 参考
- 写入 `docs/tasks.json` Phase 1，准备派 worker 实施
- 补充真实 API 验收：MiMo 兼容 API / LiteLLM provider 在 core loop 稳定后提前接入；fake provider 继续作为确定性回归基础
- 确认 v1 前端主路径为 Textual TUI；Skill / MCP 后续一起扩展

### 2026-06-11 — PRD 阶段对齐完成 + PROJECT.md 落地

- 4 轮讨论对齐 4 维决策 + 1 维项目名 + 2 维工具/权限补充
- 调研：5 个架构问题（arXiv 论文 / 主流项目对比 / TUI 选型），确认 "Registry + MCP-compatible schema" 是行业主流
- 调研：横向对比 OpenCode / Aider / Goose / OpenHands / Codex CLI / Pi — Aider 最值得借鉴（Python、Git-native）
- 写入 `docs/PROJECT.md`（本文件），`docs/tasks.json` 暂不动（等用户 review 后再写）

---

## Open Questions

> 需要用户决策才能继续的事。

1. **MiMo 接入优先走 OpenAI-compatible 还是 Anthropic-compatible** — 默认优先 OpenAI-compatible；若 tool-call / streaming 适配不顺，worker 可切 Anthropic-compatible。
2. **TUI 的最小交互形态** — worker 可按 core 验收最小化：消息区、工具事件区、输入区、状态/错误提示；不追求漂亮 UI。
