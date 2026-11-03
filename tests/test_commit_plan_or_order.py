from types import SimpleNamespace
import pytest

import cxas_app.tools.commit_plan_or_order.python_function.python_code as tool


def test_commit_plan_or_order_plan_upgrade_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.commit_plan_or_order(plan_id="NET-GIG", order_type="plan_upgrade", confirmed=True)
    assert res["status"] == "ok"
    assert res["data"]["plan_id"] == "NET-GIG"
    assert res["data"]["effective_date"] == "immediate"
    assert res["data"]["sms_receipt_sent"] is True
    assert session.state["selected_plan_id"] == "NET-GIG"


def test_commit_plan_or_order_device_with_dict_context(monkeypatch) -> None:
    session_dict = {"auth_status": "pass", "account_id": "A1002", "service_address": "456 Oak St"}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.commit_plan_or_order(device_name="Wi-Fi Pod 2", order_type="device", confirmed=True)
    assert res["status"] == "ok"
    assert res["data"]["effective_date"] == "2 to 3 business days"
    assert res["data"]["shipping_address_on_file"] == "456 Oak St"


def test_commit_plan_or_order_unauthenticated(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.commit_plan_or_order(plan_id="NET-PLUS")
    assert res["status"] == "error"
    assert res["error"] == "NOT_AUTHENTICATED"


def test_commit_plan_or_order_localization_french(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.commit_plan_or_order(plan_id="NET-PLUS", language="fr-CA", confirmed=True)
    assert res["status"] == "ok"
    assert res["data"]["plan_id"] == "NET-PLUS"


def test_commit_plan_or_order_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.commit_plan_or_order(plan_id="NET-PLUS", language="es-US", confirmed=True)
    assert res["status"] == "ok"
    assert res["data"]["plan_id"] == "NET-PLUS"


def test_commit_plan_or_order_requires_confirmation_flow(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    # 1. Unconfirmed returns REQUIRES_CONFIRMATION
    res_unconfirmed = tool.commit_plan_or_order(plan_id="NET-PLUS", confirmed=False)
    assert res_unconfirmed["status"] == "error"
    assert res_unconfirmed["error"] == "REQUIRES_CONFIRMATION"
    data = res_unconfirmed["data"]
    assert "quote_summary" in data
    assert "monthly_total_with_tax" in data
    assert "estimated_tax" in data
    assert "contract_term" in data
    assert "read the quote" in res_unconfirmed["agent_action"].lower()
    assert "confirmed=true" in res_unconfirmed["agent_action"].lower()

    # 2. Confirmed returns ok
    res_confirmed = tool.commit_plan_or_order(plan_id="NET-PLUS", confirmed=True)
    assert res_confirmed["status"] == "ok"
    assert res_confirmed["data"]["order_id"] != ""
    assert "monthly_total_with_tax" in res_confirmed["data"]


def test_commit_plan_or_order_unknown_plan_id(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.commit_plan_or_order(plan_id="nonexistent_plan_xyz", confirmed=True)
    assert res["status"] == "error"
    assert res["error"] == "UNKNOWN_PLAN_ID"
    assert "valid_plan_ids" in res["data"]
    assert len(res["data"]["valid_plan_ids"]) > 0


@pytest.mark.parametrize(
    "lang,expected_action_keyword",
    [
        ("en-US", "read the quote"),
        ("fr-CA", "lisez le devis"),
        ("es-US", "lea la cotización"),
    ],
)
def test_commit_plan_or_order_requires_confirmation_agent_action_localized(
    monkeypatch, lang: str, expected_action_keyword: str
) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "language": lang})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.commit_plan_or_order(plan_id="NET-PLUS", confirmed=False, language=lang)
    assert res["status"] == "error"
    assert res["error"] == "REQUIRES_CONFIRMATION"
    assert expected_action_keyword in res["agent_action"].lower()


def test_commit_plan_or_order_tv_sports_addon_channels_and_combined_monthly(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Quote phase
    quote_res = tool.commit_plan_or_order(plan_id="ADDON-SPORTS", confirmed=False)
    assert quote_res["status"] == "error"
    assert quote_res["error"] == "REQUIRES_CONFIRMATION"
    assert "TSN 1-5" in quote_res["data"]["included_channels"]
    assert quote_res["data"]["combined_monthly_with_tv_starter"] == "43.00"
    assert quote_res["data"]["combined_monthly_with_tv_starter_with_tax"] == "49.45"

    # Confirmed order phase
    order_res = tool.commit_plan_or_order(plan_id="ADDON-SPORTS", confirmed=True)
    assert order_res["status"] == "ok"
    assert "TSN 1-5" in order_res["data"]["included_channels"]
    assert order_res["data"]["combined_monthly_with_tv_starter"] == "43.00"
    assert order_res["data"]["combined_monthly_with_tv_starter_with_tax"] == "49.45"


def test_commit_plan_or_order_attaches_current_active_plans_quote_and_confirmed(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)

    quote_res = tool.commit_plan_or_order(plan_id="NET-PLUS", confirmed=False, language="fr-CA")
    assert quote_res["status"] == "error"
    assert quote_res["error"] == "REQUIRES_CONFIRMATION"
    assert quote_res["data"]["current_active_plans"]["internet"]["plan_id"] == "NET-STARTER"
    assert quote_res["data"]["current_active_plans"]["internet"]["name"] == "Fibre Internet 100"

    order_res = tool.commit_plan_or_order(plan_id="NET-PLUS", confirmed=True, language="fr-CA")
    assert order_res["status"] == "ok"
    assert order_res["data"]["current_active_plans"]["internet"]["plan_id"] == "NET-PLUS"
    assert order_res["data"]["current_active_plans"]["internet"]["name"] == "Fibre Internet 500"
    assert order_res["data"]["current_active_plans"]["internet"]["monthly_price"] == "75.00"

    for plan_id, cat_key in (
        ("NET-GIG", "internet"),
        ("MOB-LITE", "mobility"),
        ("MOB-UNLTD", "mobility"),
        ("MOB-PREM", "mobility"),
        ("TV-MAX", "tv"),
    ):
        r_ok = tool.commit_plan_or_order(plan_id=plan_id, confirmed=True, language="en-US")
        assert r_ok["status"] == "ok"
        assert r_ok["data"]["current_active_plans"][cat_key]["plan_id"] == plan_id






@pytest.mark.parametrize(
    ("spoken", "plan_id"),
    [
        ("Sports Ultimate Pack", "ADDON-SPORTS"),
        ("sports", "ADDON-SPORTS"),
        ("Fibre Internet 500", "NET-PLUS"),
        ("5G Unlimited 60GB", "MOB-UNLTD"),
    ],
)
def test_commit_accepts_spoken_plan_names(monkeypatch, spoken, plan_id) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.commit_plan_or_order(plan_id=spoken, confirmed=True)
    assert res["status"] == "ok"
    assert res["data"]["plan_id"] == plan_id


def test_commit_ambiguous_name_still_lists_valid_ids(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"}), raising=False)
    res = tool.commit_plan_or_order(plan_id="internet", confirmed=True)
    assert res["error"] == "UNKNOWN_PLAN_ID"
    assert "NET-PLUS" in res["data"]["valid_plan_ids"]
