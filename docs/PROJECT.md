# Project: agent-flow

> 项目代号 `agent-flow`（曾用名候选 `cca`，2026-06-11 敲定）。
> 学习 / 实践项目 — 从零实现一个简化版 Claude Code。

---

## 愿景

做一个**简化版 Claude Code**，叫 `agent-flow`：

- **形态**：终端 CLI / TUI 应用。敲 `agent-flow` 直接进入全屏 TUI 对话框，开始聊天
- **能力**：能完成"读 → 改 → 跑 → 修"完整 coding 闭环
- **设计哲学**：参考 `references/s01-s20/` 课程的 20 个模块，**全部实现**（课程本身就是 CC 简化版，CC 自身远比课程复杂）；本项目**不做** CC 的企业级特性、IDE 集成等
- **质量目标**：**真正能用**（不是 demo 玩具）— 别人 clone 完按 README 5 分钟能跑起来
- **兼容性**：多 LLM provider 可换（Anthropic / OpenAI / Ollama 等），不被绑死

---

## 当前目标

**MVP — 6 件**（最小可用且"真正能用"）：

| 件 | 含义 | 用户能看到的 |
|----|------|-------------|
| 1. **TUI 启动** | `agent-flow` 命令 → 全屏对话框 | 终端弹出有结构、有组件的界面 |
| 2. **AgentLoop** | LLM 对话 + tool 调用主循环 | 输 prompt → agent 边想边出、实时显示 |
| 3. **6 个内置工具** | bash / read / write / edit / glob / grep | 屏幕显示 `⚙ Read auth.py` / `⚙ Bash pytest` 之类 |
| 4. **LLM provider** | LiteLLM 统一接口，支持多 provider | 改一行 settings 切模型 |
| 5. **配置 + 模型 alias** | 用户级 + 项目级 settings；`/model` 切 alias | 跟 CC 一致 |
| 6. **Session + 权限系统** | 一个对话 = 一个 session；TUI 弹权限确认框 | 退出再开能从断点继续；危险命令前要确认 |

**MVP 完成判定**：用户能 `pip install agent-flow` → `agent-flow` → 改一个文件 → 跑测试 → 关掉 → 明天 `agent-flow` 选回 session 继续。**没有"玩具感"**。

---

## 下一动作

1. 用户 review `docs/PROJECT.md`（本文件）
2. 用户 review 通过后，主线程写 `docs/tasks.json`（Phase 1 拆解）
3. 派活给 worker 跑 Phase 1 task

---

## Decisions

> 按时间倒序：最新在上。

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

### 2026-06-11 — PRD 阶段对齐完成 + PROJECT.md 落地

- 4 轮讨论对齐 4 维决策 + 1 维项目名 + 2 维工具/权限补充
- 调研：5 个架构问题（arXiv 论文 / 主流项目对比 / TUI 选型），确认 "Registry + MCP-compatible schema" 是行业主流
- 调研：横向对比 OpenCode / Aider / Goose / OpenHands / Codex CLI / Pi — Aider 最值得借鉴（Python、Git-native）
- 写入 `docs/PROJECT.md`（本文件），`docs/tasks.json` 暂不动（等用户 review 后再写）

---

## Open Questions

> 需要用户决策才能继续的事。

1. **TUI 框架 textual 最终拍板** — 用户表示要自己看一下 textual v4。暂定用 textual；用户随时可改
2. **权限模式的具体设计** — 用户提到"参考 references 的权限，他比较简单"。worker 实施时调研 `references/s03_permission/` 后细化
3. **textual v4 / LiteLLM / pydantic 的具体版本** — 实施时 worker 锁定
