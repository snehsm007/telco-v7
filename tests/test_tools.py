"""Tests for cxas_app/tools wrappers and core tool functions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import re
import pytest

import cxas_app.tools.browse_plans_and_coverage.python_function.python_code as browse_tool
import cxas_app.tools.check_regional_outage.python_function.python_code as outage_tool
import cxas_app.tools.get_billing_summary.python_function.python_code as billing_tool
import cxas_app.tools.handover_to_person.python_function.python_code as handover_tool
import cxas_app.tools.lookup_account.python_function.python_code as lookup_tool
import cxas_app.tools.send_login_code.python_function.python_code as send_code_tool
import cxas_app.tools.verify_login.python_function.python_code as verify_login_tool
from lib.services import (
    ALL_TOOLS,
    handover_to_person,
    lookup_account,
    record_payment_attempt,
    send_login_code,
    verify_login,
)


def test_three_strike_login_lockout_and_direct_code_entry(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0143", "fx_pin_on_file": "4321"})
    for mod in (
        lookup_tool,
        send_code_tool,
        verify_login_tool,
        handover_tool,
        billing_tool,
        outage_tool,
        browse_tool,
    ):
        monkeypatch.setattr(mod, "context", session, raising=False)

    # Placeholder code does not consume strikes
    r_place = verify_login_tool.verify_login("0000")
    assert r_place["error"] == "CODE_NOT_RECEIVED"
    assert r_place["data"]["attempts_remaining"] == 3

    # 3 strikes with real wrong code in verify_login wrapper
    r1 = verify_login_tool.verify_login("9999")
    r2 = verify_login_tool.verify_login("9999")
    r3 = verify_login_tool.verify_login("9999")
    assert r1["data"]["attempts_remaining"] == 2
    assert r2["data"]["attempts_remaining"] == 1
    assert r3["error"] == "TOO_MANY_ATTEMPTS"
    assert r3["data"]["lockout_triggered"] is True

    # Direct login without prior send_login_code on an identified state
    fresh = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(verify_login_tool, "context", fresh, raising=False)
    ok = verify_login_tool.verify_login("1234")
    assert ok["status"] == "ok" and ok["data"]["verified"] is True
    assert verify_login(code="1234", state={"account_id": "A1001"})["status"] == "ok"


def test_domain_tool_wrappers_with_mock_context(monkeypatch) -> None:
    state = {
        "account_id": "A1001",
        "phone_last4": "0143",
        "auth_status": "pass",
        "current_balance": "85.50",
    }
    session = SimpleNamespace(state=state)
    for mod in (billing_tool, outage_tool, browse_tool):
        monkeypatch.setattr(mod, "context", session, raising=False)

    # Billing tool wrapper
    bill_res = billing_tool.get_billing_summary()
    assert bill_res["status"] == "ok"
    assert "current_balance" in bill_res["data"]

    # Outage tool wrapper
    outage_res = outage_tool.check_regional_outage(postal_code="H3Z 2Y7")
    assert outage_res["status"] == "ok"
    assert outage_res["data"]["outage_active"] is True

    # Browse plans tool wrapper
    browse_res = browse_tool.browse_plans_and_coverage(category="internet")
    assert browse_res["status"] == "ok"
    assert len(browse_res["data"]["shortlisted_plans"]) >= 2


def test_handover_language_detection_and_payment_lockout() -> None:
    r_fr = handover_to_person(reason="besoin d'un agent", language="fr-CA")
    assert "transfère" in r_fr["data"].get("handoff_message", "") or "représentant" in r_fr["data"].get("handoff_message", "")

    state_es = {"language": "es-US"}
    r_es = handover_to_person(reason="billing", state=state_es)
    assert r_es["data"]["language"] == "es-US"
    assert "transfiero" in r_es["data"].get("handoff_message", "") or "representante" in r_es["data"].get("handoff_message", "")
    explicit = handover_to_person(reason="billing", language="en-US", state={"language": "es-US"})
    assert explicit["data"]["language"] == "es-US"

    pay_state: dict[str, Any] = {}
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    assert record_payment_attempt(pay_state, False)["error"] == "TOO_MANY_ATTEMPTS"


def _find_multilingual_keys(obj: Any, path: str = "") -> list[str]:
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else str(k)
            if str(k).endswith(("_en", "_fr", "_es")):
                bad.append(current_path)
            bad.extend(_find_multilingual_keys(v, current_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            bad.extend(_find_multilingual_keys(item, f"{path}[{i}]"))
    return bad


@pytest.mark.parametrize("lang", ["en-US", "fr-CA", "es-US"])
def test_all_22_tools_no_multilingual_keys_leak(lang: str) -> None:
    from lib import services

    sample_args: dict[str, dict[str, Any]] = {
        "lookup_account": {"identifier": "555-123-4567"},
        "send_login_code": {"destination": "555-123-4567"},
        "verify_login": {"code": "1234"},
        "handover_to_person": {"department": "billing", "reason": "complex billing issue"},
        "get_billing_summary": {},
        "process_bill_payment": {"amount": "50.00", "payment_method_id": "CARD-1"},
        "setup_payment_arrangement": {"arrangement_date": "2026-11-15", "installments": 2},
        "setup_autopay": {"action": "enroll", "payment_method_id": "CARD-1"},
        "process_refund_or_dispute": {"charge_id": "CHG-101", "reason": "unrecognized_charge"},
        "check_regional_outage": {"postal_code": "H3Z 2Y7"},
        "run_troubleshooting_and_sms": {"service_type": "internet", "symptom": "slow_speed"},
        "get_appointment_and_ticket_status": {},
        "manage_appointment": {"action": "reschedule", "selected_slot": "SLOT-1"},
        "browse_plans_and_coverage": {"category": "internet"},
        "commit_plan_or_order": {"plan_id": "NET-PLUS", "confirmed": True},
        "initiate_number_transfer": {
            "phone_to_transfer": "555-123-4567",
            "current_carrier": "OtherCarrier",
            "carrier_account_number": "ACC-123",
            "port_pin": "1234",
        },
        "manage_warranty_claim": {"issue_description": "broken screen", "claim_type": "repair"},
        "send_password_reset_sms": {"phone_number": "555-123-4567"},
        "manage_mfa_settings": {"action": "status"},
        "execute_suspend_restore": {"action": "suspend"},
        "update_contact_profile": {"email": "test@example.com"},
        "cancel_or_port_out_service": {"action": "cancel", "confirmed": True},
    }

    assert len(services.ALL_TOOLS) == 22
    for tool_name in services.ALL_TOOLS:
        fn = getattr(services, f"{tool_name}_impl")
        args = sample_args.get(tool_name, {})
        state = {
            "auth_status": "pass",
            "account_id": "A1001",
            "phone_last4": "0143",
            "language": lang,
            "active_appointment_id": "APT-4021",
        }
        res = fn(**args, state=state, language=lang)
        bad_keys = _find_multilingual_keys(res)
        assert not bad_keys, f"Tool {tool_name} leaked multilingual keys in locale {lang}: {bad_keys}"


EXCLUDED_AUDIT_KEY_PATTERNS = {
    "_id", "_code", "_number", "_last4", "_pin", "_date", "_time",
    "_amount", "_balance", "_rate", "_fee", "_price", "_tax", "_total",
    "_speed", "_cost", "_status", "_type", "_channel", "_category", "_reason",
    "_name",
}
EXCLUDED_AUDIT_EXACT_KEYS = {
    "status", "error", "error_code", "id", "tracking_id", "reference",
    "account_id", "phone_last4", "card_last4", "bank_last4", "amount",
    "current_balance", "past_due_balance", "destination", "channel",
    "auth_status", "account_status", "service_status", "customer_type",
    "target_queue", "queue_hours_status", "handoff_status", "date",
    "posted_date", "due_date", "new_due_date", "next_draft_date",
    "scheduled_date", "cutoff_date", "selected_slot", "slot_id",
    "confirmation_number", "confirmation_id", "arrangement_id", "appointment_id",
    "ticket_id", "order_id", "charge_id", "plan_id", "request_id",
    "port_in_request_id", "port_out_pin", "transfer_pin", "port_pin",
    "speed_or_data", "download_speed", "upload_speed", "throttled_speed_after_cap",
    "price_display", "new_monthly_price", "estimated_tax", "estimated_total_monthly",
    "monthly_total_with_tax", "shipping_address_on_file", "address", "email", "phone_number",
    "postal_code", "region", "device_model", "warranty_coverage_end",
    "early_termination_fee", "early_cancellation_fee", "final_bill_estimate",
    "prorated_final_bill_estimate", "daily_outage_proration_rate", "statement_total",
    "payments_received", "credits_applied", "amount_due", "duplicate_payment_amount",
    "autopay_discount_monthly", "reduced_rate_monthly", "applied_amount",
    "applied_amount_display", "credit_amount", "amount_paid", "remaining_balance",
    "deferred_amount", "installment_amount", "carrier_account_number",
    "porting_account_number", "current_carrier", "order_type", "payment_method",
    "delivery_channel", "preferred_mfa_channel", "reason", "handoff_reason",
    "category", "action", "claim_type", "symptom", "service_type", "type",
    "issue", "mode", "technician_name",
    # Brand and plan names (proper names)
    "plan_name", "name",
}


def _find_unlocalized_reply_strings(
    en_val: Any,
    loc_val: Any,
    path: str = "",
) -> list[tuple[str, str]]:
    """Traverse and find non-excluded user-facing strings in localized reply matching English."""
    leaks: list[tuple[str, str]] = []
    if isinstance(en_val, dict) and isinstance(loc_val, dict):
        for k in en_val:
            if k not in loc_val:
                continue
            child_path = f"{path}.{k}" if path else str(k)
            key_lower = str(k).lower()
            if key_lower in EXCLUDED_AUDIT_EXACT_KEYS or any(
                key_lower.endswith(p) for p in EXCLUDED_AUDIT_KEY_PATTERNS
            ):
                continue
            # Coordinator directive #162 carve-out: recent_charges[*].name are brand names and remain unchanged.
            if "recent_charges" in child_path and key_lower == "name":
                continue
            leaks.extend(
                _find_unlocalized_reply_strings(en_val[k], loc_val[k], child_path)
            )
    elif isinstance(en_val, list) and isinstance(loc_val, list):
        for i, (item_en, item_loc) in enumerate(zip(en_val, loc_val)):
            leaks.extend(
                _find_unlocalized_reply_strings(item_en, item_loc, f"{path}[{i}]")
            )
    elif isinstance(en_val, str) and isinstance(loc_val, str):
        v_en = en_val.strip()
        v_loc = loc_val.strip()
        if v_en and v_loc and v_en == v_loc:
            # Exclude numbers, currencies, dates, time ranges, alphanumeric tokens, emails, phones
            if not re.match(
                r"^(\$?\d+[\d.,/]*|\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}.*|[A-Z0-9_-]+|.*@.*|\+?\d[\d -]{6,}\d)$",
                v_en,
            ):
                leaks.append((path, v_en))
    return leaks


@pytest.mark.parametrize("target_locale", ["fr-CA", "es-US"])
def test_localization_completeness_audit(target_locale: str) -> None:
    """Audit all 22 tools ensuring no unlocalized strings leak in target locales (PRD BR-TV-004)."""
    from lib import services

    sample_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        ("lookup_account", {"identifier": "555-123-4567"}, {}),
        ("send_login_code", {"destination": "555-123-4567"}, {}),
        ("verify_login", {"code": "1234"}, {}),
        ("handover_to_person", {"department": "billing", "reason": "complex billing issue"}, {}),
        ("get_billing_summary", {}, {}),
        ("get_billing_summary", {}, {"is_suspended": True, "suspension_reason": "non_payment"}),
        ("process_bill_payment", {"amount": "50.00", "payment_method_id": "CARD-1"}, {}),
        ("setup_payment_arrangement", {"arrangement_date": "2026-11-15", "installments": 2}, {}),
        ("setup_autopay", {"action": "enroll", "payment_method_id": "CARD-1"}, {}),
        ("process_refund_or_dispute", {"charge_id": "CHG-101", "reason": "unrecognized_charge"}, {}),
        ("check_regional_outage", {"postal_code": "H3Z 2Y7"}, {}),
        ("run_troubleshooting_and_sms", {"service_type": "internet", "symptom": "slow_speed"}, {}),
        ("get_appointment_and_ticket_status", {}, {}),
        ("manage_appointment", {"action": "reschedule", "selected_slot": "SLOT-1"}, {}),
        ("browse_plans_and_coverage", {"category": "internet"}, {}),
        ("commit_plan_or_order", {"plan_id": "NET-PLUS", "confirmed": True}, {}),
        ("commit_plan_or_order", {"plan_id": "NET-PLUS", "confirmed": False}, {}),
        (
            "initiate_number_transfer",
            {
                "phone_to_transfer": "555-123-4567",
                "current_carrier": "OtherCarrier",
                "carrier_account_number": "ACC-123",
                "port_pin": "1234",
            },
            {},
        ),
        ("manage_warranty_claim", {"issue_description": "broken screen", "claim_type": "repair"}, {}),
        ("send_password_reset_sms", {"phone_number": "555-123-4567"}, {}),
        ("manage_mfa_settings", {"action": "status"}, {}),
        ("execute_suspend_restore", {"action": "suspend"}, {}),
        ("execute_suspend_restore", {"action": "restore"}, {"past_due_balance": "85.50", "current_balance": "85.50"}),
        ("update_contact_profile", {"email": "test@example.com"}, {}),
        ("cancel_or_port_out_service", {"action": "cancel", "confirmed": True}, {}),
    ]

    base_state = {
        "auth_status": "pass",
        "account_id": "A1001",
        "phone_last4": "0143",
        "active_appointment_id": "APT-4021",
    }

    all_leaks: list[str] = []
    for tool_name, args, extra_state in sample_calls:
        fn = getattr(services, f"{tool_name}_impl")
        state_en = {**base_state, **extra_state, "language": "en-US"}
        state_loc = {**base_state, **extra_state, "language": target_locale}
        res_en = fn(**args, state=state_en, language="en-US")
        res_loc = fn(**args, state=state_loc, language=target_locale)
        leaks = _find_unlocalized_reply_strings(res_en, res_loc)
        for path, val in leaks:
            all_leaks.append(f"{tool_name}:{path} -> {val!r}")

    assert not all_leaks, (
        f"Unlocalized strings leaked in locale {target_locale}:\n" + "\n".join(all_leaks)
    )


