from pathlib import Path

from suite.tool_tests import main as run_tool_tests

ROOT = Path(__file__).resolve().parent.parent


def test_tool_tests_suite_passes() -> None:
    assert run_tool_tests(["--evals-dir", str(ROOT / "evals" / "tool_tests")]) == 0
