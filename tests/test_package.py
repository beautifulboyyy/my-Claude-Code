from agent_flow import __version__
from agent_flow.__main__ import build_parser


def test_version_is_exposed() -> None:
    assert __version__ == "0.1.0"


def test_cli_parser_accepts_no_arguments() -> None:
    parser = build_parser()
    namespace = parser.parse_args([])
    assert vars(namespace) == {}
