"""Contract tests verifying PRD §17/21 mock_mode contract across all 22 tools."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import lib.services as svc


REPO_ROOT = Path(__file__).resolve().parent.parent

ALL_22_TOOLS = [
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
]

AUTH_TOOLS = {"lookup_account", "send_login_code", "verify_login"}
HANDOVER_TOOLS = {"handover_to_person"}
NON_AUTH_BACKEND_TOOLS = set(ALL_22_TOOLS) - AUTH_TOOLS - HANDOVER_TOOLS


def test_app_json_mock_mode_declaration_and_variable_limit() -> None:
    """Verify cxas_app/app.json declares mock_mode with default True and <= 100 vars."""
    app_path = REPO_ROOT / "cxas_app" / "app.json"
    with open(app_path) as f:
        app_json = json.load(f)

    var_decls = app_json.get("variableDeclarations", [])
    assert len(var_decls) <= 100, f"Expected <= 100 variable declarations, found {len(var_decls)}"

    mock_mode_var = next((v for v in var_decls if v.get("name") == "mock_mode"), None)
    assert mock_mode_var is not None, "mock_mode variable declaration missing from app.json"
    assert mock_mode_var.get("schema", {}).get("default") == "True", (
        f"Expected mock_mode default to be 'True', got {mock_mode_var.get('schema', {}).get('default')}"
    )


def _call_tool(tool_name: str, state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    impl = getattr(svc, f"{tool_name}_impl")
    # Provide sensible minimal args for tools requiring non-empty parameters
    base_kwargs: dict[str, Any] = {"state": state}
    if tool_name == "lookup_account":
        base_kwargs["identifier"] = "2025550143"
    elif tool_name == "send_login_code":
        base_kwargs["channel"] = "sms"
    elif tool_name == "verify_login":
        base_kwargs["code"] = "1111"
    elif tool_name == "handover_to_person":
        base_kwargs["reason"] = "billing_dispute"
    elif tool_name == "process_bill_payment":
        base_kwargs["amount"] = "25.00"
    elif tool_name == "setup_payment_arrangement":
        base_kwargs["extension_days"] = 7
    elif tool_name == "setup_autopay":
        base_kwargs["action"] = "enroll"
    elif tool_name == "process_refund_or_dispute":
        base_kwargs["amount"] = "15.00"
    elif tool_name == "check_regional_outage":
        base_kwargs["postal_code"] = "H2X 1Y4"
    elif tool_name == "run_troubleshooting_and_sms":
        base_kwargs["service_type"] = "internet"
    elif tool_name == "manage_appointment":
        base_kwargs["action"] = "reschedule"
        base_kwargs["selected_slot"] = "SLOT-1"
    elif tool_name == "browse_plans_and_coverage":
        base_kwargs["category"] = "internet"
        base_kwargs["postal_code"] = "H2X 1Y4"
    elif tool_name == "commit_plan_or_order":
        base_kwargs["plan_id"] = "NET-PLUS"
        base_kwargs["confirmed"] = True
    elif tool_name == "initiate_number_transfer":
        base_kwargs["phone_to_transfer"] = "5145550199"
    elif tool_name == "manage_warranty_claim":
        base_kwargs["issue_description"] = "Screen cracked"
        base_kwargs["damage_screened"] = True
    elif tool_name == "send_password_reset_sms":
        base_kwargs["identifier"] = "2025550143"
    elif tool_name == "manage_mfa_settings":
        base_kwargs["action"] = "disable"
    elif tool_name == "execute_suspend_restore":
        base_kwargs["action"] = "suspend"
        base_kwargs["reason"] = "vacation"
    elif tool_name == "update_contact_profile":
        base_kwargs["email"] = "valid@example.com"
    elif tool_name == "cancel_or_port_out_service":
        base_kwargs["action_type"] = "cancel"
        base_kwargs["confirmed"] = True
        base_kwargs["decline_retention_offer"] = True

    base_kwargs.update(kwargs)
    return impl(**base_kwargs)


@pytest.mark.parametrize("tool_name", ALL_22_TOOLS)
def test_mock_mode_true_branch_stamps_mock_mode_across_all_22_tools(tool_name: str) -> None:
    """Verify all 22 tools stamp mock_mode: True when mock_mode is active."""
    # Pre-authenticated state with residential account
    state = {
        "account_id": "ACC-0001",
        "auth_status": "pass",
        "logged_in": True,
        "phone_last4": "0143",
        "mock_mode": "True",
        "current_balance": "100.00",
        "service_address": "123 Main St",
        "cancellation_fee_disclosed": True,
    }
    reply = _call_tool(tool_name, state)
    assert reply["status"] == "ok", f"Tool {tool_name} returned status={reply.get('status')}: {reply}"
    # Must stamp mock_mode into reply or data
    assert reply.get("mock_mode") is True or reply.get("data", {}).get("mock_mode") is True, (
        f"Tool {tool_name} did not stamp mock_mode: True in reply"
    )


@pytest.mark.parametrize("tool_name", sorted(AUTH_TOOLS))
@pytest.mark.parametrize("mock_val", ["False", "false", "0", "no"])
def test_auth_tools_mock_mode_false_returns_auth_service_unavailable(tool_name: str, mock_val: str) -> None:
    """Verify auth tools return AUTH_SERVICE_UNAVAILABLE when mock_mode is False."""
    state = {"account_id": "ACC-0001", "mock_mode": mock_val}
    reply = _call_tool(tool_name, state)
    assert reply["status"] == "error"
    assert reply["error"] == "AUTH_SERVICE_UNAVAILABLE"
    assert reply.get("agent_action") == "ESCALATE_SYSTEM_UNAVAILABLE"
    assert reply.get("must_escalate_immediately") is True
    assert reply.get("data", {}).get("escalation_reason") == "system_unavailable"
    assert reply.get("data", {}).get("mock_mode") is False


@pytest.mark.parametrize("tool_name", sorted(NON_AUTH_BACKEND_TOOLS))
@pytest.mark.parametrize("mock_val", ["False", "false", "0", "no"])
def test_non_auth_tools_mock_mode_false_returns_system_down(tool_name: str, mock_val: str) -> None:
    """Verify 18 non-auth backend tools return SYSTEM_DOWN when mock_mode is False."""
    state = {
        "account_id": "ACC-0001",
        "auth_status": "pass",
        "logged_in": True,
        "mock_mode": mock_val,
        "cancellation_fee_disclosed": True,
    }
    reply = _call_tool(tool_name, state)
    assert reply["status"] == "error"
    assert reply["error"] == "SYSTEM_DOWN"
    assert reply.get("agent_action") == "ESCALATE_SYSTEM_UNAVAILABLE"
    assert reply.get("must_escalate_immediately") is True
    assert reply.get("data", {}).get("escalation_reason") == "system_unavailable"
    assert reply.get("data", {}).get("mock_mode") is False


def test_handover_to_person_mock_mode_false_completes_cleanly() -> None:
    """Verify handover_to_person completes live transfer cleanly regardless of mock_mode."""
    state_live = {"account_id": "ACC-0001", "mock_mode": "False"}
    reply_live = _call_tool("handover_to_person", state_live)
    assert reply_live["status"] == "ok"
    assert reply_live.get("mock_mode") is False
    assert reply_live.get("data", {}).get("mock_mode") is False
    assert reply_live.get("data", {}).get("handover_complete") is True

    state_mock = {"account_id": "ACC-0001", "mock_mode": "True"}
    reply_mock = _call_tool("handover_to_person", state_mock)
    assert reply_mock["status"] == "ok"
    assert reply_mock.get("mock_mode") is True
    assert reply_mock.get("data", {}).get("mock_mode") is True
    assert reply_mock.get("data", {}).get("handover_complete") is True


def test_mock_mode_preserves_business_rules_and_fixtures() -> None:
    """Verify mock_mode=True preserves wrong-PIN, business deflection, and $25 refund cap."""
    # 1. PIN verification: valid PIN succeeds with no override, fails when fx_pin_on_file="8374"
    state_default = {"account_id": "ACC-0001", "phone_last4": "0143", "mock_mode": "True"}
    pass_reply = svc.verify_login_impl(code="4321", state=state_default)
    assert pass_reply["status"] == "ok"
    assert pass_reply["data"]["auth_status"] == "pass"

    state_mismatch = {
        "account_id": "ACC-0001",
        "phone_last4": "0143",
        "mock_mode": "True",
        "fx_pin_on_file": "8374",
        "fixtures": {"fx_pin_on_file": "8374"},
    }
    fail_reply = svc.verify_login_impl(code="4321", state=state_mismatch)
    assert fail_reply["status"] == "error"
    assert fail_reply["error"] == "WRONG_CODE"

    # 2. Business account deflection preserved (not bypassed)
    state_biz = {
        "mock_mode": "True",
        "fx_business_flag": "true",
        "fixtures": {"fx_business_flag": "true"},
    }
    biz_reply = svc.lookup_account_impl(identifier="2025550143", state=state_biz)
    assert biz_reply["status"] == "ok"
    assert biz_reply["data"]["customer_type"] == "business"
    assert biz_reply["data"]["must_escalate_immediately"] is True
    assert biz_reply["data"]["target_queue"] == "business_solutions"

    # 3. $25 refund cap escalation preserved (not bypassed)
    state_refund = {
        "account_id": "ACC-0001",
        "auth_status": "pass",
        "logged_in": True,
        "mock_mode": "True",
    }
    # Within cap ($15) -> approved
    approved_reply = svc.process_refund_or_dispute_impl(amount="15.00", state=dict(state_refund))
    assert approved_reply["status"] == "ok"
    assert approved_reply["data"]["approved"] is True
    assert approved_reply["data"]["applied_amount"] == "15.00"

    # Exceeding cap ($50) -> escalated to specialist
    escalated_reply = svc.process_refund_or_dispute_impl(amount="50.00", state=dict(state_refund))
    assert escalated_reply["status"] == "ok"
    assert escalated_reply["data"]["approved"] is False
    assert escalated_reply["data"]["exceeds_self_serve_cap"] is True
    assert escalated_reply["data"]["must_escalate_immediately"] is True
    assert escalated_reply["data"]["escalation_reason"] == "refund_threshold_exceeded"
    assert escalated_reply["data"]["target_queue"] == "billing_specialist"
