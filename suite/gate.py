#!/usr/bin/env python3
"""Eval gate: turns run records into PASS / FAIL / INCONCLUSIVE.

Reads `history/runs.jsonl` (one JSON object per test x repeat, see
run_record.schema.json) and `gate_thresholds.json`, looks only at records with
the given run_id, and applies these rules:

  1. Per test: strict majority of decided repeats (pass/fail; infra_error is
     not decided). Ties fail. A test whose verdict could flip if its infra
     repeats had gone the other way is UNCERTAIN.
  2. Too few repeats for a test's layer -> INCONCLUSIVE.
  3. Model check: agent_model (and judge_model, when set) must match the
     thresholds file, else FAIL (floors measured on another model mean nothing).
     A model field that is still the "<...>" placeholder is skipped with a note
     telling you to fill it in; it never fails the gate on its own.
  4. Must-pass: a failing test with a must-pass priority (P0) or listed in
     must_pass_tests -> FAIL. UNCERTAIN must-pass -> INCONCLUSIVE.
  5. Floors per layer: pass ratio of tests. Below the floor even if every
     uncertain test passed -> FAIL; below only if they fail -> INCONCLUSIVE.
  6. Infra repeats above max_infra_ratio -> INCONCLUSIVE.
  7. Strict 3/3: the share of tests that passed EVERY repeat must reach
     strict_pass_rate (legacy key: min_strict_pass_rate). Below it even if every
     infra repeat had passed -> FAIL; below only because of infra -> INCONCLUSIVE.

FAIL beats INCONCLUSIVE beats PASS. Exit codes: 0 PASS, 1 FAIL, 3 INCONCLUSIVE.

Usage:
  python suite/gate.py --records history/runs.jsonl --thresholds gate_thresholds.json \
      --run-id <id> [--summary-md $GITHUB_STEP_SUMMARY] [--json out.json]
  python suite/gate.py --self-test
"""

import argparse
import json
import sys
from collections import defaultdict

EXIT = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 3}
MARK = {"pass": "✓", "fail": "✗", "infra_error": "·"}


def is_placeholder(value):
    """True for an empty model field or the template's "<...>" placeholder."""
    text = str(value or "").strip()
    return not text or (text.startswith("<") and text.endswith(">"))


def strict_floor(thresholds):
    """The strict 3/3 bar: strict_pass_rate, or the legacy min_strict_pass_rate (None = off)."""
    value = thresholds.get("strict_pass_rate", thresholds.get("min_strict_pass_rate"))
    return None if value is None else float(value)


def test_verdict(statuses):
    p = statuses.count("pass")
    f = statuses.count("fail")
    i = statuses.count("infra_error")
    verdict = "pass" if p > f else "fail"
    best = "pass" if p + i > f else "fail"
    worst = "pass" if p > f + i else "fail"
    if p + f == 0:
        return "uncertain"
    return verdict if best == worst else "uncertain"


