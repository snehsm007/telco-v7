"""Tests for the cloud gates: push -> smoke -> record, bench-full, Gate 3, gate.py strict 3/3."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts import bench_summary, impact, run_bench
from suite import gate

APP = "projects/p/locations/us/apps/a1"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "--short=7", "HEAD")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A scaffold-shaped repo: two agents, lib/ with a login tool and a task tool, evals/, docs/."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "dev@example.com")
    _git(tmp_path, "config", "user.name", "Developer")
    _write(tmp_path / "cxas_app" / "app.json", "{}\n")
    _write(tmp_path / "cxas_app" / "global_instruction.txt", "Shared rules.\n")
    for agent in ("router", "specialist"):
        _write(tmp_path / "cxas_app" / "agents" / agent / "instruction.txt", f"{agent} v1\n")
    _write(tmp_path / "cxas_app" / "tools" / "submit_request" / "submit_request.json", '{"description": "v1"}\n')
    _write(
        tmp_path / "lib" / "fakes.py",
        'VALID_PINS = frozenset({"1234"})\nREQUEST_KINDS = ("statement",)\n',
    )
    _write(
        tmp_path / "lib" / "services.py",
        "from lib.fakes import REQUEST_KINDS, VALID_PINS\n\n\n"
        "def check_login_code_impl(code):\n    return code in VALID_PINS\n\n\n"
        "def submit_request_impl(summary):\n    return summary in REQUEST_KINDS\n",
    )
    _write(tmp_path / "evals" / "goldens" / "goldens.yaml", "goldens: []\n")
    _write(tmp_path / "docs" / "notes.md", "v1\n")
    _commit(tmp_path, "base")
    return tmp_path


def _baseline_full_run(root: Path, sha: str) -> None:
    """A clean full run on `sha` plus an impact map with three evals."""
    _write(
        root / "history" / "bench" / f"full-{sha}.json",
        json.dumps(
            {
                "label": f"full-{sha}",
                "git_sha": sha,
                "commit": sha,
                "commits": [sha],
                "is_full_run": True,
                "is_holdout": False,
                "eval_count": 3,
                "runs_per_eval": 3,
                "tool_errors": 0,
                "per_eval": {
                    "VE-01": {"pass": 3, "total": 3, "verdict": "PASS"},
                    "VE-02": {"pass": 3, "total": 3, "verdict": "PASS"},
                    "VE-03": {"pass": 3, "total": 3, "verdict": "PASS"},
                },
            }
        ),
    )
    _write(
        root / "history" / "eval_impact_map.json",
        json.dumps(
            {
                "evals": {
                    "sim_request_en": {"agents": ["router", "specialist"], "tools": ["submit_request"],
                                       "language": "en", "last_pass_rate": "3/3"},
                    "sim_login_en": {"agents": ["router", "specialist"], "tools": ["check_login_code"],
                                     "language": "en", "last_pass_rate": "3/3"},
                    "sim_route_fr": {"agents": ["router"], "tools": [], "language": "fr",
                                     "last_pass_rate": "3/3"},
                }
            }
        ),
    )


def _passing_smoke(root: Path, evals: list[str]) -> Path:
    path = root / "bench" / "runs" / "smoke-test.json"
    _write(
        path,
        json.dumps(
            {
                "results": [
                    {"display_name": ve, "pass_runs": 3, "total_runs": 3, "smoke_gate": "PASS"} for ve in evals
                ]
            }
        ),
    )
    return path


# ----------------------------------------------------------------------------- source fingerprint


def test_fingerprint_ignores_docs_commits_and_marks_uncommitted_source(repo: Path) -> None:
    fp = impact.source_fingerprint(repo)
    _write(repo / "docs" / "notes.md", "v2\n")
    _write(repo / "history" / "runs.jsonl", "{}\n")
    _commit(repo, "docs and history")
    assert impact.source_fingerprint(repo) == fp

    _write(repo / "evals" / "simulations" / "new.yaml", "simulations: []\n")  # untracked source file
    assert impact.source_fingerprint(repo).startswith(fp + "+dirty.")
    assert impact.source_dirty_files(repo)
    _commit(repo, "new eval")
    assert impact.source_fingerprint(repo) != fp
    assert impact.fingerprint_at("deadbee", repo) is None


def test_push_refuses_uncommitted_source_and_records_the_push(repo: Path, capsys) -> None:
    _write(repo / "lib" / "fakes.py", 'VALID_PINS = frozenset({"1234", "5678"})\nREQUEST_KINDS = ("statement",)\n')
    assert impact.require_clean_source(repo) is False
    assert "commit first" in capsys.readouterr().err
    sha = _commit(repo, "more pins")
    assert impact.require_clean_source(repo) is True

    data = impact.record_push(APP, f"git-{sha}", repo)
    assert data["commit"] == sha and data["app"] == APP and data["version"] == f"git-{sha}"
    assert data["source_fingerprint"] == impact.source_fingerprint(repo)
    assert set(data) >= {"commit", "source_fingerprint", "app", "version", "pushed_at"}
    impact.record_push("projects/p/locations/us/apps/preview", "draft", repo)
    assert impact.last_push_for(APP, repo)["version"] == f"git-{sha}"
    assert impact.last_push_for("", repo)["app"].endswith("/preview")


def test_deployed_check(repo: Path) -> None:
    assert impact.check_deployed(APP, repo)[0] is False  # nothing pushed
    sha = _git(repo, "rev-parse", "--short=7", "HEAD")
    impact.record_push(APP, f"git-{sha}", repo)
    ok, msg = impact.check_deployed(APP, repo)
    assert ok and "runs this checkout" in msg
    assert impact.check_deployed("projects/p/locations/us/apps/other", repo)[0] is False

    _write(repo / "docs" / "notes.md", "docs only\n")
    _commit(repo, "docs only")
    assert impact.check_deployed(APP, repo)[0] is True  # docs commit: same fingerprint

    _write(repo / "cxas_app" / "agents" / "router" / "instruction.txt", "router v2\n")
    ok, msg = impact.check_deployed(APP, repo)
    assert not ok and "uncommitted changes" in msg
    _commit(repo, "router v2")
    ok, msg = impact.check_deployed(APP, repo)
    assert not ok and "Push this commit first: make push ENV=staging" in msg


# ----------------------------------------------------------------------------- smoke-impact


def test_smoke_plan_refuses_until_pushed_and_bootstraps_without_a_full_run(repo: Path) -> None:
    assert impact.smoke_plan(APP, root=repo) == (1, "")
    impact.record_push(APP, "git-x", repo)
    assert impact.smoke_plan(APP, root=repo) == (0, "")  # no full run yet: nothing to compare


def test_smoke_plan_verdicts(repo: Path) -> None:
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)

    # SMOKE: one agent's prompt changed -> its evals plus canaries.
    _write(repo / "cxas_app" / "agents" / "specialist" / "instruction.txt", "specialist v2\n")
    _commit(repo, "specialist v2")
    impact.record_push(APP, "git-a", repo)
    code, targets = impact.smoke_plan(APP, root=repo)
    assert code == 0
    assert "sim_request_en" in targets.split(",") and "sim_login_en" in targets.split(",")

    # FULL: the global instruction changed.
    _write(repo / "cxas_app" / "global_instruction.txt", "Shared rules v2.\n")
    _commit(repo, "global v2")
    impact.record_push(APP, "git-b", repo)
    assert impact.smoke_plan(APP, root=repo) == (2, "")
    last = json.loads((repo / "history" / "last_impact.json").read_text(encoding="utf-8"))
    assert last["verdict"] == "FULL"


def test_full_verdict_for_shared_login_code(repo: Path) -> None:
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)
    _write(
        repo / "lib" / "services.py",
        "from lib.fakes import REQUEST_KINDS, VALID_PINS\n\n\n"
        "def check_login_code_impl(code):\n    return str(code) in VALID_PINS\n\n\n"
        "def submit_request_impl(summary):\n    return summary in REQUEST_KINDS\n",
    )
    res = impact.analyze_impact(base, root=repo)
    assert res["verdict"] == "FULL"
    assert any("login tool check_login_code" in r for r in res["verdict_reasons"])


def test_nothing_to_smoke_records_a_pass(repo: Path) -> None:
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)
    # The after_model callback files are generated from lib/ (which is mapped itself): 0 impacted evals.
    callback = repo / "cxas_app" / "agents" / "router" / "after_model_callbacks" / "speech_hygiene" / "python_code.py"
    _write(callback, "X = 1\n")
    _commit(repo, "regenerated callback")
    impact.record_push(APP, "git-c", repo)
    assert impact.smoke_plan(APP, root=repo) == (0, "")
    last = json.loads((repo / "history" / "last_impact.json").read_text(encoding="utf-8"))
    assert last["smoke_verified"] is True and last["verified_fingerprint"] == impact.source_fingerprint(repo)
    assert impact.check_bench_full_gate(APP, root=repo) is True


def test_tool_folder_edits_are_smoked_and_unknown_tools_need_a_full_run(repo: Path) -> None:
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)
    # A hand edit of a known tool's description smokes the evals that use the tool, plus canaries.
    _write(repo / "cxas_app" / "tools" / "submit_request" / "submit_request.json", '{"description": "v2"}\n')
    res = impact.analyze_impact(base, root=repo)
    assert res["verdict"] == "SMOKE"
    assert res["directly_impacted"] == ["sim_request_en"]
    assert res["impacted_tools"] == ["submit_request"]
    assert res["canaries"] == ["sim_route_fr"]  # the non-English canary
    assert res["must_smoke"] == ["sim_request_en", "sim_route_fr"]

    # A tool folder the impact map has never seen (new or renamed tool) needs a full run.
    _write(repo / "cxas_app" / "tools" / "brand_new_tool" / "brand_new_tool.json", '{"description": "new"}\n')
    res = impact.analyze_impact(base, root=repo)
    assert res["verdict"] == "FULL"
    assert any("tool brand_new_tool is not in the impact map" in r for r in res["verdict_reasons"])


# ----------------------------------------------------------------------------- bench-full


def test_bench_full_refuses_undeployed_code(repo: Path, capsys) -> None:
    impact.record_push(APP, "git-x", repo)
    _write(repo / "lib" / "fakes.py", "VALID_PINS = frozenset()\nREQUEST_KINDS = ()\n")
    _commit(repo, "not pushed")
    assert impact.check_bench_full_gate(APP, root=repo) is False
    assert "make push ENV=staging" in capsys.readouterr().err


def test_bench_full_bootstrap_and_unchanged_source(repo: Path) -> None:
    impact.record_push(APP, "git-x", repo)
    assert impact.check_bench_full_gate(APP, root=repo) is True  # no baseline full run yet
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)
    _write(repo / "docs" / "notes.md", "docs only\n")
    _commit(repo, "docs only")
    assert impact.check_bench_full_gate(APP, root=repo) is True  # 0 source changes since the full run


def test_bench_full_requires_a_passing_smoke_for_the_current_fingerprint(repo: Path, capsys) -> None:
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)
    _write(repo / "cxas_app" / "agents" / "specialist" / "instruction.txt", "specialist v2\n")
    _commit(repo, "specialist v2")
    impact.record_push(APP, "git-a", repo)
    assert impact.check_bench_full_gate(APP, root=repo) is False
    assert "make smoke-impact ENV=staging" in capsys.readouterr().err

    code, targets = impact.smoke_plan(APP, root=repo)
    assert code == 0 and targets
    smoke = _passing_smoke(repo, targets.split(","))
    assert impact.record_smoke_results(smoke, root=repo) is True
    assert impact.check_bench_full_gate(APP, root=repo) is True

    # A new source commit (pushed) needs a new smoke.
    _write(repo / "cxas_app" / "agents" / "specialist" / "instruction.txt", "specialist v3\n")
    _commit(repo, "specialist v3")
    impact.record_push(APP, "git-b", repo)
    assert impact.check_bench_full_gate(APP, root=repo) is False


def test_bench_full_allows_full_verdict_and_logged_override(repo: Path, capsys) -> None:
    base = _git(repo, "rev-parse", "--short=7", "HEAD")
    _baseline_full_run(repo, base)
    _write(repo / "cxas_app" / "agents" / "router" / "instruction.txt", "router v2\n")
    _commit(repo, "router v2")
    impact.record_push(APP, "git-a", repo)
    assert impact.check_bench_full_gate(APP, skip=True, reason="", root=repo) is False
    assert 'REASON="why the smoke run is skipped"' in capsys.readouterr().err
    assert impact.check_bench_full_gate(APP, skip=True, reason="quota is about to reset", root=repo) is True
    log = (repo / "history" / "impact_gate.log").read_text(encoding="utf-8")
    assert "OVERRIDE bench-full" in log and "reason=quota is about to reset" in log

    _write(repo / "cxas_app" / "app.json", '{"x": 1}\n')
    _commit(repo, "app.json")
    impact.record_push(APP, "git-b", repo)
    assert impact.check_bench_full_gate(APP, root=repo) is True  # verdict FULL


def test_check_smoke_cli_alias_runs_the_bench_full_gate(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(impact, "ROOT", repo)
    monkeypatch.chdir(repo)
    assert impact.main(["--check-smoke", "--app", APP]) == 1  # nothing pushed
    impact.record_push(APP, "git-x", repo)
    assert impact.main(["--check-bench-full", "--app", APP]) == 0


# ----------------------------------------------------------------------------- full-record lookup


def _full_record(root: Path, sha: str, cells: list[tuple[int, int]], **extra: object) -> None:
    per_eval = {
        f"VE-{n:02d}": {"pass": p, "total": t, "verdict": "PASS" if p >= 2 else "FAIL"}
        for n, (p, t) in enumerate(cells, start=1)
    }
    record = {"label": f"full-{sha}", "commit": sha, "is_full_run": True, "runs_per_eval": 3,
              "tool_errors": 0, "per_eval": per_eval}
    record.update(extra)
    _write(root / "history" / "bench" / f"full-{sha}.json", json.dumps(record))


def test_find_full_record_matches_the_same_source_after_a_docs_commit(repo: Path) -> None:
    impact.record_push(APP, "git-x", repo)
    measured = _git(repo, "rev-parse", "--short=7", "HEAD")
    _full_record(repo, measured, [(3, 3)] * 10)
    _commit(repo, "record the full run")  # commits history/bench/full-<sha7>.json: HEAD moves
    assert impact.find_full_record(repo) == repo / "history" / "bench" / f"full-{measured}.json"

    _write(repo / "lib" / "fakes.py", 'VALID_PINS = frozenset({"9876"})\nREQUEST_KINDS = ("statement",)\n')
    _commit(repo, "source change")
    impact.record_push(APP, "git-y", repo)
    assert impact.find_full_record(repo) is None  # the old run measured other code


# ----------------------------------------------------------------------------- Gate 3


def _record(cells: list[tuple[int, int]], **extra: object) -> dict:
    per_eval = {
        f"VE-{n:02d}": {"pass": p, "total": t, "verdict": "PASS" if p >= 2 else "FAIL"}
        for n, (p, t) in enumerate(cells, start=1)
    }
    rec = {"label": "full-abc1234", "commit": "abc1234", "is_full_run": True, "runs_per_eval": 3,
           "tool_errors": 0, "per_eval": per_eval}
    rec.update(extra)
    return rec


@pytest.mark.parametrize(
    ("cells", "extra", "ok"),
    [
        ([(3, 3)] * 45 + [(2, 3)] * 5, {}, True),  # 45/50 strict, 50/50 majority
        ([(3, 3)] * 44 + [(2, 3)] * 6, {}, False),  # 44/50 strict
        ([(3, 3)] * 49 + [(1, 3)], {}, False),  # 49/50 majority
        ([(3, 3)] * 49 + [(2, 2)], {}, False),  # one eval lost a scored try
        ([(3, 3)] * 50, {"tool_errors": 2}, False),
        ([(3, 3)] * 50, {"tool_errors": None}, False),
        ([(3, 3)] * 50, {"is_full_run": False}, False),
    ],
)
def test_gate3_verdict(cells, extra, ok) -> None:
    verdict = bench_summary.gate3_verdict(_record(cells, **extra), {"strict_pass_rate": 0.9, "majority_pass_rate": 1.0})
    assert verdict["pass"] is ok
    assert verdict["line"].startswith("strict 3/3")


def test_gate3_reads_thresholds_and_legacy_keys(tmp_path: Path) -> None:
    th = tmp_path / "th.json"
    th.write_text(json.dumps({"min_strict_pass_rate": 0.8, "majority_pass_rate": 1.0}), encoding="utf-8")
    assert bench_summary.load_gate3_thresholds(th) == {"strict_pass_rate": 0.8, "majority_pass_rate": 1.0}
    kit = bench_summary.load_gate3_thresholds(Path(__file__).resolve().parent.parent / "gate_thresholds.json")
    assert kit == {"strict_pass_rate": 0.9, "majority_pass_rate": 1.0}


def test_gate3_cli(tmp_path: Path, capsys) -> None:
    good = tmp_path / "full-abc1234.json"
    good.write_text(json.dumps(_record([(3, 3)] * 10)), encoding="utf-8")
    assert bench_summary.main(["--gate3", str(good)]) == 0
    assert "Gate 3 PASS" in capsys.readouterr().out
    bad = tmp_path / "full-bad.json"
    bad.write_text(json.dumps(_record([(3, 3)] * 8 + [(2, 3)] * 2)), encoding="utf-8")
    assert bench_summary.main(["--gate3", str(bad)]) == 1
    assert bench_summary.main(["--gate3", str(tmp_path / "missing.json")]) == 1
    assert "make bench-full" in capsys.readouterr().err


def test_record_counts_tool_errors_from_failing_pages(tmp_path: Path) -> None:
    report = {
        "label": "full-abc1234",
        "is_full_run": True,
        "runs_per_eval": 3,
        "results": [
            {"ve_id": "VE-01", "pass_runs": 3, "total_runs": 3, "verdict": "PASS"},
            {"ve_id": "VE-02", "pass_runs": 2, "total_runs": 3, "verdict": "PASS"},
        ],
    }
    assert bench_summary.tool_error_count(tmp_path, "full-abc1234", report)["tool_errors"] is None
    page = {
        "tool_calls": [
            {"type": "tool_response", "payload": {"display_name": "submit_request",
                                                  "response": {"status": "error", "error": "SYSTEM_DOWN"}}},
            {"type": "tool_response", "payload": {"display_name": "check_login_code",
                                                  "response": {"status": "error", "error": "WRONG_CODE"}}},
        ]
    }
    _write(tmp_path / "runs" / "failing_runs_data" / "full-abc1234" / "VE-02__run1__r2.json", json.dumps(page))
    counted = bench_summary.tool_error_count(tmp_path, "full-abc1234", report)
    assert counted["tool_errors"] == 1 and counted["tool_error_pages_checked"] == 1
    all_pass = {"results": [{"ve_id": "VE-01", "pass_runs": 3, "total_runs": 3}]}
    assert bench_summary.tool_error_count(tmp_path, "full-none", all_pass)["tool_errors"] == 0


# ----------------------------------------------------------------------------- suite/gate.py strict 3/3


def _rows(test: str, statuses: list[str], model: str = "m1") -> list[dict]:
    return [
        {"run_id": "r1", "test_id": test, "layer": "sim", "priority": "P1", "repeat": n + 1, "status": s,
         "agent_model": model, "judge_model": "j1"}
        for n, s in enumerate(statuses)
    ]


THRESHOLDS = {
    "measured_on_model": "m1",
    "judge_model": "j1",
    "repeats": {"default": 3},
    "floors": {"sim": 0.8},
    "strict_pass_rate": 0.9,
    "max_infra_ratio": 0.2,
}


def test_gate_fails_when_strict_rate_is_below_the_bar_even_if_majority_passes() -> None:
    rows = sum((_rows(f"s{n}", ["pass", "pass", "fail"]) for n in range(10)), [])
    result = gate.evaluate(rows, THRESHOLDS, "r1")
    assert result["verdict"] == "FAIL"
    assert any("strict 3/3" in r for r in result["reasons"])


def test_gate_passes_at_the_strict_bar_and_reports_it() -> None:
    rows = sum((_rows(f"s{n}", ["pass"] * 3) for n in range(9)), []) + _rows("s9", ["pass", "pass", "fail"])
    result = gate.evaluate(rows, THRESHOLDS, "r1")
    assert result["verdict"] == "PASS"
    assert result["strict"]["passed"] == 9 and result["strict"]["total"] == 10


def test_gate_strict_undecided_by_infra_is_inconclusive_and_legacy_key_works() -> None:
    rows = sum((_rows(f"s{n}", ["pass"] * 3) for n in range(8)), [])
    rows += _rows("s8", ["pass", "pass", "infra_error"]) + _rows("s9", ["pass", "pass", "infra_error"])
    assert gate.evaluate(rows, THRESHOLDS, "r1")["verdict"] == "INCONCLUSIVE"
    legacy = {k: v for k, v in THRESHOLDS.items() if k != "strict_pass_rate"}
    legacy["min_strict_pass_rate"] = 0.9
    failing = sum((_rows(f"s{n}", ["pass", "pass", "fail"]) for n in range(10)), [])
    assert gate.evaluate(failing, legacy, "r1")["verdict"] == "FAIL"


def test_gate_placeholder_model_is_a_note_not_a_failure() -> None:
    th = dict(THRESHOLDS)
    th["measured_on_model"] = "<exact agent model, e.g. from app.json>"
    th["judge_model"] = "<exact judge model, at least as strong as the agent>"
    rows = sum((_rows(f"s{n}", ["pass"] * 3, model="gemini-composite-v1") for n in range(10)), [])
    result = gate.evaluate(rows, th, "r1")
    assert result["verdict"] == "PASS"
    assert any("measured_on_model" in note for note in result["notes"])
    assert "measured_on_model" in gate.to_markdown(result, "r1")


def test_classify_audio_mode_pass_when_goal_and_expectations_satisfied() -> None:
    rec = {
        "execution_state": "COMPLETED",
        "evaluation_status": "FAIL",
        "fallback_reasons": [],
        "scenario_result": {
            "task_completed": False,
            "user_goal_satisfaction_result": {"score": 1, "explanation": "satisfied"},
            "all_expectations_satisfied": True,
            "evaluation_expectation_results": [{"prompt": "p", "outcome": 1}],
            "hallucination_result": [{"score": 1}],
        },
    }
    assert run_bench.classify(rec, modality="text") == ("FAIL", "")
    assert run_bench.classify(rec, modality="audio") == ("PASS", "")


def test_classify_audio_mode_fail_on_expectation_miss() -> None:
    rec = {
        "execution_state": "COMPLETED",
        "evaluation_status": "FAIL",
        "fallback_reasons": [],
        "scenario_result": {
            "task_completed": False,
            "user_goal_satisfaction_result": {"score": 1},
            "all_expectations_satisfied": False,
            "evaluation_expectation_results": [{"prompt": "p", "outcome": 2}],
            "hallucination_result": [{"score": 1}],
        },
    }
    assert run_bench.classify(rec, modality="audio") == ("FAIL", "")


def test_classify_audio_mode_fail_on_goal_zero() -> None:
    rec = {
        "execution_state": "COMPLETED",
        "evaluation_status": "FAIL",
        "fallback_reasons": [],
        "scenario_result": {
            "task_completed": False,
            "user_goal_satisfaction_result": {"score": 0},
            "all_expectations_satisfied": True,
            "evaluation_expectation_results": [{"prompt": "p", "outcome": 1}],
            "hallucination_result": [{"score": 1}],
        },
    }
    assert run_bench.classify(rec, modality="audio") == ("FAIL", "")


def test_classify_audio_mode_fail_on_hallucination_failure() -> None:
    rec = {
        "execution_state": "COMPLETED",
        "evaluation_status": "FAIL",
        "fallback_reasons": [],
        "scenario_result": {
            "task_completed": False,
            "user_goal_satisfaction_result": {"score": 1},
            "all_expectations_satisfied": True,
            "evaluation_expectation_results": [{"prompt": "p", "outcome": 1}],
            "hallucination_result": [{"score": 1}, {"score": 0}],
        },
    }
    assert run_bench.classify(rec, modality="audio") == ("FAIL", "")


def test_classify_audio_mode_preserves_golden_behavior() -> None:
    rec = {
        "execution_state": "COMPLETED",
        "evaluation_status": "FAIL",
        "fallback_reasons": [],
        "raw": {"golden_result": {"turn_replay_results": []}},
    }
    assert run_bench.classify(rec, modality="audio") == ("FAIL", "")
