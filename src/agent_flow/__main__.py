"""Command entry point for Agent Flow."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from agent_flow import __version__
from agent_flow.tui.app import run_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-flow",
        description="Start the Agent Flow Textual TUI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"agent-flow {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    run_tui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
