from types import SimpleNamespace
import pytest

import cxas_app.tools.get_appointment_and_ticket_status.python_function.python_code as tool


def test_get_appointment_and_ticket_status_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.get_appointment_and_ticket_status()
    assert res["status"] == "ok"
    assert res["data"]["appointment_id"] == "APT-4021"
    assert len(res["data"]["available_slots"]) == 3
    assert session.state["active_appointment_id"] == "APT-4021"
    assert session.state["appointment_status"] == "scheduled"
    assert session.state["technician_status"] == "scheduled"


def test_get_appointment_and_ticket_status_with_dict_context(monkeypatch) -> None:
    session_dict = {"auth_status": "pass", "account_id": "A1002"}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.get_appointment_and_ticket_status()
    assert res["status"] == "ok"
    assert res["data"]["ticket_id"] == "TKT-8841"
    assert len(res["data"]["available_slots"]) == 3


def test_get_appointment_and_ticket_status_unauthenticated(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.get_appointment_and_ticket_status()
    assert res["status"] == "error"
    assert res["error"] == "NOT_AUTHENTICATED"


def test_get_appointment_and_ticket_status_localization_french(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.get_appointment_and_ticket_status(language="fr-CA")
    assert res["status"] == "ok"
    assert res["data"]["technician_status"] == "scheduled"
    assert len(res["data"]["available_slots"]) == 3


def test_get_appointment_and_ticket_status_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.get_appointment_and_ticket_status(language="es-US")
    assert res["status"] == "ok"
    assert res["data"]["appointment_id"] == "APT-4021"


@pytest.mark.parametrize(
    "lang,expected_window_display,expected_slot1_window",
    [
        ("en-US", "8:00 AM - 12:00 PM", "Morning (8:00 AM - 12:00 PM)"),
        ("fr-CA", "8 h 00 - 12 h 00", "Matin (8 h 00 - 12 h 00)"),
        ("es-US", "8:00 AM - 12:00 PM", "Mañana (8:00 AM - 12:00 PM)"),
    ],
)
def test_get_appointment_and_ticket_status_single_language_replies(
    monkeypatch, lang: str, expected_window_display: str, expected_slot1_window: str
) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.get_appointment_and_ticket_status(language=lang)
    assert res["status"] == "ok"
    data = res["data"]
    # Check arrival_window and window_display at top-level and in active_appointment
    assert data["arrival_window"] == expected_window_display
    assert data["window_display"] == expected_window_display
    assert data["active_appointment"]["arrival_window"] == expected_window_display
    assert data["active_appointment"]["window_display"] == expected_window_display

    # Check available_slots single localized window field and absence of _en/_fr/_es siblings
    slots = data["available_slots"]
    assert len(slots) == 3
    assert slots[0]["window"] == expected_slot1_window
    for s in slots:
        assert "window" in s
        assert "window_en" not in s
        assert "window_fr" not in s
        assert "window_es" not in s


def test_get_appointment_and_ticket_status_dynamic_relative_dates(monkeypatch) -> None:
    from datetime import date, timedelta

    today = date.today()
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.get_appointment_and_ticket_status(language="en-US")
    assert res["status"] == "ok"
    data = res["data"]
    assert data["scheduled_date"] == today.isoformat()
    assert data["active_appointment"]["scheduled_date"] == today.isoformat()
    assert data["repair_ticket"]["reported_date"] == (today - timedelta(days=2)).isoformat()
    slots = data["available_slots"]
    assert slots[0]["date"] == (today + timedelta(days=2)).isoformat()
    assert slots[1]["date"] == (today + timedelta(days=2)).isoformat()
    assert date.fromisoformat(slots[2]["date"]).weekday() == 5 and slots[2]["weekday"] == "Saturday"


