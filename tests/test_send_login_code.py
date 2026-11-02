from types import SimpleNamespace

import cxas_app.tools.send_login_code.python_function.python_code as tool


def test_send_login_code_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0143", "auth_status": "none", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "ok"
    assert reply["data"]["sent"] is True
    assert reply["data"]["destination_last4"] == "0143"
    assert session.state["auth_status"] == "code_sent"


def test_send_login_code_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "phone_last4": "0143"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.send_login_code(channel="sms")
    assert reply["status"] == "ok"
    assert reply["data"]["sent"] is True


def test_send_login_code_context_none_with_identifier(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.send_login_code(identifier="202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["sent"] is True


def test_send_login_code_already_verified(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "logged_in": True}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "ok"
    assert reply["data"]["already_verified"] is True


def test_send_login_code_too_many_attempts(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_failure_count": 3.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "error"
    assert reply["error"] == "TOO_MANY_ATTEMPTS"


def test_send_login_code_channel_email(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "none", "contact_email": "test@example.com"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code(channel="email")
    assert reply["status"] == "ok"
    assert reply["data"]["channel"] == "email"
    assert "masked_email" in reply["data"]


def test_send_login_code_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_send_login_code_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0143", "auth_status": "none"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.send_login_code(language="fr-CA")
    assert reply_fr["status"] == "ok"
    session.state["auth_status"] = "none"
    reply_es = tool.send_login_code(language="es-US")
    assert reply_es["status"] == "ok"


def test_send_login_code_unidentified_returns_error(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_IDENTIFIED"
    assert "agent_action" in reply
    assert "mobile number" in reply["agent_action"].lower() or "10-digit" in reply["agent_action"].lower()


def test_send_login_code_accepts_caller_given_phone_and_records_last4(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "ACC-4651", "phone_last4": ""})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code(identifier="514-555-0199")
    assert reply["status"] == "ok"
    assert reply["data"]["sent"] is True
    assert reply["data"]["destination_last4"] == "0199"
    assert session.state["caller_provided_phone_last4"] == "0199"
    assert session.state["phone_last4"] == "0199"


def test_send_login_code_sms_no_mobile_on_file_returns_no_mobile_on_file(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "phone_last4": "",
            "caller_provided_phone_last4": "",
            "auth_failure_count": 0,
            "login_attempts": 0,
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code(channel="sms")
    assert reply["status"] == "error"
    assert reply["error"] == "NO_MOBILE_ON_FILE"
    assert "agent_action" in reply
    assert "10-digit mobile number" in reply["agent_action"].lower()
    assert "lookup_account" in reply["agent_action"].lower()
    # No strike recorded and auth_status untouched
    assert session.state["auth_failure_count"] == 0
    assert session.state["login_attempts"] == 0
    assert session.state["auth_status"] == "none"
    assert not session.state.get("login_code_sent")


def test_send_login_code_sms_lookup_by_name_allows_otp_dispatch(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "ACC-1001",
            "phone_last4": "",
            "caller_provided_phone_last4": "",
            "lookup_by_name": True,
            "auth_failure_count": 0,
            "login_attempts": 0,
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code(channel="sms")
    assert reply["status"] == "ok"
    assert reply["data"]["sent"] is True
    assert reply["data"]["destination_last4"] == ""
    assert session.state["auth_status"] == "code_sent"
    assert session.state["login_code_sent"] is True



def test_send_login_code_email_masked_format_mirrors_persona(monkeypatch) -> None:
    session_marcus = SimpleNamespace(
        state={
            "account_id": "A1001",
            "first_name": "Marcus",
            "contact_email": "marcus@example.com",
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session_marcus, raising=False)
    reply_marcus = tool.send_login_code(channel="email")
    assert reply_marcus["status"] == "ok"
    assert reply_marcus["data"]["masked_email"] == "m***@example.com"
    assert "starting with 'm'" in reply_marcus["data"]["spoken_message"]
    assert "starting with m" in reply_marcus["data"]["agent_action"]

    session_riley = SimpleNamespace(
        state={
            "account_id": "A1001",
            "first_name": "Riley",
            "contact_email": "riley.t.design@example.com",
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session_riley, raising=False)
    reply_riley = tool.send_login_code(channel="email")
    assert reply_riley["status"] == "ok"
    assert reply_riley["data"]["masked_email"] == "r***@example.com"


def test_send_login_code_email_spoken_phrases_locales(monkeypatch) -> None:
    # Named emails include starting initial across en-US / fr-CA / es-US
    for locale, expected_spoken, expected_action in (
        ("en-US", "starting with 'c'", "starting with c"),
        ("fr-CA", "commençant par « c »", "commençant par c"),
        ("es-US", "comienza con 'c'", "comenzando con c"),
    ):
        session_named = SimpleNamespace(
            state={
                "account_id": "ACC-0198",
                "contact_email": "claire@example.com",
                "auth_status": "none",
            }
        )
        monkeypatch.setattr(tool, "context", session_named, raising=False)
        res_named = tool.send_login_code(channel="email", language=locale)
        assert res_named["data"]["masked_email"] == "c***@example.com"
        assert expected_spoken in res_named["data"]["spoken_message"]
        assert expected_action in res_named["data"]["agent_action"]

    # Synthetic placeholder emails omit fake initial 'u' while allowing domain confirmation
    session_en = SimpleNamespace(
        state={
            "account_id": "ACC-0198",
            "contact_email": "user0198@example.com",
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session_en, raising=False)
    res_en = tool.send_login_code(channel="email", language="en-US")
    assert res_en["data"]["masked_email"] == "***@example.com"
    assert res_en["data"]["email_domain"] == "example.com"
    assert "to the email address on file" in res_en["data"]["spoken_message"]
    assert "starting with" not in res_en["data"]["spoken_message"]
    assert "@example.com" in res_en["data"]["agent_action"]

    session_fr = SimpleNamespace(
        state={
            "account_id": "ACC-0198",
            "contact_email": "user0198@example.com",
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session_fr, raising=False)
    res_fr = tool.send_login_code(channel="email", language="fr-CA")
    assert res_fr["data"]["masked_email"] == "***@example.com"
    assert res_fr["data"]["email_domain"] == "example.com"
    assert "à l'adresse courriel au dossier" in res_fr["data"]["spoken_message"]
    assert "commençant par" not in res_fr["data"]["spoken_message"]
    assert "@example.com" in res_fr["data"]["agent_action"]

    session_es = SimpleNamespace(
        state={
            "account_id": "ACC-0198",
            "contact_email": "user0198@example.com",
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session_es, raising=False)
    res_es = tool.send_login_code(channel="email", language="es-US")
    assert res_es["data"]["masked_email"] == "***@example.com"
    assert res_es["data"]["email_domain"] == "example.com"
    assert "al correo electrónico registrado" in res_es["data"]["spoken_message"]
    assert "comienza con" not in res_es["data"]["spoken_message"]
    assert "@example.com" in res_es["data"]["agent_action"]

    # Caller-provided email in identifier updates contact_email without overwriting existing account_id
    session_caller_email = SimpleNamespace(
        state={
            "account_id": "ACC-0987",
            "contact_email": "user0987@example.com",
            "auth_status": "none",
        }
    )
    monkeypatch.setattr(tool, "context", session_caller_email, raising=False)
    res_dubois = tool.send_login_code(
        identifier="jl.dubois@example.fr",
        channel="email",
        language="fr-CA",
    )
    assert session_caller_email.state["account_id"] == "ACC-0987"
    assert session_caller_email.state["contact_email"] == "jl.dubois@example.fr"
    assert res_dubois["data"]["masked_email"] == "j***@example.fr"
    assert res_dubois["data"]["email_domain"] == "example.fr"
    assert "commençant par « j »" in res_dubois["data"]["spoken_message"]

    # Caller-provided email in identifier also resolves account when session has no account_id yet
    session_unidentified_email = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session_unidentified_email, raising=False)
    res_unid = tool.send_login_code(
        identifier="jl.dubois@example.fr",
        channel="email",
        language="fr-CA",
    )
    assert res_unid["status"] == "ok"
    assert session_unidentified_email.state["contact_email"] == "jl.dubois@example.fr"
    assert res_unid["data"]["masked_email"] == "j***@example.fr"
