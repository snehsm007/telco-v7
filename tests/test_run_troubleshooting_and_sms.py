from types import SimpleNamespace

import cxas_app.tools.run_troubleshooting_and_sms.python_function.python_code as tool


def test_run_troubleshooting_and_sms_internet_default(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="internet", symptom="slow connection", send_sms_guide=True)
    assert res["status"] == "ok"
    assert res["data"]["diagnostic_status"] == "completed"
    assert res["data"]["remote_signal_sent"] is True
    assert res["data"]["sms_guide_sent"] is True
    assert session.state["troubleshooting_sms_sent"] is True


def test_run_troubleshooting_and_sms_tv_satellite(monkeypatch) -> None:
    session_dict = {"account_id": "A1002"}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="tv", symptom="error 101 on dish")
    assert res["status"] == "ok"
    assert res["data"]["diagnostic_status"] == "completed"
    assert session_dict["tv_sub_type"] == "satellite"


def test_run_troubleshooting_and_sms_tv_streaming(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="tv", tv_sub_type="streaming")
    assert res["status"] == "ok"
    assert session.state["tv_sub_type"] == "streaming"


def test_run_troubleshooting_and_sms_mobility_data(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="mobility", symptom="sim card data not working")
    assert res["status"] == "ok"
    assert len(res["data"]["concise_spoken_steps"]) > 0


def test_run_troubleshooting_and_sms_no_sms_without_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="internet", send_sms_guide=False)
    assert res["status"] == "ok"
    assert res["data"]["sms_guide_sent"] is False


def test_run_troubleshooting_and_sms_localization_french(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="internet", language="fr-CA")
    assert res["status"] == "ok"
    assert res["data"]["diagnostic_status"] == "completed"
    assert len(res["data"]["full_steps"]) > 0


def test_run_troubleshooting_and_sms_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.run_troubleshooting_and_sms(service_type="internet", language="es-US")
    assert res["status"] == "ok"
    assert res["data"]["diagnostic_status"] == "completed"


def test_run_troubleshooting_and_sms_verbal_steps_always_returned(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res_en = tool.run_troubleshooting_and_sms(service_type="internet", send_sms_guide=True, language="en-US")
    assert "verbal_steps" in res_en["data"]
    assert len(res_en["data"]["verbal_steps"]) >= 4

    res_fr = tool.run_troubleshooting_and_sms(service_type="internet", send_sms_guide=True, language="fr-CA")
    assert "verbal_steps" in res_fr["data"]
    assert len(res_fr["data"]["verbal_steps"]) >= 4
    assert res_fr["data"]["verbal_steps"] != res_en["data"]["verbal_steps"]


def test_run_troubleshooting_and_sms_repeat_call_fallback_to_verbal(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)

    # First call dispatches SMS guide
    r1 = tool.run_troubleshooting_and_sms(service_type="internet", send_sms_guide=True, language="en-US")
    assert r1["data"]["sms_guide_sent"] is True
    assert session.state["troubleshooting_sms_attempts"] == 1

    # Second call falls back to verbal steps directly without resending SMS
    r2 = tool.run_troubleshooting_and_sms(service_type="internet", send_sms_guide=True, language="en-US")
    assert r2["data"]["sms_guide_sent"] is False
    assert session.state["troubleshooting_sms_attempts"] == 2
    assert "Read the verbal_steps aloud" in r2["data"]["agent_action"]
    assert "walk you through" in r2["data"]["spoken_message"]


def test_run_troubleshooting_and_sms_declined_sms_fallback_to_verbal(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0143"})
    monkeypatch.setattr(tool, "context", session, raising=False)

    # Caller cannot receive SMS or SMS declined
    res = tool.run_troubleshooting_and_sms(service_type="mobility", send_sms_guide=False, language="fr-CA")
    assert res["data"]["sms_guide_sent"] is False
    assert session.state["troubleshooting_sms_attempts"] == 1
    assert "Lisez les verbal_steps" in res["data"]["agent_action"]
    assert "guider" in res["data"]["spoken_message"]

