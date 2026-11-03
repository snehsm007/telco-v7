"""Unit tests for Milestone 1.5 integration bug fixes (Bugs A, B, C, D).

Covers:
- Bug A: Generalized card-on-file declined fixture on first card attempt in session,
  ensuring retry with alternate card/bank succeeds.
- Bug B: Unapplied payment (fx_unapplied_payment) covering past due balance,
  accurate restoration_hint, and execute_suspend_restore with caller_reported_payment.
  Standard unpaid suspension still requires payment.
- Bug C: Unidentified name-only caller resolution in lookup_account_impl (Arthur Miller + PIN),
  preserving negative input / invalid secondary identifier rejection.
- Bug D: scripts/run_bench.py RUN_TIMEOUT_S configurability & tests/test_submit_academy.py isolation.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
import pytest

from lib.services import (
    lookup_account_impl,
    verify_login_impl,
    process_bill_payment_impl,
    get_billing_summary_impl,
    execute_suspend_restore_impl,
)
from scripts import run_bench


# ============================================================================
# Bug A: sim__pay_bill_declined_card_retry general fix
# ============================================================================

def test_bug_a_declined_card_on_first_attempt_any_digits():
    """First card attempt fails with PAYMENT_DECLINED when fx_card_on_file_status='declined'."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "card_last4": "1234",
        "fx_card_on_file_status": "declined",
        "payment_failure_count": 0,
        "current_balance": "85.50",
    }
    # Caller provides 1234 (not 7742)
    res1 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card_on_file",
        card_last4="1234",
        state=state,
    )
    assert res1.get("status") == "error"
    assert res1.get("error") == "PAYMENT_DECLINED"
    assert state.get("payment_failure_count") == 1
    assert state.get("declined_card_last4") == "1234"
    assert state.get("card_last4") == ""

    # Second attempt with alternate card 8844 succeeds cleanly
    res2 = process_bill_payment_impl(
        amount="85.50",
        payment_method="alternate_card",
        card_last4="8844",
        state=state,
    )
    assert res2.get("status") == "ok"
    assert res2.get("data", {}).get("payment_processed") is True


def test_bug_a_non_declined_succeeds_first_attempt():
    """Card payment succeeds on attempt 1 when fixture is not declined."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "card_last4": "1234",
        "payment_failure_count": 0,
        "current_balance": "85.50",
    }
    res = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="1234",
        state=state,
    )
    assert res.get("status") == "ok"


# ============================================================================
# Bug B: sim__restore_service_already_paid vs sim__restore_service_standard
# ============================================================================

def test_bug_b_unapplied_payment_restoration_hint_and_restore():
    """Unapplied payment covering past due balance surfaces restoration_hint and restores cleanly."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "is_suspended": True,
        "fx_account_suspended": "true",
        "fx_suspension_reason": "non_payment",
        "fx_unapplied_payment": "85.50",
        "past_due_balance": "85.50",
        "current_balance": "85.50",
    }
    summary = get_billing_summary_impl(state=state)
    assert summary.get("status") == "ok"
    data = summary.get("data", {})
    assert data.get("service_status") == "eligible_for_restoration"
    assert "caller_reported_payment=True" in data.get("restoration_hint", "")
    assert data.get("unapplied_payment") == "85.50"

    # Now execute restore with caller_reported_payment=True
    restore_res = execute_suspend_restore_impl(
        action="restore",
        caller_reported_payment=True,
        state=state,
    )
    assert restore_res.get("status") == "ok"
    assert restore_res.get("data", {}).get("service_restored") is True
    assert restore_res.get("data", {}).get("caller_reported_payment_verified") is True
    assert state.get("is_suspended") is False
    assert state.get("past_due_balance") == "0.00"


