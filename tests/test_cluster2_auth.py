"""Unit tests for Cluster 2: Simulator Auth Compatibility vs fx_pin_on_file / fx_otp_on_file."""

from __future__ import annotations

import pytest

from lib.fakes import (
    ALWAYS_WRONG_LOGIN_CODES,
    VALID_OTPS,
    VALID_PINS,
    fixture_state_scope,
    login_code_accepted,
    normalize_code,
    secret_pin_accepted,
)
from lib.services import verify_login_impl


def test_simulator_auth_accepts_plausible_codes_without_override() -> None:
    """Simulator-invented 4-digit PINs and 6-digit OTPs are accepted on attempts 0 and 1."""
    # 4-digit PINs invented by simulator
    for pin in ("4829", "7391", "2480", "1234", "5678"):
        assert login_code_accepted(pin, attempts=0) is True
        assert login_code_accepted(pin, attempts=1) is True
        assert secret_pin_accepted(pin, attempts=0) is True
        assert secret_pin_accepted(pin, attempts=1) is True

    # 6-digit OTPs invented by simulator
    for otp in ("384920", "847291", "102938", "123456", "246810"):
        assert login_code_accepted(otp, attempts=0) is True
        assert login_code_accepted(otp, attempts=1) is True


def test_always_wrong_codes_strictly_rejected() -> None:
    """ALWAYS_WRONG_LOGIN_CODES are always rejected regardless of attempt or state."""
    for wrong in ALWAYS_WRONG_LOGIN_CODES:
        assert login_code_accepted(wrong, attempts=0) is False
        assert login_code_accepted(wrong, attempts=1) is False
        assert secret_pin_accepted(wrong, attempts=0) is False
        assert secret_pin_accepted(wrong, attempts=1) is False

    # Even with an explicit override, ALWAYS_WRONG codes must never be accepted
    state = {"fx_pin_on_file": "9999"}
    with fixture_state_scope(state):
        assert login_code_accepted("9999", attempts=0, state=state) is False
        assert secret_pin_accepted("9999", attempts=0, state=state) is False


def test_three_strike_lockout_ladder() -> None:
    """Attempts 0 and 1 succeed, attempt 2 (3rd try) is locked out with default max_attempts=3."""
    code = "7291"
    assert login_code_accepted(code, attempts=0) is True
    assert login_code_accepted(code, attempts=1) is True
    assert login_code_accepted(code, attempts=2) is False
    assert login_code_accepted(code, attempts=3) is False

    assert secret_pin_accepted(code, attempts=0) is True
    assert secret_pin_accepted(code, attempts=1) is True
    assert secret_pin_accepted(code, attempts=2) is False

    # Custom max_attempts allows more tries
    assert login_code_accepted(code, attempts=2, max_attempts=5) is True
    assert login_code_accepted(code, attempts=3, max_attempts=5) is True
    assert login_code_accepted(code, attempts=4, max_attempts=5) is False


def test_invalid_length_codes_rejected() -> None:
    """Codes shorter than 4 or longer than 10 digits are rejected."""
    for invalid in ("", "1", "12", "123", "12345678901", "abcdef"):
        assert login_code_accepted(invalid, attempts=0) is False
        assert secret_pin_accepted(invalid, attempts=0) is False


def test_explicit_pin_override_exact_matching() -> None:
    """When fx_pin_on_file is set, only that exact PIN is accepted for PIN authentication."""
    state = {"fx_pin_on_file": "4321"}
    with fixture_state_scope(state):
        # Correct override PIN matches
        assert login_code_accepted("4321", attempts=0, state=state) is True
        assert login_code_accepted("4321", attempts=1, state=state) is True
        assert secret_pin_accepted("4321", attempts=0, state=state) is True

        # Non-matching 4-digit PIN is rejected
        assert login_code_accepted("1234", attempts=0, state=state) is False
        assert secret_pin_accepted("1234", attempts=0, state=state) is False

        # Wrong code is rejected
        assert login_code_accepted("9999", attempts=0, state=state) is False

        # 6-digit SMS OTP is accepted because fx_pin_on_file does NOT apply to OTP channel
        assert login_code_accepted("847291", attempts=0, state=state) is True
        assert login_code_accepted("384920", attempts=0, state=state) is True


