# 项目级 CLAUDE.md 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在仓库根创建 `CLAUDE.md`，落地主线程边界、子线程契约、状态外化、Superpowers 流程、异常路径等约定（依据 `docs/superpowers/specs/2026-06-10-claude-md-workflow-design.md`）。

**Architecture:** 单一 markdown 文件，按 6 节大纲组织。所有具体内容已在 spec 6.1-6.6 节确定；本计划是 spec 的运行时精简版本。CLAUDE.md 一旦写入，主线程每次启动会自动加载，因此语言需精炼、边界需明确。

**Tech Stack:** 纯 Markdown，无外部依赖。

---

## File Structure

| File | 责任 |
|------|------|
| `CLAUDE.md`（创建） | 项目级工作流契约（主线程运行时自动加载） |

无其他文件被创建或修改。

---

## Task 1: 写 CLAUDE.md 并提交

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: 写入 `CLAUDE.md`**

在仓库根（`D:\code\python\my-Claude-Code\CLAUDE.md`）写入以下完整内容：

```markdown
# my-Claude-Code 项目级工作流契约

本文档约束主线程（与你对话的线程）与子线程的角色分工、状态外化策略、Superpowers 技能选用规则。主线程每次启动会自动加载本文。

## 1. 项目定位与基本姿势

`my-Claude-Code` 是一个**关于 Claude Code 自身**的学习与实践项目。

资产分两类：
- `references/s01-s20/` — 用户提供的**启发性参考**。主/子线程可主动阅读以借鉴实现方式；若参考不是最优，按更优的来；不写进任何项目状态文件
- 其它仓库内容 — 项目自身的学习产出

基本姿势：
- 主线程以**查阅 + 派活 + 决策**为主
- 具体的开发、测试、调研、子任务实施由**子 Agent / 空上下文子线程**承担
- 上下文管理：决策/验收节点上**外化到文件**，未来主线程可低摩擦接手

## 2. 主线程边界

**允许（A + B）**：

- **A. 只读查阅**：读项目文件、查 `references/s01-s20/`、查 git 历史、看进程输出、看子 Agent 返回的报告
- **B. 试错型单条命令**：跑一条命令验证想法（如 `git status`、`python -c "1+1"`、`man xxx`）

**禁止（C / D / E）**：

- **C**：编辑或新建任何文件
- **D**：实施完整功能、调试、跑测试套件
- **E**：与外部世界交互（`git push`、PR、`gh`、装包、调外部 API）

B 的边界是"单条"——若是多步骤、或者可能改文件（如 `git commit` 会改 `.git/`），必须派活。

## 3. 子线程派活与收工契约

**派活（主线程 → 子线程）**：

- 派活 prompt 必须包含：**(1) 任务描述**、**(2) 相关文件路径**（spec/plan/state/decision）
- 子线程**自己**去读路径指向的文件，不在 prompt 里复制大段内容
- 任务可拆为多视角/多阶段/互相独立时，主线程应**主动调 `dispatching-parallel-agents`** 拆成并发子线程

**收工（子线程 → 主线程）**：

子线程完工时**必须**给出 4 块结构化产物：
1. 改动清单（文件 + 简述）
2. 关键决策/取舍（如有）
3. 验证结果（跑了什么/看了什么）
4. 未决问题（如有）

**粒度（动态）**：

- 单一原子动作（如修一行） → 1 个子线程
- 一个完整小特性 → 1 个子线程自带 `writing-plans`
- 多模块/多视角 → 多个子线程并发

## 4. 状态外化

**位置**：`docs/superpowers/` 下分三目录：

- `specs/` — 需求/设计文档（`brainstorming` 技能产出）
- `plans/` — 实施计划（`writing-plans` 技能产出）
- `state/` — 状态文件

**state/ 下 4 个文件**（按主题分多文件）：

- `docs/superpowers/state/STATE.md` — 项目当前全景：愿景、当前目标、下一动作
- `docs/superpowers/state/decisions.md` — 决策日志：按时间倒序，每条决策记日期、决策、原因、影响
- `docs/superpowers/state/progress.md` — 派活/收工流水：按时间倒序
- `docs/superpowers/state/open-questions.md` — 未决问题：需要用户决策才能继续的事

**何时写**：

- 决策/验收点 → 至少更新 `STATE.md` 和 `decisions.md`
- 子线程完工 → 至少更新 `progress.md`
- 任何阻断子线程的问题 → 写入 `open-questions.md` 并提示用户

**子线程读什么**：

- 接到任务时**先读** `STATE.md` 了解项目当前位置
- 涉及历史决策时**按需读** `decisions.md`
- 实现方式选择时**可主动**读 `references/s01-s20/`，但不是必读，也不是项目状态来源

**格式约束**：

- 纯 markdown
- 文件头部用 H1 + 简短说明
- 时间统一 ISO 日期 `YYYY-MM-DD`

## 5. Superpowers 流程：按场景选用

| 场景 | 建议技能 |
|------|---------|
| 用户说"想做个 X" / "改个行为" / "加个功能"，含义/边界/取舍还没定 | `brainstorming` |
| brainstorming 后产出 spec | `writing-plans` 把它转成可执行 plan |
| plan 已就绪，开始动手 | `executing-plans`（独立 session）或 `subagent-driven-development`（当前 session 子 Agent 派活） |
| 接到可拆解为多个独立子任务的工作 | `dispatching-parallel-agents` |
| 跑测试 / 验收子线程产出 | `test-driven-development`（如适用）/ `verification-before-completion` |
| 收到 code review 反馈 | `receiving-code-review` |
| 准备合并 / 收尾 | `finishing-a-development-branch` |
| 大改前自查或大改后自查 | `requesting-code-review` |

**强制项**（无论流程严不严）：

- 遇到任何 bug 或测试失败 → **必须**先 `systematic-debugging` 再修
- 收尾（说"做完了"前） → **必须** `verification-before-completion`
- 接到看似模糊的反馈（"代码建议改改"） → **必须** `receiving-code-review` 而不是直接动手

不强制每次都跑完整 brainstorming → spec → plan → 实施的闭环。小修小补可以跳过整套。但若用户表达"想做个 X"且含义未澄清，主线程应主动调 `brainstorming`。

## 6. 异常路径与上下文管理

**子线程失败的处置**：

- 主线程不直接在主线程修补，而是**重新派活**，prompt 里附前次失败的关键信息（读了什么、试了什么、错在哪）

**主线程上下文膨胀的处置**：

- 自我评估剩余空间不足时：
  1. 把当下共识**外化**到 `docs/superpowers/state/STATE.md`（和 `decisions.md` 如有）
  2. 提示用户：「对话已较长，已把当前状态写入 STATE.md，建议『新开会话』从 STATE.md 继续——请把 STATE.md 路径作为新会话的第一句指令」
- 用户主动说"我们暂停 / 收一下" → 同样外化

**冲突解决**：

- 子线程产出与 `STATE.md` / `decisions.md` 矛盾时 → 以状态文件为准，子线程在 completion report 中标记"与现状 X 矛盾"，主线程裁决
- 决策变更 → **追加**新决策到 `decisions.md`（带"覆盖 X 决策"标注），不删旧决策
```

