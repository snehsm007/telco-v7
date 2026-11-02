#!/usr/bin/env python3
"""Turn a public-bench report JSON into a small, committable record.

Why: the full reports written by scripts/run_bench.py live in the bench
directory (``$BENCH_DIR/runs/``, several MB each, with eval names). The
dashboard and the experiment log need a compact, name-free record per
measurement inside the repo: which commit / app version was measured, the
platform run IDs, and the per-eval pass counts by neutral VE id
(DECISIONS.md DD-17).

Usage:
  bench_summary.py <report.json> [--commit <sha7 or text>] [--out-dir history/bench]
  bench_summary.py --compare <before.json> <after.json>   # keep/undo verdict (AGENTS.md rule 22)
      [--kind targeted --targets VE-xx,VE-yy [--gated-by DEF-xx] | --kind hygiene --finding-gone yes|no]
      [--bench-dir $BENCH_DIR] [--history <label>,<label>] [--defects docs/defects.md]
  bench_summary.py --gate3 history/bench/full-<sha7>.json [--thresholds gate_thresholds.json]
      # make gate3: exit 0 only for one complete single-commit full run with strict 3/3 >=
      # strict_pass_rate, majority >= majority_pass_rate and 0 tool errors
  bench_summary.py --self-test

The bench directory defaults to the BENCH_DIR environment variable, else
<repo>/bench (the same default as the Makefile and run_bench.py).

The compare reads the failing-conversation pages under
<bench-dir>/runs/failing_runs_data/<label>/ for the failure-shape check and the
partial outcome of DD-27 (see compare() and load_shapes()). The output file
name is the report label (``unstable-<sha7>`` etc.). Nothing in the output
contains an eval display name.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts import build_dashboard  # noqa: E402  (page attribution: handover, judge)

DEFAULT_OUT_DIR = REPO_ROOT / "history" / "bench"
DEFAULT_BENCH_ROOT = Path(os.environ.get("BENCH_DIR") or REPO_ROOT / "bench")
DEFAULT_DEFECTS = REPO_ROOT / "docs" / "defects.md"
SHA_IN_LABEL = re.compile(r"(?:unstable|full|holdout|smoke)-([0-9a-f]{7,40})$")

# Names of the judge metrics inside a failure shape.
EXPECTATION_PREFIX = "expectation: "
GOAL_METRIC = "user_goal"
HALLUCINATION_METRIC = "hallucination"
OTHER_METRIC = "other (no judge metric failed)"
EFFICIENCY_TURN_WARN_DELTA = 1.5


def load_id_map(path: Path) -> dict[str, str]:
    """Read `| VE-01 | <display name> | …` rows from the (outside-repo) id map."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(VE-\d+)\s*\|\s*(\S+)\s*\|", line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def _extract_eval_efficiency(r: dict) -> tuple[float | None, float | None]:
    """Return (avg_pass_turns, avg_pass_tool_calls) for one eval result entry (with raw_runs fallback)."""
    t_val = r.get("avg_pass_turns")
    tc_val = r.get("avg_pass_tool_calls")
    if t_val is not None or tc_val is not None:
        return (
            round(float(t_val), 2) if t_val is not None else None,
            round(float(tc_val), 2) if tc_val is not None else None,
        )
    turns_list: list[int] = []
    tools_list: list[int] = []
    for raw in r.get("raw_runs") or []:
        if not isinstance(raw, dict):
            continue
        state = raw.get("execution_state")
        status = raw.get("evaluation_status")
        if state not in (2, "COMPLETED") or status not in (1, "PASS"):
            continue
        sr = raw.get("scenario_result") or {}
        gr = raw.get("golden_result") or {}
        if isinstance(sr.get("hallucination_result"), list) and sr["hallucination_result"]:
            turns_list.append(len(sr["hallucination_result"]))
        elif isinstance(gr.get("turn_replay_results"), list) and gr["turn_replay_results"]:
            turns_list.append(len(gr["turn_replay_results"]))
        if isinstance(sr.get("tool_call_latencies"), list):
            tools_list.append(len(sr["tool_call_latencies"]))
        elif isinstance(gr.get("turn_replay_results"), list) and gr["turn_replay_results"]:
            tools_list.append(
                sum(len(tr.get("tool_call_latencies") or []) for tr in gr["turn_replay_results"] if isinstance(tr, dict))
            )
    return (
        round(sum(turns_list) / len(turns_list), 2) if turns_list else None,
        round(sum(tools_list) / len(tools_list), 2) if tools_list else None,
    )


def summarize(
    report: dict,
    commit: str | None = None,
    label: str | None = None,
    id_map: dict[str, str] | None = None,
) -> dict:
    """Reduce a run_bench report to the fields the repo keeps."""
    label = label or str(report.get("label") or "unlabelled")
    if commit is None:
        m = SHA_IN_LABEL.search(label)
        commit = m.group(1) if m else ""
    per_eval = {}
    for r in report.get("results", []):
        ve = r.get("ve_id") or (id_map or {}).get(str(r.get("display_name", "")))
        if not ve:
            continue
        verdict = r.get("verdict")
        if not verdict:  # old reports only carry a boolean
            verdict = "PASS" if str(r.get("passed")).lower() == "true" else "FAIL"
        avg_turns, avg_tools = _extract_eval_efficiency(r)
        cell: dict = {
            "pass": int(r.get("pass_runs", 0)),
            "total": int(r.get("total_runs", 0)),
            "infra": int(r.get("infra_runs", 0)),
            "verdict": verdict,
        }
        if avg_turns is not None:
            cell["avg_pass_turns"] = avg_turns
        if avg_tools is not None:
            cell["avg_pass_tool_calls"] = avg_tools
        per_eval[ve] = cell
    runs = [str(x).rsplit("/", 1)[-1] for x in report.get("evaluation_runs", [])]
    passes = sum(v["pass"] for v in per_eval.values())
    total = sum(v["total"] for v in per_eval.values())
    evals_cnt = len(per_eval)
    strict = sum(1 for v in per_eval.values() if v["pass"] == v["total"] and v["total"] > 0)
    majority = sum(1 for v in per_eval.values() if v["verdict"] == "PASS")
    strict_rate = round(strict / evals_cnt, 4) if evals_cnt else 0.0
    majority_rate = round(majority / evals_cnt, 4) if evals_cnt else 0.0
    p_val = round(passes / total, 4) if total else 0.0
    predicted_strict = round(evals_cnt * (p_val ** 3), 2)
    commits = list(report.get("commits") or ([commit] if commit else []))
    app_versions = list(report.get("app_versions_seen", report.get("app_versions", [])))
    is_holdout = bool(report.get("is_holdout", False)) or ("holdout" in label.lower())
    is_full_run = bool(
        report.get("is_full_run", False)
        and not is_holdout
        and len(commits) <= 1
        and len(app_versions) <= 1
        and not report.get("app_update_time_changed")
    )
    turn_vals = [v["avg_pass_turns"] for v in per_eval.values() if v.get("avg_pass_turns") is not None]
    tool_vals = [v["avg_pass_tool_calls"] for v in per_eval.values() if v.get("avg_pass_tool_calls") is not None]
    out = {
        "label": label,
        "timestamp": report.get("timestamp", ""),
        "commit": commit,
        "git_sha": commit,
        "commits": commits,
        # Full app resource (projects/…/apps/<id>) so the dashboard can link to the
        # CES console without knowing the project; empty for reports that predate it.
        "app_resource": str(report.get("app_resource") or ""),
        "app_versions": app_versions,
        "evaluation_runs": runs,
        "runs_per_eval": int(report.get("runs_per_eval", 0)),
        "is_full_run": is_full_run,
        "is_holdout": is_holdout,
        "eval_count": evals_cnt,
        "evals": evals_cnt,
        "strict_pass": strict,
        "strict_pass_rate": strict_rate,
        "majority_pass": majority,
        "majority_pass_rate": majority_rate,
        "individual_passed": passes,
        "individual_total": total,
        "passes": passes,
        "total": total,
        "p": p_val,
        "predicted_strict_3_of_3": predicted_strict,
        "avg_pass_turns": round(sum(turn_vals) / len(turn_vals), 2) if turn_vals else None,
        "avg_pass_tool_calls": round(sum(tool_vals) / len(tool_vals), 2) if tool_vals else None,
        "per_eval": dict(sorted(per_eval.items())),
    }
    return out


