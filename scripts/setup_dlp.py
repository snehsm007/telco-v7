#!/usr/bin/env python3
"""Set up Cloud DLP redaction of personal data in the app's conversation logs (`make setup-dlp`).

Cloud Data Loss Prevention (DLP), now part of Sensitive Data Protection, hides personal
data such as phone and card numbers in the conversation logs the platform keeps. This
script, for the agent named by --agent-name, in the app's own location:

  1. Creates or updates the inspect template `<agent>-pii-inspect`: personal-data info
     types plus a custom card-number pattern, because synthetic test card numbers fail
     the built-in check-digit (Luhn) test and would slip through. It never lists DATE,
     TIME or LOCATION, so appointment times and outage areas stay readable.
  2. Creates or updates the de-identify template `<agent>-pii-deidentify`, which replaces
     each finding with its info type name, for example [PHONE_NUMBER].
  3. Runs a de-identification test on a neutral sample sentence.
  4. With --apply-app-json, sets loggingSettings.redactionConfig (enableRedaction plus
     both template names) in <app-dir>/app.json. `make push` then deploys the setting.

The platform skips redaction inside evaluation sessions, so this changes no evaluation
score and no evaluation can check it. Check it in a `make chat` session or in the logs.
REST calls send the X-Goog-User-Project header (the target project), which Application
Default Credentials (ADC) user logins need.

Usage:
  python3 scripts/setup_dlp.py --project-id <p> --location <l> --agent-name <agent> \\
      [--app-dir cxas_app] [--apply-app-json] [--dry-run]
  python3 scripts/setup_dlp.py --self-test

--dry-run makes no cloud calls and changes no file; it prints what would happen.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.request

DLP_API = "https://dlp.googleapis.com/v2"
# A neutral sentence: a phone number and a 16-digit test card number must be replaced,
# the weekday and the time must survive.
SAMPLE_TEXT = "Call me at 415-555-0132. My card is 4000 1234 5678 9010. See you on Wednesday at 4pm."
MUST_REDACT = ("[PHONE_NUMBER]", "[CREDIT_CARD_NUMBER]")
MUST_KEEP = ("Wednesday", "4pm")

DEFAULT_INFO_TYPES = [
    "CREDIT_CARD_NUMBER",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "CANADA_SOCIAL_INSURANCE_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "CANADA_DRIVERS_LICENSE_NUMBER",
    "US_DRIVERS_LICENSE_NUMBER",
    "US_BANK_ROUTING_MICR",
    "IBAN_CODE",
    "PERSON_NAME",
]
# Never redact these: operational dates, times and outage areas must stay readable.
NEVER_REDACT = ("DATE", "TIME", "LOCATION")
# 16 digits in groups of 4 (spaces or dashes optional). It extends the built-in
# CREDIT_CARD_NUMBER detector, which skips numbers that fail the Luhn check.
CARD_PATTERN = r"\b(?:\d{4}[- ]?){3}\d{4}\b"


class DeidentifyCheckError(RuntimeError):
    """The de-identification test did not redact (or kept too much of) the sample."""


def template_ids(agent_name: str) -> tuple[str, str]:
    """(<agent>-pii-inspect, <agent>-pii-deidentify), limited to the characters DLP allows."""
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", str(agent_name or "")).strip("-_")
    if not base:
        raise ValueError("--agent-name must contain at least one letter or digit")
    base = base[: 100 - len("-pii-deidentify")]
    return f"{base}-pii-inspect", f"{base}-pii-deidentify"


def get_access_token() -> str:
    """An OAuth token from an explicit override, else ADC (google-auth, then gcloud ADC)."""
    for env_var in ("GOOGLE_OAUTH_ACCESS_TOKEN", "CXAS_OAUTH_TOKEN", "CLOUDSDK_AUTH_ACCESS_TOKEN"):
        val = os.environ.get(env_var)
        if val and val.strip():
            return val.strip()
    try:
        import google.auth
        import google.auth.transport.requests

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        if creds.token:
            return str(creds.token)
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    raise RuntimeError(
        "Could not get a Google Cloud access token from Application Default Credentials (ADC). "
        "Run: gcloud auth application-default login, then run this command again."
    )


def dlp_request(
    url: str,
    method: str = "GET",
    token: str = "",
    body: dict[str, Any] | None = None,
    timeout: int = 30,
    quota_project: str = "",
) -> tuple[int, dict[str, Any]]:
    """One authenticated call to the DLP REST API; returns (status, parsed body)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    user_project = quota_project
    if not user_project and "/projects/" in url:
        user_project = url.split("/projects/", 1)[1].split("/", 1)[0]
    if user_project:
        req.add_header("X-Goog-User-Project", user_project)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(text)
        except ValueError:
            return err.code, {"raw": text[:500]}


