"""Unit tests for scripts/impact.py covering AST mapping and all three defect fixes."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts import impact


def _init_git_workspace(tmp_path: Path) -> tuple[Path, str]:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Developer"], cwd=tmp_path, check=True)

    lib_dir = tmp_path / "cxas_app" / "python_code" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "fakes.py").write_text(
        'ACCOUNTS = {"ACC-1001": {"phone": "2025550143"}}\n'
        'VALID_PINS = frozenset({"1234", "5678"})\n',
        encoding="utf-8",
    )
    (lib_dir / "services.py").write_text(
        "from lib.fakes import ACCOUNTS, VALID_PINS\n\n"
        "def lookup_account_impl(identifier: str):\n"
        "    return ACCOUNTS.get(identifier)\n\n"
        "def check_login_code_impl(code: str):\n"
        "    return code in VALID_PINS\n",
        encoding="utf-8",
    )
    (lib_dir / "speech.py").write_text("def clean_speech(text: str) -> str:\n    return text\n", encoding="utf-8")

    for agent in ("router", "specialist"):
        adir = tmp_path / "cxas_app" / "agents" / agent
        adir.mkdir(parents=True)
        (adir / "instruction.txt").write_text(f"Instruction for {agent}.\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial commit"], cwd=tmp_path, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return tmp_path, sha


def _write_impact_map(root: Path) -> None:
    map_path = root / "history" / "eval_impact_map.json"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps(
            {
                "eval_count": 3,
                "evals": {
                    "sim_lookup_en": {
                        "agents": ["router"],
                        "tools": ["lookup_account"],
                        "language": "en",
                        "last_pass_rate": "3/3",
                    },
                    "sim_login_en": {
                        "agents": ["router", "specialist"],
                        "tools": ["check_login_code"],
                        "language": "en",
                        "last_pass_rate": "3/3",
                    },
                    "sim_login_fr": {
                        "agents": ["router", "specialist"],
                        "tools": ["check_login_code"],
                        "language": "fr",
                        "last_pass_rate": "3/3",
                    },
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_first_push_bootstrap_allows_when_no_baseline_exists(tmp_path: Path) -> None:
    root, _ = _init_git_workspace(tmp_path)
    # Neither history/eval_impact_map.json nor history/bench/full-*.json exists yet
    assert impact.check_push_gate(root=root) is True


def test_defect3_selects_only_valid_single_commit_non_holdout_full_run(tmp_path: Path) -> None:
    root, base_sha = _init_git_workspace(tmp_path)
    _write_impact_map(root)
    bench_dir = root / "history" / "bench"
    bench_dir.mkdir(parents=True)

    # 1. Valid full run at base_sha
    (bench_dir / "full-20260101-010000Z.json").write_text(
        json.dumps(
            {
                "git_sha": base_sha,
                "commits": [base_sha],
                "app_versions_seen": ["v1"],
                "is_full_run": True,
                "is_holdout": False,
                "eval_count": 3,
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    # 2. Newer file named full-*.json that is actually a partial/subset run -> must be ignored
    (bench_dir / "full-20260101-020000Z.json").write_text(
        json.dumps(
            {
                "git_sha": "bad1111",
                "commits": ["bad1111"],
                "app_versions_seen": ["v2"],
                "is_full_run": False,
                "is_holdout": False,
                "eval_count": 1,
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    # 3. Newer file with multiple commits -> must be ignored
    (bench_dir / "full-20260101-030000Z.json").write_text(
        json.dumps(
            {
                "git_sha": "bad2222",
                "commits": ["bad2222", "bad3333"],
                "app_versions_seen": ["v3"],
                "is_full_run": True,
                "is_holdout": False,
                "eval_count": 3,
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    # 4. Newer file that is a holdout run -> must be ignored
    (bench_dir / "full-20260101-040000Z.json").write_text(
        json.dumps(
            {
                "git_sha": "bad4444",
                "commits": ["bad4444"],
                "app_versions_seen": ["v4"],
                "is_full_run": True,
                "is_holdout": True,
                "eval_count": 3,
                "results": [],
            }
        ),
        encoding="utf-8",
    )

    assert impact.get_last_full_run_commit(root=root) == base_sha


def test_defect1_and_defect2_smoke_schema_and_audit_log_path(tmp_path: Path) -> None:
    root, base_sha = _init_git_workspace(tmp_path)
    _write_impact_map(root)
    bench_dir = root / "history" / "bench"
    bench_dir.mkdir(parents=True)
    (bench_dir / "full-20260101-010000Z.json").write_text(
        json.dumps(
            {
                "git_sha": base_sha,
                "commits": [base_sha],
                "app_versions_seen": ["v1"],
                "is_full_run": True,
                "is_holdout": False,
                "eval_count": 3,
                "results": [],
            }
        ),
        encoding="utf-8",
    )

    # Modify specialist instruction -> impacts sim_login_en and sim_login_fr
    spec_inst = root / "cxas_app" / "agents" / "specialist" / "instruction.txt"
    spec_inst.write_text("Updated specialist instruction.\n", encoding="utf-8")

    res = impact.analyze_impact(base_sha, root=root)
    assert "sim_login_en" in res["directly_impacted"]
    assert "sim_login_fr" in res["directly_impacted"]
    assert impact.check_push_gate(root=root) is False

    # Case A: Majority pass (2/3) with boolean passed=True must FAIL strict 3/3 smoke gate
    smoke_partial = bench_dir / "smoke-partial.json"
    smoke_partial.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "display_name": "sim_login_en",
                        "passed": True,
                        "pass_runs": 2,
                        "total_runs": 3,
                        "smoke_gate": "FAIL",
                    },
                    {
                        "display_name": "sim_login_fr",
                        "passed": True,
                        "pass_runs": 3,
                        "total_runs": 3,
                        "smoke_gate": "PASS",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    assert impact.record_smoke_results(smoke_partial, root=root) is False
    assert impact.check_push_gate(root=root) is False

    # Case B: Strict 3/3 pass with boolean passed=True and smoke_gate="PASS" must PASS
    smoke_pass = bench_dir / "smoke-pass.json"
    smoke_pass.write_text(
        json.dumps(
            {
                "smoke_gate": {
                    "gate_verdict": "go",
                    "unexpected_tool_errors": [],
                },
                "results": [
                    {
                        "display_name": "sim_login_en",
                        "passed": True,
                        "pass_runs": 3,
                        "total_runs": 3,
                        "smoke_gate": "PASS",
                    },
                    {
                        "display_name": "sim_login_fr",
                        "passed": True,
                        "pass_runs": 3,
                        "total_runs": 3,
                        "smoke_gate": "PASS",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    assert impact.record_smoke_results(smoke_pass, root=root) is True
    assert impact.check_push_gate(root=root) is True

    # Defect 2 verification: writes to history/impact_gate.log, never docs/experiment_log.md
    log_path = root / "history" / "impact_gate.log"
    assert log_path.is_file()
    assert "PASS" in log_path.read_text(encoding="utf-8")
    assert not (root / "docs" / "experiment_log.md").exists()


def test_ast_derived_constant_and_service_mapping(tmp_path: Path) -> None:
    root, base_sha = _init_git_workspace(tmp_path)
    _write_impact_map(root)

    # Modify only lookup_account_impl in services.py
    services_py = root / "cxas_app" / "python_code" / "lib" / "services.py"
    services_py.write_text(
        "from lib.fakes import ACCOUNTS, VALID_PINS\n\n"
        "def lookup_account_impl(identifier: str):\n"
        "    return ACCOUNTS.get(identifier.strip())\n\n"
        "def check_login_code_impl(code: str):\n"
        "    return code in VALID_PINS\n",
        encoding="utf-8",
    )

    res = impact.analyze_impact(base_sha, root=root)
    assert res["directly_impacted"] == ["sim_lookup_en"]
    # Canary for specialist and non-en should be added
    assert "sim_login_fr" in res["canaries"]


def test_mtime_sorting_and_flat_eval_map_and_tool_errors(tmp_path: Path) -> None:
    import os

    root, base_sha = _init_git_workspace(tmp_path)
    # Write flat eval_impact_map.json (without top-level "evals" wrapper)
    map_path = root / "history" / "eval_impact_map.json"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps(
            {
                "VE-01": {
                    "agents": ["router"],
                    "tools": ["lookup_account"],
                    "language": "en",
                    "last_pass_rate": "3/3",
                },
                "VE-02": {
                    "agents": ["router", "specialist"],
                    "tools": ["check_login_code"],
                    "language": "fr",
                    "last_pass_rate": "3/3",
                },
            }
        ),
        encoding="utf-8",
    )

    bench_dir = root / "history" / "bench"
    bench_dir.mkdir(parents=True)
    # Lexicographically larger name ("full-zzzz999.json") with older mtime
    older = bench_dir / "full-zzzz999.json"
    older.write_text(
        json.dumps(
            {
                "commit": "old9999",
                "commits": ["old9999"],
                "is_full_run": True,
                "is_holdout": False,
                "evals": 2,
            }
        ),
        encoding="utf-8",
    )
    os.utime(older, (1700000000, 1700000000))

    # Lexicographically smaller name ("full-aaaa111.json") with newer mtime and bench_summary 'evals' key
    newer = bench_dir / "full-aaaa111.json"
    newer.write_text(
        json.dumps(
            {
                "commit": base_sha,
                "commits": [base_sha],
                "is_full_run": True,
                "is_holdout": False,
                "evals": 2,
            }
        ),
        encoding="utf-8",
    )
    os.utime(newer, (1700000100, 1700000100))

    assert impact.find_latest_full_run_commit(root=root) == base_sha

    # Modify router instruction and verify flat map works
    (root / "cxas_app" / "agents" / "router" / "instruction.txt").write_text("Updated.\n", encoding="utf-8")
    res = impact.analyze_impact(base_sha, root=root)
    assert "VE-01" in res["must_smoke"]

    # Smoke run with tool_errors > 0 or unexpected_errors must fail strict gate
    smoke_err = bench_dir / "smoke-err.json"
    smoke_err.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "ve_id": "VE-01",
                        "pass_runs": 3,
                        "total_runs": 3,
                        "tool_errors": 1,
                        "unexpected_errors": ["SYSTEM_DOWN"],
                    },
                    {
                        "ve_id": "VE-02",
                        "pass_runs": 3,
                        "total_runs": 3,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    assert impact.record_smoke_results(smoke_err, root=root) is False


def test_impact_self_test() -> None:
    assert impact.main(["--self-test"]) == 0

