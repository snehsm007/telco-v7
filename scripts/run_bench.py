#!/usr/bin/env python3
"""Cloud benchmark runner for CX Agent Studio (CXAS / CES) evaluations (Gates 1-4).

Runs evaluations that live in the app (public/bootcamp evals, or evals you pushed
with `cxas push-eval`), N repeats each, and writes an honest report:

  <bench-dir>/runs/<report-name>.json   full report (consumed by scripts/bench_summary.py
                                        and scripts/build_dashboard.py)
  <bench-dir>/runs/<report-name>.md     the same, readable
  <bench-dir>/runs/<report-name>_raw/   every evaluation run + result as returned
  <bench-dir>/runs/failing_runs_data/<report-name>/   one json + md per non-passing
                                        result: judge reasoning, transcript, tool calls,
                                        platform fallback reasons

Optional exported bundle (`<bench-dir>/dev/`): if `dev/evaluations/*.json` and
`dev/evaluationExpectations/*.json` exist (console / `cxas export` output), any that
are missing from the app are created first and expectation references are relinked.
`dev/index.json` ([{"name": <display name>, "topic": ..., "language": ...}, ...])
gives every evaluation a short stable id (VE-01, VE-02, ... in file order); when it is
missing it is built from the app's evaluations (sorted by display name) and written,
so ids stay stable across runs. `dev/SHA256SUMS` is verified when present.

Scoring (unchanged from the battle-tested original): a result is PASS only when the
platform completed it and the judge said PASS, FAIL only when it completed and the judge
said FAIL. Anything else (not completed, not scored, missing, or a FAIL whose
conversation shows a platform quota/availability fallback) is INFRA: it is re-run (at
most --max-infra-rounds rounds) and never counted. An eval's verdict is PASS or FAIL
when a majority of its --runs scored results agree, otherwise INCONCLUSIVE.

Every cloud call is one row in docs/cloud-log.md (suite/cloud_log.py): start time,
exact method, target resource, real outcome. Rows name evals by id, never display name.

Usage (normally through the Makefile):
  python3 scripts/run_bench.py --app <APP> --evals VE-01,VE-02 --runs 3 --smoke --report-name smoke-<sha7>
  python3 scripts/run_bench.py --app <APP> --evals @evals/unstable_set.txt --runs 5 --report-name unstable-<sha7>
  python3 scripts/run_bench.py --app <APP> --runs 3 --report-name full-<sha7> --compare-with bench/runs/full-<prev>.json
  python3 scripts/run_bench.py --app <APP> --resume-run <evaluationRun id> --evals VE-07 --report-name smoke-<sha7>
  python3 scripts/run_bench.py --app <APP> --fetch-runs <run id>,<run id>      # READ only
  python3 scripts/run_bench.py --dry-run [--app <APP>]                          # no cloud calls
  python3 scripts/run_bench.py --self-test                                     # offline

Exit codes: 0 ok, 1 error, 2 another push changed the app mid-run, 3 re-login needed.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import concurrent.futures
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from suite import cloud_log  # noqa: E402  (needs REPO_ROOT on sys.path)

try:
    from google.api_core.exceptions import GoogleAPIError  # base of every API error
except ImportError:  # offline use without the Google client libraries
    GoogleAPIError = RuntimeError

DEFAULT_BENCH_ROOT = Path(os.environ.get("BENCH_DIR") or (REPO_ROOT / "bench"))
DEFAULT_ID_PREFIX = os.environ.get("BENCH_ID_PREFIX", "VE")
EXECUTION_STATES = {
    0: "EXECUTION_STATE_UNSPECIFIED",
    1: "RUNNING",
    2: "COMPLETED",
    3: "ERROR",
    4: "CANCELLED",
    5: "QUEUED",
}
OUTCOMES = {0: "OUTCOME_UNSPECIFIED", 1: "PASS", 2: "FAIL", 3: "SKIPPED"}
RUN_STATES = {
    0: "EVALUATION_RUN_STATE_UNSPECIFIED",
    1: "RUNNING",
    2: "COMPLETED",
    3: "ERROR",
    4: "CANCELLED",
    5: "QUEUED",
}
RUN_TERMINAL_STATES = ("COMPLETED", "ERROR", "CANCELLED")
# Platform quota/availability trouble, as it shows up in error texts and span "fallback reason"s.
INFRA_PATTERN = re.compile(
    r"\b(?:429|503|504)\b|resource[ _]exhausted|quota|\bunavailable\b|deadline[ _]exceeded"
    r"|rate[ _]limit|overloaded|too many requests",
    re.IGNORECASE,
)
# For writes, only errors that mean "the request was rejected before it ran" are retried.
WRITE_RETRY_PATTERN = re.compile(
    r"\b(?:429|503)\b|resource[ _]exhausted|quota|\bunavailable\b|rate[ _]limit|too many requests",
    re.IGNORECASE,
)
REAUTH_PATTERN = re.compile(
    r"invalid_rapt|reauthentication failed|access_token_type_unsupported", re.IGNORECASE
)
RETRY_DELAYS_S = (15, 45, 90)
POLL_INTERVAL_S = 30
# A 20-eval x 5 run (100 conversations) has taken 38-46+ min. The ceiling only exists to
# catch a run that never ends; a run that hit it is continued with --resume-run.
RUN_TIMEOUT_S = 150 * 60
JUDGE_KEYS = (
    "all_expectations_satisfied",
    "task_completed",
    "evaluation_expectation_results",
    "user_goal_satisfaction_result",
    "hallucination_result",
    "expectation_outcomes",
    "rubric_outcomes",
    "task",
    "user_facts",
)
_INFRA_ERROR_CODES = frozenset({"SYSTEM_DOWN", "INTERNAL_ERROR", "AUTH_SERVICE_UNAVAILABLE"})
_DEFAULT_BUSINESS_ERROR_CODES = (
    "INVALID_INPUT",
    "NOT_FOUND",
    "NOT_IDENTIFIED",
    "NOT_LOGGED_IN",
    "CODE_NOT_SENT",
    "WRONG_CODE",
    "WRONG_PIN",
    "TOO_MANY_ATTEMPTS",
    "LOCKED_OUT",
    "LIMIT_EXCEEDED",
    "CARD_DECLINED",
    "PAYMENT_DECLINED",
    "NOT_ELIGIBLE",
    "ALREADY_APPLIED",
    "ALREADY_ENROLLED",
    "OUT_OF_WINDOW",
    "OUTAGE_ACTIVE",
    "SERVICE_UNAVAILABLE",
    "INSUFFICIENT_FUNDS",
    "MALFORMED_REQUEST",
    "REFUND_THRESHOLD_EXCEEDED",
    "BUSINESS_ACCOUNT_HANDOFF",
    "SERVICE_TYPE_REQUIRED",
    "RATE_LIMITED",
    "ALREADY_PROCESSED",
    "INELIGIBLE",
    "PAST_WINDOW",
    "OUT_OF_RANGE",
    "REQUIRES_ESCALATION",
    "UNSUPPORTED_OPERATION",
    "CONFIRMATION_REQUIRED",
)
try:
    from lib.replies import ERROR_CODES as _LIB_ERROR_CODES  # type: ignore[import-not-found]

    BUSINESS_ERROR_CODES = tuple(
        dict.fromkeys(
            [c for c in (*_LIB_ERROR_CODES, *_DEFAULT_BUSINESS_ERROR_CODES) if c not in _INFRA_ERROR_CODES]
        )
    )
except Exception:
    BUSINESS_ERROR_CODES = _DEFAULT_BUSINESS_ERROR_CODES


def _current_git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return ""


class ReauthRequired(RuntimeError):
    """The credentials need a human re-login; all cloud work stops."""


class ConcurrentPushDetected(RuntimeError):
    """`get_app().update_time` changed while the benchmark was running."""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_transient(exc: BaseException, write: bool = False) -> bool:
    """True for quota/availability errors that a retry can fix."""
    text = f"{type(exc).__name__}: {exc}"
    try:
        from google.api_core import exceptions as gexc  # gRPC/HTTP error classes
    except ImportError:
        gexc = None
    if write:
        if gexc is not None and isinstance(exc, (gexc.TooManyRequests, gexc.ServiceUnavailable)):
            return True
        return bool(WRITE_RETRY_PATTERN.search(text))
    if gexc is not None and isinstance(
        exc,
        (
            gexc.TooManyRequests,
            gexc.ServiceUnavailable,
            gexc.DeadlineExceeded,
            gexc.InternalServerError,
            gexc.BadGateway,
            gexc.GatewayTimeout,
        ),
    ):
        return True
    return bool(INFRA_PATTERN.search(text))


class Cloud:
    """SCRAPI clients plus the policy every call follows.

    One call = one cloud-log row (start time, exact method, target, real outcome). Transient
    errors are retried with backoff (each attempt is its own row); a re-login error raises
    ReauthRequired at once.
    """

    def __init__(self, apps, evals=None, history=None, *, app_clients=None, log_kwargs=None, sleep=time.sleep):
        self.apps = apps
        self.evals = evals
        self.history = history
        self.app_clients = app_clients  # app resource name -> (evals, history); no cloud call
        self.log_kwargs = dict(log_kwargs or {})
        self.sleep = sleep

    def bind_app(self, app_name: str) -> None:
        if self.evals is None and self.app_clients is not None:
            self.evals, self.history = self.app_clients(app_name)

    def call(self, op, method, target, notes, fn, describe=None, *, write=False):
        attempt = 0
        while True:
            attempt += 1
            label = notes if attempt == 1 else f"{notes} (retry {attempt - 1})"
            try:
                with cloud_log.logged_call(op, method, target, label, **self.log_kwargs) as record:
                    result = fn()
                    if describe is not None:
                        record.outcome = f"OK ({describe(result)})"
                return result
            except cloud_log.CloudLogError:
                raise
            except Exception as exc:  # the row with the error is already written
                text = f"{type(exc).__name__}: {exc}"
                if REAUTH_PATTERN.search(text):
                    raise ReauthRequired(text) from exc
                if attempt > len(RETRY_DELAYS_S) or not is_transient(exc, write):
                    raise
                self.sleep(RETRY_DELAYS_S[attempt - 1])

    def list_pages(self, method, target, notes, call_page, field):
        """List every page with one logged row per page request."""
        items: list = []
        token = ""
        page = 0
        while True:
            page += 1
            pager = self.call(
                "READ",
                method,
                target,
                f"{notes} (page {page})",
                lambda token=token: call_page(token),
                describe=lambda pg: (
                    f"{len(getattr(pg, field))} {field}, more pages={bool(pg.next_page_token)}"
                ),
            )
            items.extend(getattr(pager, field))
            token = pager.next_page_token
            if not token:
                return items


def _ces_types():
    from google.cloud.ces_v1beta import types  # CES request messages

    return types


def _field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _enum_name(value, names: dict[int, str]) -> str:
    if hasattr(value, "name") and not isinstance(value, (str, dict)):
        return str(value.name)
    if isinstance(value, int):
        return names.get(value, str(value))
    return str(value) if value else names[0]


def to_plain(obj):
    """proto-plus message -> dict (enums as ints); dicts pass through."""
    if obj is None or isinstance(obj, dict):
        return obj
    to_dict = getattr(type(obj), "to_dict", None)
    if callable(to_dict):
        return to_dict(obj)
    return {"repr": repr(obj)}


# ----------------------------------------------------------------- bench bundle (optional)


def verify_bench_sha256sums(dev_dir: Path) -> tuple[bool, list[str]]:
    sha_file = dev_dir / "SHA256SUMS"
    if not sha_file.exists():
        return False, [f"Missing {sha_file}"]
    errors = []
    for line in sha_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        want_hash, rel_path = parts[0], parts[1].lstrip("* ")
        target = dev_dir / rel_path
        if not target.exists():
            errors.append(f"Missing benchmark file: {rel_path}")
            continue
        got_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if got_hash != want_hash:
            errors.append(f"SHA256 mismatch for {rel_path}: want {want_hash}, got {got_hash}")
    return len(errors) == 0, errors


def load_bench_bundles(dev_dir: Path) -> tuple[list[dict], list[dict]]:
    """Exported expectations and evaluations (console / `cxas export` JSON); empty when absent."""
    exp_dir = dev_dir / "evaluationExpectations"
    eval_dir = dev_dir / "evaluations"
    expectations = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(exp_dir.rglob("*.json"))
    ] if exp_dir.is_dir() else []
    evaluations = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(eval_dir.rglob("*.json"))
    ] if eval_dir.is_dir() else []
    return expectations, evaluations


def check_daily_full_run_cap(runs_dir: Path, max_full_runs: int = 10) -> tuple[bool, int]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    today_prefix = datetime.now(UTC).strftime("%Y%m%d")
    full_runs_today = 0
    for f in runs_dir.glob(f"run_{today_prefix}*.json"):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            if payload.get("is_full_run", False):
                full_runs_today += 1
        except (OSError, ValueError):
            continue
    effective_max = int(os.environ.get("MAX_FULL_RUNS", str(max_full_runs)))
    return full_runs_today < effective_max, full_runs_today


def _infer_language(dname: str, tags: list[str], raw_eval: dict) -> str:
    joined = (" ".join([dname, *tags, json.dumps(raw_eval.get("scenario", {}))])).lower()
    low = dname.lower()
    if "_fr" in low or "-fr" in low or "french" in joined or "français" in joined or "francais" in joined:
        return "fr"
    if "_es" in low or "-es" in low or "spanish" in joined or "español" in joined or "espanol" in joined:
        return "es"
    return "en"


def load_eval_index(dev_dir: Path, id_prefix: str = DEFAULT_ID_PREFIX) -> dict[str, dict]:
    """display name -> {"ve_id", "topic", "language"}; <prefix>-nn follows index.json order."""
    path = dev_dir / "index.json"
    if not path.exists():
        return {}
    out = {}
    for pos, entry in enumerate(json.loads(path.read_text(encoding="utf-8")), 1):
        out[entry["name"]] = {
            "ve_id": entry.get("id") or f"{id_prefix}-{pos:02d}",
            "topic": entry.get("topic", ""),
            "language": entry.get("language", ""),
        }
    return out


def build_index_from_evaluations(evals, id_prefix: str = DEFAULT_ID_PREFIX) -> list[dict]:
    """Stable short ids for evaluations without an index.json: sorted by display name."""
    entries = []
    for ev in sorted(evals, key=lambda e: str(_field(e, "display_name", "") or "")):
        dname = str(_field(ev, "display_name", "") or "")
        if not dname:
            continue
        tags = [str(t) for t in (_field(ev, "tags", []) or [])]
        entries.append(
            {
                "name": dname,
                "topic": tags[0] if tags else "",
                "language": _infer_language(dname, tags, {}),
            }
        )
    for pos, entry in enumerate(entries, 1):
        entry["id"] = f"{id_prefix}-{pos:02d}"
    return entries


def write_eval_index(dev_dir: Path, entries: list[dict]) -> Path:
    dev_dir.mkdir(parents=True, exist_ok=True)
    path = dev_dir / "index.json"
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _expand_tokens(spec: str) -> list[str]:
    """Comma-separated tokens; `@path` tokens are replaced by the ids listed in that file."""
    tokens: list[str] = []
    for token in (spec or "").split(","):
        token = token.strip()
        if not token:
            continue
        if token.startswith("@"):
            path = Path(token[1:])
            if not path.is_absolute():
                path = REPO_ROOT / path
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    tokens.extend(t.strip() for t in line.split(",") if t.strip())
            continue
        tokens.append(token)
    return tokens


def select_evals(spec: str | None, index: dict[str, dict]) -> set[str] | None:
    """--evals accepts short ids (VE-07), display names or @file lists; None means all."""
    tokens = _expand_tokens(spec or "")
    if not tokens or (len(tokens) == 1 and tokens[0].lower() == "all"):
        return None
    by_id = {meta["ve_id"].lower(): name for name, meta in index.items()}
    return {by_id.get(token.lower(), token) for token in tokens}


# ---------------------------------------------------------------------------- app + sync


def find_app(cloud: Cloud, project: str, region: str, agent_id: str):
    """Locate the app by display name or id under projects/<project>/locations/<region>."""
    parent = f"projects/{project}/locations/{region}"
    apps = cloud.list_pages(
        "AgentService.list_apps",
        parent,
        "bench: locate the target app",
        lambda token: cloud.apps.client.list_apps(
            request=_ces_types().ListAppsRequest(parent=parent, page_token=token)
        ),
        "apps",
    )
    for app in apps:
        if app.display_name == agent_id or app.name.split("/")[-1] == agent_id:
            cloud.bind_app(app.name)
            return app
    return None


def get_app(cloud: Cloud, app_name: str, notes: str):
    """One logged get_app; also used for the concurrent-push guard (update_time)."""
    app = cloud.call(
        "READ",
        "AgentService.get_app",
        app_name,
        notes,
        lambda: cloud.apps.client.get_app(request=_ces_types().GetAppRequest(name=app_name)),
        describe=lambda a: f"update_time={_field(a, 'update_time', '')}",
    )
    cloud.bind_app(app.name)
    return app


def list_all_evaluations(cloud: Cloud, app_name: str, notes: str) -> list:
    return cloud.list_pages(
        "EvaluationService.list_evaluations",
        app_name,
        notes,
        lambda token: cloud.evals.client.list_evaluations(
            request=_ces_types().ListEvaluationsRequest(parent=app_name, page_token=token)
        ),
        "evaluations",
    )


def build_evals_map(evals) -> dict[str, dict[str, str]]:
    """Same shape as SCRAPI's get_evaluations_map(reverse=True)."""
    out: dict[str, dict[str, str]] = {"goldens": {}, "scenarios": {}}
    for ev in evals:
        if not (ev.display_name and ev.name):
            continue
        if getattr(ev, "golden", None):
            out["goldens"][ev.display_name] = ev.name
        elif getattr(ev, "scenario", None):
            out["scenarios"][ev.display_name] = ev.name
    return out


