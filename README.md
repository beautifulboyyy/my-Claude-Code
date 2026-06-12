# agent-flow

学习与实践 Codex 自身的项目。当前目标是从零实现一个稳定、简单、高效、可扩展的 Agent Core；Textual TUI 是 thin frontend。

## 目录结构

- `.claude/` — Claude Code 项目级配置
- `src/agent_flow/` — Python 包代码
- `tests/` — pytest 测试
- `references/` — Claude Code 教程参考材料（s01-s20）

## 工具栈

- Git 2.48.1
- GitHub CLI (gh) 2.93.0
- Python 3.12+
- Textual
- pytest

## 本地启动

首次使用建议在虚拟环境中安装开发依赖：

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

启动最小 TUI：

```powershell
agent-flow
```

运行测试：

```powershell
python -m pytest
```

运行类型检查：

```powershell
python -m mypy
```
