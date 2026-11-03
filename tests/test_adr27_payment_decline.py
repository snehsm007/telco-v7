"""Unit tests for ADR-27: Realistic payment decline and alternative payment retry flow.

Mandated by coordinator #270:
1. Decline-then-on-file-card retry
2. Decline-then-new-card-capture retry
3. On-file-card first-try succeeds without decline
4. Autopay enrollment with newly named card remains untouched
"""

from typing import Any

from lib.services import process_bill_payment_impl, setup_autopay_impl


def test_decline_then_on_file_card() -> None:
    """Attempt 1 with unknown card declines; Attempt 2 with on-file secondary card succeeds."""
    state: dict[str, Any] = {
        "account_id": "ACC-1001",
        "auth_status": "pass",
        "card_last4": "7742",
        "bank_last4": "6789",
        "current_balance": "85.50",
    }
    # Attempt 1: Caller provides named card 1234 (not on file)
    rep1 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="1234",
        state=state,
    )
    assert rep1["status"] == "error"
    assert rep1["error"] == "PAYMENT_DECLINED"
    assert rep1["data"]["payment_failure_count"] == 1
    assert rep1["data"]["declined_card_last4"] == "1234"
    assert state.get("payment_failure_count") == 1
    assert state.get("declined_card_last4") == "1234"
    assert "payment_methods_on_file" in rep1["data"]
    assert any(m["last4"] == "7742" for m in rep1["data"]["payment_methods_on_file"])
    assert any(m["last4"] == "8844" for m in rep1["data"]["payment_methods_on_file"])
    assert any(m["last4"] == "6789" for m in rep1["data"]["payment_methods_on_file"])

    # Attempt 2: Caller switches to secondary card ending in 8844 on file
    rep2 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="8844",
        state=state,
    )
    assert rep2["status"] == "ok"
    assert rep2["data"]["payment_processed"] is True
    assert rep2["data"]["amount_paid"] == "85.50"
    assert state.get("payment_failure_count") == 0
    assert state.get("declined_card_last4") == ""


def test_decline_then_new_card_capture() -> None:
    """Attempt 1 with unknown card declines; Attempt 2 via secure new-card capture flow succeeds."""
    state: dict[str, Any] = {
        "account_id": "ACC-1001",
        "auth_status": "pass",
        "card_last4": "7742",
        "current_balance": "85.50",
    }
    # Attempt 1: Unknown card
    rep1 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="4421",
        state=state,
    )
    assert rep1["status"] == "error"
    assert rep1["error"] == "PAYMENT_DECLINED"
    assert state.get("payment_failure_count") == 1

    # Caller goes through secure keypad card capture
    state["card_capture_prompted"] = True
    rep2 = process_bill_payment_impl(
        amount="85.50",
        payment_method="new_card",
        card_last4="4321",
        state=state,
    )
    assert rep2["status"] == "ok"
    assert rep2["data"]["payment_processed"] is True
    assert state.get("payment_failure_count") == 0
    assert state.get("declined_card_last4") == ""


def test_on_file_card_first_try_no_decline() -> None:
    """Attempt 1 with on-file primary card succeeds immediately without decline."""
    state: dict[str, Any] = {
        "account_id": "ACC-1001",
        "auth_status": "pass",
        "card_last4": "7742",
        "current_balance": "85.50",
    }
    rep = process_bill_payment_impl(
        amount="85.50",
        payment_method="card_on_file",
        state=state,
    )
    assert rep["status"] == "ok"
    assert rep["data"]["payment_processed"] is True
    assert rep["data"]["amount_paid"] == "85.50"
    assert state.get("payment_failure_count", 0) == 0
    assert not state.get("declined_card_last4")


def test_autopay_untouched() -> None:
    """setup_autopay with a newly named card (e.g. card ending in 4321) is completely untouched."""
    state: dict[str, Any] = {
        "account_id": "ACC-1001",
        "auth_status": "pass",
        "card_last4": "7742",
    }
    rep = setup_autopay_impl(
        payment_method="card",
        card_last4="4321",
        action="enroll",
        state=state,
    )
    assert rep["status"] == "ok"
    assert rep["data"]["autopay_enrolled"] is True
    assert state.get("autopay_enrolled") is True
