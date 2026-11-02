from types import SimpleNamespace
import pytest

import cxas_app.tools.browse_plans_and_coverage.python_function.python_code as tool


def test_browse_plans_and_coverage_internet_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="internet", postal_code="H3Z 2Y7", max_budget="80")
    assert res["status"] == "ok"
    assert res["data"]["category"] == "internet"
    assert len(res["data"]["shortlisted_plans"]) > 0
    assert res["data"]["fiber_coverage_available"] is True
    assert session.state["postal_code"] == "H3Z 2Y7"


def test_browse_plans_and_coverage_tv_with_dict_context(monkeypatch) -> None:
    session_dict = {}
    monkeypatch.setattr(tool, "context", session_dict, raising=False)
    res = tool.browse_plans_and_coverage(category="tv", service_address="123 Main St")
    assert res["status"] == "ok"
    assert res["data"]["category"] == "tv"
    assert len(res["data"]["shortlisted_plans"]) > 0
    assert session_dict["service_address"] == "123 Main St"


def test_browse_plans_and_coverage_mobility_without_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    res = tool.browse_plans_and_coverage(category="mobility")
    assert res["status"] == "ok"
    assert res["data"]["category"] == "mobility"
    assert res["data"]["five_g_coverage_available"] is True


def test_browse_plans_and_coverage_localization_french(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="internet", language="fr-CA")
    assert res["status"] == "ok"
    assert len(res["data"]["shortlisted_plans"]) > 0


def test_browse_plans_and_coverage_localization_spanish(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="internet", language="es-US")
    assert res["status"] == "ok"
    assert len(res["data"]["shortlisted_plans"]) > 0


def test_browse_plans_and_coverage_french_comma_max_budget(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res_dot = tool.browse_plans_and_coverage(
        category="internet", postal_code="H3Z 2Y7", max_budget="60.00", language="fr-CA"
    )
    res_comma = tool.browse_plans_and_coverage(
        category="internet", postal_code="H3Z 2Y7", max_budget="60,00 $", language="fr-CA"
    )
    ids_dot = [p["id"] for p in res_dot["data"]["shortlisted_plans"]]
    ids_comma = [p["id"] for p in res_comma["data"]["shortlisted_plans"]]
    assert ids_comma == ids_dot == ["NET-STARTER"]
    assert all(float(p["monthly_price"]) <= 60.0 for p in res_comma["data"]["shortlisted_plans"])


def test_browse_plans_and_coverage_catalog_coherence_tax_speed_addons(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="internet", postal_code="H3Z 2Y7")
    assert res["status"] == "ok"
    plans = res["data"]["shortlisted_plans"]
    assert len(plans) >= 2
    for p in plans:
        assert "estimated_tax" in p
        assert "estimated_total_monthly" in p
        assert "monthly_total_with_tax" in p
        assert "download_speed" in p
        assert "upload_speed" in p
        assert "modem_compatibility" in p
        assert "included_modem" in p
        assert p["contract_required"] is False
        price = float(p["monthly_price"])
        tax = float(p["estimated_tax"])
        total = float(p["monthly_total_with_tax"])
        assert round(price + tax, 2) == round(total, 2)

    # Addons must be present with contract_required: False
    addons = res["data"].get("available_add_ons") or res["data"].get("add_ons")
    assert addons is not None and len(addons) > 0
    for a in addons:
        assert a["contract_required"] is False
        assert "estimated_tax" in a
        assert "monthly_total_with_tax" in a


@pytest.mark.parametrize(
    "lang,expected_feature_prefix,expected_desc_prefix,expected_modem",
    [
        ("en-US", "Unlimited downloads", "Full access", "Wi-Fi 6 Gateway (included at $0/month)"),
        ("fr-CA", "Téléchargements illimités", "Accès complet", "Borne Wi-Fi 6 (incluse à 0 $/mois)"),
        ("es-US", "Descargas ilimitadas", "Acceso completo", "Módem Wi-Fi 6 (incluido a $0/mes)"),
    ],
)
def test_browse_plans_and_coverage_single_language_replies(
    monkeypatch, lang: str, expected_feature_prefix: str, expected_desc_prefix: str, expected_modem: str
) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="internet", language=lang)
    assert res["status"] == "ok"
    plans = res["data"]["shortlisted_plans"]
    assert len(plans) >= 2
    for p in plans:
        assert "features" in p
        assert "features_en" not in p
        assert "features_fr" not in p
        assert "features_es" not in p
    assert plans[0]["features"].startswith(expected_feature_prefix)
    assert plans[0]["included_modem"] == expected_modem

    addons = res["data"].get("available_add_ons") or res["data"].get("add_ons")
    assert addons is not None and len(addons) > 0
    for a in addons:
        assert "description" in a
        assert "description_en" not in a
        assert "description_fr" not in a
        assert "description_es" not in a
    sports_addon = next((a for a in addons if a["id"] == "ADDON-SPORTS"), None)
    if sports_addon:
        assert sports_addon["description"].startswith(expected_desc_prefix)