- [ ] **Step 2: 验证文件存在**

Run:
```bash
test -f CLAUDE.md && echo OK || echo MISSING
```
Expected: `OK`

- [ ] **Step 3: 验证关键节和关键术语存在**

Run:
```bash
grep -c "^## 1\. " CLAUDE.md
grep -c "^## 6\. " CLAUDE.md
grep -c "systematic-debugging" CLAUDE.md
grep -c "verification-before-completion" CLAUDE.md
grep -c "receiving-code-review" CLAUDE.md
grep -c "docs/superpowers/state/STATE.md" CLAUDE.md
```
Expected: 6 行均输出 `1`（每条 grep 命中 1 次）

- [ ] **Step 4: 验证无 placeholder**

Run:
```bash
grep -nE "TBD|TODO|implement later|fill in details|待补|待定" CLAUDE.md || echo CLEAN
```
Expected: `CLEAN`

- [ ] **Step 5: 提交**

Run:
```bash
git add CLAUDE.md
git commit -m "feat: project-level CLAUDE.md workflow contract"
```

Expected: commit 成功；`git log -1 --oneline` 显示新 commit

---

## Task 2: 按 spec 验收清单核对

**Files:**
- Read: `CLAUDE.md`
- Read: `docs/superpowers/specs/2026-06-10-claude-md-workflow-design.md`（第 8 节验收标准）

- [ ] **Step 1: 人工对照 spec 第 8 节前 5 项**

打开 spec 第 8 节，逐项核对 `CLAUDE.md`：

- [ ] `CLAUDE.md` 存在于仓库根
- [ ] 中文撰写（与 `README.md` 一致）
- [ ] 只描述工作流约定，不描述项目自身的学习产出
- [ ] 主线程边界以「允许列表 + 禁止列表」双形式明确写出
- [ ] 状态文件绝对路径全部写明（`docs/superpowers/state/STATE.md` 等 4 个）

如有未通过项 → 走 Task 3 修补。

- [ ] **Step 2: 核对 spec 第 8 节后 6 项**

- [ ] 三个强制项（`systematic-debugging` / `verification-before-completion` / `receiving-code-review`）以显眼格式列出
- [ ] Superpowers 技能选用以「场景 → 技能对照表」呈现
- [ ] 不预置 `docs/superpowers/state/` 下的任何状态文件
- [ ] 不预置派活/收工模板文件
- [ ] 不修改 `references/` 下任何内容
- [ ] `git status` 干净

第 3 / 4 / 5 项机器验证：

Run:
```bash
test ! -f docs/superpowers/state/STATE.md && echo "no STATE.md ok"
test ! -f docs/superpowers/state/decisions.md && echo "no decisions.md ok"
test ! -f docs/superpowers/state/progress.md && echo "no progress.md ok"
test ! -f docs/superpowers/state/open-questions.md && echo "no open-questions.md ok"
find . -path ./docs -prune -o -name "*template*" -print | grep -v "^$" || echo "no template files ok"
git -C "$(git rev-parse --show-toplevel)" status --porcelain | wc -l
```
Expected:
- 5 行 `ok` 全部出现
- `git status --porcelain | wc -l` 输出 `0`

- [ ] **Step 3: 把验收结果回报给主线程**

回报内容（4 行以内）：
- 通过项数量：`X / 11`
- 未通过项（如有）：列出 spec 第 8 节对应的条目编号
- 建议（如有）：是否要进 Task 3 修补

---

## Task 3（如需）：修补未通过项

> 本任务**条件触发**：仅当 Task 2 发现未通过项时执行。如果 Task 2 全部通过，**跳过**本任务并结束本计划。

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 编辑 `CLAUDE.md` 修补**

针对 Task 2 列出的未通过项，按 spec 第 6 节对应内容编辑 `CLAUDE.md`。修后再跑 Task 2 Step 1 和 Step 2 的核对。

- [ ] **Step 2: 提交修补**

Run:
```bash
git add CLAUDE.md
git commit -m "fix: address spec verification gaps in CLAUDE.md"
```

Expected: 新 commit；`git log -2 --oneline` 显示本次修补

- [ ] **Step 3: 重跑 Task 2 验收**

跑 Task 2 Step 1 / Step 2 / Step 3，确认 11 项全部通过。

---

## 收尾

- 所有 11 项验收标准通过后，本计划完成
- 主线程把"已完成项目级 CLAUDE.md"写入 `docs/superpowers/state/progress.md`（首次实战状态外化的示范）
