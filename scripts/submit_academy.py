#!/usr/bin/env python3
"""Automated Agent Submissions for CXAS Agent Academy (fde-bootcamp-chi).

Submits a deployed CES agent to the Agent Academy platform for a specific
track (such as Greenfield) and handles authentication, track matching,
score resolution from history/bench/full-*.json, and certification reporting.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BASE_URL = "https://cxas-labs-api-6mnjcet6bq-uc.a.run.app"
DEFAULT_EVENT_ID = "fde-bootcamp-chi"
DEFAULT_USER_ID = "snehsm@google.com"
DEFAULT_TRACK = "greenfield"
DEFAULT_AGENT_NAME = "snehsm-FDEBootcamp-CHI-greenfield"


def resolve_agent_name(
    explicit_name: Optional[str] = None,
    staging_mk_path: Optional[Path] = None,
) -> str:
  """Resolves the agent display name from CLI, env, staging.mk, or default."""
  if explicit_name and explicit_name.strip():
    return explicit_name.strip()

  env_name = os.getenv("AGENT_NAME")
  if env_name and env_name.strip():
    return env_name.strip()

  mk_path = staging_mk_path or (REPO_ROOT / "environments" / "staging.mk")
  if mk_path.is_file():
    try:
      content = mk_path.read_text(encoding="utf-8")
      m = re.search(
          r"^[ \t]*AGENT_NAME[ \t]*[:?]?=[ \t]*([^\s#\n\r]+)",
          content,
          re.MULTILINE,
      )
      if m:
        val = m.group(1).strip()
        if val and not val.startswith("<"):
          return val
    except OSError:
      pass

  return DEFAULT_AGENT_NAME


def resolve_agent_app_id(
    explicit_app: Optional[str] = None,
    staging_mk_path: Optional[Path] = None,
    last_push_path: Optional[Path] = None,
    is_dry_run: bool = False,
) -> str:
  """Resolves the deployed agent app resource path."""
  if explicit_app and explicit_app.strip():
    app = explicit_app.strip()
    if not app.startswith("projects/") and not "/" in app:
      return f"projects/fde-bootcamp/locations/us/apps/{app}"
    return app

  for env_var in ("APP_ID", "CES_APP_NAME", "APP"):
    val = os.getenv(env_var)
    if val and val.strip() and not val.strip().startswith("<"):
      app = val.strip()
      if not app.startswith("projects/") and not "/" in app:
        return f"projects/fde-bootcamp/locations/us/apps/{app}"
      return app

  push_file = last_push_path or (REPO_ROOT / "history" / "last_push.json")
  if push_file.is_file():
    try:
      data = json.loads(push_file.read_text(encoding="utf-8"))
      app = data.get("app")
      if app and str(app).strip():
        return str(app).strip()
    except (OSError, json.JSONDecodeError):
      pass

  mk_path = staging_mk_path or (REPO_ROOT / "environments" / "staging.mk")
  if mk_path.is_file():
    try:
      content = mk_path.read_text(encoding="utf-8")
      m = re.search(
          r"^[ \t]*APP_ID[ \t]*[:?]?=[ \t]*([^\s#\n\r]+)",
          content,
          re.MULTILINE,
      )
      if m:
        val = m.group(1).strip()
        if val and not val.startswith("<"):
          if not val.startswith("projects/") and not "/" in val:
            return f"projects/fde-bootcamp/locations/us/apps/{val}"
          return val
    except OSError:
      pass

  if is_dry_run:
    return "projects/fde-bootcamp/locations/us/apps/<pending-cloud-push>"

  raise ValueError(
      "CES Agent App ID could not be resolved. Please specify --app or set"
      " APP_ID in environments/staging.mk or via environment variable."
  )


def find_latest_bench_record(bench_dir: Path) -> Optional[Path]:
  """Finds the latest full-*.json benchmark record by mtime."""
  if not bench_dir.is_dir():
    return None
  candidates = sorted(
      list(bench_dir.glob("full-*.json")) + list(bench_dir.glob("full_*.json")),
      key=lambda p: p.stat().st_mtime,
      reverse=True,
  )
  return candidates[0] if candidates else None


def parse_bench_scores(record_path: Path) -> Tuple[int, int]:
  """Parses real evals_passed and evals_total from a full benchmark record."""
  try:
    data = json.loads(record_path.read_text(encoding="utf-8"))
  except Exception as exc:
    raise ValueError(
        f"Failed to read benchmark record from {record_path}: {exc}"
    ) from exc

  evals_passed: Optional[int] = None
  evals_total: Optional[int] = None

  if "evals_passed" in data and "evals_total" in data:
    evals_passed = int(data["evals_passed"])
    evals_total = int(data["evals_total"])
  elif "majority_pass" in data:
    evals_passed = int(data["majority_pass"])
    evals_total = int(
        data.get("eval_count")
        or data.get("evals")
        or len(data.get("per_eval", {}))
        or 70
    )
  elif "strict_pass" in data:
    evals_passed = int(data["strict_pass"])
    evals_total = int(
        data.get("eval_count")
        or data.get("evals")
        or len(data.get("per_eval", {}))
        or 70
    )
  elif "individual_passed" in data and "individual_total" in data:
    evals_passed = int(data["individual_passed"])
    evals_total = int(data["individual_total"])
  elif "passes" in data and "total" in data:
    evals_passed = int(data["passes"])
    evals_total = int(data["total"])

  if evals_passed is None or evals_total is None:
    raise ValueError(
        f"Could not parse pass/total evaluation counts from {record_path}."
    )

  if evals_total <= 0:
    raise ValueError(
        f"Invalid total evaluations count in {record_path}: {evals_total} (must"
        " be > 0)."
    )

  if evals_passed < 0 or evals_passed > evals_total:
    raise ValueError(
        f"Invalid passed evaluations count in {record_path}: {evals_passed}"
        f" (must be between 0 and {evals_total})."
    )

  return evals_passed, evals_total


def resolve_scores(
    cli_passed: Optional[int],
    cli_total: Optional[int],
    bench_dir: Path,
    is_dry_run: bool,
) -> Tuple[int, int, str]:
  """Resolves evaluation counts from CLI overrides, bench history, or dry-run pending state."""
  if cli_passed is not None and cli_total is not None:
    if cli_total <= 0 or cli_passed < 0 or cli_passed > cli_total:
      raise ValueError(
          f"Invalid CLI overrides: passed={cli_passed}, total={cli_total}."
      )
    return cli_passed, cli_total, "cli_override"

  if (cli_passed is not None and cli_total is None) or (
      cli_passed is None and cli_total is not None
  ):
    raise ValueError(
        "Both --evals-passed and --evals-total must be specified together if"
        " overriding via CLI."
    )

  latest = find_latest_bench_record(bench_dir)
  if latest is not None:
    passed, total = parse_bench_scores(latest)
    return passed, total, f"history_bench:{latest.name}"

  if is_dry_run:
    return 0, 70, "dry_run_pending_bench"

  raise RuntimeError(
      "No benchmark record found in history/bench/full-*.json and no"
      " --evals-passed/--evals-total overrides provided. Refusing to submit"
      " unverified scores."
  )


def build_submission_payload(
    event_id: str,
    track_id: str,
    user_id: str,
    agent_name: str,
    agent_app_id: str,
    evals_passed: int,
    evals_total: int,
    score_source: Optional[str] = None,
) -> Dict[str, Any]:
  """Builds the submission JSON payload for CXAS Agent Academy."""
  payload: Dict[str, Any] = {
      "event_id": event_id,
      "track_id": track_id,
      "user_id": user_id,
      "agent_name": agent_name,
      "agent_app_id": agent_app_id,
      "confirm_out_of_bounds": True,
      "evals_passed": evals_passed,
      "evals_total": evals_total,
  }
  if score_source:
    payload["score_source"] = score_source
  return payload


def format_submission_summary(result: Dict[str, Any]) -> str:
  """Formats the API response into a user-readable summary."""
  lines = [
      "=" * 60,
      "CXAS AGENT ACADEMY SUBMISSION RESPONSE",
      "=" * 60,
  ]
  message = result.get("message", "Submitted successfully.")
  lines.append(f"Status Message : {message}")

  sub = result.get("submission") or {}
  if sub:
    lines.append(f"Submission ID  : {sub.get('id', 'N/A')}")
    lines.append(f"Track ID       : {sub.get('track_id', 'N/A')}")
    lines.append(f"Certified      : {'YES' if sub.get('is_certified') else 'NO'}")
    if "grade" in sub:
      lines.append(f"Grade          : {sub.get('grade')}")
    if "pass_rate" in sub:
      lines.append(f"Pass Rate      : {sub.get('pass_rate')}")
    if sub.get("feedback"):
      lines.append(f"Feedback       : {sub.get('feedback')}")

  if "grade" in result and "grade" not in sub:
    lines.append(f"Grade          : {result.get('grade')}")
  if "pass_rate" in result and "pass_rate" not in sub:
    lines.append(f"Pass Rate      : {result.get('pass_rate')}")

  cert = result.get("track_certificate")
  if cert:
    lines.append("\n🎉 TRACK CERTIFICATE ISSUED:")
    lines.append(f"  Certificate ID : {cert.get('id')}")
    lines.append(f"  Track Name     : {cert.get('track_name')}")
    lines.append(f"  Issued At      : {cert.get('issued_at')}")
    if cert.get("certificate_url") or cert.get("url"):
      lines.append(
          f"  Certificate URL: {cert.get('certificate_url') or cert.get('url')}"
      )

  badge = result.get("moma_badge")
  if badge:
    lines.append("\n🏆 MOMA BADGE AWARDED:")
    lines.append(f"  Badge ID       : {badge.get('id')}")
    lines.append(
        f"  Badge Type     : {badge.get('moma_badge_type') or badge.get('badge_type')}"
    )
    if badge.get("awarded_at"):
      lines.append(f"  Awarded At     : {badge.get('awarded_at')}")

  if result.get("feedback") and not (sub and sub.get("feedback")):
    lines.append(f"\nFeedback       : {result.get('feedback')}")

  return "\n".join(lines)


def format_user_progress_summary(progress: Dict[str, Any]) -> str:
  """Formats user event progress into a readable summary."""
  lines = [
      "=" * 60,
      "CXAS AGENT ACADEMY USER PROGRESS",
      "=" * 60,
  ]
  user_id = progress.get("user_id") or progress.get("userId") or "N/A"
  event_id = progress.get("event_id") or progress.get("eventId") or "N/A"
  lines.append(f"User ID        : {user_id}")
  lines.append(f"Event ID       : {event_id}")

  pct = progress.get("completion_percentage") or progress.get("progress_pct")
  if pct is not None:
    lines.append(f"Completion     : {pct}%")

  tracks = progress.get("tracks") or []
  if tracks:
    lines.append("\nTrack Statuses:")
    for t in tracks:
      tid = t.get("id") or t.get("track_id") or "N/A"
      tname = t.get("name") or tid
      status = t.get("status") or ("COMPLETED" if t.get("completed") else "OPEN")
      cert = " (Certified)" if t.get("is_certified") else ""
      lines.append(f"  - {tname} [{tid}]: {status}{cert}")

  submissions = progress.get("submissions") or []
  if submissions:
    lines.append(f"\nTotal Submissions: {len(submissions)}")
    for s in submissions[-3:]:
      lines.append(
          f"  - Sub #{s.get('id', 'N/A')}: Track {s.get('track_id', 'N/A')},"
          f" Grade={s.get('grade', 'N/A')},"
          f" Certified={'YES' if s.get('is_certified') else 'NO'}"
      )

  return "\n".join(lines)


def log_cloud_activity(
    op: str,
    method: str,
    target: str,
    notes: str,
    outcome: str,
    log_path: Optional[Path] = None,
) -> None:
  """Appends an audit entry to docs/cloud-log.md."""
  path = log_path or (REPO_ROOT / "docs" / "cloud-log.md")
  if not path.is_file():
    return

  try:
    if str(REPO_ROOT) not in sys.path:
      sys.path.insert(0, str(REPO_ROOT))
    from suite import cloud_log  # type: ignore[import-not-found]

    cloud_log.append_row(
        op=op,
        method=method,
        target=target,
        notes=notes,
        outcome=outcome,
        log_path=path,
    )
  except Exception:
    # Direct fallback if suite.cloud_log cannot be loaded or fails validation
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    cell = lambda t: " ".join(str(t).replace("`", "'").replace("|", "/").split())
    try:
      text = path.read_text(encoding="utf-8")
      idx = 0
      for line in text.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|", line)
        if m:
          idx = max(idx, int(m.group(1)) + 1)
      row = (
          f"| {idx} | {now_iso} | `{op}` | `{cell(method)}` | `{cell(target)}`"
          f" | {cell(notes)} — outcome: {cell(outcome)[:300]} |\n"
      )
      with open(path, "a", encoding="utf-8") as f:
        f.write(row)
    except OSError:
      pass


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
  """Parses command-line arguments."""
  parser = argparse.ArgumentParser(
      description="Automate agent submissions to CXAS Agent Academy."
  )
  parser.add_argument(
      "--base-url",
      default=os.getenv("ACADEMY_BASE_URL", DEFAULT_BASE_URL),
      help=f"Academy API URL (default: {DEFAULT_BASE_URL})",
  )
  parser.add_argument(
      "--event-id",
      default=os.getenv("ACADEMY_EVENT_ID", DEFAULT_EVENT_ID),
      help=f"Target Event ID (default: {DEFAULT_EVENT_ID})",
  )
  parser.add_argument(
      "--app",
      default=None,
      help=(
          "CES Agent App resource path or UUID (auto-resolved if omitted)"
      ),
  )
  parser.add_argument(
      "--agent-name",
      default=None,
      help="Agent display name (default: auto-resolved)",
  )
  parser.add_argument(
      "--track",
      default=os.getenv("ACADEMY_TRACK", DEFAULT_TRACK),
      help=f"Track keyword or ID to submit against (default: {DEFAULT_TRACK})",
  )
  parser.add_argument(
      "--user-id",
      default=os.getenv("ACADEMY_USER_ID", DEFAULT_USER_ID),
      help=f"Participant user identity (default: {DEFAULT_USER_ID})",
  )
  parser.add_argument(
      "--evals-passed",
      type=int,
      default=None,
      help=(
          "Evaluations passed count (overrides reading from"
          " history/bench/full-*.json)"
      ),
  )
  parser.add_argument(
      "--evals-total",
      type=int,
      default=None,
      help=(
          "Total evaluations evaluated (overrides reading from"
          " history/bench/full-*.json)"
      ),
  )
  parser.add_argument(
      "--cookie",
      default=os.getenv("ACADEMY_COOKIE", None),
      help="Browser IAP session cookie string (or set ACADEMY_COOKIE env var).",
  )
  parser.add_argument(
      "--token",
      default=os.getenv("ACADEMY_TOKEN", None),
      help="Bearer authorization token (if using token-based access).",
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help="Validate and preview the submission payload without sending it.",
  )
  parser.add_argument(
      "--bench-history-dir",
      type=Path,
      default=REPO_ROOT / "history" / "bench",
      help="Directory containing benchmark run JSON summaries.",
  )
  parser.add_argument(
      "--staging-mk",
      type=Path,
      default=REPO_ROOT / "environments" / "staging.mk",
      help="Path to environments/staging.mk for app/agent resolution.",
  )
  parser.add_argument(
      "--cloud-log",
      type=Path,
      default=REPO_ROOT / "docs" / "cloud-log.md",
      help="Path to docs/cloud-log.md for activity logging.",
  )
  parser.add_argument(
      "--no-cloud-log",
      action="store_true",
      help="Skip appending rows to docs/cloud-log.md.",
  )
  return parser.parse_args(argv)


def build_headers(cookie: Optional[str], token: Optional[str]) -> Dict[str, str]:
  """Constructs request headers including authentication."""
  headers = {
      "Content-Type": "application/json",
      "Accept": "application/json",
  }
  if cookie:
    headers["Cookie"] = cookie.strip()
  elif token:
    headers["Authorization"] = f"Bearer {token.strip()}"
  return headers


def send_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
  """Performs an HTTP request and decodes the JSON response."""
  req_headers = headers or {}
  req_body = json.dumps(data).encode("utf-8") if data else None

  req = urllib.request.Request(
      url=url, data=req_body, headers=req_headers, method=method
  )

  try:
    with urllib.request.urlopen(req) as response:
      body_text = response.read().decode("utf-8")
      return json.loads(body_text) if body_text else {}
  except urllib.error.HTTPError as exc:
    err_body = exc.read().decode("utf-8", errors="replace")
    raise RuntimeError(
        f"API request to {url} failed with HTTP {exc.code}: {err_body}"
    ) from exc
  except urllib.error.URLError as exc:
    raise RuntimeError(f"Network connection failed: {exc.reason}") from exc


def resolve_track_id(
    base_url: str,
    event_id: str,
    track_query: str,
    headers: Dict[str, str],
) -> str:
  """Finds the track ID by name, or falls back to 'auto'."""
  if track_query.lower() == "auto":
    return "auto"

  try:
    event_url = f"{base_url}/academy/api/events/{urllib.parse.quote(event_id)}"
    event_data = send_request(event_url, headers=headers)
    tracks = event_data.get("tracks", [])

    q = track_query.strip().lower()
    for t in tracks:
      tid = str(t.get("id", "")).lower()
      tname = str(t.get("name", "")).lower()
      tdesc = str(t.get("description", "")).lower()
      if q == tid or q in tname or q in tdesc:
        matched_id = t.get("id")
        matched_name = t.get("name")
        print(f"-> Matched Track: '{matched_name}' (ID: {matched_id})")
        return str(matched_id)

    print(
        f"-> Track matching '{track_query}' not found in event {event_id}."
        " Using 'auto'."
    )
    return "auto"
  except Exception as e:
    print(
        f"-> Notice: Could not query event tracks ({e}). Falling back to 'auto'."
    )
    return "auto"


def main(argv: Optional[list[str]] = None) -> int:
  args = parse_args(argv)

  agent_name = resolve_agent_name(args.agent_name, args.staging_mk)
  try:
    agent_app_id = resolve_agent_app_id(
        explicit_app=args.app,
        staging_mk_path=args.staging_mk,
        last_push_path=REPO_ROOT / "history" / "last_push.json",
        is_dry_run=args.dry_run,
    )
  except ValueError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 1

  try:
    evals_passed, evals_total, score_source = resolve_scores(
        cli_passed=args.evals_passed,
        cli_total=args.evals_total,
        bench_dir=args.bench_history_dir,
        is_dry_run=args.dry_run,
    )
  except Exception as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 1

  pass_pct = (
      (evals_passed / evals_total) * 100.0 if evals_total > 0 else 0.0
  )

  print("=" * 60)
  print("CXAS AGENT ACADEMY SUBMISSION AUTOMATION")
  print("=" * 60)
  print(f"Target URL   : {args.base_url}")
  print(f"Event ID     : {args.event_id}")
  print(f"Agent Name   : {agent_name}")
  print(f"Agent App    : {agent_app_id}")
  print(f"Participant  : {args.user_id}")
  print(f"Score Source : {score_source}")
  if score_source == "dry_run_pending_bench":
    print(f"Evals Passed : {evals_passed} / {evals_total} (Pending Bench Run)")
    print("Pass Rate    : Pending Bench Run")
  else:
    print(f"Evals Passed : {evals_passed} / {evals_total}")
    print(f"Pass Rate    : {pass_pct:.1f}%")
  print("=" * 60)

  headers = build_headers(args.cookie, args.token)

  if args.dry_run:
    track_id = args.track
    payload = build_submission_payload(
        event_id=args.event_id,
        track_id=track_id,
        user_id=args.user_id,
        agent_name=agent_name,
        agent_app_id=agent_app_id,
        evals_passed=evals_passed,
        evals_total=evals_total,
        score_source=score_source,
    )
    print("\n[DRY RUN] Planned Submission Payload:")
    print(json.dumps(payload, indent=2))

    if not args.no_cloud_log:
      log_cloud_activity(
          op="READ",
          method="Academy.submit_dry_run",
          target=f"{args.base_url}/academy/api/submissions",
          notes=(
              f"Dry-run submission check for {agent_name} (event:"
              f" {args.event_id}, track: {track_id})"
          ),
          outcome=(
              f"DRY_RUN_OK (score_source={score_source},"
              f" passed={evals_passed}/{evals_total})"
          ),
          log_path=args.cloud_log,
      )

    print("\nDry run completed successfully.")
    return 0

  # Check authentication credentials for live submission
  if not args.cookie and not args.token:
    print("\n[!] AUTHENTICATION REQUIRED:")
    print(
        "The Academy Cloud Run service is protected by Google Cloud"
        " Identity-Aware Proxy (IAP)."
    )
    print("To authenticate from this script:")
    print("  1. Open your browser tab where you are signed in:")
    print(f"     {args.base_url}/academy?eventId={args.event_id}")
    print("  2. Open DevTools (F12 or Cmd+Option+I) -> Console tab.")
    print("  3. Run: copy(document.cookie)")
    print("  4. Pass it to this script via --cookie, for example:")
    print(
        f"     python3 {sys.argv[0]} --app '{agent_app_id}' --cookie"
        " '<PASTED_COOKIE>'"
    )
    print(
        "\nAlternatively, export ACADEMY_COOKIE='<PASTED_COOKIE>' in your"
        " environment."
    )
    return 1

  # Resolve track ID (e.g. greenfield)
  track_id = resolve_track_id(args.base_url, args.event_id, args.track, headers)

  payload = build_submission_payload(
      event_id=args.event_id,
      track_id=track_id,
      user_id=args.user_id,
      agent_name=agent_name,
      agent_app_id=agent_app_id,
      evals_passed=evals_passed,
      evals_total=evals_total,
  )

  submit_url = f"{args.base_url}/academy/api/submissions"
  print(f"\nSubmitting agent to {submit_url}...")
  try:
    result = send_request(submit_url, method="POST", headers=headers, data=payload)
  except RuntimeError as e:
    print(f"\n[ERROR] Submission failed:\n{e}", file=sys.stderr)
    if not args.no_cloud_log:
      log_cloud_activity(
          op="WRITE",
          method="POST /academy/api/submissions",
          target=submit_url,
          notes=(
              f"Submission attempt for {agent_name} (event: {args.event_id},"
              f" track: {track_id})"
          ),
          outcome=f"ERROR ({str(e)[:120]})",
          log_path=args.cloud_log,
      )
    return 1

  print("\n" + format_submission_summary(result))

  grade = result.get("grade") or (result.get("submission") or {}).get("grade", "N/A")
  rate = result.get("pass_rate") or (result.get("submission") or {}).get(
      "pass_rate", f"{pass_pct:.1f}%"
  )

  if not args.no_cloud_log:
    log_cloud_activity(
        op="WRITE",
        method="POST /academy/api/submissions",
        target=submit_url,
        notes=(
            f"Submission for {agent_name} (event: {args.event_id}, track:"
            f" {track_id})"
        ),
        outcome=f"OK (grade={grade}, pass_rate={rate})",
        log_path=args.cloud_log,
    )

  # Query user progress
  progress_url = (
      f"{args.base_url}/academy/api/users/{urllib.parse.quote(args.user_id)}/events/{urllib.parse.quote(args.event_id)}/progress"
  )
  print(f"\nQuerying participant progress from {progress_url}...")
  try:
    progress_data = send_request(progress_url, method="GET", headers=headers)
    print("\n" + format_user_progress_summary(progress_data))
    if not args.no_cloud_log:
      log_cloud_activity(
          op="READ",
          method="GET /academy/api/users/<user>/events/<event>/progress",
          target=progress_url,
          notes=f"User progress check for {args.user_id} (event: {args.event_id})",
          outcome="OK (retrieved user progress)",
          log_path=args.cloud_log,
      )
  except Exception as e:
    print(f"-> Notice: Could not retrieve user progress ({e}).")

  return 0


if __name__ == "__main__":
  sys.exit(main())