def test_browse_plans_and_coverage_tv_sports_addon_channels_and_combined_monthly(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="tv")
    assert res["status"] == "ok"
    data = res["data"]
    assert data["category"] == "tv"
    assert "included_channels" in data
    assert "TSN 1-5" in data["included_channels"]
    assert "ESPN" in data["included_channels"]
    assert data["combined_monthly_with_tv_starter"] == "43.00"
    assert data["combined_monthly_with_tv_starter_with_tax"] == "49.45"

    addons = data.get("available_add_ons") or data.get("add_ons")
    sports_addon = next((a for a in addons if a["id"] == "ADDON-SPORTS"), None)
    assert sports_addon is not None
    assert "TSN 1-5" in sports_addon["included_channels"]
    assert "Sportsnet" in sports_addon["included_channels"]
    assert "ESPN" in sports_addon["included_channels"]
    assert sports_addon["combined_monthly_with_tv_starter"] == "43.00"
    assert sports_addon["combined_monthly_with_tv_starter_with_tax"] == "49.45"
    assert "TSN 1-5" in sports_addon["description"]


def test_browse_plans_and_coverage_internet_wfh_technical_specifications(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    res = tool.browse_plans_and_coverage(category="internet", postal_code="H3Z 2Y7")
    assert res["status"] == "ok"
    data = res["data"]
    assert data["category"] == "internet"
    assert "latency" in data
    assert "sub-15ms" in data["latency"]
    assert "<2ms jitter" in data["latency"]
    assert "technical_specifications" in data
    assert "Pure fiber symmetrical bandwidth" in data["technical_specifications"]
    assert "99.9% uptime" in data["technical_specifications"]
    assert "sla_or_guarantee" in data
    assert "work_from_home_recommended_tier" in data
    assert "Fiber Internet 500 or Gigabit Fiber" in data["work_from_home_recommended_tier"]

    plans = data["shortlisted_plans"]
    assert len(plans) >= 2
    for p in plans:
        assert "latency" in p
        assert "sub-15ms" in p["latency"]
        assert "technical_specifications" in p
        assert "sla_or_guarantee" in p
        assert "99.9%" in p["sla_or_guarantee"]


def test_browse_plans_sets_browsed_category_budget_flags_and_post_auth_active_plans(monkeypatch) -> None:
    # Pre-auth browse sets browsed_plan_category + budget flags, omits current_active_plans
    session_pre = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session_pre, raising=False)
    res_pre = tool.browse_plans_and_coverage(category="mobility", max_budget=55, language="en-US")
    assert res_pre["status"] == "ok"
    assert session_pre.state["browsed_plan_category"] == "mobility"
    assert "current_active_plans" not in res_pre["data"]
    plans_pre = res_pre["data"]["shortlisted_plans"]
    assert any(p["within_budget_before_tax"] is True and p["within_budget_after_tax"] is True for p in plans_pre)
    assert any(p["within_budget_before_tax"] is True and p["within_budget_after_tax"] is False for p in plans_pre)

    # Fallback shortlist when max_budget is below lowest plan also sets budget flags
    res_low = tool.browse_plans_and_coverage(category="mobility", max_budget=10, language="en-US")
    assert res_low["status"] == "ok"
    assert all(p["within_budget_before_tax"] is False and p["within_budget_after_tax"] is False for p in res_low["data"]["shortlisted_plans"])

    # Post-auth browse attaches localized current_active_plans
    session_post = SimpleNamespace(state={"auth_status": "pass", "account_id": "A1001", "language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session_post, raising=False)
    res_post = tool.browse_plans_and_coverage(category="internet", language="fr-CA")
    assert res_post["status"] == "ok"
    assert session_post.state["browsed_plan_category"] == "internet"
    active = res_post["data"]["current_active_plans"]
    assert active["internet"]["plan_id"] == "NET-STARTER"
    assert active["internet"]["name"] == "Fibre Internet 100"
    assert active["internet"]["monthly_price"] == "45.00"
    assert active["mobility"]["plan_id"] == "MOB-STARTER"
    assert active["mobility"]["monthly_price"] == "35.00"