def evaluate(records, thresholds, run_id):
    rows = [r for r in records if r.get("run_id") == run_id]
    fails, inconclusive, notes = [], [], []
    if not rows:
        return {
            "verdict": "INCONCLUSIVE",
            "reasons": [f"no records for run_id {run_id}"],
            "notes": [],
            "tests": [],
        }

    # 3. model check (a "<...>" placeholder is skipped with a note, never a FAIL)
    want_model = thresholds.get("measured_on_model")
    want_judge = thresholds.get("judge_model")
    models = {r.get("agent_model") for r in rows}
    if is_placeholder(want_model):
        if want_model is not None:
            notes.append(
                "gate_thresholds.json: measured_on_model is still a placeholder; set it to the agent model "
                "these floors were measured on (modelSettings.model in cxas_app/app.json, for example "
                f"{sorted(m or '?' for m in models)[0]}). The model check is skipped until then."
            )
    elif models != {want_model}:
        fails.append(
            f"agent model {sorted(m or '?' for m in models)} != measured_on_model {want_model}; re-measure floors"
        )
    judges = {r.get("judge_model") for r in rows if r.get("judge_model")}
    if is_placeholder(want_judge):
        if thresholds.get("judge_model") is not None:
            notes.append(
                "gate_thresholds.json: judge_model is still a placeholder; set it to the judge model "
                "the floors were measured with. The judge check is skipped until then."
            )
    elif judges and judges != {want_judge}:
        fails.append(
            f"judge model {sorted(judges)} != {want_judge}; re-run judge calibration"
        )

    by_test = defaultdict(list)
    meta = {}
    for r in sorted(rows, key=lambda r: r.get("repeat", 0)):
        by_test[r["test_id"]].append(r.get("status"))
        meta[r["test_id"]] = r

    repeats = thresholds.get("repeats", {})
    must_pri = set(thresholds.get("must_pass_priorities", ["P0"]))
    must_ids = set(thresholds.get("must_pass_tests", []))
    floors = thresholds.get("floors", {})

    tests = []
    layer_counts = defaultdict(lambda: {"pass": 0, "fail": 0, "uncertain": 0})
    for test_id, statuses in sorted(by_test.items()):
        m = meta[test_id]
        layer = m.get("layer", "unknown")
        v = test_verdict(statuses)
        need = repeats.get(layer, repeats.get("default", 1))
        must = m.get("priority") in must_pri or test_id in must_ids
        tests.append(
            {
                "test_id": test_id,
                "layer": layer,
                "priority": m.get("priority"),
                "requirement_ids": m.get("requirement_ids", []),
                "repeats": "".join(MARK.get(s, "?") for s in statuses),
                "verdict": v,
                "must_pass": must,
            }
        )
        layer_counts[layer][v] += 1
        if len(statuses) < need:  # 2.
            inconclusive.append(
                f"{test_id}: ran {len(statuses)} repeats, {layer} needs {need}"
            )
        if must and v == "fail":  # 4.
            fails.append(
                f"must-pass {test_id} ({m.get('priority')}) failed {tests[-1]['repeats']}"
            )
        elif must and v == "uncertain":
            inconclusive.append(
                f"must-pass {test_id} undecided because of infra errors {tests[-1]['repeats']}"
            )

    for layer, c in sorted(layer_counts.items()):  # 5.
        floor = floors.get(layer)
        total = c["pass"] + c["fail"] + c["uncertain"]
        if floor is None or total == 0:
            continue
        best = (c["pass"] + c["uncertain"]) / total
        worst = c["pass"] / total
        if best < floor:
            fails.append(
                f"{layer}: {c['pass']}/{total} passed, below floor {floor:.0%}"
            )
        elif worst < floor:
            inconclusive.append(
                f"{layer}: {c['pass']}/{total} passed; {c['uncertain']} undecided could drop it below {floor:.0%}"
            )

    infra = sum(r.get("status") == "infra_error" for r in rows) / len(rows)  # 6.
    if infra > thresholds.get("max_infra_ratio", 0.2):
        inconclusive.append(
            f"{infra:.0%} of repeats were infra errors (max {thresholds.get('max_infra_ratio', 0.2):.0%}); re-run"
        )

    strict = None  # 7. strict 3/3: every repeat of a test passed
    bar = strict_floor(thresholds)
    if bar is not None and by_test:
        n = len(by_test)
        worst = sum(1 for s in by_test.values() if s and all(x == "pass" for x in s))
        best = sum(1 for s in by_test.values() if s and all(x in ("pass", "infra_error") for x in s))
        strict = {"passed": worst, "total": n, "rate": round(worst / n, 4), "bar": bar}
        if best / n + 1e-9 < bar:
            fails.append(
                f"strict 3/3: {worst}/{n} tests passed every repeat ({worst / n:.0%}), below {bar:.0%}"
            )
        elif worst / n + 1e-9 < bar:
            inconclusive.append(
                f"strict 3/3: {worst}/{n} tests passed every repeat; {best - worst} undecided because of "
                f"infra errors could keep it below {bar:.0%}"
            )

    verdict = "FAIL" if fails else "INCONCLUSIVE" if inconclusive else "PASS"
    return {
        "verdict": verdict,
        "reasons": fails + inconclusive,
        "notes": notes,
        "strict": strict,
        "layers": {k: dict(v) for k, v in layer_counts.items()},
        "tests": tests,
    }


