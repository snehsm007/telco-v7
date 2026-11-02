#!/usr/bin/env python3
"""Strict local runner for the YAML tool tests (`evals/tool_tests/*.yaml`), no cloud calls.

A tool test passes only when the tool's real output matches expected values;
"it ran" is never a pass.

Usage:
  python suite/tool_tests.py [--file evals/tool_tests/tool_tests.yaml] [--repeats 3]
                             [--json out.json]
  python suite/tool_tests.py --self-test
Exit code 0 only if every case passes (with --repeats N: passes a majority of N runs).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

DEFAULT_FILE = REPO_ROOT / "evals" / "tool_tests" / "tool_tests.yaml"

DOCUMENTED_ERROR_CODES = (
    "SYSTEM_DOWN",
    "INTERNAL_ERROR",
    "AUTH_SERVICE_UNAVAILABLE",
    "INSUFFICIENT_FUNDS",
    "NOT_ELIGIBLE",
    "ALREADY_APPLIED",
    "NOT_FOUND",
    "INVALID_INPUT",
    "MALFORMED_REQUEST",
)

REQUIRED_KEYS = ("id", "tool", "args", "expected_status")
OPTIONAL_KEYS = (
    "priority",
    "requirements",
    "description",
    "initial_state",
    "setup",
    "setup_profile_clid",
    "setup_auth_clid",
    "setup_outage_check",
    "setup_payment_arrangement",
    "setup_step_up",
    "expected_fields",
    "expected_error",
    "expected_agent_action",
    "expected_state",
    "forbidden_substrings",
    "source",
)
STEP_KEYS = ("tool", "args", "expected_status", "expected_fields", "expected_error")
STATE_GROUPS = ("caller", "login", "call", "counters")
_MISSING = object()


class CaseError(ValueError):
    """A tool-test case that breaks the schema rules above."""


def _default_services():
    from lib import services

    return services


def _known_tools_from_services(svc) -> set[str] | None:
    tools = getattr(svc, "ALL_TOOLS", None) or getattr(svc, "ALL_33_TOOLS", None)
    return set(tools) if tools else None


def _error_codes_from_services(svc) -> tuple[str, ...]:
    """The agent's own error codes (`lib/services.ERROR_CODES`), else the documented list."""
    codes = getattr(svc, "ERROR_CODES", None)
    return tuple(codes) if codes else DOCUMENTED_ERROR_CODES


