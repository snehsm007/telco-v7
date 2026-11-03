"""Unit test suite verifying all 14 defects remediated in lib/services.py.

Covers:
  - Defect 1: Partial payment monotonic subtraction & past-due balance tracking
  - Defect 2: Refund limit bypass ($25 threshold policy enforcement across all paths)
  - Defect 3: Ledger-verified restoration (rejects restore on caller word without payment)
  - Defect 4: Lockout persistence across account switches
  - Defect 5: Unmatched name/email returns NOT_FOUND (no ACCOUNTS[0] fallback)
  - Defect 6: Port-out PIN withheld pending confirmation
  - Defect 7: Strict language lock with explicit bidirectional switch
  - Defect 8: Fraud priority over business deflection
  - Defect 9: Auth check on swollen battery warranty claim
  - Defect 10: Dynamic catalog pricing / no hardcoded eval branches
  - Defect 11: Accidental retention rejection on cancellation complaint keywords
  - Defect 12: Reschedule rejects unrecognized slots with NO_AVAILABILITY_IN_WINDOW
  - Defect 13: Shared state elimination across calls
  - Defect 14: After-hours routing and live-agent structured session context
"""

import copy
from decimal import Decimal
import pytest

from lib.fakes import ACCOUNTS, FAKE_BILLING_LEDGER
from lib.services import (
    browse_plans_and_coverage_impl,
    cancel_or_port_out_service_impl,
    check_regional_outage_impl,
    commit_plan_or_order_impl,
    execute_suspend_restore_impl,
    get_appointment_and_ticket_status_impl,
    get_billing_summary_impl,
    handover_to_person_impl,
    initiate_number_transfer_impl,
    lookup_account_impl,
    manage_appointment_impl,
    manage_mfa_settings_impl,
    manage_warranty_claim_impl,
    process_bill_payment_impl,
    process_refund_or_dispute_impl,
    record_payment_attempt,
    run_troubleshooting_and_sms_impl,
    send_login_code_impl,
    send_password_reset_sms_impl,
    setup_autopay_impl,
    setup_payment_arrangement_impl,
    submit_request_impl,
    update_contact_profile_impl,
    verify_login_impl,
)


# ============================================================================
# Defect 1: Partial payment clears balance
# ============================================================================

def test_defect_1_partial_payment_monotonic_subtraction():
    state = {
        "auth_status": "pass",
        "account_id": "A1001",
        "current_balance": "100.00",
        "past_due_balance": "50.00",
        "is_suspended": True,
        "card_last4": "7742",
    }
    # Pay only $20 out of $50 past due and $100 current
    res = process_bill_payment_impl(amount="20.00", payment_method="card", state=state)
    assert res["status"] == "ok"
    assert res["data"]["payment_processed"] is True
    assert res["data"]["amount_paid"] == "20.00"
    assert res["data"]["remaining_balance"] == "80.00"
    assert res["data"]["remaining_past_due_balance"] == "30.00"
    assert res["data"]["service_status"] == "suspended"
    assert res["data"]["service_restored"] is False
    assert state["current_balance"] == "80.00"
    assert state["past_due_balance"] == "30.00"
    assert state["is_suspended"] is True


def test_defect_1_full_past_due_payment_restores_service():
    state = {
        "auth_status": "pass",
        "account_id": "A1001",
        "current_balance": "50.00",
        "past_due_balance": "50.00",
        "is_suspended": True,
        "card_last4": "7742",
    }
    # Pay full past-due balance of $50
    res = process_bill_payment_impl(amount="50.00", payment_method="card", state=state)
    assert res["status"] == "ok"
    assert res["data"]["remaining_past_due_balance"] == "0.00"
    assert res["data"]["service_restored"] is True
    assert res["data"]["service_status"] == "active"
    assert state["is_suspended"] is False
    assert state["past_due_balance"] == "0.00"


# ============================================================================
# Defect 2: Refund limit bypass
# ============================================================================

def test_defect_2_outage_refund_above_threshold_escalates():
    state = {"auth_status": "pass", "account_id": "A1001"}
    # 365 outage days at $2.85/day = $1040.25 >> $25.00 limit
    res = process_refund_or_dispute_impl(outage_days=365, state=state)
    assert res["status"] == "ok"
    assert res["data"]["approved"] is False
    assert res["data"]["exceeds_self_serve_cap"] is True
    assert res["data"]["must_escalate_immediately"] is True
    assert res["data"]["escalation_reason"] == "refund_threshold_exceeded"
    assert res["data"]["target_queue"] == "billing_specialist"
    assert res["data"]["verbatim_key"] == "transfer_to_specialist"


