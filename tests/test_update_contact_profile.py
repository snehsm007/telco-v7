from types import SimpleNamespace

import cxas_app.tools.update_contact_profile.python_function.python_code as tool


def test_update_contact_profile_unauthenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile(email="test@example.com")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_update_contact_profile_missing_inputs(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile()
    assert reply["status"] == "error"
    assert reply["error"] == "MISSING_INPUT"


def test_update_contact_profile_email_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"auth_status": "pass", "account_id": "A1001", "contact_email": "old@example.com"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile(email="new.email@example.com")
    assert reply["status"] == "ok"
    assert reply["data"]["profile_updated"] is True
    assert reply["data"]["updated_fields"]["email"] == "new.email@example.com"
    assert "confirmation_number" in reply["data"]
    assert session.state["contact_email"] == "new.email@example.com"


def test_update_contact_profile_address_and_postal_code(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile(
        service_address="123 Main St, Ottawa, ON",
        postal_code="k1p 1j1",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["profile_updated"] is True
    assert reply["data"]["updated_fields"]["postal_code"] == "K1P 1J1"
    assert session.state["postal_code"] == "K1P 1J1"


def test_update_contact_profile_preferred_language(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile(preferred_language_update="fr-CA")
    assert reply["status"] == "ok"
    assert reply["data"]["updated_fields"]["preferred_language"] == "fr-CA"
    assert session.state["preferred_language"] == "fr-CA"


def test_update_contact_profile_inline_auth(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile(
        email="verified@example.com",
        identifier="2025550143",
        verification_code="1234",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["profile_updated"] is True


def test_update_contact_profile_dict_context(monkeypatch) -> None:
    ctx = {"auth_status": "pass", "account_id": "A1001"}
    monkeypatch.setattr(tool, "context", ctx, raising=False)
    reply = tool.update_contact_profile(email="ctx@example.com")
    assert reply["status"] == "ok"
    assert reply["data"]["profile_updated"] is True


def test_update_contact_profile_none_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.update_contact_profile(email="none@example.com")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_update_contact_profile_localization(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile(
        email="es@example.com",
        language="es-US",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["profile_updated"] is True
    assert session.state["language"] == "es-US"
