"""Unit tests for suite/overfit_check.py (NUMBER_IN_PROMPT and EVAL_VALUE_IN_FAKES)."""

from __future__ import annotations

import json
from pathlib import Path

from suite.overfit_check import check_app, main


def _make_workspace(tmp_path: Path, prd_text: str = "# PRD\nRefunds up to $50 are allowed within 30 days.\n") -> tuple[Path, Path, Path]:
    prd = tmp_path / "prd.md"
    prd.write_text(prd_text, encoding="utf-8")
    app_dir = tmp_path / "cxas_app"
    (app_dir / "agents" / "router").mkdir(parents=True, exist_ok=True)
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / "fakes.py").write_text(
        "ACCOUNTS = {\n"
        '    "ACC-1001": {"account_id": "ACC-1001", "phone": "2025550143", "first_name": "Jordan"},\n'
        "}\n"
        'VALID_PINS = frozenset({"1234", "5678"})\n'
        'VALID_OTPS = frozenset({"123456"})\n'
        'ALWAYS_WRONG_LOGIN_CODES = frozenset({"0000", "9999"})\n',
        encoding="utf-8",
    )
    return app_dir, lib_dir, prd


def test_structural_numbers_and_prd_numbers_allowed_in_prompt(tmp_path: Path) -> None:
    app_dir, lib_dir, prd = _make_workspace(tmp_path)
    (app_dir / "agents" / "router" / "instruction.txt").write_text(
        "<taskflow>\n"
        '  <subtask name="M1 Verify">\n'
        '    <step name="Step 1">\n'
        "      <trigger>Caller speaks en-US, fr-CA, or es-419</trigger>\n"
        "      <action>\n"
        "        1. Ask for the 6-digit 2FA code or 4-digit PIN.\n"
        "        2. Confirm the last 4 digits ({phone_last4}) of the 10-digit phone number.\n"
        "        3. Refunds up to $50 within 30 days are auto-approved (24/7 support at 1-800-555-0100).\n"
        "      </action>\n"
        "    </step>\n"
        "  </subtask>\n"
        "</taskflow>\n",
        encoding="utf-8",
    )

    result = check_app(app_dir=app_dir, lib_dir=lib_dir, prd_path=prd)
    num_findings = [f for f in result["findings"] if f["code"] == "NUMBER_IN_PROMPT"]
    assert num_findings == [], f"Unexpected NUMBER_IN_PROMPT findings: {num_findings}"
    assert result["ok"]


def test_unallowed_number_in_prompt_triggers_error(tmp_path: Path) -> None:
    app_dir, lib_dir, prd = _make_workspace(tmp_path)
    (app_dir / "agents" / "router" / "instruction.txt").write_text(
        "<step name=\"quote\">\n"
        "  <trigger>Caller asks about speed</trigger>\n"
        "  <action>Tell the caller their download speed is 450 Mbps with a 75 GB cap.</action>\n"
        "</step>\n",
        encoding="utf-8",
    )

    result = check_app(app_dir=app_dir, lib_dir=lib_dir, prd_path=prd)
    assert not result["ok"]
    codes = {f["code"] for f in result["findings"]}
    assert "NUMBER_IN_PROMPT" in codes
    messages = " ".join(f["message"] for f in result["findings"] if f["code"] == "NUMBER_IN_PROMPT")
    assert "450" in messages
    assert "75" in messages


def test_eval_value_in_fakes_flags_bloated_credential_set(tmp_path: Path) -> None:
    app_dir, lib_dir, prd = _make_workspace(tmp_path)
    (app_dir / "agents" / "router" / "instruction.txt").write_text(
        "<step name=\"greet\"><trigger>Start</trigger><action>Say hello.</action></step>\n",
        encoding="utf-8",
    )
    # 9 entries (> 8 max) in VALID_PINS
    (lib_dir / "fakes.py").write_text(
        'VALID_PINS = frozenset({"1234", "5678", "1111", "0000", "9999", "123456", "654321", "482913", "2468"})\n',
        encoding="utf-8",
    )

    result = check_app(app_dir=app_dir, lib_dir=lib_dir, prd_path=prd)
    assert not result["ok"]
    fakes_findings = [f for f in result["findings"] if f["code"] == "EVAL_VALUE_IN_FAKES"]
    assert fakes_findings, f"Expected EVAL_VALUE_IN_FAKES in {result['findings']}"


def test_eval_value_in_fakes_flags_eval_literal_not_in_prd(tmp_path: Path) -> None:
    app_dir, lib_dir, prd = _make_workspace(tmp_path)
    (app_dir / "agents" / "router" / "instruction.txt").write_text(
        "<step name=\"greet\"><trigger>Start</trigger><action>Say hello.</action></step>\n",
        encoding="utf-8",
    )
    evals_dir = tmp_path / "bench" / "dev" / "evaluations" / "sim_special"
    evals_dir.mkdir(parents=True)
    (evals_dir / "sim_special.json").write_text(
        json.dumps(
            {
                "displayName": "sim_special",
                "scenario": {
                    "task": "Caller provides PIN 7391 and account ACC-7788.",
                    "userFacts": ["Customer: Evelyn Vance"],
                },
            }
        ),
        encoding="utf-8",
    )
    (lib_dir / "fakes.py").write_text(
        "ACCOUNTS = {\n"
        '    "ACC-7788": {"account_id": "ACC-7788", "phone": "2025550143", "first_name": "Evelyn Vance"},\n'
        "}\n"
        'VALID_PINS = frozenset({"1234", "7391"})\n',
        encoding="utf-8",
    )

    result = check_app(
        app_dir=app_dir,
        lib_dir=lib_dir,
        prd_path=prd,
        eval_dirs=[tmp_path / "bench" / "dev"],
    )
    assert not result["ok"]
    fakes_msgs = " ".join(
        f["message"] for f in result["findings"] if f["code"] == "EVAL_VALUE_IN_FAKES"
    )
    assert "7391" in fakes_msgs
    assert "ACC-7788" in fakes_msgs


def test_overfit_check_self_test() -> None:
    assert main(["--self-test"]) == 0
