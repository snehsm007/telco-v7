"""Comprehensive unit and regression tests for Track R-A (Backend & Tool Services)."""

from decimal import Decimal
import pytest

from lib.replies import normalize_money_str
from lib.services import (
    browse_plans_and_coverage_impl,
    cancel_or_port_out_service_impl,
    check_regional_outage_impl,
    commit_plan_or_order_impl,
    execute_suspend_restore_impl,
    initiate_number_transfer_impl,
    lookup_account_impl,
    manage_appointment_impl,
    manage_mfa_settings_impl,
    manage_warranty_claim_impl,
    process_bill_payment_impl,
    process_refund_or_dispute_impl,
    run_troubleshooting_and_sms_impl,
    send_login_code_impl,
    send_password_reset_sms_impl,
    setup_autopay_impl,
    setup_payment_arrangement_impl,
    update_contact_profile_impl,
    verify_login_impl,
)


def test_normalize_money_str_french_and_edge_cases() -> None:
    assert normalize_money_str("15,00") == "15.00"
    assert normalize_money_str("85,50 $") == "85.50"
    assert normalize_money_str("1 234,50 CAD") == "1234.50"
    assert normalize_money_str(75) == "75"
    assert normalize_money_str(Decimal("95.00")) == "95.00"

    with pytest.raises(ValueError):
        normalize_money_str(float("nan"))
    with pytest.raises(ValueError):
        normalize_money_str(float("inf"))
    with pytest.raises(ValueError):
        normalize_money_str(True)
    with pytest.raises(ValueError):
        normalize_money_str("")


def test_nanp_11_digit_phone_and_ban_lookup() -> None:
    st: dict = {}
    # 11-digit NANP starting with 1 -> normalizes to 10 digits 2025550143
    res = lookup_account_impl(identifier="12025550143", state=st)
    assert res["status"] == "ok"
    assert res["data"]["account_id"] == "A1001"
    assert st["caller_provided_phone_last4"] == "0143"
    assert st["phone_last4"] == "0143"

    # 9-digit BAN -> synthetic BAN profile keeps linked mobile last4 empty per BR-TV-017
    st_ban: dict = {}
    res_ban = lookup_account_impl(identifier="987654321", state=st_ban)
    assert res_ban["status"] == "ok"
    assert res_ban["data"]["account_id"] == "ACC-4321"
    assert st_ban["phone_last4"] == ""
    assert res_ban["data"]["linked_mobile_last4"] == ""
    assert res_ban["data"]["phone_last4"] == ""
    assert st_ban["caller_provided_phone_last4"] == ""

    # Boolean is rejected
    res_bool = lookup_account_impl(identifier=True, state={})
    assert res_bool["status"] == "error"
    assert res_bool["error"] == "INVALID_INPUT"


def test_browse_plans_fuzz_nan_and_address_alias() -> None:
    st: dict = {}
    res = browse_plans_and_coverage_impl(
        max_budget=float("nan"),
        address="456 Elm Street",
        language="fr-CA",
        state=st,
    )
    assert res["status"] == "ok"
    assert st["service_address"] == "456 Elm Street"
    assert "sans contrat annuel" in res["data"]["contract_term"]
    assert len(res["data"]["shortlisted_plans"]) >= 2


def test_commit_plan_card_last4_validation() -> None:
    st: dict = {"account_id": "A1001", "auth_status": "pass", "logged_in": True}
    # Integer card_last4 should not crash
    res_int = commit_plan_or_order_impl(plan_id="NET-PLUS", card_last4=1234, confirmed=True, state=st)
    assert res_int["status"] == "ok"
    assert res_int["data"]["plan_name"] == "Fiber Internet 500"
    assert res_int["data"]["new_monthly_price"] == "75.00"

    # Declined card 9999
    res_dec = commit_plan_or_order_impl(plan_id="NET-PLUS", card_last4="9999", confirmed=True, state=st)
    assert res_dec["status"] == "error"
    assert res_dec["error"] == "CARD_DECLINED"


def test_outage_credit_proration_rule_35() -> None:
    st: dict = {"account_id": "A1001", "auth_status": "pass", "logged_in": True, "current_balance": "85.50"}
    res = process_refund_or_dispute_impl(
        amount="85.50",
        dispute_type="outage_credit",
        outage_days=3,
        state=st,
    )
    assert res["status"] == "ok"
    assert res["data"]["approved"] is True
    # 3 days * $2.85/day = $8.55
    assert res["data"]["applied_amount"] == "8.55"
    assert res["data"]["daily_rate"] == "2.85"
    assert res["data"]["credit_amount"] == "8.55"


def test_appointment_two_step_cancel_enforcement() -> None:
    st: dict = {"account_id": "A1001", "auth_status": "pass", "logged_in": True, "technician_status": "scheduled"}
    # Call 1 with confirmed_cancel=True without prior disclosure is blocked
    res1 = manage_appointment_impl(action="cancel", confirmed_cancel=True, state=st)
    assert res1["status"] == "ok"
    assert res1["data"]["requires_confirmation"] is True
    assert res1["data"]["appointment_cancelled"] is False

    # Call 2 with confirmed_cancel=True after disclosure succeeds
    res2 = manage_appointment_impl(action="cancel", confirmed_cancel=True, state=st)
    assert res2["status"] == "ok"
    assert res2["data"]["appointment_cancelled"] is True


def test_warranty_swollen_battery_safety_override() -> None:
    # Swollen battery requires immediate safety guidance without auth
    st: dict = {}
    res = manage_warranty_claim_impl(issue_description="device battery swollen", language="en-US", state=st)
    assert res["status"] == "ok"
    assert res["data"]["safety_hazard"] is True
    assert res["data"]["claim_status"] == "urgent_safety_replacement"
    assert res["data"]["expedited_replacement_eta"] == "1 business day"
    assert res["data"]["do_not_mail_warning"] is True
    assert "do not mail" in res["data"]["urgent_safety_instructions"].lower()


def test_password_reset_unknown_phone_propagates_not_found() -> None:
    st: dict = {}
    res = send_password_reset_sms_impl(identifier="514-555-9999", state=st)
    assert res["status"] == "error"
    assert res["error"] == "NOT_FOUND"


def test_mfa_ve13_sms_login_does_not_skip_email_otp() -> None:
    st: dict = {}
    lookup_account_impl(identifier="202-555-0143", state=st)
    send_login_code_impl(channel="sms", state=st)
    verify_login_impl(code="123456", state=st)

    # Now caller requests lost authenticator -> MUST still require email step up!
    r_mfa = manage_mfa_settings_impl(action="disable", lost_authenticator=True, state=st)
    assert r_mfa["status"] == "ok"
    assert r_mfa["data"]["requires_email_step_up"] is True
    assert r_mfa["data"]["mfa_updated"] is False
    assert st.get("mfa_email_code_sent") is True
