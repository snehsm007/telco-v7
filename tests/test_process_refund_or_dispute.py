from types import SimpleNamespace

import cxas_app.tools.process_refund_or_dispute.python_function.python_code as tool


def test_process_refund_or_dispute_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(amount="15.00", reason="incorrect charge")
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is True
    assert reply["data"]["applied_amount"] == "15.00"
    assert session.state["current_balance"] == "70.50"
    ref = reply["data"]["confirmation_number"]
    expected_confirm = (
        f"Your refund of $15.00 will appear on your next statement within 5 business days. "
        f"Your confirmation number is {ref}."
    )
    assert reply["data"]["verbatim_confirmation"] == expected_confirm
    assert reply["data"]["spoken_message"] == expected_confirm


def test_process_refund_or_dispute_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.process_refund_or_dispute(amount="10.00")
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is True


def test_process_refund_or_dispute_context_none_with_inline_auth(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.process_refund_or_dispute(
        amount="10.00",
        identifier="202 555 0143",
        verification_code="123456",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is True


def test_process_refund_or_dispute_duplicate_payment(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(amount="22.50", reason="overpayment duplicate bill")
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is True
    assert reply["data"]["refund_type"] == "duplicate_payment"


def test_process_refund_or_dispute_outage_credit(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(outage_days=3, dispute_type="outage_credit")
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is True
    assert reply["data"]["dispute_type"] == "outage_credit"
    assert reply["data"]["outage_days"] == 3


def test_process_refund_or_dispute_exceeds_cap(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(amount="50.00", reason="high fee dispute")
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is False
    assert reply["data"]["exceeds_self_serve_cap"] is True
    assert reply["data"]["target_queue"] == "billing_specialist"
    assert reply["data"]["verbatim_key"] == "transfer_to_specialist"
    assert reply["data"]["spoken_message"] == (
        "I'll connect you to a billing specialist now — they'll have everything we've already discussed."
    )
    assert reply["data"]["handoff_message"] == reply["data"]["spoken_message"]


def test_process_refund_or_dispute_exceeds_cap_french(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50", "language": "fr-CA"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(amount="50.00", reason="trop élevé", language="fr-CA")
    assert reply["status"] == "ok"
    assert reply["data"]["approved"] is False
    assert reply["data"]["exceeds_self_serve_cap"] is True
    assert reply["data"]["verbatim_key"] == "transfer_to_specialist"
    assert reply["data"]["spoken_message"] == (
        "Je vous mets maintenant en communication avec un spécialiste de la facturation — il aura déjà tout ce dont nous avons discuté."
    )
    assert reply["data"]["handoff_message"] == reply["data"]["spoken_message"]


def test_process_refund_or_dispute_not_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(amount="15.00")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_process_refund_or_dispute_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_refund_or_dispute(amount="15.00")
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_process_refund_or_dispute_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.process_refund_or_dispute(amount="10.00", language="fr-CA")
    assert reply_fr["status"] == "ok"
    ref_fr = reply_fr["data"]["confirmation_number"]
    expected_fr = (
        f"Votre remboursement de 10.00 $ figurera sur votre prochain relevé d'ici 5 jours ouvrables. "
        f"Votre numéro de confirmation est le {ref_fr}."
    )
    assert reply_fr["data"]["verbatim_confirmation"] == expected_fr
    assert reply_fr["data"]["spoken_message"] == expected_fr

    session_es = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session_es, raising=False)
    reply_es = tool.process_refund_or_dispute(amount="10.00", language="es-US")
    assert reply_es["status"] == "ok"
    ref_es = reply_es["data"]["confirmation_number"]
    expected_es = (
        f"Su reembolso de $10.00 aparecerá en su próximo estado de cuenta dentro de 5 días hábiles. "
        f"Su número de confirmación es {ref_es}."
    )
    assert reply_es["data"]["verbatim_confirmation"] == expected_es
    assert reply_es["data"]["spoken_message"] == expected_es


def test_handover_to_person_billing_specialist_verbatim_key() -> None:
    from lib.services import handover_to_person_impl
    state = {"account_id": "A1001", "auth_status": "pass"}
    reply = handover_to_person_impl(
        reason="refund_threshold_exceeded",
        target_queue="billing_specialist",
        language="en-US",
        state=state,
    )
    assert reply["status"] == "ok"
    assert reply["data"]["verbatim_key"] == "transfer_to_specialist"
    assert reply["data"]["spoken_message"] == (
        "I'll connect you to a billing specialist now — they'll have everything we've already discussed."
    )
