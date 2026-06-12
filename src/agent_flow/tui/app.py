"""Minimal Textual shell for Agent Flow.

The TUI is intentionally a thin frontend. Agent loop behavior belongs in
the core package tasks that follow this skeleton.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, Static


class AgentFlowApp(App[None]):
    """A minimal Textual app that can host future Agent Core events."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
        padding: 1 2;
    }

    #messages {
        height: 1fr;
        border: solid $primary;
        padding: 1 2;
    }

    #prompt {
        dock: bottom;
    }
    """

    TITLE = "agent-flow"
    SUB_TITLE = "Agent Core TUI"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="body"):
            yield Static(
                "Agent Flow is ready. Core event stream wiring starts in T011.",
                id="messages",
            )
            yield Input(placeholder="Type a message for the future agent core...", id="prompt")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        messages = self.query_one("#messages", Static)
        text = event.value.strip()
        if text:
            messages.update(f"Queued input for future Agent Core integration:\n\n{text}")
            event.input.value = ""


def run_tui() -> None:
    """Run the Textual app."""

    AgentFlowApp().run()
