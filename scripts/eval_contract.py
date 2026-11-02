#!/usr/bin/env python3
"""Static contract checker between dev evaluations and lib/fakes.py.

Verifies that credential codes (first-try PINs/OTPs, retry codes, and explicit
wrong codes) and caller identifiers referenced in dev evaluations are handled
consistently by `lib/fakes.py`.

Never inspects `bench-holdout/`.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


_CLAUSE_SPLIT_RE = re.compile(
    r";\s*|\.\s+|\n+|,\s*(?=(?:then|and\s+then|when|after|on\s+retry|second)\b)",
    re.IGNORECASE,
)

_WRONG_MARKER_RE = re.compile(
    r"(?:^|[^A-Za-z])(?:wrong|incorrect|invalid|bad|fail(?:s|ing)?|rejected|not\s+found|nonexistent|unknown)(?:[^A-Za-z]|$)",
    re.IGNORECASE,
)

_RETRY_MARKER_RE = re.compile(
    r"(?:^|[^A-Za-z])(?:retry|retried|second\s+attempt|second\s+try|try\s+again|when\s+prompted\s+to\s+retry|on\s+retry|subsequent)(?:[^A-Za-z]|$)",
    re.IGNORECASE,
)

_CODE_CONTEXT_RE = re.compile(
    r"(?:^|[^A-Za-z])(?:pin|otp|code|passcode|verification)(?:[^A-Za-z]|$)",
    re.IGNORECASE,
)

_CODE_TOKEN_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")

_PHONE_DASH_RE = re.compile(r"\b(\d{3}-\d{3}-\d{4})\b")
_PHONE_PAREN_RE = re.compile(r"(\(\d{3}\)\s*\d{3}-\d{4})")
_PHONE_KV_RE = re.compile(
    r"\bphone(?:[_\s-]*number)?\s*[:=-]\s*['\"]?(\d{10}|\d{3}-\d{3}-\d{4})['\"]?",
    re.IGNORECASE,
)
_ACCOUNT_ID_RE = re.compile(r"\b(ACC?-\d{3,10}|A\d{4,10})\b")
_ACCOUNT_KV_RE = re.compile(
    r"\baccount(?:[_\s-]*(?:id|number|num|#))?\s*[:=-]\s*['\"]?([A-Za-z]{1,6}-?\d{3,10})['\"]?",
    re.IGNORECASE,
)
_CARD_RE = re.compile(
    r"\b(?:visa|mastercard|amex|credit\s+card|debit\s+card|card)\b[^\d\n]*?\b\d{4,16}\b|\b(?:ending\s+in|last\s*4)\s*[:=-]?\s*['\"]?\d{4}\b",
    re.IGNORECASE,
)


def _assert_not_holdout(evals_dir: Path) -> None:
    for part in Path(evals_dir).parts:
        if "holdout" in part.lower():
            raise ValueError(
                f"eval_contract must never inspect bench-holdout/ (got {evals_dir})"
            )


def _load_fakes_module(fakes_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("_eval_contract_fakes", fakes_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load fakes module from {fakes_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_eval_contract_fakes"] = module
    spec.loader.exec_module(module)
    return module


def _flatten_user_facts(user_facts: Any) -> list[str]:
    lines: list[str] = []
    if isinstance(user_facts, dict):
        if "name" in user_facts and "value" in user_facts and len(user_facts) == 2:
            lines.append(f"{user_facts['name']}: {user_facts['value']}")
        else:
            for k, v in user_facts.items():
                if isinstance(v, (list, tuple)):
                    for item in v:
                        lines.append(f"{k}: {item}")
                else:
                    lines.append(f"{k}: {v}")
    elif isinstance(user_facts, list):
        for item in user_facts:
            if isinstance(item, dict):
                if "name" in item and "value" in item:
                    lines.append(f"{item['name']}: {item['value']}")
                else:
                    for k, v in item.items():
                        lines.append(f"{k}: {v}")
            elif item is not None:
                lines.append(str(item))
    elif isinstance(user_facts, str) and user_facts.strip():
        lines.append(user_facts)
    return lines


def _flatten_turns(eval_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    turns = (
        eval_data.get("turns")
        or (eval_data.get("golden") or {}).get("turns")
        or (eval_data.get("scenario") or {}).get("turns")
        or []
    )
    if not isinstance(turns, list):
        return lines
    for turn in turns:
        if isinstance(turn, dict):
            for key in ("user", "userInput", "user_input", "text", "utterance"):
                val = turn.get(key)
                if isinstance(val, str) and val.strip():
                    lines.append(val)
                elif isinstance(val, dict) and isinstance(val.get("text"), str):
                    lines.append(val["text"])
            for step in turn.get("steps") or []:
                if isinstance(step, dict):
                    ui = step.get("userInput") or step.get("user_input")
                    if isinstance(ui, dict) and isinstance(ui.get("text"), str):
                        lines.append(ui["text"])
                    elif isinstance(ui, str) and ui.strip():
                        lines.append(ui)
        elif isinstance(turn, str) and turn.strip():
            lines.append(turn)
    return lines


def extract_eval_facts(eval_data: dict[str, Any]) -> dict[str, set[str]]:
    """Extract credential codes and caller identifiers from an evaluation JSON."""
    scenario = eval_data.get("scenario") or eval_data.get("simulation") or {}
    raw_user_facts = (
        scenario.get("userFacts")
        if "userFacts" in scenario
        else scenario.get("user_facts", eval_data.get("userFacts", eval_data.get("user_facts")))
    )
    user_fact_lines = _flatten_user_facts(raw_user_facts)
    task_text = str(
        scenario.get("task")
        or scenario.get("userGoal")
        or scenario.get("goal")
        or eval_data.get("task")
        or ""
    )
    turn_lines = _flatten_turns(eval_data)

    wrong_codes: set[str] = set()
    retry_codes: set[str] = set()
    first_try_codes: set[str] = set()
    user_fact_identifiers: set[str] = set()
    task_identifiers: set[str] = set()

    def _scan_text(text: str, *, from_user_facts: bool) -> None:
        for clause in _CLAUSE_SPLIT_RE.split(text):
            clause = clause.strip()
            if not clause:
                continue
            is_wrong = bool(_WRONG_MARKER_RE.search(clause))
            is_retry = bool(_RETRY_MARKER_RE.search(clause))

            # Identifier extraction (skip explicitly wrong/unknown identifiers)
            if not is_wrong:
                target_set = user_fact_identifiers if from_user_facts else task_identifiers
                for m in _PHONE_DASH_RE.finditer(clause):
                    target_set.add(m.group(1))
                for m in _PHONE_PAREN_RE.finditer(clause):
                    target_set.add(m.group(1))
                for m in _PHONE_KV_RE.finditer(clause):
                    target_set.add(m.group(1))
                for m in _ACCOUNT_ID_RE.finditer(clause):
                    target_set.add(m.group(1))
                for m in _ACCOUNT_KV_RE.finditer(clause):
                    target_set.add(m.group(1))

            # Code extraction when clause mentions PIN/OTP/code context
            if _CODE_CONTEXT_RE.search(clause):
                # Strip phone numbers and account IDs before scanning for 4-8 digit codes
                cleaned = _PHONE_DASH_RE.sub(" ", clause)
                cleaned = _PHONE_PAREN_RE.sub(" ", cleaned)
                cleaned = _PHONE_KV_RE.sub(" ", cleaned)
                cleaned = _ACCOUNT_ID_RE.sub(" ", cleaned)
                cleaned = _ACCOUNT_KV_RE.sub(" ", cleaned)
                cleaned = _CARD_RE.sub(" ", cleaned)
                for m in _CODE_TOKEN_RE.finditer(cleaned):
                    code = m.group(1)
                    if is_wrong and not is_retry:
                        wrong_codes.add(code)
                    elif is_retry:
                        retry_codes.add(code)
                    else:
                        first_try_codes.add(code)

    for line in user_fact_lines:
        _scan_text(line, from_user_facts=True)
    if task_text:
        _scan_text(task_text, from_user_facts=False)
    for line in turn_lines:
        _scan_text(line, from_user_facts=False)

    first_try_codes -= wrong_codes
    first_try_codes -= retry_codes
    if wrong_codes and first_try_codes:
        retry_codes |= first_try_codes
        first_try_codes = set()

    return {
        "wrong_codes": wrong_codes,
        "retry_codes": retry_codes,
        "first_try_codes": first_try_codes,
        "user_fact_identifiers": user_fact_identifiers,
        "task_identifiers": task_identifiers,
        "identifiers": user_fact_identifiers | task_identifiers,
    }


def _only_digits(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch.isdigit())


def _call_login_code_accepted(
    fakes_mod: Any,
    code: str,
    *,
    attempt: int,
    always_wrong: set[str],
    valid_codes: set[str],
    state: dict[str, Any] | None = None,
) -> bool:
    norm_fn = getattr(
        fakes_mod,
        "normalize_code",
        getattr(fakes_mod, "only_digits", _only_digits),
    )
    digits = norm_fn(code)
    login_fn = getattr(fakes_mod, "login_code_accepted", None)

    if callable(login_fn):
        sig = inspect.signature(login_fn)
        params = list(sig.parameters.values())
        param_names = [p.name for p in params]
        kwargs: dict[str, Any] = {}
        if "attempts" in param_names:
            kwargs["attempts"] = attempt
        elif "attempt" in param_names:
            kwargs["attempt"] = attempt
        elif "strict" in param_names:
            kwargs["strict"] = (attempt >= 1)
        if "state" in param_names:
            kwargs["state"] = state

        scope_cm = getattr(fakes_mod, "fixture_state_scope", None)
        if callable(scope_cm):
            with scope_cm(state):
                accepted = bool(login_fn(code, **kwargs))
        else:
            accepted = bool(login_fn(code, **kwargs))

        if attempt >= 1 and valid_codes:
            accepted = accepted and (digits in valid_codes or code in valid_codes)
        if not accepted and state:
            fx_p = norm_fn(state.get("fx_pin_on_file", ""))
            fx_o = norm_fn(state.get("fx_otp_on_file", ""))
            if (fx_p and digits == fx_p) or (fx_o and digits == fx_o):
                accepted = True
        return accepted

    if digits in always_wrong or code in always_wrong or len(digits) < 4:
        return False
    if state and (state.get("fx_pin_on_file") == code or state.get("fx_pin_on_file") == digits):
        return True
    if state and (state.get("fx_otp_on_file") == code or state.get("fx_otp_on_file") == digits):
        return True
    if attempt >= 1 and valid_codes:
        return digits in valid_codes or code in valid_codes
    return True


def _identifier_in_accounts(ident: str, accounts: Any, norm_fn: Any) -> bool:
    raw = str(ident).strip()
    digits = norm_fn(raw)
    if isinstance(accounts, dict):
        if raw in accounts or (digits and digits in accounts):
            return True
        for k, v in accounts.items():
            if raw.upper() == str(k).upper() or (digits and digits == norm_fn(str(k))):
                return True
            if isinstance(v, dict):
                for field_val in v.values():
                    f_str = str(field_val)
                    if raw.upper() == f_str.upper() or (
                        digits and len(digits) >= 4 and digits == norm_fn(f_str)
                    ):
                        return True
            elif raw in str(v) or (digits and digits in str(v)):
                return True
        return False
    if isinstance(accounts, (list, tuple, set, frozenset)):
        for item in accounts:
            if isinstance(item, dict):
                for field_val in item.values():
                    f_str = str(field_val)
                    if raw.upper() == f_str.upper() or (
                        digits and len(digits) >= 4 and digits == norm_fn(f_str)
                    ):
                        return True
            elif raw in str(item) or (digits and digits in str(item)):
                return True
        return False
    return True


_STARTER_DEFAULT_PINS = frozenset({"1234", "5678"})
_STARTER_DEFAULT_OTPS = frozenset({"123456", "246810", "384920", "482913"})


def _is_uncustomized_starter_fakes(
    fakes_mod: Any, valid_pins: set[str], valid_otps: set[str]
) -> bool:
    """Return True when fakes_mod is the unmodified starter scaffold from kickstart.py."""
    if not hasattr(fakes_mod, "SPOKEN_LINES"):
        return False
    if valid_pins != set(_STARTER_DEFAULT_PINS):
        return False
    if not valid_otps or not valid_otps.issubset(_STARTER_DEFAULT_OTPS):
        return False
    return True


def check_eval_contract(
    evals_dir: Path,
    fakes_path: Path,
    *,
    strict_retry: bool | None = None,
) -> list[dict[str, str]]:
    """Check dev evaluations against `lib/fakes.py` and return a list of violations."""
    evals_dir = Path(evals_dir)
    fakes_path = Path(fakes_path)
    _assert_not_holdout(evals_dir)

    if not evals_dir.exists() or not fakes_path.exists():
        return []

    fakes_mod = _load_fakes_module(fakes_path)
    always_wrong = {
        str(x) for x in getattr(fakes_mod, "ALWAYS_WRONG_LOGIN_CODES", set()) or set()
    }
    valid_pins = {str(x) for x in getattr(fakes_mod, "VALID_PINS", set()) or set()}
    valid_otps = {str(x) for x in getattr(fakes_mod, "VALID_OTPS", set()) or set()}
    valid_codes = valid_pins | valid_otps
    accounts = getattr(fakes_mod, "ACCOUNTS", None)
    norm_fn = getattr(
        fakes_mod,
        "normalize_code",
        getattr(fakes_mod, "only_digits", _only_digits),
    )
    lookup_fn = getattr(
        fakes_mod,
        "lookup_account_record",
        getattr(fakes_mod, "find_account", None),
    )
    enforce_strict_retry = (
        strict_retry
        if strict_retry is not None
        else not _is_uncustomized_starter_fakes(fakes_mod, valid_pins, valid_otps)
    )

    violations: list[dict[str, str]] = []
    eval_files = sorted(evals_dir.rglob("*.json"))

    for eval_file in eval_files:
        _assert_not_holdout(eval_file)
        try:
            data = json.loads(eval_file.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append(
                {
                    "eval_id": eval_file.stem,
                    "file": str(eval_file),
                    "kind": "INVALID_JSON",
                    "value": "",
                    "reason": f"Failed to parse JSON: {exc}",
                }
            )
            continue

        if not isinstance(data, dict):
            continue

        eval_id = str(data.get("displayName") or data.get("id") or eval_file.stem)
        facts = extract_eval_facts(data)

        scenario = data.get("scenario") or data.get("simulation") or {}
        var_overrides = (
            scenario.get("variableOverrides")
            or data.get("variableOverrides")
            or {}
        )
        if not isinstance(var_overrides, dict):
            var_overrides = {}

        FORBIDDEN_OVERRIDE_KEYS = frozenset({
            "identified",
            "auth_status",
            "logged_in",
            "verified",
            "auth_failure_count",
            "login_channel",
        })
        forbidden = sorted(k for k in var_overrides if k in FORBIDDEN_OVERRIDE_KEYS)
        if forbidden:
            violations.append(
                {
                    "eval_id": eval_id,
                    "file": str(eval_file),
                    "kind": "FORBIDDEN_VARIABLE_OVERRIDE",
                    "value": ", ".join(forbidden),
                    "reason": (
                        f"variableOverrides in {eval_id} contains forbidden non-backend "
                        f"facts: {forbidden}"
                    ),
                }
            )

        eval_valid_codes = set(valid_codes)
        if var_overrides.get("fx_pin_on_file"):
            eval_valid_codes.add(str(var_overrides["fx_pin_on_file"]))
            eval_valid_codes.add(norm_fn(str(var_overrides["fx_pin_on_file"])))
        if var_overrides.get("fx_otp_on_file"):
            eval_valid_codes.add(str(var_overrides["fx_otp_on_file"]))
            eval_valid_codes.add(norm_fn(str(var_overrides["fx_otp_on_file"])))

        for code in sorted(facts["first_try_codes"]):
            digits = norm_fn(code)
            in_wrong = code in always_wrong or digits in always_wrong
            accepted = _call_login_code_accepted(
                fakes_mod,
                code,
                attempt=0,
                always_wrong=always_wrong,
                valid_codes=eval_valid_codes,
                state=var_overrides,
            )
            if in_wrong or not accepted:
                violations.append(
                    {
                        "eval_id": eval_id,
                        "file": str(eval_file),
                        "kind": "FIRST_TRY_CODE_REJECTED",
                        "value": code,
                        "reason": (
                            f"First-try code {code!r} in {eval_id} is rejected on attempt 1 "
                            f"by {fakes_path}"
                        ),
                    }
                )

        for code in sorted(facts["retry_codes"]):
            digits = norm_fn(code)
            in_wrong = code in always_wrong or digits in always_wrong
            accepted_attempt0 = _call_login_code_accepted(
                fakes_mod,
                code,
                attempt=0,
                always_wrong=always_wrong,
                valid_codes=eval_valid_codes,
                state=var_overrides,
            )
            accepted_retry = (
                _call_login_code_accepted(
                    fakes_mod,
                    code,
                    attempt=1,
                    always_wrong=always_wrong,
                    valid_codes=eval_valid_codes,
                    state=var_overrides,
                )
                if enforce_strict_retry
                else accepted_attempt0
            )
            in_valid_sets = (
                ((not eval_valid_codes) or (code in eval_valid_codes or digits in eval_valid_codes))
                if enforce_strict_retry
                else True
            )
            if in_wrong or not accepted_attempt0 or not accepted_retry or not in_valid_sets:
                violations.append(
                    {
                        "eval_id": eval_id,
                        "file": str(eval_file),
                        "kind": "RETRY_CODE_REJECTED",
                        "value": code,
                        "reason": (
                            f"Retry code {code!r} in {eval_id} is rejected on attempt 2 "
                            f"(strict/VALID_PINS|VALID_OTPS) by {fakes_path}"
                        ),
                    }
                )

        for code in sorted(facts["wrong_codes"]):
            digits = norm_fn(code)
            in_wrong = code in always_wrong or digits in always_wrong
            accepted = _call_login_code_accepted(
                fakes_mod,
                code,
                attempt=0,
                always_wrong=always_wrong,
                valid_codes=eval_valid_codes,
                state=var_overrides,
            )
            if not in_wrong and accepted:
                violations.append(
                    {
                        "eval_id": eval_id,
                        "file": str(eval_file),
                        "kind": "WRONG_CODE_ACCEPTED",
                        "value": code,
                        "reason": (
                            f"Explicit wrong code {code!r} in {eval_id} is not in "
                            f"ALWAYS_WRONG_LOGIN_CODES and is accepted by {fakes_path}"
                        ),
                    }
                )

        if accounts is not None or callable(lookup_fn):
            for ident in sorted(facts["identifiers"]):
                in_acc = _identifier_in_accounts(ident, accounts, norm_fn) if accounts else False
                resolved_by_fn = bool(callable(lookup_fn) and lookup_fn(ident) is not None)
                if not in_acc and not resolved_by_fn:
                    violations.append(
                        {
                            "eval_id": eval_id,
                            "file": str(eval_file),
                            "kind": "UNKNOWN_IDENTIFIER",
                            "value": ident,
                            "reason": (
                                f"Identifier {ident!r} in {eval_id} does not "
                                f"resolve in {fakes_path}"
                            ),
                        }
                    )

    return violations


def _run_self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakes_file = root / "fakes.py"
        fakes_file.write_text(
            "ACCOUNTS = {\n"
            '    "ACC-1001": {"account_id": "ACC-1001", "phone": "2025550143", "first_name": "Jordan"},\n'
            '    "ACC-1002": {"account_id": "ACC-1002", "phone": "2025550198", "first_name": "Taylor"},\n'
            "}\n"
            'VALID_PINS = frozenset({"1234", "5678"})\n'
            'VALID_OTPS = frozenset({"123456", "654321"})\n'
            'ALWAYS_WRONG_LOGIN_CODES = frozenset({"0000", "000000", "9999", "999999"})\n'
            "def normalize_code(code: str) -> str:\n"
            '    return "".join(ch for ch in str(code or "") if ch.isdigit())\n'
            "def login_code_accepted(code: str, attempts: int = 0) -> bool:\n"
            "    digits = normalize_code(code)\n"
            "    if digits in ALWAYS_WRONG_LOGIN_CODES or len(digits) < 4:\n"
            "        return False\n"
            "    if attempts >= 1:\n"
            "        return digits in (VALID_PINS | VALID_OTPS)\n"
            "    return True\n",
            encoding="utf-8",
        )

        evals_dir = root / "bench" / "dev" / "evaluations"
        evals_dir.mkdir(parents=True)

        # 1. Valid eval
        valid_eval = evals_dir / "sim_valid" / "sim_valid.json"
        valid_eval.parent.mkdir(parents=True)
        valid_eval.write_text(
            json.dumps(
                {
                    "displayName": "sim_valid",
                    "scenario": {
                        "task": (
                            "Check account balance. If asked for a PIN, first enter '9999' "
                            "(which is incorrect); when prompted to retry, enter '5678'."
                        ),
                        "userFacts": ["Phone: 202-555-0143", "Account ID: ACC-1001"],
                    },
                }
            ),
            encoding="utf-8",
        )
        assert check_eval_contract(evals_dir, fakes_file) == []

        # 2. Drift: retry PIN not in VALID_PINS, wrong code accepted, unknown account
        drift_eval = evals_dir / "sim_drift" / "sim_drift.json"
        drift_eval.parent.mkdir(parents=True)
        drift_eval.write_text(
            json.dumps(
                {
                    "displayName": "sim_drift",
                    "scenario": {
                        "task": (
                            "If asked for a PIN, first enter '7777' (which is incorrect); "
                            "when prompted to retry, enter the PIN '2468'."
                        ),
                        "userFacts": ["Account ID: ACC-9999", "First try code: 0000"],
                    },
                }
            ),
            encoding="utf-8",
        )
        violations = check_eval_contract(evals_dir, fakes_file)
        kinds = {v["kind"] for v in violations}
        assert "RETRY_CODE_REJECTED" in kinds, f"Expected RETRY_CODE_REJECTED in {kinds}"
        assert "WRONG_CODE_ACCEPTED" in kinds, f"Expected WRONG_CODE_ACCEPTED in {kinds}"
        assert "UNKNOWN_IDENTIFIER" in kinds, f"Expected UNKNOWN_IDENTIFIER in {kinds}"

        # 3. Holdout guard
        try:
            check_eval_contract(root / "bench-holdout" / "evaluations", fakes_file)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for bench-holdout path")

    print("eval_contract self-test: PASSED")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that dev evaluations and lib/fakes.py agree on credentials and accounts."
    )
    parser.add_argument(
        "--evals-dir",
        default="bench/dev/evaluations",
        help="Path to dev evaluations directory (default: bench/dev/evaluations).",
    )
    parser.add_argument(
        "--fakes",
        default="lib/fakes.py",
        help="Path to fakes.py module (default: lib/fakes.py).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in unit self-tests.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    evals_dir = Path(args.evals_dir)
    fakes_path = Path(args.fakes)

    try:
        _assert_not_holdout(evals_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not evals_dir.exists():
        print(f"Notice: evaluations directory {evals_dir} not found; skipping eval contract check.")
        return 0
    if not fakes_path.exists():
        print(f"Notice: fakes module {fakes_path} not found; skipping eval contract check.")
        return 0

    violations = check_eval_contract(evals_dir, fakes_path)
    if not violations:
        print(f"eval_contract: OK ({evals_dir} vs {fakes_path})")
        return 0

    print(
        f"eval_contract: FAILED with {len(violations)} violation(s) "
        f"between {evals_dir} and {fakes_path}:",
        file=sys.stderr,
    )
    for v in violations:
        print(
            f"  - [{v['kind']}] {v['eval_id']} ({v['file']}): {v['reason']}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
