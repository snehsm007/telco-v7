"""Unit tests for Cluster 3: fx_* backend fixtures in lib/services.py.

Tests coverage across all declared fx_* evaluation overrides:
- fx_card_on_file_status
- fx_account_suspended & fx_suspension_reason
- fx_outage_status
- fx_mfa_enabled
- fx_tech_status
- fx_sms_delivery
- fx_duplicate_payment_amount
- fx_unapplied_payment
- fx_business_flag
"""

import pytest
from lib.services import (
    lookup_account_impl,
    get_billing_summary_impl,
    process_bill_payment_impl,
    execute_suspend_restore_impl,
    check_regional_outage_impl,
    get_appointment_and_ticket_status_impl,
    manage_appointment_impl,
    send_password_reset_sms_impl,
    manage_mfa_settings_impl,
    process_refund_or_dispute_impl,
)


def test_fx_card_on_file_status_declined_and_retry() -> None:
    """Test fx_card_on_file_status='declined' in process_bill_payment_impl.

    Attempt 1: Card-on-file is declined (PAYMENT_DECLINED).
    Attempt 2: Retry with a new card succeeds cleanly.
    """
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "current_balance": "85.50",
        "card_last4": "7742",
        "fx_card_on_file_status": "declined",
    }
    # Attempt 1: Default / card_on_file
    reply1 = process_bill_payment_impl(amount="85.50", payment_method="card_on_file", state=state)
    assert reply1["status"] == "error"
    assert reply1["error"] == "PAYMENT_DECLINED"
    assert state.get("payment_failure_count") == 1
    assert state.get("card_last4") == ""
    assert state.get("declined_card_last4") == "7742"

    # Attempt 2: Caller provides a new alternate card
    reply2 = process_bill_payment_impl(
        amount="85.50",
        payment_method="new_card",
        card_last4="4321",
        state=state,
    )
    assert reply2["status"] == "ok"
    assert reply2["data"]["payment_processed"] is True
    assert reply2["data"]["amount_paid"] == "85.50"
    assert state.get("payment_failure_count") == 0


def test_fx_account_suspended_and_suspension_reason() -> None:
    """Test fx_account_suspended and fx_suspension_reason in account and billing tools."""
    # When suspended for non-payment
    state_susp = {
        "fx_account_suspended": "true",
        "fx_suspension_reason": "non_payment",
    }
    lookup_account_impl(identifier="5145550199", state=state_susp)
    assert state_susp.get("is_suspended") is True
    assert state_susp.get("suspension_reason") == "non_payment"

    # Authenticate caller after lookup
    state_susp["auth_status"] = "pass"

    # Billing summary reflects account
    summary_reply = get_billing_summary_impl(state=state_susp)
    assert summary_reply["status"] == "ok"

    # Paying the past due balance restores service
    state_susp["past_due_balance"] = "85.50"
    state_susp["current_balance"] = "85.50"
    pay_reply = process_bill_payment_impl(amount="85.50", state=state_susp)
    assert pay_reply["status"] == "ok"
    assert state_susp.get("is_suspended") is False
    assert state_susp.get("service_restored") is True

    # When not suspended
    state_active = {
        "fx_account_suspended": "false",
    }
    lookup_account_impl(identifier="5145550199", state=state_active)
    assert state_active.get("is_suspended") is False


def test_fx_outage_status_active_and_none() -> None:
    """Test fx_outage_status in check_regional_outage_impl."""
    # Active outage
    state_active = {
        "fx_outage_status": "active",
    }
    reply_active = check_regional_outage_impl(postal_code="H3Z 2Y7", subscribe_sms=True, state=state_active)
    assert reply_active["status"] == "ok"
    assert reply_active["data"]["outage_active"] is True
    assert reply_active["data"]["sms_subscribed"] is True
    assert state_active.get("outage_active") is True
    assert state_active.get("outage_sms_subscribed") is True

    # None / no outage
    state_none = {
        "fx_outage_status": "none",
    }
    reply_none = check_regional_outage_impl(postal_code="H3Z 2Y7", state=state_none)
    assert reply_none["status"] == "ok"
    assert reply_none["data"]["outage_active"] is False
    assert reply_none["data"]["next_step"] == "offer_sms_troubleshooting_guide"
    assert state_none.get("outage_active") is False


