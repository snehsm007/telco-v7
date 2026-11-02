"""Unit tests for scripts/lint_check.py (cxas lint + lint_waivers.json)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import lint_check

WARN_T014 = {"file": "tools/a/python_function/python_code.py", "line": 6, "severity": "warning",
             "rule_id": "T014", "message": "lacks a conversational pacing directive"}
WARN_I004 = {"file": "agents/x/instruction.txt", "line": 9, "severity": "warning", "rule_id": "I004",
             "message": "Negative condition in trigger", "fix_suggestion": "Use positive triggers only."}
ERROR = {"file": "app.json", "line": 1, "severity": "error", "rule_id": "S001", "message": "bad schema"}


def test_waived_warnings_pass_and_unwaived_fail() -> None:
    waivers = {"T014": "reason"}
    code, lines = lint_check.check([WARN_T014], waivers)
    assert code == 0 and any("waived because: reason" in line for line in lines)
    code, lines = lint_check.check([WARN_T014, WARN_I004], waivers)
    assert code == 1 and any("FAIL   I004" in line for line in lines)
    assert lint_check.check([ERROR], {"S001": "no"})[0] == 1


def test_kit_waivers_file_is_valid_and_explains_each_waiver() -> None:
    waivers = lint_check.load_waivers(Path(__file__).resolve().parent.parent / "lint_waivers.json")
    assert "T014" in waivers and "WHY_IT_TOOK_SO_LONG" in waivers["T014"]
    assert "I004" not in waivers  # fixed in the scaffold, never waived


def test_main_with_a_fake_cxas(tmp_path: Path, capsys) -> None:
    fake = tmp_path / "cxas"
    fake.write_text("#!/bin/sh\necho 'Linting app'\necho '%s'\n" % json.dumps([WARN_T014]), encoding="utf-8")
    fake.chmod(0o755)
    waivers = tmp_path / "w.json"
    waivers.write_text(json.dumps({"T014": "reason"}), encoding="utf-8")
    assert lint_check.main(["--cxas", str(fake), "--waivers", str(waivers)]) == 0
    assert "lint: OK" in capsys.readouterr().out
    waivers.write_text(json.dumps({}), encoding="utf-8")
    assert lint_check.main(["--cxas", str(fake), "--waivers", str(waivers)]) == 1


def test_self_test() -> None:
    assert lint_check.main(["--self-test"]) == 0