def sync_bench(cloud: Cloud, app_name: str, expectations: list[dict], evaluations: list[dict],
               index: dict[str, dict], types_mod=None, parse_dict=None):
    """Make sure every bundle expectation/evaluation exists on the app; return name -> Evaluation.

    With an empty bundle this only lists the app's evaluations (one logged listing).
    """
    exp_map: dict[str, str] = {}
    if expectations:
        listed_exps = cloud.list_pages(
            "EvaluationService.list_evaluation_expectations",
            app_name,
            "bench: list expectations before sync",
            lambda token: cloud.evals.client.list_evaluation_expectations(
                request=_ces_types().ListEvaluationExpectationsRequest(parent=app_name, page_token=token)
            ),
            "evaluation_expectations",
        )
        exp_map = {e.display_name: e.name for e in listed_exps}
        for pos, data in enumerate(expectations, 1):
            dname = data["displayName"]
            if dname in exp_map:
                continue
            proto = types_mod.EvaluationExpectation(
                display_name=dname,
                tags=data.get("tags", []),
                llm_criteria=types_mod.EvaluationExpectation.LlmCriteria(
                    prompt=(data.get("llmCriteria") or {}).get("prompt", "")
                ),
            )
            created = cloud.call(
                "WRITE",
                "Evaluations.create_evaluation_expectation",
                app_name,
                f"bench: create missing expectation file #{pos}",
                lambda proto=proto: cloud.evals.create_evaluation_expectation(
                    evaluation_expectation=proto, app_name=app_name
                ),
                describe=lambda c: f"created {c.name}",
                write=True,
            )
            exp_map[dname] = created.name

    listed = list_all_evaluations(cloud, app_name, "bench: list evaluations before sync")
    existing = {ev.display_name: ev for ev in listed}
    eval_by_name = {} if evaluations else dict(existing)
    for raw in evaluations:
        data = json.loads(json.dumps(raw))
        dname = data["displayName"]
        ve_id = index.get(dname, {}).get("ve_id", "VE-??")
        if isinstance(data.get("scenario"), dict):
            refs = data["scenario"].get("evaluationExpectations", [])
            data["scenario"]["evaluationExpectations"] = [exp_map.get(ref, ref) for ref in refs]
        for se in data.get("scenarioExpectations", []):
            if se.get("expectation", "") in exp_map:
                se["expectation"] = exp_map[se["expectation"]]
        for turn in (data.get("golden") or {}).get("turns", []):
            for step in turn.get("steps", []):
                ref = (step.get("expectation") or {}).get("expectation", "")
                if ref in exp_map:
                    step["expectation"]["expectation"] = exp_map[ref]

        if dname in existing:
            ex_ev = existing[dname]
            ex_refs = list(getattr(ex_ev.scenario, "evaluation_expectations", []) or [])
            if all(r.startswith("projects/") for r in ex_refs):
                eval_by_name[dname] = ex_ev
                continue
            data["name"] = ex_ev.name
            proto = types_mod.Evaluation()
            parse_dict(data, proto._pb, ignore_unknown_fields=True)
            eval_by_name[dname] = cloud.call(
                "WRITE",
                "Evaluations.update_evaluation",
                ex_ev.name,
                f"bench: relink expectation resource names on {ve_id}",
                lambda proto=proto: cloud.evals.update_evaluation(evaluation=proto, app_name=app_name),
                describe=lambda u: f"updated {u.name}",
                write=True,
            )
            continue

        data.pop("name", None)
        proto = types_mod.Evaluation()
        parse_dict(data, proto._pb, ignore_unknown_fields=True)
        eval_by_name[dname] = cloud.call(
            "WRITE",
            "Evaluations.create_evaluation",
            app_name,
            f"bench: create missing {ve_id}",
            lambda proto=proto: cloud.evals.create_evaluation(evaluation=proto, app_name=app_name),
            describe=lambda c: f"created {c.name}",
            write=True,
        )

    # SCRAPI's run_evaluation resolves names through a cached evals map and would otherwise fill
    # it with its own (unlogged) list_evaluations call; seed the cache from the logged listing.
    known = {ev.name: ev for ev in listed}
    known.update({ev.name: ev for ev in eval_by_name.values()})
    cloud.evals.evals_map = build_evals_map(known.values())
    return exp_map, eval_by_name


