"""Unit tests for lib/services.py covering all 22 atomic tools, auth ladder, and mutations."""

from __future__ import annotations

from typing import Any
import pytest

from lib.services import (
    ALL_TOOLS,
    MAX_LOGIN_ATTEMPTS,
    MAX_PAYMENT_ATTEMPTS,
    browse_plans_and_coverage,
    browse_plans_and_coverage_impl,
    cancel_or_port_out_service,
    cancel_or_port_out_service_impl,
    check_regional_outage,
    check_regional_outage_impl,
    commit_plan_or_order,
    commit_plan_or_order_impl,
    execute_suspend_restore,
    execute_suspend_restore_impl,
    get_appointment_and_ticket_status,
    get_appointment_and_ticket_status_impl,
    get_billing_summary,
    get_billing_summary_impl,
    handover_to_person,
    handover_to_person_impl,
    initiate_number_transfer,
    initiate_number_transfer_impl,
    lookup_account,
    lookup_account_impl,
    manage_appointment,
    manage_appointment_impl,
    manage_mfa_settings,
    manage_mfa_settings_impl,
    manage_warranty_claim,
    manage_warranty_claim_impl,
    not_identified_reply,
    process_bill_payment,
    process_bill_payment_impl,
    process_refund_or_dispute,
    process_refund_or_dispute_impl,
    read_count,
    record_payment_attempt,
    run_troubleshooting_and_sms,
    run_troubleshooting_and_sms_impl,
    send_login_code,
    send_login_code_impl,
    _session_language,
    send_password_reset_sms,
    send_password_reset_sms_impl,
    setup_autopay,
    setup_autopay_impl,
    setup_payment_arrangement,
    setup_payment_arrangement_impl,
    submit_request_impl,
    update_contact_profile,
    update_contact_profile_impl,
    verify_login,
    verify_login_impl,
)

KNOWN_PHONE = "202 555 0143"


def logged_in_state() -> dict[str, Any]:
    state: dict[str, Any] = {}
    assert lookup_account_impl(identifier=KNOWN_PHONE, state=state)["status"] == "ok"
    assert send_login_code_impl(state=state)["status"] == "ok"
    assert verify_login_impl(code="123456", state=state)["status"] == "ok"
    assert state.get("auth_status") == "pass"
    return state


def test_all_tools_inventory() -> None:
    assert len(ALL_TOOLS) == 22
    expected_tools = {
        "lookup_account",
        "send_login_code",
        "verify_login",
        "handover_to_person",
        "get_billing_summary",
        "process_bill_payment",
        "setup_payment_arrangement",
        "setup_autopay",
        "process_refund_or_dispute",
        "check_regional_outage",
        "run_troubleshooting_and_sms",
        "get_appointment_and_ticket_status",
        "manage_appointment",
        "browse_plans_and_coverage",
        "commit_plan_or_order",
        "initiate_number_transfer",
        "manage_warranty_claim",
        "send_password_reset_sms",
        "manage_mfa_settings",
        "execute_suspend_restore",
        "update_contact_profile",
        "cancel_or_port_out_service",
    }
    assert set(ALL_TOOLS) == expected_tools


def test_read_count_handles_decimals_and_junk() -> None:
    assert read_count({"n": 2.0}, "n") == 2
    assert read_count({"n": "3"}, "n") == 3
    assert read_count({}, "n") == 0
    assert read_count({"n": "x"}, "n") == 0