def to_markdown(result, run_id):
    lines = [f"## Eval gate: **{result['verdict']}** (run `{run_id}`)", ""]
    for r in result["reasons"]:
        lines.append(f"- {r}")
    for note in result.get("notes") or []:
        lines.append(f"- note: {note}")
    strict = result.get("strict")
    if strict:
        lines += [
            "",
            f"Strict 3/3: {strict['passed']}/{strict['total']} tests passed every repeat "
            f"({strict['rate']:.0%}; bar {strict['bar']:.0%})",
        ]
    lines += [
        "",
        "| Test | Layer | Priority | REQ | Repeats | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for t in result["tests"]:
        lines.append(
            f"| {t['test_id']} | {t['layer']} | {t['priority'] or ''}{' (must)' if t['must_pass'] else ''} "
            f"| {', '.join(t['requirement_ids'])} | {t['repeats']} | {t['verdict']} |"
        )
    lines += ["", "✓ pass · ✗ fail · `·` infra error"]
    return "\n".join(lines) + "\n"


def _rec(test, layer, pri, statuses, model="m1", run="r1"):
    return [
        {
            "run_id": run,
            "test_id": test,
            "layer": layer,
            "priority": pri,
            "repeat": n + 1,
            "status": s,
            "agent_model": model,
            "judge_model": "j1",
            "requirement_ids": ["REQ-1"],
        }
        for n, s in enumerate(statuses)
    ]


def self_test():
    th = {
        "measured_on_model": "m1",
        "judge_model": "j1",
        "repeats": {"default": 3, "tool": 1},
        "must_pass_priorities": ["P0"],
        "floors": {"sim": 0.8, "tool": 1.0},
        "max_infra_ratio": 0.2,
    }
    ok = _rec("t1", "tool", "P1", ["pass"])
    cases = [
        ("all pass", ok + _rec("s1", "sim", "P0", ["pass", "pass", "fail"]), "PASS"),
        (
            "P0 fails despite high overall",
            ok
            + _rec("s1", "sim", "P0", ["fail", "fail", "pass"])
            + sum((_rec(f"s{n}", "sim", "P1", ["pass"] * 3) for n in range(2, 12)), []),
            "FAIL",
        ),
        (
            "tie fails",
            ok + _rec("s1", "sim", "P1", ["pass", "fail", "pass", "fail"]),
            "FAIL",
        ),
        (
            "infra could flip P0",
            ok + _rec("s1", "sim", "P0", ["pass", "infra_error", "fail"]),
            "INCONCLUSIVE",
        ),
        ("too few repeats", ok + _rec("s1", "sim", "P1", ["pass"]), "INCONCLUSIVE"),
        ("model mismatch", _rec("t1", "tool", "P1", ["pass"], model="m2"), "FAIL"),
        (
            "floor",
            ok
            + _rec("s1", "sim", "P1", ["pass"] * 3)
            + _rec("s2", "sim", "P1", ["fail"] * 3),
            "FAIL",
        ),
        ("no records", [], "INCONCLUSIVE"),
    ]
    bad = []
    for name, recs, want in cases:
        got = evaluate(recs, th, "r1")
        if got["verdict"] != want:
            bad.append(f"{name}: want {want}, got {got['verdict']} {got['reasons']}")
    to_markdown(evaluate(cases[1][1], th, "r1"), "r1")  # smoke-test rendering

    # Strict 3/3 (rule 7): majority passes on every test, but strict is the bar.
    th_strict = dict(th, strict_pass_rate=0.9, floors={"sim": 0.8})
    two_of_three = sum((_rec(f"s{n}", "sim", "P1", ["pass", "pass", "fail"]) for n in range(10)), [])
    nine_strict = sum((_rec(f"s{n}", "sim", "P1", ["pass"] * 3) for n in range(9)), []) + _rec(
        "s9", "sim", "P1", ["pass", "pass", "fail"]
    )
    infra_open = sum((_rec(f"s{n}", "sim", "P1", ["pass"] * 3) for n in range(8)), []) + sum(
        (_rec(f"s{n}", "sim", "P1", ["pass", "pass", "infra_error"]) for n in (8, 9)), []
    )
    legacy = {k: v for k, v in th_strict.items() if k != "strict_pass_rate"}
    legacy["min_strict_pass_rate"] = 0.9
    placeholder = dict(th_strict, measured_on_model="<exact agent model, e.g. from app.json>")
    strict_cases = [
        ("strict below the bar while majority passes", two_of_three, th_strict, "FAIL"),
        ("strict exactly at the bar", nine_strict, th_strict, "PASS"),
        ("strict undecided because of infra", infra_open, th_strict, "INCONCLUSIVE"),
        ("legacy min_strict_pass_rate key", two_of_three, legacy, "FAIL"),
        ("placeholder model is a note, not a FAIL", nine_strict, placeholder, "PASS"),
    ]
    for name, recs, thresholds, want in strict_cases:
        got = evaluate(recs, thresholds, "r1")
        if got["verdict"] != want:
            bad.append(f"{name}: want {want}, got {got['verdict']} {got['reasons']}")
    if not evaluate(nine_strict, placeholder, "r1")["notes"]:
        bad.append("placeholder model: expected a note telling you to fill in measured_on_model")
    if "Strict 3/3: 9/10" not in to_markdown(evaluate(nine_strict, th_strict, "r1"), "r1"):
        bad.append("markdown: expected the strict 3/3 line")
    if bad:
        print("FAIL\n" + "\n".join(bad))
        return 1
    print(f"OK ({len(cases) + len(strict_cases)} cases)")
    return 0


def main():
    p = argparse.ArgumentParser(description="Eval gate: PASS / FAIL / INCONCLUSIVE")
    p.add_argument("--records", default="history/runs.jsonl")
    p.add_argument("--thresholds", default="gate_thresholds.json")
    p.add_argument("--run-id")
    p.add_argument(
        "--summary-md",
        help="append a markdown summary here (e.g. $GITHUB_STEP_SUMMARY)",
    )
    p.add_argument("--json", help="write the full result as JSON here")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not a.run_id:
        p.error("--run-id or --self-test is required")
    records = []
    try:
        with open(a.records, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        print(f"note: {a.records} does not exist yet (run `make eval` first)", file=sys.stderr)
    try:
        with open(a.thresholds, encoding="utf-8") as f:
            thresholds = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {a.thresholds} not found (copy assets/gate_thresholds.json and fill in the models)", file=sys.stderr)
        return 1
    result = evaluate(records, thresholds, a.run_id)
    md = to_markdown(result, a.run_id)
    print(md)
    if a.summary_md:
        with open(a.summary_md, "a", encoding="utf-8") as f:
            f.write(md)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
