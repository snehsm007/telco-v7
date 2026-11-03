from types import SimpleNamespace

import cxas_app.tools.handover_to_person.python_function.python_code as tool


def test_handover_to_person_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "language": "en-US"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.handover_to_person(reason="caller_requested")
    assert reply["status"] == "ok"
    assert reply["data"]["handoff_status"] == "completed_via_specialist_queue"
    assert reply["data"]["target_queue"] == "customer_service"
    assert session.state["handover_complete"] is True
    assert "representative" in session.state["handoff_message"].lower()


def test_handover_to_person_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "language": "en-US"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.handover_to_person(reason="agent_assistance")
    assert reply["status"] == "ok"
    assert state_dict["handover_complete"] is True


def test_handover_to_person_context_none(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.handover_to_person(reason="caller_requested")
    assert reply["status"] == "ok"
    assert reply["data"]["handoff_status"] == "completed_via_specialist_queue"


def test_handover_to_person_with_queue_and_summary(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.handover_to_person(
        reason="complex_billing",
        target_queue="billing_specialist",
        summary="Customer has unresolved charge questions",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["target_queue"] == "billing_specialist"
    assert session.state["handoff_reason"] == "complex_billing"


def test_handover_to_person_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.handover_to_person()
    assert reply["status"] == "error"
    assert reply["error"] == "SYSTEM_DOWN"


def test_handover_to_person_localization(monkeypatch) -> None:
    session_fr = SimpleNamespace(state={"account_id": "A1001", "language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session_fr, raising=False)
    reply_fr = tool.handover_to_person(reason="besoin d'aide", language="fr-CA")
    assert reply_fr["status"] == "ok"
    assert "représentant" in session_fr.state["handoff_message"]

    session_es = SimpleNamespace(state={"account_id": "A1001", "language": "es-US"})
    monkeypatch.setattr(tool, "context", session_es, raising=False)
    reply_es = tool.handover_to_person(reason="ayuda", language="es-US")
    assert reply_es["status"] == "ok"
    assert "representante" in session_es.state["handoff_message"].lower()


def test_handover_to_person_preserves_french_session_when_model_passes_en_us(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.handover_to_person(language="en-US", reason="transfer_to_representative")
    assert reply["status"] == "ok"
    assert reply["active_language"] == "fr-CA"
    assert reply["data"]["language"] == "fr-CA"
    assert session.state["language"] == "fr-CA"
    assert "représentant" in session.state["handoff_message"].lower()
