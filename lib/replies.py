"""Standardized reply shapes and error responses for CXAS tools."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
import sys
from typing import Any

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.copy import LOCALIZED_ERROR_DEFAULTS, resolve_copy_locale


class _StatusStr(str):
    """String status value that compares equal case-insensitively ('ok' == 'OK')."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.lower() == other.lower()
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.lower() != other.lower()
        return super().__ne__(other)

    def __hash__(self) -> int:
        return super().__hash__()


OK_STATUS = _StatusStr("ok")
ERROR_STATUS = _StatusStr("error")

ERROR_CODES: tuple[str, ...] = (
    "INVALID_INPUT",
    "NOT_FOUND",
    "NOT_IDENTIFIED",
    "NOT_LOGGED_IN",
    "CODE_NOT_SENT",
    "WRONG_CODE",
    "WRONG_PIN",
    "TOO_MANY_ATTEMPTS",
    "LOCKED_OUT",
    "CARD_DECLINED",
    "PAYMENT_DECLINED",
    "INELIGIBLE",
    "NOT_ELIGIBLE",
    "ALREADY_PROCESSED",
    "ALREADY_APPLIED",
    "ALREADY_ENROLLED",
    "OUT_OF_WINDOW",
    "OUTAGE_ACTIVE",
    "LIMIT_EXCEEDED",
    "REFUND_THRESHOLD_EXCEEDED",
    "CANNOT_CANCEL_EN_ROUTE",
    "BLOCKED_CALLER",
    "PERMISSION_DENIED",
    "MISSING_INPUT",
    "INVALID_FORMAT",
    "NOT_AUTHENTICATED",
    "PAST_DUE_BALANCE_REQUIRED",
    "REQUIRES_CONFIRMATION",
    "BUSINESS_ACCOUNT_HANDOFF",
    "CONFIRMATION_REQUIRED",
    "REQUIRES_ESCALATION",
    "MALFORMED_REQUEST",
    "SERVICE_TYPE_REQUIRED",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",
    "SYSTEM_DOWN",
    "UNKNOWN_PLAN_ID",
    "CODE_NOT_RECEIVED",
    "CARD_CAPTURE_REQUIRED",
    "INVALID_CARD_DIGITS",
    "NO_MOBILE_ON_FILE",
)

ERROR_CODE_DEFAULTS: dict[str, tuple[str, str]] = dict(LOCALIZED_ERROR_DEFAULTS["en-US"])


def tracking_id(prefix: str, *parts: object) -> str:
    """Return a deterministic short reference number (R followed by 6 digits)."""
    raw = "|".join([prefix, *(str(value).strip().lower() for value in parts)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)


def normalize_money_str(amount: str | int | float | Decimal) -> str:
    """Parse human/ASR money input (including French decimal comma) into a canonical decimal string."""
    if amount is None or isinstance(amount, bool):
        raise ValueError(f"Unsupported amount: {amount!r}")
    if isinstance(amount, float) and (amount != amount or amount in (float("inf"), float("-inf"))):
        raise ValueError(f"Non-finite amount: {amount!r}")
    if isinstance(amount, (int, float, Decimal)):
        d = Decimal(str(amount))
        if not d.is_finite():
            raise ValueError(f"Non-finite amount: {amount!r}")
        return str(d)
    s = str(amount).strip()
    if not s:
        raise ValueError("Empty amount")
    # Strip currency symbols and codes ($, CAD, USD, EUR) at edges
    s = re.sub(r"(?i)\b(?:cad|usd|eur|dollars?)\b", "", s)
    s = s.replace("$", "").replace("\u00a0", " ").strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(" ", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+", s):
            # 1,000 -> 1000
            s = s.replace(",", "")
        elif re.search(r",\d{1,2}$", s):
            # 15,00 or 9 876,50 -> comma as decimal separator
            s = s.replace(" ", "")
            idx = s.rfind(",")
            s = s[:idx].replace(",", "") + "." + s[idx + 1 :]
        else:
            raise ValueError(f"Invalid comma amount: {amount!r}")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        raise ValueError(f"Malformed numeric amount: {amount!r}")
    return s


def display_amount(value: Any) -> str:
    """Format money for speech: 12.5 -> "12.50" (two decimals, half-up rounding)."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not an amount: {value!r}")
    try:
        norm = normalize_money_str(value)
        amount = Decimal(norm)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"not an amount: {value!r}")
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def ok_reply(
    data: dict[str, Any] | None = None,
    reference: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Build a success reply envelope."""
    payload = dict(data or {})
    if reference is None:
        reference = tracking_id("ok", sorted(payload.keys()))
    reply: dict[str, Any] = {
        "status": OK_STATUS,
        "data": payload,
        "error_message": "",
        "tracking_id": reference,
    }
    if language is not None:
        reply["active_language"] = resolve_copy_locale(language)
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "spoken_line",
        "spoken_summary",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
        "must_escalate_immediately",
        "requested_card_last4",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply


def error_reply(
    code: str,
    message: str = "",
    agent_action: str = "",
    reference: str | None = None,
    data: dict[str, Any] | None = None,
    language: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an error reply envelope with localized messaging."""
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code {code!r}; add it to ERROR_CODES first")
    if not language:
        if state and callable(getattr(state, "get", None)):
            language = (
                state.get("explicit_language_switch")
                or state.get("fx_language")
                or state.get("language")
                or state.get("preferred_language")
            )
        elif data and callable(getattr(data, "get", None)):
            language = (
                data.get("explicit_language_switch")
                or data.get("fx_language")
                or data.get("language")
                or data.get("preferred_language")
            )
    loc = resolve_copy_locale(language)
    loc_defaults = LOCALIZED_ERROR_DEFAULTS.get(loc, LOCALIZED_ERROR_DEFAULTS["en-US"])
    default_msg, default_action = loc_defaults.get(
        code,
        LOCALIZED_ERROR_DEFAULTS["en-US"].get(
            code,
            ("The request could not be completed.", "Explain the issue to the caller."),
        ),
    )
    msg = message or default_msg
    action = agent_action or default_action
    if reference is None:
        reference = tracking_id("error", code, msg)
    payload = dict(data or {})
    reply: dict[str, Any] = {
        "status": ERROR_STATUS,
        "error": code,
        "data": payload,
        "error_message": msg,
        "agent_action": action,
        "tracking_id": reference,
        "active_language": loc,
    }
    if "lockout_triggered" in payload:
        reply["lockout_triggered"] = payload["lockout_triggered"]
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "spoken_line",
        "spoken_summary",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
        "must_escalate_immediately",
        "requested_card_last4",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply
