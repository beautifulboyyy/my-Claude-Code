# AGENTS — worker 累计模式 / 坑 / 约定

> worker 启动时**必读**。这里只放**可复用**的约定与教训，不放一次性事实。
> 矛盾时以 `CLAUDE.md` / `docs/PROJECT.md` 为准。

---

## 初始约定

### 平台与环境

- **平台**：Windows 11。**PowerShell 是默认 shell**（Bash 工具仍可用于 POSIX 脚本）
- **Python 开发环境默认使用项目 `.venv`**：如果仓库根目录没有 `.venv`，worker 在跑 Python 测试 / 安装依赖前先创建 `.venv` 并使用 `.\.venv\Scripts\python.exe` / 激活后的 `python`。不要把依赖装进 Anaconda / 全局 Python。
- **写文件路径时优先用正斜杠**（`/d/code/...` 或 `D:/code/...`），跨 shell 兼容
- **多行命令 + 含反斜杠路径容易踩坑**：拆成多步、用 `&&` 串接；含路径的 `Remove-Item` / `Move-Item` 失败时优先怀疑路径转义

### 文件与目录

- **写文件优先用 `Write` 工具**；**改文件**用 `Edit` 工具（必须先 `Read`）。不要用 shell 跑 `cat > file` 这种 heredoc
- **删除文件**用 `Remove-Item`（PowerShell）；**删除空目录**用 `rmdir`（强制非空失败，避免误删）
- **重构目录前先 `Get-ChildItem` 看清**：不要凭记忆做链式操作

### Git

- **本仓库在 master 分支，工作树干净**（v2 落地后）。除非用户在主线程明确说"建 worktree / 切分支"，否则 worker 直接在 master 改
- **每个 task 一次 commit**：`git add <files> && git commit -m "<conventional commit style>"`，commit message 写清对应 task id
- **commit message 用 conventional commits 风格**：`feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:`
- **不要 `git push`**：那是主线程 E 类禁止项。worker 只在本地 commit
- **不要 `git commit --amend` 已 push 的 commit**：本环境也用不上，列出仅为防呆

### Worker 行为

- **接到 task 立刻读三件套**：`docs/PROJECT.md` + `docs/tasks.json` + 本文件。不要在 prompt 里复制大段内容
- **完成任务后改 `passes: true`**：在 `docs/tasks.json` 里就地修改，然后 commit
- **遇到可复用经验就追加到本文件**：按时间倒序；新加小节用 `### YYYY-MM-DD — 主题`；不要删除旧条目
- **不要问已确认的事**：v2 契约中写明的不需要再问主线程（主线程 CDE 边界、worker 4 块结构化产物、task 粒度、质量门禁等）
- **bug 必修先调 `systematic-debugging`**：先定根因再动手改代码
- **说"做完了"前必跑 `verification-before-completion`**

### 收工 report

worker 完工回主线程时**必给 4 块**：

1. 改动清单（文件 + 简述）
2. 关键决策 / 取舍（如有）
3. 验证结果（跑了什么 / 看了什么）
4. 未决问题（如有）

不要在主线程上下文里堆大段历史。

---

## 经验追加区

> worker 跑完发现可复用的教训 / 模式 / 踩坑时，按 `### YYYY-MM-DD — 主题` 追加在此区上方（按时间倒序）。

### 2026-06-12 — Python TUI 依赖用项目虚拟环境隔离

- Textual 新版本会带入较新的 `rich`，可能与全局 / Anaconda 里已有包（如 `streamlit`）的旧约束冲突；项目验证优先按 README 创建 `.venv` 后 `python -m pip install -e ".[dev]"`。
- 交互式 Textual App 不会自然退出；自动化验收用 `App.run_test()` / pilot 检查挂载，不要用裸 `app.run(headless=True)` 当 smoke test。
