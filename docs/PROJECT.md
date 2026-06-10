# Project: my-Claude-Code

> 项目全景：愿景、当前目标、下一动作、决策与进度流水。
> 最后更新：2026-06-10

## 愿景

`my-Claude-Code` 是一个**关于 Claude Code 自身**的学习与实践项目。围绕 Claude Code 的工作流（CLAUDE.md、子 Agent、superpowers、ralph 风格 worker 等）做实验性落地，把学到的契约、模式、坑都沉淀进这个仓库。

## 当前目标

- v2 工作流契约（ralph 风格长程 worker）已落地
- `docs/{PROJECT.md, tasks.json, AGENTS.md}` 三件套已就位
- v1 文档已归档到 `docs/archive/superpowers-v1/`

## 下一动作

按新契约开始执行第一个真实 task：等用户在主线程给方向，由主线程把方向拆成 task 写进 `docs/tasks.json`，worker 启动读三件套并自主循环。

## Decisions

> 按时间倒序：最新在上。

### D-002 — 工作流契约升级 v1 → v2（2026-06-10）

- **决策**：将工作流契约从"强 superpowers 绑定"（v1：spec/plan/4 个 state 文件）改为"ralph 风格长程 worker"（v2：PROJECT/tasks.json/AGENTS 三件套）。
- **原因**：v1 的 spec/plan 闭环在小任务上摩擦大；ralph 风格的 task list + 自主循环更适合"长程小步快跑"。
- **影响**：
  - 砍掉 `docs/superpowers/{specs,plans,state}/`；旧文件归档到 `docs/archive/superpowers-v1/`
  - 状态文件从 4 个变为 3 个（PROJECT.md / tasks.json / AGENTS.md）
  - worker 自主循环替代 brainstorming → spec → plan → execute 闭环
  - 详见 `CLAUDE.md` 第 5 节"v1 → v2 变更摘要"

### D-001 — 落地项目级 CLAUDE.md（2026-06-10）

- **决策**：在仓库根创建 `CLAUDE.md`，约束主线程边界、子线程契约、状态外化、Superpowers 流程。
- **原因**：主线程容易被大量上下文撑爆；需要项目级契约约束主线程"该做什么、不该做什么"。
- **影响**：
  - 主线程 A+B / C+D+E 边界明确
  - `docs/superpowers/` 作为状态根目录
  - 已被 D-002 覆盖（v2 不再使用此结构）

## Progress

> 派活 / 收工流水，按时间倒序。每条简短即可。

### 2026-06-10 — v2 契约落地

- 主线程与用户敲定 v2 设计
- 由子 Agent（本次任务）实施：
  - 写新 `CLAUDE.md`（v2 ralph 风格）
  - 创建 `docs/PROJECT.md` / `docs/tasks.json` / `docs/AGENTS.md`
  - 归档 v1 文档到 `docs/archive/superpowers-v1/`
  - 单 commit：`feat: migrate workflow contract v1→v2 (ralph-style worker)`

## Open Questions

> 需要用户决策才能继续的事。当前为空。
