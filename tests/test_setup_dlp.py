"""Unit tests for scripts/setup_dlp.py (Cloud DLP templates and app.json redaction wiring).

Ported from the telco-rebuild build, where the same flow ran against the real API.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.setup_dlp import (
    DEFAULT_INFO_TYPES,
    DeidentifyCheckError,
    apply_to_app_json,
    deidentify_template_payload,
    ensure_deidentify_template,
    ensure_inspect_template,
    get_access_token,
    inspect_template_payload,
    main,
    template_ids,
    verify_deidentification,
)


def test_inspect_and_deidentify_payloads() -> None:
    insp = inspect_template_payload("demo-agent")
    assert insp["inspectConfig"]["minLikelihood"] == "POSSIBLE"
    assert insp["inspectConfig"]["includeQuote"] is True
    names = {it["name"] for it in insp["inspectConfig"]["infoTypes"]}
    assert set(DEFAULT_INFO_TYPES) == names
    assert {"CREDIT_CARD_NUMBER", "PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON_NAME"} <= names
    assert not {"DATE", "TIME", "LOCATION"} & names
    custom = insp["inspectConfig"]["customInfoTypes"]
    assert custom[0]["infoType"]["name"] == "CREDIT_CARD_NUMBER" and custom[0]["regex"]["pattern"]
    assert "telco" not in json.dumps(insp).lower()

    deid = deidentify_template_payload("demo-agent")
    trans = deid["deidentifyConfig"]["infoTypeTransformations"]["transformations"]
    assert len(trans) == 1
    assert "replaceWithInfoTypeConfig" in trans[0]["primitiveTransformation"]


def test_template_ids_follow_the_agent_name() -> None:
    assert template_ids("billing-agent") == ("billing-agent-pii-inspect", "billing-agent-pii-deidentify")
    assert template_ids("my agent/v2") == ("my-agent-v2-pii-inspect", "my-agent-v2-pii-deidentify")
    with pytest.raises(ValueError):
        template_ids("!!!")


def test_ensure_inspect_template_create() -> None:
    with patch("scripts.setup_dlp.dlp_request") as mock_req:
        mock_req.side_effect = [
            (404, {"error": "not found"}),
            (200, {"name": "projects/p/locations/us/inspectTemplates/a-pii-inspect"}),
        ]
        name = ensure_inspect_template("p", "us", "a-pii-inspect", token="fake-token")
        assert name == "projects/p/locations/us/inspectTemplates/a-pii-inspect"
        assert mock_req.call_count == 2
        post_call = mock_req.call_args_list[1]
        assert post_call.kwargs["method"] == "POST"
        assert post_call.kwargs["body"]["templateId"] == "a-pii-inspect"


def test_ensure_inspect_template_update() -> None:
    with patch("scripts.setup_dlp.dlp_request") as mock_req:
        mock_req.side_effect = [(200, {"name": "x"}), (200, {"name": "x"})]
        name = ensure_inspect_template("p", "us", "a-pii-inspect", token="fake-token")
        assert name == "projects/p/locations/us/inspectTemplates/a-pii-inspect"
        patch_call = mock_req.call_args_list[1]
        assert patch_call.kwargs["method"] == "PATCH"
        assert "updateMask=" in patch_call.args[0]


def test_ensure_inspect_template_failure() -> None:
    with patch("scripts.setup_dlp.dlp_request") as mock_req:
        mock_req.side_effect = [(404, {}), (403, {"error": {"message": "Permission denied"}})]
        with pytest.raises(RuntimeError, match="Failed to create InspectTemplate"):
            ensure_inspect_template("p", "us", "a-pii-inspect", token="fake-token")


def test_ensure_deidentify_template_create_and_update() -> None:
    with patch("scripts.setup_dlp.dlp_request") as mock_req:
        mock_req.side_effect = [(404, {}), (200, {})]
        name = ensure_deidentify_template("p", "us", "a-pii-deidentify", token="fake-token")
        assert name == "projects/p/locations/us/deidentifyTemplates/a-pii-deidentify"
    with patch("scripts.setup_dlp.dlp_request") as mock_req:
        mock_req.side_effect = [(200, {}), (200, {})]
        name = ensure_deidentify_template("p", "us", "a-pii-deidentify", token="fake-token")
        assert name == "projects/p/locations/us/deidentifyTemplates/a-pii-deidentify"


def test_verify_deidentification() -> None:
    redacted = "Call me at [PHONE_NUMBER]. My card is [CREDIT_CARD_NUMBER]. See you on Wednesday at 4pm."
    with patch("scripts.setup_dlp.dlp_request", return_value=(200, {"item": {"value": redacted}})) as mock_req:
        assert verify_deidentification("p", "us", "insp", "deid", token="tok") == redacted
        body = mock_req.call_args.kwargs["body"]
        assert body["inspectTemplateName"] == "insp" and body["deidentifyTemplateName"] == "deid"


def test_verify_deidentification_fails_on_unredacted_or_overredacted_data() -> None:
    with patch("scripts.setup_dlp.dlp_request", return_value=(200, {"item": {"value": "Call me at 415-555-0132."}})):
        with pytest.raises(DeidentifyCheckError, match=r"\[PHONE_NUMBER\]"):
            verify_deidentification("p", "us", "insp", "deid", token="tok")
    over = "Call me at [PHONE_NUMBER]. My card is [CREDIT_CARD_NUMBER]. See you on [DATE] at [TIME]."
    with patch("scripts.setup_dlp.dlp_request", return_value=(200, {"item": {"value": over}})):
        with pytest.raises(DeidentifyCheckError, match="Wednesday"):
            verify_deidentification("p", "us", "insp", "deid", token="tok")


def test_apply_to_app_json(tmp_path: Path) -> None:
    app_file = tmp_path / "app.json"
    app_file.write_text(
        json.dumps({"displayName": "demo", "loggingSettings": {"evaluationAudioRecordingConfig": {"gcsBucket": "gs://b"}}}),
        encoding="utf-8",
    )
    apply_to_app_json(app_file, "projects/p/locations/us/inspectTemplates/i", "projects/p/locations/us/deidentifyTemplates/d")
    updated = json.loads(app_file.read_text(encoding="utf-8"))
    rc = updated["loggingSettings"]["redactionConfig"]
    assert rc == {
        "enableRedaction": True,
        "inspectTemplate": "projects/p/locations/us/inspectTemplates/i",
        "deidentifyTemplate": "projects/p/locations/us/deidentifyTemplates/d",
    }
    assert updated["loggingSettings"]["evaluationAudioRecordingConfig"]["gcsBucket"] == "gs://b"
    with pytest.raises(FileNotFoundError):
        apply_to_app_json(tmp_path / "missing.json", "i", "d")


def test_get_access_token_env_override(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_ACCESS_TOKEN", "custom-token-xyz")
    assert get_access_token() == "custom-token-xyz"


def test_main_dry_run_changes_nothing(tmp_path: Path) -> None:
    app_dir = tmp_path / "cxas_app"
    app_dir.mkdir()
    (app_dir / "app.json").write_text(json.dumps({"loggingSettings": {}}), encoding="utf-8")
    argv = ["--project-id", "demo-project", "--location", "us", "--agent-name", "demo-agent",
            "--app-dir", str(app_dir), "--dry-run", "--apply-app-json"]
    assert main(argv) == 0
    assert json.loads((app_dir / "app.json").read_text(encoding="utf-8")) == {"loggingSettings": {}}


def test_main_applies_templates_to_app_json(tmp_path: Path, monkeypatch) -> None:
    app_dir = tmp_path / "cxas_app"
    app_dir.mkdir()
    (app_dir / "app.json").write_text(json.dumps({"loggingSettings": {}}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_OAUTH_ACCESS_TOKEN", "tok")
    redacted = "Call me at [PHONE_NUMBER]. My card is [CREDIT_CARD_NUMBER]. See you on Wednesday at 4pm."
    responses = [(404, {}), (200, {}), (404, {}), (200, {}), (200, {"item": {"value": redacted}})]
    with patch("scripts.setup_dlp.dlp_request", side_effect=responses) as mock_req:
        assert main(["--project-id", "demo-project", "--location", "us", "--agent-name", "demo-agent",
                     "--app-dir", str(app_dir), "--apply-app-json"]) == 0
    urls = [c.args[0] for c in mock_req.call_args_list]
    assert all("/projects/demo-project/locations/us/" in u for u in urls)
    rc = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))["loggingSettings"]["redactionConfig"]
    assert rc["inspectTemplate"].endswith("/inspectTemplates/demo-agent-pii-inspect")
    assert rc["deidentifyTemplate"].endswith("/deidentifyTemplates/demo-agent-pii-deidentify")


def test_main_requires_the_target(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["--location", "us"])
    assert "--project-id" in capsys.readouterr().err


def test_self_test() -> None:
    assert main(["--self-test"]) == 0