def test_lookup_account_finds_and_remembers_the_account() -> None:
    state: dict[str, Any] = {}
    reply = lookup_account_impl(identifier=KNOWN_PHONE, state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["first_name"] == "Jordan"
    assert reply["data"]["phone_last4"] == "0143"
    assert reply["data"]["caller_provided_phone_last4"] == "0143"
    assert reply["data"]["account_status"] == "active"
    assert state["account_id"] == "A1001" and state["phone_last4"] == "0143"
    assert "2025550143" not in str(reply)


def test_lookup_account_errors() -> None:
    assert lookup_account_impl(identifier="", state={})["error"] == "INVALID_INPUT"
    assert lookup_account_impl(identifier="123", state={})["error"] == "NOT_FOUND"
    assert lookup_account_impl(identifier="ACC-12", state={})["error"] == "NOT_FOUND"
    assert lookup_account(identifier=KNOWN_PHONE)["status"] == "ok"
    assert not_identified_reply("R000001")["error"] == "NOT_IDENTIFIED"


# Kills MUTATION 4: Keep a login when the caller switches to another account
def test_switching_accounts_clears_the_login() -> None:
    state = logged_in_state()
    assert state.get("auth_status") == "pass"
    lookup_account_impl(identifier="303 555 0188", state=state)
    assert state["auth_status"] == "none"
    assert state["auth_failure_count"] == 0


def test_send_login_code_works_with_or_without_prior_lookup() -> None:
    empty_state: dict[str, Any] = {}
    mid_flow = send_login_code_impl(state=empty_state)
    assert mid_flow["status"] == "error"
    assert mid_flow["error"] == "NOT_IDENTIFIED"
    assert "agent_action" in mid_flow

    state: dict[str, Any] = {}
    lookup_account_impl(identifier=KNOWN_PHONE, state=state)
    reply = send_login_code_impl(state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["sent"] is True
    assert reply["data"]["destination_last4"] == "0143"
    assert state["auth_status"] == "code_sent"


def test_no_second_login_on_the_same_call() -> None:
    state = logged_in_state()
    assert send_login_code_impl(state=state)["data"]["already_verified"] is True
    assert verify_login_impl(code="000000", state=state)["data"]["verified"] is True


def test_verify_login_direct_and_invalid_inputs() -> None:
    empty_state: dict[str, Any] = {}
    assert verify_login_impl(code="1234", state=empty_state)["error"] == "NOT_IDENTIFIED"

    direct_state: dict[str, Any] = {"account_id": "A1001"}
    direct_reply = verify_login_impl(code="1234", state=direct_state)
    assert direct_reply["status"] == "ok"
    assert direct_reply["data"]["logged_in"] is True
    assert direct_state["auth_status"] == "pass"

    state: dict[str, Any] = {"account_id": "A1001"}
    assert verify_login_impl(code="12", state=state)["error"] == "CODE_NOT_RECEIVED"
    assert verify_login_impl(code="123456789012", state=state)["error"] == "INVALID_INPUT"
    assert verify_login_impl(code="0000", state=state)["error"] == "WRONG_CODE"
    assert state.get("auth_failure_count", 0) == 1


# Kills MUTATION 3 and MUTATION 5
def test_wrong_codes_are_counted_until_login_is_refused() -> None:
    state: dict[str, Any] = {"fx_otp_on_file": "123456"}
    lookup_account_impl(identifier=KNOWN_PHONE, state=state)
    send_login_code_impl(state=state)

    # Attempt 1: wrong code
    rep1 = verify_login_impl(code="999999", state=state)
    assert rep1["error"] == "WRONG_CODE"
    assert rep1["data"]["attempts_left"] == 2
    assert state["auth_failure_count"] == 1

    # Attempt 2: wrong code
    rep2 = verify_login_impl(code="999999", state=state)
    assert rep2["error"] == "WRONG_CODE"
    assert rep2["data"]["attempts_left"] == 1
    assert state["auth_failure_count"] == 2

    # Attempt 3: wrong code -> LOCKOUT
    rep3 = verify_login_impl(code="999999", state=state)
    assert rep3["error"] == "TOO_MANY_ATTEMPTS"
    assert rep3["data"]["lockout_triggered"] is True
    assert state["auth_status"] == "locked"
    assert state["auth_failure_count"] == 3

    # Subsequent attempts refused
    assert verify_login_impl(code="123456", state=state)["error"] == "TOO_MANY_ATTEMPTS"
    assert send_login_code_impl(state=state)["error"] == "TOO_MANY_ATTEMPTS"


# Tests lenient retry contract on Attempt 2 and lockout on Attempt 3
def test_lenient_retry_on_second_try_and_lockout_on_third() -> None:
    state: dict[str, Any] = {"account_id": "A1001", "fx_pin_on_file": "4321"}
    # Attempt 1 wrong code
    assert verify_login_impl(code="9999", state=state)["error"] == "WRONG_CODE"
    assert state["auth_failure_count"] == 1

    # Attempt 2 lenient retry with valid code succeeds!
    assert verify_login_impl(code="314159", state=state)["status"] == "ok"
    assert state["auth_status"] == "pass"


def test_lockout_after_three_wrong_attempts() -> None:
    state: dict[str, Any] = {"account_id": "A1001", "fx_pin_on_file": "4321"}
    assert verify_login_impl(code="9999", state=state)["error"] == "WRONG_CODE"
    assert verify_login_impl(code="9999", state=state)["error"] == "WRONG_CODE"
    last = verify_login_impl(code="123456", state=state)
    assert last["error"] == "TOO_MANY_ATTEMPTS"
    assert last["data"]["lockout_triggered"] is True
    assert state["auth_status"] == "locked"


# Kills MUTATION 2: Let submit_request run before caller passed login
def test_submit_request_needs_a_login_and_returns_repeatable_reference() -> None:
    state: dict[str, Any] = {"auth_status": "none"}
    assert submit_request_impl("Mail a statement", state=state)["error"] == "NOT_LOGGED_IN"

    lookup_account_impl(identifier=KNOWN_PHONE, state=state)
    assert submit_request_impl("Mail a statement", state=state)["error"] == "NOT_LOGGED_IN"

    authed = logged_in_state()
    first = submit_request_impl("Mail a paper statement", state=authed)
    again = submit_request_impl("Mail a  paper statement", state=authed)
    assert first["status"] == "ok" and first["data"] == {"submitted": True}
    assert first["tracking_id"] == again["tracking_id"]
    assert submit_request_impl("  ", state=authed)["error"] == "INVALID_INPUT"


def test_payment_attempts_and_lockout() -> None:
    pay_state: dict[str, Any] = {}
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    third_pay = record_payment_attempt(pay_state, False)
    assert third_pay["error"] == "TOO_MANY_ATTEMPTS"
    assert third_pay["data"]["lockout_triggered"] is True
    assert record_payment_attempt(pay_state, True)["status"] == "ok"


def test_handover_to_person_language_hierarchy_and_state() -> None:
    state_fr: dict[str, Any] = {}
    res_fr = handover_to_person_impl(reason="besoin d'un agent humain", state=state_fr)
    assert res_fr["status"] == "ok"
    assert res_fr["data"]["language"] == "fr-CA"
    assert state_fr["handover_complete"] is True
    assert "transfère" in res_fr["handoff_message"] or "représentant" in res_fr["handoff_message"]

    spanish_words = {"last_user_utterance": "Hola necesito hablar con una persona"}
    res_es = handover_to_person_impl(reason="help", language="", state=dict(spanish_words))
    assert res_es["data"]["language"] == "es-US"
    assert "transfiero" in res_es["handoff_message"] or "representante" in res_es["handoff_message"]

    assert handover_to_person_impl(reason="help", language="en-US", state=dict(spanish_words))["data"]["language"] == "en-US"
    active_fr = dict(spanish_words, language="fr-CA")
    assert handover_to_person_impl(reason="help", state=active_fr)["data"]["language"] == "fr-CA"

    assert handover_to_person_impl(reason="caller wants an agent", state={})["data"]["language"] == "en-US"
    assert handover_to_person_impl(reason="caller wants an agent", state={"preferred_language": "es-US"})["data"]["language"] == "es-US"

    state_en: dict[str, Any] = {}
    res_en = handover_to_person_impl(reason="caller_request", language="en-US", state=state_en)
    assert res_en["data"]["language"] == "en-US"
    assert "transferring" in res_en["handoff_message"] or "representative" in res_en["handoff_message"]


# Kills tool breakages: test all 22 tools have happy paths (status == ok) and error paths
def test_all_22_tools_happy_and_error_paths() -> None:
    authed = logged_in_state()
    unauthed: dict[str, Any] = {"auth_status": "none"}

    # 1. lookup_account
    r1_ok = lookup_account_impl(identifier=KNOWN_PHONE, state={})
    assert r1_ok["status"] == "ok"
    r1_err = lookup_account_impl(identifier="", state={})
    assert r1_err["status"] == "error"

    # 2. send_login_code
    r2_ok = send_login_code_impl(state=dict(authed, auth_status="none"))
    assert r2_ok["status"] == "ok"
    r2_err = send_login_code_impl(state={"auth_status": "locked", "auth_failure_count": 3})
    assert r2_err["status"] == "error"

    # 3. verify_login
    r3_ok = verify_login_impl(code="123456", state=dict(authed, auth_status="none"))
    assert r3_ok["status"] == "ok"
    r3_err = verify_login_impl(code="000000", state=dict(authed, auth_status="none"))
    assert r3_err["status"] == "error"

    # 4. handover_to_person
    r4_ok = handover_to_person_impl(reason="billing question", state=authed)
    assert r4_ok["status"] == "ok"
    r4_err = handover_to_person_impl(state={"mock_error": "SYSTEM_DOWN"})
    assert r4_err["status"] == "error"

    # 5. get_billing_summary
    r5_ok = get_billing_summary_impl(state=authed)
    assert r5_ok["status"] == "ok"
    r5_err = get_billing_summary_impl(state=unauthed)
    assert r5_err["status"] == "error"

    # 6. process_bill_payment
    r6_ok = process_bill_payment_impl(amount="50.00", card_last4="4242", state=dict(authed))
    assert r6_ok["status"] == "ok"
    r6_err = process_bill_payment_impl(amount="50.00", card_last4="0000", state=dict(authed))
    assert r6_err["status"] == "error"

    # 7. setup_payment_arrangement
    r7_ok = setup_payment_arrangement_impl(extension_days=14, installments=2, state=dict(authed))
    assert r7_ok["status"] == "ok"
    r7_err = setup_payment_arrangement_impl(state=unauthed)
    assert r7_err["status"] == "error"

    # 8. setup_autopay
    r8_ok = setup_autopay_impl(payment_method="card", last4="4242", state=dict(authed))
    assert r8_ok["status"] == "ok"
    r8_err = setup_autopay_impl(state=unauthed)
    assert r8_err["status"] == "error"

    # 9. process_refund_or_dispute
    r9_ok = process_refund_or_dispute_impl(amount="20.00", reason="overcharge", state=dict(authed))
    assert r9_ok["status"] == "ok"
    r9_err = process_refund_or_dispute_impl(state=unauthed)
    assert r9_err["status"] == "error"

    # 10. check_regional_outage
    r10_ok = check_regional_outage_impl(postal_code="H3Z 2Y7", state=authed)
    assert r10_ok["status"] == "ok"
    r10_err = check_regional_outage_impl(postal_code="", state={"postal_code": ""})
    assert r10_err["status"] == "error"

    # 11. run_troubleshooting_and_sms
    r11_ok = run_troubleshooting_and_sms_impl(service_type="internet", symptom="slow", state=authed)
    assert r11_ok["status"] == "ok"
    r11_err = run_troubleshooting_and_sms_impl(state={"mock_error": "SYSTEM_DOWN"})
    assert r11_err["status"] == "error"

    # 12. get_appointment_and_ticket_status
    r12_ok = get_appointment_and_ticket_status_impl(state=authed)
    assert r12_ok["status"] == "ok"
    r12_err = get_appointment_and_ticket_status_impl(state=unauthed)
    assert r12_err["status"] == "error"

    # 13. manage_appointment
    r13_ok = manage_appointment_impl(action="reschedule", selected_slot="SLOT-1", state=dict(authed))
    assert r13_ok["status"] == "ok"
    r13_err = manage_appointment_impl(action="cancel", technician_en_route=True, state=dict(authed))
    assert r13_err["status"] == "error"

    # 14. browse_plans_and_coverage
    r14_ok = browse_plans_and_coverage_impl(category="internet", state=authed)
    assert r14_ok["status"] == "ok"
    r14_err = browse_plans_and_coverage_impl(state={"mock_error": "SYSTEM_DOWN"})
    assert r14_err["status"] == "error"

    # 15. commit_plan_or_order
    r15_ok = commit_plan_or_order_impl(plan_id="NET-PLUS", confirmed=True, state=dict(authed))
    assert r15_ok["status"] == "ok"
    r15_unconf = commit_plan_or_order_impl(plan_id="NET-PLUS", confirmed=False, state=dict(authed))
    assert r15_unconf["status"] == "error"
    assert r15_unconf["error"] == "REQUIRES_CONFIRMATION"
    r15_err = commit_plan_or_order_impl(state=unauthed)
    assert r15_err["status"] == "error"

    # 16. initiate_number_transfer
    r16_ok = initiate_number_transfer_impl(phone_to_transfer="2025550199", state=authed)
    assert r16_ok["status"] == "ok"
    r16_err = initiate_number_transfer_impl(state={"mock_error": "SYSTEM_DOWN"})
    assert r16_err["status"] == "error"

    # 17. manage_warranty_claim
    r17_ok = manage_warranty_claim_impl(action="status", state=dict(authed))
    assert r17_ok["status"] == "ok"
    r17_err = manage_warranty_claim_impl(state=unauthed)
    assert r17_err["status"] == "error"

    # 18. send_password_reset_sms
    r18_ok = send_password_reset_sms_impl(state=authed)
    assert r18_ok["status"] == "ok"
    r18_err = send_password_reset_sms_impl(state={"mock_error": "SYSTEM_DOWN"})
    assert r18_err["status"] == "error"

    # 19. manage_mfa_settings
    r19_ok = manage_mfa_settings_impl(action="status", state=dict(authed))
    assert r19_ok["status"] == "ok"
    r19_err = manage_mfa_settings_impl(state=unauthed)
    assert r19_err["status"] == "error"

    # 20. execute_suspend_restore
    r20_ok = execute_suspend_restore_impl(action="suspend", reason="vacation", state=dict(authed))
    assert r20_ok["status"] == "ok"
    r20_err = execute_suspend_restore_impl(state=unauthed)
    assert r20_err["status"] == "error"

    # 21. update_contact_profile
    r21_ok = update_contact_profile_impl(email="test@example.com", state=dict(authed))
    assert r21_ok["status"] == "ok"
    r21_err = update_contact_profile_impl(state=unauthed)
    assert r21_err["status"] == "error"

    # 22. cancel_or_port_out_service
    r22_ok = cancel_or_port_out_service_impl(service_line="mobile", state=dict(authed))
    assert r22_ok["status"] == "ok"
    r22_err = cancel_or_port_out_service_impl(state=unauthed)
    assert r22_err["status"] == "error"


def test_services_extended_branches_and_edge_cases() -> None:
    authed = logged_in_state()

    # lookup_account: business deflection & blocked numbers & account_id format
    biz_rep = lookup_account_impl(identifier="business inquiry", is_business_inquiry=True, state={})
    assert biz_rep["status"] == "ok"
    assert biz_rep["data"]["business_flag"] is True

    blocked_rep = lookup_account_impl(identifier="9005550199", state={})
    assert blocked_rep["status"] == "error"
    assert blocked_rep["error"] == "PERMISSION_DENIED"

    acc_id_rep = lookup_account_impl(identifier="ACC-1002", state={})
    assert acc_id_rep["status"] == "ok"
    assert acc_id_rep["data"]["first_name"] == "Taylor"

    # send_login_code: email channel
    email_code = send_login_code_impl(channel="email", state=dict(authed, auth_status="none"))
    assert email_code["status"] == "ok"
    assert email_code["data"]["channel"] == "email"

    # verify_login with email code
    verify_email = verify_login_impl(code="123456", method="email", state=dict(authed, auth_status="none"))
    assert verify_email["status"] == "ok"

    # process_bill_payment: full balance and payment lockout
    pay_full = process_bill_payment_impl(amount="full", card_last4="4242", state=dict(authed))
    assert pay_full["status"] == "ok"
    assert pay_full["data"]["remaining_balance"] == "0.00"

    lockout_pay_state = dict(authed, payment_failure_count=2)
    pay_lockout = process_bill_payment_impl(amount="10.00", card_last4="0000", state=lockout_pay_state)
    assert pay_lockout["error"] == "TOO_MANY_ATTEMPTS"
    assert pay_lockout["data"]["lockout_triggered"] is True

    # setup_autopay: bank method and cancel
    autopay_bank = setup_autopay_impl(payment_method="bank", last4="6789", state=dict(authed))
    assert autopay_bank["status"] == "ok"
    assert autopay_bank["data"]["payment_method"] == "bank"

    autopay_cancel = setup_autopay_impl(action="cancel", state=dict(authed))
    assert autopay_cancel["status"] == "ok"
    assert autopay_cancel["data"]["autopay_enrolled"] is False

    # process_refund_or_dispute: duplicate payment, outage credit, and cap exceeded
    dup_refund = process_refund_or_dispute_impl(amount="20.00", reason="duplicate charge", state=dict(authed))
    assert dup_refund["status"] == "ok"
    assert dup_refund["data"]["refund_type"] == "duplicate_payment"

    outage_credit = process_refund_or_dispute_impl(dispute_type="outage", outage_days=3, state=dict(authed))
    assert outage_credit["status"] == "ok"
    assert outage_credit["data"]["dispute_type"] == "outage_credit"

    exceed_cap = process_refund_or_dispute_impl(amount="75.00", reason="disputed fee", state=dict(authed))
    assert exceed_cap["status"] == "ok"
    assert exceed_cap["data"]["exceeds_self_serve_cap"] is True

    # check_regional_outage with SMS subscription
    outage_sub = check_regional_outage_impl(postal_code="H3Z 2Y7", subscribe_sms=True, state=dict(authed))
    assert outage_sub["status"] == "ok"
    assert outage_sub["data"]["sms_subscribed"] is True

    # run_troubleshooting_and_sms: satellite TV and mobility
    tbs_sat = run_troubleshooting_and_sms_impl(service_type="tv", symptom="satellite error 101", state=dict(authed))
    assert tbs_sat["status"] == "ok"

    tbs_mob = run_troubleshooting_and_sms_impl(service_type="mobility", symptom="sim data not working", state=dict(authed))
    assert tbs_mob["status"] == "ok"

    # manage_appointment: 2-step confirmation and cancel
    apt_state = dict(authed, technician_status="scheduled")
    apt_conf_step = manage_appointment_impl(action="cancel", state=apt_state)
    assert apt_conf_step["status"] == "ok"
    assert apt_conf_step["data"]["requires_confirmation"] is True

    apt_cancel_done = manage_appointment_impl(action="cancel", confirmed_cancel=True, state=apt_state)
    assert apt_cancel_done["status"] == "ok"
    assert apt_cancel_done["data"]["appointment_cancelled"] is True

    # initiate_number_transfer: full transfer request
    port_req = initiate_number_transfer_impl(
        phone_to_transfer="2025550199",
        current_carrier="OtherTel",
        carrier_account_number="98765432",
        port_pin="1234",
        state=dict(authed),
    )
    assert port_req["status"] == "ok"

    # manage_warranty_claim: safety issue and standard claim
    swollen_battery = manage_warranty_claim_impl(issue_description="battery swollen and hot", state=dict(authed))
    assert swollen_battery["status"] == "ok"
    assert swollen_battery["data"]["safety_hazard"] is True

    # manage_warranty_claim: physical damage and clean claim
    dmg_claim = manage_warranty_claim_impl(has_physical_or_liquid_damage="liquid", state=dict(authed))
    assert dmg_claim["status"] == "ok"
    assert dmg_claim["data"]["warranty_covered"] is False

    clean_claim = manage_warranty_claim_impl(damage_screened=True, has_physical_or_liquid_damage=False, state=dict(authed))
    assert clean_claim["status"] == "ok"
    assert clean_claim["data"]["warranty_covered"] is True

    # send_password_reset_sms: email delivery method
    pwd_email = send_password_reset_sms_impl(delivery_channel="email", state=dict(authed))
    assert pwd_email["status"] == "ok"

    # manage_mfa_settings: reset and toggle
    mfa_reset = manage_mfa_settings_impl(action="lost_device", state=dict(authed))
    assert mfa_reset["status"] == "ok"

    mfa_disable = manage_mfa_settings_impl(action="disable", state=dict(authed))
    assert mfa_disable["status"] == "ok"

    mfa_enable = manage_mfa_settings_impl(action="enable_sms", state=dict(authed))
    assert mfa_enable["status"] == "ok"

    mfa_backup = manage_mfa_settings_impl(action="generate_backup_codes", state=dict(authed))
    assert mfa_backup["status"] == "ok"

    # execute_suspend_restore: restore action & error when past due
    restore_res = execute_suspend_restore_impl(action="restore", state=dict(authed, is_suspended=True, past_due_balance="0.00"))
    assert restore_res["status"] == "ok"
    assert restore_res["data"]["service_restored"] is True

    restore_due = execute_suspend_restore_impl(action="restore", state=dict(authed, is_suspended=True, suspension_reason="non_payment", past_due_balance="150.00"))
    assert restore_due["error"] == "PAST_DUE_BALANCE_REQUIRED"

    # update_contact_profile: all update fields & empty error
    profile_upd = update_contact_profile_impl(
        email="new@example.com",
        service_address="456 Elm St",
        postal_code="H2Y 1C6",
        preferred_language_update="fr-CA",
        state=dict(authed),
    )
    assert profile_upd["status"] == "ok"
    assert profile_upd["data"]["profile_updated"] is True

    profile_empty = update_contact_profile_impl(state=dict(authed))
    assert profile_empty["error"] == "MISSING_INPUT"

    # cancel_or_port_out_service: confirmed cancellation and port_out pin
    cancel_done = cancel_or_port_out_service_impl(confirmed=True, state=dict(authed, cancellation_fee_disclosed=True))
    assert cancel_done["status"] == "ok"
    assert cancel_done["data"]["service_cancelled"] is True

    port_out_res = cancel_or_port_out_service_impl(action_type="port_out", confirmed=True, state=dict(authed, cancellation_fee_disclosed=True))
    assert port_out_res["status"] == "ok"
    assert "port_out_pin" in port_out_res["data"]


def test_language_lock_tool_precedence() -> None:
    # (1) state has fr-CA, model passes "en-US" -> tool copy is fr-CA and state stays fr-CA
    base_state = {
        "account_id": "A1001",
        "phone_last4": "0143",
        "auth_status": "pass",
        "language": "fr-CA",
    }

    # send_login_code_impl
    s1 = dict(base_state, auth_status="none")
    r1 = send_login_code_impl(language="en-US", state=s1)
    assert s1["language"] == "fr-CA"
    assert r1.get("active_language") == "fr-CA"
    assert "code à 6 chiffres" in r1.get("spoken_message", "")

    # verify_login_impl
    s2 = dict(base_state, auth_status="code_sent")
    r2 = verify_login_impl(code="123456", language="en-US", state=s2)
    assert s2["language"] == "fr-CA"
    assert r2.get("active_language") == "fr-CA"

    # get_billing_summary_impl
    s3 = dict(base_state)
    r3 = get_billing_summary_impl(language="en-US", state=s3)
    assert s3["language"] == "fr-CA"
    assert r3.get("active_language") == "fr-CA"

    # process_refund_or_dispute_impl
    s4 = dict(base_state)
    r4 = process_refund_or_dispute_impl(amount="15.00", dispute_type="billing_error", language="en-US", state=s4)
    assert s4["language"] == "fr-CA"
    assert r4.get("active_language") == "fr-CA"
    assert "remboursement" in (r4.get("spoken_message") or r4.get("data", {}).get("verbatim_confirmation", ""))

    # send_password_reset_sms_impl
    s5 = dict(base_state)
    r5 = send_password_reset_sms_impl(language="en-US", state=s5)
    assert s5["language"] == "fr-CA"
    assert r5.get("active_language") == "fr-CA"
    assert "réinitialisation" in r5.get("data", {}).get("spoken_summary", "")

    # (2) empty state + model passes fr-CA -> lock set to fr-CA
    s_init = {"account_id": "A1001"}
    r_init = send_login_code_impl(language="fr-CA", state=s_init)
    assert s_init["language"] == "fr-CA"
    assert r_init.get("active_language") == "fr-CA"

    # (3) en-US state + model passes fr-CA -> upgrade to fr-CA
    s_upgrade = {"account_id": "A1001", "language": "en-US"}
    r_upgrade = send_login_code_impl(language="fr-CA", state=s_upgrade)
    assert s_upgrade["language"] == "fr-CA"
    assert r_upgrade.get("active_language") == "fr-CA"

    # (4) empty state + model passes "" -> default behaviour unchanged
    s_default = {"account_id": "A1001"}
    r_default = send_login_code_impl(language="", state=s_default)
    assert s_default.get("language") is None or s_default.get("language") == ""
    assert r_default.get("active_language") == "en-US"


def test_asymmetric_session_language_lock() -> None:
    # fr-CA state + "en-US" arg -> fr-CA
    s1 = {"language": "fr-CA"}
    assert _session_language(s1, "en-US") == "fr-CA"
    assert s1["language"] == "fr-CA"

    # en-US state + "fr-CA" arg -> fr-CA (upgrade)
    s2 = {"language": "en-US"}
    assert _session_language(s2, "fr-CA") == "fr-CA"
    assert s2["language"] == "fr-CA"

    # fr-CA state + "" -> fr-CA
    s3 = {"language": "fr-CA"}
    assert _session_language(s3, "") == "fr-CA"
    assert s3["language"] == "fr-CA"

    # empty state + "" -> default (en-US)
    s4: dict[str, Any] = {}
    assert _session_language(s4, "") == "en-US"