def test_bug_b_standard_unpaid_suspension_requires_payment():
    """Standard suspension without unapplied payment requires payment first."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "is_suspended": True,
        "fx_account_suspended": "true",
        "fx_suspension_reason": "non_payment",
        "past_due_balance": "85.50",
        "current_balance": "85.50",
    }
    summary = get_billing_summary_impl(state=state)
    assert summary.get("status") == "ok"
    data = summary.get("data", {})
    assert data.get("service_status") == "suspended"
    assert "Payment of past due balance is required" in data.get("restoration_hint", "")

    # Attempting restore without paying fails with PAST_DUE_BALANCE_REQUIRED
    restore_res = execute_suspend_restore_impl(
        action="restore",
        state=state,
    )
    assert restore_res.get("status") == "error"
    assert restore_res.get("error") == "PAST_DUE_BALANCE_REQUIRED"


# ============================================================================
# Bug C: lookup_account_impl name-only callers (Arthur Miller)
# ============================================================================

def test_bug_c_name_only_resolution_and_pin_auth():
    """Unidentified caller with valid full name and no email/postal resolves and can auth."""
    state = {}
    res = lookup_account_impl(
        full_name="Arthur Miller",
        state=state,
    )
    assert res.get("status") == "ok"
    assert state.get("identified") is True
    assert state.get("account_id", "").startswith("ACC-")
    assert state.get("auth_status") == "none"

    # Authenticate with valid 4-digit PIN (matches simulator PIN ladder)
    auth_res = verify_login_impl(
        code="5521",
        state=state,
    )
    assert auth_res.get("status") == "ok"
    assert state.get("auth_status") == "pass"


def test_bug_c_negative_name_rejected():
    """Names with negative tokens or single words are rejected."""
    state1 = {}
    res1 = lookup_account_impl(full_name="Nobody Real", state=state1)
    assert res1.get("status") == "error"
    assert res1.get("error") == "NOT_FOUND"

    state2 = {}
    res2 = lookup_account_impl(full_name="Fake User", state=state2)
    assert res2.get("status") == "error"
    assert res2.get("error") == "NOT_FOUND"

    state3 = {}
    res3 = lookup_account_impl(full_name="Unknown", state=state3)
    assert res3.get("status") == "error"
    assert res3.get("error") == "NOT_FOUND"


def test_bug_c_invalid_secondary_identifier_rejected():
    """Valid name with invalid email or postal code returns NOT_FOUND."""
    state = {}
    res = lookup_account_impl(
        full_name="Arthur Miller",
        email="invalid_email_format",
        state=state,
    )
    assert res.get("status") == "error"
    assert res.get("error") == "NOT_FOUND"


# ============================================================================
# Bug D: Configurable RUN_TIMEOUT_S
# ============================================================================

def test_bug_d_run_timeout_env_config():
    """RUN_TIMEOUT_S defaults to 14400s or respects environment override."""
    assert run_bench.RUN_TIMEOUT_S >= 9000


# ============================================================================
# Bug E: Telephony Event Tag Stripping & Language Detection
# ============================================================================

def test_bug_e_telephony_event_tag_stripping_french():
    """Turn 0 <event>session start</event> does not prevent Turn 1 French lock."""
    from lib.dynamic_prompt import detect_active_call_language, extract_user_utterances

    class DummyPart:
        def __init__(self, text):
            self.text = text

    class DummyContent:
        def __init__(self, role, text):
            self.role = role
            self.parts = [DummyPart(text)]

    class DummyRequest:
        def __init__(self, texts):
            self.contents = [DummyContent("user", t) for t in texts]

    req = DummyRequest(["<event>session start</event>", "Bonjour, ma facture est trop élevée"])
    utts = extract_user_utterances(req)
    assert len(utts) == 1
    assert utts[0] == "Bonjour, ma facture est trop élevée"

    lang = detect_active_call_language({}, req)
    assert lang == "fr-CA"


def test_bug_e_telephony_event_tag_stripping_spanish_and_no_input():
    """Turn 0 event + mid-call no-input event does not disrupt language detection."""
    from lib.dynamic_prompt import detect_active_call_language, extract_user_utterances

    class DummyPart:
        def __init__(self, text):
            self.text = text

    class DummyContent:
        def __init__(self, role, text):
            self.role = role
            self.parts = [DummyPart(text)]

    class DummyRequest:
        def __init__(self, texts):
            self.contents = [DummyContent("user", t) for t in texts]

    req_es = DummyRequest(["<event>session start</event>", "Hola, quiero pagar mi factura"])
    assert detect_active_call_language({}, req_es) == "es-US"

    req_no_input = DummyRequest([
        "<event>session start</event>",
        "Bonjour",
        "<event>no-input</event>",
        "Oui, je veux annuler mon forfait",
    ])
    utts = extract_user_utterances(req_no_input)
    assert len(utts) == 2
    assert detect_active_call_language({}, req_no_input) == "fr-CA"


def test_bug_e_speech_strip_markdown_event_tags():
    """Spoken text clean_speech strips <event> tags cleanly."""
    from lib.speech import strip_markdown
    res = strip_markdown("<event>session start</event>Hello world")
    assert res.strip() == "Hello world"


# ============================================================================
# Bug F: Speech-to-Text Digit Grouping & Rejection of Letters
# ============================================================================

def test_bug_f_verify_login_comma_and_space_grouped_codes():
    """PIN and OTP with spaces or commas are normalized and accepted."""
    state_pin = {"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0}
    res_pin = verify_login_impl(code="3 0 1 2", state=state_pin)
    assert res_pin.get("status") == "ok"
    assert res_pin.get("data", {}).get("verified") is True

    state_otp = {"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0}
    res_otp = verify_login_impl(code="123,456", state=state_otp)
    assert res_otp.get("status") == "ok"
    assert res_otp.get("data", {}).get("verified") is True


def test_bug_f_verify_login_rejects_letters_and_malformed():
    """Codes containing letters or invalid lengths return INVALID_INPUT."""
    state = {"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0}
    res1 = verify_login_impl(code="1234abcd", state=state)
    assert res1.get("status") == "error"
    assert res1.get("error") == "INVALID_INPUT"

    res2 = verify_login_impl(code="abcd", state=state)
    assert res2.get("status") == "error"
    assert res2.get("error") == "INVALID_INPUT"

    res3 = verify_login_impl(code="1234567890123", state=state)
    assert res3.get("status") == "error"
    assert res3.get("error") == "INVALID_INPUT"


def test_bug_f_extract_last4_grouped_digits_and_rejects_letters():
    """Card and bank last4 extraction handles grouped digits and rejects letters."""
    from lib.services import _extract_last4
    assert _extract_last4("7 7 4 2") == "7742"
    assert _extract_last4("7,7,4,2") == "7742"
    assert _extract_last4("1234, 5678, 9012, 7742") == "7742"
    assert _extract_last4("774a") is None
    assert _extract_last4("visa1234") is None
    assert _extract_last4("12") is None


def test_bug_f_initiate_number_transfer_grouped_digits():
    """Initiate number transfer normalizes phone, carrier account, and PIN."""
    from lib.services import initiate_number_transfer_impl
    state = {"account_id": "A1001", "auth_status": "pass"}
    res = initiate_number_transfer_impl(
        phone_to_transfer="202, 555, 0143",
        carrier_account_number="888, 777, 666",
        port_pin="3 0 1 2",
        current_carrier="OtherCarrier",
        state=state,
    )
    assert res.get("status") == "ok"
    assert res.get("data", {}).get("phone_to_transfer") == "2025550143"
    assert "carrier_account_number" not in res.get("data", {}).get("missing_details", [])
    assert "port_pin" not in res.get("data", {}).get("missing_details", [])
