#!/usr/bin/env python3
"""Check the Google Cloud login and permissions before a cloud command (`make preflight`).

`make push`, `push-evals`, `setup-dlp`, `smoke-impact` and every `bench-*` target run
this first (set SKIP_PREFLIGHT=1 to skip it). In a few seconds it catches the problems
that otherwise stop an unattended evaluation run halfway:

  1. Gets an access token from Application Default Credentials (ADC), the login that
     scripts use (`gcloud auth application-default login`). Plain
     `gcloud auth print-access-token` user tokens are not enough: certificate-based
     access on google.com projects rejects them (401 ACCESS_TOKEN_TYPE_UNSUPPORTED).
  2. Prints whose login it is and the ADC quota project, and warns when the quota
     project is not the target project.
  3. Asks Cloud Resource Manager (testIamPermissions) whether this login has
     ces.apps.get, ces.apps.update, ces.apps.runEvaluation and ces.evaluations.create
     on the project, and fails with the list of missing permissions.
  4. Warns (never fails) when `gcertstatus` says the corp certificate expired.

ADC renews its own short-lived access tokens, so the minutes left on one token do not
matter. What expires is the login itself; step 1 catches that.

Usage:
  python3 scripts/preflight.py --project-id <project> [--app projects/<p>/locations/<l>/apps/<id>]
  python3 scripts/preflight.py --self-test

Exit codes: 0 OK, 1 a check failed (the message says what to run next).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import shutil
import subprocess
import sys
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

REQUIRED_PERMISSIONS = (
    "ces.apps.get",
    "ces.apps.update",
    "ces.apps.runEvaluation",
    "ces.evaluations.create",
)
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
TEST_IAM_URL = "https://cloudresourcemanager.googleapis.com/v1/projects/{project}:testIamPermissions"
LOGIN_FIX = "gcloud auth application-default login"
ROLE_HINT = (
    "Ask a project owner for roles/ces.admin, or for roles/ces.appEditor plus roles/ces.evalsEditor"
)

# http(method, url, headers, body) -> (status, parsed JSON body)
Http = Callable[[str, str, dict[str, str], Any], tuple[int, Any]]


class PreflightError(RuntimeError):
    """A check failed; the message says what to run next."""


@dataclass
class Adc:
    token: str
    quota_project: str
    source: str


def http_json(method: str, url: str, headers: dict[str, str], body: Any = None, timeout: int = 20) -> tuple[int, Any]:
    """One HTTPS call; returns (status, parsed JSON or {"raw": text}). Status 0 = no connection."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(text)
        except ValueError:
            return err.code, {"raw": text[:500]}
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return 0, {"raw": str(err)}


