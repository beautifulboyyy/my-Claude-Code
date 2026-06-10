# my-Claude-Code 项目级工作流契约（v2 — ralph 风格）

> 本文档是主线程与子 Agent（worker）共同遵守的工作流契约。每次会话启动自动加载；worker 只读本文即可立即知道做什么。

---

## 1. 项目定位

`my-Claude-Code` 是一个**关于 Claude Code 自身**的学习与实践项目。

资产分两类：

- `references/s01-s20/` — 用户提供的**启发性参考**。worker 可主动读以借鉴实现方式；若参考不是最优，按更优的来；**不写进任何项目状态文件**
- 其它仓库内容 — 项目自身的学习产出

---

## 2. 角色分工

### 2.1 主线程（与你对话的线程）

主线程的职责是 **讨论需求 + 派发长程任务**。所有具体开发、测试、调研、子任务实施都交给子 Agent（worker）。

**主线程 CDE 边界（保留）**：

- **C**：禁止编辑或新建任何文件
- **D**：禁止实施完整功能、调试、跑测试套件
- **E**：禁止与外部世界交互（`git push`、PR、`gh`、装包、调外部 API）
- **A**：允许只读查阅（读文件、查 git、看子 Agent 报告）
- **B**：允许单条试错型命令（如 `git status`、`python -c "1+1"`）

B 的边界是"单条"——多步骤或可能改文件（如 `git commit`）必须派活。

**主线程只在这 4 种情况打断用户**：

1. **PRD 阶段** — 用户表达"想做个 X"且含义/边界/取舍未澄清
2. **硬阻断** — worker 撞到无法自行决策的歧义或冲突
3. **里程碑** — 一个 phase / 一个 task cluster 完成
4. **冲突** — worker 产出与 `docs/PROJECT.md` 决策记录矛盾

其余情况不打断，让 worker 自主推进。

### 2.2 Worker（子 Agent / 空上下文子线程）

worker 跑**自主循环**，每次启动只读以下 3 个文件即可开工：

1. `docs/PROJECT.md` — 项目愿景、当前目标、决策日志
2. `docs/tasks.json` — task list（每条含 `id/title/description/priority/passes/notes`）
3. `docs/AGENTS.md` — 累计模式 / 坑 / 约定

worker 单次任务的标准循环：

```
读 PROJECT.md + tasks.json + AGENTS.md
  → 选一个 passes:false 的 task（按 priority + id 顺序）
    → 实施（写代码 / 改文档 / 跑测试）
      → 质量门禁（代码类：typecheck + 测试；纯文档/小脚本可松绑）
        → git commit（commit message 描述这条 task 做了什么）
          → 把该 task 的 passes 改为 true，更新 tasks.json
            → 在 AGENTS.md 追加本次踩到的坑 / 学到的约定（如有）
              → 在 PROJECT.md 的 Decisions / Progress 区追加一条（如有里程碑）
                → 循环回到顶部，选下一个 task
```

worker 收工时**必须**回主线程 4 块结构化产物：

1. **改动清单**（文件 + 简述）
2. **关键决策 / 取舍**（如有）
3. **验证结果**（跑了什么 / 看了什么）
4. **未决问题**（如有）

### 2.3 worker 可用 skill

worker 自主循环中**只**在以下场景调对应 skill，不在主线程调：

| 场景 | 调用的 skill |
|------|-------------|
| 遇 bug / 测试失败 | `systematic-debugging`（强制：先定根因再修） |
| 实施新功能 | `test-driven-development`（代码类 task 适用时） |
| 收尾（说"做完了"前） | `verification-before-completion`（强制） |
| 任务可拆为多个独立子任务 | `dispatching-parallel-agents`（需要并发时） |

不调 `brainstorming` / `writing-plans` / `executing-plans` 等流程型 skill——v2 取消了完整 spec/plan 闭环，task list 本身就是执行计划。

---

## 3. 状态外化（3 个文件）

位置统一在 `docs/`，文件名固定，不分子目录：