# ------------------------------------------------------------------------- run + fetch


def _operation_name(op) -> str:
    return str(getattr(getattr(op, "operation", None), "name", "") or "")


def _run_name_from_metadata(op) -> str:
    try:
        meta = getattr(op, "metadata", None)
        return str(getattr(meta, "evaluation_run", "") or "") if meta else ""
    except (AttributeError, RuntimeError, ValueError, TypeError):
        return ""


def _describe_result(res) -> str:
    return (
        f"execution_state={_enum_name(_field(res, 'execution_state'), EXECUTION_STATES)}, "
        f"evaluation_status={_enum_name(_field(res, 'evaluation_status'), OUTCOMES)}"
    )


def wait_for_run(cloud: Cloud, run_name: str, label: str):
    """Poll get_evaluation_run (one logged row per poll) until the run ends."""
    started = time.monotonic()
    poll = 0
    while True:
        poll += 1
        run = cloud.call(
            "READ",
            "Evaluations.get_evaluation_run",
            run_name,
            f"{label}: poll #{poll}",
            lambda: cloud.evals.get_evaluation_run(run_name),
            describe=lambda r: (
                f"state={_enum_name(r.state, RUN_STATES)}, results={len(r.evaluation_results)}"
            ),
        )
        state = _enum_name(run.state, RUN_STATES)
        if state in RUN_TERMINAL_STATES:
            return run
        if time.monotonic() - started > RUN_TIMEOUT_S:
            raise TimeoutError(f"{label}: {run_name} still {state} after {RUN_TIMEOUT_S}s")
        cloud.sleep(POLL_INTERVAL_S)


def fetch_run_results(cloud: Cloud, run, label: str) -> list[dict]:
    """One logged get_evaluation_result per result of the run (judge reasoning included)."""
    names = list(run.evaluation_results)
    results = []
    for pos, result_name in enumerate(names, 1):
        res = cloud.call(
            "READ",
            "Evaluations.get_evaluation_result",
            result_name,
            f"{label}: result {pos}/{len(names)}",
            lambda result_name=result_name: cloud.evals.get_evaluation_result(result_name),
            describe=_describe_result,
        )
        results.append(to_plain(res))
    return results


def _save_raw(raw_dir: Path, run_name: str, payload: dict) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{run_name.rsplit('/', 1)[-1]}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def wait_for_run_name(cloud: Cloud, op, label: str, app_name: str) -> str:
    """Return the evaluation run named by a run_evaluation operation (one row per poll)."""
    run_name = _run_name_from_metadata(op)
    started = time.monotonic()
    poll = 0
    while not run_name:
        poll += 1
        done = cloud.call(
            "READ",
            "Operations.get_operation (Operation.done)",
            _operation_name(op) or app_name,
            f"{label}: operation poll #{poll}",
            op.done,
            describe=lambda d: f"done={d}, evaluation_run={_run_name_from_metadata(op) or 'not yet'}",
        )
        run_name = _run_name_from_metadata(op)
        if run_name:
            break
        if done:
            run_name = str(getattr(op.result(), "evaluation_run", "") or "")
            break
        if time.monotonic() - started > RUN_TIMEOUT_S:
            raise TimeoutError(f"{label}: operation still running after {RUN_TIMEOUT_S}s")
        cloud.sleep(POLL_INTERVAL_S)
    if not run_name:
        raise RuntimeError(f"{label}: the platform returned no evaluation run name")
    return run_name


def run_and_fetch(cloud: Cloud, app_name: str, eval_names: list[str], run_count: int, label: str,
                  raw_dir: Path, resume_run_name: str | None = None, modality: str = "text"):
    """Start one evaluation run, poll it to the end and fetch every result; every call is logged.

    With `resume_run_name` no new run is started: the existing run is polled and read (READ only).
    """
    if resume_run_name:
        run_name = resume_run_name
    else:
        op = cloud.call(
            "WRITE",
            "Evaluations.run_evaluation",
            app_name,
            f"{label}: {len(eval_names)} evals, modality={modality}, run_count={run_count}",
            lambda: cloud.evals.run_evaluation(
                evaluations=list(eval_names), app_name=app_name, modality=modality, run_count=run_count
            ),
            describe=lambda o: (
                f"operation={_operation_name(o) or 'unnamed'}, "
                f"evaluation_run={_run_name_from_metadata(o) or 'not in metadata'}"
            ),
            write=True,
        )
        run_name = wait_for_run_name(cloud, op, label, app_name)
    run = wait_for_run(cloud, run_name, label)
    results = fetch_run_results(cloud, run, label)
    _save_raw(
        raw_dir,
        run_name,
        {
            "label": label,
            "evaluation_run": run_name,
            "run_count": run_count,
            "modality": modality,
            "evaluations": list(eval_names),
            "resumed": bool(resume_run_name),
            "run": to_plain(run),
            "results": results,
        },
    )
    return run_name, run, results


# --------------------------------------------------------------- records + classification


def extract_result_efficiency(
    raw: dict | None,
    conversation: dict | None = None,
    tool_calls: list[dict] | None = None,
) -> tuple[int, int]:
    """Return (turns, tool_call_count) for one EvaluationResult without requiring get_conversation."""
    raw = raw or {}
    scenario = raw.get("scenario_result") or {}
    golden = raw.get("golden_result") or {}

    turns = 0
    if isinstance(conversation, dict) and isinstance(conversation.get("turns"), list) and conversation["turns"]:
        turns = len(conversation["turns"])
    elif isinstance(scenario.get("hallucination_result"), list) and scenario["hallucination_result"]:
        turns = len(scenario["hallucination_result"])
    elif isinstance(golden.get("turn_replay_results"), list) and golden["turn_replay_results"]:
        turns = len(golden["turn_replay_results"])

    tool_call_count = 0
    if isinstance(scenario.get("tool_call_latencies"), list) and scenario["tool_call_latencies"]:
        tool_call_count = len(scenario["tool_call_latencies"])
    elif isinstance(golden.get("turn_replay_results"), list) and golden["turn_replay_results"]:
        tool_call_count = sum(
            len(tr.get("tool_call_latencies") or [])
            for tr in golden["turn_replay_results"]
            if isinstance(tr, dict)
        )
    elif tool_calls:
        direct = [tc for tc in tool_calls if tc.get("type") in ("tool_call", "toolCall")]
        tool_call_count = len(direct) if direct else len(tool_calls)

    return turns, tool_call_count


def build_records(results: list[dict], display_of: dict[str, str], index: dict[str, dict],
                  round_no: int, run_name: str) -> list[dict]:
    """One record per result; slot = position among that eval's results in this run."""
    records = []
    seen: dict[str, int] = defaultdict(int)
    ordered = sorted(results, key=lambda r: (str(r.get("create_time", "")), str(r.get("name", ""))))
    for res in ordered:
        eval_res = "/".join(str(res.get("name", "")).split("/")[:-2])
        dname = display_of.get(eval_res, "")
        meta = index.get(dname, {})
        seen[eval_res] += 1
        scenario = res.get("scenario_result") or {}
        turns, tool_call_count = extract_result_efficiency(res)
        records.append(
            {
                "ve_id": meta.get("ve_id", "VE-??"),
                "display_name": dname,
                "topic": meta.get("topic", ""),
                "language": meta.get("language", ""),
                "evaluation": eval_res,
                "result": str(res.get("name", "")),
                "evaluation_run": str(res.get("evaluation_run") or run_name),
                "round": round_no,
                "slot": seen[eval_res],
                "execution_state": _enum_name(res.get("execution_state"), EXECUTION_STATES),
                "evaluation_status": _enum_name(res.get("evaluation_status"), OUTCOMES),
                "conversation_name": str(scenario.get("conversation", "") or ""),
                "conversation": None,
                "conversation_error": "",
                "transcript": [],
                "tool_calls": [],
                "turns": turns,
                "tool_call_count": tool_call_count,
                "fallback_reasons": [],
                "classification": "",
                "classification_reason": "",
                "raw": res,
            }
        )
    return records


def _walk_spans(span):
    if not isinstance(span, dict):
        return
    yield span
    for child in span.get("child_spans", []) or []:
        yield from _walk_spans(child)


def conversation_digest(conv: dict) -> tuple[list[str], list[dict], list[dict]]:
    """Readable transcript lines, tool calls/responses and span fallback reasons of one conversation."""
    lines: list[str] = []
    tools: list[dict] = []
    fallbacks: list[dict] = []
    tool_keys = ("tool_call", "tool_response", "toolCall", "toolResponse", "agent_transfer", "agentTransfer")
    for t_idx, turn in enumerate((conv or {}).get("turns", []) or [], 1):
        for msg in turn.get("messages", []) or []:
            role = msg.get("role", "?")
            for chunk in msg.get("chunks", []) or []:
                if chunk.get("text"):
                    lines.append(f"[turn {t_idx}] {role}: {chunk['text']}")
                for key in tool_keys:
                    if chunk.get(key):
                        tools.append({"turn": t_idx, "role": role, "type": key, "payload": chunk[key]})
                        lines.append(
                            f"[turn {t_idx}] {role}: <{key}> "
                            f"{json.dumps(chunk[key], ensure_ascii=False, default=str)}"
                        )
        for span in _walk_spans(turn.get("root_span")):
            attrs = span.get("attributes") or {}
            reason = attrs.get("fallback reason")
            if reason:
                fallbacks.append({"turn": t_idx, "span": span.get("name", ""), "reason": str(reason)})
            if "tool" in str(span.get("name", "")).lower():
                tools.append({"turn": t_idx, "type": "span", "name": span.get("name", ""), "attributes": attrs})
    return lines, tools, fallbacks


def classify(record: dict) -> tuple[str, str]:
    """(PASS | FAIL | INFRA, reason). Only a completed, judged result can pass or fail."""
    state, status = record["execution_state"], record["evaluation_status"]
    if state != "COMPLETED":
        return "INFRA", f"execution_state={state}"
    if status == "PASS":
        return "PASS", ""
    if status != "FAIL":
        return "INFRA", f"not scored (evaluation_status={status})"
    infra = [f["reason"] for f in record.get("fallback_reasons", []) if INFRA_PATTERN.search(f["reason"])]
    if infra:
        return "INFRA", f"platform fallback: {infra[0][:300]}"
    return "FAIL", ""


def _response_envelope(payload: dict) -> dict:
    """The tool's own {status, data | error, ...} envelope inside a recorded tool_response."""
    res = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(res, dict):
        return {}
    inner = res.get("result")
    return inner if isinstance(inner, dict) else res


