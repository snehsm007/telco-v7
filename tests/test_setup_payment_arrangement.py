from types import SimpleNamespace

import cxas_app.tools.setup_payment_arrangement.python_function.python_code as tool


def test_setup_payment_arrangement_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "100.00", "is_suspended": True}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_payment_arrangement(extension_days=14, installments=2, amount="100.00")
    assert reply["status"] == "ok"
    assert reply["data"]["arrangement_active"] is True
    assert reply["data"]["deferred_amount"] == "100.00"
    assert reply["data"]["installments"] == 2
    assert reply["data"]["service_restored"] is True
    assert session.state["service_restored"] is True
    assert session.state["payment_arrangement_active"] is True


def test_setup_payment_arrangement_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.setup_payment_arrangement()
    assert reply["status"] == "ok"
    assert reply["data"]["arrangement_active"] is True


def test_setup_payment_arrangement_context_none_with_inline_auth(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.setup_payment_arrangement(
        identifier="202 555 0143",
        verification_code="123456",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["arrangement_active"] is True


def test_setup_payment_arrangement_default_balance(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_payment_arrangement(amount="")
    assert reply["status"] == "ok"
    assert reply["data"]["deferred_amount"] == "85.50"


def test_setup_payment_arrangement_not_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_payment_arrangement()
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_setup_payment_arrangement_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_payment_arrangement()
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_setup_payment_arrangement_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.setup_payment_arrangement(language="fr-CA")
    assert reply_fr["status"] == "ok"
    reply_es = tool.setup_payment_arrangement(language="es-US")
    assert reply_es["status"] == "ok"


def test_setup_payment_arrangement_restoration_summary_and_agent_action(monkeypatch) -> None:
    # English default
    session_en = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50", "is_suspended": True}
    )
    monkeypatch.setattr(tool, "context", session_en, raising=False)
    reply_en = tool.setup_payment_arrangement(extension_days=14, installments=2, amount="85.50", language="en-US")
    assert reply_en["status"] == "ok"
    arr_id = reply_en["data"]["arrangement_id"]
    assert reply_en["data"]["confirmation_number"] == arr_id
    assert reply_en["confirmation_number"] == arr_id

    # Check spoken_summary (envelope and payload)
    summary_en = reply_en["spoken_summary"]
    assert summary_en == reply_en["data"]["spoken_summary"]
    assert f"Payment arrangement {arr_id}" in summary_en
    assert "in 2 installments of $42.75" in summary_en
    assert "suspended service has been restored and will be back on within 15 minutes" in summary_en

    # Check agent_action (envelope and payload)
    action_en = reply_en["agent_action"]
    assert action_en == reply_en["data"]["agent_action"]
    assert f"confirm payment arrangement {arr_id}" in action_en
    assert "suspended service has been restored within 15 minutes" in action_en

    # French localization
    session_fr = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50", "is_suspended": True}
    )
    monkeypatch.setattr(tool, "context", session_fr, raising=False)
    reply_fr = tool.setup_payment_arrangement(extension_days=14, installments=2, amount="85.50", language="fr-CA")
    assert reply_fr["status"] == "ok"
    summary_fr = reply_fr["spoken_summary"]
    assert "L'entente de paiement" in summary_fr
    assert "service suspendu a été rétabli et sera de nouveau fonctionnel d'ici 15 minutes" in summary_fr
    action_fr = reply_fr["agent_action"]
    assert "confirmez que l'entente de paiement" in action_fr
    assert "service suspendu a été rétabli d'ici 15 minutes" in action_fr

    # Spanish localization
    session_es = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "current_balance": "85.50", "is_suspended": True}
    )
    monkeypatch.setattr(tool, "context", session_es, raising=False)
    reply_es = tool.setup_payment_arrangement(extension_days=14, installments=2, amount="85.50", language="es-US")
    assert reply_es["status"] == "ok"
    summary_es = reply_es["spoken_summary"]
    assert "El acuerdo de pago" in summary_es
    assert "servicio suspendido ha sido restablecido y estará funcionando dentro de 15 minutos" in summary_es
    action_es = reply_es["agent_action"]
    assert "confirme que el acuerdo de pago" in action_es
    assert "servicio suspendido ha sido restablecido dentro de 15 minutos" in action_es

