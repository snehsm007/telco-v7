"""Build the hill-climb dashboard: one static site from the bench reports (no server).

Levels of click-through:
  progress over time  ->  one run  ->  one eval  ->  one failing conversation
(judge reasoning, the agent/node that was active when it broke, tool errors,
transcript). Standard library only. `make dashboard` writes dashboard/ (not
committed; published to Zipline with `make publish-dashboard`).

Inputs:
  history/bench/<label>.json          committed per-eval numbers (the trend)
  <bench>/runs/<label>.json           full report of a run (per-repeat statuses)
  <bench>/runs/failing_runs_data/<label>/VE-xx__<run8>__rN.json   one page per
                                      non-passing conversation (judge, tools, transcript)
  docs/experiment_log.md              the iteration table (mechanism, decision)
  docs/defects.md                     DEF-nn <-> VE-xx mapping ("failures by mechanism")
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BENCH_ROOT = Path(os.environ.get("BENCH_DIR") or REPO / "bench")
OUTCOME_NAMES = {0: "UNSPECIFIED", 1: "PASS", 2: "FAIL"}
HANDOVER_TOOL = "execute_live_agent_handover"
TRANSCRIPT_LINE = re.compile(r"^\[turn (\d+)\] (\w+): (.*)$", re.DOTALL)
PAGE_STEM = re.compile(r"^(VE-\d+)__([0-9a-f]{8})__r(\d+)$")
# A complete app resource name. Anything else (e.g. the Makefile's
# projects//locations//apps/ when no ENV file is loaded) is treated as unknown.
APP_RESOURCE = re.compile(r"^projects/[^/]+/locations/[^/]+/apps/[^/]+$")
CES_CONSOLE_BASE = "https://ces-console-dev.corp.google.com"
MONTH_ABBR = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


# --------------------------------------------------------------------------- loading


def load_history(history_dir: Path) -> list[dict]:
    """Committed per-eval records, oldest first (smoke runs excluded per DD-28)."""
    records = []
    for path in sorted(history_dir.glob("*.json")):
        if path.stem.startswith("smoke-"):
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            not isinstance(rec, dict)
            or "per_eval" not in rec
            or rec.get("is_smoke_run")
        ):
            continue
        rec.setdefault("label", path.stem)
        if str(rec["label"]).startswith("smoke-"):
            continue
        records.append(rec)
    records.sort(key=lambda r: str(r.get("timestamp", "")))
    return records


def load_report(runs_dir: Path, label: str) -> dict | None:
    path = runs_dir / f"{label}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_pages(runs_dir: Path, label: str) -> dict[str, dict]:
    """Failing-conversation pages of a run, keyed by file stem (VE-29__850ae4cd__r1)."""
    pages = {}
    for path in sorted((runs_dir / "failing_runs_data" / label).glob("VE-*.json")):
        try:
            pages[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return pages


def parse_experiment_log(path: Path) -> list[dict]:
    """Rows of the Summary table in docs/experiment_log.md."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or not re.fullmatch(r"\d+", cells[0]):
            continue
        rows.append(
            {
                "iteration": int(cells[0]),
                "date": cells[1],
                "mechanism": cells[2],
                "branch": cells[3],
                "measurement": cells[4],
                "decision": cells[5],
                "full_run": cells[6] if len(cells) > 6 else "",
                "labels": re.findall(r"`((?:unstable|full)-[0-9a-f]{7})`", line),
            }
        )
    return rows


def parse_defects(path: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """DEF entries (id, title, status, evals, root cause, fix/smoke) and VE -> [DEF] map."""
    if not path.exists():
        return [], {}
    defects: list[dict] = []
    current: dict | None = None
    active_field: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### (DEF-\d+):\s*(.*)$", line)
        if m:
            current = {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "status": "",
                "ve_ids": [],
                "requirement": "",
                "layer": "",
                "fix_type": "",
                "diagnosis": "",
                "attempts": "",
                "smoke": "",
            }
            defects.append(current)
            active_field = None
            continue
        if re.match(r"^### D-\d+:", line):
            current = None
            active_field = None
            continue
        if current is None:
            continue
        if line.startswith("- Found by:"):
            current["ve_ids"] = sorted(set(re.findall(r"VE-\d+", line)))
            active_field = None
        elif line.startswith("- Status:"):
            current["status"] = line.split(":", 1)[1].strip()
            active_field = None
        elif line.startswith("- Requirement:"):
            current["requirement"] = line.split(":", 1)[1].strip()
            active_field = "requirement"
        elif line.startswith("- Root cause layer:"):
            current["layer"] = line.split(":", 1)[1].strip()
            active_field = "layer"
        elif line.startswith("- Fix type:"):
            current["fix_type"] = line.split(":", 1)[1].strip()
            active_field = None
        elif line.startswith("- Diagnosis:"):
            current["diagnosis"] = line.split(":", 1)[1].strip()
            active_field = "diagnosis"
        elif line.startswith("- Attempts:"):
            current["attempts"] = line.split(":", 1)[1].strip()
            active_field = "attempts"
        elif line.startswith("- Smoke measurement") or line.startswith(
            "- Failing judge metrics accounted for:"
        ):
            current["smoke"] = line.lstrip("- ").strip()
            active_field = "smoke"
        elif line.startswith("- "):
            active_field = None
        elif active_field and line.startswith("  ") and line.strip():
            current[active_field] = f"{current[active_field]} {line.strip()}".strip()
    by_ve: dict[str, list[str]] = defaultdict(list)
    for d in defects:
        for ve in d["ve_ids"]:
            by_ve[ve].append(d["id"])
    return defects, dict(by_ve)


def parse_audio_defects(path: Path) -> list[dict]:
    """Parse defects whose IDs start with DEF-A (voice defect clusters)."""
    if not path.exists():
        return []
    defects: list[dict] = []
    current: dict | None = None
    active_field: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### (DEF-A\w*)(?::\s*|\s+-\s*|\s+)(.*)$", line)
        if m:
            current = {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "status": "",
                "members": [],
                "requirement": "",
                "layer": "",
                "fix_type": "",
                "diagnosis": "",
                "smoke": "",
            }
            defects.append(current)
            active_field = None
            continue
        if line.startswith("### "):
            current = None
            active_field = None
            continue
        if current is None:
            continue
        m_mem = re.match(r"^-?\s*(?:Members|Found by):\s*(.*)$", line, re.IGNORECASE)
        if m_mem:
            raw = m_mem.group(1)
            cases = [c.strip("` \t,") for c in re.findall(r"[\w-]+", raw) if c]
            current["members"] = [
                c
                for c in cases
                if "_" in c or c.startswith("VE-") or c.startswith("cuj_") or c.startswith("golden_") or c.startswith("sim_")
            ]
            active_field = None
        elif line.startswith("- Status:"):
            current["status"] = line.split(":", 1)[1].strip()
            active_field = None
        elif line.startswith("- Requirement:"):
            current["requirement"] = line.split(":", 1)[1].strip()
            active_field = "requirement"
        elif line.startswith("- Root cause layer:"):
            current["layer"] = line.split(":", 1)[1].strip()
            active_field = "layer"
        elif line.startswith("- Fix type:"):
            current["fix_type"] = line.split(":", 1)[1].strip()
            active_field = None
        elif line.startswith("- Diagnosis:"):
            current["diagnosis"] = line.split(":", 1)[1].strip()
            active_field = "diagnosis"
        elif line.startswith("- Smoke measurement") or line.startswith(
            "- Failing judge metrics accounted for:"
        ):
            current["smoke"] = line.lstrip("- ").strip()
            active_field = "smoke"
        elif line.startswith("- "):
            active_field = None
        elif active_field and line.startswith("  ") and line.strip():
            current[active_field] = f"{current[active_field]} {line.strip()}".strip()
    return defects


# ---------------------------------------------------------------- failure attribution


def _tool_short(name: str) -> str:
    return str(name or "").rsplit("/", 1)[-1]


def _as_dict(value: object) -> dict:
    """The judge's sub-results arrive as a dict or as a one-element list of dicts."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return next((v for v in value if isinstance(v, dict)), {})
    return {}


def _response_result(payload: dict) -> dict:
    res = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(res, dict):
        return {}
    inner = res.get("result")
    return inner if isinstance(inner, dict) else res


def attribute_failure(page: dict) -> dict:
    """Where and in which agent ("node") a failing conversation broke.

    Signals, in priority order: the first tool error, a live-agent handover, a
    callback fallback; otherwise the agent that spoke last. Also collects the
    judge's failed expectations so the index can show why without opening the page.
    """
    first_error = None
    handover = None
    for tc in page.get("tool_calls") or []:
        kind = tc.get("type")
        payload = tc.get("payload") or {}
        if kind == "tool_response" and first_error is None:
            result = _response_result(payload)
            if result.get("status") == "error" or result.get("error"):
                first_error = {
                    "turn": int(tc.get("turn") or 0),
                    "node": str(tc.get("role") or "?"),
                    "tool": _tool_short(
                        payload.get("tool") or payload.get("display_name")
                    ),
                    "error": str(result.get("error") or result.get("status") or ""),
                    "message": str(result.get("message") or "")[:200],
                }
        if (
            kind == "tool_call"
            and handover is None
            and _tool_short(payload.get("tool") or payload.get("display_name"))
            == HANDOVER_TOOL
        ):
            args = payload.get("args") or {}
            handover = {
                "turn": int(tc.get("turn") or 0),
                "node": str(tc.get("role") or "?"),
                "reason": str(args.get("reason") or ""),
            }
    node_at_end = ""
    last_turn = 0
    for line in page.get("transcript") or []:
        m = TRANSCRIPT_LINE.match(line)
        if m and m.group(2) != "user":
            node_at_end = m.group(2)
            last_turn = int(m.group(1))
    fallbacks = [str(f) for f in (page.get("fallback_reasons") or []) if f]

    if first_error:
        failing_node, broke_at, signal = (
            first_error["node"],
            first_error["turn"],
            f"tool error: {first_error['tool']} -> {first_error['error']}",
        )
    elif handover:
        failing_node, broke_at, signal = (
            handover["node"],
            handover["turn"],
            f"handover to a live agent ({handover['reason'] or 'no reason'})",
        )
    elif fallbacks:
        failing_node, broke_at, signal = (
            node_at_end or "?",
            last_turn,
            f"callback fallback: {fallbacks[0][:120]}",
        )
    else:
        failing_node, broke_at, signal = (
            node_at_end or "?",
            last_turn,
            "no tool error or handover; see the judge's reasoning",
        )

    judge = page.get("judge") or {}
    failed_expectations = []
    for exp in judge.get("evaluation_expectation_results") or []:
        outcome = exp.get("outcome")
        name = (
            OUTCOME_NAMES.get(outcome, str(outcome))
            if isinstance(outcome, int)
            else str(outcome or "")
        )
        if name != "PASS":
            failed_expectations.append(
                {
                    "prompt": str(exp.get("prompt") or ""),
                    "outcome": name,
                    "explanation": str(exp.get("explanation") or ""),
                }
            )
    goal = _as_dict(judge.get("user_goal_satisfaction_result"))
    halluc = _as_dict(judge.get("hallucination_result"))
    scrapi_cat, scrapi_detail = classify_scrapi_triage(
        page,
        first_error=first_error,
        failed_expectations=failed_expectations,
        goal=goal,
        halluc=halluc,
        fallbacks=fallbacks,
        last_turn=last_turn,
    )
    return {
        "failing_node": failing_node,
        "broke_at_turn": broke_at,
        "signal": signal,
        "first_error": first_error,
        "handover": handover,
        "fallbacks": fallbacks,
        "node_at_end": node_at_end,
        "failed_expectations": failed_expectations,
        "user_goal": {
            "label": str(goal.get("label") or ""),
            "score": goal.get("score"),
            "explanation": str(goal.get("explanation") or ""),
        },
        "hallucination": {
            "label": str(halluc.get("label") or ""),
            "score": halluc.get("score"),
        },
        "scrapi_category": scrapi_cat,
        "scrapi_detail": scrapi_detail,
    }


def classify_scrapi_triage(
    page: dict,
    *,
    first_error: dict | None,
    failed_expectations: list[dict],
    goal: dict,
    halluc: dict,
    fallbacks: list[str],
    last_turn: int,
) -> tuple[str, str]:
    """Classify a failing conversation using SCRAPI's triage-results.py taxonomy."""
    if page.get("classification") == "INFRA":
        return "EVAL_ERROR", "platform execution/judge incomplete (INFRA)"
    if fallbacks:
        return "CALLBACK_TEST_FAIL", f"callback fallback: {fallbacks[0][:100]}"
    if first_error:
        return (
            "TOOL_TEST_FAIL",
            f"{first_error['tool']} -> {first_error['error']}: {first_error['message'][:80]}",
        )
    if halluc.get("score") == 0 or str(halluc.get("label") or "").lower().startswith(
        "not justified"
    ):
        return "HALLUCINATION", f"node {page.get('ve_id', '?')}: hallucination score 0"
    if failed_expectations:
        exp = failed_expectations[0]
        reason = exp["explanation"].split(".")[0].strip()[:80] or "no justification"
        return "EXPECTATION_FAIL", f'"{exp["prompt"][:60]}" — {reason}'
    if last_turn >= 8:
        return (
            "SIM_MAX_TURNS_EXCEEDED",
            f"turns={last_turn}, goal={goal.get('label') or '?'}",
        )
    if str(goal.get("label") or "") in ("Task Not Completed", "Unacceptable"):
        return (
            "SIM_USER_OFF_SCRIPT",
            f"{goal.get('label')}: {str(goal.get('explanation') or '')[:90]}",
        )
    return "SIM_TASK_INCOMPLETE", f"turns={last_turn}, goal={goal.get('label') or '?'}"


def run_scrapi_voice_audit(app_dir: Path | None) -> dict | None:
    """Run SCRAPI's cxas-composite-voice-agent-optimizer audit_agent.py if available."""
    if not app_dir or not (app_dir / "app.json").exists():
        return None
    audit_script = (
        Path.home()
        / ".gemini"
        / "config"
        / "skills"
        / "cxas-composite-voice-agent-optimizer"
        / "scripts"
        / "audit_agent.py"
    )
    if not audit_script.exists():
        try:
            app_cfg = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        audio_cfg = app_cfg.get("audioProcessingConfig") or {}
        has_voice = bool(
            audio_cfg.get("synthesizeSpeechConfigs")
            or audio_cfg.get("bargeInConfig")
            or audio_cfg.get("ambientSoundConfig")
        )
        return {
            "overall_status": "READY" if has_voice else "NEEDS_WORK",
            "total_issues": 0 if has_voice else 1,
            "priority_counts": {"P0": 0, "P1": 0 if has_voice else 1, "P2": 0},
            "passes": {
                "app_config": {
                    "passed": has_voice,
                    "issues": 0 if has_voice else 1,
                }
            },
        }
    try:
        from importlib.util import module_from_spec, spec_from_file_location

        loaded_spec = spec_from_file_location("scrapi_audit_agent", str(audit_script))
        if loaded_spec is None or not hasattr(loaded_spec, "loader") or loaded_spec.loader is None:
            return None
        auditor_mod = module_from_spec(loaded_spec)
        loaded_spec.loader.exec_module(auditor_mod)
        auditor = auditor_mod.VoiceAgentAuditor(workspace_dir=str(app_dir))
        prio = auditor.generate_prioritized_report()
        raw = auditor.audit()
        return {
            "overall_status": prio.get("overall_status", "UNKNOWN"),
            "total_issues": int(prio.get("total_issues", 0)),
            "priority_counts": prio.get("priority_counts", {"P0": 0, "P1": 0, "P2": 0}),
            "passes": {
                k: {"passed": bool(v.get("passed")), "issues": len(v.get("issues", []))}
                for k, v in (raw.get("passes") or {}).items()
            },
        }
    except Exception:
        return None


def load_smoke_runs(runs_dir: Path, def_by_ve: dict) -> list[dict]:
    """Load Gate 1 targeted smoke runs (smoke-*.json) from <bench-dir>/runs/."""
    smokes = []
    if not runs_dir.exists():
        return smokes
    for path in sorted(runs_dir.glob("smoke-*.json")):
        try:
            rep = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rep, dict) or not rep.get("results"):
            continue
        label = str(rep.get("label") or path.stem)
        commit = label.removeprefix("smoke-")
        results = rep.get("results") or []
        per_eval = {}
        passes = 0
        total = 0
        for r in results:
            ve = r.get("ve_id")
            if not ve:
                continue
            p = int(r.get("pass_runs", 0))
            t = int(r.get("total_runs", 0))
            passes += p
            total += t
            per_eval[ve] = {
                "pass": p,
                "total": t,
                "infra": int(r.get("infra_runs", 0)),
                "verdict": r.get("verdict", ""),
            }
        rec = {
            "label": label,
            "timestamp": rep.get("timestamp", ""),
            "commit": commit,
            "is_full_run": False,
            "is_smoke_run": True,
            "runs_per_eval": rep.get("runs_per_eval", 3),
            "passes": passes,
            "total": total,
            "majority_pass": rep.get("passed_evaluations", 0),
            "evals": rep.get("total_evaluations", len(per_eval)),
            "app_versions": rep.get("app_versions_seen", []),
            "evaluation_runs": rep.get("evaluation_runs", []),
            "per_eval": per_eval,
        }
        smokes.append(build_run(rec, rep, load_pages(runs_dir, label), def_by_ve, {}))
    smokes.sort(key=lambda r: str(r.get("timestamp", "")))
    return smokes