def validate_full_summary(summary: dict) -> None:
    """Refuse to write a `full-*.json` summary if it is a holdout, subset, or multi-SHA/version run."""
    if summary.get("is_holdout"):
        raise ValueError("Holdout runs must never be written as full-*.json")
    if not summary.get("is_full_run"):
        raise ValueError("Subset/targeted runs must never be written as full-*.json")
    if len(summary.get("commits") or []) > 1:
        raise ValueError(f"Multi-commit run ({summary.get('commits')}) cannot be recorded as full-*.json")
    if len(summary.get("app_versions") or []) > 1:
        raise ValueError(f"Multi-version run ({summary.get('app_versions')}) cannot be recorded as full-*.json")


# ------------------------------------------------------------ Gate 3 (make gate3)

GATE3_DEFAULTS = {"strict_pass_rate": 0.90, "majority_pass_rate": 1.00}


def tool_error_count(bench_root: Path | str, label: str, report: dict | None = None) -> dict:
    """Unexpected (non-business-rule) tool errors in a run's failing-conversation pages.

    A full run fetches only the conversations that did not pass, so this counts the
    tool errors in those pages (<bench-dir>/runs/failing_runs_data/<label>/). Business
    errors a test expects, such as WRONG_CODE, do not count. `tool_errors` is None
    (unknown) when conversations failed but none of their pages can be found.
    """
    from scripts import run_bench  # local import: run_bench pulls in the cloud helpers

    folder = Path(bench_root) / "runs" / "failing_runs_data" / str(label)
    pages = sorted(folder.glob("*.json")) if folder.is_dir() else []
    errors: list[dict] = []
    checked = 0
    for path in pages:
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(page, dict):
            continue
        checked += 1
        for err in run_bench.tool_errors(page.get("tool_calls") or []):
            if not err.get("business_rule"):
                errors.append({"page": path.stem, "tool": err.get("tool", ""), "error": err.get("error", "")})
    not_passed = 0
    for r in (report or {}).get("results", []) or []:
        total, passed = int(r.get("total_runs") or 0), int(r.get("pass_runs") or 0)
        not_passed += max(total - passed, 0) + int(r.get("infra_runs") or 0)
    known = checked > 0 or not_passed == 0
    return {
        "tool_errors": len(errors) if known else None,
        "tool_error_pages_checked": checked,
        "tool_error_samples": errors[:5],
    }


def load_gate3_thresholds(path: Path | str | None = None) -> dict:
    """The strict 3/3 and majority bars from gate_thresholds.json (legacy min_* keys accepted)."""
    data: dict = {}
    try:
        loaded = json.loads(Path(path or REPO_ROOT / "gate_thresholds.json").read_text(encoding="utf-8"))
        data = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        data = {}
    floors = data.get("floors") if isinstance(data.get("floors"), dict) else {}
    out = {}
    for key in ("strict_pass_rate", "majority_pass_rate"):
        value = data.get(key, data.get(f"min_{key}", floors.get(key, GATE3_DEFAULTS[key])))
        out[key] = float(value)
    return out