def validate_case(case, known_tools=None, error_codes=DOCUMENTED_ERROR_CODES):
    """Raise CaseError if `case` breaks the schema; return the case otherwise."""
    if not isinstance(case, dict):
        raise CaseError(f"case must be a mapping, got {type(case).__name__}")
    cid = case.get("id", "<no id>")
    missing = [k for k in REQUIRED_KEYS if k not in case]
    if missing:
        raise CaseError(f"{cid}: missing required keys {missing}")
    unknown = sorted(set(case) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise CaseError(f"{cid}: unknown keys {unknown} (typo?)")
    if known_tools is not None and case["tool"] not in known_tools:
        raise CaseError(f"{cid}: unknown tool {case['tool']!r}")
    if not isinstance(case["args"], dict):
        raise CaseError(f"{cid}: args must be a mapping")
    status = str(case["expected_status"]).lower()
    if status == "ok":
        fields = case.get("expected_fields")
        if not isinstance(fields, dict) or not fields:
            raise CaseError(
                f"{cid}: an ok test needs a non-empty expected_fields "
                "(a pass on status alone only proves the tool ran)"
            )
        if "expected_error" in case:
            raise CaseError(f"{cid}: expected_error only applies to error tests")
    elif status == "error":
        code = case.get("expected_error")
        if code not in error_codes:
            raise CaseError(
                f"{cid}: an error test needs expected_error, one of {tuple(error_codes)}"
            )
        if case.get("expected_fields"):
            raise CaseError(f"{cid}: expected_fields only applies to ok tests")
    else:
        raise CaseError(f"{cid}: expected_status must be 'ok' or 'error'")
    for step in case.get("setup") or []:
        if not isinstance(step, dict) or "tool" not in step:
            raise CaseError(f"{cid}: every setup step needs a tool")
        bad = sorted(set(step) - set(STEP_KEYS))
        if bad:
            raise CaseError(f"{cid}: unknown setup step keys {bad}")
        if known_tools is not None and step["tool"] not in known_tools:
            raise CaseError(f"{cid}: unknown setup tool {step['tool']!r}")
    for key in ("expected_state",):
        if key in case and not isinstance(case[key], dict):
            raise CaseError(f"{cid}: {key} must be a mapping")
    forbidden = case.get("forbidden_substrings", [])
    if not isinstance(forbidden, list) or not all(
        isinstance(s, str) for s in forbidden
    ):
        raise CaseError(f"{cid}: forbidden_substrings must be a list of strings")
    return case


def load_tool_tests(path=DEFAULT_FILE, known_tools=None, error_codes=None):
    """Load and validate one YAML tool-test file (or directory of YAML files); raise CaseError on any bad case."""
    if known_tools is None or error_codes is None:
        try:
            svc = _default_services()
        except ImportError:
            svc = None
        if known_tools is None and svc is not None:
            known_tools = _known_tools_from_services(svc)
        if error_codes is None:
            error_codes = (
                _error_codes_from_services(svc) if svc is not None else DOCUMENTED_ERROR_CODES
            )
    p = Path(path)
    paths = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    if not paths:
        raise CaseError(f"{path}: no YAML files found")
    all_cases = []
    seen = set()
    for fp in paths:
        with open(fp, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        cases = doc.get("tests")
        if not isinstance(cases, list) or not cases:
            raise CaseError(f"{fp}: no 'tests' list")
        for raw_case in cases:
            case = (
                {k: v for k, v in raw_case.items() if k != "regression_of"}
                if isinstance(raw_case, dict)
                else raw_case
            )
            validate_case(case, known_tools, error_codes)
            if case["id"] in seen:
                raise CaseError(f"{fp}: duplicate id {case['id']}")
            seen.add(case["id"])
            all_cases.append(case)
    return all_cases


def resolve_path(obj, path):
    """Follow a dotted path (`a.0.b`) or `len(a.b)`; return _MISSING if it does not exist."""
    want_len = path.startswith("len(") and path.endswith(")")
    if want_len:
        path = path[4:-1]
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif (
            isinstance(cur, list)
            and seg.lstrip("-").isdigit()
            and -len(cur) <= int(seg) < len(cur)
        ):
            cur = cur[int(seg)]
        else:
            return _MISSING
    if want_len:
        return len(cur) if isinstance(cur, (list, dict, str)) else _MISSING
    return cur


def _error_text(res):
    return res.get("error_message") or res.get("message") or ""


def envelope_problems(res, error_codes=DOCUMENTED_ERROR_CODES):
    """Problems with the shared return shape (docs/DESIGN_RULES.md rule 10).

    ok    -> {status: "ok", data: {...}}
    error -> {status: "error", error: <code>, error_message (or message), agent_action}
    agent_action is required on errors only; an ok reply may carry one too.
    """
    if not isinstance(res, dict):
        return [f"response is {type(res).__name__}, not a mapping"]
    problems = []
    status = res.get("status")
    if status not in ("ok", "error"):
        problems.append(f"status must be 'ok' or 'error', got {status!r}")
    if status == "ok" and not isinstance(res.get("data"), dict):
        problems.append("ok response without a data mapping")
    if status == "error":
        if res.get("error") not in error_codes:
            problems.append(f"error code {res.get('error')!r} is not a documented code")
        if not isinstance(_error_text(res), str) or not _error_text(res).strip():
            problems.append("error response without an error_message")
        if not isinstance(res.get("agent_action"), str) or not res.get("agent_action"):
            problems.append("error response without an agent_action (return shape)")
    return problems


def _state_view(sess):
    try:
        from lib import state as state_lib

        view = {g: state_lib.read_state_group(sess, g) for g in STATE_GROUPS}
        view["mock_mode"] = sess.get("mock_mode")
        return view
    except (ImportError, TypeError, KeyError):
        return dict(sess)


def _call_tool_fn(fn, sess, args):
    """Call a tool or *_impl once, passing the session the way its signature asks.

    New layout: `state=`. Older layout: `session_state=`. Only signature
    inspection is guarded; an error raised inside the tool propagates, so a
    tool is never called twice.
    """
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (ValueError, TypeError):  # no inspectable signature (rare)
        return fn(**args)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    call_args = dict(args) if has_var_kw else {k: v for k, v in args.items() if k in params}
    if "state" in params:
        call_args["state"] = sess
    elif "session_state" in params or has_var_kw:
        call_args["session_state"] = sess
    return fn(**call_args)


def _initial_session(initial):
    sess = {}
    for key, val in (initial or {}).items():
        sess[key] = dict(val) if isinstance(val, dict) else val
    try:
        from lib import state as state_lib

        return state_lib.ensure_session_defaults(sess)
    except ImportError:
        return sess


def _check_result(res, want_status, fields=None, error=None, error_codes=DOCUMENTED_ERROR_CODES):
    """Return the first mismatch between `res` and the expectations, or ''."""
    problems = envelope_problems(res, error_codes)
    if problems:
        return "; ".join(problems)
    if res["status"] != want_status:
        return (
            f"expected status {want_status}, got {res['status']} "
            f"({res.get('error')}: {_error_text(res)})"
        )
    if error is not None and res.get("error") != error:
        return f"expected error {error}, got {res.get('error')} ({_error_text(res)})"
    for path, want in (fields or {}).items():
        got = resolve_path(res.get("data") or {}, path)
        if got is _MISSING:
            return f"field {path}: missing from data"
        if got != want:
            return f"field {path}: expected {want!r}, got {got!r}"
    return ""


def _legacy_setup_steps(case):
    steps = []
    if case.get("setup_profile_clid"):
        steps.append(
            ("fetch_customer_profile", {"clid": case["setup_profile_clid"]}, "ok", {})
        )
    clid = case.get("setup_auth_clid")
    if clid:
        steps.append(("fetch_customer_profile", {"clid": clid}, "ok", {}))
        steps.append(("send_authentication_otp", {"clid": clid}, "ok", {}))
        steps.append(
            (
                "validate_authentication_otp",
                {"code": "123456"},
                "ok",
                {"auth_status": "Pass"},
            )
        )
    return steps


def run_case(case, services_module=None):
    """Run one case; return (passed, failure_reason). Never raises."""
    svc = services_module or _default_services()
    codes = _error_codes_from_services(svc)
    try:
        validate_case(case, _known_tools_from_services(svc), codes)
        sess = _initial_session(case.get("initial_state"))
        steps = _legacy_setup_steps(case)
        for step in case.get("setup") or []:
            steps.append(
                (
                    step["tool"],
                    dict(step.get("args") or {}),
                    str(step.get("expected_status", "ok")).lower(),
                    step.get("expected_fields") or {},
                    step.get("expected_error"),
                )
            )
        for n, step in enumerate(steps, 1):
            tool, args, want, fields = step[:4]
            error = step[4] if len(step) > 4 else None
            args = dict(args)
            args.setdefault("rationale", f"Test setup step {n}")
            fn = getattr(svc, tool, None) or getattr(svc, f"{tool}_impl")
            res = _call_tool_fn(fn, sess, args)
            why = _check_result(res, want, fields, error, codes)
            if why:
                return False, f"setup step {n} ({tool}) failed: {why}"

        fn = getattr(svc, case["tool"], None) or getattr(svc, f"{case['tool']}_impl")
        res = _call_tool_fn(fn, sess, dict(case["args"]))
        want = str(case["expected_status"]).lower()
        why = _check_result(
            res, want, case.get("expected_fields"), case.get("expected_error"), codes
        )
        if why:
            return False, why
        if (
            "expected_agent_action" in case
            and res.get("agent_action") != case["expected_agent_action"]
        ):
            return False, (
                f"expected agent_action {case['expected_agent_action']}, "
                f"got {res.get('agent_action')}"
            )
        text = json.dumps(res, ensure_ascii=False, default=str)
        for needle in case.get("forbidden_substrings") or []:
            if needle in text:
                return False, f"forbidden value {needle!r} appears in the response"
        view = _state_view(sess)
        for path, want_val in (case.get("expected_state") or {}).items():
            got = resolve_path(view, path)
            if got is _MISSING:
                return False, f"state {path}: missing"
            if got != want_val:
                return False, f"state {path}: expected {want_val!r}, got {got!r}"
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"crash: {type(exc).__name__}: {exc}"


def run_tool_tests(cases, services_module=None):
    """Run every case; return one record per case."""
    results = []
    for case in cases:
        t0 = time.monotonic()
        passed, why = run_case(case, services_module)
        cid = case.get("id", "<no id>") if isinstance(case, dict) else "<bad case>"
        meta = case if isinstance(case, dict) else {}
        results.append(
            {
                "test_id": cid,
                "layer": "tool",
                "priority": meta.get("priority", "P0"),
                "requirement_ids": meta.get("requirements") or ["REQ-1"],
                "status": "pass" if passed else "fail",
                "failure_reason": why,
                "code_graders": {"tool_contract": "pass" if passed else "fail"},
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
        )
    return results


def run_suite(cases, services_module=None):
    """Run cases and return a summary dict with `details` list."""
    records = run_tool_tests(cases, services_module=services_module)
    details = [
        {
            "id": r["test_id"],
            "passed": r["status"] == "pass",
            "reason": r.get("failure_reason", ""),
        }
        for r in records
    ]
    passed = sum(1 for d in details if d["passed"])
    return {
        "total": len(details),
        "passed": passed,
        "failed": len(details) - passed,
        "details": details,
    }


def majority(runs):
    """Combine N result lists (same case order): a case passes if it passed > N/2 runs."""
    out = []
    for per_case in zip(*runs):
        passes = sum(r["status"] == "pass" for r in per_case)
        merged = dict(per_case[0])
        merged["runs_passed"] = passes
        merged["runs"] = len(per_case)
        merged["status"] = "pass" if passes * 2 > len(per_case) else "fail"
        merged["failure_reason"] = next(
            (r["failure_reason"] for r in per_case if r["status"] != "pass"), ""
        )
        out.append(merged)
    return out


def self_test() -> int:
    def fake_lookup(session_state=None, account_id="", **_):
        if account_id == "1001":
            return {
                "status": "ok",
                "agent_action": "PROCEED",
                "data": {"account_last4": "****1001", "balance": 42.5},
            }
        return {
            "status": "error",
            "error": "NOT_FOUND",
            "message": "Account not found",
            "agent_action": "ASK_ALTERNATE_ID",
        }

    fake_svc = SimpleNamespace(ALL_TOOLS=("lookup_account",), lookup_account=fake_lookup)
    ok_case = {
        "id": "tt_ok",
        "tool": "lookup_account",
        "args": {"account_id": "1001"},
        "expected_status": "ok",
        "expected_fields": {"account_last4": "****1001", "balance": 42.5},
        "forbidden_substrings": ["999999999"],
    }
    err_case = {
        "id": "tt_err",
        "tool": "lookup_account",
        "args": {"account_id": "0000"},
        "expected_status": "error",
        "expected_error": "NOT_FOUND",
    }
    res = run_tool_tests([ok_case, err_case], services_module=fake_svc)
    assert all(r["status"] == "pass" for r in res), f"Expected pass, got {res}"

    # Verify that status-alone ok test is rejected by validate_case
    try:
        validate_case(
            {
                "id": "bad",
                "tool": "lookup_account",
                "args": {},
                "expected_status": "ok",
            },
            {"lookup_account"},
        )
        raise AssertionError("Expected CaseError on empty expected_fields")
    except CaseError:
        pass

    # New layout: session state arrives as `state=`, ok replies carry no
    # agent_action, errors carry error_message + agent_action, and the agent's
    # own ERROR_CODES replace the documented list.
    calls = []

    def send_code_impl(state=None):
        calls.append(1)
        if not state.get("account_id"):
            return {
                "status": "error",
                "data": {},
                "error": "NOT_IDENTIFIED",
                "error_message": "No account found yet.",
                "agent_action": "Ask for the phone number first.",
                "tracking_id": "R000001",
            }
        state["auth_status"] = "code_sent"
        return {"status": "ok", "data": {"sent": True}, "error_message": "", "tracking_id": "R000002"}

    def broken_impl(state=None):
        calls.append(1)
        raise TypeError("bug inside the tool")

    new_svc = SimpleNamespace(
        ALL_TOOLS=("send_code", "broken"),
        ERROR_CODES=("NOT_IDENTIFIED",),
        send_code_impl=send_code_impl,
        broken_impl=broken_impl,
    )
    state_ok = {
        "id": "tt_state_ok",
        "tool": "send_code",
        "args": {},
        "initial_state": {"account_id": "A1"},
        "expected_status": "ok",
        "expected_fields": {"sent": True},
        "expected_state": {"auth_status": "code_sent"},
    }
    state_err = {
        "id": "tt_state_err",
        "tool": "send_code",
        "args": {},
        "expected_status": "error",
        "expected_error": "NOT_IDENTIFIED",
    }
    res = run_tool_tests([state_ok, state_err], services_module=new_svc)
    assert all(r["status"] == "pass" for r in res), f"Expected pass, got {res}"
    calls.clear()
    passed, why = run_case(
        {"id": "tt_broken", "tool": "broken", "args": {}, "expected_status": "ok", "expected_fields": {"x": 1}},
        services_module=new_svc,
    )
    assert not passed and "bug inside the tool" in why, why
    assert len(calls) == 1, f"a failing tool must run once, ran {len(calls)} times"
    try:
        validate_case(dict(state_err, expected_error="NOT_FOUND"), {"send_code"}, ("NOT_IDENTIFIED",))
        raise AssertionError("Expected CaseError for a code outside the agent's ERROR_CODES")
    except CaseError:
        pass

    print("OK (tool_tests self-test)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Strict local YAML tool-test runner (no cloud)"
    )
    p.add_argument("--file", default=str(DEFAULT_FILE))
    p.add_argument("--evals-dir", default="")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--json", default="")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)
    if a.self_test:
        return self_test()
    target = a.evals_dir if a.evals_dir else a.file
    cases = load_tool_tests(target)
    runs = [run_tool_tests(cases) for _ in range(max(1, a.repeats))]
    final = majority(runs)
    for r in final:
        mark = "PASS" if r["status"] == "pass" else "FAIL"
        line = f"{mark} {r['test_id']} ({r['runs_passed']}/{r['runs']})"
        print(line + (f" -- {r['failure_reason']}" if r["failure_reason"] else ""))
    n_pass = sum(r["status"] == "pass" for r in final)
    print(f"{n_pass}/{len(final)} tool tests pass (majority of {len(runs)} run(s))")
    if a.json:
        Path(a.json).write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    return 0 if n_pass == len(final) else 1


if __name__ == "__main__":
    sys.exit(main())
