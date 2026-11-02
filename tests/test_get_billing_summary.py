from types import SimpleNamespace
import pytest

import cxas_app.tools.get_billing_summary.python_function.python_code as tool


def test_get_billing_summary_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "ok"
    assert "85.50" in reply["data"]["current_balance"]
    assert "due_date" in reply["data"]


def test_get_billing_summary_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "ok"
    assert "85.50" in reply["data"]["current_balance"]


def test_get_billing_summary_context_none_with_inline_auth(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.get_billing_summary(identifier="202 555 0143", verification_code="123456")
    assert reply["status"] == "ok"


def test_get_billing_summary_not_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_get_billing_summary_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_get_billing_summary_suspended_and_autopay(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "is_suspended": True,
            "suspension_reason": "past_due",
            "autopay_enrolled": True,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "ok"
    assert reply["data"]["is_suspended"] is True
    assert reply["data"]["autopay_enrolled"] is True


def test_get_billing_summary_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.get_billing_summary(language="fr-CA")
    assert reply_fr["status"] == "ok"
    reply_es = tool.get_billing_summary(language="es-US")
    assert reply_es["status"] == "ok"


def test_get_billing_summary_restoration_facts_when_payment_covers_past_due(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "past_due_balance": "0.00"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["service_status"] == "eligible_for_restoration"
    assert "restoration_hint" in data
    assert "execute_suspend_restore" in data["restoration_hint"]
    assert data["last_payment"]["covers_past_due"] is True
    assert data["last_payment"]["amount"] == "85.50"
    assert data["last_payment"]["posted_date"] == "2026-10-15"
    assert data["last_payment"]["method_last4"] == "7742"

    # When past-due balance is present and unverified, service is suspended and requires payment
    session_past_due = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "past_due_balance": "85.50",
            "is_suspended": True,
        }
    )
    monkeypatch.setattr(tool, "context", session_past_due, raising=False)
    reply_past_due = tool.get_billing_summary()
    assert reply_past_due["status"] == "ok"
    data_pd = reply_past_due["data"]
    assert data_pd["service_status"] == "suspended"
    assert data_pd["last_payment"]["covers_past_due"] is False
    assert "Payment of past due balance is required" in data_pd["restoration_hint"]


def test_get_billing_summary_reconciles_and_surfaces_payment_methods(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "current_balance": "85.50",
            "card_last4": "7742",
            "bank_last4": "6789",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary()
    assert reply["status"] == "ok"
    data = reply["data"]

    # Reconciliation fields
    assert data["statement_total"] == "307.50"
    assert data["payments_received"] == "171.00"
    assert data["credits_applied"] == "51.00"
    assert data["amount_due"] == "85.50"
    assert data["current_balance"] == "85.50"
    assert data["adjustments"] == [{"description": "Account credit", "amount": "-51.00"}]

    from decimal import Decimal

    stmt = Decimal(data["statement_total"])
    pmts = Decimal(data["payments_received"])
    creds = Decimal(data["credits_applied"])
    due = Decimal(data["amount_due"])
    assert stmt - pmts - creds == due == Decimal("85.50")

    # Payment methods on file
    methods = data["payment_methods_on_file"]
    assert len(methods) == 3
    assert methods[0] == {"type": "card", "last4": "7742", "primary": True}
    assert methods[1] == {"type": "card", "last4": "8844"}
    assert methods[2] == {"type": "bank", "last4": "6789"}

    # Spoken summary
    assert "spoken_summary" in data
    assert "$85.50" in data["spoken_summary"]
    assert "$307.50" in data["spoken_summary"]
    assert "$171.00" in data["spoken_summary"]
    assert "$51.00" in data["spoken_summary"]

    # French localization
    reply_fr = tool.get_billing_summary(language="fr-CA")
    assert reply_fr["status"] == "ok"
    fr_summary = reply_fr["data"]["spoken_summary"]
    assert "85.50 $" in fr_summary or "85,50 $" in fr_summary
    assert "307.50 $" in fr_summary or "307,50 $" in fr_summary


def test_get_billing_summary_reconciliation_for_all_accounts(monkeypatch) -> None:
    from decimal import Decimal
    from lib.fakes import ACCOUNTS, find_account

    test_accounts = [acc["account_id"] for acc in ACCOUNTS]
    # Add synthesized account IDs as well
    for sample_id in ("2025550198", "5145550199", "928374651"):
        acct = find_account(sample_id)
        if acct:
            test_accounts.append(acct["account_id"])

    for acct_id in test_accounts:
        session = SimpleNamespace(
            state={
                "account_id": acct_id,
                "auth_status": "pass",
                "current_balance": "85.50",
            }
        )
        monkeypatch.setattr(tool, "context", session, raising=False)
        reply = tool.get_billing_summary()
        assert reply["status"] == "ok"
        data = reply["data"]
        stmt = Decimal(str(data["statement_total"]))
        pmts = Decimal(str(data["payments_received"]))
        creds = Decimal(str(data["credits_applied"]))
        due = Decimal(str(data["amount_due"]))
        bal = Decimal(str(data["current_balance"]))
        assert stmt - pmts - creds == due == bal


def test_get_billing_summary_agent_action_guides_payment_methods(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "current_balance": "85.50",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_en = tool.get_billing_summary(language="en-US")
    assert reply_en["status"] == "ok"
    assert "offer payment methods on file only if the caller has not named one" in reply_en["data"]["agent_action"]
    assert reply_en["agent_action"] == reply_en["data"]["agent_action"]

    reply_fr = tool.get_billing_summary(language="fr-CA")
    assert reply_fr["status"] == "ok"
    assert "ne proposez les modes de paiement au dossier" in reply_fr["data"]["agent_action"]


@pytest.mark.parametrize(
    "lang,expected_adj,expected_hint_keyword",
    [
        ("en-US", "Account credit", "Payment of past due balance"),
        ("fr-CA", "Crédit au compte", "Le paiement du solde en souffrance"),
        ("es-US", "Crédito en cuenta", "Se requiere el pago del saldo vencido"),
    ],
)
def test_get_billing_summary_adjustments_and_restoration_hint_localized(
    monkeypatch, lang: str, expected_adj: str, expected_hint_keyword: str
) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "is_suspended": True,
            "past_due_balance": "85.50",
            "language": lang,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.get_billing_summary(language=lang)
    assert res["status"] == "ok"
    data = res["data"]
    assert data["adjustments"][0]["description"] == expected_adj
    assert expected_hint_keyword in data["restoration_hint"]