def gate3_verdict(record: dict, thresholds: dict | None = None) -> dict:
    """Gate 3 on one full-run record (history/bench/full-<sha7>.json or a raw report).

    PASS only when all hold: a clean single-commit full run (is_full_run), every eval
    scored on all of its tries (runs_per_eval >= 3; a partial run is never scored),
    strict 3/3 rate >= strict_pass_rate, majority rate >= majority_pass_rate, and 0
    unexpected tool errors.
    """
    th = dict(GATE3_DEFAULTS)
    th.update(thresholds or {})
    if "per_eval" not in record and "results" in record:
        record = summarize(record)
    per_eval = record.get("per_eval") or {}
    n = len(per_eval)
    runs = int(record.get("runs_per_eval") or 0)
    reasons: list[str] = []
    if not record.get("is_full_run"):
        reasons.append(
            "not a clean single-commit full run (is_full_run is false: a holdout or subset run, "
            "several commits or app versions, or the app changed mid-run)"
        )
    if n == 0:
        reasons.append("the record has no evaluations")
    if runs < 3:
        reasons.append(f"strict 3/3 needs at least 3 tries per evaluation; this run used {runs}")
    incomplete = sorted(ve for ve, c in per_eval.items() if int(c.get("total", 0)) < max(runs, 1))
    if incomplete:
        reasons.append(
            f"incomplete run: {len(incomplete)} evaluation(s) have fewer than {runs} scored tries "
            f"({', '.join(incomplete[:5])}{', ...' if len(incomplete) > 5 else ''}); re-run instead "
            "of scoring a partial run"
        )
    strict = sum(
        1 for c in per_eval.values() if int(c.get("total", 0)) >= max(runs, 1) and c.get("pass") == c.get("total")
    )
    majority = sum(1 for c in per_eval.values() if c.get("verdict") == "PASS")
    passes = sum(int(c.get("pass", 0)) for c in per_eval.values())
    total = sum(int(c.get("total", 0)) for c in per_eval.values())
    strict_rate = strict / n if n else 0.0
    majority_rate = majority / n if n else 0.0
    if n and strict_rate + 1e-9 < th["strict_pass_rate"]:
        reasons.append(f"strict 3/3 {strict}/{n} ({strict_rate:.1%}) is below {th['strict_pass_rate']:.0%}")
    if n and majority_rate + 1e-9 < th["majority_pass_rate"]:
        below = sorted(ve for ve, c in per_eval.items() if c.get("verdict") != "PASS")
        reasons.append(
            f"majority {majority}/{n} ({majority_rate:.1%}) is below {th['majority_pass_rate']:.0%} "
            f"(no majority: {', '.join(below[:8])}{', ...' if len(below) > 8 else ''})"
        )
    tool_errors = record.get("tool_errors")
    if tool_errors is None:
        reasons.append(
            "tool errors are not recorded in this file; re-record it from the run's report: "
            "make bench-record REPORT=<bench dir>/runs/<label>.json"
        )
    elif int(tool_errors) > 0:
        reasons.append(f"{tool_errors} unexpected tool error(s) in the failing conversations")
    commit = str(record.get("commit") or record.get("git_sha") or "?")
    line = (
        f"strict 3/3 {strict}/{n} ({strict_rate:.1%}, needs >= {th['strict_pass_rate']:.0%}) | "
        f"majority >=2/3 {majority}/{n} ({majority_rate:.1%}, needs >= {th['majority_pass_rate']:.0%}) | "
        f"individual {passes}/{total} ({(passes / total if total else 0.0):.1%}) | "
        f"tool errors {'not recorded' if tool_errors is None else tool_errors} | "
        f"single-commit full run: {'yes' if record.get('is_full_run') else 'no'} (commit {commit})"
    )
    return {
        "pass": not reasons,
        "verdict": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "line": line,
        "strict_pass": strict,
        "majority_pass": majority,
        "evals": n,
        "label": str(record.get("label") or ""),
    }


def run_gate3(path: Path | str, thresholds_path: Path | str | None = None, bench_dir: Path | str | None = None) -> int:
    """`make gate3`: print the Gate 3 verdict for one record; exit 0 PASS, 1 FAIL."""
    p = Path(path)
    if not p.is_file():
        print(
            f"Gate 3: no record at {p}. Run `make bench-full ENV=<env>` first (it writes "
            "history/bench/full-<sha7>.json), or pass REPORT=<file>.",
            file=sys.stderr,
        )
        return 1
    try:
        record = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Gate 3: cannot read {p}: {exc}", file=sys.stderr)
        return 1
    if "per_eval" not in record and "results" in record:  # a raw run_bench report
        summary = summarize(record)
        summary.update(tool_error_count(bench_dir or DEFAULT_BENCH_ROOT, summary["label"], record))
        record = summary
    verdict = gate3_verdict(record, load_gate3_thresholds(thresholds_path))
    print(f"Gate 3 {verdict['verdict']} ({p.name}): {verdict['line']}")
    for reason in verdict["reasons"]:
        print(f"  - {reason}")
    if not verdict["pass"]:
        print(
            "Gate 3 needs strict 3/3 >= the strict_pass_rate in gate_thresholds.json, every evaluation "
            "passing by majority, 0 tool errors, and one complete single-commit full run."
        )
    return 0 if verdict["pass"] else 1


def _fraction(cell: dict) -> float:
    return cell["pass"] / cell["total"] if cell["total"] else 0.0


# ------------------------------------------------------------ failure shapes (DD-27)


def _judge_items(value: object) -> list[dict]:
    """A judge sub-result arrives as a dict or as a list of dicts (one per turn)."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _outcome_name(outcome: object) -> str:
    if isinstance(outcome, int):
        return build_dashboard.OUTCOME_NAMES.get(outcome, str(outcome))
    return str(outcome or "")


def conversation_shape(page: dict, stem: str = "") -> dict:
    """The failure shape of one failing conversation (AGENTS.md rule 22, DD-27).

    metrics: the judge metrics that failed — "expectation: <prompt>" for every
    failed expectation, "user_goal" when the goal scored 0, "hallucination" when
    any turn scored 0 (the hallucination result is a per-turn list; the first
    entry alone is not enough). handover: the reason of the first
    execute_live_agent_handover call, or "" when there was none. The defect id
    is attached per eval from docs/defects.md (see load_shapes). signal is the
    dashboard's one-line attribution (tool error / handover), kept for reading.
    """
    att = build_dashboard.attribute_failure(page)
    judge = page.get("judge") or {}
    expectations = judge.get("evaluation_expectation_results") or []
    goals = _judge_items(judge.get("user_goal_satisfaction_result"))
    metrics, passed = [], []
    for exp in expectations:
        prompt = str(exp.get("prompt") or "")
        name = _outcome_name(exp.get("outcome"))
        if name == "FAIL":
            metrics.append(EXPECTATION_PREFIX + prompt)
        elif name == "PASS":
            passed.append(prompt)
    if any(g.get("score") == 0 for g in goals):
        metrics.append(GOAL_METRIC)
    hallucinations = _judge_items(judge.get("hallucination_result"))
    if any(h.get("score") == 0 for h in hallucinations):
        metrics.append(HALLUCINATION_METRIC)
    known = bool(expectations or goals)
    if known and not metrics:
        metrics = [OTHER_METRIC]
    return {
        "stem": stem or f"{page.get('ve_id')}__r{page.get('slot')}",
        "metrics": sorted(metrics),
        "passed_expectations": sorted(passed),
        "handover": str((att["handover"] or {}).get("reason") or ""),
        "signal": att["signal"],
        "metrics_known": known,
    }


def load_run_shapes(folder: Path) -> dict:
    """FAIL pages of one run folder grouped by VE id, plus the run's first result time."""
    shapes: dict[str, list[dict]] = defaultdict(list)
    first_result = ""
    for path in sorted(folder.glob("VE-*.json")):
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        created = str((page.get("result_raw") or {}).get("create_time") or "")[:19]
        if created and (not first_result or created < first_result):
            first_result = created
        if str(page.get("classification") or page.get("evaluation_status")) != "FAIL":
            continue  # INFRA pages: re-run by the bench, never a failure of the agent
        ve = str(page.get("ve_id") or path.stem.split("__")[0])
        shapes[ve].append(conversation_shape(page, path.stem))
    return {"shapes": dict(shapes), "first_result": first_result}