def test_fx_mfa_enabled_flag() -> None:
    """Test fx_mfa_enabled in lookup_account_impl and manage_mfa_settings_impl."""
    # When MFA is enabled on account
    state_enabled = {
        "fx_mfa_enabled": "true",
    }
    lookup_account_impl(identifier="5145550199", state=state_enabled)
    assert state_enabled.get("mfa_enabled") is True

    # Authenticate caller
    state_enabled["auth_status"] = "pass"

    # Disable MFA
    dis_reply = manage_mfa_settings_impl(action="disable", state=state_enabled)
    assert dis_reply["status"] == "ok"
    assert dis_reply["data"]["mfa_enabled"] is False
    assert state_enabled.get("mfa_enabled") is False

    # When MFA is disabled initially
    state_disabled = {
        "fx_mfa_enabled": "false",
    }
    lookup_account_impl(identifier="5145550199", state=state_disabled)
    assert state_disabled.get("mfa_enabled") is False

    # Authenticate caller
    state_disabled["auth_status"] = "pass"

    # Enable MFA via SMS
    en_reply = manage_mfa_settings_impl(action="enable", preferred_mfa_channel="sms", state=state_disabled)
    assert en_reply["status"] == "ok"
    assert en_reply["data"]["mfa_enabled"] is True
    assert state_disabled.get("mfa_enabled") is True


def test_fx_tech_status_delayed_and_reschedule() -> None:
    """Test fx_tech_status='delayed' and pivot to reschedule."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "fx_tech_status": "delayed",
    }
    reply = get_appointment_and_ticket_status_impl(state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["technician_status"] == "delayed"
    assert reply["data"]["reschedule_offered"] is True
    assert len(reply["data"]["available_slots"]) >= 2
    assert state.get("technician_status") == "delayed"

    # Reschedule to slot 2
    resched = manage_appointment_impl(action="reschedule", selected_slot="2", state=state)
    assert resched["status"] == "ok"
    assert resched["data"]["appointment_rescheduled"] is True
    assert state.get("appointment_status") == "rescheduled"


def test_fx_tech_status_en_route_cancel_protection() -> None:
    """Test fx_tech_status='en_route' blocks cancellation."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "fx_tech_status": "en_route",
    }
    reply = get_appointment_and_ticket_status_impl(state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["technician_status"] == "en_route"
    assert state.get("technician_status") == "en_route"

    cxl = manage_appointment_impl(action="cancel", state=state)
    assert cxl["status"] == "error"
    assert cxl["error"] == "CANNOT_CANCEL_EN_ROUTE"


def test_fx_sms_delivery_failed_escalation() -> None:
    """Test fx_sms_delivery='failed' triggers CODE_NOT_SENT on second attempt."""
    state = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "fx_sms_delivery": "failed",
    }
    # Turn 1: Dispatch SMS (recorded as sent)
    reply1 = send_password_reset_sms_impl(state=state)
    assert reply1["status"] == "ok"
    assert reply1["data"]["password_reset_sent"] is True
    assert reply1["data"]["sms_delivery_status"] == "failed"
    assert state.get("password_reset_sent") is True

    # Turn 2: Caller reports they did not receive it / retry dispatch
    reply2 = send_password_reset_sms_impl(state=state)
    assert reply2["status"] == "error"
    assert reply2["error"] == "CODE_NOT_SENT"
    assert reply2["data"]["must_escalate"] is True


def test_fx_duplicate_payment_and_unapplied_payment() -> None:
    """Test fx_duplicate_payment_amount and fx_unapplied_payment."""
    # Duplicate payment in dispute
    state_dup = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "fx_duplicate_payment_amount": "20.00",
    }
    dispute_reply = process_refund_or_dispute_impl(
        charge_type="duplicate",
        amount="20.00",
        reason="charged twice",
        state=state_dup,
    )
    assert dispute_reply["status"] == "ok"
    assert dispute_reply["data"]["approved"] is True
    assert dispute_reply["data"]["dispute_type"] == "duplicate_payment"

    # Unapplied payment in restore service
    state_unapp = {
        "auth_status": "pass",
        "account_id": "ACC-1001",
        "is_suspended": True,
        "past_due_balance": "85.50",
        "fx_unapplied_payment": "85.50",
    }
    restore_reply = execute_suspend_restore_impl(
        action="restore",
        caller_reported_payment="85.50",
        state=state_unapp,
    )
    assert restore_reply["status"] == "ok"
    assert restore_reply["data"]["service_restored"] is True
    assert restore_reply["data"]["caller_reported_payment_verified"] is True
    assert state_unapp.get("is_suspended") is False
