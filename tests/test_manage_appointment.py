from types import SimpleNamespace

import cxas_app.tools.manage_appointment.python_function.python_code as tool


def test_manage_appointment_reschedule_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "active_appointment_id": "APT-4021"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_appointment(action="reschedule", selected_slot="SLOT-2")
    assert res["status"] == "ok"
    assert res["data"]["appointment_rescheduled"] is True
    assert res["data"]["slot_id"] == "SLOT-2"
    assert session.state["appointment_status"] == "rescheduled"


def test_manage_appointment_cancel_requires_confirmation(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_appointment(action="cancel", confirmed_cancel=False)
    assert res["status"] == "ok"
    assert res["data"]["requires_confirmation"] is True
    assert res["data"]["appointment_cancelled"] is False


def test_manage_appointment_cancel_confirmed_with_dict(monkeypatch) -> None:
    session_dict = {"auth_status": "pass", "account_id": "A1001", "appointment_cancel_confirmed": True}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.manage_appointment(action="cancel", confirmed_cancel=True)
    assert res["status"] == "ok"
    assert res["data"]["appointment_cancelled"] is True
    assert session_dict["appointment_status"] == "cancelled"


def test_manage_appointment_cannot_cancel_when_technician_en_route(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "technician_status": "en_route"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_appointment(action="cancel", confirmed_cancel=True, technician_en_route=True)
    assert res["status"] == "error"
    assert res["error"] == "CANNOT_CANCEL_EN_ROUTE"
    assert res["data"]["can_cancel"] is False


def test_manage_appointment_unauthenticated(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.manage_appointment(action="reschedule")
    assert res["status"] == "error"
    assert res["error"] == "NOT_AUTHENTICATED"


def test_manage_appointment_localization_french(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_appointment(action="cancel", confirmed_cancel=False, language="fr-CA")
    assert res["status"] == "ok"
    assert "annuler" in res["data"]["spoken_message"].lower()


def test_manage_appointment_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_appointment(action="cancel", confirmed_cancel=False, language="es-US")
    assert res["status"] == "ok"
    assert "cancelar" in res["data"]["spoken_message"].lower()


def test_manage_appointment_reschedule_numeric_and_spanish_window(monkeypatch) -> None:
    import inspect

    sig = inspect.signature(tool.manage_appointment)
    assert sig.parameters["selected_slot"].annotation == (str | int | float)

    session = SimpleNamespace(
        state={"auth_status": "pass", "account_id": "A1001", "active_appointment_id": "APT-4021"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)

    for slot_arg in (2, "2", 2.0, "Slot 2"):
        res = tool.manage_appointment(action="reschedule", selected_slot=slot_arg, language="en-US")
        assert res["status"] == "ok"
        assert res["data"]["slot_id"] == "SLOT-2"

    res_es = tool.manage_appointment(action="reschedule", selected_slot="Tarde", language="es-US")
    assert res_es["status"] == "ok"
    assert res_es["data"]["slot_id"] == "SLOT-2"

    res_s3 = tool.manage_appointment(action="reschedule", selected_slot=3, language="en-US")
    assert res_s3["status"] == "ok"
    assert res_s3["data"]["slot_id"] == "SLOT-3"


def test_manage_appointment_reschedule_dynamic_dates(monkeypatch) -> None:
    from datetime import date, timedelta

    today = date.today()
    session = SimpleNamespace(
        state={"auth_status": "pass", "account_id": "A1001", "active_appointment_id": "APT-4021"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)

    res_slot2 = tool.manage_appointment(action="reschedule", selected_slot="SLOT-2", language="en-US")
    assert res_slot2["status"] == "ok"
    assert res_slot2["data"]["slot_id"] == "SLOT-2"
    assert res_slot2["data"]["scheduled_date"] == (today + timedelta(days=2)).isoformat()

    res_slot3 = tool.manage_appointment(action="reschedule", selected_slot="SLOT-3", language="en-US")
    assert res_slot3["status"] == "ok"
    assert res_slot3["data"]["slot_id"] == "SLOT-3"
    assert date.fromisoformat(res_slot3["data"]["scheduled_date"]).weekday() == 5  # next Saturday

    res_fallback = tool.manage_appointment(action="reschedule", selected_slot="", language="en-US")
    assert res_fallback["status"] == "error"
    assert res_fallback["data"]["appointment_rescheduled"] is False
    assert "available_slots" in res_fallback["data"]



def test_reschedule_to_saturday_by_weekday_name(monkeypatch) -> None:
    from datetime import date

    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    for spoken, lang in (("Saturday morning", "en-US"), ("samedi", "fr-CA")):
        res = tool.manage_appointment(action="reschedule", selected_slot=spoken, language=lang)
        assert res["status"] == "ok", res
        assert date.fromisoformat(res["data"]["scheduled_date"]).weekday() == 5
