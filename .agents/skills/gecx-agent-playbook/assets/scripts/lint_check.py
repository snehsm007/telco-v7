#!/usr/bin/env python3
"""Run `cxas lint` and fail on errors and on warnings that lint_waivers.json does not waive.

`cxas lint` exits 0 when it finds only warnings, so warnings used to scroll by unseen.
This wrapper (used by `make lint` and `make ci`) prints every finding and fails when:
  - `cxas lint` reports an error (errors can never be waived), or
  - a warning's rule ID is not listed in lint_waivers.json.

lint_waivers.json maps a rule ID to the reason the warning is accepted, for example
{"T014": "why pre-tool pacing phrases are left out"}. Keys that start with "_" are comments.
A waiver that matches no warning is reported so it can be removed.

Usage:
  python3 scripts/lint_check.py [--app-dir cxas_app] [--waivers lint_waivers.json] [--cxas <cxas binary>]
  python3 scripts/lint_check.py --self-test

Exit codes: 0 clean (or only waived warnings), 1 errors or unwaived warnings,
2 cxas is missing, its output cannot be read, or lint_waivers.json is broken.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
RULE_ID = re.compile(r"^[A-Z]{1,4}\d{2,4}$")


def load_waivers(path: Path) -> dict[str, str]:
    """Rule ID -> reason. Raises ValueError on a malformed file or an entry without a reason."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object of rule ID -> reason")
    waivers: dict[str, str] = {}
    for key, reason in data.items():
        if str(key).startswith("_"):
            continue
        if not RULE_ID.match(str(key)):
            raise ValueError(f"{path}: {key!r} is not a cxas lint rule ID (for example T014)")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{path}: the waiver for {key} needs a reason a reviewer can check")
        waivers[str(key)] = reason.strip()
    return waivers


def parse_findings(stdout: str) -> list[dict[str, Any]]:
    """The JSON list `cxas lint --json` prints (tolerates a banner before it)."""
    text = stdout.strip()
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("cxas lint --json did not print a list")
    return [f for f in data if isinstance(f, dict)]


def check(findings: list[dict[str, Any]], waivers: dict[str, str]) -> tuple[int, list[str]]:
    """(exit code, report lines) for the findings under the waivers."""
    errors = [f for f in findings if str(f.get("severity", "")).lower() == "error"]
    warnings = [f for f in findings if str(f.get("severity", "")).lower() == "warning"]
    unwaived = [f for f in warnings if str(f.get("rule_id")) not in waivers]
    lines = [
        f"cxas lint: {len(errors)} error(s), {len(warnings)} warning(s) "
        f"({len(warnings) - len(unwaived)} waived in lint_waivers.json, {len(unwaived)} not waived)"
    ]
    shown_reasons: set[str] = set()
    for f in errors + warnings:
        rule = str(f.get("rule_id") or "?")
        is_error = f in errors
        tag = "ERROR " if is_error else ("WAIVED" if rule in waivers else "FAIL  ")
        lines.append(f"  {tag} {rule} {f.get('file', '?')}:{f.get('line', '?')} {f.get('message', '')}")
        if not is_error and rule in waivers and rule not in shown_reasons:
            lines.append(f"         waived because: {waivers[rule]}")
            shown_reasons.add(rule)
        elif (is_error or rule not in waivers) and f.get("fix_suggestion"):
            lines.append(f"         fix: {f['fix_suggestion']}")
    seen_rules = {str(f.get("rule_id")) for f in warnings}
    for rule in sorted(set(waivers) - seen_rules):
        lines.append(f"  note: the waiver for {rule} matches no warning any more; remove it from lint_waivers.json")
    if errors or unwaived:
        lines.append(
            "lint: FAILED. Fix the findings marked ERROR or FAIL. If a warning is intended, add its rule ID "
            "with the reason to lint_waivers.json (errors cannot be waived)."
        )
        return 1, lines
    lines.append("lint: OK (0 errors, 0 unwaived warnings)")
    return 0, lines


def run_lint(cxas: str, app_dir: str, runner: Callable[..., Any] = subprocess.run) -> list[dict[str, Any]]:
    proc = runner([cxas, "lint", "--app-dir", app_dir, "--json"], capture_output=True, text=True, check=False)
    try:
        return parse_findings(proc.stdout or "")
    except ValueError as exc:
        raise RuntimeError(
            f"could not read the output of `{cxas} lint --app-dir {app_dir} --json` "
            f"(exit {proc.returncode}): {(proc.stderr or proc.stdout or '').strip()[:500]}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--app-dir", default="cxas_app")
    parser.add_argument("--waivers", default=str(REPO_ROOT / "lint_waivers.json"))
    parser.add_argument("--cxas", default="", help="cxas binary (default: .venv/bin/cxas, then PATH)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    cxas = args.cxas or (str(REPO_ROOT / ".venv" / "bin" / "cxas") if (REPO_ROOT / ".venv" / "bin" / "cxas").exists()
                         else shutil.which("cxas") or "")
    if not cxas:
        print("ERROR: cxas CLI not found. Run 'make install' (uv sync) or pip install cxas-scrapi.", file=sys.stderr)
        return 2
    try:
        waivers = load_waivers(Path(args.waivers))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        findings = run_lint(cxas, args.app_dir)
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    code, lines = check(findings, waivers)
    print("\n".join(lines))
    return code


def _self_test() -> int:
    import tempfile

    warn = {"file": "tools/a/python_function/python_code.py", "line": 6, "severity": "warning", "rule_id": "T014",
            "message": "Tool 'a' lacks a conversational pacing directive.", "fix_suggestion": "Add a pacing phrase."}
    neg = {"file": "agents/x/instruction.txt", "line": 9, "severity": "warning", "rule_id": "I004",
           "message": "Negative condition in trigger", "fix_suggestion": "Use positive triggers only."}
    err = {"file": "app.json", "line": 1, "severity": "error", "rule_id": "T014", "message": "broken"}
    waivers = {"T014": "pacing phrases made the model skip tool calls"}
    assert check([warn], waivers)[0] == 0
    assert check([warn, neg], waivers)[0] == 1
    assert check([err], waivers)[0] == 1  # errors are never waived
    assert any("matches no warning" in line for line in check([], waivers)[1])
    assert parse_findings("Linting app: cxas_app\n" + json.dumps([warn])) == [warn]

    class _Proc:
        def __init__(self, out: str, code: int = 0) -> None:
            self.stdout, self.stderr, self.returncode = out, "", code

    assert run_lint("cxas", "cxas_app", runner=lambda *a, **k: _Proc(json.dumps([neg]))) == [neg]
    try:
        run_lint("cxas", "cxas_app", runner=lambda *a, **k: _Proc("Traceback: boom", 1))
        raise AssertionError("unreadable output must fail")
    except RuntimeError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "w.json"
        good.write_text(json.dumps({"_comment": "x", "T014": "reason"}), encoding="utf-8")
        assert load_waivers(good) == {"T014": "reason"}
        bad = Path(tmp) / "bad.json"
        bad.write_text(json.dumps({"T014": " "}), encoding="utf-8")
        try:
            load_waivers(bad)
            raise AssertionError("a waiver without a reason must be rejected")
        except ValueError:
            pass
        assert load_waivers(Path(tmp) / "missing.json") == {}
    kit_waivers = REPO_ROOT / "lint_waivers.json"
    if kit_waivers.exists():
        load_waivers(kit_waivers)
    print("OK: 9/9 lint_check self-test cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
