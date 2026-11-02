"""Unit tests for scripts/preflight.py (offline: every Google call is faked)."""

from __future__ import annotations

from typing import Any

import pytest

from scripts import preflight


def _http(responses: list[tuple[int, Any]], seen: list[dict[str, Any]]):
    queue = list(responses)

    def http(method: str, url: str, headers: dict[str, str], body: Any):
        if url.startswith(preflight.TOKENINFO_URL):
            return 200, {"email": "dev@example.com"}
        seen.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        return queue.pop(0)

    return http


def _mint(quota: str = "demo-project"):
    return lambda: preflight.Adc("tok", quota, "google-auth AuthorizedUser")


def test_all_permissions_granted(capsys) -> None:
    seen: list[dict[str, Any]] = []
    granted = {"permissions": list(preflight.REQUIRED_PERMISSIONS)}
    code = preflight.preflight("demo-project", mint=_mint(), http=_http([(200, granted)], seen), gcert=lambda: "")
    assert code == 0
    assert seen[0]["url"].endswith("/v1/projects/demo-project:testIamPermissions")
    assert seen[0]["headers"]["X-Goog-User-Project"] == "demo-project"
    out = capsys.readouterr().out
    assert "ADC login: dev@example.com" in out and out.strip().endswith("preflight: OK")


def test_missing_permissions_fail_with_names_and_next_step(capsys) -> None:
    partial = {"permissions": ["ces.apps.get"]}
    code = preflight.preflight("demo-project", mint=_mint(), http=_http([(200, partial)], []), gcert=lambda: "")
    assert code == 1
    out = capsys.readouterr().out
    assert "ces.apps.update, ces.apps.runEvaluation, ces.evaluations.create" in out
    assert "roles/ces.admin" in out


def test_domain_scoped_project_and_app_project() -> None:
    seen: list[dict[str, Any]] = []
    granted = {"permissions": list(preflight.REQUIRED_PERMISSIONS)}
    app = "projects/google.com:demo-sandbox/locations/us/apps/123"
    code = preflight.preflight("my-gcp-project", app=app, mint=_mint("google.com:demo-sandbox"),
                               http=_http([(200, granted)], seen), gcert=lambda: "")
    assert code == 0
    assert "/projects/google.com:demo-sandbox:testIamPermissions" in seen[0]["url"]


def test_expired_login_and_placeholder_project(capsys) -> None:
    def expired() -> preflight.Adc:
        raise preflight.PreflightError(f"login expired. Run: {preflight.LOGIN_FIX}")

    assert preflight.preflight("demo-project", mint=expired, http=_http([], []), gcert=lambda: "") == 1
    assert preflight.LOGIN_FIX in capsys.readouterr().out
    assert preflight.preflight("<gcp-project>", mint=_mint(), http=_http([], []), gcert=lambda: "") == 1
    assert "PROJECT_ID is not set" in capsys.readouterr().out


def test_disabled_resource_manager_api_says_how_to_enable_it() -> None:
    disabled = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "API has not been used",
                          "details": [{"reason": "SERVICE_DISABLED"}]}}
    with pytest.raises(preflight.PreflightError, match="gcloud services enable cloudresourcemanager"):
        preflight.missing_permissions("tok", "demo-project", http=_http([(403, disabled)], []))


def test_helpers() -> None:
    assert preflight.project_from_app("projects/p-1/locations/us/apps/a") == "p-1"
    assert preflight.project_from_app("projects/p-1/locations/us/apps/") == ""
    assert preflight.is_placeholder_project("my-gcp-project")
    assert not preflight.is_placeholder_project("google.com:demo")


def test_self_test() -> None:
    assert preflight.main(["--self-test"]) == 0
