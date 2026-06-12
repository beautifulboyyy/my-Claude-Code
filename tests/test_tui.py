import asyncio

from agent_flow.tui.app import AgentFlowApp


def test_tui_app_has_stable_identity() -> None:
    app = AgentFlowApp()
    assert app.TITLE == "agent-flow"
    assert app.SUB_TITLE == "Agent Core TUI"


def test_tui_app_mounts_in_headless_mode() -> None:
    async def run_app() -> None:
        app = AgentFlowApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.query_one("#messages") is not None
            assert app.query_one("#prompt") is not None

    asyncio.run(run_app())