def pick_history(
    runs: dict[str, dict], before_label: str, after_label: str, after_timestamp: str
) -> list[str]:
    """BEFORE's folder plus every folder whose first platform result is older than AFTER's."""
    after_time = (runs.get(after_label) or {}).get("first_result") or str(
        after_timestamp or ""
    )[:19]
    names = []
    for name, run in runs.items():
        if name == after_label:
            continue
        if name.startswith("smoke-") and name != before_label:
            continue
        older = bool(
            after_time and run["first_result"] and run["first_result"] < after_time
        )
        if name == before_label or older:
            names.append(name)
    return sorted(names, key=lambda n: runs[n]["first_result"])


def build_record(runs: dict[str, dict], names: list[str]) -> dict[str, dict]:
    """Per eval: every failing metric and handover reason seen in the named runs."""
    record: dict[str, dict] = {}
    for name in names:
        for ve, convs in runs[name]["shapes"].items():
            entry = record.setdefault(
                ve, {"metrics": set(), "handovers": set(), "runs": []}
            )
            for c in convs:
                if c["metrics_known"]:
                    entry["metrics"].update(c["metrics"])
                    entry["handovers"].add(c["handover"])
            entry["runs"].append(name)
    return record


def load_shapes(
    bench_root: Path | str,
    before: dict,
    after: dict,
    history: list[str] | None = None,
    defects_path: Path | str | None = None,
) -> dict:
    """Read the failing-conversation pages that compare() needs for DD-27.

    Pages: <bench_root>/runs/failing_runs_data/<label>/VE-xx__<run8>__rN.json
    (written by run_bench.py). "On record" for an eval = the shapes seen
    in BEFORE's pages plus every other folder whose first platform result is
    older than AFTER's first result (AFTER's record time when AFTER has no
    pages). `history` names the folders explicitly instead; BEFORE's folder is
    always part of the record and AFTER's never is. Runs of older agent
    versions count on purpose: the rule asks whether the shape was ever seen
    on that eval, and the output names the runs the record came from.
    """
    pages_root = Path(bench_root) / "runs" / "failing_runs_data"
    runs: dict[str, dict] = {}
    if pages_root.is_dir():
        for folder in sorted(p for p in pages_root.iterdir() if p.is_dir()):
            runs[folder.name] = load_run_shapes(folder)
    before_label, after_label = str(before.get("label")), str(after.get("label"))
    missing: list[str] = []
    if history is None:
        names = pick_history(
            runs, before_label, after_label, str(after.get("timestamp") or "")
        )
    else:
        wanted = list(dict.fromkeys([Path(h).name for h in history] + [before_label]))
        missing = [n for n in wanted if n not in runs and n != before_label]
        names = sorted(
            (n for n in wanted if n in runs and n != after_label),
            key=lambda n: runs[n]["first_result"],
        )
    defects, by_ve = build_dashboard.parse_defects(
        Path(defects_path or DEFAULT_DEFECTS)
    )
    return {
        "pages_root": str(pages_root),
        "after": (runs.get(after_label) or {}).get("shapes"),  # None: no folder
        "before": (runs.get(before_label) or {}).get("shapes"),
        "record": build_record(runs, names),
        "history_runs": names,
        "history_missing": missing,
        "defects_by_ve": by_ve,
        "defect_ids": [d["id"] for d in defects],
    }


def _empty_record() -> dict:
    return {"metrics": set(), "handovers": set(), "runs": []}


def _new_components(metrics: list[str], handover: str, record: dict) -> list[str]:
    """Parts of a failure shape never seen before on this eval (empty = on record)."""
    new = [m for m in metrics if m not in record["metrics"]]
    if handover not in record["handovers"]:
        new.append(f"handover {handover or 'none'}")
    return new


def _pass_text(before_cell: dict, after_cell: dict) -> str:
    return (
        f"{before_cell['pass']}/{before_cell['total']} -> "
        f"{after_cell['pass']}/{after_cell['total']}"
    )


def check_fall(ve: str, before_cell: dict, after_cell: dict, shapes: dict) -> dict:
    """noise / regression / unknown for one eval that fell (rule 22, DD-27)."""
    record = shapes["record"].get(ve) or _empty_record()
    convs = (shapes["after"] or {}).get(ve, [])
    conversations = []
    for c in convs:
        new = (
            _new_components(c["metrics"], c["handover"], record)
            if c["metrics_known"]
            else ["judge data missing"]
        )
        conversations.append(
            {
                "stem": c["stem"],
                "metrics": c["metrics"],
                "handover": c["handover"],
                "signal": c["signal"],
                "new": new,
            }
        )
    expected = after_cell["total"] - after_cell["pass"]
    note = ""
    if shapes["after"] is None:
        result = "unknown"
        note = f"no failing-conversation pages for AFTER under {shapes['pages_root']}"
    elif len(convs) < expected:
        result = "unknown"
        note = f"only {len(convs)} of {expected} failing conversations have a page"
    elif any(not c["metrics_known"] for c in convs):
        result = "unknown"
        note = "judge data missing in " + ", ".join(
            c["stem"] for c in convs if not c["metrics_known"]
        )
    elif any(c["new"] for c in conversations):
        result = "regression"
    else:
        result = "noise"
    return {
        "pass": _pass_text(before_cell, after_cell),
        "result": result,
        "note": note,
        "defects": shapes["defects_by_ve"].get(ve, []),
        "record_runs": record["runs"],
        "conversations": conversations,
    }


def _metric_passes(cell: dict, failing: list[dict], metric: str) -> tuple[int, int]:
    """(conversations where the metric passed, conversations accounted for) in one run.

    Passing conversations have no page, so every metric passed there; failing
    conversations are read from their pages.
    """
    if metric.startswith(EXPECTATION_PREFIX):
        prompt = metric[len(EXPECTATION_PREFIX) :]
        ok = sum(
            1
            for c in failing
            if c["metrics_known"] and prompt in c["passed_expectations"]
        )
    else:
        ok = sum(
            1 for c in failing if c["metrics_known"] and metric not in c["metrics"]
        )
    return cell["pass"] + ok, cell["pass"] + len(failing)


def _flipped_to_pass(before: tuple[int, int], after: tuple[int, int]) -> bool:
    """Now passes in >= 4/5, after gaining >= 3/5 (or >= 2/5 when it reaches n/n)."""
    (b_ok, _), (a_ok, a_n) = before, after
    if not a_n or a_ok / a_n < 0.8:
        return False
    return a_ok - b_ok >= 3 or (a_ok == a_n and a_ok - b_ok >= 2)


