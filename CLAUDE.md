# my-Claude-Code 工作流契约（v2 — ralph 风格）

主线程 + worker 共同遵守。worker 启动读 §3 三件套即可开工。

---

## 1. 项目定位

学习与实践 Claude Code 自身的项目。

- `references/s01-s20/` — 用户提供的**启发性参考**。worker 可读以借鉴；若不是最优，按更优的来；**不写进任何项目状态文件**
- 其它仓库内容 — 项目自身的学习产出（详见 `docs/PROJECT.md`）

---

## 2. 角色分工

### 2.1 主线程（与你对话的线程）

**职责**：讨论需求 + 派发长程任务。所有具体开发、测试、调研、子任务实施都交给 worker。

**CDE 边界**：

- **A**：允许只读查阅（读文件、查 git、看 worker 报告）
- **B**：允许单条试错型命令（如 `git status`、`python -c "1+1"`）
- **C**：禁止编辑 / 新建代码 / 测试 / 配置文件
- **D**：禁止实施完整功能、跑测试套件
- **E**：禁止 `git push`、PR、`gh`、装包、调外部 API

B 的边界是"单条"——多步骤或可能改文件（如 `git commit`）必须派活。

**契约文件例外**：`CLAUDE.md` / `docs/PROJECT.md` / `docs/tasks.json` / `docs/AGENTS.md` 这 4 个工作流契约文件，主线程可直接编辑（用于修订工作流本身）。改动需一句话说明原因并 commit。

**主线程只在这 4 种情况打断用户**：

1. **PRD 阶段** — "想做个 X"含义/边界/取舍未澄清
2. **硬阻断** — worker 撞到无法自行决策的歧义或冲突
3. **里程碑** — 一个 phase / 一个 task cluster 完成
4. **冲突** — worker 产出与 `docs/PROJECT.md` 决策记录矛盾

### 2.2 Worker（子 Agent）

**职责**：自主循环。每次启动读 §3 三件套 → 选一个 `passes:false` 的 task → 实施 → 质量门禁 → `git commit` → 更新 tasks.json → 必要时追加 AGENTS.md / PROJECT.md → 循环。

**单次任务循环（4 步）**：

1. 实施（写代码 / 改文档 / 跑测试）
2. 质量门禁（代码类：typecheck + 测试；纯文档 / 小脚本可松绑）
3. `git commit`（message 描述这条 task 做了什么） + `tasks.json` 中该 task 改 `passes:true`
4. 必要时追加 AGENTS.md（坑 / 约定）/ PROJECT.md（里程碑）

**收工时回 4 块结构化产物**：改动清单 / 关键决策 / 验证结果 / 未决问题。

**强制调用的 skill**（仅 worker 调，主线程不调）：

| 场景 | skill |
|------|-------|
| 遇 bug / 测试失败 | `systematic-debugging`（先定根因再修） |
| 实施新功能（代码类） | `test-driven-development` |
| 收尾说"做完了"前 | `verification-before-completion`（强制） |
| 任务可拆为多个独立子任务 | `dispatching-parallel-agents` |

v2 取消了完整 spec / plan 闭环——task list 本身就是执行计划，不调任何流程型 skill。

---

## 3. 状态外化（3 个文件）

worker 启动必读；主线程按需读 / 写。

| 文件 | 角色 |
|------|------|
| `docs/PROJECT.md` | 愿景 + 当前目标 + 下一动作 + Decisions（倒序）+ Progress（倒序） |
| `docs/tasks.json` | ralph 风格 task list |
| `docs/AGENTS.md` | 累计模式 / 坑 / 约定（不空、持续追加、不删旧条目；与本文件矛盾时以本文件为准） |

`tasks.json` schema：

```json
{"stories": [{
  "id": "T001",
  "title": "短句标题，≤50字",
  "description": "1-3 句；可含验收标准",
  "priority": 1,
  "passes": false,
  "notes": ""
}]}
```

- worker 选下一个：`(priority asc, id asc)`
- task 粒度：≤ "半天人工工作量"，一个 commit 级别

---

## 4. 异常路径

- **worker 失败**：主线程不修，重新派活（prompt 里附前次失败信息）。
- **上下文膨胀**：把共识外化到 `docs/PROJECT.md`，提示用户开新会话从 PROJECT.md 继续。
- **冲突**：worker 产出 vs `docs/PROJECT.md` / `CLAUDE.md` → 以状态文件为准，worker 在 completion report 中标"与现状 X 矛盾"。
- **PRD 触发**：worker 接到含义未清的"想做个 X"→ 暂停、回主线程 → 主线程跟用户对齐 → 拆 task 写进 `tasks.json`。
- **决策变更**：**追加**新决策到 `docs/PROJECT.md` 的 Decisions 区（带"覆盖 X 决策"标注），不删旧决策。