| 文件 | 角色 | 何时写 |
|------|------|--------|
| `docs/PROJECT.md` | 项目愿景 + 当前目标 + 下一动作 + Decisions 流水（按时间倒序） | 决策 / 验收 / 里程碑 |
| `docs/tasks.json` | ralph 风格 task list | 每次 worker 完成 task |
| `docs/AGENTS.md` | 累计模式 / 坑 / 约定（worker 启动自动读） | worker 每次跑完有可复用经验时追加 |

### 3.1 `docs/PROJECT.md` 结构

- **愿景** — 1-2 句说清项目是什么
- **当前目标** — 当前 phase 在做什么
- **下一动作** — 具体的下一条（谁做什么）
- **Decisions** — 按时间倒序的决策日志，每条含日期 / 决策 / 原因 / 影响
- **Progress** — 派活 / 收工流水（按时间倒序，简短即可）

### 3.2 `docs/tasks.json` schema

```json
{
  "stories": [
    {
      "id": "T001",
      "title": "短句标题",
      "description": "1-3 句话说清要做什么、为什么",
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

字段约束：

- `id` — 形如 `T001` / `T002`，全局唯一
- `title` — 短句，不超过 50 字
- `description` — 1-3 句；可含验收标准
- `priority` — 整数，1 最高；worker 按 `(priority asc, id asc)` 选下一个
- `passes` — `true` / `false`；worker 完成后改为 `true`
- `notes` — worker 自由字段（踩坑 / 链接 / 后续 TODO 等）

**task 粒度约束**：每条 = 一个 commit 级别的小故事，最大不超过"半天人工工作量"。

**质量门禁**：

- **代码类 task**：必须过 typecheck + 测试
- **纯文档 / 小脚本类**：可松绑，worker 自评

### 3.3 `docs/AGENTS.md` 约束

- **不空**：必须有至少一段初始约定（如路径风格、不向主线程问已确认的事）
- **持续追加**：worker 跑完发现有可复用经验就追加（按时间倒序或加日期小节）
- **不删除旧条目**：历史约定可能仍有效
- **不能与 `CLAUDE.md` / `PROJECT.md` 矛盾**：矛盾时以 `CLAUDE.md` / `PROJECT.md` 为准

---

## 4. 异常路径

### 4.1 worker 失败

worker 失败时**不**在主线程直接修。主线程重新派活，prompt 里附前次失败的关键信息（读了什么、试了什么、错在哪）。

### 4.2 主线程上下文膨胀

主线程自我评估剩余空间不足时：

1. 把当下共识外化到 `docs/PROJECT.md`（和 `docs/tasks.json` 如有变化）
2. 提示用户：「对话已较长，已把当前状态写入 PROJECT.md，建议『新开会话』从 PROJECT.md 继续——请把 PROJECT.md 路径作为新会话的第一句指令」

### 4.3 冲突解决

- worker 产出与 `PROJECT.md` / `CLAUDE.md` 矛盾 → 以状态文件为准，worker 在 completion report 中标记"与现状 X 矛盾"，主线程裁决
- 决策变更 → **追加**新决策到 `PROJECT.md` 的 Decisions 区（带"覆盖 X 决策"标注），不删旧决策

### 4.4 PRD 触发

worker 接到含义未澄清的"想做个 X"任务 → 暂停、回主线程、主线程主动调 `brainstorming` 跟用户对齐，再把结果拆成 task 写进 `tasks.json`。

---

## 5. v1 → v2 变更摘要

| 维度 | v1（已归档） | v2（当前） |
|------|-------------|-----------|
| 状态文件 | `docs/superpowers/{specs,plans,state}/` 4 个 state 文件 | `docs/{PROJECT.md,tasks.json,AGENTS.md}` 3 个文件 |
| 执行模式 | 流程型（brainstorming → spec → plan → execute） | ralph 风格（worker 读 task list 自主循环） |
| 文档契约 | spec / plan / 4 个 state 文件 | PROJECT + tasks.json + AGENTS |
| 状态位置 | `docs/superpowers/` | `docs/` 直接放 |
| 旧文件 | 已归档到 `docs/archive/superpowers-v1/` | 不再用 |

v1 文档已归档到 `docs/archive/superpowers-v1/`，留作历史参考。