def target_detail(ve: str, before_cell: dict, after_cell: dict, shapes: dict) -> dict:
    """Per-metric pass counts of a target before/after and whether it is gated (partial)."""
    b_fail = (shapes["before"] or {}).get(ve, [])
    a_fail = (shapes["after"] or {}).get(ve, [])
    record = shapes["record"].get(ve) or _empty_record()
    names = {m for c in b_fail + a_fail for m in c["metrics"]}
    names |= {
        EXPECTATION_PREFIX + p
        for c in b_fail + a_fail
        for p in c["passed_expectations"]
    }
    names |= {GOAL_METRIC, HALLUCINATION_METRIC}
    metrics, fixed = {}, []
    for m in sorted(names):
        b = _metric_passes(before_cell, b_fail, m)
        a = _metric_passes(after_cell, a_fail, m)
        metrics[m] = {"before": f"{b[0]}/{b[1]}", "after": f"{a[0]}/{a[1]}"}
        if m.startswith(EXPECTATION_PREFIX) and _flipped_to_pass(b, a):
            fixed.append(m)
    complete = {
        "before": before_cell["pass"] + len(b_fail) == before_cell["total"],
        "after": after_cell["pass"] + len(a_fail) == after_cell["total"],
    }
    remaining = []
    for c in a_fail:
        left = [m for m in c["metrics"] if m not in fixed]
        remaining.append(
            {
                "stem": c["stem"],
                "metrics": left,
                "handover": c["handover"],
                "new": _new_components(left, c["handover"], record),
            }
        )
    on_record = bool(remaining) and all(
        r["metrics"] and not r["new"] for r in remaining
    )
    return {
        "pass": _pass_text(before_cell, after_cell),
        "metrics": metrics,
        "fixed_expectations": [m[len(EXPECTATION_PREFIX) :] for m in fixed],
        "remaining_after": remaining,
        "remaining_on_record": on_record,
        "pages_complete": complete,
        "record_runs": record["runs"],
        "defects": shapes["defects_by_ve"].get(ve, []),
        "gated": bool(fixed) and complete["before"] and complete["after"] and on_record,
        "status": "",
    }


def _short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _metric_text(metric: str) -> str:
    if metric.startswith(EXPECTATION_PREFIX):
        return f"expectation '{_short(metric[len(EXPECTATION_PREFIX) :])}'"
    return {
        GOAL_METRIC: "user goal not completed",
        HALLUCINATION_METRIC: "hallucination",
    }.get(metric, metric)


def _describe_shapes(conversations: list[dict]) -> str:
    """'expectation 'x' + hallucination with handover y (x2); …' for a reasons line."""
    counts = Counter((tuple(c["metrics"]), c["handover"]) for c in conversations)
    parts = []
    for (metrics, handover), n in counts.most_common():
        what = " + ".join(_metric_text(m) for m in metrics) or "no judge metric"
        where = f"handover {handover}" if handover else "no handover"
        parts.append(f"{what} with {where} (x{n})")
    return "; ".join(parts)


def _fall_reason(ve: str, check: dict) -> str:
    runs = ", ".join(check["record_runs"]) or "no earlier failing pages"
    defects = f"; {', '.join(check['defects'])}" if check["defects"] else ""
    n = len(check["conversations"])
    if check["result"] == "noise":
        return (
            f"{ve} fell {check['pass']}: all {n} failing conversations show shapes "
            f"already on record for {ve} (runs: {runs}{defects}): "
            f"{_describe_shapes(check['conversations'])} -> noise, not a regression (DD-27)"
        )
    if check["result"] == "regression":
        fresh = [c for c in check["conversations"] if c["new"]]
        parts = sorted({p for c in fresh for p in c["new"]})
        return (
            f"{ve} fell {check['pass']}: {len(fresh)} of {n} failing conversations show "
            f"a shape new for {ve} (never seen in {runs}): {'; '.join(parts)} -> "
            "counts as a regression"
        )
    return (
        f"{ve} fell {check['pass']}: {check['note']} -> cannot tell noise from a "
        "regression; read the pages by hand or pass --bench-dir / --history"
    )


def _target_reason(ve: str, detail: dict, gated_by: str | None, gated_ok: bool) -> str:
    fixed = "; ".join(
        f"expectation '{_short(p)}' {detail['metrics'][EXPECTATION_PREFIX + p]['before']}"
        f" -> {detail['metrics'][EXPECTATION_PREFIX + p]['after']}"
        for p in detail["fixed_expectations"]
    )
    text = f"{ve} {detail['pass']}: {fixed} (fixed)"
    if detail["status"] == "satisfied":
        return text
    if not detail["gated"]:
        if detail["remaining_after"] and not detail["remaining_on_record"]:
            return (
                text + ", but the remaining failures include a shape new for "
                f"{ve}: {_describe_shapes(detail['remaining_after'])} -> not partial"
            )
        return text
    runs = ", ".join(detail["record_runs"]) or "no earlier failing pages"
    text += (
        f", but every failing conversation still fails on "
        f"{_describe_shapes(detail['remaining_after'])}, a shape on record for {ve} "
        f"(runs: {runs})"
    )
    if gated_ok:
        return (
            text + f"; gated by {gated_by} (listed in docs/defects.md) -> partial: "
            "keep as a prerequisite, never as progress; the eval joins that defect's iteration"
        )
    if gated_by:
        return (
            text + f"; --gated-by {gated_by} is not a DEF id listed in docs/defects.md "
            "-> name the listed defect to record partial, otherwise undo"
        )
    return (
        text + "; if that remaining failure is a listed defect, rerun with "
        "--gated-by DEF-xx to record it as partial; otherwise the target did not gain -> undo"
    )


def _target_satisfied(before_cell: dict, after_cell: dict) -> bool:
    """Gains >= 3/5; a target with nothing to gain, or one that reaches n/n after gaining >= 2/5, counts too."""
    delta = after_cell["pass"] - before_cell["pass"]
    if before_cell["pass"] == before_cell["total"] or delta >= 3:
        return True
    return after_cell["pass"] == after_cell["total"] and delta >= 2