def tool_errors(tool_calls: list[dict]) -> list[dict]:
    """Every recorded tool response whose envelope says error (business-rule errors marked as such)."""
    out = []
    for tc in tool_calls or []:
        if tc.get("type") not in ("tool_response", "toolResponse"):
            continue
        payload = tc.get("payload") or {}
        env = _response_envelope(payload)
        if env.get("status") != "error" and not env.get("error"):
            continue
        code = str(env.get("error") or env.get("status") or "error")
        out.append(
            {
                "turn": tc.get("turn"),
                "tool": str(payload.get("display_name") or payload.get("tool") or "").rsplit("/", 1)[-1],
                "error": code,
                "business_rule": code in BUSINESS_ERROR_CODES,
                "message": str(env.get("message") or "")[:200],
            }
        )
    return out


def attach_conversations(cloud: Cloud, records: list[dict], label: str, all_results: bool = False) -> None:
    """Fetch the conversation of every non-passing result (one logged call each), then classify all.

    With `all_results` (Gate 1 smoke runs) passing results are fetched too, because the gate rule
    "no conversation has a tool error" must be checked on every conversation.
    """
    todo = [
        r for r in records
        if all_results or not (r["execution_state"] == "COMPLETED" and r["evaluation_status"] == "PASS")
    ]
    what = "result" if all_results else "non-passing result"
    for pos, rec in enumerate(todo, 1):
        name = rec["conversation_name"]
        if not name:
            rec["conversation_error"] = "the result has no conversation reference"
            continue
        try:
            conv = cloud.call(
                "READ",
                "ConversationHistory.get_conversation",
                name,
                f"{label}: conversation of {what} {pos}/{len(todo)} ({rec['ve_id']})",
                lambda name=name: cloud.history.get_conversation(name),
                describe=lambda c: f"{len(_field(c, 'turns') or [])} turns",
            )
        except (ReauthRequired, cloud_log.CloudLogError):
            raise
        except (GoogleAPIError, RuntimeError, ValueError, TypeError, OSError) as exc:
            rec["conversation_error"] = f"{type(exc).__name__}: {exc}"  # kept as evidence
            continue
        rec["conversation"] = to_plain(conv)
        rec["transcript"], rec["tool_calls"], rec["fallback_reasons"] = conversation_digest(rec["conversation"])
        rec["turns"], rec["tool_call_count"] = extract_result_efficiency(
            rec.get("raw"), rec["conversation"], rec["tool_calls"]
        )
    for rec in records:
        rec["classification"], rec["classification_reason"] = classify(rec)


def scored_statuses(records: list[dict], runs: int) -> list[str]:
    ordered = sorted(records, key=lambda r: (r["round"], r["evaluation_run"], r["slot"]))
    return [r["classification"] for r in ordered if r["classification"] in ("PASS", "FAIL")][:runs]


def slots_needed(records: list[dict], eval_names: list[str], runs: int) -> dict[str, int]:
    """evaluation resource -> number of results still missing a PASS/FAIL score."""
    by_eval = defaultdict(list)
    for rec in records:
        by_eval[rec["evaluation"]].append(rec)
    need = {}
    for name in eval_names:
        missing = runs - len(scored_statuses(by_eval.get(name, []), runs))
        if missing > 0:
            need[name] = missing
    return need


def eval_outcome(dname: str, eval_res: str, records: list[dict], index: dict[str, dict], runs: int) -> dict:
    meta = index.get(dname, {})
    statuses = scored_statuses(records, runs)
    passes, fails = statuses.count("PASS"), statuses.count("FAIL")
    majority = runs // 2 + 1
    verdict = "PASS" if passes >= majority else "FAIL" if fails >= majority else "INCONCLUSIVE"
    ordered = sorted(records, key=lambda r: (r["round"], r["evaluation_run"], r["slot"]))
    scored_recs = [r for r in ordered if r["classification"] in ("PASS", "FAIL")][:runs]
    pass_recs = [r for r in scored_recs if r["classification"] == "PASS"]
    pass_turns = [int(r.get("turns") or 0) for r in pass_recs if int(r.get("turns") or 0) > 0]
    pass_tools = [int(r.get("tool_call_count") or 0) for r in pass_recs]
    avg_pass_turns = round(sum(pass_turns) / len(pass_turns), 2) if pass_turns else None
    avg_pass_tool_calls = round(sum(pass_tools) / len(pass_tools), 2) if pass_tools else None
    return {
        "ve_id": meta.get("ve_id", "VE-??"),
        "display_name": dname,
        "evaluation_name": eval_res,
        "topic": meta.get("topic", ""),
        "language": meta.get("language", ""),
        "verdict": verdict,
        "passed": verdict == "PASS",
        "pass_runs": passes,
        "fail_runs": fails,
        "total_runs": len(statuses),
        "infra_runs": sum(1 for r in ordered if r["classification"] == "INFRA"),
        "avg_pass_turns": avg_pass_turns,
        "avg_pass_tool_calls": avg_pass_tool_calls,
        "per_run_statuses": statuses,
        "pattern": [
            {
                "run": r["evaluation_run"].rsplit("/", 1)[-1],
                "round": r["round"],
                "slot": r["slot"],
                "classification": r["classification"],
                "reason": r["classification_reason"],
                "turns": int(r.get("turns") or 0),
                "tool_call_count": int(r.get("tool_call_count") or 0),
            }
            for r in ordered
        ],
        "raw_runs": [r["raw"] for r in ordered],
    }


def summarize(outcomes: list[dict]) -> tuple[dict, dict]:
    def bucket():
        return {"passed": 0, "failed": 0, "inconclusive": 0, "total": 0}

    by_language: dict[str, dict] = defaultdict(bucket)
    by_topic: dict[str, dict] = defaultdict(bucket)
    for o in outcomes:
        key = {"PASS": "passed", "FAIL": "failed"}.get(o["verdict"], "inconclusive")
        for table, name in ((by_language, o["language"]), (by_topic, o["topic"])):
            table[name][key] += 1
            table[name]["total"] += 1
    return dict(sorted(by_language.items())), dict(sorted(by_topic.items()))


def compare_with_reference(outcomes: list[dict], reference: dict) -> dict:
    """Regressions (reference passed, now not PASS) and newly passing (reference failed, now PASS)."""
    ref = {r["display_name"]: r for r in reference.get("results", [])}
    regressions, newly_passing, missing = [], [], []
    for o in outcomes:
        old = ref.get(o["display_name"])
        if old is None:
            missing.append(o["ve_id"])
            continue
        entry = {
            "ve_id": o["ve_id"],
            "display_name": o["display_name"],
            "reference": f"{old.get('pass_runs', '?')}/{old.get('total_runs', '?')}",
            "now": f"{o['pass_runs']}/{o['total_runs']}",
            "now_verdict": o["verdict"],
        }
        if old.get("passed") and o["verdict"] != "PASS":
            regressions.append(entry)
        elif not old.get("passed") and o["verdict"] == "PASS":
            newly_passing.append(entry)
    return {
        "reference_runs": reference.get("evaluation_runs", []),
        "reference_passed": sum(1 for r in ref.values() if r.get("passed")),
        "reference_total": len(ref),
        "regressions": regressions,
        "newly_passing": newly_passing,
        "not_in_reference": missing,
    }


# ------------------------------------------------------------------------- evidence files


def _has_judge_text(judge: dict) -> bool:
    items = list(judge.get("evaluation_expectation_results") or [])
    items += list(judge.get("hallucination_result") or [])
    items.append(judge.get("user_goal_satisfaction_result") or {})
    return any(str((i or {}).get("explanation", "")).strip() for i in items)


def _render_failing_run_md(p: dict) -> str:
    judge = p["judge"]
    out = [
        f"# {p['ve_id']} ({p['display_name']}) — {p['classification']}",
        "",
        f"- Evaluation run: `{p['evaluation_run']}` (round {p['round']}, slot {p['slot']})",
        f"- Result: `{p['result']}`",
        f"- Evaluation: `{p['evaluation']}`",
        f"- execution_state={p['execution_state']}, evaluation_status={p['evaluation_status']}",
        f"- Classification: {p['classification']} {p['classification_reason']}".rstrip(),
        f"- Missing: {', '.join(p['missing']) or 'nothing'}",
        "",
        "## Judge reasoning",
        "",
    ]
    for er in judge.get("evaluation_expectation_results") or []:
        outcome = _enum_name(er.get("outcome"), OUTCOMES)
        out.append(f"- Expectation [{outcome}] {er.get('prompt', '')}")
        out.append(f"  - {str(er.get('explanation', '')).strip()}")
    goal = judge.get("user_goal_satisfaction_result") or {}
    if goal:
        out.append(
            f"- User goal: {goal.get('label', '')} (score {goal.get('score', '')}): "
            f"{str(goal.get('explanation', '')).strip()}"
        )
    for hr in judge.get("hallucination_result") or []:
        out.append(
            f"- Hallucination: {hr.get('label', '')} (score {hr.get('score', '')}): "
            f"{str(hr.get('explanation', '')).strip()}"
        )
    out.append(
        f"- task_completed={judge.get('task_completed')}, "
        f"all_expectations_satisfied={judge.get('all_expectations_satisfied')}"
    )
    out += ["", "## Platform fallback reasons", ""]
    out += [f"- turn {f['turn']} ({f['span']}): {f['reason']}" for f in p["fallback_reasons"]]
    if not p["fallback_reasons"]:
        out.append("- none")
    out += ["", f"## Tool calls ({len(p['tool_calls'])})", "", "```json"]
    out.append(json.dumps(p["tool_calls"], indent=2, ensure_ascii=False, default=str))
    out += ["```", "", "## Transcript", ""]
    out += p["transcript"] or ["(no transcript)"]
    return "\n".join(out) + "\n"


