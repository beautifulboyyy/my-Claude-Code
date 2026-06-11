# AGENTS — worker 累计模式 / 坑 / 约定

> worker 启动时**必读**。这里只放**可复用**的约定与教训，不放一次性事实。
> 矛盾时以 `CLAUDE.md` / `docs/PROJECT.md` 为准。

---

## 初始约定

### 平台与环境

- **平台**：Windows 11 + Git Bash。`bash` 是默认 shell，但**写文件路径时优先用正斜杠**（`/d/code/...` 或 `D:/code/...`），减少 `Bash` 工具对反斜杠转义的解析错误
- **不要假设 PowerShell/CMD 语法**：在 Bash 工具里写命令时按 Unix 风格（`/dev/null`、`&&`、`|`、`grep`），不要用 `>` / `<` 之类被 shell 解释的字符
- **多行 bash 命令 + 含反斜杠路径容易踩坑**：拆成多行、用 `&&` 串接；含路径的 `mv` / `rm` 失败时优先怀疑路径转义

### 文件与目录

- **写文件优先用 `Write` 工具**；**改文件**用 `Edit` 工具（必须先 `Read`）。不要用 `Bash` 跑 `cat > file` 这种 heredoc
- **删除文件**用 `Bash` + `rm`；**删除空目录**用 `Bash` + `rmdir`（强制非空失败，避免误删）
- **重构目录前先 `find` 看清**：不要凭记忆做 `mv` / `rmdir` 链式操作
- **Windows 上 `rm` / `mv` 一次失败会留下"字面文件名"的脏文件**（命令被吃成字符串）。`rm` 之后立刻 `ls` 验证

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

### 2026-06-10 — Bash `rm` / `mv` 失败会留下"字面命令名"垃圾文件

- **症状**：在 Windows Git Bash 里跑带反斜杠 Windows 路径的 `mv` / `rm`，若命令因任何原因失败（目标目录不存在、路径解析问题、命令截断等），bash 有时会把整条未执行的命令字符串当成单一文件名**创建一个真实文件**，命名形如 `"src" && mv src dst"` 这种
- **后果**：
  - `find` 把它当正常文件列出，污染输出
  - `rmdir` 因为非空而失败，看似"目标目录删不掉"
  - 文件可能恰好覆盖了你想保留的内容
- **规避**：
  - 路径一律用正斜杠：`/d/code/...` 或 `D:/code/...`
  - 多步操作前先 `mkdir -p` 确认目标在；`mv` 之后立刻 `ls` 验证
  - 改用 `Write` / `Edit` 工具做内容写入；只把 `Bash` 留给 git / 测试 / 简单 `ls` / `find`
  - 看到 `find` 输出里出现类似 `&&` / `rm` / `mv` 的长文件名，立刻警觉——那是脏文件
- **清理**：`rm -- '<literal-filename>'`（`--` 避免文件名被当参数），然后 `ls` 确认

### 2026-06-10 — 不要在 Bash 工具里写 heredoc / 多行字符串

- 教训：本次任务初版尝试用 `cat > file <<EOF` 写 `tasks.json`，发现 Bash 工具对 heredoc 解析不稳定，转用 `Write` 工具
- **规则**：写文件 / 改文件 = `Write` / `Edit` 工具；`Bash` 只跑命令、不出文件内容