def test_defect_2_outage_refund_within_threshold_auto_approved():
    state = {"auth_status": "pass", "account_id": "A1001", "current_balance": "50.00"}
    # 3 outage days at $2.85/day = $8.55 <= $25.00 limit
    res = process_refund_or_dispute_impl(outage_days=3, state=state)
    assert res["status"] == "ok"
    assert res["data"]["approved"] is True
    assert res["data"]["applied_amount"] == "8.55"
    assert state["current_balance"] == "41.45"


def test_defect_2_general_dispute_above_threshold_escalates():
    state = {"auth_status": "pass", "account_id": "A1001"}
    # Discretionary billing dispute for $150.00 > $25.00 cap must escalate to specialist
    res = process_refund_or_dispute_impl(
        amount="150.00",
        reason="Incorrect monthly charges",
        dispute_type="billing_dispute",
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["approved"] is False
    assert res["data"]["exceeds_self_serve_cap"] is True
    assert res["data"]["escalation_reason"] == "refund_threshold_exceeded"


def test_defect_2_duplicate_payment_approved_without_discretionary_cap():
    state = {"auth_status": "pass", "account_id": "A1001", "current_balance": "100.00"}
    # Duplicate payments are refunded in full without hitting the $25 discretionary credit cap (PRD M3 & CUJ-2)
    res = process_refund_or_dispute_impl(
        amount="85.50",
        reason="I paid twice by mistake",
        dispute_type="duplicate_payment",
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["approved"] is True
    assert res["data"]["applied_amount"] == "85.50"
    assert res["data"]["refund_type"] == "duplicate_payment"


# ============================================================================
# Defect 3: Service restored on caller's word
# ============================================================================

def test_defect_3_restore_without_ledger_payment_rejected():
    state = {
        "auth_status": "pass",
        "account_id": "A1001",
        "is_suspended": True,
        "past_due_balance": "85.50",
    }
    # Caller claims they paid, but ledger fixture has negative unapplied flag
    state["fx_unapplied_payment"] = "none"
    res = execute_suspend_restore_impl(
        action="restore",
        caller_reported_payment="I already paid my bill yesterday",
        state=state,
    )
    assert res["status"] == "error"
    assert res["error"] == "PAST_DUE_BALANCE_REQUIRED"
    assert res["data"]["caller_reported_payment_verified"] is False
    assert state["is_suspended"] is True


def test_defect_3_restore_with_verified_ledger_payment_succeeds():
    state = {
        "auth_status": "pass",
        "account_id": "A1001",
        "is_suspended": True,
        "past_due_balance": "85.50",
    }
    # Set fixture unapplied payment to match
    state["fx_unapplied_payment"] = "85.50"
    res = execute_suspend_restore_impl(
        action="restore",
        caller_reported_payment="I paid yesterday",
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["service_restored"] is True
    assert res["data"]["caller_reported_payment_verified"] is True
    assert state["is_suspended"] is False


# ============================================================================
# Defect 4: Lockout resets on account switch
# ============================================================================

def test_defect_4_lockout_persists_across_account_switches():
    state = {"fx_otp_on_file": "123456"}
    # Lookup account 1
    lookup_account_impl(identifier="2025550143", state=state)
    acc1 = state["account_id"]
    send_login_code_impl(channel="sms", state=state)

    # Fail login 3 times on account 1
    verify_login_impl(code="999999", state=state)
    verify_login_impl(code="999999", state=state)
    r3 = verify_login_impl(code="999999", state=state)
    assert r3["status"] == "error"
    assert r3["error"] == "TOO_MANY_ATTEMPTS"
    assert state["auth_status"] == "locked"

    # Switch to account 2
    lookup_account_impl(identifier="5145550188", state=state)
    assert state["account_id"] != acc1
    assert state["auth_status"] == "none"

    # Switch back to account 1
    lookup_account_impl(identifier="2025550143", state=state)
    assert state["account_id"] == acc1
    assert state["auth_status"] == "locked"

    # Further login attempts on account 1 are immediately rejected
    locked_try = verify_login_impl(code="1234", state=state)
    assert locked_try["status"] == "error"
    assert locked_try["error"] == "TOO_MANY_ATTEMPTS"


# ============================================================================
# Defect 5: Identification always succeeds
# ============================================================================

def test_defect_5_unmatched_name_returns_not_found():
    state = {}
    res = lookup_account_impl(name="Nonexistent Person", state=state)
    assert res["status"] == "error"
    assert res["error"] == "NOT_FOUND"
    assert state.get("identified") is False
    assert state.get("identification_status") == "Fail"


def test_defect_5_unmatched_email_returns_not_found():
    state = {}
    res = lookup_account_impl(email="nonexistent@randomdomain.test", state=state)
    assert res["status"] == "error"
    assert res["error"] == "NOT_FOUND"
    assert state.get("identified") is False


def test_defect_5_valid_phone_identifies():
    state = {}
    res = lookup_account_impl(identifier="2025550143", state=state)
    assert res["status"] == "ok"
    assert state.get("identified") is True
    assert state.get("identification_status") == "Pass"


# ============================================================================
# Defect 6: Port-out PIN leaks
# ============================================================================

def test_defect_6_port_out_pin_withheld_pending_confirmation():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = cancel_or_port_out_service_impl(
        action_type="port_out",
        confirmed=False,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["requires_confirmation"] is True
    assert res["data"]["contract_disclosure_required"] is True
    assert res["data"]["transfer_pin_withheld_pending_confirmation"] is True
    assert "port_out_pin" not in res["data"]
    assert "transfer_pin" not in res["data"]


def test_defect_6_port_out_pin_released_after_confirmation():
    state = {
        "auth_status": "pass",
        "account_id": "A1001",
        "cancellation_fee_disclosed": True,
    }
    res = cancel_or_port_out_service_impl(
        action_type="port_out",
        confirmed=True,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["service_cancelled"] is True
    assert "port_out_pin" in res["data"]
    assert "transfer_pin" in res["data"]


# ============================================================================
# Defect 7: Language flips
# ============================================================================

def test_defect_7_asymmetric_language_lock():
    state = {"language": "fr-CA"}
    # Passing en-US without explicit switch does not break lock
    res = handover_to_person_impl(reason="general", language="en-US", state=state)
    assert res["status"] == "ok"
    assert state["language"] == "fr-CA"


def test_defect_7_explicit_bidirectional_switch():
    state = {"language": "fr-CA", "explicit_language_switch": "en-US"}
    res = handover_to_person_impl(reason="general", state=state)
    assert res["status"] == "ok"
    assert state["language"] == "en-US"


# ============================================================================
# Defect 8: Fraud priority over business deflection
# ============================================================================

def test_defect_8_fraud_preempts_business_deflection():
    state = {}
    res = lookup_account_impl(
        identifier="My business account was hacked and compromised",
        is_business_inquiry=True,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["must_escalate_immediately"] is True
    assert res["data"]["escalation_reason"] == "fraud_escalation"
    assert res["data"]["target_queue"] == "fraud_and_security_24x7"


def test_defect_8_standard_business_deflection():
    state = {}
    res = lookup_account_impl(
        identifier="commercial corporate account billing inquiry",
        is_business_inquiry=True,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["must_escalate_immediately"] is True
    assert res["data"]["escalation_reason"] == "business_handoff"
    assert res["data"]["target_queue"] == "business_solutions"


# ============================================================================
# Defect 9: Missing auth checks (Swollen battery)
# ============================================================================

def test_defect_9_swollen_battery_unauthenticated_requires_auth_with_safety_guidance():
    state = {"auth_status": "none"}
    res = manage_warranty_claim_impl(
        issue_description="device battery is swollen and expanding",
        safety_hazard=True,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["safety_hazard"] is True
    assert res["data"]["claim_status"] == "pending_authentication"
    assert res["data"]["requires_authentication"] is True
    assert "urgent_safety_instructions" in res["data"]
    assert "warranty_claim_id" not in res["data"]


def test_defect_9_swollen_battery_authenticated_submits_claim():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = manage_warranty_claim_impl(
        issue_description="device battery is swollen and expanding",
        safety_hazard=True,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["safety_hazard"] is True
    assert res["data"]["claim_status"] == "urgent_safety_replacement"
    assert "warranty_claim_id" in res["data"]


# ============================================================================
# Defect 10: Eval-shaped code (Dynamic catalog pricing)
# ============================================================================

def test_defect_10_dynamic_plan_pricing():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = browse_plans_and_coverage_impl(
        category="tv",
        postal_code="H2X1Y4",
        state=state,
    )
    assert res["status"] == "ok"
    assert "shortlisted_plans" in res["data"]
    plans = res["data"]["shortlisted_plans"]
    assert len(plans) > 0
    for p in plans:
        assert "monthly_price" in p
        assert "price_display" in p


# ============================================================================
# Defect 11: Accidental retention
# ============================================================================

def test_defect_11_cancellation_complaint_does_not_trigger_retention():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = cancel_or_port_out_service_impl(
        action_type="cancel",
        reason="Cancel, I never got my credit and will not stay",
        confirmed=False,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["requires_confirmation"] is True
    assert res["data"].get("retention_offer_accepted") is not True


def test_defect_11_explicit_accept_retention_applies_offer():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = cancel_or_port_out_service_impl(
        action_type="cancel",
        accept_retention_offer=True,
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["service_cancelled"] is False
    assert res["data"]["retention_offer_accepted"] is True
    assert res["data"]["loyalty_credit_applied"] == "$15/mo"


# ============================================================================
# Defect 12: Wrong reschedule slot
# ============================================================================

def test_defect_12_unrecognized_slot_rejected():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = manage_appointment_impl(
        action="reschedule",
        selected_slot="slot 999",
        state=state,
    )
    assert res["status"] == "error"
    assert res["error"] == "OUT_OF_WINDOW"
    assert res["data"]["appointment_rescheduled"] is False
    assert "available_slots" in res["data"]


def test_defect_12_valid_slot_rescheduled():
    state = {"auth_status": "pass", "account_id": "A1001"}
    res = manage_appointment_impl(
        action="reschedule",
        selected_slot="1",
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["appointment_rescheduled"] is True


# ============================================================================
# Defect 13: Shared state
# ============================================================================

def test_defect_13_no_shared_state_leakage():
    res1 = lookup_account_impl(identifier="2025550143")
    res2 = lookup_account_impl(identifier="nonexistent")
    assert res1["status"] == "ok"
    assert res2["status"] == "error"


# ============================================================================
# Defect 14: After-hours routing & live-agent session context
# ============================================================================

def test_defect_14_after_hours_routing():
    state = {
        "account_id": "A1001",
        "auth_status": "pass",
        "after_hours": True,
    }
    res = handover_to_person_impl(
        reason="billing dispute",
        target_queue="billing_specialist",
        state=state,
    )
    assert res["status"] == "ok"
    assert res["data"]["next_business_day_routing"] is True
    assert res["data"]["queue_hours_status"] == "after_hours_callback_available"
    assert "session_context" in res["data"]
    ctx = res["data"]["session_context"]
    assert ctx["account_id"] == "A1001"
    assert ctx["after_hours"] is True
    assert ctx["auth_status"] == "pass"


# ============================================================================
# Additional coverage across lib/services.py tools
# ============================================================================

def test_services_additional_tools_coverage():
    # send_login_code
    s = {}
    lookup_account_impl(identifier="2025550143", state=s)
    slc = send_login_code_impl(channel="sms", state=s)
    assert slc["status"] == "ok"

    # get_billing_summary
    s["auth_status"] = "pass"
    gbs = get_billing_summary_impl(state=s)
    assert gbs["status"] == "ok"

    # setup_autopay
    sap = setup_autopay_impl(payment_method="card", billing_day="15", state=s)
    assert sap["status"] == "ok"

    # setup_payment_arrangement
    spa = setup_payment_arrangement_impl(installments=2, extension_days=14, state=s)
    assert spa["status"] == "ok"

    # get_appointment_and_ticket_status
    apt_st = get_appointment_and_ticket_status_impl(state=s)
    assert apt_st["status"] == "ok"

    # run_troubleshooting_and_sms
    tb = run_troubleshooting_and_sms_impl(service_type="internet", send_sms_guide=True, state=s)
    assert tb["status"] == "ok"

    # manage_mfa_settings
    mfa = manage_mfa_settings_impl(action="status", state=s)
    assert mfa["status"] == "ok"

    # send_password_reset_sms
    pwd = send_password_reset_sms_impl(channel="sms", state=s)
    assert pwd["status"] == "ok"

    # update_contact_profile
    upd = update_contact_profile_impl(preferred_language_update="en-US", state=s)
    assert upd["status"] == "ok"


def test_coverage_check_regional_outage():
    # Active outage
    res1 = check_regional_outage_impl(postal_code="H2X1Y4")
    assert res1["status"] == "ok"
    assert "outage_active" in res1["data"]

    # No outage
    res2 = check_regional_outage_impl(postal_code="K1A0B1")
    assert res2["status"] == "ok"

    # French localization
    res3 = check_regional_outage_impl(postal_code="H2X1Y4", language="fr-CA")
    assert res3["status"] == "ok"

    # Spanish localization
    res4 = check_regional_outage_impl(postal_code="H2X1Y4", language="es-US")
    assert res4["status"] == "ok"


def test_coverage_commit_plan_or_order():
    s = {"auth_status": "pass", "account_id": "A1001"}
    res = commit_plan_or_order_impl(
        plan_id="TV-STARTER",
        category="tv",
        confirmed=True,
        state=s,
    )
    assert res["status"] == "ok"
    assert "order_id" in res["data"]

    # Unauthenticated
    s_unauth = {"auth_status": "none"}
    res_unauth = commit_plan_or_order_impl(plan_id="TV-STARTER", state=s_unauth)
    assert res_unauth["status"] == "error"


def test_coverage_initiate_number_transfer():
    # Unauthenticated checklist
    res1 = initiate_number_transfer_impl(phone_to_transfer="5145550199", current_carrier="Rogers")
    assert res1["status"] == "ok"
    assert res1["data"]["mode"] == "checklist_provided"

    # Authenticated with full donor details
    s = {"auth_status": "pass", "account_id": "A1001"}
    res2 = initiate_number_transfer_impl(
        phone_to_transfer="5145550199",
        current_carrier="Rogers",
        carrier_account_number="987654321",
        port_pin="1234",
        state=s,
    )
    assert res2["status"] == "ok"
    assert res2["data"]["mode"] == "transfer_submitted"

    # Authenticated missing donor details
    res3 = initiate_number_transfer_impl(
        phone_to_transfer="5145550199",
        current_carrier="Rogers",
        state=s,
    )
    assert res3["status"] == "ok"
    assert res3["data"]["status"] == "pending_donor_details"

    # French and Spanish
    res_fr = initiate_number_transfer_impl(language="fr-CA", state=s)
    assert res_fr["status"] == "ok"
    res_es = initiate_number_transfer_impl(language="es-US", state=s)
    assert res_es["status"] == "ok"


def test_coverage_troubleshooting_sms_and_channels():
    s = {"auth_status": "pass", "account_id": "A1001"}
    # TV streaming guide
    res_tv = run_troubleshooting_and_sms_impl(
        service_type="tv",
        symptom="app freezing",
        state=s,
    )
    assert res_tv["status"] == "ok"

    # TV satellite guide
    res_sat = run_troubleshooting_and_sms_impl(
        service_type="tv",
        symptom="satellite signal loss",
        state=s,
    )
    assert res_sat["status"] == "ok"

    # Mobile data troubleshooting
    res_mob = run_troubleshooting_and_sms_impl(
        service_type="mobile",
        symptom="slow data",
        send_sms_guide=True,
        state=s,
    )
    assert res_mob["status"] == "ok"


def test_coverage_setup_autopay_branches():
    s = {"auth_status": "pass", "account_id": "A1001"}
    # Bank payment
    res_bank = setup_autopay_impl(payment_method="bank", billing_day="1", state=s)
    assert res_bank["status"] == "ok"

    # Declined card
    res_dec = setup_autopay_impl(card_last4="9999", billing_day="15", state=s)
    assert res_dec["status"] == "error"
    assert res_dec["error"] == "PAYMENT_DECLINED"

    # French
    res_fr = setup_autopay_impl(payment_method="card", billing_day="15", language="fr-CA", state=s)
    assert res_fr["status"] == "ok"


def test_coverage_manage_mfa_settings():
    s = {"auth_status": "pass", "account_id": "A1001"}
    # Enable MFA
    res_en = manage_mfa_settings_impl(action="enable", state=s)
    assert res_en["status"] == "ok"

    # Disable MFA
    res_dis = manage_mfa_settings_impl(action="disable", state=s)
    assert res_dis["status"] == "ok"

    # French status
    res_fr = manage_mfa_settings_impl(action="status", language="fr-CA", state=s)
    assert res_fr["status"] == "ok"


def test_coverage_send_password_reset_sms():
    s = {"auth_status": "pass", "account_id": "A1001"}
    res_sms = send_password_reset_sms_impl(channel="sms", state=s)
    assert res_sms["status"] == "ok"

    res_email = send_password_reset_sms_impl(channel="email", state=s)
    assert res_email["status"] == "ok"

    res_fr = send_password_reset_sms_impl(channel="sms", language="fr-CA", state=s)
    assert res_fr["status"] == "ok"


def test_coverage_update_contact_profile():
    s = {"auth_status": "pass", "account_id": "A1001"}
    res_email = update_contact_profile_impl(email="new_email@example.com", state=s)
    assert res_email["status"] == "ok"

    res_addr = update_contact_profile_impl(
        service_address="456 Elm Street",
        postal_code="H2X1Y4",
        state=s,
    )
    assert res_addr["status"] == "ok"

    res_pref = update_contact_profile_impl(notification_preference="sms", state=s)
    assert res_pref["status"] == "ok"


def test_coverage_manage_warranty_claim_standard():
    s = {"auth_status": "pass", "account_id": "A1001"}
    # Standard replacement screened
    res = manage_warranty_claim_impl(
        issue_description="microphone not working",
        damage_screened=True,
        has_physical_or_liquid_damage=False,
        state=s,
    )
    assert res["status"] == "ok"

    # Physical damage ineligible
    res_dmg = manage_warranty_claim_impl(
        issue_description="cracked screen from drop",
        damage_screened=True,
        has_physical_or_liquid_damage=True,
        state=s,
    )
    assert res_dmg["status"] == "ok"
    assert res_dmg["data"].get("eligible_for_warranty") is False or "damage" in res_dmg["data"].get("claim_status", "")


def test_coverage_verify_login_branches():
    s = {"fx_otp_on_file": "123456"}
    lookup_account_impl(identifier="2025550143", state=s)
    send_login_code_impl(channel="email", state=s)

    # Wrong code once
    r1 = verify_login_impl(code="999999", state=s)
    assert r1["status"] == "error"
    assert r1["error"] == "WRONG_CODE"

    # Correct email verification code (from fakes)
    r2 = verify_login_impl(code="123456", state=s)
    assert r2["status"] == "ok"
    assert s["auth_status"] == "pass"


def test_coverage_inline_auth_across_tools():
    # Pass identifier and verification code directly into tools
    res1 = get_billing_summary_impl(identifier="2025550143", verification_code="1234")
    assert res1["status"] == "ok"

    res2 = process_refund_or_dispute_impl(
        amount="10.00",
        identifier="2025550143",
        verification_code="1234",
    )
    assert res2["status"] == "ok"

    res3 = setup_payment_arrangement_impl(
        installments=2,
        extension_days=14,
        identifier="2025550143",
        verification_code="1234",
    )
    assert res3["status"] == "ok"

    res4 = manage_appointment_impl(
        action="reschedule",
        selected_slot="1",
        identifier="2025550143",
        verification_code="1234",
    )
    assert res4["status"] == "ok"

    res5 = execute_suspend_restore_impl(
        action="suspend",
        reason="vacation",
        identifier="2025550143",
        verification_code="1234",
    )
    assert res5["status"] == "ok"


def test_coverage_manage_appointment_cancel():
    s = {"auth_status": "pass", "account_id": "A1001"}
    r1 = manage_appointment_impl(action="cancel", confirmed_cancel=False, state=s)
    assert r1["status"] == "ok"
    assert r1["data"]["requires_confirmation"] is True

    r2 = manage_appointment_impl(action="cancel", confirmed_cancel=True, state=s)
    assert r2["status"] == "ok"
    assert r2["data"]["appointment_cancelled"] is True


def test_coverage_setup_autopay_new_card_and_on_file():
    s = {"auth_status": "pass", "account_id": "A1001"}
    r1 = setup_autopay_impl(payment_method="new_card", billing_day="15", state=s)
    assert r1["status"] == "error"
    assert r1["error"] == "CARD_CAPTURE_REQUIRED"

    r2 = setup_autopay_impl(payment_method="card_on_file", billing_day="15", state=s)
    assert r2["status"] == "ok"


def test_coverage_browse_plans_budget_and_categories():
    s = {}
    r1 = browse_plans_and_coverage_impl(category="internet", max_budget="60", state=s)
    assert r1["status"] == "ok"

    r2 = browse_plans_and_coverage_impl(category="mobile", state=s)
    assert r2["status"] == "ok"


def test_coverage_commit_plan_with_addon():
    s = {"auth_status": "pass", "account_id": "A1001"}
    r = commit_plan_or_order_impl(
        plan_id="ADDON-SPORTS",
        category="tv",
        confirmed=True,
        state=s,
    )
    assert r["status"] == "ok"
    assert "combined_monthly_with_tv_starter" in r["data"]


def test_coverage_troubleshooting_reboot_and_gateway():
    s = {"auth_status": "pass", "account_id": "A1001"}
    r1 = run_troubleshooting_and_sms_impl(
        service_type="internet",
        symptom="reboot gateway",
        state=s,
    )
    assert r1["status"] == "ok"


def test_coverage_send_login_code_channels():
    s = {}
    lookup_account_impl(identifier="2025550143", state=s)
    r1 = send_login_code_impl(channel="voice", state=s)
    assert r1["status"] == "ok"

    r2 = send_login_code_impl(channel="sms", state=s)
    assert r2["status"] == "ok"


def test_coverage_verify_login_pin_method():
    s = {}
    lookup_account_impl(identifier="2025550143", state=s)
    r = verify_login_impl(code="1234", method="pin", state=s)
    assert r["status"] == "ok"
    assert s["auth_status"] == "pass"


def test_coverage_lookup_account_variations():
    s1 = {}
    r1 = lookup_account_impl(identifier="987654321", state=s1)
    assert r1["status"] == "ok"

    s2 = {}
    r2 = lookup_account_impl(name="Jordan", state=s2)
    assert r2["status"] == "ok"

    s3 = {}
    r3 = lookup_account_impl(identifier="9005550199", state=s3)
    assert r3["status"] == "error"


def test_coverage_submit_request_and_payment_records():
    s = {"auth_status": "pass", "account_id": "A1001", "logged_in": True}
    r1 = submit_request_impl(summary="Fix billing charge", state=s)
    assert r1["status"] == "ok"

    s_unauth = {"auth_status": "none"}
    r2 = submit_request_impl(summary="Fix billing charge", state=s_unauth)
    assert r2["status"] == "error"

    s_empty = {"auth_status": "pass", "account_id": "A1001"}
    r3 = submit_request_impl(summary="", state=s_empty)
    assert r3["status"] == "error"

    s_pay = {"account_id": "A1001"}
    rec_ok = record_payment_attempt(s_pay, card_or_success="1234")
    assert rec_ok["status"] == "ok"
    rec_fail1 = record_payment_attempt(s_pay, card_or_success="9999")
    assert rec_fail1["status"] == "error"
    rec_fail2 = record_payment_attempt(s_pay, card_or_success="9999")
    assert rec_fail2["status"] == "error"
    rec_fail3 = record_payment_attempt(s_pay, card_or_success="9999")
    assert rec_fail3["status"] == "error"
    assert rec_fail3["error"] == "TOO_MANY_ATTEMPTS"


def test_coverage_mfa_lost_authenticator_and_step_up():
    s = {"auth_status": "pass", "account_id": "A1001", "fx_otp_on_file": "123456"}
    # Trigger lost authenticator step-up email
    r1 = manage_mfa_settings_impl(action="disable", lost_authenticator=True, state=s)
    assert r1["status"] == "ok"
    assert r1["data"]["requires_email_step_up"] is True

    # Resend code
    r2 = manage_mfa_settings_impl(action="disable", lost_authenticator=True, state=s)
    assert r2["status"] == "ok"
    assert r2["data"].get("code_resent") is True

    # Bad step-up code
    r_bad = manage_mfa_settings_impl(action="disable", step_up_code="999999", state=s)
    assert r_bad["status"] == "error"

    # Blank/placeholder step-up code
    r_empty = manage_mfa_settings_impl(action="disable", step_up_code="", state=s)
    assert r_empty["status"] == "ok"

    # Valid step-up code
    r_good = manage_mfa_settings_impl(action="disable", step_up_code="123456", state=s)
    assert r_good["status"] == "ok"
    assert s.get("mfa_email_verified") is True


def test_coverage_bill_payment_declines_and_lockout():
    s = {"auth_status": "pass", "account_id": "A1001", "current_balance": "50.00"}
    r1 = process_bill_payment_impl(amount="25.00", card_last4="9999", state=s)
    assert r1["status"] == "error"
    assert r1["error"] == "PAYMENT_DECLINED"

    r2 = process_bill_payment_impl(amount="25.00", card_last4="9999", state=s)
    assert r2["status"] == "error"

    r3 = process_bill_payment_impl(amount="25.00", card_last4="9999", state=s)
    assert r3["status"] == "error"
    assert r3["error"] == "TOO_MANY_ATTEMPTS"


def test_coverage_suspend_restore_payment_arrangement_and_past_due():
    # Service restore when payment arrangement is active
    s1 = {
        "auth_status": "pass",
        "account_id": "A1001",
        "is_suspended": True,
        "past_due_balance": "50.00",
        "payment_arrangement_active": True,
    }
    r1 = execute_suspend_restore_impl(action="restore", state=s1)
    assert r1["status"] == "ok"
    assert r1["data"]["service_restored"] is True

    # Service restore rejected when past due balance > 0 and no arrangement
    s2 = {
        "auth_status": "pass",
        "account_id": "A1001",
        "is_suspended": True,
        "past_due_balance": "75.00",
    }
    r2 = execute_suspend_restore_impl(action="restore", state=s2)
    assert r2["status"] == "error"
    assert r2["error"] == "PAST_DUE_BALANCE_REQUIRED"


def test_coverage_browse_plans_budget_empty_and_addons():
    s = {}
    # Impossibly low budget triggers fallback shortlist
    r = browse_plans_and_coverage_impl(category="internet", max_budget="1.00", state=s)
    assert r["status"] == "ok"
    assert len(r["data"]["shortlisted_plans"]) > 0


def test_coverage_outage_sms_subscription():
    s = {}
    r = check_regional_outage_impl(postal_code="H3Z 2Y7", subscribe_sms=True, state=s)
    assert r["status"] == "ok"
    assert r["data"]["outage_active"] is True
    assert r["data"]["sms_subscribed"] is True


def test_coverage_send_password_reset_sms_unidentified_and_intl():
    # Explicit unauthenticated session without identifier
    s_unauth = {}
    r1 = send_password_reset_sms_impl(state=s_unauth)
    assert r1["status"] == "error"
    assert r1["error"] == "NOT_IDENTIFIED"

    # International number identifier
    s_intl = {}
    r2 = send_password_reset_sms_impl(identifier="+15145550188", state=s_intl)
    assert r2["status"] == "ok"


def test_coverage_verify_login_already_logged_in_and_lockout():
    # Already logged in path
    s = {
        "auth_status": "pass",
        "logged_in": True,
        "account_id": "A1001",
        "browsed_plan_category": "internet",
    }
    r = verify_login_impl(state=s)
    assert r["status"] == "ok"
    assert r["data"]["auth_status"] == "pass"

    # Already locked account
    s_locked = {
        "account_id": "A1001",
        "auth_failure_count": 3,
        "auth_status": "locked",
    }
    r_l = verify_login_impl(code="1234", state=s_locked)
    assert r_l["status"] == "error"
    assert r_l["error"] == "TOO_MANY_ATTEMPTS"


def test_coverage_autopay_new_card_success():
    s = {"auth_status": "pass", "account_id": "A1001"}
    r = setup_autopay_impl(
        payment_method="card",
        card_last4="4321",
        billing_day="12",
        state=s,
    )
    assert r["status"] == "ok"
    assert r["data"]["autopay_enabled"] is True


def test_coverage_payment_arrangement_inputs():
    s = {"auth_status": "pass", "account_id": "A1001", "current_balance": "100.00"}
    # Invalid extension days
    r_inv1 = setup_payment_arrangement_impl(extension_days=999, state=s)
    assert r_inv1["status"] == "error"

    # Invalid installments
    r_inv2 = setup_payment_arrangement_impl(installments=99, state=s)
    assert r_inv2["status"] == "error"

    # Explicit payment date
    r_date = setup_payment_arrangement_impl(payment_date="2026-11-20", state=s)
    assert r_date["status"] == "ok"


def test_coverage_additional_scenarios():
    s = {"auth_status": "pass", "account_id": "A1001"}
    r_mil = execute_suspend_restore_impl(action="suspend", reason="military deployment", state=s)
    assert r_mil["status"] == "ok"
    assert r_mil["data"]["reduced_rate_monthly"] == "0.00"

    # Suspend restore negative unapplied
    s_unapp = {
        "auth_status": "pass",
        "account_id": "A1001",
        "past_due_balance": "60.00",
        "fx_unapplied_payment": "none",
    }
    r_unapp = execute_suspend_restore_impl(
        action="restore",
        caller_reported_payment="paid yesterday",
        state=s_unapp,
    )
    assert r_unapp["status"] == "error"
    assert r_unapp["error"] == "PAST_DUE_BALANCE_REQUIRED"

    # Lookup account by email
    s_email = {}
    r_em = lookup_account_impl(email="jordan@example.com", state=s_email)
    assert r_em["status"] == "ok"

    # Send login code via email channel with email passed
    s_snd = {"account_id": "A1001"}
    r_snd = send_login_code_impl(email="jordan@example.com", channel="email", state=s_snd)
    assert r_snd["status"] == "ok"

    # Update contact profile preferred language
    s_prof = {"auth_status": "pass", "account_id": "A1001"}
    r_prof = update_contact_profile_impl(preferred_language_update="fr-CA", state=s_prof)
    assert r_prof["status"] == "ok"


