#!/usr/bin/env python3
"""Evaluation runner: offline validation (Gate 0) and server-side evaluation runs (Gates 1-4).

Two modes:

  --mode local (default)
      Offline, no cloud. EXECUTES evals/tool_tests/*.yaml with suite/tool_tests.py and
      VALIDATES goldens / simulations / probes (YAML -> normalised spec -> CES Evaluation
      proto). Validation is not execution: those specs are reported as VALID / LOADED /
      INVALID, never PASS, because only the server can run a conversation.

  --mode staging  (or any of --smoke / --unstable / --full / --resume-run)
      Runs evaluations that already exist in the CXAS app (pushed with `cxas push-eval`)
      through scripts/run_bench.py (same report format as the proven public-bench runner)
      and, when the run completes, appends one record per test x repeat to
      history/runs.jsonl (see assets/run_record.schema.json) so `suite/gate.py` can
      decide PASS / FAIL / INCONCLUSIVE.

Usage:
  python3 scripts/run_evals.py --mode local
  python3 scripts/run_evals.py --app projects/P/locations/L/apps/A --smoke --targets golden_x,sim_y
  python3 scripts/run_evals.py --app ... --unstable            # evals/unstable_set.txt, 5 repeats
  python3 scripts/run_evals.py --app ... --full                # every eval in the app, 3 repeats
  python3 scripts/run_evals.py --app ... --resume-run <evaluationRun name>
  python3 scripts/run_evals.py --app ... --smoke --dry-run     # print the plan, no cloud calls
  python3 scripts/run_evals.py --self-test

Exit codes (cloud): 0 run completed (read the verdicts in the report), 1 error,
2 the app changed mid-run (numbers not trustworthy), 3 credentials need `gcloud auth login`.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from suite import cloud_log, regression
from suite import tool_tests as tool_tests_mod

INFRA_ERROR_TOKENS = (
    "429",
    "resource_exhausted",
    "quota_exhausted",
    "rate_limit",
    "rate limit",
    "too many requests",
    "deadline_exceeded",
    "unavailable",
    "internal error",
    "503",
    "504",
    "connection reset",
    "timed out",
)

REAUTH_TOKENS = (
    "invalid_rapt",
    "reauthentication failed",
    "unauthenticated",
    "access_token_type_unsupported",
)

# Gate layer names (suite/gate.py, run_record.schema.json) per local layer x modality.
GATE_LAYER = {
    ("golden", "text"): "golden",
    ("golden", "audio"): "audio_golden",
    ("simulation", "text"): "sim",
    ("simulation", "audio"): "audio_sim",
    ("probe", "text"): "probe",
    ("probe", "audio"): "probe",
}

DEFAULT_REPEATS = {"smoke": 3, "unstable": 5, "full": 3}


class ReauthRequired(RuntimeError):
    """Raised when GCP credentials require interactive re-authentication."""


class ConcurrentPushError(RuntimeError):
    """Raised when `get_app().update_time` changes while a benchmark is running."""


def refresh_credentials_if_needed(
    credentials: Any, min_ttl_sec: float = 600.0
) -> bool:
    """Refresh credentials if invalid or expiring within `min_ttl_sec` (default 10 min).

    Prevents 1-hour OAuth token expiry (`ACCESS_TOKEN_TYPE_UNSUPPORTED` / 401)
    between evaluation batches. Prints `creds refreshed (expiry <t>)` when refreshed.
    """
    if credentials is None:
        return False
    needs_refresh = False
    valid = getattr(credentials, "valid", None)
    if valid is False:
        needs_refresh = True
    else:
        expiry = getattr(credentials, "expiry", None)
        if expiry is not None:
            if isinstance(expiry, (int, float)):
                time_left = expiry - time.time()
            elif isinstance(expiry, datetime):
                now = (
                    datetime.now(UTC).replace(tzinfo=None)
                    if expiry.tzinfo is None
                    else datetime.now(UTC)
                )
                time_left = (expiry - now).total_seconds()
            else:
                time_left = 0.0
            if time_left < min_ttl_sec:
                needs_refresh = True

    if not needs_refresh:
        return False

    req = None
    try:
        import google.auth.transport.requests

        req = google.auth.transport.requests.Request()
    except Exception:
        req = None

    if hasattr(credentials, "refresh"):
        try:
            credentials.refresh(req)
        except TypeError:
            credentials.refresh()
        tok = getattr(credentials, "token", None)
        if tok:
            os.environ["CXAS_OAUTH_TOKEN"] = str(tok)
        exp = getattr(credentials, "expiry", None)
        print(f"creds refreshed (expiry {exp})", flush=True)
        return True
    return False


def format_update_time(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "rfc3339"):
        return str(val.rfc3339())
    if hasattr(val, "isoformat"):
        return str(val.isoformat())
    if hasattr(val, "ToJsonString"):
        return str(val.ToJsonString())
    return str(val)


def check_app_version_guard(
    app_client: Any,
    app_name: str,
    baseline_update_time: str | None = None,
    log_path: Path | None = None,
) -> str:
    """Read `get_app(name=app_name).update_time` and fail if it changed since baseline."""
    with cloud_log.logged_call(
        "READ",
        "AgentService.get_app",
        app_name,
        "Concurrent-push version guard (check app.update_time)",
        log_path=log_path or cloud_log.DEFAULT_LOG,
    ) as call:
        app_obj = app_client.get_app(name=app_name)
        current = format_update_time(getattr(app_obj, "update_time", None))
        call.outcome = f"OK (update_time={current or 'unknown'})"

    if baseline_update_time and current and current != baseline_update_time:
        raise ConcurrentPushError(
            f"App {app_name} was modified mid-run: update_time changed from "
            f"{baseline_update_time!r} to {current!r}. Discard this contaminated run."
        )
    return current


def _to_protobuf_struct(data: dict[str, Any] | None) -> Any:
    from google.protobuf import struct_pb2

    st = struct_pb2.Struct()
    if data:
        st.update(data)
    return st


def yaml_case_to_spec(case: dict[str, Any], layer: str = "golden") -> dict[str, Any]:
    """Normalize a YAML golden/simulation/probe case into the canonical spec dict."""
    cid = str(case.get("id") or "unnamed")
    if layer == "simulation" or case.get("task") or case.get("user_goal"):
        raw_facts = case.get("user_facts") or []
        if isinstance(raw_facts, dict):
            user_facts = [{"name": str(k), "value": str(v)} for k, v in raw_facts.items()]
        else:
            user_facts = [
                {"name": str(f.get("name", "")), "value": str(f.get("value", ""))}
                for f in raw_facts
                if isinstance(f, dict)
            ]
        return {
            "case_id": cid,
            "layer": "simulation",
            "language": str(case.get("language") or "en"),
            "priority": str(case.get("priority") or "P0"),
            "cuj": str(case.get("cuj") or ""),
            "task": str(case.get("task") or case.get("user_goal") or ""),
            "max_turns": int(case.get("max_turns") or 12),
            "user_facts": user_facts,
            "rubrics": [str(r) for r in (case.get("rubrics") or [])],
            "variable_overrides": dict(
                case.get("variable_overrides") or case.get("session_variables") or {}
            ),
            "evaluation_expectations": [
                str(e) for e in (case.get("evaluation_expectations") or [])
            ],
        }

    turns_out: list[dict[str, Any]] = []
    session_vars = case.get("session_variables") or case.get("variable_overrides") or {}
    for idx, turn in enumerate(case.get("turns") or []):
        steps: list[dict[str, Any]] = []
        if idx == 0 and isinstance(session_vars, dict) and session_vars:
            steps.append({"kind": "user_variables", "variables": dict(session_vars)})
        user_text = str(turn.get("user") or turn.get("text") or "").strip()
        if user_text:
            steps.append({"kind": "user_text", "text": user_text})
        for transfer_target in (
            ([turn["expected_transfer"]] if turn.get("expected_transfer") else [])
            + list(turn.get("expected_transfers") or [])
        ):
            if transfer_target:
                steps.append(
                    {"kind": "agent_transfer", "target_agent": str(transfer_target)}
                )
        for tc in turn.get("expected_tool_calls") or turn.get("tool_calls") or []:
            if isinstance(tc, dict):
                tname = str(tc.get("name") or tc.get("tool") or "")
                tpath = str(tc.get("tool") or tname)
            else:
                tname = str(tc)
                tpath = tname
            if tname:
                steps.append({"kind": "tool_call", "name": tname, "tool": tpath})
        agent_resp = str(turn.get("agent") or turn.get("expected_response") or "").strip()
        if agent_resp:
            steps.append({"kind": "agent_response", "text": agent_resp, "role": "agent"})
        turns_out.append({"steps": steps})

    return {
        "case_id": cid,
        "layer": layer,
        "language": str(case.get("language") or "en"),
        "priority": str(case.get("priority") or "P0"),
        "cuj": str(case.get("cuj") or ""),
        "turns": turns_out,
    }


def spec_to_ces_evaluation(spec: dict[str, Any], display_name: str, app_name: str = "") -> Any:
    """Convert a normalized spec into a `google.cloud.ces_v1beta.types.Evaluation` proto.

    Preserves `agent_transfer`, `tool_call`, `agent_response`, `user_variables`, and
    `user_text` steps on golden evaluations so sub-agent transfers are evaluated honestly.
    """
    from google.cloud.ces_v1beta import types

    tags = [
        spec.get("layer", "golden"),
        spec.get("case_id", display_name),
        spec.get("language", "en"),
        spec.get("priority", "P0"),
    ]
    if spec.get("cuj"):
        tags.append(str(spec["cuj"]))
    tags = [t for t in tags if t]

    if spec.get("layer") == "simulation":
        return types.Evaluation(
            display_name=display_name,
            description=f"Scenario evaluation for {spec['case_id']}",
            tags=tags,
            scenario=types.Evaluation.Scenario(
                task=spec["task"],
                max_turns=int(spec.get("max_turns", 12)),
                user_facts=[
                    types.Evaluation.Scenario.UserFact(
                        name=uf["name"], value=uf["value"]
                    )
                    for uf in spec.get("user_facts", [])
                ],
                rubrics=list(spec.get("rubrics", [])),
                variable_overrides=_to_protobuf_struct(spec.get("variable_overrides", {})),
                evaluation_expectations=list(spec.get("evaluation_expectations", [])),
            ),
        )

    ces_turns = []
    for turn in spec.get("turns", []):
        ces_steps = []
        for step in turn.get("steps", []):
            kind = step["kind"]
            if kind == "user_variables":
                ces_steps.append(
                    types.Evaluation.Step(
                        user_input=types.SessionInput(
                            variables=_to_protobuf_struct(step["variables"])
                        )
                    )
                )
            elif kind == "user_text":
                ces_steps.append(
                    types.Evaluation.Step(
                        user_input=types.SessionInput(text=step["text"])
                    )
                )
            elif kind == "agent_transfer":
                target = str(step["target_agent"])
                if app_name and "/" not in target:
                    target = f"{app_name}/agents/{target}"
                ces_steps.append(
                    types.Evaluation.Step(
                        expectation=types.Evaluation.GoldenExpectation(
                            agent_transfer=types.AgentTransfer(target_agent=target)
                        )
                    )
                )
            elif kind == "tool_call":
                tool_ref = str(step.get("tool") or step["name"])
                if app_name and "/" not in tool_ref:
                    tool_ref = f"{app_name}/tools/{tool_ref}"
                ces_steps.append(
                    types.Evaluation.Step(
                        expectation=types.Evaluation.GoldenExpectation(
                            tool_call=types.ToolCall(
                                display_name=step["name"],
                                tool=tool_ref,
                                args=_to_protobuf_struct(step.get("args") or {}),
                            )
                        )
                    )
                )
            elif kind == "agent_response":
                ces_steps.append(
                    types.Evaluation.Step(
                        expectation=types.Evaluation.GoldenExpectation(
                            agent_response=types.Message(
                                role=step.get("role", "agent"),
                                chunks=[types.Chunk(text=step["text"])],
                            )
                        )
                    )
                )
        ces_turns.append(types.Evaluation.GoldenTurn(steps=ces_steps))

    return types.Evaluation(
        display_name=display_name,
        description=f"Golden evaluation for {spec.get('case_id', display_name)}",
        tags=tags,
        golden=types.Evaluation.Golden(turns=ces_turns),
    )


def _load_yaml_items_in_dir(
    folder: Path, primary_file: str, top_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    candidates: list[Path] = []
    primary = folder / primary_file
    if primary.exists():
        candidates.append(primary)
    if folder.exists():
        for p in sorted(folder.rglob("*.yaml")):
            if p != primary:
                candidates.append(p)
    for path in candidates:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = []
        if isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            for k in top_keys:
                if isinstance(data.get(k), list):
                    items.extend(x for x in data[k] if isinstance(x, dict))
        for item in items:
            cid = str(item.get("id", "")).strip()
            if not cid:
                continue
            if cid not in by_id:
                ordered_ids.append(cid)
            by_id[cid] = item
    return [by_id[cid] for cid in ordered_ids]


def load_yaml_suite(eval_dir: Path) -> dict[str, list[dict[str, Any]]]:
    eval_dir = Path(eval_dir)
    tt_path = eval_dir / "tool_tests" / "tool_tests.yaml"
    tool_tests = tool_tests_mod.load_tool_tests(tt_path) if tt_path.exists() else []
    goldens = _load_yaml_items_in_dir(
        eval_dir / "goldens", "goldens.yaml", ("goldens", "cases")
    )
    simulations = _load_yaml_items_in_dir(
        eval_dir / "simulations", "simulations.yaml", ("simulations", "cases")
    )
    probes = _load_yaml_items_in_dir(
        eval_dir / "probes",
        "probes.yaml",
        ("probes", "routing_probes", "safety_probes", "cases"),
    )
    suite_data = {
        "tool_tests": tool_tests,
        "goldens": goldens,
        "simulations": simulations,
        "probes": probes,
    }
    return regression.merge_into(suite_data, eval_dir)


# ----------------------------------------------------------------------------- local mode


def _ces_types_available() -> bool:
    try:
        import google.cloud.ces_v1beta  # noqa: F401
    except Exception:
        return False
    return True


def validate_spec(spec: dict[str, Any], app_name: str = "") -> tuple[str, str]:
    """Check a normalised spec WITHOUT running it.

    Returns (status, reason):
      INVALID  structural problem (no turns / no task) or the CES proto conversion failed
      VALID    structure OK and the spec converts to a `types.Evaluation` proto
      LOADED   structure OK; the CES library is not installed so the proto was not built
    """
    if spec.get("layer") == "simulation":
        if not spec.get("task"):
            return "INVALID", "simulation has no task / user_goal"
    elif not spec.get("turns"):
        return "INVALID", "golden has no turns"
    elif not any(
        s["kind"] == "user_text" for turn in spec["turns"] for s in turn.get("steps", [])
    ):
        return "INVALID", "golden has no user text in any turn"

    if not _ces_types_available():
        return "LOADED", "CES library not installed; structure checked only"
    try:
        spec_to_ces_evaluation(
            spec,
            display_name=spec["case_id"],
            app_name=app_name or "projects/p/locations/l/apps/a",
        )
    except Exception as exc:  # the proto constructor is the real validator
        return "INVALID", f"{type(exc).__name__}: {exc}"
    return "VALID", ""


def run_local_suite(
    eval_dir: Path,
    targets: set[str] | None = None,
    app_name: str = "",
) -> dict[str, Any]:
    """Gate 0: EXECUTE tool tests, VALIDATE goldens / simulations / probes (never run them)."""
    suite_data = load_yaml_suite(eval_dir)
    results: list[dict[str, Any]] = []

    tt_cases = [
        c for c in suite_data["tool_tests"]
        if not targets or str(c.get("id")) in targets
    ]
    if tt_cases:
        tt_report = tool_tests_mod.run_suite(tt_cases)
        for detail in tt_report["details"]:
            results.append(
                {
                    "id": detail["id"],
                    "layer": "tool_test",
                    "executed": True,
                    "status": "PASS" if detail["passed"] else "FAIL",
                    "reason": detail.get("reason", ""),
                }
            )

    for layer_key, layer_name in (
        ("goldens", "golden"),
        ("simulations", "simulation"),
        ("probes", "probe"),
    ):
        for case in suite_data[layer_key]:
            cid = str(case.get("id") or "")
            if targets and cid not in targets:
                continue
            spec = yaml_case_to_spec(case, layer=layer_name)
            status, reason = validate_spec(spec, app_name=app_name)
            results.append(
                {
                    "id": cid,
                    "layer": layer_name,
                    "executed": False,
                    "status": status,
                    "reason": reason,
                    "priority": spec.get("priority", "P0"),
                    "language": spec.get("language", "en"),
                }
            )

    tool_rows = [r for r in results if r["executed"]]
    spec_rows = [r for r in results if not r["executed"]]
    tool_passed = sum(1 for r in tool_rows if r["status"] == "PASS")
    counts = {
        "total": len(spec_rows),
        "valid": sum(1 for r in spec_rows if r["status"] == "VALID"),
        "loaded": sum(1 for r in spec_rows if r["status"] == "LOADED"),
        "invalid": sum(1 for r in spec_rows if r["status"] == "INVALID"),
    }
    return {
        "mode": "local",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_tests": {
            "total": len(tool_rows),
            "passed": tool_passed,
            "failed": len(tool_rows) - tool_passed,
        },
        "specs": counts,
        "note": (
            "goldens / simulations / probes were validated offline, NOT executed; "
            "run them on the server with --mode staging --app <app resource>"
        ),
        "ok": (len(tool_rows) - tool_passed) == 0 and counts["invalid"] == 0,
        "results": results,
    }


# ----------------------------------------------------------------------------- cloud mode


def git_sha(short: bool = False) -> str:
    try:
        args = ["git", "rev-parse"] + (["--short=7"] if short else []) + ["HEAD"]
        return subprocess.check_output(args, cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "nogit"


def git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        )
        return bool(out.strip())
    except Exception:
        return False


def read_agent_model(app_dir: Path) -> str:
    """The agent model from <app_dir>/app.json (gate.py compares it with gate_thresholds.json)."""
    try:
        app = json.loads((Path(app_dir) / "app.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    settings = app.get("modelSettings") or app.get("model_settings") or {}
    return str(settings.get("model") or app.get("model") or "")


def read_judge_model(thresholds_path: Path) -> str:
    try:
        return str(json.loads(Path(thresholds_path).read_text(encoding="utf-8")).get("judge_model") or "")
    except Exception:
        return ""


def layer_lookup(eval_dir: Path) -> dict[str, tuple[str, str]]:
    """test id -> (local layer, priority) from the YAML suite, so records get the right gate layer."""
    out: dict[str, tuple[str, str]] = {}
    try:
        suite_data = load_yaml_suite(eval_dir)
    except Exception:
        return out
    for layer_key, layer_name in (
        ("goldens", "golden"),
        ("simulations", "simulation"),
        ("probes", "probe"),
    ):
        for case in suite_data.get(layer_key, []):
            cid = str(case.get("id") or "")
            if cid:
                out[cid] = (layer_name, str(case.get("priority") or "P0"))
    return out


def infer_layer(display_name: str) -> tuple[str, str]:
    """Fallback when a cloud eval is not in the local YAML: guess the layer from its name."""
    low = display_name.lower()
    if low.startswith("probe"):
        return "probe", "P0"
    if low.startswith("golden"):
        return "golden", "P1"
    return "simulation", "P1"


def bench_report_to_records(
    report: dict[str, Any],
    *,
    run_id: str,
    layers: dict[str, tuple[str, str]],
    modality: str = "text",
    agent_model: str = "",
    judge_model: str = "",
    git_sha_value: str = "",
    dirty: bool = False,
    trigger: str = "local",
    change_note: str = "",
) -> list[dict[str, Any]]:
    """One run_record per test x repeat from a run_bench report (pass/fail/infra counts)."""
    records: list[dict[str, Any]] = []
    ts = str(report.get("timestamp") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    versions = [v for v in report.get("app_versions_seen", []) if v and v != "(draft)"]
    app_version = versions[0] if len(versions) == 1 else ""
    for res in report.get("results", []):
        test_id = str(res.get("display_name") or res.get("ve_id") or "")
        if not test_id:
            continue
        local_layer, priority = layers.get(test_id) or infer_layer(test_id)
        passes = int(res.get("pass_runs") or 0)
        fails = int(res.get("fail_runs") or 0)
        if not fails and res.get("total_runs"):
            fails = max(int(res["total_runs"]) - passes, 0)
        infra = int(res.get("infra_runs") or 0)
        statuses = ["pass"] * passes + ["fail"] * fails + ["infra_error"] * infra
        reasons = [p.get("reason", "") for p in res.get("pattern", []) if p.get("classification") == "FAIL"]
        for n, status in enumerate(statuses, start=1):
            rec = {
                "run_id": run_id,
                "timestamp": ts,
                "trigger": trigger,
                "git_sha": git_sha_value,
                "dirty": bool(dirty),
                "app_version": app_version,
                "agent_model": agent_model,
                "judge_model": judge_model,
                "test_id": test_id,
                "layer": GATE_LAYER[(local_layer, modality)],
                "priority": priority,
                "modality": modality,
                "repeat": n,
                "status": status,
                "label": "",
                "reason": (reasons[0] if status == "fail" and reasons else "")[:300],
            }
            if change_note:
                rec["change_note"] = change_note
            records.append(rec)
    return records


def append_records(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return len(records)


LOCAL_LAYER_OF = {"golden": "golden", "audio_golden": "golden", "sim": "simulation", "audio_sim": "simulation",
                  "probe": "probe", "simulation": "simulation"}


def select_targets(eval_dir: Path, layers: str, priority: str) -> list[str]:
    """Eval ids from the local YAML suite matching LAYERS (gate names) and PRIORITY.

    After `cxas push-eval` the cloud display names equal the YAML ids, so these ids are
    valid --evals selectors for run_bench. Offline-only layers (tool, callback, contract)
    are ignored here: `make ci` runs them.
    """
    wanted = {LOCAL_LAYER_OF[l] for l in (x.strip() for x in layers.split(",")) if l in LOCAL_LAYER_OF}
    if layers and not wanted:
        return []
    ids: list[str] = []
    for cid, (layer, pri) in layer_lookup(eval_dir).items():
        if wanted and layer not in wanted:
            continue
        if priority and pri != priority:
            continue
        ids.append(cid)
    return ids


def build_bench_argv(args: argparse.Namespace, label: str, repeats: int) -> list[str]:
    """Translate run_evals flags into scripts/run_bench.py flags."""
    argv = [
        "--app", args.app_name,
        "--bench-dir", args.bench_dir,
        "--modality", args.modality,
        "--runs", str(repeats),
        "--report-name", label,
        "--run-label", label,
    ]
    if args.targets:
        argv += ["--evals", args.targets]
    elif args.unstable:
        argv += ["--evals", f"@{args.unstable_set}"]
    elif getattr(args, "layers", "") or getattr(args, "priority", ""):
        ids = select_targets(Path(args.eval_dir), args.layers, args.priority)
        if not ids:
            raise LookupError(
                f"no evals in {args.eval_dir} match layers={args.layers or 'any'} priority={args.priority or 'any'}"
            )
        argv += ["--evals", ",".join(ids)]
    if args.smoke:
        argv.append("--smoke")
    if args.full:
        argv += ["--batch-size", str(args.batch_size)]
    if args.resume_run:
        argv += ["--resume-run", args.resume_run]
    if args.compare_with:
        argv += ["--compare-with", args.compare_with]
    if args.dry_run:
        argv.append("--dry-run")
    return argv


def run_cloud(args: argparse.Namespace) -> int:
    if not args.app_name:
        print(
            "ERROR: cloud runs need --app projects/<p>/locations/<l>/apps/<id> (or CES_APP_NAME).",
            file=sys.stderr,
        )
        return 1
    if args.smoke and not (args.targets or args.resume_run or args.dry_run):
        print("ERROR: --smoke needs --targets <eval ids or display names> (Gate 1 is targeted).", file=sys.stderr)
        return 1

    kind = "smoke" if args.smoke else "unstable" if args.unstable else "full" if args.full else "eval"
    repeats = args.repeats or DEFAULT_REPEATS.get(kind, 1)
    label = args.label or f"{kind}-{git_sha(short=True)}"

    from scripts import run_bench  # local import: heavy google-cloud deps only in cloud mode

    try:
        bench_argv = build_bench_argv(args, label, repeats)
    except LookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    code = run_bench.main(bench_argv)
    if args.dry_run or args.no_records:
        return code
    if code not in (0, 2):
        return code

    report_path = Path(args.bench_dir) / "runs" / f"{label}.json"
    if not report_path.exists():
        print(f"WARNING: no report at {report_path}; nothing appended to {args.records}", file=sys.stderr)
        return code
    report = json.loads(report_path.read_text(encoding="utf-8"))
    note = args.change_note
    if code == 2:
        note = (note + " " if note else "") + "APP CHANGED MID-RUN: discard"
    records = bench_report_to_records(
        report,
        run_id=label,
        layers=layer_lookup(Path(args.eval_dir)),
        modality=args.modality,
        agent_model=read_agent_model(Path(args.app_dir)),
        judge_model=read_judge_model(Path(args.thresholds)),
        git_sha_value=git_sha(),
        dirty=git_dirty(),
        trigger=args.trigger,
        change_note=note,
    )
    n = append_records(Path(args.records), records)
    print(f"appended {n} records (run_id={label}) to {args.records}; next: suite/gate.py --run-id {label}")
    return code


def push_specs(args: argparse.Namespace, client: Any = None) -> int:
    """Create or update every local golden / simulation / probe in the app.

    Uses SCRAPI's `Evaluations.update_evaluation` (create-or-update by display name), the
    same call `cxas push-eval` makes, but also covers simulations (scenario evaluations)
    which the CLI's goldens-only YAML loader cannot push. Display name == YAML id, so the
    ids stay valid selectors for `make eval TARGETS=...` and run_bench.
    """
    if not args.app_name:
        print("ERROR: --push needs --app projects/<p>/locations/<l>/apps/<id> (or CES_APP_NAME).", file=sys.stderr)
        return 1
    targets = {t.strip() for t in args.targets.split(",") if t.strip()} or None
    suite_data = load_yaml_suite(Path(args.eval_dir))
    plan: list[tuple[str, str, dict[str, Any]]] = []
    for layer_key, layer_name in (("goldens", "golden"), ("simulations", "simulation"), ("probes", "probe")):
        for case in suite_data[layer_key]:
            cid = str(case.get("id") or "")
            if not cid or (targets and cid not in targets):
                continue
            spec = yaml_case_to_spec(case, layer=layer_name)
            status, reason = validate_spec(spec, app_name=args.app_name)
            if status == "INVALID":
                print(f"INVALID: {layer_name} {cid}: {reason}", file=sys.stderr)
                return 1
            plan.append((cid, layer_name, spec))
    if not plan:
        print(f"ERROR: nothing to push from {args.eval_dir}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps({"mode": "push", "dry_run": True, "app": args.app_name,
                          "evals": [{"id": c, "layer": l} for c, l, _ in plan]}, indent=2))
        return 0

    if client is None:
        from cxas_scrapi.core.evaluations import Evaluations  # SCRAPI: list/create/update evaluations

        client = Evaluations(app_name=args.app_name)
    log_path = Path(os.environ.get("CLOUD_LOG_PATH") or cloud_log.DEFAULT_LOG)
    with cloud_log.logged_call("READ", "Evaluations.list_evaluations", args.app_name,
                               "push evals: existing display names", log_path=log_path) as call:
        existing = {e.display_name: e.name for e in client.list_evaluations(args.app_name)}
        call.outcome = f"OK ({len(existing)} evaluations)"
    pushed: list[dict[str, str]] = []
    for cid, layer_name, spec in plan:
        proto = spec_to_ces_evaluation(spec, display_name=cid, app_name=args.app_name)
        if existing.get(cid):
            proto.name = existing[cid]
        action = "update" if existing.get(cid) else "create"
        with cloud_log.logged_call("WRITE", "Evaluations.update_evaluation", args.app_name,
                                   f"push eval {cid} ({layer_name}, {action})", log_path=log_path) as call:
            res = client.update_evaluation(evaluation=proto, app_name=args.app_name)
            name = str(getattr(res, "name", "") or "")
            call.outcome = f"OK ({name.rsplit('/', 1)[-1] or action})"
        pushed.append({"id": cid, "layer": layer_name, "action": action, "name": name})
    print(json.dumps({"mode": "push", "app": args.app_name, "pushed": len(pushed), "evals": pushed}, indent=2))
    return 0


# ----------------------------------------------------------------------------- self-test


def _self_test() -> int:
    # 1. Credential refresh test (expiring within 10 min triggers refresh)
    class FakeCreds:
        def __init__(self, expiry: float) -> None:
            self.valid = True
            self.expiry = expiry
            self.token = "old-token"
            self.refreshed = 0

        def refresh(self, request: Any = None) -> None:
            self.refreshed += 1
            self.token = "new-token"
            self.expiry = time.time() + 3600

    creds = FakeCreds(time.time() + 120)
    assert refresh_credentials_if_needed(creds, min_ttl_sec=600) is True
    assert creds.refreshed == 1 and creds.token == "new-token"
    assert refresh_credentials_if_needed(creds, min_ttl_sec=600) is False

    # 2. spec_to_ces_evaluation preserves agent_transfer and tool_call steps
    golden_case = {
        "id": "golden_transfer_01",
        "language": "en",
        "session_variables": {"auth_status": "none"},
        "turns": [
            {
                "user": "I have an internet outage",
                "expected_transfer": "tech_support",
                "expected_tool_calls": [{"name": "check_service_outage"}],
                "agent": "Let me check for outages in your area.",
            }
        ],
    }
    spec = yaml_case_to_spec(golden_case, layer="golden")
    if _ces_types_available():
        ev_proto = spec_to_ces_evaluation(
            spec,
            display_name="golden_transfer_01",
            app_name="projects/p/locations/us/apps/a1",
        )
        steps = list(ev_proto.golden.turns[0].steps)
        transfer_steps = [
            s for s in steps if s.expectation and s.expectation.agent_transfer.target_agent
        ]
        assert len(transfer_steps) == 1, steps
        assert (
            transfer_steps[0].expectation.agent_transfer.target_agent
            == "projects/p/locations/us/apps/a1/agents/tech_support"
        )
    else:
        print("note: google-cloud-ces not installed; proto conversion case skipped", file=sys.stderr)

    # 3. Concurrent-push version guard detects mid-run app modification
    class FakeApp:
        def __init__(self, ut: str) -> None:
            self.update_time = ut

    class FakeAppClient:
        def __init__(self, times: list[str]) -> None:
            self._times = list(times)

        def get_app(self, name: str) -> FakeApp:
            return FakeApp(self._times.pop(0))

    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "cloud-log.md"
        log_file.write_text(
            "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        client = FakeAppClient(["2026-10-06T10:00:00Z", "2026-10-06T10:05:00Z"])
        t0 = check_app_version_guard(client, "projects/p/locations/us/apps/a1", log_path=log_file)
        assert t0 == "2026-10-06T10:00:00Z"
        caught = False
        try:
            check_app_version_guard(
                client,
                "projects/p/locations/us/apps/a1",
                baseline_update_time=t0,
                log_path=log_file,
            )
        except ConcurrentPushError:
            caught = True
        assert caught, "Expected ConcurrentPushError when app.update_time changed"

    # 4. Local validation never reports an unexecuted spec as PASS
    status, _ = validate_spec(spec)
    assert status in ("VALID", "LOADED"), status
    bad_status, bad_reason = validate_spec(yaml_case_to_spec({"id": "g_empty", "turns": []}))
    assert bad_status == "INVALID" and "turns" in bad_reason, (bad_status, bad_reason)
    sim_status, _ = validate_spec(yaml_case_to_spec({"id": "s1", "task": "Cancel my line"}, layer="simulation"))
    assert sim_status in ("VALID", "LOADED"), sim_status

    # 5. Bench report -> gate records: one row per repeat, statuses and layers mapped
    report = {
        "timestamp": "2026-10-07T00:00:00Z",
        "app_versions_seen": ["(draft)"],
        "results": [
            {"display_name": "golden_transfer_01", "pass_runs": 3, "fail_runs": 1, "total_runs": 4,
             "infra_runs": 1, "pattern": [{"classification": "FAIL", "reason": "judge: wrong tool"}]},
            {"display_name": "probe_prompt_injection", "pass_runs": 1, "fail_runs": 0, "total_runs": 1,
             "infra_runs": 0, "pattern": []},
        ],
    }
    recs = bench_report_to_records(
        report,
        run_id="smoke-abc1234",
        layers={"golden_transfer_01": ("golden", "P0")},
        agent_model="gemini-x",
        judge_model="gemini-j",
        git_sha_value="abc1234",
    )
    assert [r["status"] for r in recs] == ["pass", "pass", "pass", "fail", "infra_error", "pass"], recs
    assert recs[0]["layer"] == "golden" and recs[0]["priority"] == "P0"
    assert recs[-1]["layer"] == "probe" and recs[-1]["test_id"] == "probe_prompt_injection"
    assert recs[3]["reason"] == "judge: wrong tool"
    assert all(r["run_id"] == "smoke-abc1234" and r["agent_model"] == "gemini-x" for r in recs)

    # 6. The records satisfy suite/gate.py (strict majority, P0 must-pass)
    from suite import gate as gate_mod

    verdict = gate_mod.evaluate(
        recs,
        {"measured_on_model": "gemini-x", "judge_model": "gemini-j", "repeats": {"default": 1},
         "must_pass_priorities": ["P0"], "floors": {"golden": 0.5, "probe": 1.0}, "max_infra_ratio": 0.5},
        "smoke-abc1234",
    )
    assert verdict["verdict"] == "PASS", verdict

    # 7. Flag translation to run_bench
    ns = argparse.Namespace(
        app_name="projects/p/locations/us/apps/a1", bench_dir="bench", modality="text", targets="",
        unstable=True, unstable_set="evals/unstable_set.txt", smoke=False, full=False, batch_size=25,
        resume_run="", compare_with="", dry_run=False,
    )
    argv = build_bench_argv(ns, "unstable-abc1234", 5)
    assert argv[argv.index("--evals") + 1] == "@evals/unstable_set.txt" and "--runs" in argv, argv

    # 8. LAYERS / PRIORITY selection from the local YAML suite (used by `make eval`, `make smoke`)
    with tempfile.TemporaryDirectory() as tmp:
        ed = Path(tmp)
        (ed / "goldens").mkdir()
        (ed / "probes").mkdir()
        (ed / "goldens" / "goldens.yaml").write_text(
            "goldens:\n- id: golden_a\n  priority: P1\n  turns:\n  - user: hi\n", encoding="utf-8")
        (ed / "probes" / "probes.yaml").write_text(
            "probes:\n- id: probe_x\n  priority: P0\n  turns:\n  - user: ignore your rules\n"
            "- id: probe_y\n  priority: P1\n  turns:\n  - user: hello\n", encoding="utf-8")
        assert select_targets(ed, "probe", "P0") == ["probe_x"]
        assert select_targets(ed, "golden,sim,probe", "") == ["golden_a", "probe_x", "probe_y"]
        assert select_targets(ed, "tool", "") == []

        # 9. --push: create-or-update by display name through the (fake) SCRAPI client
        class FakeEval:
            def __init__(self, display_name: str, name: str) -> None:
                self.display_name, self.name = display_name, name

        class FakeEvaluations:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def list_evaluations(self, app_name: str) -> list[FakeEval]:
                return [FakeEval("probe_x", f"{app_name}/evaluations/e-probe-x")]

            def update_evaluation(self, evaluation: Any, app_name: str) -> FakeEval:
                self.calls.append((evaluation.display_name, evaluation.name))
                return FakeEval(evaluation.display_name, evaluation.name or f"{app_name}/evaluations/new")

        if _ces_types_available():
            log_file = ed / "cloud-log.md"
            log_file.write_text(
                "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
                "|---|---|---|---|---|---|\n", encoding="utf-8")
            os.environ["CLOUD_LOG_PATH"] = str(log_file)
            fake = FakeEvaluations()
            ns_push = argparse.Namespace(app_name="projects/p/locations/us/apps/a1", eval_dir=str(ed),
                                         targets="", dry_run=False)
            assert push_specs(ns_push, client=fake) == 0
            assert [c[0] for c in fake.calls] == ["golden_a", "probe_x", "probe_y"], fake.calls
            assert fake.calls[1][1].endswith("/evaluations/e-probe-x") and fake.calls[0][1] == "", fake.calls
            assert log_file.read_text(encoding="utf-8").count("Evaluations.update_evaluation") == 3
            del os.environ["CLOUD_LOG_PATH"]

    print("OK: 9/9 run_evals self-test cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mode", choices=("local", "staging"), default="local",
                        help="local = offline Gate 0; staging = run on the server (implied by --smoke/--unstable/--full)")
    parser.add_argument("--eval-dir", "--evals-dir", dest="eval_dir", default=str(REPO_ROOT / "evals"))
    parser.add_argument("--app-dir", default="cxas_app", help="Agent folder; app.json gives agent_model for the records")
    parser.add_argument("--smoke", action="store_true", help="Gate 1: targeted evals, 3 repeats, go/no-go verdict")
    parser.add_argument("--unstable", action="store_true", help="Gate 2: evals listed in --unstable-set, 5 repeats")
    parser.add_argument("--full", action="store_true", help="Gate 3: every eval in the app, 3 repeats")
    parser.add_argument("--targets", default=os.environ.get("TARGETS", ""),
                        help="Comma-separated eval ids / display names / @file (cloud) or test ids (local)")
    parser.add_argument("--unstable-set", default="evals/unstable_set.txt", help="One eval id or display name per line")
    parser.add_argument("--layers", default="", help="Cloud: pick local YAML evals by gate layer (golden,sim,probe,audio_golden,audio_sim)")
    parser.add_argument("--priority", default="", choices=("", "P0", "P1", "P2"), help="Cloud: pick local YAML evals by priority")
    parser.add_argument("--repeats", type=int, default=0, help="Conversations per eval (default: smoke 3, unstable 5, full 3, else 1)")
    parser.add_argument("--batch-size", type=int, default=25, help="Evals per evaluation run in --full mode")
    parser.add_argument("--modality", choices=("text", "audio"), default="text")
    parser.add_argument("--resume-run", default="", help="Continue polling an existing evaluationRun")
    parser.add_argument("--compare-with", default="", help="Earlier report JSON to list regressions against")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without cloud calls")
    parser.add_argument("--app-name", "--app", dest="app_name", default=os.environ.get("CES_APP_NAME", ""),
                        help="projects/<p>/locations/<l>/apps/<id>")
    parser.add_argument("--bench-dir", default=os.environ.get("BENCH_DIR", "bench"),
                        help="Where run_bench keeps dev/index.json and runs/ (reports)")
    parser.add_argument("--label", default="", help="Run id / report name (default <kind>-<git sha7>)")
    parser.add_argument("--records", default="history/runs.jsonl", help="Gate records file to append to")
    parser.add_argument("--no-records", action="store_true", help="Do not append gate records")
    parser.add_argument("--thresholds", default="gate_thresholds.json", help="Gives judge_model for the records")
    parser.add_argument("--trigger", default=os.environ.get("TRIGGER", "local"),
                        choices=("local", "pr", "main", "nightly", "release"))
    parser.add_argument("--change-note", default="", help="Why this run happened (stored in the records)")
    parser.add_argument("--out", default="", help="Optional JSON report output path (local mode)")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self-tests")
    parser.add_argument("--push", action="store_true",
                        help="Create/update the local goldens, simulations and probes in --app (SCRAPI update_evaluation)")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.push:
        return push_specs(args)

    cloud_requested = args.mode == "staging" or args.smoke or args.unstable or args.full or bool(args.resume_run)
    if cloud_requested:
        return run_cloud(args)

    targets = {t.strip() for t in args.targets.split(",") if t.strip()} or None
    report = run_local_suite(Path(args.eval_dir), targets=targets, app_name=args.app_name)
    report["label"] = args.label or "local"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for r in report["results"]:
        if r["status"] in ("FAIL", "INVALID"):
            print(f"{r['status']}: {r['layer']} {r['id']}: {r['reason']}", file=sys.stderr)
    tt, sp = report["tool_tests"], report["specs"]
    print(
        json.dumps(
            {
                "mode": "local",
                "label": report["label"],
                "tool_tests_executed": f"{tt['passed']}/{tt['total']} passed",
                "specs_validated": f"{sp['valid'] + sp['loaded']}/{sp['total']} valid, {sp['invalid']} invalid",
                "note": report["note"],
            }
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
