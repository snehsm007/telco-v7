from types import SimpleNamespace
import pytest

import cxas_app.tools.execute_suspend_restore.python_function.python_code as tool


def test_execute_suspend_restore_unauthenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="suspend")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_execute_suspend_vacation_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="suspend", reason="vacation")
    assert reply["status"] == "ok"
    assert reply["data"]["service_suspended"] is True
    assert reply["data"]["is_suspended"] is True
    assert reply["data"]["reduced_rate_monthly"] == "15.00"
    assert "confirmation_number" in reply["data"]
    assert session.state["is_suspended"] is True


def test_execute_suspend_other_reason(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="suspend", reason="travel")
    assert reply["status"] == "ok"
    assert reply["data"]["reduced_rate_monthly"] == "0.00"


def test_execute_restore_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "past_due_balance": "0.00",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="restore")
    assert reply["status"] == "ok"
    assert reply["data"]["service_restored"] is True
    assert reply["data"]["is_suspended"] is False
    assert reply["data"]["restoration_eta_minutes"] == 15
    assert session.state["is_suspended"] is False


def test_execute_restore_blocked_by_past_due(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "suspension_reason": "non_payment",
            "past_due_balance": "150.00",
            "payment_arrangement_active": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="restore")
    assert reply["status"] == "error"
    assert reply["error"] == "PAST_DUE_BALANCE_REQUIRED"


def test_execute_restore_caller_reported_payment_yesterday(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "suspension_reason": "non_payment",
            "past_due_balance": "85.50",
            "payment_arrangement_active": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(
        action="restore",
        caller_reported_payment="paid yesterday 85.50",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["status"] == "restored"
    assert reply["data"]["service_restored"] is True
    assert reply["data"]["restored_after_payment"] is True
    assert reply["data"]["is_suspended"] is False
    assert reply["data"]["past_due_balance"] == "0.00"
    assert reply["data"]["payment_verified"]["date"] == "2026-10-28"
    assert reply["data"]["payment_verified"]["amount"] == "85.50"
    assert "yesterday" in reply["data"]["spoken_summary"].lower()
    assert session.state["is_suspended"] is False
    assert session.state["service_restored"] is True
    assert session.state["past_due_balance"] == "0.00"


def test_execute_restore_forgot_to_pay_requires_payment_first(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "suspension_reason": "non_payment",
            "past_due_balance": "85.50",
            "payment_arrangement_active": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Attempting to restore without paying returns PAST_DUE_BALANCE_REQUIRED
    reply = tool.execute_suspend_restore(action="restore")
    assert reply["status"] == "error"
    assert reply["error"] == "PAST_DUE_BALANCE_REQUIRED"
    assert "process_bill_payment" in reply["agent_action"]
    assert reply["data"]["past_due_balance"] == "85.50"
    assert reply["data"]["payment_required"] is True

    # Now make payment in session
    session.state["past_due_balance"] = "0.00"
    session.state["service_restored"] = True
    session.state["is_suspended"] = False

    # Calling restore now succeeds
    reply2 = tool.execute_suspend_restore(action="restore")
    assert reply2["status"] == "ok"
    assert reply2["data"]["service_restored"] is True


def test_execute_restore_allowed_with_payment_arrangement(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "suspension_reason": "non_payment",
            "past_due_balance": "85.50",
            "payment_arrangement_active": True,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="restore")
    assert reply["status"] == "ok"
    assert reply["data"]["service_restored"] is True


def test_execute_suspend_inline_auth(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(
        action="suspend",
        identifier="2025550143",
        verification_code="1234",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["service_suspended"] is True


def test_execute_suspend_dict_context(monkeypatch) -> None:
    ctx = {"auth_status": "pass", "account_id": "A1001"}
    monkeypatch.setattr(tool, "context", ctx, raising=False)
    reply = tool.execute_suspend_restore(action="suspend")
    assert reply["status"] == "ok"
    assert reply["data"]["service_suspended"] is True


def test_execute_suspend_none_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.execute_suspend_restore(action="suspend")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_execute_suspend_localization(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="suspend", language="fr-CA")
    assert reply["status"] == "ok"
    assert session.state["language"] == "fr-CA"


@pytest.mark.parametrize(
    "lang,expected_action_prefix",
    [
        ("en-US", "Take the payment first"),
        ("fr-CA", "Effectuez d'abord le paiement"),
        ("es-US", "Tome el pago primero"),
    ],
)
def test_execute_restore_past_due_agent_action_localized(
    monkeypatch, lang: str, expected_action_prefix: str
) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "past_due_balance": "85.50",
            "language": lang,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore(action="restore", language=lang)
    assert reply["status"] == "error"
    assert reply["error"] == "PAST_DUE_BALANCE_REQUIRED"
    assert reply["agent_action"].startswith(expected_action_prefix)



def test_execute_restore_caller_reported_payment_boolean(monkeypatch) -> None:
    session_true = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "past_due_balance": "85.50",
            "payment_arrangement_active": False,
        }
    )
    monkeypatch.setattr(tool, "context", session_true, raising=False)
    reply_true = tool.execute_suspend_restore(
        action="restore",
        caller_reported_payment=True,
    )
    assert reply_true["status"] == "ok"
    assert reply_true["data"]["service_restored"] is True
    assert reply_true["data"]["caller_reported_payment_verified"] is True

    session_false = SimpleNamespace(
        state={
            "auth_status": "pass",
            "account_id": "A1001",
            "is_suspended": True,
            "past_due_balance": "85.50",
            "payment_arrangement_active": False,
        }
    )
    monkeypatch.setattr(tool, "context", session_false, raising=False)
    reply_false = tool.execute_suspend_restore(
        action="restore",
        caller_reported_payment=False,
    )
    assert reply_false["status"] == "error"
    assert reply_false["error"] == "PAST_DUE_BALANCE_REQUIRED"