def write_failing_runs(records: list[dict], out_dir: Path, title: str) -> list[dict]:
    """Save every non-passing result (json + md) and an index.md; return the inventory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    inventory = []
    failing = sorted(
        (r for r in records if r["classification"] != "PASS"),
        key=lambda r: (r["ve_id"], r["round"], r["evaluation_run"], r["slot"]),
    )
    for rec in failing:
        run_id = rec["evaluation_run"].rsplit("/", 1)[-1]
        stem = f"{rec['ve_id']}__{run_id[:8]}__r{rec['slot']}"
        scenario = rec["raw"].get("scenario_result") or {}
        judge = {k: scenario.get(k) for k in JUDGE_KEYS}
        missing = []
        if rec["conversation"] is None:
            missing.append(f"conversation ({rec['conversation_error'] or 'not fetched'})")
        if not _has_judge_text(judge):
            missing.append("judge reasoning (no explanation text in the result)")
        payload = {
            key: rec[key]
            for key in (
                "ve_id", "display_name", "topic", "language", "classification", "classification_reason",
                "evaluation", "evaluation_run", "result", "round", "slot", "execution_state",
                "evaluation_status", "conversation_name", "fallback_reasons", "tool_calls", "transcript",
                "conversation",
            )
        }
        payload["judge"] = judge
        payload["missing"] = missing
        payload["result_raw"] = rec["raw"]
        json_path = out_dir / f"{stem}.json"
        md_path = out_dir / f"{stem}.md"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        md_path.write_text(_render_failing_run_md(payload), encoding="utf-8")
        inventory.append(
            {
                "ve_id": rec["ve_id"],
                "display_name": rec["display_name"],
                "classification": rec["classification"],
                "evaluation_run": rec["evaluation_run"],
                "slot": rec["slot"],
                "turns": len((rec["conversation"] or {}).get("turns", []) or []),
                "tool_calls": len(rec["tool_calls"]),
                "fallback_reasons": len(rec["fallback_reasons"]),
                "missing": missing,
                "json": str(json_path),
                "md": str(md_path),
            }
        )
    lines = [
        f"# Non-passing results — {title}",
        "",
        (
            f"Written {_now_iso()} by scripts/run_bench.py. One json (full result, judge reasoning, "
            "full conversation, tool calls, fallback reasons) and one md per result."
        ),
        "",
        f"{len(inventory)} non-passing results; {sum(1 for i in inventory if i['missing'])} with something missing.",
        "",
        "| Id | Eval | Class | Run | Slot | Turns | Tool calls | Fallbacks | Missing | File |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i in inventory:
        lines.append(
            f"| {i['ve_id']} | {i['display_name']} | {i['classification']} | "
            f"{i['evaluation_run'].rsplit('/', 1)[-1]} | {i['slot']} | {i['turns']} | "
            f"{i['tool_calls']} | {i['fallback_reasons']} | {'; '.join(i['missing']) or '—'} | "
            f"{Path(i['md']).name} |"
        )
    (out_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return inventory


def _md_table(title: str, table: dict) -> list[str]:
    out = [f"## {title}", "", "| Group | Passed | Failed | Inconclusive | Total |", "|---|---|---|---|---|"]
    for name, v in table.items():
        out.append(f"| {name} | {v['passed']} | {v['failed']} | {v['inconclusive']} | {v['total']} |")
    return out + [""]


def compute_smoke_gate(records: list[dict], outcomes: list[dict]) -> dict:
    """Gate 1: per-eval judge metrics and tool errors across all smoke conversations."""
    per_eval = {}
    all_tool_errors = []
    for o in outcomes:
        ve = o["ve_id"]
        eval_recs = [
            r for r in sorted(records, key=lambda r: (r["round"], r["evaluation_run"], r["slot"]))
            if r["evaluation"] == o["evaluation_name"] and r["classification"] in ("PASS", "FAIL")
        ][: o["total_runs"]]
        exp_passes: dict[str, int] = defaultdict(int)
        exp_totals: dict[str, int] = defaultdict(int)
        goal_passes = 0
        halluc_passes = 0
        conv_rows = []
        for r in eval_recs:
            scenario = (r.get("raw") or {}).get("scenario_result") or {}
            exps = scenario.get("evaluation_expectation_results") or []
            exp_summary = []
            for er in exps:
                prompt = str(er.get("prompt") or "")
                out_name = _enum_name(er.get("outcome"), OUTCOMES)
                exp_totals[prompt] += 1
                if out_name == "PASS":
                    exp_passes[prompt] += 1
                exp_summary.append(f"{out_name}:{prompt[:40]}")
            goal = scenario.get("user_goal_satisfaction_result") or {}
            g_ok = goal.get("score") != 0
            if g_ok:
                goal_passes += 1
            hallucs = scenario.get("hallucination_result") or []
            if isinstance(hallucs, dict):
                hallucs = [hallucs]
            h_ok = not any(isinstance(h, dict) and h.get("score") == 0 for h in hallucs)
            if h_ok:
                halluc_passes += 1
            errs = tool_errors(r.get("tool_calls") or [])
            bad_errs = [e for e in errs if not e["business_rule"]]
            for e in bad_errs:
                all_tool_errors.append({"ve_id": ve, "slot": r["slot"], **e})
            conv_rows.append(
                {
                    "slot": r["slot"],
                    "classification": r["classification"],
                    "expectations": exp_summary,
                    "user_goal_ok": g_ok,
                    "hallucination_ok": h_ok,
                    "tool_errors": bad_errs,
                }
            )
        n = len(eval_recs)
        threshold = max(1, (2 * n + 2) // 3) if n else 2
        any_exp_go = any(p >= threshold for p in exp_passes.values())
        verdict_go = o["pass_runs"] >= threshold
        eval_go = (verdict_go or any_exp_go) and not any(c["tool_errors"] for c in conv_rows)
        per_eval[ve] = {
            "pass_runs": o["pass_runs"],
            "total_runs": n,
            "threshold": threshold,
            "expectations": {k: f"{exp_passes[k]}/{exp_totals[k]}" for k in sorted(exp_totals)},
            "user_goal": f"{goal_passes}/{n}",
            "hallucination": f"{halluc_passes}/{n}",
            "conversations": conv_rows,
            "eval_go": eval_go,
        }
    gate_verdict = (
        "go" if per_eval and all(v["eval_go"] for v in per_eval.values()) and not all_tool_errors else "stop"
    )
    return {"gate_verdict": gate_verdict, "unexpected_tool_errors": all_tool_errors, "per_eval": per_eval}


def render_report_md(payload: dict) -> str:
    out = []
    if payload.get("is_smoke_run"):
        out += [
            "> **GATE 1 SMOKE RUN (stop-only): never a keep, never progress, never committed to `history/bench/`.**",
            "",
        ]
    total_ev = payload["total_evaluations"]
    strict_pass = payload.get("strict_pass", 0)
    strict_pct = payload.get("strict_pass_rate", 0.0) * 100
    maj_pass = payload.get("majority_pass", payload["passed_evaluations"])
    maj_pct = payload.get("majority_pass_rate", payload.get("pass_rate", 0.0)) * 100
    ind_p = payload.get("individual_passed", 0)
    ind_t = payload.get("individual_total", 0)
    p_val = payload.get("p", 0.0)
    pred_strict = payload.get("predicted_strict_3_of_3", 0.0)
    out += [
        f"# Benchmark — {payload['label']} ({payload['timestamp']})",
        "",
        f"- App: `{payload['app_resource']}`",
        f"- Modality: {payload.get('modality', 'text')}",
        f"- Full visible run: {payload['is_full_run']}"
        + (f" (#{payload['full_run_number_today']} today)" if payload.get("full_run_number_today") else ""),
        f"- Runs per eval: {payload['runs_per_eval']}; verdict = majority of scored results",
        (
            f"- Headline: **strict 3/3: {strict_pass}/{total_ev} ({strict_pct:.1f}%)** | "
            f"majority >=2/3: {maj_pass}/{total_ev} ({maj_pct:.1f}%) | "
            f"individual: {ind_p}/{ind_t} (p={p_val:.3f}, N*p^3={pred_strict:.1f})"
        ),
        (
            f"- Result: **{payload['passed_evaluations']}/{payload['total_evaluations']} PASS**, "
            f"{payload['failed_evaluations']} FAIL, {payload['inconclusive_evaluations']} INCONCLUSIVE"
        ),
        (
            f"- Efficiency (passing runs only): avg turns = `{payload.get('avg_pass_turns') or '—'}`, "
            f"avg tool calls = `{payload.get('avg_pass_tool_calls') or '—'}`"
        ),
        f"- App versions seen in results: {payload['app_versions_seen']}",
    ]
    if payload.get("app_update_time_changed"):
        out.append("- **WARNING: the app's update_time changed during this run (another push?). Treat as invalid.**")
    out.append("")
    smoke = payload.get("smoke_gate")
    if smoke:
        out += [
            f"## Gate 1 check — **GATE 1: {smoke['gate_verdict']}**",
            "",
            f"- Unexpected tool errors across all conversations: **{len(smoke['unexpected_tool_errors'])}**",
            "",
            "| Id | Verdict passes | Expectations | User goal | Hallucination | Tool errors | Eval gate |",
            "|---|---|---|---|---|---|---|",
        ]
        for ve, info in sorted(smoke["per_eval"].items()):
            exps_txt = "; ".join(f"{k[:35]}: {v}" for k, v in info["expectations"].items()) or "—"
            err_cnt = sum(len(c["tool_errors"]) for c in info["conversations"])
            out.append(
                f"| {ve} | {info['pass_runs']}/{info['total_runs']} | {exps_txt} | "
                f"{info['user_goal']} | {info['hallucination']} | {err_cnt} | "
                f"{'GO' if info['eval_go'] else 'STOP'} |"
            )
        out.append("")
    out += ["## Evaluation runs", "", "| Label | Run | run_count | Evals | State |", "|---|---|---|---|---|"]
    for r in payload["evaluation_run_details"]:
        out.append(f"| {r['label']} | `{r['evaluation_run']}` | {r['run_count']} | {r['evals']} | {r['state']} |")
    out.append("")
    out += _md_table("By language", payload["by_language"])
    out += _md_table("By topic", payload["by_topic"])
    out += [
        "## Per eval",
        "",
        "| Id | Eval | Topic | Lang | Scored runs | Passes | Avg pass turns | Avg pass tools | Infra re-runs | Verdict | Reference |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    ref = {r["display_name"]: r for r in (payload.get("reference_results") or [])}
    for o in payload["results"]:
        old = ref.get(o["display_name"])
        old_txt = (
            f"{'PASS' if old.get('passed') else 'FAIL'} {old.get('pass_runs')}/{old.get('total_runs')}" if old else "—"
        )
        t_txt = f"{o['avg_pass_turns']:.2f}" if o.get("avg_pass_turns") is not None else "—"
        tc_txt = f"{o['avg_pass_tool_calls']:.2f}" if o.get("avg_pass_tool_calls") is not None else "—"
        out.append(
            f"| {o['ve_id']} | {o['display_name']} | {o['topic']} | {o['language']} | "
            f"{' '.join(s[0] for s in o['per_run_statuses']) or '—'} | {o['pass_runs']}/{o['total_runs']} | "
            f"{t_txt} | {tc_txt} | {o['infra_runs']} | {o['verdict']} | {old_txt} |"
        )
    cmp_ = payload.get("comparison")
    if cmp_:
        out += [
            "",
            (
                f"## Compared with the reference ({cmp_['reference_passed']}/{cmp_['reference_total']}; "
                f"runs {', '.join(r.rsplit('/', 1)[-1] for r in cmp_['reference_runs'])})"
            ),
            "",
            f"Regressions ({len(cmp_['regressions'])}):",
        ]
        out += [
            f"- {e['ve_id']} ({e['display_name']}): {e['reference']} -> {e['now']} {e['now_verdict']}"
            for e in cmp_["regressions"]
        ] or ["- none"]
        out += ["", f"Newly passing ({len(cmp_['newly_passing'])}):"]
        out += [
            f"- {e['ve_id']} ({e['display_name']}): {e['reference']} -> {e['now']}" for e in cmp_["newly_passing"]
        ] or ["- none"]
    if payload.get("failing_runs_dir"):
        out += ["", f"Non-passing result data: `{payload['failing_runs_dir']}` (see index.md there)."]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------- the run


def resolve_app(cloud: Cloud, opts):
    """`--app <resource>` (one logged get_app) or `--project/--location/--agent-id` (list + match).

    If the last segment of `--app` is a display name rather than the app id (a common way to
    fill in environments/<env>.mk), the direct read fails and we fall back to the same
    list-and-match lookup `--agent-id` uses, so the canonical resource is used from then on.
    """
    if getattr(opts, "app", ""):
        try:
            return get_app(cloud, opts.app, "bench: read the target app (update_time baseline)")
        except Exception as exc:  # NOT_FOUND / 404 when the id is really a display name
            if not any(tok in str(exc).lower() for tok in ("not found", "404", "not_found", "invalid")):
                raise
            project, location = _parse_app_resource(opts.app)
            maybe_name = opts.app.rsplit("/", 1)[-1]
            app = find_app(cloud, project, location, maybe_name)
            if app is None:
                raise LookupError(f"app {opts.app!r} not found (neither as an id nor as a display name)") from exc
            print(f"note: resolved display name {maybe_name!r} to {app.name}", file=sys.stderr)
            opts.app = app.name
            return app
    if not (opts.project and opts.agent_id):
        raise LookupError("set --app projects/<p>/locations/<l>/apps/<id>, or --project and --agent-id")
    app = find_app(cloud, opts.project, opts.location, opts.agent_id)
    if app is None:
        raise LookupError(f"app {opts.agent_id!r} not found under projects/{opts.project}/locations/{opts.location}")
    return app


def run_bench(cloud: Cloud, opts, expectations: list[dict], evaluations: list[dict], index: dict[str, dict],
              raw_dir: Path, dev_dir: Path | None = None, full_run_no: int | None = None,
              types_mod=None, parse_dict=None) -> dict:
    """Resolve the app, sync the bundle, run in batches, re-run INFRA slots; return everything."""
    app = resolve_app(cloud, opts)
    app_name = app.name
    update_time_before = str(_field(app, "update_time", "") or "")
    _, eval_by_name = sync_bench(cloud, app_name, expectations, evaluations, index, types_mod, parse_dict)
    if not index and eval_by_name:
        entries = build_index_from_evaluations(eval_by_name.values(), opts.id_prefix)
        index.update(load_eval_index_entries(entries))
        if dev_dir is not None and not getattr(opts, "no_write_index", False):
            write_eval_index(dev_dir, entries)
    selected = select_evals(opts.evals, index)
    target = [(dname, ev) for dname, ev in sorted(eval_by_name.items()) if selected is None or dname in selected]
    if not target:
        raise LookupError("no matching evaluations selected to run")
    if selected is not None:
        unknown = sorted(selected - {dname for dname, _ in target})
        if unknown:
            raise LookupError(f"unknown evaluation id(s)/name(s): {', '.join(unknown)}")
    display_of = {ev.name: dname for dname, ev in eval_by_name.items()}
    kind = f"full visible run #{full_run_no} today" if full_run_no else "targeted run"
    batch_size = max(1, int(opts.batch_size))
    batches = [target[i : i + batch_size] for i in range(0, len(target), batch_size)]
    resume_run = str(getattr(opts, "resume_run", "") or "").strip()
    if resume_run and not resume_run.startswith("projects/"):
        resume_run = f"{app_name}/evaluationRuns/{resume_run}"
    if resume_run and len(batches) != 1:
        raise LookupError(
            "--resume-run continues one evaluation run, so it needs a single-batch "
            f"selection (<= {batch_size} evals); got {len(batches)} batches"
        )
    records: list[dict] = []
    run_details: list[dict] = []
    batch_lock = threading.Lock()
    is_smoke = bool(getattr(opts, "smoke", False))
    modality = getattr(opts, "modality", "text") or "text"

    def one_run(names: list[str], run_count: int, label: str, round_no: int, resume_run_name: str | None = None) -> None:
        run_name, run, results = run_and_fetch(
            cloud, app_name, names, run_count, label, raw_dir, resume_run_name, modality=modality
        )
        new = build_records(results, display_of, index, round_no, run_name)
        attach_conversations(cloud, new, label, all_results=is_smoke)
        with batch_lock:
            records.extend(new)
            run_details.append(
                {
                    "label": label,
                    "evaluation_run": run_name,
                    "run_count": run_count,
                    "evals": len(names),
                    "ve_ids": sorted(index.get(display_of.get(n, ""), {}).get("ve_id", "VE-??") for n in names),
                    "state": _enum_name(run.state, RUN_STATES),
                    "results": len(results),
                    "resumed": bool(resume_run_name),
                }
            )

    if getattr(opts, "parallel_batches", False) and len(batches) > 1 and not resume_run:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            for b, batch in enumerate(batches, 1):
                if b > 1:
                    time.sleep(2)
                futures.append(
                    executor.submit(
                        one_run,
                        [ev.name for _, ev in batch],
                        opts.runs,
                        f"{opts.run_label}: {kind}, batch {b}/{len(batches)}",
                        0,
                        None,
                    )
                )
            for fut in concurrent.futures.as_completed(futures):
                fut.result()
    else:
        for b, batch in enumerate(batches, 1):
            one_run(
                [ev.name for _, ev in batch],
                opts.runs,
                f"{opts.run_label}: {kind}, batch {b}/{len(batches)}" + (" (resumed)" if resume_run else ""),
                0,
                resume_run or None,
            )
    for round_no in range(1, opts.max_infra_rounds + 1):
        need = slots_needed(records, [ev.name for _, ev in target], opts.runs)
        if not need:
            break
        for count in sorted(set(need.values())):
            names = sorted(n for n, c in need.items() if c == count)
            one_run(names, count, f"{opts.run_label}: infra re-run round {round_no} ({len(names)} evals)", round_no)
    outcomes = [
        eval_outcome(dname, ev.name, [r for r in records if r["evaluation"] == ev.name], index, opts.runs)
        for dname, ev in target
    ]
    outcomes.sort(key=lambda o: o["ve_id"])
    app_after = get_app(cloud, app_name, "bench: re-read the app (update_time check)")
    update_time_after = str(_field(app_after, "update_time", "") or "")
    return {
        "app_resource": app_name,
        "runs": run_details,
        "records": records,
        "outcomes": outcomes,
        "app_update_time_before": update_time_before,
        "app_update_time_after": update_time_after,
        "app_update_time_changed": bool(update_time_before and update_time_before != update_time_after),
    }


def load_eval_index_entries(entries: list[dict]) -> dict[str, dict]:
    return {
        e["name"]: {"ve_id": e["id"], "topic": e.get("topic", ""), "language": e.get("language", "")}
        for e in entries
    }


def validate_full_run_payload(payload: dict) -> None:
    """Refuse to write a `full-*.json` record if it is a holdout, subset, or multi-SHA/version run."""
    if payload.get("is_holdout"):
        raise ValueError("Holdout runs must never be written as full-*.json")
    if not payload.get("is_full_run"):
        raise ValueError("Subset/targeted runs must never be written as full-*.json")
    commits = payload.get("commits") or []
    if len(commits) > 1:
        raise ValueError(f"Multi-commit run ({commits}) cannot be recorded as a clean full-*.json")
    versions = payload.get("app_versions_seen") or []
    if len(versions) > 1:
        raise ValueError(f"Multi-version run ({versions}) cannot be recorded as a clean full-*.json")
    if payload.get("app_update_time_changed"):
        raise ValueError("App update_time changed mid-run; refusing to record as clean full-*.json")


def build_payload(result: dict, opts, label: str, is_full_run: bool, full_run_no: int | None,
                  reference: dict | None, failing_dir: Path | None, inventory: list[dict]) -> dict:
    outcomes = result["outcomes"]
    by_language, by_topic = summarize(outcomes)
    versions = sorted(
        {
            f"{r['raw'].get('app_version', '') or '(draft)'} {r['raw'].get('app_version_display_name', '')}".strip()
            for r in result["records"]
        }
    )
    is_smoke = bool(getattr(opts, "smoke", False))
    is_holdout = bool(getattr(opts, "is_holdout", False)) or (
        "holdout" in str(getattr(opts, "bench_dir", "")).lower()
    )
    git_sha = str(getattr(opts, "git_sha", "") or _current_git_sha())
    commits = list(getattr(opts, "commits", None) or ([git_sha] if git_sha else []))

    total = len(outcomes)
    strict_pass = sum(
        1 for o in outcomes if o.get("pass_runs", 0) == o.get("total_runs", 0) and o.get("total_runs", 0) > 0
    )
    majority_pass = sum(1 for o in outcomes if o["verdict"] == "PASS")
    individual_passed = sum(int(o.get("pass_runs") or 0) for o in outcomes)
    individual_total = sum(int(o.get("total_runs") or 0) for o in outcomes)
    strict_pass_rate = round(strict_pass / total, 4) if total else 0.0
    majority_pass_rate = round(majority_pass / total, 4) if total else 0.0
    p_val = round(individual_passed / individual_total, 4) if individual_total else 0.0
    predicted_strict = round(total * (p_val ** 3), 2)

    effective_is_full_run = bool(
        is_full_run
        and not is_holdout
        and len(commits) <= 1
        and len(versions) <= 1
        and not result.get("app_update_time_changed")
    )

    pass_turn_vals = [o["avg_pass_turns"] for o in outcomes if o.get("avg_pass_turns") is not None]
    pass_tool_vals = [o["avg_pass_tool_calls"] for o in outcomes if o.get("avg_pass_tool_calls") is not None]
    avg_pass_turns = round(sum(pass_turn_vals) / len(pass_turn_vals), 2) if pass_turn_vals else None
    avg_pass_tool_calls = round(sum(pass_tool_vals) / len(pass_tool_vals), 2) if pass_tool_vals else None
    payload = {
        "timestamp": _now_iso(),
        "label": label,
        "git_sha": git_sha,
        "commits": commits,
        "agent_id": getattr(opts, "agent_id", "") or result["app_resource"].rsplit("/", 1)[-1],
        "app_resource": result["app_resource"],
        "modality": getattr(opts, "modality", "text") or "text",
        "evaluation_runs": [r["evaluation_run"] for r in result["runs"]],
        "evaluation_run_details": result["runs"],
        "is_full_run": effective_is_full_run,
        "is_holdout": is_holdout,
        "is_smoke_run": is_smoke,
        "full_run_number_today": full_run_no,
        "runs_per_eval": opts.runs,
        "eval_count": total,
        "total_evaluations": total,
        "strict_pass": strict_pass,
        "strict_pass_rate": strict_pass_rate,
        "majority_pass": majority_pass,
        "majority_pass_rate": majority_pass_rate,
        "individual_passed": individual_passed,
        "individual_total": individual_total,
        "p": p_val,
        "predicted_strict_3_of_3": predicted_strict,
        "passed_evaluations": majority_pass,
        "failed_evaluations": sum(1 for o in outcomes if o["verdict"] == "FAIL"),
        "inconclusive_evaluations": sum(1 for o in outcomes if o["verdict"] == "INCONCLUSIVE"),
        "avg_pass_turns": avg_pass_turns,
        "avg_pass_tool_calls": avg_pass_tool_calls,
        "app_versions_seen": versions,
        "app_update_time_before": result.get("app_update_time_before", ""),
        "app_update_time_after": result.get("app_update_time_after", ""),
        "app_update_time_changed": bool(result.get("app_update_time_changed")),
        "by_language": by_language,
        "by_topic": by_topic,
        "failing_runs_dir": str(failing_dir) if failing_dir else "",
        "failing_runs_inventory": inventory,
        "results": outcomes,
    }
    payload["pass_rate"] = majority_pass_rate
    if is_smoke:
        payload["smoke_gate"] = compute_smoke_gate(result["records"], outcomes)
    if reference is not None:
        payload["comparison"] = compare_with_reference(outcomes, reference)
        payload["reference_results"] = [
            {k: r.get(k) for k in ("display_name", "passed", "pass_runs", "total_runs")}
            for r in reference.get("results", [])
        ]
    return payload


def _scrapi_app_clients(app_name: str):
    from cxas_scrapi.core.conversation_history import ConversationHistory  # transcripts
    from cxas_scrapi.core.evaluations import Evaluations  # evaluation runner client

    evals = Evaluations(app_name=app_name)
    return evals, ConversationHistory(app_name=app_name, creds=evals.creds)


def _parse_app_resource(app: str) -> tuple[str, str]:
    m = re.match(r"^projects/([^/]+)/locations/([^/]+)/apps/[^/]+$", app or "")
    if not m:
        raise LookupError(f"--app must look like projects/<p>/locations/<l>/apps/<id>, got {app!r}")
    return m.group(1), m.group(2)


def _make_cloud(project: str, region: str) -> Cloud:
    from cxas_scrapi.core.apps import Apps  # CXAS application client

    return Cloud(Apps(project_id=project, location=region), app_clients=_scrapi_app_clients)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# ----------------------------------------------------------------------- READ-only re-fetch


def refetch_runs(cloud: Cloud, app_name: str, run_names: list[str], index: dict[str, dict], label: str,
                 runs_dir: Path) -> dict:
    listed = list_all_evaluations(cloud, app_name, f"{label}: map evaluation resources to ids")
    display_of = {ev.name: ev.display_name for ev in listed}
    records: list[dict] = []
    runs = []
    for run_name in run_names:
        run = cloud.call(
            "READ",
            "Evaluations.get_evaluation_run",
            run_name,
            f"{label}: read finished run",
            lambda run_name=run_name: cloud.evals.get_evaluation_run(run_name),
            describe=lambda r: f"state={_enum_name(r.state, RUN_STATES)}, results={len(r.evaluation_results)}",
        )
        results = fetch_run_results(cloud, run, label)
        _save_raw(runs_dir / f"{label}_raw", run_name,
                  {"label": label, "evaluation_run": run_name, "run": to_plain(run), "results": results})
        records.extend(build_records(results, display_of, index, 0, run_name))
        runs.append({"evaluation_run": run_name, "state": _enum_name(run.state, RUN_STATES), "results": len(results)})
    attach_conversations(cloud, records, label)
    failing_dir = runs_dir / "failing_runs_data" / label
    inventory = write_failing_runs(records, failing_dir, label)
    return {"runs": runs, "records": records, "failing_dir": failing_dir, "inventory": inventory}


def refetch_summary(result: dict, label: str, reference: dict | None) -> dict:
    by_eval = defaultdict(list)
    for rec in result["records"]:
        by_eval[(rec["ve_id"], rec["display_name"], rec["evaluation"])].append(rec)
    evals = []
    for (ve_id, dname, eval_res), recs in sorted(by_eval.items()):
        ordered = sorted(recs, key=lambda r: (r["evaluation_run"], r["slot"]))
        evals.append(
            {
                "ve_id": ve_id,
                "display_name": dname,
                "evaluation_name": eval_res,
                "classifications": [r["classification"] for r in ordered],
                "platform_pass_runs": sum(
                    1 for r in ordered if r["execution_state"] == "COMPLETED" and r["evaluation_status"] == "PASS"
                ),
                "runs": len(ordered),
            }
        )
    mismatches = []
    if reference is not None:
        ref = {r["display_name"]: r for r in reference.get("results", [])}
        for e in evals:
            old = ref.get(e["display_name"])
            if old is None:
                mismatches.append({"ve_id": e["ve_id"], "issue": "not in reference"})
            elif old.get("pass_runs") != e["platform_pass_runs"]:
                mismatches.append(
                    {"ve_id": e["ve_id"],
                     "issue": f"reference pass_runs={old.get('pass_runs')}, refetched={e['platform_pass_runs']}"}
                )
    counts = defaultdict(int)
    for rec in result["records"]:
        counts[rec["classification"]] += 1
    return {
        "timestamp": _now_iso(),
        "label": label,
        "runs": result["runs"],
        "results": len(result["records"]),
        "classification_counts": dict(counts),
        "failing_runs_dir": str(result["failing_dir"]),
        "failing_runs_with_missing_items": sum(1 for i in result["inventory"] if i["missing"]),
        "reference_mismatches": mismatches,
        "inventory": result["inventory"],
        "evals": evals,
    }


def fetch_runs_mode(args, index: dict[str, dict], runs_dir: Path) -> int:
    """READ only: re-fetch finished runs, classify, save every non-passing result's evidence."""
    tokens = [t.strip() for t in args.fetch_runs.split(",") if t.strip()]
    label = args.report_name or "refetch_" + "_".join(t.rsplit("/", 1)[-1][:8] for t in tokens)
    cloud = _make_cloud(args.project, args.location)
    try:
        app = resolve_app(cloud, args)
        run_names = [t if t.startswith("projects/") else f"{app.name}/evaluationRuns/{t}" for t in tokens]
        result = refetch_runs(cloud, app.name, run_names, index, label, runs_dir)
    except ReauthRequired as exc:
        print(f"STOP: credentials need a re-login ({exc}); no further cloud calls.", file=sys.stderr)
        return 3
    except LookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    reference = json.loads(Path(args.compare_with).read_text(encoding="utf-8")) if args.compare_with else None
    summary = refetch_summary(result, label, reference)
    _write_json(runs_dir / f"{label}_refetch.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("evals", "inventory")}, indent=2))
    return 0


# --------------------------------------------------------------------------------- main


def sync_and_run_bench(args) -> int:
    bench_root = Path(args.bench_dir)
    dev_dir = bench_root / "dev"
    runs_dir = bench_root / "runs"

    if (dev_dir / "SHA256SUMS").exists() or args.require_sha256:
        ok_sha, sha_errors = verify_bench_sha256sums(dev_dir)
        if not ok_sha:
            print("ERROR: benchmark SHA256SUMS verification failed:", file=sys.stderr)
            for err in sha_errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    expectations, evaluations = load_bench_bundles(dev_dir)
    index = load_eval_index(dev_dir, args.id_prefix)
    try:
        selected_names = select_evals(args.evals, index)
    except OSError as exc:
        print(f"ERROR: cannot read the eval list: {exc}", file=sys.stderr)
        return 1
    is_full_run = selected_names is None and not getattr(args, "is_holdout", False)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run_ok",
                    "bench_dir": str(bench_root),
                    "app": args.app or f"{args.project}/{args.location}/{args.agent_id}",
                    "sha256_verified": (dev_dir / "SHA256SUMS").exists(),
                    "bundle_expectations": len(expectations),
                    "bundle_evaluations": len(evaluations),
                    "indexed_evaluations": len(index),
                    "selected_evals": sorted(selected_names) if selected_names else "ALL",
                    "runs_per_eval": args.runs,
                    "modality": args.modality,
                    "smoke": bool(args.smoke),
                    "parallel_batches": bool(getattr(args, "parallel_batches", False)),
                    "is_holdout": bool(getattr(args, "is_holdout", False)),
                    "note": "no cloud calls made; evaluations already in the app are listed at run time",
                },
                indent=2,
            )
        )
        return 0

    if args.fetch_runs:
        return fetch_runs_mode(args, index, runs_dir)

    full_run_no = None
    if is_full_run:
        allowed, count_today = check_daily_full_run_cap(runs_dir, max_full_runs=args.max_full_runs)
        if not allowed:
            print(
                f"ERROR: daily full-run cap reached ({count_today}/{args.max_full_runs} full runs today). "
                "Use --evals <ids> for targeted re-runs, or MAX_FULL_RUNS=<n>.",
                file=sys.stderr,
            )
            return 1
        full_run_no = count_today + 1

    from google.cloud.ces_v1beta import types  # CES protobuf message definitions
    from google.protobuf.json_format import ParseDict  # proto-to-dict parser

    ts_slug = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = args.report_name or f"run_{ts_slug}"
    cloud = _make_cloud(args.project, args.location)
    try:
        result = run_bench(
            cloud, args, expectations, evaluations, index, runs_dir / f"{label}_raw", dev_dir, full_run_no,
            types, ParseDict,
        )
    except ReauthRequired as exc:
        print(f"STOP: credentials need a re-login ({exc}); no further cloud calls.", file=sys.stderr)
        return 3
    except LookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reference = json.loads(Path(args.compare_with).read_text(encoding="utf-8")) if args.compare_with else None
    failing_dir = runs_dir / "failing_runs_data" / label
    inventory = write_failing_runs(result["records"], failing_dir, label)
    payload = build_payload(result, args, label, is_full_run, full_run_no, reference, failing_dir, inventory)
    md_text = render_report_md(payload)
    runs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(runs_dir / f"run_{ts_slug}.json", payload)
    (runs_dir / f"run_{ts_slug}.md").write_text(md_text, encoding="utf-8")
    if args.report_name:
        if args.report_name.startswith("full-"):
            try:
                validate_full_run_payload(payload)
            except ValueError as exc:
                print(f"ERROR: refusing to write {args.report_name}.json: {exc}", file=sys.stderr)
                return 1
        _write_json(runs_dir / f"{args.report_name}.json", payload)
        (runs_dir / f"{args.report_name}.md").write_text(md_text, encoding="utf-8")
    print(
        f"Headline: strict 3/3: {payload['strict_pass']}/{payload['total_evaluations']} "
        f"({payload['strict_pass_rate'] * 100:.1f}%) | "
        f"majority >=2/3: {payload['majority_pass']}/{payload['total_evaluations']} "
        f"({payload['majority_pass_rate'] * 100:.1f}%) | "
        f"individual: {payload['individual_passed']}/{payload['individual_total']} "
        f"(p={payload['p']:.3f}, N*p^3={payload['predicted_strict_3_of_3']:.1f})"
    )
    print(
        json.dumps(
            {k: v for k, v in payload.items() if k not in ("results", "reference_results", "failing_runs_inventory")},
            indent=2,
        )
    )
    if payload.get("smoke_gate"):
        print(f"GATE 1: {payload['smoke_gate']['gate_verdict']}")
    if payload["app_update_time_changed"]:
        print(
            "WARNING: the app changed during the run (update_time "
            f"{payload['app_update_time_before']} -> {payload['app_update_time_after']}); the numbers are not trustworthy.",
            file=sys.stderr,
        )
        return 2
    return 0