def test_explicit_otp_override_exact_matching() -> None:
    """When fx_otp_on_file is set, only that exact OTP is accepted for OTP authentication."""
    state = {"fx_otp_on_file": "654321"}
    with fixture_state_scope(state):
        # Correct override OTP matches
        assert login_code_accepted("654321", attempts=0, state=state) is True
        assert login_code_accepted("654321", attempts=1, state=state) is True

        # Non-matching 6-digit OTP is rejected
        assert login_code_accepted("123456", attempts=0, state=state) is False

        # 4-digit PIN is accepted because fx_otp_on_file does NOT apply to PIN channel
        assert login_code_accepted("4829", attempts=0, state=state) is True
        assert secret_pin_accepted("4829", attempts=0, state=state) is True


def test_channel_specific_overrides() -> None:
    """Channel state explicitly enforces respective overrides."""
    # When login_channel is 'sms' and only fx_pin_on_file is set, SMS OTP is accepted
    state_sms = {"login_channel": "sms", "fx_pin_on_file": "4321"}
    assert login_code_accepted("928301", attempts=0, state=state_sms) is True

    # When login_channel is 'sms' and fx_otp_on_file is set, SMS OTP must match
    state_sms_otp = {"login_channel": "sms", "fx_otp_on_file": "928301"}
    assert login_code_accepted("928301", attempts=0, state=state_sms_otp) is True
    assert login_code_accepted("112233", attempts=0, state=state_sms_otp) is False

    # When login_channel is 'pin' and fx_pin_on_file is set, PIN must match
    state_pin = {"login_channel": "pin", "fx_pin_on_file": "4321"}
    assert login_code_accepted("4321", attempts=0, state=state_pin) is True
    assert login_code_accepted("7890", attempts=0, state=state_pin) is False


def test_verify_login_impl_end_to_end_auth_retry_and_lockout() -> None:
    """verify_login_impl handles simulator PINs, retry with explicit override, and 3-strike lockout."""
    # 1. Successful verification with simulator-invented PIN when no override is set
    state1: dict[str, object] = {
        "account_id": "A1001",
        "phone_last4": "0143",
        "identified": True,
    }
    res1 = verify_login_impl(code="7821", state=state1)
    assert res1["status"] == "ok"
    assert state1["auth_status"] == "pass"
    assert state1["logged_in"] is True

    # 2. Retry scenario with explicit override (sim__dispute_charge_auth_retry pattern)
    state2: dict[str, object] = {
        "account_id": "A1001",
        "phone_last4": "0143",
        "identified": True,
        "fx_pin_on_file": "4321",
    }
    # Turn 1: intentionally wrong code '9999'
    res2_wrong = verify_login_impl(code="9999", state=state2)
    assert res2_wrong["status"] == "error"
    assert res2_wrong["error"] == "WRONG_CODE"
    assert state2["auth_failure_count"] == 1
    assert state2["auth_status"] != "pass"

    # Turn 2: correct retry code '4321'
    res2_retry = verify_login_impl(code="4321", state=state2)
    assert res2_retry["status"] == "ok"
    assert state2["auth_status"] == "pass"
    assert state2["logged_in"] is True
    assert state2["auth_failure_count"] == 0

    # 3. Three-strike lockout ladder
    state3: dict[str, object] = {
        "account_id": "ACC-1002",
        "phone_last4": "0198",
        "identified": True,
    }
    # Strike 1
    r1 = verify_login_impl(code="9999", state=state3)
    assert r1["status"] == "error"
    assert r1["error"] == "WRONG_CODE"
    assert state3["auth_failure_count"] == 1

    # Strike 2
    r2 = verify_login_impl(code="9999", state=state3)
    assert r2["status"] == "error"
    assert r2["error"] == "WRONG_CODE"
    assert state3["auth_failure_count"] == 2

    # Strike 3 -> Lockout!
    r3 = verify_login_impl(code="9999", state=state3)
    assert r3["status"] == "error"
    assert r3["error"] == "TOO_MANY_ATTEMPTS"
    assert state3["auth_status"] == "locked"
    assert state3["logged_in"] is False
    assert "ACC-1002" in str(state3.get("locked_accounts", ""))

    # Subsequent verification attempt on locked account immediately rejected
    r4 = verify_login_impl(code="1234", state=state3)
    assert r4["status"] == "error"
    assert r4["error"] == "TOO_MANY_ATTEMPTS"
