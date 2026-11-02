#!/usr/bin/env python3
"""Fail if ANY hand-written Python file is below the coverage bar, or has no test file.

pytest-cov's --cov-fail-under only checks the total; one well-tested file can
hide an untested one. This reads coverage.py's JSON report and checks each file.

Usage:
  uv run pytest --cov=cxas_app --cov=lib --cov-report=json:coverage.json
  python suite/coverage_check.py --report coverage.json --min 80 [--tests-dir tests]
  python suite/coverage_check.py --self-test

--tests-dir also enforces one test file per code file: `.../tools/<name>/.../python_code.py`
-> `test_<name>.py`, `lib/<mod>.py` -> `test_<mod>.py`, anywhere under the tests dir.
"""

import argparse
import json
import os
import sys
import tempfile


def expected_test_name(path):
    parts = path.replace("\\", "/").split("/")
    if parts[-1] == "python_code.py":
        # cxas_app/tools/<name>/python_function/python_code.py
        # cxas_app/agents/<agent>/<callback_type>/<name>/python_code.py
        name = parts[-3] if parts[-2] == "python_function" else parts[-2]
        return f"test_{name}.py"
    return f"test_{os.path.splitext(parts[-1])[0]}.py"


def check(report, minimum, tests_dir=None):
    problems = []
    test_files = set()
    if tests_dir:
        for _, _, files in os.walk(tests_dir):
            test_files.update(f for f in files if f.startswith("test_"))
    for path, data in sorted(report.get("files", {}).items()):
        if path.endswith("__init__.py"):
            continue
        pct = data["summary"]["percent_covered"]
        if data["summary"]["num_statements"] and pct < minimum:
            problems.append(f"{path}: {pct:.0f}% < {minimum}%")
        if tests_dir and expected_test_name(path) not in test_files:
            problems.append(f"{path}: no {expected_test_name(path)} under {tests_dir}/")
    return problems


def self_test():
    rep = {
        "files": {
            "lib/responses.py": {
                "summary": {"percent_covered": 95.0, "num_statements": 20}
            },
            "cxas_app/tools/lookup/python_function/python_code.py": {
                "summary": {"percent_covered": 60.0, "num_statements": 10}
            },
            "lib/__init__.py": {
                "summary": {"percent_covered": 0.0, "num_statements": 0}
            },
        }
    }
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "test_responses.py"), "w").close()
        got = check(rep, 80, d)
    want = [
        "cxas_app/tools/lookup/python_function/python_code.py: 60% < 80%",
        f"cxas_app/tools/lookup/python_function/python_code.py: no test_lookup.py under {d}/",
    ]
    if got != want:
        print("FAIL", got)
        return 1
    assert (
        expected_test_name(
            "cxas_app/agents/root/before_agent_callbacks/set_lang/python_code.py"
        )
        == "test_set_lang.py"
    )
    print("OK (coverage self-test)")
    return 0


def main():
    p = argparse.ArgumentParser(description="Per-file coverage and test-file check")
    p.add_argument("--report", default="coverage.json")
    p.add_argument("--min", type=float, default=80)
    p.add_argument("--tests-dir")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    with open(a.report, encoding="utf-8") as f:
        problems = check(json.load(f), a.min, a.tests_dir)
    for line in problems:
        print(line)
    print("coverage: OK" if not problems else f"coverage: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