# ----------------------------------------------------------------------------- self-test


def _fake_result(name: str, state: int, status: int, conv: str = "", turns: int = 3, tool_calls: int = 2) -> dict:
    return {
        "name": name,
        "create_time": name,
        "execution_state": state,
        "evaluation_status": status,
        "scenario_result": {
            "conversation": conv,
            "evaluation_expectation_results": [{"prompt": "greets", "outcome": status, "explanation": "x"}],
            "user_goal_satisfaction_result": {"score": 1 if status == 1 else 0, "label": "", "explanation": "y"},
            "hallucination_result": [{"score": 1, "label": "", "explanation": "z"} for _ in range(turns)],
            "tool_call_latencies": [{"tool": f"t{i}"} for i in range(tool_calls)],
        },
    }


def _self_test() -> int:
    app = "projects/p/locations/us/apps/a1"
    e1, e2 = f"{app}/evaluations/e1", f"{app}/evaluations/e2"
    run = f"{app}/evaluationRuns/r1"
    index = {"golden_a": {"ve_id": "VE-01", "topic": "t", "language": "en"},
             "sim_b_fr": {"ve_id": "VE-02", "topic": "t", "language": "fr"}}
    display_of = {e1: "golden_a", e2: "sim_b_fr"}

    # 1. select_evals: ids, display names, @file lists
    with tempfile.TemporaryDirectory() as tmp:
        lst = Path(tmp) / "unstable.txt"
        lst.write_text("# unstable\nVE-02, golden_a\n", encoding="utf-8")
        assert select_evals(f"@{lst}", index) == {"sim_b_fr", "golden_a"}
    assert select_evals("ve-01", index) == {"golden_a"}
    assert select_evals("", index) is None

    # 2. classify + majority verdict + infra slots + passing-only efficiency
    results = [
        _fake_result(f"{e1}/results/x1", 2, 1, turns=4, tool_calls=3),
        _fake_result(f"{e1}/results/x2", 2, 2, turns=9, tool_calls=8),
        _fake_result(f"{e1}/results/x3", 2, 1, turns=6, tool_calls=5),
        _fake_result(f"{e2}/results/y1", 2, 2, turns=7, tool_calls=4),
        _fake_result(f"{e2}/results/y2", 3, 0),
        _fake_result(f"{e2}/results/y3", 2, 0),
    ]
    records = build_records(results, display_of, index, 0, run)
    for r in records:
        r["classification"], r["classification_reason"] = classify(r)
    assert [r["classification"] for r in records] == ["PASS", "FAIL", "PASS", "FAIL", "INFRA", "INFRA"]
    assert slots_needed(records, [e1, e2], 3) == {e2: 2}
    o1 = eval_outcome("golden_a", e1, [r for r in records if r["evaluation"] == e1], index, 3)
    o2 = eval_outcome("sim_b_fr", e2, [r for r in records if r["evaluation"] == e2], index, 3)
    assert (o1["verdict"], o1["pass_runs"], o1["total_runs"]) == ("PASS", 2, 3)
    # Passing runs for e1 have turns=(4, 6) -> avg 5.0 and tool_calls=(3, 5) -> avg 4.0 (the failing run with 9 turns is excluded!)
    assert (o1["avg_pass_turns"], o1["avg_pass_tool_calls"]) == (5.0, 4.0), o1
    assert (o2["verdict"], o2["infra_runs"], o2["avg_pass_turns"]) == ("INCONCLUSIVE", 2, None)
    rec_fallback = dict(records[1], fallback_reasons=[{"turn": 1, "span": "s", "reason": "429 quota exceeded"}])
    assert classify(rec_fallback)[0] == "INFRA"

    # 3. payload shape (what bench_summary / build_dashboard read) + smoke gate + md
    class Opts:
        runs, smoke, modality, agent_id = 3, True, "text", "demo"

    result = {
        "app_resource": app,
        "runs": [{"label": "l", "evaluation_run": run, "run_count": 3, "evals": 2, "ve_ids": ["VE-01", "VE-02"],
                  "state": "COMPLETED", "results": 6, "resumed": False}],
        "records": records, "outcomes": [o1, o2],
        "app_update_time_before": "t0", "app_update_time_after": "t0", "app_update_time_changed": False,
    }
    reference = {"evaluation_runs": [run], "results": [
        {"display_name": "golden_a", "passed": False, "pass_runs": 0, "total_runs": 3},
        {"display_name": "sim_b_fr", "passed": True, "pass_runs": 3, "total_runs": 3}]}
    payload = build_payload(result, Opts, "smoke-abc1234", False, None, reference, None, [])
    for key in ("label", "timestamp", "results", "evaluation_runs", "app_versions_seen", "runs_per_eval",
                "is_full_run", "is_holdout", "strict_pass", "strict_pass_rate", "majority_pass",
                "majority_pass_rate", "p", "predicted_strict_3_of_3", "pass_rate",
                "avg_pass_turns", "avg_pass_tool_calls", "smoke_gate", "comparison"):
        assert key in payload, key
    for key in ("ve_id", "display_name", "verdict", "passed", "pass_runs", "total_runs", "infra_runs",
                "avg_pass_turns", "avg_pass_tool_calls"):
        assert key in payload["results"][0], key
    assert payload["avg_pass_turns"] == 5.0 and payload["avg_pass_tool_calls"] == 4.0
    assert payload["comparison"]["newly_passing"][0]["ve_id"] == "VE-01"
    assert payload["comparison"]["regressions"][0]["ve_id"] == "VE-02"
    assert payload["smoke_gate"]["gate_verdict"] == "stop"  # VE-02 has 1/1 scored runs but no 2/3
    md = render_report_md(payload)
    assert "GATE 1 SMOKE RUN" in md and "| VE-01 |" in md and "Efficiency (passing runs only)" in md
    assert "strict 3/3:" in md

    # 4. index building for apps without index.json
    class Ev:
        def __init__(self, dn, tags):
            self.display_name, self.tags = dn, tags

    entries = build_index_from_evaluations([Ev("zeta_fr", ["billing"]), Ev("alpha", [])], "VE")
    assert [e["id"] for e in entries] == ["VE-01", "VE-02"] and entries[1]["language"] == "fr"
    with tempfile.TemporaryDirectory() as tmp:
        path = write_eval_index(Path(tmp), entries)
        loaded = load_eval_index(path.parent)
        assert loaded["zeta_fr"]["ve_id"] == "VE-02"

    # 5. evidence files
    with tempfile.TemporaryDirectory() as tmp:
        inv = write_failing_runs(records, Path(tmp), "selftest")
        assert len(inv) == 4 and (Path(tmp) / "index.md").exists()

    # 6. retry policy: transient read errors retry, re-auth stops at once
    class FakeClient:
        pass

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("503 Service Unavailable")
        return "ok"

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "cloud-log.md"
        log.write_text(
            "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
            "|---|---|---|---|---|---|\n", encoding="utf-8")
        cloud = Cloud(FakeClient(), log_kwargs={"log_path": log, "forbidden": set()}, sleep=lambda s: None)
        assert cloud.call("READ", "X.y", app, "flaky", flaky) == "ok" and calls["n"] == 2
        try:
            cloud.call("READ", "X.y", app, "reauth", lambda: (_ for _ in ()).throw(RuntimeError("invalid_rapt")))
        except ReauthRequired:
            pass
        else:
            raise AssertionError("expected ReauthRequired")
        assert log.read_text(encoding="utf-8").count("\n| ") >= 3  # one row per attempt

    # 7. full-run write guard and BUSINESS_ERROR_CODES
    assert "WRONG_CODE" in BUSINESS_ERROR_CODES
    assert "CARD_DECLINED" in BUSINESS_ERROR_CODES
    assert "SYSTEM_DOWN" not in BUSINESS_ERROR_CODES
    try:
        validate_full_run_payload(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected validate_full_run_payload to reject non-full run")

    print("OK: 7/7 run_bench self-test cases passed")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--app", default=os.environ.get("CES_APP_NAME", ""),
                   help="App resource name projects/<p>/locations/<l>/apps/<id> (or env CES_APP_NAME)")
    p.add_argument("--project", default=os.environ.get("PROJECT_ID", ""), help="GCP project (with --agent-id)")
    p.add_argument("--location", "--region", dest="location", default=os.environ.get("LOCATION", "us"))
    p.add_argument("--agent-id", default=os.environ.get("AGENT_ID", ""),
                   help="App display name or id under --project/--location (alternative to --app)")
    p.add_argument("--bench-dir", default=str(DEFAULT_BENCH_ROOT),
                   help="<bench-dir>/dev = optional exported bundle + index.json; <bench-dir>/runs = outputs")
    p.add_argument("--runs", type=int, default=3, help="Conversations per evaluation (majority verdict)")
    p.add_argument("--batch-size", type=int, default=25, help="Evaluations per evaluation run")
    p.add_argument(
        "--parallel-batches",
        action="store_true",
        default=os.environ.get("PARALLEL_BATCHES", "0").lower() in ("1", "true", "yes"),
        help="Submit evaluation batches concurrently with max_workers=2",
    )
    p.add_argument(
        "--is-holdout",
        action="store_true",
        help="Mark run as a holdout evaluation run (never recorded as a dev full run)",
    )
    p.add_argument("--evals", default=os.environ.get("TARGETS", ""),
                   help="Comma-separated ids (VE-07), display names, or @file lists; empty = all")
    p.add_argument("--modality", choices=("text", "audio"), default="text")
    p.add_argument("--report-name", help="Fixed report basename in runs/ (also names raw and failing-run folders)")
    p.add_argument("--run-label", default="bench", help="Prefix for the cloud-log notes of this run (no eval names)")
    p.add_argument("--max-infra-rounds", type=int, default=2,
                   help="How many times INFRA (not completed / not scored / quota) results are re-run")
    p.add_argument("--max-full-runs", type=int, default=10, help="Daily cap on full (all-eval) runs")
    p.add_argument("--compare-with", help="Earlier report json: list regressions and newly passing")
    p.add_argument("--fetch-runs", help="READ only: comma-separated evaluationRun ids or names to re-fetch and save")
    p.add_argument("--resume-run", help="Continue an evaluationRun started earlier (single-batch selections only)")
    p.add_argument("--smoke", action="store_true",
                   help="Gate 1 smoke run: fetch every conversation, check judge metrics + tool errors")
    p.add_argument("--id-prefix", default=DEFAULT_ID_PREFIX, help="Short id prefix when building index.json")
    p.add_argument("--no-write-index", action="store_true", help="Do not write <bench-dir>/dev/index.json")
    p.add_argument("--require-sha256", action="store_true", help="Fail when dev/SHA256SUMS is missing")
    p.add_argument("--dry-run", action="store_true", help="Validate inputs and print the plan; no cloud calls")
    p.add_argument("--self-test", action="store_true", help="Run offline self-tests")
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.dry_run:
        if args.app:
            try:
                args.project, args.location = _parse_app_resource(args.app)
            except LookupError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
        elif not (args.project and args.agent_id):
            print("ERROR: set --app projects/<p>/locations/<l>/apps/<id> (or CES_APP_NAME), "
                  "or --project with --agent-id.", file=sys.stderr)
            return 1
    return sync_and_run_bench(args)


if __name__ == "__main__":
    sys.exit(main())