def compare(
    before: dict,
    after: dict,
    kind: str = "hygiene",
    targets: tuple[str, ...] | list[str] = (),
    finding_gone: bool | None = None,
    shapes: dict | None = None,
    gated_by: str | None = None,
) -> dict:
    """Apply AGENTS.md rule 22 (amended 2026-10-05, DD-27) over the common evals.

    kind="targeted": keep when every target is satisfied (gains >= 3/5; a
      target already at n/n, or one that reaches n/n after gaining >= 2/5,
      counts as satisfied), no other eval falls by >= 2/5 and the total does
      not drop.
    kind="hygiene": keep when the judge finding is gone (finding_gone=True; the
      human/agent confirms this from the transcripts, the tool cannot), no eval
      falls from >= 4/5 to <= 2/5, and the total drops by at most 3.
    Failure-shape check (DD-27, needs `shapes` from load_shapes): a fall on a
      non-target eval counts only when one of its failing conversations shows a
      metric or handover reason never seen on that eval before ("new shape");
      the same old shapes are noise. A fall whose pages cannot be read makes
      the verdict "needs_check". shapes=None skips the check (numbers only).
    Partial (DD-27): a target whose judge expectation flipped to PASS in >= 4/5
      while every failing conversation still fails on an old shape is "gated";
      with gated_by=<DEF id listed in docs/defects.md> the verdict is "partial"
      (kept as a prerequisite, never progress), without it "needs_check".
    Ambiguous (a target gains 1-2/5, or an eval falls by exactly 2/5 with a new
      shape while the total rises) -> "rerun": measure once more and pool.
      Otherwise "undo".
    """
    if kind not in ("targeted", "hygiene"):
        raise ValueError(f"kind must be targeted or hygiene, got {kind!r}")
    if "per_eval" not in before and "results" in before:
        before = summarize(before)
    if "per_eval" not in after and "results" in after:
        after = summarize(after)
    common = sorted(set(before["per_eval"]) & set(after["per_eval"]))
    targets = [t for t in targets if t in common]
    b = sum(before["per_eval"][v]["pass"] for v in common)
    a = sum(after["per_eval"][v]["pass"] for v in common)
    gain = a - b
    collapsed, fell_two, fell_more = [], [], []
    target_gain: dict[str, int] = {}
    for v in common:
        pb, pa = before["per_eval"][v], after["per_eval"][v]
        delta = pa["pass"] - pb["pass"]
        if _fraction(pb) >= 0.8 and _fraction(pa) <= 0.4:
            collapsed.append(v)
        if v in targets:
            target_gain[v] = delta
        elif delta == -2:
            fell_two.append(v)
        elif delta < -2:
            fell_more.append(v)

    # DD-27: a fall on an eval the change does not target counts only with a new shape.
    shape_check: dict[str, dict] = {}
    noise, regressions, unknown = [], [], []
    if shapes is not None:
        for v in sorted(set(collapsed + fell_two + fell_more) - set(targets)):
            check = check_fall(v, before["per_eval"][v], after["per_eval"][v], shapes)
            shape_check[v] = check
            if check["result"] == "regression":
                regressions.append(v)
                continue
            (noise if check["result"] == "noise" else unknown).append(v)
            for bucket in (collapsed, fell_two, fell_more):
                if v in bucket:
                    bucket.remove(v)

    gated_by = (gated_by or "").strip() or None
    known_ids = shapes["defect_ids"] if shapes else []
    gated_ok = bool(gated_by) and (not known_ids or gated_by in known_ids)
    targets_detail: dict[str, dict] = {}
    if shapes is not None and kind == "targeted":
        for t in targets:
            targets_detail[t] = target_detail(
                t, before["per_eval"][t], after["per_eval"][t], shapes
            )

    reasons: list[str] = []
    gated, pending = [], []
    if kind == "targeted":
        weak = []
        for t in targets:
            if _target_satisfied(before["per_eval"][t], after["per_eval"][t]):
                status = "satisfied"
            elif targets_detail.get(t, {}).get("gated"):
                status = "gated" if gated_ok else "gated_pending"
                (gated if gated_ok else pending).append(t)
            else:
                status = "weak"
                weak.append(t)
            if t in targets_detail:
                targets_detail[t]["status"] = status
        if collapsed or fell_more or gain < 0 or (fell_two and gain <= 0):
            verdict = "undo"
        elif any(1 <= target_gain[v] <= 2 for v in weak) or fell_two:
            verdict = "rerun"
        elif weak:
            verdict = "undo"
        elif gated:
            verdict = "partial"
        else:
            verdict = "keep"
        reasons.append(f"targets {target_gain or 'none in common evals'}")
    else:
        if finding_gone is None:
            verdict = "needs_check"
            reasons.append(
                "hygiene fix: confirm from the new transcripts that the judge finding is gone, "
                "then rerun with --finding-gone yes|no"
            )
        elif not finding_gone or collapsed or gain < -3:
            verdict = "undo"
        elif fell_two and gain > 0:
            verdict = "rerun"
        else:
            verdict = "keep"
    if unknown and verdict in ("keep", "partial", "rerun"):
        verdict = "needs_check"
    if pending and verdict in ("keep", "partial"):
        verdict = "needs_check"

    if verdict == "rerun":
        reasons.append("ambiguous under rule 22: run bench-unstable once more and pool")
    if collapsed:
        reasons.append(f"collapsed (>=4/5 -> <=2/5): {collapsed}")
    if fell_two:
        reasons.append(f"fell by exactly 2/5: {fell_two}")
    if fell_more:
        reasons.append(f"fell by 3/5 or more: {fell_more}")
    for v, check in shape_check.items():
        reasons.append(_fall_reason(v, check))
    for t, detail in targets_detail.items():
        if detail["fixed_expectations"]:
            reasons.append(_target_reason(t, detail, gated_by, gated_ok))
    if gated_by and not gated and not pending:
        reasons.append(
            f"--gated-by {gated_by} given, but no target has an expectation that flipped "
            "to PASS in >= 4/5 while the rest of its failure is an old shape -> ignored"
        )
    reasons.append(f"total {b} -> {a} ({gain:+d})")

    # Passing-only efficiency comparison (turns and tool calls)
    both_turn_evals = [
        v
        for v in common
        if before["per_eval"][v].get("avg_pass_turns") is not None
        and after["per_eval"][v].get("avg_pass_turns") is not None
    ]
    both_tool_evals = [
        v
        for v in common
        if before["per_eval"][v].get("avg_pass_tool_calls") is not None
        and after["per_eval"][v].get("avg_pass_tool_calls") is not None
    ]
    b_turns = (
        round(sum(before["per_eval"][v]["avg_pass_turns"] for v in both_turn_evals) / len(both_turn_evals), 2)
        if both_turn_evals
        else before.get("avg_pass_turns")
    )
    a_turns = (
        round(sum(after["per_eval"][v]["avg_pass_turns"] for v in both_turn_evals) / len(both_turn_evals), 2)
        if both_turn_evals
        else after.get("avg_pass_turns")
    )
    b_tools = (
        round(sum(before["per_eval"][v]["avg_pass_tool_calls"] for v in both_tool_evals) / len(both_tool_evals), 2)
        if both_tool_evals
        else before.get("avg_pass_tool_calls")
    )
    a_tools = (
        round(sum(after["per_eval"][v]["avg_pass_tool_calls"] for v in both_tool_evals) / len(both_tool_evals), 2)
        if both_tool_evals
        else after.get("avg_pass_tool_calls")
    )
    delta_turns = round(a_turns - b_turns, 2) if (b_turns is not None and a_turns is not None) else None
    delta_tools = round(a_tools - b_tools, 2) if (b_tools is not None and a_tools is not None) else None
    turn_bloat_evals: dict[str, str] = {}
    for v in both_turn_evals:
        bt = float(before["per_eval"][v]["avg_pass_turns"])
        at = float(after["per_eval"][v]["avg_pass_turns"])
        if at - bt >= EFFICIENCY_TURN_WARN_DELTA - 1e-9:
            turn_bloat_evals[v] = f"{bt:.2f}->{at:.2f} ({at - bt:+.2f})"
    efficiency = {
        "before_avg_pass_turns": b_turns,
        "after_avg_pass_turns": a_turns,
        "delta_turns": delta_turns,
        "before_avg_pass_tool_calls": b_tools,
        "after_avg_pass_tool_calls": a_tools,
        "delta_tool_calls": delta_tools,
        "turn_bloat_evals": turn_bloat_evals,
    }
    if delta_turns is not None or delta_tools is not None:
        t_part = (
            f"turns {b_turns:.2f} -> {a_turns:.2f} ({delta_turns:+.2f})"
            if delta_turns is not None
            else "turns n/a"
        )
        tc_part = (
            f"tool_calls {b_tools:.2f} -> {a_tools:.2f} ({delta_tools:+.2f})"
            if delta_tools is not None
            else "tool_calls n/a"
        )
        reasons.append(f"efficiency (passing runs): {t_part}, {tc_part}")
    target_turn_bloat = {k: v for k, v in turn_bloat_evals.items() if k in targets}
    if (delta_turns is not None and delta_turns >= EFFICIENCY_TURN_WARN_DELTA - 1e-9) or target_turn_bloat:
        reasons.append(
            f"EFFICIENCY WARNING: passing turns increased by >= +{EFFICIENCY_TURN_WARN_DELTA:.1f} "
            f"(overall delta={delta_turns if delta_turns is not None else 'n/a'}, "
            f"targets={target_turn_bloat or 'overall'}) — check for extra clarification or tool retry loops"
        )

    if shapes is not None:
        runs = shapes["history_runs"]
        reasons.append(
            f"shape record: {len(runs)} earlier run(s) with failing pages"
            + (f" ({', '.join(runs)})" if runs else f" under {shapes['pages_root']}")
        )
        if shapes["history_missing"]:
            reasons.append(f"--history folders not found: {shapes['history_missing']}")
    movers = {
        v: f"{before['per_eval'][v]['pass']}->{after['per_eval'][v]['pass']}"
        for v in common
        if before["per_eval"][v]["pass"] != after["per_eval"][v]["pass"]
    }
    return {
        "before": before["label"],
        "after": after["label"],
        "kind": kind,
        "targets": targets,
        "finding_gone": finding_gone,
        "gated_by": gated_by,
        "common_evals": len(common),
        "before_passes": b,
        "after_passes": a,
        "gain": gain,
        "efficiency": efficiency,
        "broke": collapsed,
        "fell_two": fell_two,
        "fell_more": fell_more,
        "noise": noise,
        "regressions": regressions,
        "unknown": unknown,
        "history_runs": shapes["history_runs"] if shapes else [],
        "shape_check": shape_check,
        "targets_detail": targets_detail,
        "movers": movers,
        "verdict": verdict,
        "reasons": reasons,
    }


