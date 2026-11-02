from types import SimpleNamespace

import pytest
import cxas_app.tools.process_bill_payment.python_function.python_code as tool
from lib.services import process_bill_payment_impl


def test_process_bill_payment_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50", "is_suspended": True}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="85.50", card_last4="4242")
    assert reply["status"] == "ok"
    assert reply["data"]["payment_processed"] is True
    assert reply["data"]["amount_paid"] == "85.50"
    assert reply["data"]["service_restored"] is True
    assert session.state["service_restored"] is True
    assert session.state["current_balance"] == "0.00"


def test_process_bill_payment_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "auth_status": "pass", "current_balance": "50.00"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.process_bill_payment(amount="50.00")
    assert reply["status"] == "ok"
    assert reply["data"]["payment_processed"] is True


def test_process_bill_payment_context_none_with_inline_auth(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.process_bill_payment(
        amount="25.00",
        identifier="202 555 0143",
        verification_code="123456",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["payment_processed"] is True


def test_process_bill_payment_full_balance_string(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "95.00"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="full")
    assert reply["status"] == "ok"
    assert reply["data"]["amount_paid"] == "95.00"


def test_process_bill_payment_declined_card(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "payment_failure_count": 0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="50.00", card_last4="0000")
    assert reply["status"] == "error"
    assert reply["error"] == "PAYMENT_DECLINED"


def test_process_bill_payment_too_many_attempts(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "payment_failure_count": 2}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="50.00", card_last4="0000")
    assert reply["status"] == "error"
    assert reply["error"] == "TOO_MANY_ATTEMPTS"


def test_process_bill_payment_not_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="50.00")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_process_bill_payment_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="50.00")
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_process_bill_payment_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "50.00"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.process_bill_payment(amount="50.00", language="fr-CA")
    assert reply_fr["status"] == "ok"
    reply_es = tool.process_bill_payment(amount="50.00", language="es-US")
    assert reply_es["status"] == "ok"


def test_process_bill_payment_bank_preserves_card_last4(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "current_balance": "85.50",
            "card_last4": "4242",
            "bank_last4": "6789",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)

    res_onfile = tool.process_bill_payment(amount="85.50", payment_method="bank")
    assert res_onfile["status"] == "ok"
    assert res_onfile["data"]["bank_last4"] == "6789"
    assert res_onfile["data"]["card_last4"] == ""
    assert session.state["card_last4"] == "4242"
    assert session.state["bank_last4"] == "6789"

    res_explicit = tool.process_bill_payment(
        amount="85.50", payment_method="bank", bank_last4="001234561234"
    )
    assert res_explicit["status"] == "ok"
    assert res_explicit["data"]["bank_last4"] == "1234"
    assert res_explicit["data"]["card_last4"] == ""
    assert session.state["card_last4"] == "4242"
    assert session.state["bank_last4"] == "1234"

    res_declined = tool.process_bill_payment(
        amount="85.50", payment_method="bank", bank_last4="0000"
    )
    assert res_declined["status"] == "error"
    assert res_declined["error"] == "PAYMENT_DECLINED"
    assert session.state["card_last4"] == "4242"
    assert session.state["bank_last4"] == ""

    res_debit_card = tool.process_bill_payment(
        amount="85.50", payment_method="debit_card", card_last4="8844"
    )
    assert res_debit_card["status"] == "ok"
    assert res_debit_card["data"]["card_last4"] == "8844"
    assert session.state["card_last4"] == "8844"


def test_process_bill_payment_spoken_summary_and_suspension_avoided(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "current_balance": "85.50",
            "past_due_balance": "85.50",
            "card_last4": "4242",
            "is_suspended": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="85.50", card_last4="4242", language="en-US")
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["service_status"] == "active"
    assert data["suspension_avoided"] is True
    assert "spoken_summary" in data
    assert "spoken_message" in data
    summary = data["spoken_summary"]
    assert "Payment of $85.50 with the card ending in 4242 processed" in summary
    assert f"confirmation {data['confirmation_number']}" in summary
    assert "remaining balance $0.00" in summary
    assert "your service is active and no suspension is pending." in summary
    assert reply.get("spoken_message") == summary

    # fr-CA localization
    session.state["past_due_balance"] = "85.50"
    session.state["is_suspended"] = True
    reply_fr = tool.process_bill_payment(amount="85.50", card_last4="4242", language="fr-CA")
    assert reply_fr["status"] == "ok"
    data_fr = reply_fr["data"]
    assert data_fr["suspension_avoided"] is True
    assert data_fr["service_status"] == "active"
    summary_fr = data_fr["spoken_summary"]
    assert "Paiement de 85.50 $ avec la carte se terminant par 4242 traité" in summary_fr
    assert "solde restant 0.00 $" in summary_fr
    assert "votre service est actif et aucune suspension n'est en attente." in summary_fr


def test_process_bill_payment_spoken_summary_not_past_due(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "current_balance": "50.00",
            "past_due_balance": "0.00",
            "card_last4": "1122",
            "is_suspended": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="50.00", card_last4="1122", language="en-US")
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["service_status"] == "active"
    assert data["suspension_avoided"] is False
    assert "your service is active." in data["spoken_summary"]
    assert "no suspension is pending" not in data["spoken_summary"]


def test_process_bill_payment_bank_spoken_summary(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "pass",
            "current_balance": "85.50",
            "past_due_balance": "85.50",
            "bank_last4": "6789",
            "is_suspended": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="85.50", payment_method="bank", bank_last4="6789", language="en-US")
    assert reply["status"] == "ok"
    assert "bank account ending in 6789" in reply["data"]["spoken_summary"]


@pytest.mark.parametrize("locale,expected_phrase", [
    ("en-US", "confirm the card ending 4321 the caller named; do not mention other cards"),
    ("fr-CA", "confirmez la carte se terminant par 4321 nommée par le client; ne mentionnez pas d'autres cartes"),
    ("es-US", "confirme la tarjeta que termina en 4321 que el cliente nombró; no mencione otras tarjetas"),
])
def test_process_bill_payment_new_card_3_locales(locale: str, expected_phrase: str) -> None:
    st = {"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    rep = process_bill_payment_impl(
        amount="50.00", payment_method="new_card", card_last4="4321", language=locale, state=st
    )
    assert rep["status"] == "ok"
    assert rep["requested_card_last4"] == "4321"
    assert rep["data"]["requested_card_last4"] == "4321"
    assert "payment_methods_on_file" not in rep
    assert "payment_methods_on_file" not in rep.get("data", {})
    assert expected_phrase in rep["agent_action"]
    assert expected_phrase in rep["data"]["agent_action"]


@pytest.mark.parametrize("locale", ["en-US", "fr-CA", "es-US"])
def test_process_bill_payment_on_file_path_3_locales(locale: str) -> None:
    st = {"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    rep = process_bill_payment_impl(
        amount="50.00", payment_method="card_on_file", language=locale, state=st
    )
    assert rep["status"] == "ok"
    assert "payment_methods_on_file" not in rep
    assert "requested_card_last4" not in rep