def mint_adc_token(run: Callable[..., Any] = subprocess.run) -> Adc:
    """An ADC access token: google-auth first (works for user logins and CI federation),
    else `gcloud auth application-default print-access-token`."""
    try:
        import google.auth
        import google.auth.exceptions
        import google.auth.transport.requests
    except ImportError:
        google = None  # type: ignore[assignment]
    if google is not None:
        try:
            creds, _ = google.auth.default(scopes=SCOPES)
            creds.refresh(google.auth.transport.requests.Request())
        except google.auth.exceptions.DefaultCredentialsError as exc:
            raise PreflightError(
                f"No Application Default Credentials (ADC) were found ({str(exc)[:160]}). Run: {LOGIN_FIX}"
            ) from exc
        except Exception as exc:  # RefreshError, TransportError, ...
            raise PreflightError(
                "Your Google Cloud login for scripts (Application Default Credentials, ADC) has expired "
                f"or was revoked ({str(exc)[:200]}). Run: {LOGIN_FIX} (and `gcloud auth login` if gcloud "
                "asks for it), then run this command again."
            ) from exc
        kind = type(creds).__name__
        source = f"google-auth {creds.__class__.__module__.split('.')[-2] if '.' in creds.__class__.__module__ else ''} {kind}".replace("  ", " ")
        return Adc(str(creds.token or ""), str(getattr(creds, "quota_project_id", "") or ""), source.strip())
    if shutil.which("gcloud") is None:
        raise PreflightError("Neither the google-auth library nor the gcloud CLI is installed. Run: make install")
    proc = run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token:
        raise PreflightError(
            "Your Google Cloud login for scripts (Application Default Credentials, ADC) is missing or "
            f"expired ({(proc.stderr or '').strip()[:200]}). Run: {LOGIN_FIX}, then run this command again."
        )
    quota = ""
    q = run(
        ["gcloud", "config", "get-value", "billing/quota_project"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if q.returncode == 0:
        quota = (q.stdout or "").strip()
    return Adc(token, quota, "gcloud application-default")


def token_identity(token: str, http: Http = http_json) -> str:
    """Whose token this is (tokeninfo email, else the OAuth client id), or "unknown"."""
    url = f"{TOKENINFO_URL}?{urllib.parse.urlencode({'access_token': token})}"
    status, body = http("GET", url, {}, None)
    if status != 200 or not isinstance(body, dict):
        return "unknown (tokeninfo did not answer)"
    return str(body.get("email") or body.get("sub") or body.get("azp") or "unknown")


def _error_text(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("status") or err)
        return str(body.get("raw") or body)[:300]
    return str(body)[:300]


def _error_reasons(body: Any) -> set[str]:
    out: set[str] = set()
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        for detail in err.get("details") or []:
            if isinstance(detail, dict) and detail.get("reason"):
                out.add(str(detail["reason"]))
        if err.get("status"):
            out.add(str(err["status"]))
    return out


def missing_permissions(
    token: str,
    project: str,
    permissions: tuple[str, ...] = REQUIRED_PERMISSIONS,
    http: Http = http_json,
    quota_project: str = "",
) -> tuple[list[str], list[str]]:
    """(missing permissions, notes) from Cloud Resource Manager testIamPermissions."""
    url = TEST_IAM_URL.format(project=project)
    wanted = list(permissions)
    notes: list[str] = []
    user_project = quota_project or project
    for _ in range(4):
        headers = {"Authorization": f"Bearer {token}"}
        if user_project:
            headers["X-Goog-User-Project"] = user_project
        status, body = http("POST", url, headers, {"permissions": wanted})
        if status == 200:
            granted = set((body or {}).get("permissions") or []) if isinstance(body, dict) else set()
            return [p for p in wanted if p not in granted], notes
        text = _error_text(body)
        reasons = _error_reasons(body)
        if status == 400:
            bad = re.findall(r"Permission '?([\w.]+)'? is not valid", text)
            if bad and set(bad) & set(wanted):
                notes.append(f"skipped permissions this project cannot check: {', '.join(sorted(set(bad)))}")
                wanted = [p for p in wanted if p not in bad]
                if wanted:
                    continue
                return [], notes
        if status == 403 and user_project and (
            "USER_PROJECT_DENIED" in reasons or "serviceusage.services.use" in text
        ):
            notes.append(
                f"could not bill the check to {user_project} (no serviceusage.services.use there); retried without it"
            )
            user_project = ""
            continue
        if status == 401:
            raise PreflightError(
                f"Google Cloud rejected the ADC token (401: {text}). Run: {LOGIN_FIX}, then run this command again."
            )
        if status == 403 and ("SERVICE_DISABLED" in reasons or "has not been used" in text):
            raise PreflightError(
                f"The Cloud Resource Manager API is turned off for the project that pays for this check ({text}). "
                f"Run: gcloud services enable cloudresourcemanager.googleapis.com --project {user_project or project}, "
                "or skip the check once with SKIP_PREFLIGHT=1."
            )
        if status in (403, 404):
            raise PreflightError(
                f"Project {project} does not exist or your login cannot see it ({status}: {text}). "
                "Check PROJECT_ID in environments/<env>.mk, or ask the project owner for access."
            )
        raise PreflightError(
            f"Could not check permissions on {project} (HTTP {status}: {text}). Check your network, "
            "or skip the check once with SKIP_PREFLIGHT=1."
        )
    raise PreflightError(f"Could not check permissions on {project}: too many retries.")


def gcert_warning(run: Callable[..., Any] = subprocess.run, which: Callable[[str], Any] = shutil.which) -> str:
    """A warning when gcertstatus reports a missing or expired corp certificate, else ""."""
    if which("gcertstatus") is None:
        return ""
    try:
        proc = run(["gcertstatus", "-quiet"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return "gcert is missing or expired; run gcert if a step needs corp resources (Cloud itself does not)."
    return ""


def project_from_app(app: str) -> str:
    m = re.match(r"^projects/([^/]+)/locations/[^/]+/apps/[^/]+$", str(app or "").strip().rstrip("/"))
    return m.group(1) if m else ""


def is_placeholder_project(project: str) -> bool:
    text = str(project or "").strip()
    return not text or text in ("my-gcp-project", "<gcp-project>") or ("<" in text and ">" in text)


def preflight(
    project: str,
    app: str = "",
    mint: Callable[[], Adc] = mint_adc_token,
    http: Http = http_json,
    gcert: Callable[[], str] = gcert_warning,
    out: Callable[[str], None] = print,
) -> int:
    """Run every check and print a short report; 0 OK, 1 failed."""
    from_app = project_from_app(app)
    if from_app and from_app != project:
        out(f"preflight: using project {from_app} from APP (PROJECT_ID says {project or 'nothing'})")
        project = from_app
    if is_placeholder_project(project):
        out(
            "preflight: FAILED: PROJECT_ID is not set. Create environments/<env>.mk from "
            "environments/example.mk (PROJECT_ID, LOCATION, APP_ID) and pass ENV=<env>, or pass PROJECT_ID=<project>."
        )
        return 1
    out(f"preflight: project {project}")
    try:
        adc = mint()
        if not adc.token:
            raise PreflightError(f"ADC returned an empty token. Run: {LOGIN_FIX}")
        identity = token_identity(adc.token, http)
        out(f"  ADC login: {identity} ({adc.source})")
        if "ComputeEngine" in adc.source or identity.endswith("-compute@developer.gserviceaccount.com"):
            out(
                "  WARNING: ADC fell back to this machine's service account, so no ADC login file was found. "
                f"Run: {LOGIN_FIX}"
            )
        if adc.quota_project:
            out(f"  ADC quota project: {adc.quota_project}")
            if adc.quota_project != project:
                out(
                    f"  WARNING: the ADC quota project is {adc.quota_project}, not {project}; API quota is charged "
                    f"there. To change it: gcloud auth application-default set-quota-project {project}"
                )
        else:
            out(f"  ADC quota project: not set (scripts send X-Goog-User-Project: {project})")
        missing, notes = missing_permissions(adc.token, project, http=http)
        for note in notes:
            out(f"  note: {note}")
        if missing:
            raise PreflightError(
                f"Your login ({identity}) is missing these permissions on project {project}: "
                f"{', '.join(missing)}. {ROLE_HINT}, then run this command again."
            )
        out(f"  Permissions: {', '.join(REQUIRED_PERMISSIONS)}: all granted")
    except PreflightError as exc:
        out(f"preflight: FAILED: {exc}")
        return 1
    warning = gcert()
    if warning:
        out(f"  WARNING: {warning}")
    out("preflight: OK")
    return 0


# ----------------------------------------------------------------------------- self-test


def _self_test() -> int:
    lines: list[str] = []

    def out(text: str) -> None:
        lines.append(text)

    def make_http(responses: list[tuple[int, Any]], seen: list[tuple[str, dict[str, str], Any]]) -> Http:
        queue = list(responses)

        def http(method: str, url: str, headers: dict[str, str], body: Any) -> tuple[int, Any]:
            if url.startswith(TOKENINFO_URL):
                return 200, {"email": "dev@example.com", "expires_in": "3599"}
            seen.append((url, dict(headers), body))
            return queue.pop(0)

        return http

    def mint_ok(quota: str = "proj-a") -> Callable[[], Adc]:
        return lambda: Adc("tok", quota, "google-auth AuthorizedUser")

    granted = {"permissions": list(REQUIRED_PERMISSIONS)}
    no_gcert = lambda: ""  # noqa: E731
    checks = 0

    # 1. Everything granted.
    seen: list[tuple[str, dict[str, str], Any]] = []
    assert preflight("proj-a", mint=mint_ok(), http=make_http([(200, granted)], seen), gcert=no_gcert, out=out) == 0
    assert seen[0][1]["X-Goog-User-Project"] == "proj-a" and seen[0][1]["Authorization"] == "Bearer tok"
    assert seen[0][2] == {"permissions": list(REQUIRED_PERMISSIONS)}
    assert lines[-1] == "preflight: OK"
    checks += 1

    # 2. Missing permissions fail with their names.
    lines.clear()
    partial = {"permissions": ["ces.apps.get", "ces.apps.update"]}
    assert preflight("proj-a", mint=mint_ok(), http=make_http([(200, partial)], []), gcert=no_gcert, out=out) == 1
    assert "ces.apps.runEvaluation, ces.evaluations.create" in lines[-1] and "roles/ces.admin" in lines[-1]
    checks += 1

    # 3. Quota project mismatch warns; USER_PROJECT_DENIED retries without the header.
    lines.clear()
    seen = []
    denied = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "no serviceusage.services.use",
                        "details": [{"reason": "USER_PROJECT_DENIED"}]}}
    http = make_http([(403, denied), (200, granted)], seen)
    assert preflight("proj-b", mint=mint_ok("proj-a"), http=http, gcert=no_gcert, out=out) == 0
    assert any("quota project is proj-a, not proj-b" in line for line in lines)
    assert "X-Goog-User-Project" in seen[0][1] and "X-Goog-User-Project" not in seen[1][1]
    checks += 1

    # 4. A permission the project cannot check is dropped, the rest still checked.
    lines.clear()
    invalid = {"error": {"code": 400, "message": "Permission ces.evaluations.create is not valid for this resource."}}
    assert preflight("proj-a", mint=mint_ok(), http=make_http([(400, invalid), (200, granted)], []),
                     gcert=no_gcert, out=out) == 0
    assert any("skipped permissions" in line for line in lines)
    checks += 1

    # 5. Expired login, rejected token, unknown project, placeholder project.
    def mint_expired() -> Adc:
        raise PreflightError(f"login expired. Run: {LOGIN_FIX}")

    lines.clear()
    assert preflight("proj-a", mint=mint_expired, http=make_http([], []), gcert=no_gcert, out=out) == 1
    assert LOGIN_FIX in lines[-1]
    lines.clear()
    assert preflight("proj-a", mint=mint_ok(), http=make_http([(401, {"error": {"message": "bad"}})], []),
                     gcert=no_gcert, out=out) == 1
    assert LOGIN_FIX in lines[-1]
    lines.clear()
    assert preflight("nope", mint=mint_ok(), http=make_http([(403, {"error": {"message": "denied"}})], []),
                     gcert=no_gcert, out=out) == 1
    assert "does not exist or your login cannot see it" in lines[-1]
    lines.clear()
    assert preflight("my-gcp-project", mint=mint_ok(), http=make_http([], []), gcert=no_gcert, out=out) == 1
    assert "PROJECT_ID is not set" in lines[-1]
    checks += 1

    # 6. APP decides the project; gcert expiry only warns.
    lines.clear()
    seen = []
    assert preflight("my-gcp-project", app="projects/proj-c/locations/us/apps/123", mint=mint_ok("proj-c"),
                     http=make_http([(200, granted)], seen), gcert=lambda: "gcert is missing or expired", out=out) == 0
    assert "proj-c:testIamPermissions" in seen[0][0]
    assert any("gcert is missing or expired" in line for line in lines) and lines[-1] == "preflight: OK"

    class _Proc:
        def __init__(self, code: int) -> None:
            self.returncode, self.stdout, self.stderr = code, "", ""

    assert gcert_warning(run=lambda *a, **k: _Proc(1), which=lambda _: "/usr/bin/gcertstatus")
    assert gcert_warning(run=lambda *a, **k: _Proc(0), which=lambda _: "/usr/bin/gcertstatus") == ""
    assert gcert_warning(which=lambda _: None) == ""
    checks += 1

    print(f"OK: {checks}/{checks} preflight self-test cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-id", default="", help="Target Google Cloud project")
    parser.add_argument("--app", default="", help="App resource; its project wins over --project-id")
    parser.add_argument("--self-test", action="store_true", help="Run the offline self-test")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    return preflight(args.project_id, app=args.app)


if __name__ == "__main__":
    sys.exit(main())
