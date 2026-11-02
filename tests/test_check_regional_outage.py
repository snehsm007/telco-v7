from types import SimpleNamespace

import cxas_app.tools.check_regional_outage.python_function.python_code as tool


def test_check_regional_outage_active_with_sms_subscription(monkeypatch) -> None:
    session = SimpleNamespace(state={"language": "en-US"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.check_regional_outage(postal_code="H3Z 2Y7", service_type="internet", subscribe_sms=True)
    assert res["status"] == "ok"
    assert res["data"]["outage_active"] is True
    assert res["data"]["sms_subscribed"] is True
    assert session.state["outage_active"] is True
    assert session.state["outage_sms_subscribed"] is True


def test_check_regional_outage_normal_status_with_dict_context(monkeypatch) -> None:
    session_dict = {"postal_code": "M5V 2T6"}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.check_regional_outage(postal_code="M5V 2T6", service_type="internet")
    assert res["status"] == "ok"
    assert res["data"]["outage_active"] is False
    assert res["data"]["network_status"] == "normal"
    assert session_dict["outage_active"] is False


def test_check_regional_outage_missing_postal_code(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.check_regional_outage(postal_code="")
    assert res["status"] == "error"
    assert res["error"] == "MISSING_INPUT"


def test_check_regional_outage_localization_french(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.check_regional_outage(postal_code="H3Z 1A1", subscribe_sms="oui", language="fr-CA")
    assert res["status"] == "ok"
    assert res["data"]["outage_active"] is True
    assert res["data"]["sms_subscribed"] is True
    assert "SMS" in res["data"]["spoken_message"]


def test_check_regional_outage_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.check_regional_outage(postal_code="K1A 0B1", language="es-US")
    assert res["status"] == "ok"
    assert res["data"]["outage_active"] is False


def test_check_regional_outage_no_outage_offers_sms_guide_en(monkeypatch) -> None:
    session = SimpleNamespace(state={"language": "en-US"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.check_regional_outage(postal_code="M5V 2T6", service_type="internet")
    assert res["status"] == "ok"
    assert res["data"]["outage_active"] is False
    assert res["data"]["next_step"] == "offer_sms_troubleshooting_guide"
    assert "spoken_message" in res["data"]
    assert "troubleshooting steps to your mobile" in res["data"]["spoken_message"]
    assert "run_troubleshooting_and_sms" in res["data"]["agent_action"]


def test_check_regional_outage_no_outage_offers_sms_guide_fr(monkeypatch) -> None:
    session = SimpleNamespace(state={"language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.check_regional_outage(postal_code="H2X 1Y8", service_type="internet", language="fr-CA")
    assert res["status"] == "ok"
    assert res["data"]["outage_active"] is False
    assert res["data"]["next_step"] == "offer_sms_troubleshooting_guide"
    assert "spoken_message" in res["data"]
    assert "dépannage" in res["data"]["spoken_message"]
    assert "run_troubleshooting_and_sms" in res["data"]["agent_action"]


def test_check_regional_outage_postal_prefixes(monkeypatch) -> None:
    session = SimpleNamespace(state={"language": "en-US"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res_active = tool.check_regional_outage(postal_code="H3Z 2Y7")
    assert res_active["data"]["outage_active"] is True

    res_h3z1a1 = tool.check_regional_outage(postal_code="H3Z 1A1")
    assert res_h3z1a1["data"]["outage_active"] is True

    res_g1r = tool.check_regional_outage(postal_code="G1R 2J3")
    assert res_g1r["data"]["outage_active"] is True

    res_h2x1y4 = tool.check_regional_outage(postal_code="H2X 1Y4")
    assert res_h2x1y4["data"]["outage_active"] is False