def _self_test() -> int:
    before = {
        "label": "unstable-1111111",
        "per_eval": {
            "VE-01": {
                "pass": 1,
                "total": 5,
                "infra": 0,
                "verdict": "FAIL",
                "avg_pass_turns": 4.0,
                "avg_pass_tool_calls": 3.0,
            },
            "VE-02": {
                "pass": 5,
                "total": 5,
                "infra": 0,
                "verdict": "PASS",
                "avg_pass_turns": 3.0,
                "avg_pass_tool_calls": 2.0,
            },
        },
    }
    after_keep = {
        "label": "unstable-2222222",
        "per_eval": {
            "VE-01": {
                "pass": 5,
                "total": 5,
                "infra": 0,
                "verdict": "PASS",
                "avg_pass_turns": 6.0,
                "avg_pass_tool_calls": 5.0,
            },
            "VE-02": {
                "pass": 5,
                "total": 5,
                "infra": 0,
                "verdict": "PASS",
                "avg_pass_turns": 3.0,
                "avg_pass_tool_calls": 2.0,
            },
        },
    }
    res = compare(before, after_keep, kind="targeted", targets=("VE-01",))
    assert res["verdict"] == "keep", res
    assert res["efficiency"]["delta_turns"] == 1.0, res["efficiency"]
    assert "VE-01" in res["efficiency"]["turn_bloat_evals"], res["efficiency"]
    assert any("EFFICIENCY WARNING" in r for r in res["reasons"]), res["reasons"]

    after_undo = {
        "label": "unstable-3333333",
        "per_eval": {
            "VE-01": {"pass": 1, "total": 5, "infra": 0, "verdict": "FAIL"},
            "VE-02": {"pass": 2, "total": 5, "infra": 0, "verdict": "FAIL"},
        },
    }
    res2 = compare(before, after_undo, kind="targeted", targets=("VE-01",))
    assert res2["verdict"] == "undo", res2

    summary = summarize(
        {
            "label": "full-abcdef0",
            "runs_per_eval": 5,
            "is_full_run": True,
            "results": [
                {
                    "ve_id": "VE-01",
                    "pass_runs": 5,
                    "total_runs": 5,
                    "verdict": "PASS",
                    "avg_pass_turns": 4.2,
                    "avg_pass_tool_calls": 3.4,
                }
            ],
        }
    )
    assert summary["commit"] == "abcdef0" and summary["passes"] == 5, summary
    assert summary["strict_pass"] == 1 and summary["strict_pass_rate"] == 1.0, summary
    assert summary["majority_pass"] == 1 and summary["majority_pass_rate"] == 1.0, summary
    assert summary["avg_pass_turns"] == 4.2 and summary["avg_pass_tool_calls"] == 3.4, summary
    validate_full_summary(summary)
    bad_summary = summarize(
        {
            "label": "full-abcdef0",
            "runs_per_eval": 3,
            "is_full_run": True,
            "is_holdout": True,
            "results": [{"ve_id": "VE-01", "pass_runs": 3, "total_runs": 3, "verdict": "PASS"}],
        }
    )
    try:
        validate_full_summary(bad_summary)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected validate_full_summary to reject holdout run")

    # Gate 3: strict 3/3 first, then majority, complete runs only, 0 tool errors, one commit.
    def _record(cells: list[tuple[int, int]], **extra: object) -> dict:
        per_eval = {
            f"VE-{n:02d}": {"pass": p, "total": t, "verdict": "PASS" if p >= 2 else "FAIL"}
            for n, (p, t) in enumerate(cells, start=1)
        }
        rec = {"label": "full-abcdef0", "commit": "abcdef0", "is_full_run": True, "runs_per_eval": 3,
               "tool_errors": 0, "per_eval": per_eval}
        rec.update(extra)
        return rec

    th = {"strict_pass_rate": 0.9, "majority_pass_rate": 1.0}
    assert gate3_verdict(_record([(3, 3)] * 9 + [(2, 3)]), th)["pass"]  # 9/10 strict, 10/10 majority
    assert not gate3_verdict(_record([(3, 3)] * 8 + [(2, 3)] * 2), th)["pass"]  # strict 8/10
    assert not gate3_verdict(_record([(3, 3)] * 9 + [(1, 3)]), th)["pass"]  # majority 9/10
    assert not gate3_verdict(_record([(3, 3)] * 9 + [(2, 2)]), th)["pass"]  # incomplete eval
    assert not gate3_verdict(_record([(3, 3)] * 10, tool_errors=1), th)["pass"]
    assert not gate3_verdict(_record([(3, 3)] * 10, tool_errors=None), th)["pass"]
    assert not gate3_verdict(_record([(3, 3)] * 10, is_full_run=False), th)["pass"]
    assert not gate3_verdict(_record([(1, 1)] * 10, runs_per_eval=1), th)["pass"]
    assert load_gate3_thresholds(REPO_ROOT / "does-not-exist.json") == GATE3_DEFAULTS
    print("OK: 6/6 bench_summary self-test cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("report", nargs="?", help="run_bench report .json")
    p.add_argument("--commit", help="commit or version text if not in the label")
    p.add_argument(
        "--label", help="record name if the report has no label (old reports)"
    )
    p.add_argument(
        "--id-map",
        help="display-name -> VE id table (markdown) for old reports without ve_id; kept outside the repo",
    )
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    p.add_argument("--before", help="Before report JSON (alias for first --compare arg)")
    p.add_argument("--after", help="After report JSON (alias for second --compare arg)")
    p.add_argument(
        "--kind",
        choices=("targeted", "hygiene"),
        default="hygiene",
        help="rule 22 branch: targeted (named target evals) or hygiene (a judge finding)",
    )
    p.add_argument(
        "--targets",
        default="",
        help="comma-separated VE ids the change aims at (targeted)",
    )
    p.add_argument(
        "--finding-gone",
        choices=("yes", "no"),
        help="hygiene: is the judge finding gone from the new transcripts? (checked by a human/agent)",
    )
    p.add_argument(
        "--gated-by",
        help="targeted: DEF id (docs/defects.md) that still blocks a target whose expectation "
        "flipped to PASS in >= 4/5 -> verdict partial (DD-27)",
    )
    p.add_argument(
        "--bench-dir",
        default=str(DEFAULT_BENCH_ROOT),
        help="bench root; failing-conversation pages are read from "
        "<bench-dir>/runs/failing_runs_data/<label>/ (same layout as make dashboard)",
    )
    p.add_argument(
        "--history",
        help="comma-separated page folders that form the shape record "
        "(default: every folder older than AFTER; BEFORE's folder always counts)",
    )
    p.add_argument(
        "--defects",
        default=str(DEFAULT_DEFECTS),
        help="docs/defects.md: DEF ids and the VE -> DEF map",
    )
    p.add_argument("--self-test", action="store_true", help="Run built-in self-tests")
    p.add_argument(
        "--gate3",
        metavar="RECORD",
        help="Gate 3 verdict for history/bench/full-<sha7>.json (or a raw report): exit 0 PASS, 1 FAIL",
    )
    p.add_argument(
        "--thresholds",
        default=str(REPO_ROOT / "gate_thresholds.json"),
        help="gate_thresholds.json with strict_pass_rate and majority_pass_rate (for --gate3)",
    )
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.gate3:
        return run_gate3(args.gate3, args.thresholds, args.bench_dir)

    compare_pair = args.compare or (
        [args.before, args.after] if (args.before and args.after) else None
    )
    if compare_pair:
        before = json.loads(Path(compare_pair[0]).read_text(encoding="utf-8"))
        after = json.loads(Path(compare_pair[1]).read_text(encoding="utf-8"))
        targets = tuple(t.strip() for t in args.targets.split(",") if t.strip())
        finding_gone = None if args.finding_gone is None else args.finding_gone == "yes"
        history = None
        if args.history is not None:
            history = [h.strip() for h in args.history.split(",") if h.strip()]
        shapes = load_shapes(args.bench_dir, before, after, history, args.defects)
        print(
            json.dumps(
                compare(
                    before,
                    after,
                    args.kind,
                    targets,
                    finding_gone,
                    shapes,
                    args.gated_by,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if not args.report:
        p.error("report path required (or --compare BEFORE AFTER)")
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    id_map = load_id_map(Path(args.id_map)) if args.id_map else None
    summary = summarize(report, args.commit, args.label, id_map)
    summary.update(tool_error_count(args.bench_dir, summary["label"], report))
    if str(summary.get("label") or "").startswith("full-"):
        try:
            validate_full_summary(summary)
        except ValueError as exc:
            print(f"ERROR: refusing to write {summary['label']}.json: {exc}", file=sys.stderr)
            return 1
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{summary['label']}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"{out}: strict 3/3: {summary['strict_pass']}/{summary['evals']} "
        f"({summary['strict_pass_rate'] * 100:.1f}%) | "
        f"majority >=2/3: {summary['majority_pass']}/{summary['evals']} "
        f"({summary['majority_pass_rate'] * 100:.1f}%) | "
        f"individual: {summary['passes']}/{summary['total']} "
        f"(p={summary['p']:.3f}, N*p^3={summary['predicted_strict_3_of_3']:.1f}) | "
        f"tool errors: {'not recorded' if summary.get('tool_errors') is None else summary['tool_errors']} | "
        f"commit={summary['commit'] or '?'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