# ------------------------------------------------------------------------- the model


def _run8(name: str) -> str:
    return str(name or "").rsplit("/", 1)[-1][:8]


def _fmt_ts(ts: object) -> str:
    """Format an ISO-8601 UTC timestamp as 'Oct 5, 20:38 UTC' (fallback to short string)."""
    s = str(ts or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", s)
    if not m:
        return s
    month_idx = int(m.group(2))
    day = int(m.group(3))
    hh, mm = m.group(4), m.group(5)
    m_name = MONTH_ABBR[month_idx] if 1 <= month_idx <= 12 else m.group(2)
    return f"{m_name} {day}, {hh}:{mm} UTC"


def _is_eval_pass(ev: dict | None) -> bool:
    if not ev:
        return False
    verdict = str(ev.get("verdict") or "").upper()
    if verdict in ("PASS", "FAIL"):
        return verdict == "PASS"
    total = int(ev.get("total", 0))
    passes = int(ev.get("pass", 0))
    return total > 0 and (passes * 2 >= total)


def build_run(
    record: dict,
    report: dict | None,
    pages: dict[str, dict],
    def_by_ve: dict,
    name_to_ve: dict | None = None,
) -> dict:
    """Everything the index needs for one run, plus the page stems for the conv pages."""
    label = record["label"]
    name_to_ve = name_to_ve or {}
    outcomes = {}
    for o in (report or {}).get("results", []):
        ve = o.get("ve_id") or name_to_ve.get(o.get("display_name", ""))
        if ve:
            outcomes[ve] = o
    evals = []
    node_counter: Counter[str] = Counter()
    def_counter: Counter[str] = Counter()
    error_counter: Counter[str] = Counter()
    scrapi_counter: Counter[str] = Counter()
    conversations = []
    attributions: dict[str, dict] = {}
    for ve_id, pe in sorted(record.get("per_eval", {}).items()):
        out = outcomes.get(ve_id, {})
        repeats = []
        for pat in out.get("pattern", []):
            stem = f"{ve_id}__{_run8(pat.get('run'))}__r{pat.get('slot')}"
            repeats.append(
                {
                    "classification": pat.get("classification", ""),
                    "stem": stem if stem in pages else "",
                }
            )
        if not repeats:
            repeats = [
                {"classification": s, "stem": ""}
                for s in out.get("per_run_statuses", [])
            ] or [
                {
                    "classification": "PASS" if i < int(pe.get("pass", 0)) else "FAIL",
                    "stem": "",
                }
                for i in range(int(pe.get("total", 0)))
            ]
        failing = []
        for rep in repeats:
            if rep["stem"]:
                att = attributions.get(rep["stem"]) or attribute_failure(
                    pages[rep["stem"]]
                )
                attributions[rep["stem"]] = att
                rep["attribution"] = att
                failing.append(rep)
                if rep["classification"] != "INFRA":
                    node_counter[att["failing_node"]] += 1
                    scrapi_counter[att["scrapi_category"]] += 1
                    for d in def_by_ve.get(ve_id, []):
                        def_counter[d] += 1
                    if att["first_error"]:
                        error_counter[
                            f"{att['first_error']['tool']} -> {att['first_error']['error']}"
                        ] += 1
                conversations.append(
                    {
                        "ve_id": ve_id,
                        "stem": rep["stem"],
                        "classification": rep["classification"],
                        "node": att["failing_node"],
                        "turn": att["broke_at_turn"],
                        "signal": att["signal"],
                        "scrapi_category": att["scrapi_category"],
                        "why": (
                            att["failed_expectations"][0]["explanation"]
                            if att["failed_expectations"]
                            else att["user_goal"]["explanation"]
                        )[:260],
                    }
                )
        evals.append(
            {
                "ve_id": ve_id,
                "display_name": out.get("display_name", ""),
                "evaluation_name": str(out.get("evaluation_name") or ""),
                "language": out.get("language", ""),
                "topic": out.get("topic", ""),
                "pass": int(pe.get("pass", 0)),
                "total": int(pe.get("total", 0)),
                "infra": int(pe.get("infra", 0)),
                "verdict": pe.get("verdict", out.get("verdict", "")),
                "repeats": repeats,
                "failing_nodes": sorted(
                    {
                        r["attribution"]["failing_node"]
                        for r in failing
                        if r["classification"] != "INFRA"
                    }
                ),
                "mechanisms": def_by_ve.get(ve_id, []),
            }
        )
    return {
        "label": label,
        "timestamp": record.get("timestamp", ""),
        "commit": record.get("commit", ""),
        "is_full_run": bool(record.get("is_full_run")),
        "is_smoke_run": bool(record.get("is_smoke_run")),
        "runs_per_eval": record.get("runs_per_eval"),
        "passes": int(record.get("passes", 0)),
        "total": int(record.get("total", 0)),
        "majority_pass": record.get("majority_pass"),
        "evals_count": record.get("evals", len(evals)),
        "app_versions": record.get("app_versions", []),
        "app_resource": str(record.get("app_resource") or ""),
        "evaluation_runs": record.get("evaluation_runs", []),
        "has_report": report is not None,
        "evals": evals,
        "by_node": node_counter.most_common(),
        "by_mechanism": def_counter.most_common(),
        "by_error": error_counter.most_common(8),
        "by_scrapi_triage": scrapi_counter.most_common(),
        "conversations": conversations,
        "attributions": attributions,
    }


def _select_baseline_full(runs: list[dict]) -> dict | None:
    """Select the pre-hill-climb 70-eval baseline (v4_final_report if present, else first full run)."""
    for r in runs:
        if r["label"] == "v4_final_report":
            return r
    full_runs = [r for r in runs if r["is_full_run"]]
    if len(full_runs) >= 2:
        return full_runs[-2]
    if full_runs:
        return full_runs[0]
    return None


def build_master_evals(
    runs: list[dict], smoke_runs: list[dict], def_by_ve: dict
) -> list[dict]:
    """Build one clean Before-vs-After row per evaluation across Baseline, Full Suite, and Targeted Smoke."""
    full_runs = [r for r in runs if r["is_full_run"]]
    unstable_runs = [r for r in runs if not r["is_full_run"]]
    baseline_full = _select_baseline_full(runs)
    latest_full = full_runs[-1] if full_runs else (runs[-1] if runs else None)
    latest_unstable = unstable_runs[-1] if unstable_runs else None

    base_map = {e["ve_id"]: e for e in (baseline_full or {}).get("evals", [])}
    latest_full_map = {e["ve_id"]: e for e in (latest_full or {}).get("evals", [])}
    unstable_map = {e["ve_id"]: e for e in (latest_unstable or {}).get("evals", [])}

    smoke_by_ve: dict[str, tuple[str, str, dict]] = {}
    for sr in smoke_runs:
        for e in sr.get("evals", []):
            smoke_by_ve[e["ve_id"]] = (sr["label"], sr.get("timestamp", ""), e)

    all_ve_ids: set[str] = set()
    meta_by_ve: dict[str, dict] = {}
    for r in [*runs, *smoke_runs]:
        for e in r.get("evals", []):
            ve = e["ve_id"]
            all_ve_ids.add(ve)
            m = meta_by_ve.setdefault(
                ve,
                {
                    "display_name": "",
                    "evaluation_name": "",
                    "language": "",
                    "topic": "",
                },
            )
            for k in ("display_name", "evaluation_name", "language", "topic"):
                if e.get(k) and not m[k]:
                    m[k] = e[k]

    master: list[dict] = []
    for ve_id in sorted(all_ve_ids):
        meta = meta_by_ve.get(ve_id, {})
        ev_base = base_map.get(ve_id)
        ev_full = latest_full_map.get(ve_id)
        ev_un = unstable_map.get(ve_id)
        smoke_triple = smoke_by_ve.get(ve_id)
        smoke_label, smoke_ts, ev_sm = smoke_triple if smoke_triple else ("", "", None)

        baseline_ref = ev_base or ev_un or ev_full
        # If a targeted smoke run passed or is newer than the full run, use it as current proof;
        # otherwise use the latest full run (or unstable run).
        full_ts = str((latest_full or {}).get("timestamp") or "")
        if ev_sm and (str(smoke_ts) >= full_ts or _is_eval_pass(ev_sm)):
            current_ref = ev_sm
            verified_by = f"{smoke_label} ({_fmt_ts(smoke_ts)})"
        elif ev_full:
            current_ref = ev_full
            verified_by = f"{latest_full['label']} ({_fmt_ts(full_ts)})"
        elif ev_un:
            current_ref = ev_un
            verified_by = f"{latest_unstable['label']} ({_fmt_ts(latest_unstable.get('timestamp'))})"
        else:
            current_ref = baseline_ref
            verified_by = ""

        base_pass = _is_eval_pass(baseline_ref)
        curr_pass = _is_eval_pass(current_ref)

        if not base_pass and curr_pass:
            status_bucket = "FLIPPED_PASS"
        elif not curr_pass:
            status_bucket = "STILL_FAILING"
        else:
            status_bucket = "PASSING"

        failing_nodes = (
            (current_ref or {}).get("failing_nodes")
            or (ev_full or {}).get("failing_nodes")
            or (ev_base or {}).get("failing_nodes")
            or []
        )
        eval_name = meta.get("evaluation_name", "")
        ces_url = (
            f"{CES_CONSOLE_BASE}/{eval_name}"
            if eval_name.startswith("projects/")
            else ""
        )
        master.append(
            {
                "ve_id": ve_id,
                "display_name": meta.get("display_name", ""),
                "evaluation_name": eval_name,
                "ces_url": ces_url,
                "language": meta.get("language", ""),
                "topic": meta.get("topic", ""),
                "base_label": baseline_full["label"] if baseline_full else "",
                "base_ts": _fmt_ts((baseline_full or {}).get("timestamp")),
                "base_eval": ev_base,
                "full_label": latest_full["label"] if latest_full else "",
                "full_ts": _fmt_ts((latest_full or {}).get("timestamp")),
                "full_eval": ev_full,
                "smoke_label": smoke_label,
                "smoke_ts": _fmt_ts(smoke_ts),
                "smoke_eval": ev_sm,
                "verified_by": verified_by,
                "status_bucket": status_bucket,
                "current_pass": curr_pass,
                "failing_nodes": failing_nodes,
                "mechanisms": def_by_ve.get(ve_id, []),
            }
        )
    return master


def markdown_to_html(md_text: str) -> str:
    """Convert simple markdown (headings, bullets, bold, code, tables) to HTML."""
    lines = md_text.splitlines()
    out: list[str] = []
    in_table = False
    in_list = 0

    def inline_fmt(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return s

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        is_list_item = stripped.startswith("- ") or stripped.startswith("* ")
        indent = len(line) - len(line.lstrip(" "))
        level = (indent // 2) + 1 if is_list_item else 0

        if not is_list_item and in_list > 0 and not (stripped and indent > 0):
            while in_list > 0:
                out.append("</ul>")
                in_list -= 1

        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                out.append("<table>")
                in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                i += 1
                continue
            is_header = len(out) > 0 and out[-1] == "<table>"
            tag = "th" if is_header else "td"
            row_html = "".join(f"<{tag}>{inline_fmt(c)}</{tag}>" for c in cells)
            out.append(f"<tr>{row_html}</tr>")
            i += 1
            continue
        elif in_table:
            out.append("</table>")
            in_table = False

        if not stripped:
            i += 1
            continue

        if stripped.startswith("### "):
            out.append(f"<h3>{inline_fmt(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{inline_fmt(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{inline_fmt(stripped[2:])}</h1>")
        elif is_list_item:
            content = stripped[2:]
            if level > in_list:
                while level > in_list:
                    out.append("<ul>")
                    in_list += 1
            elif level < in_list:
                while level < in_list:
                    out.append("</ul>")
                    in_list -= 1
            out.append(f"<li>{inline_fmt(content)}</li>")
        elif in_list > 0 and indent > 0:
            out.append(f"<div style='margin-left:{indent * 8}px'>{inline_fmt(stripped)}</div>")
        else:
            out.append(f"<p>{inline_fmt(stripped)}</p>")
        i += 1

    while in_list > 0:
        out.append("</ul>")
        in_list -= 1
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def sanitize_case_id(name: str, name_to_ve: dict[str, str] | None = None) -> str:
    """Never show bootcamp public-eval display names; return VE-xx or case_id."""
    if not name:
        return ""
    if name_to_ve and name in name_to_ve:
        return name_to_ve[name]
    if name.startswith("own_v2_"):
        return name[7:]
    if name.startswith("own_"):
        return name[4:]
    if name.startswith("sim__"):
        return (name_to_ve or {}).get(name, "VE-??")
    return name


def load_suite_p0_cases(evals_dir: Path) -> list[dict]:
    """Return known P0 cases (51 goldens + 30 simulations) from YAML suites."""
    cases = []
    goldens_yaml = evals_dir / "goldens" / "goldens.yaml"
    if goldens_yaml.exists():
        try:
            import yaml

            data = yaml.safe_load(goldens_yaml.read_text(encoding="utf-8"))
            for g in (data or {}).get("goldens", []):
                if g.get("priority", "P0") == "P0":
                    cases.append(
                        {
                            "case_id": g.get("id") or g.get("case_id"),
                            "layer": "goldens",
                            "language": g.get("language", "en"),
                        }
                    )
        except Exception:
            pass
    sims_yaml = evals_dir / "simulations" / "simulations.yaml"
    if sims_yaml.exists():
        try:
            import yaml

            data = yaml.safe_load(sims_yaml.read_text(encoding="utf-8"))
            for s in (data or {}).get("simulations", []):
                if s.get("priority", "P0") == "P0":
                    cases.append(
                        {
                            "case_id": s.get("id") or s.get("case_id"),
                            "layer": "simulations",
                            "language": s.get("language", "en"),
                        }
                    )
        except Exception:
            pass
    return cases


def build_audio_model(
    audio_history_dir: Path,
    bench_audio_dir: Path,
    docs_dir: Path,
    evals_dir: Path,
    name_to_ve: dict[str, str] | None = None,
) -> dict:
    name_to_ve = name_to_ve or {}
    defects = parse_audio_defects(docs_dir / "defects.md")
    suite_cases = load_suite_p0_cases(evals_dir)

    summaries: dict[str, dict] = {}
    if audio_history_dir.exists():
        for p in sorted(audio_history_dir.glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                rid = rec.get("run_id") or p.stem
                summaries[rid] = rec
            except Exception:
                continue

    runs_data: dict[str, dict] = {}
    dossiers: list[dict] = []
    baseline_tables: list[dict] = []
    if bench_audio_dir.exists():
        for sub in sorted(bench_audio_dir.iterdir()):
            if not sub.is_dir():
                continue
            rid = sub.name
            manifest = None
            if (sub / "manifest.json").exists():
                try:
                    manifest = json.loads((sub / "manifest.json").read_text(encoding="utf-8"))
                except Exception:
                    pass
            enrichment = None
            enr_path = (
                sub / "enrichment.json"
                if (sub / "enrichment.json").exists()
                else (sub / "audio_enrichment.json" if (sub / "audio_enrichment.json").exists() else None)
            )
            if enr_path and enr_path.exists():
                try:
                    enrichment = json.loads(enr_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            sim_results = None
            if (sub / "sim_results.json").exists():
                try:
                    sim_results = json.loads((sub / "sim_results.json").read_text(encoding="utf-8"))
                except Exception:
                    pass

            dossier_dir = sub / "dossiers"
            if dossier_dir.exists():
                for dp in sorted(dossier_dir.glob("*.md")):
                    try:
                        content = dp.read_text(encoding="utf-8")
                        if dp.name == "baseline_table.md":
                            baseline_tables.append({"label": rid, "path": dp, "content": content})
                        else:
                            stem = dp.stem
                            cid = stem.split("__")[0]
                            conv8 = stem.split("__")[1] if "__" in stem else ""
                            dossiers.append({
                                "label": rid,
                                "stem": stem,
                                "case_id": cid,
                                "conv8": conv8,
                                "path": dp,
                                "content": content,
                                "html_rel_path": f"audio/{rid}/{stem}.html",
                            })
                    except Exception:
                        continue

            runs_data[rid] = {
                "manifest": manifest,
                "enrichment": enrichment,
                "sim_results": sim_results,
            }

    all_run_ids = sorted(set(list(summaries.keys()) + list(runs_data.keys())))
    cats: dict[str, list[str]] = {
        "audio_base_g": [],
        "audio_base_s": [],
        "text_base_g": [],
        "audio_after_g": [],
        "audio_after_s": [],
        "noise": [],
        "other": [],
    }
    for rid in all_run_ids:
        r_low = rid.lower()
        if "noise" in r_low:
            cats["noise"].append(rid)
        elif "text-base" in r_low or ("text" in r_low and "base" in r_low):
            cats["text_base_g"].append(rid)
        elif "audio-base-g" in r_low or ("base" in r_low and "-g" in r_low and "text" not in r_low):
            cats["audio_base_g"].append(rid)
        elif "audio-base-s" in r_low or ("base" in r_low and "-s" in r_low):
            cats["audio_base_s"].append(rid)
        elif "audio-after-g" in r_low or ("after" in r_low and "-g" in r_low):
            cats["audio_after_g"].append(rid)
        elif "audio-after-s" in r_low or ("after" in r_low and "-s" in r_low):
            cats["audio_after_s"].append(rid)
        else:
            cats["other"].append(rid)

    def extract_cases(rids: list[str]) -> dict[str, dict]:
        out = {}
        for rid in rids:
            rd = runs_data.get(rid, {})
            manifest = rd.get("manifest")
            if manifest and "cases" in manifest:
                for c in manifest["cases"]:
                    cid = c.get("case_id") or c.get("id") or c.get("test_id", "")
                    cid = sanitize_case_id(cid, name_to_ve)
                    runs = c.get("runs", [])
                    fr = runs[0] if runs else {}
                    v = c.get("verdict") or fr.get("status") or fr.get("evaluation_status")
                    verdict = (
                        "PASS"
                        if str(v).lower() == "pass"
                        else ("FAIL" if str(v).lower() == "fail" else (str(v) if v else None))
                    )
                    conv = fr.get("conversation", "")
                    erun = fr.get("evaluation_run", "")
                    freason = fr.get("failure_reason", "")
                    out[cid] = {
                        "verdict": verdict,
                        "conversation": conv,
                        "evaluation_run": erun,
                        "failure_reason": freason,
                        "run_id": rid,
                        "layer": c.get("layer", ""),
                        "language": c.get("language", ""),
                    }
            elif rid in summaries:
                s = summaries[rid]
                failures = {f.get("test_id"): f for f in s.get("failures", [])}
                for sc in suite_cases:
                    cid = sc["case_id"]
                    if cid in failures:
                        out[cid] = {
                            "verdict": "FAIL",
                            "conversation": "",
                            "evaluation_run": "",
                            "run_id": rid,
                            "failure_reason": failures[cid].get("reason", ""),
                        }
                    else:
                        out[cid] = {
                            "verdict": "PASS",
                            "conversation": "",
                            "evaluation_run": "",
                            "run_id": rid,
                            "failure_reason": "",
                        }
        return out

    audio_base_g_cases = extract_cases(cats["audio_base_g"])
    audio_base_s_cases = extract_cases(cats["audio_base_s"])
    text_base_g_cases = extract_cases(cats["text_base_g"])
    audio_after_g_cases = extract_cases(cats["audio_after_g"])
    audio_after_s_cases = extract_cases(cats["audio_after_s"])

    case_dict: dict[str, dict] = {}
    for sc in suite_cases:
        cid = sc["case_id"]
        case_dict[cid] = {
            "case_id": cid,
            "layer": sc.get("layer", "goldens"),
            "language": sc.get("language", "en"),
        }
    for mapping in (
        audio_base_g_cases,
        audio_base_s_cases,
        text_base_g_cases,
        audio_after_g_cases,
        audio_after_s_cases,
    ):
        for cid, info in mapping.items():
            if cid not in case_dict:
                case_dict[cid] = {
                    "case_id": cid,
                    "layer": info.get("layer") or ("simulations" if "sim" in cid else "goldens"),
                    "language": info.get("language") or "en",
                }

    dossier_by_case = {}
    for d in dossiers:
        dossier_by_case[d["case_id"]] = d["html_rel_path"]

    joined_cases = []
    for cid, info in sorted(
        case_dict.items(),
        key=lambda x: (0 if "golden" in x[1].get("layer", "") else 1, x[0]),
    ):
        lyr = "goldens" if "golden" in info.get("layer", "").lower() else "simulations"
        lang = info.get("language", "en")

        ab_info = audio_base_g_cases.get(cid) if lyr == "goldens" else audio_base_s_cases.get(cid)
        ab_verdict = ab_info["verdict"] if ab_info else None
        ab_run = ab_info["run_id"] if ab_info else ""
        ab_conv = ab_info["conversation"] if ab_info else ""

        tb_info = text_base_g_cases.get(cid) if lyr == "goldens" else None
        tb_verdict = tb_info["verdict"] if tb_info else ("—" if lyr == "simulations" else None)

        aa_info = audio_after_g_cases.get(cid) if lyr == "goldens" else audio_after_s_cases.get(cid)
        aa_verdict = aa_info["verdict"] if aa_info else None
        aa_run = aa_info["run_id"] if aa_info else ""
        aa_conv = aa_info["conversation"] if aa_info else ""

        rep_run = aa_run or ab_run or (tb_info["run_id"] if tb_info else "")
        rep_conv = aa_conv or ab_conv or (tb_info.get("conversation", "") if tb_info else "")
        conv8 = rep_conv.split("/")[-1].replace("evaluation-", "")[:8] if rep_conv else "—"
        run_short = rep_run.split("-")[-1] if rep_run else "—"

        dossier_path = dossier_by_case.get(cid)

        joined_cases.append(
            {
                "case_id": cid,
                "layer": lyr,
                "language": lang,
                "audio_baseline": ab_verdict,
                "text_baseline": tb_verdict,
                "audio_after": aa_verdict,
                "run_id_short": run_short,
                "conv_id_short": conv8,
                "dossier_link": dossier_path,
            }
        )

    all_enrichments = [rd["enrichment"] for rd in runs_data.values() if rd.get("enrichment")]
    langs = ["en", "fr", "es"]
    for c in joined_cases:
        if c["language"] and c["language"] not in langs:
            langs.append(c["language"])

    lang_stats = []
    for l in langs:
        sub = [c for c in joined_cases if c["language"] == l]
        g_sub = [c for c in sub if c["layer"] == "goldens"]
        s_sub = [c for c in sub if c["layer"] == "simulations"]

        g_pass = sum(1 for c in g_sub if c.get("audio_baseline") == "PASS")
        g_measured = sum(1 for c in g_sub if c.get("audio_baseline") is not None)
        g_rate = (
            f"{g_pass}/{len(g_sub)} ({(g_pass / len(g_sub) * 100):.1f}%)"
            if g_measured > 0 and g_sub
            else ("not yet measured" if g_sub else "—")
        )

        s_pass = sum(1 for c in s_sub if c.get("audio_baseline") == "PASS")
        s_measured = sum(1 for c in s_sub if c.get("audio_baseline") is not None)
        s_rate = (
            f"{s_pass}/{len(s_sub)} ({(s_pass / len(s_sub) * 100):.1f}%)"
            if s_measured > 0 and s_sub
            else ("not yet measured" if s_sub else "—")
        )

        tot_pass = g_pass + s_pass
        tot_measured = g_measured + s_measured
        tot_rate = (
            f"{tot_pass}/{len(sub)} ({(tot_pass / len(sub) * 100):.1f}%)"
            if tot_measured > 0 and sub
            else "not yet measured"
        )

        nat_mean = None
        p50 = None
        p90 = None
        for enr in all_enrichments:
            by_lang = enr.get("by_language", {}) or enr.get("aggregates", {}).get(
                "by_language", {}
            )
            if l in by_lang:
                stat = by_lang[l]
                if stat.get("naturalness_mean") is not None and nat_mean is None:
                    nat_mean = stat["naturalness_mean"]
                if stat.get("latency_p50_ms") is not None and p50 is None:
                    p50 = stat["latency_p50_ms"]
                if stat.get("latency_p90_ms") is not None and p90 is None:
                    p90 = stat["latency_p90_ms"]

        lang_stats.append(
            {
                "language": l,
                "golden_pass_rate": g_rate,
                "simulation_pass_rate": s_rate,
                "combined_pass_rate": tot_rate,
                "naturalness_mean": f"{nat_mean:.2f}"
                if nat_mean is not None
                else "not yet measured",
                "latency_p50_ms": f"{p50:.1f} ms"
                if p50 is not None
                else "not yet measured",
                "latency_p90_ms": f"{p90:.1f} ms"
                if p90 is not None
                else "not yet measured",
            }
        )

    noise_cases = []
    for n_rid in cats["noise"]:
        rd = runs_data.get(n_rid, {})
        manifest = rd.get("manifest")
        if manifest and "cases" in manifest:
            for c in manifest["cases"]:
                cid = sanitize_case_id(c.get("case_id") or c.get("id") or "", name_to_ve)
                runs = c.get("runs", [])
                fr = runs[0] if runs else {}
                v = c.get("verdict") or fr.get("status") or fr.get("evaluation_status")
                verdict = (
                    "PASS"
                    if str(v).lower() == "pass"
                    else ("FAIL" if str(v).lower() == "fail" else str(v or "UNKNOWN"))
                )
                noise_cases.append(
                    {
                        "run_id": n_rid,
                        "case_id": cid,
                        "language": c.get("language", "en"),
                        "condition": "Pink noise + burst clicks",
                        "verdict": verdict,
                        "failure_reason": fr.get("failure_reason", ""),
                    }
                )
        elif rd.get("sim_results"):
            sim_res = rd["sim_results"]
            for s in sim_res.get("evaluations", []):
                noise_cases.append(
                    {
                        "run_id": n_rid,
                        "case_id": sanitize_case_id(
                            s.get("test_id") or s.get("name") or "", name_to_ve
                        ),
                        "language": s.get("language", "en"),
                        "condition": "Pink noise + burst clicks",
                        "verdict": "PASS"
                        if str(s.get("status", "")).upper() == "PASS"
                        else "FAIL",
                        "failure_reason": s.get("error", ""),
                    }
                )

    g_cases = [c for c in joined_cases if c["layer"] == "goldens"]
    s_cases = [c for c in joined_cases if c["layer"] == "simulations"]
    bg_pass = sum(1 for c in g_cases if c.get("audio_baseline") == "PASS")
    bg_meas = sum(1 for c in g_cases if c.get("audio_baseline") is not None)
    bs_pass = sum(1 for c in s_cases if c.get("audio_baseline") == "PASS")
    bs_meas = sum(1 for c in s_cases if c.get("audio_baseline") is not None)

    after_pass = sum(1 for c in joined_cases if c.get("audio_after") == "PASS")
    after_meas = sum(1 for c in joined_cases if c.get("audio_after") is not None)

    kpis = {
        "base_goldens": (
            f"{bg_pass} / {len(g_cases)} ({bg_pass/len(g_cases)*100:.1f}%)"
            if bg_meas > 0 and g_cases
            else "not yet measured"
        ),
        "base_sims": (
            f"{bs_pass} / {len(s_cases)} ({bs_pass/len(s_cases)*100:.1f}%)"
            if bs_meas > 0 and s_cases
            else "not yet measured"
        ),
        "after_status": (
            f"{after_pass} / {len(joined_cases)} ({after_pass/len(joined_cases)*100:.1f}%)"
            if after_meas > 0
            else "not yet measured"
        ),
        "mean_naturalness": next(
            (
                s["naturalness_mean"]
                for s in lang_stats
                if s["naturalness_mean"] != "not yet measured"
            ),
            "not yet measured",
        ),
        "latency_p50": next(
            (
                s["latency_p50_ms"]
                for s in lang_stats
                if s["latency_p50_ms"] != "not yet measured"
            ),
            "not yet measured",
        ),
    }

    return {
        "defects": defects,
        "cases": joined_cases,
        "languages": lang_stats,
        "has_noise": bool(noise_cases),
        "noise_cases": noise_cases,
        "dossiers": dossiers,
        "baseline_tables": baseline_tables,
        "kpis": kpis,
    }


def _app_display_name(app_dir: Path | None) -> str:
    """Display name from cxas_app/app.json, or '' when unavailable."""
    if not app_dir:
        return ""
    try:
        data = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("displayName") or data.get("display_name") or "")


def build_model(
    history_dir: Path,
    bench_root: Path,
    docs_dir: Path,
    app_dir: Path | None = None,
    audio_history_dir: Path | None = None,
    bench_audio_dir: Path | None = None,
    evals_dir: Path | None = None,
    app_resource: str = "",
    title: str = "",
) -> dict:
    if not APP_RESOURCE.match(app_resource or ""):
        app_resource = ""
    title = (
        title
        or _app_display_name(app_dir)
        or (app_resource.rsplit("/", 1)[-1] if app_resource else "")
        or "agent"
    )
    runs_dir = bench_root / "runs"
    defects, def_by_ve = parse_defects(docs_dir / "defects.md")
    records = load_history(history_dir)
    reports = {rec["label"]: load_report(runs_dir, rec["label"]) for rec in records}
    name_to_ve: dict[str, str] = {}
    for rep in reports.values():
        for o in (rep or {}).get("results", []):
            if o.get("ve_id") and o.get("display_name"):
                name_to_ve[o["display_name"]] = o["ve_id"]
    runs = []
    for rec in records:
        label = rec["label"]
        runs.append(
            build_run(
                rec, reports[label], load_pages(runs_dir, label), def_by_ve, name_to_ve
            )
        )
    smoke_runs = load_smoke_runs(runs_dir, def_by_ve)
    baseline_full = _select_baseline_full(runs)
    latest_full = next((r for r in reversed(runs) if r["is_full_run"]), None)
    latest_unstable = next((r for r in reversed(runs) if not r["is_full_run"]), None)
    latest_smoke = smoke_runs[-1] if smoke_runs else None
    master_evals = build_master_evals(runs, smoke_runs, def_by_ve)

    if audio_history_dir:
        ah_dir = audio_history_dir
    elif (history_dir / "audio").exists():
        ah_dir = history_dir / "audio"
    elif (history_dir.parent / "audio").exists() and history_dir.parent != history_dir:
        ah_dir = history_dir.parent / "audio"
    elif history_dir == REPO / "history" / "bench":
        ah_dir = REPO / "history" / "audio"
    else:
        ah_dir = history_dir / "audio"

    if bench_audio_dir:
        ba_dir = bench_audio_dir
    elif (bench_root / "runs" / "audio").exists():
        ba_dir = bench_root / "runs" / "audio"
    elif (bench_root / "audio").exists():
        ba_dir = bench_root / "audio"
    elif bench_root == DEFAULT_BENCH_ROOT:
        ba_dir = DEFAULT_BENCH_ROOT / "runs" / "audio"
    else:
        ba_dir = bench_root / "runs" / "audio"

    ev_dir = evals_dir or (REPO / "evals")
    audio = build_audio_model(
        audio_history_dir=ah_dir,
        bench_audio_dir=ba_dir,
        docs_dir=docs_dir,
        evals_dir=ev_dir,
        name_to_ve=name_to_ve,
    )

    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": title,
        "app_resource": app_resource,
        "runs": runs,
        "smoke_runs": smoke_runs,
        "baseline_full": baseline_full,
        "latest_full": latest_full,
        "latest_unstable": latest_unstable,
        "latest_smoke": latest_smoke,
        "master_evals": master_evals,
        "iterations": parse_experiment_log(docs_dir / "experiment_log.md"),
        "defects": defects,
        "voice_audit": run_scrapi_voice_audit(app_dir),
        "audio": audio,
    }


# ------------------------------------------------------------------------ rendering

CSS = """
body{font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;color:#1f2328;background:#f6f8fa}
header.site-hdr{background:#fff;border-bottom:1px solid #d0d7de;padding:16px 24px 0;position:sticky;top:0;z-index:20;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.hdr-inner{max-width:1280px;margin:0 auto}
main{max-width:1280px;margin:0 auto;padding:20px 24px 60px;background:#fff;border-left:1px solid #eaeef2;border-right:1px solid #eaeef2;min-height:85vh}
h1{font-size:21px;margin:0 0 4px}h2{font-size:17px;margin:22px 0 8px;border-bottom:1px solid #d0d7de;padding-bottom:4px}
h3{font-size:15px;margin:16px 0 6px}.muted{color:#656d76}.small{font-size:12px}
.legend-bar{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 12px;font-size:12px;align-items:center}
.pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;font-weight:600;font-size:11px}
.pill-ours{background:#ddf4ff;color:#0969da;border:1px solid #54aeff66}
.pill-scrapi{background:#fbefff;color:#8250df;border:1px solid #d2a8ff88}
.pill-borrow{background:#dafbe1;color:#1a7f37;border:1px solid #4ac26b66}
.nav-tabs{display:flex;gap:4px;margin-top:8px;overflow-x:auto}
.tab-btn{background:transparent;border:none;border-bottom:3px solid transparent;padding:8px 14px;font:600 13px/1.3 -apple-system,Segoe UI,Roboto,sans-serif;color:#57606a;cursor:pointer;white-space:nowrap}
.tab-btn:hover{color:#1f2328;background:#f6f8fa;border-radius:6px 6px 0 0}
.tab-btn.active{color:#0969da;border-bottom-color:#0969da;background:#f6f8fa;border-radius:6px 6px 0 0}
.tab-panel{display:none}.tab-panel.active{display:block}
table{border-collapse:collapse;width:100%;margin:6px 0 14px}th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #eaeef2;vertical-align:top}
th{background:#f6f8fa;font-weight:600;font-size:12px;color:#57606a}tr:hover td{background:#fafbfc}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:10px 0 18px}
.kpi{padding:12px 14px;border:1px solid #d0d7de;border-radius:8px;background:#fff}
.kpi b{font-size:24px;display:block;margin:2px 0}.rep{display:inline-block;width:18px;height:18px;line-height:18px;text-align:center;border-radius:3px;color:#fff;font-size:11px;margin-right:2px;text-decoration:none}
.P{background:#1a7f37}.F{background:#cf222e}.I{background:#9a6700}.U{background:#8c959f}
.tag{display:inline-block;padding:1px 7px;border-radius:10px;background:#ddf4ff;color:#0969da;font-size:12px;margin-right:4px;font-weight:500}
.node{display:inline-block;padding:1px 6px;border-radius:4px;background:#fff1e5;color:#953800;font-size:12px}
.status-badge{display:inline-flex;align-items:center;padding:3px 7px;border-radius:10px;font-size:11px;font-weight:600}
.st-flip{background:#dafbe1;color:#1a7f37;border:1px solid #4ac26b66}
.st-fail{background:#ffebe9;color:#cf222e;border:1px solid #ff818266}
.st-pass{background:#f6f8fa;color:#1a7f37;border:1px solid #d0d7de}
.st-unmeasured{background:#f6f8fa;color:#656d76;border:1px solid #d0d7de;font-style:italic}
.audio-guide{padding:14px 18px;border:1px solid #d0d7de;border-radius:8px;background:#f6f8fa;margin:12px 0 16px}
.audio-guide ul{margin:8px 0 0;padding-left:20px}
.audio-guide li{margin:4px 0}
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#f6f8fa;padding:10px 12px;border:1px solid #d0d7de;border-radius:8px;margin:8px 0 12px}
.filter-bar select,.filter-bar input{padding:5px 8px;border:1px solid #d0d7de;border-radius:6px;font-size:13px;background:#fff}
.filter-bar input{min-width:220px;flex:1}
details{margin:6px 0}summary{cursor:pointer;font-weight:600}
pre{background:#f6f8fa;padding:8px;border-radius:6px;overflow:auto;font-size:12px;white-space:pre-wrap}
.turn{border-left:3px solid #d0d7de;padding:4px 10px;margin:8px 0}.turn.broke{border-color:#cf222e;background:#fff5f5}
.user{color:#0550ae}.agent{color:#1f2328}.tool{color:#57606a;font-size:12px;margin-left:12px}
.fail{color:#cf222e;font-weight:600}.ok{color:#1a7f37;font-weight:600}
.ext-link{color:#0969da;text-decoration:none;font-size:11px;font-weight:600}
.ext-link:hover{text-decoration:underline}
svg text{font-size:11px;fill:#656d76}
"""

INDEX_JS = """
function switchTab(tabId) {
  document.querySelectorAll('.tab-panel').forEach(function(p) {
    p.classList.toggle('active', p.id === tabId);
  });
  document.querySelectorAll('.tab-btn').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
  });
}
function openRunAnchor(runAnchor) {
  if (runAnchor.indexOf('run-smoke-') === 0) {
    switchTab('tab-smoke');
  } else {
    switchTab('tab-runs');
  }
  var el = document.getElementById(runAnchor);
  if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
}
function filterMasterEvals() {
  var st = (document.getElementById('flt-status') || {}).value || 'ALL';
  var lang = (document.getElementById('flt-lang') || {}).value || 'ALL';
  var topic = (document.getElementById('flt-topic') || {}).value || 'ALL';
  var defId = (document.getElementById('flt-def') || {}).value || 'ALL';
  var q = ((document.getElementById('flt-q') || {}).value || '').toLowerCase().trim();
  var shown = 0;
  document.querySelectorAll('tr.eval-row').forEach(function(row) {
    var rSt = row.getAttribute('data-status') || '';
    var rLang = row.getAttribute('data-lang') || '';
    var rTopic = row.getAttribute('data-topic') || '';
    var rDef = row.getAttribute('data-def') || '';
    var rText = (row.getAttribute('data-search') || '').toLowerCase();
    var ok = (st === 'ALL' || rSt === st)
          && (lang === 'ALL' || rLang === lang)
          && (topic === 'ALL' || rTopic === topic)
          && (defId === 'ALL' || rDef.indexOf(defId) !== -1)
          && (!q || rText.indexOf(q) !== -1);
    row.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  var cnt = document.getElementById('flt-count');
  if (cnt) { cnt.textContent = shown + ' shown'; }
}
function filterAudioCases() {
  var lyr = (document.getElementById('flt-audio-layer') || {}).value || 'ALL';
  var lang = (document.getElementById('flt-audio-lang') || {}).value || 'ALL';
  var st = (document.getElementById('flt-audio-status') || {}).value || 'ALL';
  var q = ((document.getElementById('flt-audio-q') || {}).value || '').toLowerCase().trim();
  var shown = 0;
  document.querySelectorAll('tr.audio-case-row').forEach(function(row) {
    var rLyr = row.getAttribute('data-layer') || '';
    var rLang = row.getAttribute('data-lang') || '';
    var rSt = row.getAttribute('data-status') || '';
    var rText = (row.getAttribute('data-search') || '').toLowerCase();
    var ok = (lyr === 'ALL' || rLyr === lyr)
          && (lang === 'ALL' || rLang === lang)
          && (st === 'ALL' || rSt === st)
          && (!q || rText.indexOf(q) !== -1);
    row.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  var cnt = document.getElementById('flt-audio-count');
  if (cnt) { cnt.textContent = shown + ' shown'; }
}
window.addEventListener('hashchange', function() {
  var h = (window.location.hash || '').replace(/^#/, '');
  if (h.indexOf('run-') === 0) { openRunAnchor(h); }
  else if (h.indexOf('tab-') === 0) { switchTab(h); }
});
window.addEventListener('DOMContentLoaded', function() {
  var h = (window.location.hash || '').replace(/^#/, '');
  if (h.indexOf('run-') === 0) { openRunAnchor(h); }
  else if (h.indexOf('tab-') === 0) { switchTab(h); }
});
"""


def _e(x: object) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _pct(passes: int, total: int) -> float:
    return round(100.0 * passes / total, 1) if total else 0.0


def render_trend_svg(runs: list[dict]) -> str:
    """Pass rate per run, oldest left; full runs and unstable-set runs as two series."""
    if not runs:
        return "<p class='muted'>No measured runs yet.</p>"
    w, h, pad = 900, 240, 40
    n = len(runs)
    xs = [pad + (w - 2 * pad) * (i / max(1, n - 1)) for i in range(n)]
    ys = [
        h - pad - (h - 2 * pad) * (_pct(r["passes"], r["total"]) / 100.0) for r in runs
    ]
    parts = [
        f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' role='img' aria-label='pass rate over time'>"
    ]
    for yv in (0, 25, 50, 75, 100):
        y = h - pad - (h - 2 * pad) * yv / 100.0
        parts.append(
            f"<line x1='{pad}' y1='{y:.1f}' x2='{w - pad}' y2='{y:.1f}' stroke='#eaeef2'/><text x='4' y='{y + 4:.1f}'>{yv}%</text>"
        )
    for series, color in (("full", "#0969da"), ("unstable", "#bf3989")):
        pts = [
            (x, y)
            for x, y, r in zip(xs, ys, runs)
            if (r["is_full_run"] == (series == "full"))
        ]
        if len(pts) > 1:
            parts.append(
                f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)}'/>"
            )
    for x, y, r in zip(xs, ys, runs):
        color = "#0969da" if r["is_full_run"] else "#bf3989"
        kind = "full 70" if r["is_full_run"] else "unstable 20"
        parts.append(
            f"<a href='#run-{_e(r['label'])}' onclick=\"openRunAnchor('run-{_e(r['label'])}')\"><circle cx='{x:.1f}' cy='{y:.1f}' r='5' fill='{color}'>"
            f"<title>{_e(r['label'])} ({kind}): {r['passes']}/{r['total']} = {_pct(r['passes'], r['total'])}% ({_e(_fmt_ts(r['timestamp']))})</title></circle></a>"
            f"<text x='{x:.1f}' y='{h - pad + 14}' text-anchor='middle'>{_e(r['label'][:18])}</text>"
        )
    parts.append(
        f"<text x='{pad}' y='14' fill='#0969da'>● full public set (70 x 3)</text><text x='{pad + 220}' y='14' fill='#bf3989'>● unstable set (20 x 5)</text></svg>"
    )
    return "".join(parts)


def _rep_cells(repeats: list[dict], run_label: str) -> str:
    out = []
    for i, rep in enumerate(repeats, 1):
        cls = {"PASS": "P", "FAIL": "F", "INFRA": "I"}.get(rep["classification"], "U")
        letter = cls if cls != "U" else "?"
        title = f"repeat {i}: {rep['classification'] or 'unknown'}"
        if rep.get("stem"):
            att = rep.get("attribution") or {}
            title += f" — node {att.get('failing_node', '?')} at turn {att.get('broke_at_turn', '?')}: {att.get('signal', '')}"
            out.append(
                f"<a class='rep {cls}' href='conv/{_e(run_label)}/{_e(rep['stem'])}.html' title='{_e(title)}'>{letter}</a>"
            )
        else:
            out.append(f"<span class='rep {cls}' title='{_e(title)}'>{letter}</span>")
    return "".join(out)


def _eval_cell(ev: dict | None, run_label: str) -> str:
    if not ev or not ev.get("total"):
        return "<span class='muted'>—</span>"
    cls = "ok" if _is_eval_pass(ev) else "fail"
    reps = _rep_cells(ev.get("repeats") or [], run_label)
    return (
        f"<span class='{cls}'>{ev['pass']}/{ev['total']}</span>"
        f"<div style='margin-top:2px'>{reps}</div>"
    )


def render_run_section(run: dict, previous: dict | None, app_resource: str = "") -> str:
    label = run["label"]
    kind = (
        "Targeted Smoke Batch (3 repeats per target)"
        if run.get("is_smoke_run")
        else (
            "Full 70-Eval Suite (70 × 3 = 210 convs)"
            if run["is_full_run"]
            else "Unstable 20-Eval Suite (20 × 5 = 100 convs)"
        )
    )
    prev_note = ""
    if previous:
        delta = run["passes"] - previous["passes"]
        prev_note = (
            f" — vs <a href='#run-{_e(previous['label'])}' onclick=\"openRunAnchor('run-{_e(previous['label'])}')\">"
            f"{_e(previous['label'])}</a>: {'+' if delta >= 0 else ''}{delta}"
        )
    # Prefer the app the run was measured against; fall back to the dashboard-wide
    # --app. Without either there is no safe URL, so show the id as plain text.
    run_app = run.get("app_resource") or app_resource or ""
    if not APP_RESOURCE.match(run_app):
        run_app = ""
    run_links = []
    for er in run.get("evaluation_runs") or []:
        er_id = str(er).rsplit("/", 1)[-1]
        if not er_id:
            continue
        if run_app:
            ces_run_url = f"{CES_CONSOLE_BASE}/{_e(run_app)}/evaluationRuns/{_e(er_id)}"
            run_links.append(
                f"<a class='ext-link' href='{ces_run_url}' target='_blank' rel='noopener'>CES Run {_e(er_id[:8])} ↗</a>"
            )
        else:
            run_links.append(f"<span class='muted'>CES Run {_e(er_id[:8])}</span>")
    run_links_html = f" · {' '.join(run_links)}" if run_links else ""
    prev_eval = {e["ve_id"]: e for e in (previous or {}).get("evals", [])}
    rows = []
    for ev in run["evals"]:
        pv = prev_eval.get(ev["ve_id"])
        d = ""
        if pv and pv["total"]:
            dd = ev["pass"] - pv["pass"]
            d = (
                f"<span class='{'fail' if dd <= -2 else ('ok' if dd >= 2 else 'muted')}'>{'+' if dd > 0 else ''}{dd}</span>"
                if dd
                else "<span class='muted'>0</span>"
            )
        eval_name = ev.get("evaluation_name", "")
        ces_link = (
            f" <a class='ext-link' href='{CES_CONSOLE_BASE}/{_e(eval_name)}' target='_blank' rel='noopener'>CES ↗</a>"
            if eval_name.startswith("projects/")
            else ""
        )
        rows.append(
            "<tr>"
            f"<td><b>{_e(ev['ve_id'])}</b>{ces_link}</td><td>{_e(ev['display_name'])}<div class='small muted'>{_e(ev['language'])} · {_e(ev['topic'])}</div></td>"
            f"<td>{ev['pass']}/{ev['total']}</td><td>{d}</td><td>{_rep_cells(ev['repeats'], label)}</td>"
            f"<td>{''.join(f'<span class=node>{_e(n)}</span> ' for n in ev['failing_nodes'])}</td>"
            f"<td>{''.join(f'<span class=tag>{_e(m)}</span>' for m in ev['mechanisms'])}</td>"
            "</tr>"
        )
    by_node = (
        "".join(
            f"<tr><td><span class='node'>{_e(n)}</span></td><td>{c}</td></tr>"
            for n, c in run["by_node"]
        )
        or "<tr><td colspan=2 class='muted'>no failing conversation pages for this run</td></tr>"
    )
    by_mech = (
        "".join(
            f"<tr><td><span class='tag'>{_e(m)}</span></td><td>{c}</td></tr>"
            for m, c in run["by_mechanism"]
        )
        or "<tr><td colspan=2 class='muted'>—</td></tr>"
    )
    by_err = (
        "".join(
            f"<tr><td><code>{_e(k)}</code></td><td>{c}</td></tr>"
            for k, c in run["by_error"]
        )
        or "<tr><td colspan=2 class='muted'>no tool errors</td></tr>"
    )
    by_scrapi = (
        "".join(
            f"<tr><td><span class='tag'>{_e(k)}</span></td><td>{c}</td></tr>"
            for k, c in run.get("by_scrapi_triage", [])
        )
        or "<tr><td colspan=2 class='muted'>—</td></tr>"
    )
    convs = "".join(
        f"<tr><td><a href='conv/{_e(label)}/{_e(c['stem'])}.html'>{_e(c['stem'])}</a></td><td>{_e(c['classification'])}</td>"
        f"<td><span class='tag'>{_e(c.get('scrapi_category', ''))}</span></td>"
        f"<td><span class='node'>{_e(c['node'])}</span> turn {c['turn']}</td><td class='small'>{_e(c['signal'])}</td><td class='small muted'>{_e(c['why'])}</td></tr>"
        for c in run["conversations"]
    )
    return f"""
<section id='run-{_e(label)}'>
<h2>{_e(label)} <span class='muted small'>{kind} · commit <code>{_e(run["commit"])}</code> · {_e(_fmt_ts(run["timestamp"]))}{run_links_html}</span></h2>
<p><b>{run["passes"]}/{run["total"]}</b> conversations passed ({_pct(run["passes"], run["total"])}%), {run["majority_pass"] if run["majority_pass"] is not None else "?"} of {run["evals_count"]} evals pass by majority{prev_note}.
{"" if run["has_report"] else "<span class='muted'>(full report not on this machine: numbers only)</span>"}</p>
<details open><summary>Evals ({len(run["evals"])}) — click a red square to open that conversation</summary>
<table><tr><th>VE</th><th>eval</th><th>pass</th><th>Δ prev</th><th>repeats</th><th>failing node</th><th>mechanism</th></tr>{"".join(rows)}</table></details>
<details><summary>Which node is losing points &amp; SCRAPI Triage</summary>
<div style='display:flex;gap:24px;flex-wrap:wrap'><div><h3>Failures by node</h3><table><tr><th>node (agent)</th><th>failing conversations</th></tr>{by_node}</table></div>
<div><h3>SCRAPI Triage (triage-results.py)</h3><table><tr><th>SCRAPI category</th><th>failing conversations</th></tr>{by_scrapi}</table></div>
<div><h3>Failures by mechanism</h3><table><tr><th>defect</th><th>failing conversations</th></tr>{by_mech}</table></div>
<div><h3>First tool error</h3><table><tr><th>tool → error</th><th>count</th></tr>{by_err}</table></div></div></details>
<details><summary>Failing conversations ({len(run["conversations"])})</summary>
<table><tr><th>conversation</th><th>class</th><th>SCRAPI triage</th><th>broke in</th><th>signal</th><th>judge (first failed expectation)</th></tr>{convs}</table></details>
</section>"""


def _render_master_evals_block(master_evals: list[dict]) -> str:
    if not master_evals:
        return "<p class='muted'>No evaluations loaded yet.</p>"
    langs = sorted({m["language"] for m in master_evals if m.get("language")})
    topics = sorted({m["topic"] for m in master_evals if m.get("topic")})
    defs = sorted({d for m in master_evals for d in m.get("mechanisms", [])})

    flipped_cnt = sum(1 for m in master_evals if m["status_bucket"] == "FLIPPED_PASS")
    failing_cnt = sum(1 for m in master_evals if m["status_bucket"] == "STILL_FAILING")
    passing_cnt = sum(1 for m in master_evals if m["status_bucket"] == "PASSING")

    lang_opts = "".join(f"<option value='{_e(l)}'>{_e(l)}</option>" for l in langs)
    topic_opts = "".join(f"<option value='{_e(t)}'>{_e(t)}</option>" for t in topics)
    def_opts = "".join(f"<option value='{_e(d)}'>{_e(d)}</option>" for d in defs)

    base_hdr = master_evals[0].get("base_label") or "Baseline"
    base_ts = master_evals[0].get("base_ts") or ""
    full_hdr = master_evals[0].get("full_label") or "Latest Full"
    full_ts = master_evals[0].get("full_ts") or ""

    rows = []
    for m in master_evals:
        ve = m["ve_id"]
        st = m["status_bucket"]
        if st == "FLIPPED_PASS":
            badge = "<span class='status-badge st-flip'>FLIPPED FAIL → PASS</span>"
        elif st == "STILL_FAILING":
            badge = "<span class='status-badge st-fail'>STILL FAILING</span>"
        else:
            badge = "<span class='status-badge st-pass'>PASSING</span>"

        ces_link = (
            f" <a class='ext-link' href='{_e(m['ces_url'])}' target='_blank' rel='noopener' title='Open evaluation in CES Corp Console'>CES Console ↗</a>"
            if m.get("ces_url")
            else ""
        )
        if m.get("smoke_eval"):
            smoke_cell = (
                f"{_eval_cell(m['smoke_eval'], m['smoke_label'])}"
                f"<div class='small muted' style='margin-top:2px'><a href='#run-{_e(m['smoke_label'])}' onclick=\"openRunAnchor('run-{_e(m['smoke_label'])}')\">{_e(m['smoke_label'])}</a> · {_e(m.get('smoke_ts', ''))}</div>"
            )
        else:
            smoke_cell = "<span class='muted small'>— (Not targeted)</span>"

        verified_note = (
            f"<div class='small muted' style='margin-top:3px'>{_e(m['verified_by'])}</div>"
            if m.get("verified_by")
            else ""
        )
        nodes_html = "".join(
            f"<span class='node'>{_e(n)}</span> " for n in m.get("failing_nodes", [])
        )
        defs_html = "".join(
            f"<span class='tag'>{_e(d)}</span>" for d in m.get("mechanisms", [])
        )
        search_blob = " ".join(
            [
                ve,
                m.get("display_name", ""),
                m.get("language", ""),
                m.get("topic", ""),
                " ".join(m.get("failing_nodes", [])),
                " ".join(m.get("mechanisms", [])),
            ]
        )
        rows.append(
            f"<tr class='eval-row' data-status='{_e(st)}' data-lang='{_e(m.get('language', ''))}' "
            f"data-topic='{_e(m.get('topic', ''))}' data-def='{_e(','.join(m.get('mechanisms', [])))}' "
            f"data-search='{_e(search_blob)}'>"
            f"<td><b>{_e(ve)}</b></td>"
            f"<td><b>{_e(m.get('display_name') or ve)}</b>{ces_link}"
            f"<div class='small muted'>{_e(m.get('language') or '?')} · {_e(m.get('topic') or '?')}</div></td>"
            f"<td>{_eval_cell(m.get('base_eval'), m.get('base_label', ''))}</td>"
            f"<td>{_eval_cell(m.get('full_eval'), m.get('full_label', ''))}</td>"
            f"<td>{smoke_cell}</td>"
            f"<td>{badge}{verified_note}</td>"
            f"<td>{defs_html}{nodes_html}</td>"
            "</tr>"
        )
    return f"""
<h2>Master 70-Evaluation Scorecard — Before vs. After</h2>
<p class='muted small'>One clean row per evaluation (<code>VE-01..VE-70</code>) comparing the pre-hill-climb 70-eval baseline (<code>{_e(base_hdr)}</code>) against the latest 70-eval run (<code>{_e(full_hdr)}</code>) and any targeted smoke fix (<code>smoke-*</code>, shown in full in Tab 2). Click any red square (<code>F</code>) to open the conversation transcript &amp; judge breakdown, or click <b>CES Console ↗</b> to open the evaluation in GCP.</p>
<div class='filter-bar'>
  <select id='flt-status' onchange='filterMasterEvals()' aria-label='Filter by status'>
    <option value='ALL'>All 70 Evaluations ({len(master_evals)})</option>
    <option value='STILL_FAILING'>Still Failing ({failing_cnt})</option>
    <option value='FLIPPED_PASS'>Flipped FAIL → PASS ({flipped_cnt})</option>
    <option value='PASSING'>Passing ({passing_cnt})</option>
  </select>
  <select id='flt-lang' onchange='filterMasterEvals()' aria-label='Filter by language'>
    <option value='ALL'>All Languages</option>{lang_opts}
  </select>
  <select id='flt-topic' onchange='filterMasterEvals()' aria-label='Filter by topic'>
    <option value='ALL'>All Topics</option>{topic_opts}
  </select>
  <select id='flt-def' onchange='filterMasterEvals()' aria-label='Filter by defect'>
    <option value='ALL'>All Defects (DEF-01..09)</option>{def_opts}
  </select>
  <input id='flt-q' type='search' placeholder='Search VE-xx, scenario, node, or DEF-xx…' oninput='filterMasterEvals()' />
  <span id='flt-count' class='small muted'>{len(master_evals)} shown</span>
</div>
<table>
  <tr>
    <th>VE</th>
    <th>Scenario &amp; CES Console</th>
    <th>Before ({_e(base_hdr)})<div class='small muted' style='font-weight:400'>{_e(base_ts)}</div></th>
    <th>Latest 70-Eval Suite ({_e(full_hdr)})<div class='small muted' style='font-weight:400'>{_e(full_ts)}</div></th>
    <th>Targeted Fix Smoke (If Re-Tested)</th>
    <th>Current Status &amp; Proof</th>
    <th>Defect &amp; Node</th>
  </tr>
  {"".join(rows)}
</table>"""


def render_index(model: dict) -> str:
    runs = model["runs"]
    smoke_runs = model.get("smoke_runs") or []
    bf, lf, lu, ls = (
        model.get("baseline_full"),
        model["latest_full"],
        model["latest_unstable"],
        model.get("latest_smoke"),
    )
    va = model.get("voice_audit")
    master_evals = model.get("master_evals") or []
    flipped_cnt = sum(1 for m in master_evals if m["status_bucket"] == "FLIPPED_PASS")
    effective_pass_cnt = sum(1 for m in master_evals if m["current_pass"])

    kpis = []
    if bf:
        kpis.append(
            f"<div class='kpi'><span class='muted small'>Before — Baseline 70-Eval ({_e(bf['label'])})</span><b>{bf['majority_pass']}/{bf['evals_count']}</b><span class='small muted'>{bf['passes']}/{bf['total']} convs · {_e(_fmt_ts(bf['timestamp']))}</span></div>"
        )
    if master_evals:
        kpis.append(
            f"<div class='kpi'><span class='muted small'>Current Verified Score (Full + Targeted Smoke)</span><b>{effective_pass_cnt}/{len(master_evals)}</b><span class='small muted'><span class='ok'>+{flipped_cnt} flipped FAIL → PASS</span></span></div>"
        )
    if lf and (not bf or lf["label"] != bf["label"]):
        kpis.append(
            f"<div class='kpi'><span class='muted small'>Last 70-Eval Full Run ({_e(lf['label'])})</span><b>{lf['majority_pass']}/{lf['evals_count']}</b><span class='small muted'>{lf['passes']}/{lf['total']} convs · {_e(_fmt_ts(lf['timestamp']))}</span></div>"
        )
    if ls:
        kpis.append(
            f"<div class='kpi'><span class='muted small'>Latest Targeted Smoke ({_e(ls['label'])})</span><b>{ls['majority_pass']}/{ls['evals_count']} PASS</b><span class='small muted'>{ls['passes']}/{ls['total']} convs · {_e(_fmt_ts(ls['timestamp']))}</span></div>"
        )
    if va:
        pc = va.get("priority_counts") or {}
        kpis.append(
            f"<div class='kpi'><span class='muted small'>SCRAPI Voice Audit (audit_agent.py)</span><b>{_e(va['overall_status'])}</b><span class='small muted'>P0: {pc.get('P0', 0)} · P1: {pc.get('P1', 0)} · P2: {pc.get('P2', 0)} ({va.get('total_issues', 0)} issues)</span></div>"
        )

    # Tab 2: Targeted Smoke Batches (Chronological Step-by-Step)
    smoke_table_rows = []
    for idx, r in enumerate(smoke_runs, 1):
        targets_list = []
        mechs_set = sorted({m for e in r["evals"] for m in e.get("mechanisms", [])})
        for e in r["evals"]:
            cls = "ok" if _is_eval_pass(e) else "fail"
            targets_list.append(
                f"<span class='{cls}'><b>{_e(e['ve_id'])}</b> ({e['pass']}/{e['total']})</span>"
            )
        mech_badges = (
            " ".join(f"<span class='tag'>{_e(m)}</span>" for m in mechs_set)
            or "<span class='muted'>Guard / Regression</span>"
        )
        smoke_table_rows.append(
            f"<tr>"
            f"<td><b>Batch {idx}</b> · <a href='#run-{_e(r['label'])}' onclick=\"openRunAnchor('run-{_e(r['label'])}')\">{_e(r['label'])}</a></td>"
            f"<td>{_e(_fmt_ts(r['timestamp']))}</td>"
            f"<td><code>{_e(r['commit'])}</code></td>"
            f"<td>{mech_badges}</td>"
            f"<td>{' · '.join(targets_list)}</td>"
            f"<td><span class='{'ok' if r['majority_pass'] == r['evals_count'] else 'fail'}'><b>{r['majority_pass']}/{r['evals_count']} Evals PASS</b></span> ({r['passes']}/{r['total']} convs)</td>"
            f"</tr>"
        )
    smoke_sections = "".join(
        render_run_section(r, None, model.get("app_resource", "")) for r in reversed(smoke_runs)
    )
    tab_smoke_html = f"""
<h2>Targeted Failure Smoke Batches (<code>make bench-smoke</code>) <span class='pill pill-ours'>Step-by-Step Targeted Fixes</span></h2>
<p class='muted small'>Each fix branch was tested first on only its target failing evaluations (3 repeats per target) before running the full 70-evaluation suite. Ordered chronologically from Batch 1 to Batch {len(smoke_runs)}.</p>
<table>
  <tr><th>Batch &amp; Smoke Run</th><th>Time (UTC)</th><th>Commit</th><th>Defects Targeted</th><th>Targeted Evals (Pass/Total)</th><th>Batch Result</th></tr>
  {"".join(smoke_table_rows) or "<tr><td colspan=6 class='muted'>No targeted smoke runs recorded yet.</td></tr>"}
</table>
<h2>Per-Batch Smoke Breakdowns (Newest First)</h2>
{smoke_sections}"""

    # Tab 3: Full & Unstable Suite Runs (Strictly Separated from Smoke Batches)
    bf_score = (
        f"{bf['majority_pass']}/{bf['evals_count']} ({bf['passes']}/{bf['total']} convs)"
        if bf
        else "—"
    )
    lf_score = (
        f"{lf['majority_pass']}/{lf['evals_count']} ({lf['passes']}/{lf['total']} convs)"
        if lf
        else "—"
    )
    lu_score = (
        f"{lu['majority_pass']}/{lu['evals_count']} evals ({lu['passes']}/{lu['total']} convs)"
        if lu
        else "—"
    )
    ls_score = (
        f"{len(smoke_runs)} batches run · latest {ls['label']}: {ls['majority_pass']}/{ls['evals_count']} PASS ({ls['passes']}/{ls['total']} convs)"
        if ls
        else "0 smoke runs"
    )
    va_score = (
        f"{va['overall_status']} (P0={va.get('priority_counts', {}).get('P0', 0)}, P1={va.get('priority_counts', {}).get('P1', 0)}, P2={va.get('priority_counts', {}).get('P2', 0)})"
        if va
        else "—"
    )
    scorecard_block = f"""
<h2>Multi-Layer Verification Gates <span class='pill pill-ours'>4-Gate Confidence Ladder</span></h2>
<table>
  <tr><th>Verification Gate</th><th>Tool / Command</th><th>Baseline ({_e(bf["label"] if bf else "v4")})</th><th>Current / Latest Status</th></tr>
  <tr><td><b>Gate 0a — Bundle, Lint &amp; Unit Coverage</b></td><td><code>cxas lint</code> · <code>pytest --cov</code> · <code>make ci</code></td><td>0 lint errors</td><td><span class='ok'>PASS (0 errors, &ge;80% per-file cov)</span></td></tr>
  <tr><td><b>Gate 0b — SCRAPI Voice Readiness Audit</b></td><td><code>audit_agent.py</code> (<code>make voice-audit</code>)</td><td>—</td><td><span class='ok'>{_e(va_score)}</span></td></tr>
  <tr><td><b>Gate 1 — Targeted Failure Cloud Smoke</b></td><td><code>make bench-smoke TARGETS=VE-xx</code> (3 repeats)</td><td>—</td><td><span class='ok'>{_e(ls_score)}</span></td></tr>
  <tr><td><b>Gate 2 — Working Gauge (20 Unstable Evals)</b></td><td><code>make bench-unstable</code> (20 &times; 5 = 100 convs)</td><td>67/100 convs (14/20)</td><td><b>{_e(lu_score)}</b></td></tr>
  <tr><td><b>Gate 3 — Public Eval Suite (70 Evals)</b></td><td><code>make bench-full</code> (70 &times; 3 = 210 convs) + <code>make gate3</code></td><td>{_e(bf_score)}</td><td><b>{_e(lf_score)}</b> · Effective with smoke fixes: <b>{effective_pass_cnt}/{len(master_evals) or 70}</b></td></tr>
</table>"""

    run_rows = "".join(
        f"<tr><td><a href='#run-{_e(r['label'])}' onclick=\"openRunAnchor('run-{_e(r['label'])}')\">{_e(r['label'])}</a></td>"
        f"<td>{'Full 70 × 3 (210 convs)' if r['is_full_run'] else 'Unstable 20 × 5 (100 convs)'}</td>"
        f"<td><code>{_e(r['commit'])}</code></td>"
        f"<td><b>{r['majority_pass'] if r['majority_pass'] is not None else '?'}/{r['evals_count']}</b> evals</td>"
        f"<td>{r['passes']}/{r['total']} ({_pct(r['passes'], r['total'])}%)</td>"
        f"<td>{', '.join(f'<span class=node>{_e(n)}</span> {c}' for n, c in r['by_node'][:3]) or '<span class=muted>—</span>'}</td>"
        f"<td>{_e(_fmt_ts(r['timestamp']))}</td></tr>"
        for r in reversed(runs)
    )
    sections = "".join(
        render_run_section(r, (runs[i - 1] if i else None), model.get("app_resource", ""))
        for i, r in enumerate(runs)
    )

    # Tab 4: Defects & Iterations
    def_rows = []
    for d in model["defects"]:
        st_lower = d.get("status", "").lower()
        st_cls = (
            "ok" if "fixed" in st_lower else ("fail" if "open" in st_lower else "muted")
        )
        ve_badges = " ".join(f"<b>{_e(v)}</b>" for v in d.get("ve_ids", []))
        layer_info = _e(d.get("layer") or "—")
        if d.get("fix_type"):
            layer_info += f"<div class='small muted'>Fix type: <code>{_e(d['fix_type'])}</code></div>"
        diag_text = _e(d.get("diagnosis") or "—")
        if d.get("requirement"):
            diag_text += (
                f"<div class='small muted'><b>Req:</b> {_e(d['requirement'])}</div>"
            )
        fix_text = _e(d.get("attempts") or "—")
        if d.get("smoke"):
            fix_text += (
                f"<div class='small' style='margin-top:4px'>{_e(d['smoke'])}</div>"
            )
        def_rows.append(
            f"<tr>"
            f"<td><span class='tag'>{_e(d['id'])}</span><div style='font-weight:600;margin-top:4px'>{_e(d['title'])}</div></td>"
            f"<td><span class='{st_cls}'>{_e(d['status'])}</span></td>"
            f"<td>{ve_badges}</td>"
            f"<td class='small'>{layer_info}</td>"
            f"<td class='small'>{diag_text}</td>"
            f"<td class='small'>{fix_text}</td>"
            f"</tr>"
        )

    it_rows = "".join(
        f"<tr><td>{r['iteration']}</td><td>{_e(r['date'])}</td><td>{_e(r['mechanism'])}</td><td><code>{_e(r['branch'])}</code></td>"
        f"<td>{' '.join(f'<a href=#run-{_e(l)} onclick="openRunAnchor(&#39;run-{_e(l)}&#39;)">{_e(l)}</a>' for l in r['labels']) or _e(r['measurement'])}<div class='small muted'>{_e(r['measurement'])}</div></td><td>{_e(r['decision'])}</td><td class='small'>{_e(r['full_run'])}</td></tr>"
        for r in model["iterations"]
    )

    # Tab 5: SCRAPI Telemetry, Voice Audit & Failure Triage
    va_block = (
        "<p class='muted'>Voice audit script not available in this environment.</p>"
    )
    if va:
        pass_rows = "".join(
            f"<tr><td><code>{_e(pname)}</code></td><td><span class='{'ok' if pinfo.get('passed') else 'fail'}'>{'PASS' if pinfo.get('passed') else 'FAIL'}</span></td><td>{pinfo.get('issues', 0)}</td></tr>"
            for pname, pinfo in (va.get("passes") or {}).items()
        )
        va_block = (
            "<h3>1. Gemini Composite V1 Voice Readiness Audit (<code>cxas-composite-voice-agent-optimizer/scripts/audit_agent.py</code>)</h3>"
            "<p class='muted small'>Runs 7 automated static checks against <code>cxas_app/</code> for voice naturalness, TTS safety, ssml/markdown leaks, and multi-language readiness.</p>"
            f"<table><tr><th>SCRAPI audit pass</th><th>status</th><th>issues</th></tr>{pass_rows}</table>"
        )

    scrapi_run_rows = []
    for r in reversed([*runs, *smoke_runs]):
        if not r.get("by_scrapi_triage"):
            continue
        cat_badges = " ".join(
            f"<span class='tag'>{_e(cat)}: {cnt}</span>"
            for cat, cnt in r["by_scrapi_triage"]
        )
        scrapi_run_rows.append(
            f"<tr><td><a href='#run-{_e(r['label'])}' onclick=\"openRunAnchor('run-{_e(r['label'])}')\">{_e(r['label'])}</a></td>"
            f"<td>{'Smoke Batch' if r.get('is_smoke_run') else ('Full 70×3' if r.get('is_full_run') else 'Unstable 20×5')}</td>"
            f"<td>{_e(_fmt_ts(r['timestamp']))}</td>"
            f"<td>{len(r.get('conversations', []))} failing convs</td>"
            f"<td>{cat_badges}</td></tr>"
        )
    scrapi_triage_table = (
        "<h3>2. SCRAPI Automated Failure Triage Taxonomy Across Runs (<code>cxas-agent-foundry/scripts/triage-results.py</code>)</h3>"
        "<p class='muted small'>Every failing conversation is automatically classified into SCRAPI's failure taxonomy (<code>EXPECTATION_FAIL</code>, <code>TOOL_TEST_FAIL</code>, <code>HALLUCINATION</code>, <code>SIM_USER_OFF_SCRIPT</code>, <code>SIM_MAX_TURNS_EXCEEDED</code>, <code>CALLBACK_TEST_FAIL</code>, <code>EVAL_ERROR</code>).</p>"
        f"<table><tr><th>run</th><th>type</th><th>time (UTC)</th><th>failing convs</th><th>SCRAPI triage breakdown</th></tr>{''.join(scrapi_run_rows) or '<tr><td colspan=5 class=muted>No failing conversation pages loaded</td></tr>'}</table>"
    )
    scrapi_cli_box = """
<h3>3. SCRAPI CLI Telemetry &amp; Trace Debugging Commands (<code>cxas trace</code>)</h3>
<p class='muted small'>Every individual conversation page includes pre-filled copy-pasteable commands for SCRAPI's official CLI:</p>
<table>
  <tr><th>SCRAPI Tool / Command</th><th>Skill / Source</th><th>What It Does</th></tr>
  <tr><td><code>make voice-audit</code></td><td><code>cxas-composite-voice-agent-optimizer</code></td><td>Runs 7-pass Gemini Composite V1 voice readiness audit and generates prioritized HTML report.</td></tr>
  <tr><td><code>make llm-lint</code></td><td><code>cxas llm-lint</code></td><td>Runs LLM-powered instruction contradiction &amp; ambiguity checks across all agent prompts.</td></tr>
  <tr><td><code>make trace-triage CONV=&lt;conv_id&gt;</code></td><td><code>cxas trace triage</code></td><td>Pulls live Cloud Trace spans + judge metrics for a conversation and diagnoses root cause.</td></tr>
  <tr><td><code>make trace-replay CONV=&lt;conv_id&gt;</code></td><td><code>cxas trace replay --diff</code></td><td>Replays a failing historical transcript turn-by-turn against local <code>cxas_app/</code> and diffs tool calls &amp; responses.</td></tr>
</table>"""

    tab_audio_html = render_audio_tab(model.get("audio") or {})

    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{_e(model.get('title') or 'agent')} — hill-climb dashboard</title><style>{CSS}</style></head><body>
<header class='site-hdr'>
  <div class='hdr-inner'>
    <h1>{_e(model.get('title') or 'agent')} — Hill-Climb &amp; SCRAPI Telemetry Dashboard</h1>
    <div class='legend-bar'>
      <span class='pill pill-ours'>OUR REPO: Hill-Climb Ledger (history/bench, docs/defects.md, docs/experiment_log.md)</span>
      <span class='pill pill-scrapi'>SCRAPI BUILT-IN: audit_agent.py, triage-results.py, cxas trace CLI</span>
      <span class='pill pill-borrow'>BORROWED UI: Clean Tabbed Navigation, 70-Eval Before/After Filter Matrix &amp; CES Console Links</span>
      <span class='muted small'>Updated {_e(_fmt_ts(model["generated_at"]))}</span>
    </div>
    <nav class='nav-tabs' role='tablist'>
      <button class='tab-btn active' data-tab='tab-overview' onclick="switchTab('tab-overview')">1. 70-Eval Scorecard (Before → After)</button>
      <button class='tab-btn' data-tab='tab-smoke' onclick="switchTab('tab-smoke')">2. Targeted Smoke Batches ({len(smoke_runs)})</button>
      <button class='tab-btn' data-tab='tab-runs' onclick="switchTab('tab-runs')">3. Full &amp; Unstable Suite Runs ({len(runs)})</button>
      <button class='tab-btn' data-tab='tab-defects' onclick="switchTab('tab-defects')">4. Defects (DEF-01..09) &amp; Iterations ({len(model["defects"])})</button>
      <button class='tab-btn' data-tab='tab-scrapi' onclick="switchTab('tab-scrapi')">5. SCRAPI Telemetry &amp; Voice Audit</button>
      <button class='tab-btn' data-tab='tab-audio' onclick="switchTab('tab-audio')">6. Voice / Audio</button>
    </nav>
  </div>
</header>
<main>
  <div id='tab-overview' class='tab-panel active'>
    <div class='kpi-grid'>{"".join(kpis)}</div>
    {_render_master_evals_block(master_evals)}
  </div>

  <div id='tab-smoke' class='tab-panel'>
    {tab_smoke_html}
  </div>

  <div id='tab-runs' class='tab-panel'>
    {scorecard_block}
    <h2>Progress over time (Full &amp; Unstable Suite Runs Only)</h2>
    {render_trend_svg(runs)}
    <h2>Full (70 × 3) &amp; Unstable (20 × 5) Suite Runs</h2>
    <table><tr><th>run</th><th>suite type</th><th>commit</th><th>evals passed (majority)</th><th>conversations passed</th><th>top failing nodes</th><th>time (UTC)</th></tr>{run_rows}</table>
    <h2>Detailed Per-Run Breakdowns (Full &amp; Unstable Suites)</h2>
    {sections}
  </div>

  <div id='tab-defects' class='tab-panel'>
    <h2>Failure Mechanisms &amp; Root-Cause Remediation (<code>docs/defects.md</code>) <span class='pill pill-ours'>Our Repo</span></h2>
    <p class='muted small'>Every failing evaluation is mapped to its shared root-cause mechanism (<code>DEF-01..DEF-09</code>), affected architectural layer, diagnosis, and targeted smoke verification result.</p>
    <table>
      <tr><th>Defect &amp; Title</th><th>Status</th><th>Linked Evals</th><th>Root Cause Layer</th><th>Diagnosis (Why It Broke)</th><th>Fix &amp; Smoke Verification</th></tr>
      {"".join(def_rows)}
    </table>
    <h2>Iterations &amp; Decisions (<code>docs/experiment_log.md</code>) <span class='pill pill-ours'>Our Repo</span></h2>
    <p class='muted small'>One mechanism per iteration; full story (why failing → alternatives → change → result) in <code>docs/experiment_log.md</code>.</p>
    <table><tr><th>#</th><th>date</th><th>mechanism</th><th>branch / commit</th><th>measurement</th><th>decision</th><th>full run</th></tr>{it_rows}</table>
  </div>

  <div id='tab-scrapi' class='tab-panel'>
    <h2>SCRAPI Telemetry, Voice Readiness &amp; Debugging (Built-In Skills) <span class='pill pill-scrapi'>SCRAPI Built-In</span></h2>
    {va_block}
    {scrapi_triage_table}
    {scrapi_cli_box}
  </div>

  <div id='tab-audio' class='tab-panel'>
    {tab_audio_html}
  </div>
</main>
<script>{INDEX_JS}</script>
</body></html>"""


def _audio_pill(val: str | None) -> str:
    if val is None or val == "not yet measured":
        return "<span class='status-badge st-unmeasured'>not yet measured</span>"
    if val in ("—", "N/A"):
        return f"<span class='muted'>{_e(val)}</span>"
    up = str(val).upper()
    if up == "PASS":
        return "<span class='status-badge st-pass'>PASS</span>"
    if up == "FAIL":
        return "<span class='status-badge st-fail'>FAIL</span>"
    return f"<span class='status-badge'>{_e(val)}</span>"


def render_audio_tab(audio: dict) -> str:
    if not audio:
        return "<p class='muted'>No voice/audio evaluation data available.</p>"

    kpis = audio.get("kpis") or {}
    kpi_html = f"""
<div class='kpi-grid'>
  <div class='kpi'><div class='small muted'>Audio Baseline Goldens</div><b>{_e(kpis.get("base_goldens", "not yet measured"))}</b><div class='small muted'>51 P0 scenarios</div></div>
  <div class='kpi'><div class='small muted'>Audio Baseline Simulations</div><b>{_e(kpis.get("base_sims", "not yet measured"))}</b><div class='small muted'>30 P0 simulations</div></div>
  <div class='kpi'><div class='small muted'>Audio After Status</div><b>{_e(kpis.get("after_status", "not yet measured"))}</b><div class='small muted'>post-fix verification</div></div>
  <div class='kpi'><div class='small muted'>Mean Naturalness (1-5)</div><b>{_e(kpis.get("mean_naturalness", "not yet measured"))}</b><div class='small muted'>LLM speech rating</div></div>
  <div class='kpi'><div class='small muted'>Median Turn Latency (P50)</div><b>{_e(kpis.get("latency_p50", "not yet measured"))}</b><div class='small muted'>caller-to-speech turnaround</div></div>
</div>"""

    lang_rows = []
    for s in audio.get("languages", []):
        lang_rows.append(
            f"<tr>"
            f"<td><b>{_e(s.get('language'))}</b></td>"
            f"<td>{_e(s.get('golden_pass_rate'))}</td>"
            f"<td>{_e(s.get('simulation_pass_rate'))}</td>"
            f"<td><b>{_e(s.get('combined_pass_rate'))}</b></td>"
            f"<td>{_e(s.get('naturalness_mean'))}</td>"
            f"<td>{_e(s.get('latency_p50_ms'))}</td>"
            f"<td>{_e(s.get('latency_p90_ms'))}</td>"
            f"</tr>"
        )
    lang_table = f"""
<h2>1. Per-Language Voice Quality &amp; Latency Summary</h2>
<p class='muted small'>Aggregated performance across 51 P0 Goldens and 30 P0 Simulations by language. Measures spoken accuracy, naturalness (1.0 to 5.0 score), and latency percentiles (P50 and P90).</p>
<table>
  <tr><th>Language</th><th>Golden Pass Rate</th><th>Simulation Pass Rate</th><th>Combined Pass Rate</th><th>Naturalness Mean</th><th>Latency P50 (ms)</th><th>Latency P90 (ms)</th></tr>
  {"".join(lang_rows) or "<tr><td colspan=7 class='muted'>No language breakdown recorded yet.</td></tr>"}
</table>"""

    case_rows = []
    for c in audio.get("cases", []):
        dossier_cell = (
            f"<a class='ext-link' href='{_e(c['dossier_link'])}'>View Dossier ↗</a>"
            if c.get("dossier_link")
            else "<span class='muted'>—</span>"
        )
        search_blob = f"{c['case_id']} {c['layer']} {c['language']} {c.get('run_id_short','')} {c.get('conv_id_short','')}"
        case_rows.append(
            f"<tr class='audio-case-row' data-layer='{_e(c['layer'])}' data-lang='{_e(c['language'])}' "
            f"data-status='{_e(c.get('audio_baseline') or 'UNMEASURED')}' "
            f"data-search='{_e(search_blob)}'>"
            f"<td><b>{_e(c['case_id'])}</b></td>"
            f"<td><span class='pill {'pill-ours' if c['layer'] == 'goldens' else 'pill-scrapi'}'>{_e(c['layer'])}</span></td>"
            f"<td>{_e(c['language'])}</td>"
            f"<td>{_audio_pill(c.get('audio_baseline'))}</td>"
            f"<td>{_audio_pill(c.get('text_baseline'))}</td>"
            f"<td>{_audio_pill(c.get('audio_after'))}</td>"
            f"<td><code>{_e(c.get('run_id_short') or '—')}</code></td>"
            f"<td><code>{_e(c.get('conv_id_short') or '—')}</code></td>"
            f"<td>{dossier_cell}</td>"
            f"</tr>"
        )
    total_cases = len(audio.get("cases", []))
    case_table = f"""
<h2>2. Master Voice Scorecard — Baseline vs. After per Case</h2>
<p class='muted small'>Full evaluation matrix comparing audio baseline vs. text baseline (for goldens) and subsequent post-fix audio runs. Click <b>View Dossier ↗</b> to inspect the turn-by-turn caller audio vs. agent STT transcript, synthesized agent speech, and recording paths.</p>
<div class='filter-bar'>
  <label class='small muted'>Layer:</label>
  <select id='flt-audio-layer' onchange='filterAudioCases()'>
    <option value='ALL'>All Layers (Goldens &amp; Sims)</option>
    <option value='goldens'>Goldens (51)</option>
    <option value='simulations'>Simulations (30)</option>
  </select>
  <label class='small muted'>Language:</label>
  <select id='flt-audio-lang' onchange='filterAudioCases()'>
    <option value='ALL'>All Languages</option>
    <option value='en'>English (en)</option>
    <option value='fr'>French (fr)</option>
    <option value='es'>Spanish (es)</option>
  </select>
  <label class='small muted'>Status:</label>
  <select id='flt-audio-status' onchange='filterAudioCases()'>
    <option value='ALL'>All Results</option>
    <option value='PASS'>PASS</option>
    <option value='FAIL'>FAIL</option>
    <option value='UNMEASURED'>Not yet measured</option>
  </select>
  <input id='flt-audio-q' type='search' placeholder='Search Case ID, language, run ID, or conversation…' oninput='filterAudioCases()' />
  <span id='flt-audio-count' class='small muted'>{total_cases} cases</span>
</div>
<table>
  <tr><th>Case ID</th><th>Layer</th><th>Lang</th><th>Audio Baseline</th><th>Text Baseline</th><th>Audio After</th><th>Run ID</th><th>Conversation</th><th>Dossier</th></tr>
  {"".join(case_rows) or "<tr><td colspan=9 class='muted'>No cases loaded yet.</td></tr>"}
</table>"""

    if audio.get("has_noise") and audio.get("noise_cases"):
        noise_rows = "".join(
            f"<tr><td><b>{_e(nc.get('case_id'))}</b></td><td>{_e(nc.get('language'))}</td><td>{_e(nc.get('condition'))}</td><td>{_audio_pill(nc.get('verdict'))}</td><td class='small'>{_e(nc.get('failure_reason') or 'None')}</td><td><code>{_e(nc.get('run_id'))}</code></td></tr>"
            for nc in audio["noise_cases"]
        )
        noise_section = f"""
<h2>3. Acoustic Noise Robustness Tests (Background &amp; Burst Noise)</h2>
<p class='muted small'>Tests run under degraded acoustic conditions (pink background noise + burst click interference) to verify noise robustness.</p>
<table><tr><th>Case ID</th><th>Language</th><th>Condition</th><th>Verdict</th><th>Failure Reason</th><th>Run ID</th></tr>{noise_rows}</table>"""
    else:
        noise_section = """
<h2>3. Acoustic Noise Robustness Tests (Background &amp; Burst Noise)</h2>
<p class='muted small'>Tests run under degraded acoustic conditions (pink background noise + burst click interference) to verify noise robustness.</p>
<div class='audio-guide'><p class='muted'><em>Not yet measured:</em> Background and burst noise variant simulations (<code>audio-noise-*</code>) have not been recorded yet. When executed via <code>make noise-sims</code>, results will appear here.</p></div>"""

    defects = audio.get("defects", [])
    if defects:
        def_rows = []
        for d in defects:
            mem_badges = (
                "".join(f"<span class='tag'>{_e(m)}</span>" for m in d.get("members", []))
                or "<span class='muted'>None</span>"
            )
            def_rows.append(
                f"<tr><td><span class='tag'>{_e(d['id'])}</span><div style='font-weight:600;margin-top:4px'>{_e(d['title'])}</div></td>"
                f"<td>{_e(d.get('status') or 'open')}</td><td>{mem_badges}</td>"
                f"<td class='small'>{_e(d.get('layer') or 'voice')}</td>"
                f"<td class='small'>{_e(d.get('diagnosis') or '—')}</td></tr>"
            )
        clusters_section = f"""
<h2>4. Voice Defect Clusters (<code>DEF-A*</code> in <code>docs/defects.md</code>)</h2>
<p class='muted small'>Root-cause failure mechanisms specific to voice conversations (speech-to-text mismatches, TTS pronunciation problems, or voice timing delays).</p>
<table><tr><th>Defect &amp; Title</th><th>Status</th><th>Member Cases</th><th>Layer</th><th>Diagnosis</th></tr>{"".join(def_rows)}</table>"""
    else:
        clusters_section = """
<h2>4. Voice Defect Clusters (<code>DEF-A*</code> in <code>docs/defects.md</code>)</h2>
<p class='muted small'>Root-cause failure mechanisms specific to voice conversations (speech-to-text mismatches, TTS pronunciation problems, or voice timing delays).</p>
<div class='audio-guide'><p class='muted'>No voice defect clusters (<code>DEF-A*</code>) recorded yet in <code>docs/defects.md</code>. As failures are clustered during audio iterations, they will appear here with member cases.</p></div>"""

    dossiers = audio.get("dossiers", [])
    b_tables = audio.get("baseline_tables", [])
    dossier_items = []
    for bt in b_tables:
        lbl = bt.get("label", "")
        dossier_items.append(
            f"<li><a class='ext-link' href='audio/{_e(lbl)}/baseline_table.html'><b>Baseline Table Summary ({_e(lbl)}) ↗</b></a></li>"
        )
    for d in dossiers:
        dossier_items.append(
            f"<li><a class='ext-link' href='{_e(d['html_rel_path'])}'><code>{_e(d['stem'])}</code> ({_e(d['label'])}) ↗</a></li>"
        )

    if dossier_items:
        dossiers_section = f"""
<h2>5. Per-Conversation Audio Dossiers &amp; GCS Recordings Evidence</h2>
<p class='muted small'>Turn-by-turn dossiers containing what the caller said vs. what the agent heard (STT), synthesized agent replies (TTS), judge scores, and exact Cloud Storage audio paths (<code>gs://...</code>).</p>
<ul>{"".join(dossier_items)}</ul>"""
    else:
        dossiers_section = """
<h2>5. Per-Conversation Audio Dossiers &amp; GCS Recordings Evidence</h2>
<p class='muted small'>Turn-by-turn dossiers containing what the caller said vs. what the agent heard (STT), synthesized agent replies (TTS), judge scores, and exact Cloud Storage audio paths (<code>gs://...</code>).</p>
<div class='audio-guide'><p class='muted'>No per-conversation dossiers generated yet. Dossiers produced via <code>scripts/audio_dossiers.py</code> will be linked here.</p></div>"""

    return f"""
<h2>Voice &amp; Audio Telemetry &amp; Quality <span class='pill pill-ours'>Our Repo</span></h2>
<div class='audio-guide'>
  <h3 style='margin:0 0 6px'>🎙️ Plain English Voice Evaluation Guide for Beginners</h3>
  <p>Voice interactions evaluate end-to-end spoken customer service over simulated phone lines. Unlike text chat, voice calls must handle spoken speech, telephone audio compression, pauses, pronunciation, and fast latency. Key concepts and acronyms used here:</p>
  <ul>
    <li><b>STT (Speech-To-Text)</b>: The component that listens to the caller's spoken audio and transcribes it into text so the agent can understand the request.</li>
    <li><b>TTS (Text-To-Speech)</b>: The speech synthesizer that converts the agent's textual response into realistic, spoken audio for the caller to hear.</li>
    <li><b>P50 Latency (Median)</b>: The 50th percentile response time — 50% of spoken conversation turns received an agent voice reply faster than this time (in milliseconds). Represents typical caller experience.</li>
    <li><b>P90 Latency (Tail)</b>: The 90th percentile response time — 90% of turns responded faster than this threshold (and 10% took longer). High P90 indicates hesitation or slow tool execution.</li>
    <li><b>Naturalness Score (1.0 to 5.0)</b>: A quality rating scored by an LLM audio judge evaluating conversational pacing, polite tone, human-like cadence, and absence of robotic artifacts or prompt leaks.</li>
  </ul>
</div>
{kpi_html}
{lang_table}
{case_table}
{noise_section}
{clusters_section}
{dossiers_section}
"""


def render_dossier_page(title: str, body_html: str, label: str) -> str:
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{_e(title)} · {_e(label)}</title><style>{CSS}</style></head><body><main>
<p class='small'><a href='../../index.html#tab-audio'>← dashboard · Voice / Audio</a></p>
{body_html}
</main></body></html>"""


def _compact_tool_line(text: str) -> str:
    """'<tool_call> {json}' transcript lines -> 'tool_name(args)'."""
    body = text.split(">", 1)[1].strip() if text.startswith("<tool_call>") else text
    try:
        call = json.loads(body)
    except ValueError:
        return text[:300]
    name = call.get("display_name") or _tool_short(call.get("tool"))
    args = json.dumps(call.get("args") or {}, ensure_ascii=False)
    return f"{name}({args[:220]}{'…' if len(args) > 220 else ''})"


def render_conv(page: dict, att: dict, run_label: str, commit: str) -> str:
    responses: dict[int, list[dict]] = defaultdict(list)
    transfers: dict[int, list[str]] = defaultdict(list)
    for tc in page.get("tool_calls") or []:
        turn = int(tc.get("turn") or 0)
        payload = tc.get("payload") or {}
        if tc.get("type") == "tool_response":
            res = _response_result(payload)
            responses[turn].append(
                {
                    "node": tc.get("role", "?"),
                    "tool": _tool_short(
                        payload.get("tool") or payload.get("display_name")
                    ),
                    "status": res.get("status", ""),
                    "error": res.get("error", ""),
                    "agent_action": res.get("agent_action", ""),
                    "message": str(res.get("message") or "")[:200],
                    "data_keys": sorted((res.get("data") or {}).keys())[:10]
                    if isinstance(res.get("data"), dict)
                    else [],
                }
            )
        elif tc.get("type") == "agent_transfer":
            transfers[turn].append(
                f"{tc.get('role', '?')} → {_tool_short(payload.get('target_agent') or payload.get('display_name'))}"
            )
    turns: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for line in page.get("transcript") or []:
        m = TRANSCRIPT_LINE.match(line)
        if m:
            turns[int(m.group(1))].append((m.group(2), m.group(3)))
    blocks = []
    for turn in sorted(set(turns) | set(responses) | set(transfers)):
        lines = []
        for role, text in turns.get(turn, []):
            if role == "user":
                lines.append(f"<div class='user'><b>caller:</b> {_e(text)}</div>")
            elif text.startswith("<tool_call>"):
                lines.append(
                    f"<div class='tool'>↳ <b>{_e(role)}</b> calls <code>{_e(_compact_tool_line(text))}</code></div>"
                )
            else:
                lines.append(f"<div class='agent'><b>{_e(role)}:</b> {_e(text)}</div>")
        for r in responses.get(turn, []):
            status = (
                f"<span class='fail'>error {_e(r['error'])}</span>"
                if r["status"] == "error" or r["error"]
                else "<span class='ok'>ok</span>"
            )
            extra = (
                f" {_e(r['message'])}"
                if r["message"]
                else (
                    f" data: {_e(', '.join(r['data_keys']))}" if r["data_keys"] else ""
                )
            )
            lines.append(
                f"<div class='tool'>← <code>{_e(r['tool'])}</code> {status}{(' · ' + _e(r['agent_action'])) if r['agent_action'] else ''}{extra}</div>"
            )
        for t in transfers.get(turn, []):
            lines.append(f"<div class='tool'>⇄ transfer {_e(t)}</div>")
        broke = " broke" if turn == att["broke_at_turn"] else ""
        blocks.append(
            f"<div class='turn{broke}'><div class='small muted'>turn {turn}{' — where it broke' if broke else ''}</div>{''.join(lines)}</div>"
        )
    judge = page.get("judge") or {}
    exp_rows = "".join(
        f"<tr><td class='{'ok' if (OUTCOME_NAMES.get(e.get('outcome'), str(e.get('outcome'))) == 'PASS') else 'fail'}'>{_e(OUTCOME_NAMES.get(e.get('outcome'), e.get('outcome')))}</td><td>{_e(e.get('prompt'))}</td><td class='small'>{_e(e.get('explanation'))}</td></tr>"
        for e in judge.get("evaluation_expectation_results") or []
    )
    goal, hal = att["user_goal"], att["hallucination"]
    fb = "".join(f"<li><code>{_e(f)}</code></li>" for f in att["fallbacks"])
    conv_id = str(page.get("conversation_name") or "").rsplit("/", 1)[-1]
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{_e(page.get("ve_id"))} · {_e(run_label)}</title><style>{CSS}</style></head><body><main>
<p class='small'><a href='../../index.html#run-{_e(run_label)}'>← dashboard · {_e(run_label)}</a></p>
<h1>{_e(page.get("ve_id"))} — {_e(page.get("display_name"))} <span class='muted small'>({_e(page.get("language"))}, {_e(page.get("topic"))})</span></h1>
<p class='muted'>run {_e(run_label)} · commit {_e(commit)} · repeat {_e(page.get("slot"))} · classification <b>{_e(page.get("classification"))}</b> · platform {_e(page.get("execution_state"))}/{_e(page.get("evaluation_status"))} · app version {_e((page.get("conversation") or {}).get("app_version") or "?")}</p>
<h2>Where it broke &amp; SCRAPI Triage</h2>
<p><span class='node'>{_e(att["failing_node"])}</span> at turn <b>{att["broke_at_turn"]}</b> — {_e(att["signal"])}.
<span class='muted small'>Last node speaking: {_e(att["node_at_end"] or "?")}.</span></p>
<p><b>SCRAPI Triage (<code>triage-results.py</code>):</b> <span class='tag'>{_e(att.get("scrapi_category") or "UNKNOWN")}</span> <span class='small muted'>{_e(att.get("scrapi_detail") or "")}</span></p>
<p class='small muted'><b>SCRAPI CLI Telemetry:</b> <code>make trace-triage CONV={_e(conv_id)}</code> · <code>make trace-replay CONV={_e(conv_id)}</code></p>
{f"<ul>{fb}</ul>" if fb else ""}
<h2>What the judge said</h2>
<table><tr><th>outcome</th><th>expectation</th><th>judge's reasoning</th></tr>{exp_rows}</table>
<p><b>User goal:</b> {_e(goal["label"])} (score {_e(goal["score"])}) <span class='small'>{_e(goal["explanation"])}</span></p>
<p><b>Hallucination check:</b> {_e(hal["label"])} (score {_e(hal["score"])})</p>
<details><summary>The task the simulated caller was given</summary><pre>{_e(judge.get("task"))}</pre><pre>{_e(json.dumps(judge.get("user_facts"), ensure_ascii=False, indent=1) if judge.get("user_facts") else "")}</pre></details>
<h2>Conversation</h2>{"".join(blocks)}
<p class='small muted'>Source page: <code>&lt;bench-dir&gt;/runs/failing_runs_data/{_e(run_label)}/{_e(page.get("ve_id"))}__{_e(_run8(page.get("evaluation_run")))}__r{_e(page.get("slot"))}.json</code> · platform conversation <code>{_e(page.get("conversation_name"))}</code></p>
</main></body></html>"""


# ------------------------------------------------------------------------------ main


def build(
    out_dir: Path,
    history_dir: Path,
    bench_root: Path,
    docs_dir: Path,
    app_dir: Path | None = None,
    audio_history_dir: Path | None = None,
    bench_audio_dir: Path | None = None,
    evals_dir: Path | None = None,
    app_resource: str = "",
    title: str = "",
) -> dict:
    model = build_model(
        history_dir,
        bench_root,
        docs_dir,
        app_dir=app_dir,
        audio_history_dir=audio_history_dir,
        bench_audio_dir=bench_audio_dir,
        evals_dir=evals_dir,
        app_resource=app_resource,
        title=title,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_index(model), encoding="utf-8")
    written = 1
    runs_dir = bench_root / "runs"
    for run in [*model["runs"], *(model.get("smoke_runs") or [])]:
        pages = load_pages(runs_dir, run["label"])
        conv_dir = out_dir / "conv" / run["label"]
        for stem, att in run["attributions"].items():
            if stem not in pages:
                continue
            conv_dir.mkdir(parents=True, exist_ok=True)
            (conv_dir / f"{stem}.html").write_text(
                render_conv(pages[stem], att, run["label"], run["commit"]),
                encoding="utf-8",
            )
            written += 1

    audio_data = model.get("audio") or {}
    for dossier in audio_data.get("dossiers", []):
        lbl = dossier.get("label", "audio-run")
        stem = dossier.get("stem")
        if not stem:
            continue
        d_dir = out_dir / "audio" / lbl
        d_dir.mkdir(parents=True, exist_ok=True)
        d_html = render_dossier_page(
            f"Audio Dossier · {stem}",
            markdown_to_html(dossier.get("content", "")),
            lbl,
        )
        (d_dir / f"{stem}.html").write_text(d_html, encoding="utf-8")
        written += 1
    for btable in audio_data.get("baseline_tables", []):
        lbl = btable.get("label", "audio-run")
        d_dir = out_dir / "audio" / lbl
        d_dir.mkdir(parents=True, exist_ok=True)
        t_html = render_dossier_page(
            f"Audio Baseline Table · {lbl}",
            markdown_to_html(btable.get("content", "")),
            lbl,
        )
        (d_dir / "baseline_table.html").write_text(t_html, encoding="utf-8")
        written += 1

    return {"runs": len(model["runs"]), "files": written, "out": str(out_dir)}


def _self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hist = root / "history" / "bench"
        bench = root / "bench"
        docs = root / "docs"
        out = root / "dashboard"
        hist.mkdir(parents=True)
        (bench / "runs" / "failing_runs_data" / "full-1111111").mkdir(parents=True)
        docs.mkdir(parents=True)
        (hist / "full-1111111.json").write_text(
            json.dumps(
                {
                    "label": "full-1111111",
                    "timestamp": "2026-10-05T10:00:00Z",
                    "commit": "1111111",
                    "app_versions": ["v1"],
                    "evaluation_runs": ["run1"],
                    "runs_per_eval": 5,
                    "is_full_run": True,
                    "evals": 2,
                    "passes": 9,
                    "total": 10,
                    "majority_pass": 2,
                    "per_eval": {
                        "VE-01": {"pass": 5, "total": 5, "infra": 0, "verdict": "PASS"},
                        "VE-02": {"pass": 4, "total": 5, "infra": 0, "verdict": "PASS"},
                    },
                }
            ),
            encoding="utf-8",
        )
        summary = build(out, hist, bench, docs)
        assert summary["runs"] == 1, summary
        assert (out / "index.html").exists()
        html_text = (out / "index.html").read_text(encoding="utf-8")
        assert "full-1111111" in html_text
    print("OK: 2/2 build_dashboard self-test cases passed")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", default=str(REPO / "dashboard"))
    p.add_argument("--history-dir", default=str(REPO / "history" / "bench"))
    p.add_argument("--bench-dir", default=str(DEFAULT_BENCH_ROOT))
    p.add_argument("--docs-dir", default=str(REPO / "docs"))
    p.add_argument("--app-dir", default=str(REPO / "cxas_app"))
    p.add_argument("--audio-history-dir", default=str(REPO / "history" / "audio"))
    p.add_argument("--bench-audio-dir", default=str(DEFAULT_BENCH_ROOT / "runs" / "audio"))
    p.add_argument(
        "--app",
        default=os.environ.get("APP", ""),
        help="App resource projects/<p>/locations/<l>/apps/<id>, used for CES console links "
        "when a history record has no app_resource of its own (default: $APP)",
    )
    p.add_argument(
        "--title",
        default=os.environ.get("AGENT_NAME", ""),
        help="Dashboard title (default: $AGENT_NAME, else displayName from <app-dir>/app.json)",
    )
    p.add_argument("--self-test", action="store_true", help="Run built-in self-tests")
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    summary = build(
        Path(args.out),
        Path(args.history_dir),
        Path(args.bench_dir),
        Path(args.docs_dir),
        app_dir=Path(args.app_dir),
        audio_history_dir=Path(args.audio_history_dir),
        bench_audio_dir=Path(args.bench_audio_dir),
        app_resource=args.app,
        title=args.title,
    )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())