def _api_error(resp: dict[str, Any]) -> str:
    err = resp.get("error") if isinstance(resp, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(resp)[:300]


def inspect_template_payload(agent_name: str) -> dict[str, Any]:
    """InspectTemplate body: personal-data info types plus the card pattern; no DATE, TIME or LOCATION."""
    return {
        "displayName": f"{agent_name} PII inspect"[:256],
        "description": (
            "Finds personal data (cards, phone numbers, emails, government ids, names) in conversation "
            "logs. Dates, times and locations are left readable."
        ),
        "inspectConfig": {
            "minLikelihood": "POSSIBLE",
            "infoTypes": [{"name": it} for it in DEFAULT_INFO_TYPES],
            "customInfoTypes": [
                {
                    "infoType": {"name": "CREDIT_CARD_NUMBER"},
                    "regex": {"pattern": CARD_PATTERN},
                    "likelihood": "VERY_LIKELY",
                }
            ],
            "includeQuote": True,
        },
    }


def deidentify_template_payload(agent_name: str) -> dict[str, Any]:
    """DeidentifyTemplate body: replace each finding with its info type name, e.g. [PHONE_NUMBER]."""
    return {
        "displayName": f"{agent_name} PII de-identify"[:256],
        "description": "Replaces personal data with its info type name, for example [PHONE_NUMBER].",
        "deidentifyConfig": {
            "infoTypeTransformations": {
                "transformations": [{"primitiveTransformation": {"replaceWithInfoTypeConfig": {}}}]
            }
        },
    }


def _ensure_template(
    kind: str,
    project_id: str,
    location: str,
    template_id: str,
    payload: dict[str, Any],
    token: str,
    dry_run: bool,
) -> str:
    """Create the template, or update it in place when it already exists."""
    collection = {"InspectTemplate": "inspectTemplates", "DeidentifyTemplate": "deidentifyTemplates"}[kind]
    body_key = {"InspectTemplate": "inspectTemplate", "DeidentifyTemplate": "deidentifyTemplate"}[kind]
    config_key = {"InspectTemplate": "inspectConfig", "DeidentifyTemplate": "deidentifyConfig"}[kind]
    full_name = f"projects/{project_id}/locations/{location}/{collection}/{template_id}"
    base_url = f"{DLP_API}/projects/{project_id}/locations/{location}/{collection}"
    if dry_run:
        print(f"[DRY-RUN] would create or update {kind} {full_name}")
        return full_name
    status, _ = dlp_request(f"{base_url}/{template_id}", method="GET", token=token)
    if status == 200:
        status, resp = dlp_request(
            f"{base_url}/{template_id}?updateMask={config_key},displayName,description",
            method="PATCH",
            token=token,
            body={body_key: payload},
        )
        if status not in (200, 204):
            raise RuntimeError(f"Failed to update {kind} {full_name} (HTTP {status}): {_api_error(resp)}")
        print(f"Updated {kind}: {full_name}")
        return full_name
    status, resp = dlp_request(
        base_url,
        method="POST",
        token=token,
        body={"templateId": template_id, body_key: payload},
    )
    if status not in (200, 201):
        raise RuntimeError(f"Failed to create {kind} {full_name} (HTTP {status}): {_api_error(resp)}")
    print(f"Created {kind}: {full_name}")
    return full_name


def ensure_inspect_template(
    project_id: str, location: str, template_id: str, token: str, dry_run: bool = False, agent_name: str = ""
) -> str:
    """Create or update the inspect template (personal data, never DATE/TIME/LOCATION)."""
    payload = inspect_template_payload(agent_name or template_id)
    return _ensure_template("InspectTemplate", project_id, location, template_id, payload, token, dry_run)


def ensure_deidentify_template(
    project_id: str, location: str, template_id: str, token: str, dry_run: bool = False, agent_name: str = ""
) -> str:
    """Create or update the de-identify template (replace with the info type name)."""
    payload = deidentify_template_payload(agent_name or template_id)
    return _ensure_template("DeidentifyTemplate", project_id, location, template_id, payload, token, dry_run)


def verify_deidentification(
    project_id: str,
    location: str,
    inspect_name: str,
    deidentify_name: str,
    token: str,
    sample_text: str = SAMPLE_TEXT,
    dry_run: bool = False,
) -> str:
    """De-identify the sample with both templates; personal data must go, the day and time must stay."""
    if dry_run:
        print(f"[DRY-RUN] would de-identify the sample sentence: {sample_text!r}")
        return "Call me at [PHONE_NUMBER]. My card is [CREDIT_CARD_NUMBER]. See you on Wednesday at 4pm."
    url = f"{DLP_API}/projects/{project_id}/locations/{location}/content:deidentify"
    body = {
        "inspectTemplateName": inspect_name,
        "deidentifyTemplateName": deidentify_name,
        "item": {"value": sample_text},
    }
    status, resp = dlp_request(url, method="POST", token=token, body=body)
    if status != 200:
        raise RuntimeError(f"The de-identification test failed (HTTP {status}): {_api_error(resp)}")
    result = str((resp.get("item") or {}).get("value") or "")
    print(f"DLP test input:  {sample_text!r}")
    print(f"DLP test output: {result!r}")
    for tag in MUST_REDACT:
        if tag not in result:
            raise DeidentifyCheckError(f"expected {tag} in the de-identified sample, got {result!r}")
    for word in MUST_KEEP:
        if word not in result:
            raise DeidentifyCheckError(f"expected {word!r} to stay readable, got {result!r}")
    print("DLP test passed: personal data was replaced; the day and time stayed readable.")
    return result


def apply_to_app_json(app_json_path: Path, inspect_name: str, deidentify_name: str, dry_run: bool = False) -> None:
    """Set loggingSettings.redactionConfig in app.json, keeping every other setting."""
    if not app_json_path.exists():
        raise FileNotFoundError(f"{app_json_path} does not exist; run make kickstart first or pass --app-dir")
    redaction = {
        "enableRedaction": True,
        "inspectTemplate": inspect_name,
        "deidentifyTemplate": deidentify_name,
    }
    if dry_run:
        print(f"[DRY-RUN] would set loggingSettings.redactionConfig in {app_json_path} to {json.dumps(redaction)}")
        return
    data = json.loads(app_json_path.read_text(encoding="utf-8"))
    data.setdefault("loggingSettings", {})["redactionConfig"] = redaction
    app_json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Set loggingSettings.redactionConfig in {app_json_path}. Next: commit it, then make push")


def run(
    project_id: str,
    location: str,
    agent_name: str,
    app_dir: str = "cxas_app",
    apply_app_json: bool = False,
    dry_run: bool = False,
) -> int:
    inspect_id, deidentify_id = template_ids(agent_name)
    token = "" if dry_run else get_access_token()
    inspect_name = ensure_inspect_template(project_id, location, inspect_id, token, dry_run, agent_name)
    deidentify_name = ensure_deidentify_template(project_id, location, deidentify_id, token, dry_run, agent_name)
    verify_deidentification(project_id, location, inspect_name, deidentify_name, token, dry_run=dry_run)
    if apply_app_json:
        apply_to_app_json(Path(app_dir) / "app.json", inspect_name, deidentify_name, dry_run=dry_run)
    else:
        print("app.json not changed (pass --apply-app-json to turn redaction on in the app).")
    print(
        "Note: evaluation sessions skip redaction, so scores do not change and evals cannot check it; "
        "check a `make chat` session or the conversation logs."
    )
    return 0


# ----------------------------------------------------------------------------- self-test


def self_test() -> int:
    from unittest import mock

    insp = inspect_template_payload("demo-agent")
    names = [it["name"] for it in insp["inspectConfig"]["infoTypes"]]
    for required in ("PHONE_NUMBER", "CREDIT_CARD_NUMBER", "EMAIL_ADDRESS", "PERSON_NAME"):
        assert required in names, required
    assert not set(NEVER_REDACT) & set(names)
    custom = insp["inspectConfig"]["customInfoTypes"][0]
    assert custom["infoType"]["name"] == "CREDIT_CARD_NUMBER" and re.search(custom["regex"]["pattern"], SAMPLE_TEXT)
    trans = deidentify_template_payload("demo-agent")["deidentifyConfig"]["infoTypeTransformations"]["transformations"]
    assert trans == [{"primitiveTransformation": {"replaceWithInfoTypeConfig": {}}}]
    assert template_ids("My Agent!") == ("My-Agent-pii-inspect", "My-Agent-pii-deidentify")
    assert all(len(t) <= 100 for t in template_ids("x" * 300))

    with mock.patch(f"{__name__}.dlp_request") as req:
        req.side_effect = [(404, {}), (200, {"name": "n"})]
        name = ensure_inspect_template("p", "us", "a-pii-inspect", token="t")
        assert name == "projects/p/locations/us/inspectTemplates/a-pii-inspect"
        assert req.call_args_list[1].kwargs["method"] == "POST"
        assert req.call_args_list[1].kwargs["body"]["templateId"] == "a-pii-inspect"
    with mock.patch(f"{__name__}.dlp_request") as req:
        req.side_effect = [(200, {}), (200, {})]
        ensure_deidentify_template("p", "us", "a-pii-deidentify", token="t")
        assert req.call_args_list[1].kwargs["method"] == "PATCH" and "updateMask=" in req.call_args_list[1].args[0]
    with mock.patch(f"{__name__}.dlp_request", return_value=(200, {"item": {"value": "Call me at 415-555-0132."}})):
        try:
            verify_deidentification("p", "us", "i", "d", token="t")
            raise AssertionError("an unredacted sample must fail the check")
        except DeidentifyCheckError:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp) / "cxas_app"
        app_dir.mkdir()
        app_json = app_dir / "app.json"
        original = {"name": "x", "loggingSettings": {"evaluationAudioRecordingConfig": {"gcsBucket": "gs://b"}}}
        app_json.write_text(json.dumps(original), encoding="utf-8")
        assert main(["--project-id", "p", "--location", "us", "--agent-name", "a", "--app-dir", str(app_dir),
                     "--apply-app-json", "--dry-run"]) == 0
        assert json.loads(app_json.read_text(encoding="utf-8")) == original  # dry run: no change
        apply_to_app_json(app_json, "insp", "deid")
        saved = json.loads(app_json.read_text(encoding="utf-8"))
        assert saved["loggingSettings"]["redactionConfig"] == {
            "enableRedaction": True,
            "inspectTemplate": "insp",
            "deidentifyTemplate": "deid",
        }
        assert saved["loggingSettings"]["evaluationAudioRecordingConfig"] == {"gcsBucket": "gs://b"}
    print("OK: scripts/setup_dlp.py self-test passed (6 checks)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-id", default="", help="Google Cloud project of the app")
    parser.add_argument("--location", default="", help="Location of the app (the templates go there too), e.g. us")
    parser.add_argument("--agent-name", default="", help="Agent name; templates are <agent>-pii-inspect/-deidentify")
    parser.add_argument("--app-dir", default="cxas_app", help="Folder with app.json (default: cxas_app)")
    parser.add_argument("--apply-app-json", action="store_true", help="Set loggingSettings.redactionConfig in app.json")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen; no cloud calls, no file changes")
    parser.add_argument("--self-test", action="store_true", help="Run the offline self-test")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    missing = [flag for flag, value in (("--project-id", args.project_id), ("--location", args.location),
                                        ("--agent-name", args.agent_name)) if not str(value).strip()]
    if missing:
        parser.error(f"{', '.join(missing)} required (make setup-dlp ENV=<env> passes them from environments/<env>.mk)")
    if "<" in args.project_id or args.project_id == "my-gcp-project":
        parser.error("--project-id is still a placeholder; set PROJECT_ID in environments/<env>.mk")
    try:
        return run(args.project_id, args.location, args.agent_name, args.app_dir, args.apply_app_json, args.dry_run)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
