from types import SimpleNamespace

import cxas_app.tools.manage_warranty_claim.python_function.python_code as tool


def test_manage_warranty_claim_swollen_battery_safety_override(monkeypatch) -> None:
    # Swollen battery hazard gives immediate safety advice, requires auth for claim (Defect 9)
    session = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_warranty_claim(issue_description="The battery is swollen and bulging")
    assert res["status"] == "ok"
    assert res["data"]["safety_hazard"] is True
    assert res["data"]["claim_status"] == "pending_authentication"
    assert res["data"]["requires_authentication"] is True
    assert "battery" in res["data"]["urgent_safety_instructions"].lower()

    # Once authenticated, replacement claim is filed
    session.state["auth_status"] = "pass"
    res_auth = tool.manage_warranty_claim(issue_description="The battery is swollen and bulging")
    assert res_auth["status"] == "ok"
    assert res_auth["data"]["claim_status"] == "urgent_safety_replacement"
    assert session.state["warranty_claim_id"] == res_auth["data"]["warranty_claim_id"]


def test_manage_warranty_claim_swollen_battery_french_localization(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_warranty_claim(issue_description="La batterie est gonflée", language="fr-CA")
    assert res["status"] == "ok"
    assert res["data"]["safety_hazard"] is True
    assert "batterie" in res["data"]["urgent_safety_instructions"].lower()


def test_manage_warranty_claim_unauthenticated_regular_issue(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.manage_warranty_claim(issue_description="The screen flickers occasionally")
    assert res["status"] == "error"
    assert res["error"] == "NOT_AUTHENTICATED"


def test_manage_warranty_claim_requires_damage_screening(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_warranty_claim(issue_description="The screen flickers occasionally")
    assert res["status"] == "ok"
    assert res["data"]["requires_damage_check"] is True
    assert session.state["warranty_damage_checked"] is True


def test_manage_warranty_claim_rejected_for_physical_damage(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_warranty_claim(
        issue_description="Dropped phone in water",
        has_physical_or_liquid_damage=True,
    )
    assert res["status"] == "ok"
    assert res["data"]["warranty_covered"] is False
    assert res["data"]["claim_status"] == "rejected_physical_or_liquid_damage"


def test_manage_warranty_claim_approved_with_dict_context(monkeypatch) -> None:
    session_dict = {"auth_status": "pass", "account_id": "A1001"}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.manage_warranty_claim(
        issue_description="Internal microphone failure",
        has_physical_or_liquid_damage=False,
        damage_screened=True,
    )
    assert res["status"] == "ok"
    assert res["data"]["warranty_covered"] is True
    assert res["data"]["claim_status"] == "approved"
    assert "warranty_claim_id" in res["data"]


def test_manage_warranty_claim_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.manage_warranty_claim(issue_description="Humo saliendo de la batería (smoke)", language="es-US")
    assert res["status"] == "ok"
    assert res["data"]["safety_hazard"] is True
    assert "batería" in res["data"]["urgent_safety_instructions"].lower()
