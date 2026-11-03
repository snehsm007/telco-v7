"""Unit tests for ADR-27 / ADR-33: Payment decline and card-not-on-file disambiguation flow.

Mandated by coordinator #429:
1. Card not on file prompts CARD_NOT_ON_FILE without failure count increment or decline wording.
2. Caller can switch to a stored method on file (8844).
3. Caller can confirm running the card as a one-time card payment.
4. Fixture fx_card_on_file_status="declined" still returns PAYMENT_DECLINED.
"""

from typing import Any

from lib.services import process_bill_payment_impl, setup_autopay_impl


def test_card_not_on_file_then_on_file_card() -> None:
    """Attempt 1 with unknown card returns CARD_NOT_ON_FILE; Attempt 2 with on-file card succeeds."""
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
    assert rep1["error"] == "CARD_NOT_ON_FILE"
    assert rep1["data"]["payment_failure_count"] == 0
    assert rep1["data"]["requested_card_last4"] == "1234"
    assert state.get("payment_failure_count", 0) == 0
    assert state.get("card_not_on_file_prompted") == "1234"
    assert not state.get("declined_card_last4")
    assert "declined" not in rep1["error_message"].lower()
    assert "refusée" not in rep1["error_message"].lower()
    assert "rechazada" not in rep1["error_message"].lower()
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
    assert not state.get("declined_card_last4")
    assert state.get("card_not_on_file_prompted") == ""


def test_card_not_on_file_then_new_card_capture() -> None:
    """Attempt 1 with unknown card returns CARD_NOT_ON_FILE; Attempt 2 via secure new-card capture succeeds."""
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
    assert rep1["error"] == "CARD_NOT_ON_FILE"
    assert state.get("payment_failure_count", 0) == 0
    assert state.get("card_not_on_file_prompted") == "4421"

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
    assert not state.get("declined_card_last4")
    assert state.get("card_not_on_file_prompted") == ""


def test_adr33_card_not_on_file_then_confirm_one_time_card() -> None:
    """ADR-33: Attempt 1 returns CARD_NOT_ON_FILE; Attempt 2 confirming same card processes payment."""
    state: dict[str, Any] = {
        "account_id": "ACC-1001",
        "auth_status": "pass",
        "card_last4": "7742",
        "bank_last4": "6789",
        "current_balance": "85.50",
    }
    rep1 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="5678",
        state=state,
    )
    assert rep1["status"] == "error"
    assert rep1["error"] == "CARD_NOT_ON_FILE"
    assert rep1["data"]["payment_failure_count"] == 0
    assert state.get("payment_failure_count", 0) == 0
    assert state.get("card_not_on_file_prompted") == "5678"
    assert not state.get("declined_card_last4")
    assert "declined" not in rep1["error_message"].lower()

    # Attempt 2: Caller confirms running 5678 as one-time card payment
    rep2 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="5678",
        state=state,
    )
    assert rep2["status"] == "ok"
    assert rep2["data"]["payment_processed"] is True
    assert rep2["data"]["amount_paid"] == "85.50"
    assert state.get("card_last4") == "5678"
    assert state.get("payment_failure_count") == 0
    assert state.get("card_not_on_file_prompted") == ""


def test_adr33_fx_card_on_file_status_declined_returns_payment_declined() -> None:
    """ADR-33: fx_card_on_file_status='declined' still returns PAYMENT_DECLINED and increments failure count."""
    state: dict[str, Any] = {
        "account_id": "ACC-1001",
        "auth_status": "pass",
        "card_last4": "7742",
        "bank_last4": "6789",
        "current_balance": "85.50",
        "fx_card_on_file_status": "declined",
    }
    rep1 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card_on_file",
        state=state,
    )
    assert rep1["status"] == "error"
    assert rep1["error"] == "PAYMENT_DECLINED"
    assert rep1["data"]["payment_failure_count"] == 1
    assert state.get("payment_failure_count") == 1
    assert state.get("declined_card_last4") == "7742"

    # Attempt 2 with secondary card 8844 on file succeeds
    rep2 = process_bill_payment_impl(
        amount="85.50",
        payment_method="card",
        card_last4="8844",
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
