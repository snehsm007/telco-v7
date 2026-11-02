from types import SimpleNamespace

import cxas_app.tools.send_password_reset_sms.python_function.python_code as tool


def test_send_password_reset_sms_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "phone_last4": "0143",
            "caller_provided_phone_last4": "0143",
            "auth_status": "pass",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_password_reset_sms()
    assert reply["status"] == "ok"
    assert reply["data"]["password_reset_sent"] is True
    assert reply["data"]["expires_in_minutes"] == 30
    assert reply["data"]["destination_phone_last4"] == "0143"
    assert "http" not in str(reply)
    assert "https" not in str(reply)
    assert session.state.get("password_reset_sent") is True


def test_send_password_reset_sms_unidentified_returns_error(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_password_reset_sms()
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_IDENTIFIED"
    assert "http" not in str(reply)


def test_send_password_reset_sms_with_identifier_lookup(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_password_reset_sms(identifier="2025550143")
    assert reply["status"] == "ok"
    assert reply["data"]["password_reset_sent"] is True
    assert reply["data"]["expires_in_minutes"] == 30
    assert "http" not in str(reply)


def test_send_password_reset_sms_dict_context(monkeypatch) -> None:
    ctx = {
        "account_id": "A1001",
        "phone_last4": "0143",
    }
    monkeypatch.setattr(tool, "context", ctx, raising=False)
    reply = tool.send_password_reset_sms()
    assert reply["status"] == "ok"
    assert reply["data"]["password_reset_sent"] is True


def test_send_password_reset_sms_none_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.send_password_reset_sms()
    assert reply["status"] == "ok"
    assert reply["data"]["password_reset_sent"] is True


def test_send_password_reset_sms_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "mock_error": "SYSTEM_DOWN",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_password_reset_sms()
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_send_password_reset_sms_localization_fr_and_es(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "phone_last4": "0143",
            "caller_provided_phone_last4": "0143",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)

    reply_fr = tool.send_password_reset_sms(language="fr-CA")
    assert reply_fr["status"] == "ok"
    assert "cellulaire" in reply_fr["data"]["spoken_summary"]

    session.state.pop("language", None)
    reply_es = tool.send_password_reset_sms(language="es-US")
    assert reply_es["status"] == "ok"
    assert "enlace de restablecimiento" in reply_es["data"]["spoken_summary"]


def test_send_password_reset_sms_honours_new_identifier_when_account_in_state(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "ACC-0199",
            "phone_last4": "0199",
            "caller_provided_phone_last4": "0199",
            "auth_status": "pass",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Caller corrects: that's not my number, send to 514-555-0102
    reply = tool.send_password_reset_sms(identifier="514-555-0102")
    assert reply["status"] == "ok"
    assert reply["data"]["destination_phone_last4"] == "0102"
    assert "0102" in reply["data"]["spoken_summary"]
    assert session.state["phone_last4"] == "0102"
    assert session.state["caller_provided_phone_last4"] == "0102"


def test_send_password_reset_sms_empty_phone_says_on_file(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "ACC-4651",
            "phone_last4": "",
            "caller_provided_phone_last4": "",
            "auth_status": "pass",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_password_reset_sms()
    assert reply["status"] == "ok"
    assert reply["data"]["destination_phone_last4"] == ""
    assert "on file" in reply["data"]["spoken_summary"]
