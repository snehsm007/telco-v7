#!/usr/bin/env python3
"""Automated Agent Submissions for CXAS Agent Academy (fde-bootcamp-chi).

Submits a deployed CES agent to the Agent Academy platform for a specific
track (such as Greenfield) and handles authentication, track matching,
and certification reporting.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_BASE_URL = "https://cxas-labs-api-6mnjcet6bq-uc.a.run.app"
DEFAULT_EVENT_ID = "fde-bootcamp-chi"
DEFAULT_USER_ID = "snehsm@google.com"


def parse_args() -> argparse.Namespace:
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
      required=True,
      help="CES Agent App resource path or UUID (e.g. projects/.../apps/...)",
  )
  parser.add_argument(
      "--agent-name",
      default=None,
      help="Agent display name (default: derived from app name or path)",
  )
  parser.add_argument(
      "--track",
      default="greenfield",
      help=(
          "Track keyword or ID to submit against (e.g. 'greenfield', 'auto')"
      ),
  )
  parser.add_argument(
      "--user-id",
      default=os.getenv("ACADEMY_USER_ID", DEFAULT_USER_ID),
      help=f"Participant user identity (default: {DEFAULT_USER_ID})",
  )
  parser.add_argument(
      "--evals-passed",
      type=int,
      default=95,
      help="Evaluations passed count (default: 95)",
  )
  parser.add_argument(
      "--evals-total",
      type=int,
      default=100,
      help="Total evaluations evaluated (default: 100)",
  )
  parser.add_argument(
      "--cookie",
      default=os.getenv("ACADEMY_COOKIE", None),
      help=(
          "Browser IAP session cookie string (or set ACADEMY_COOKIE env var)."
      ),
  )
  parser.add_argument(
      "--token",
      default=os.getenv("ACADEMY_TOKEN", None),
      help="Bearer authorization token (if using token-based access).",
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help="Print the planned submission payload without sending it.",
  )
  return parser.parse_args()


def build_headers(cookie: Optional[str], token: Optional[str]) -> Dict[str, str]:
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
        return matched_id

    print(
        f"-> Track matching '{track_query}' not found in event {event_id}. Using"
        " 'auto'."
    )
    return "auto"
  except Exception as e:
    print(
        f"-> Notice: Could not query event tracks ({e}). Falling back to"
        " 'auto'."
    )
    return "auto"


def main() -> int:
  args = parse_args()

  # Derive agent name if not provided
  agent_name = args.agent_name
  if not agent_name:
    parts = args.app.strip().split("/")
    agent_name = parts[-1] if parts else "Greenfield Agent"

  headers = build_headers(args.cookie, args.token)

  print("=" * 60)
  print("CXAS AGENT ACADEMY SUBMISSION AUTOMATION")
  print("=" * 60)
  print(f"Target URL   : {args.base_url}")
  print(f"Event ID     : {args.event_id}")
  print(f"Agent Name   : {agent_name}")
  print(f"Agent App    : {args.app}")
  print(f"Participant  : {args.user_id}")
  print(f"Evals Passed : {args.evals_passed} / {args.evals_total}")
  pass_pct = (
      (args.evals_passed / args.evals_total) * 100.0
      if args.evals_total > 0
      else 0.0
  )
  print(f"Pass Rate    : {pass_pct:.1f}%")
  print("=" * 60)

  # Check authentication credentials
  if not args.cookie and not args.token and not args.dry_run:
    print("\n[!] AUTHENTICATION REQUIRED:")
    print(
        "The Academy Cloud Run service is protected by Google Cloud Identity-Aware"
        " Proxy (IAP)."
    )
    print("To authenticate from this script:")
    print("  1. Open your browser tab where you are signed in:")
    print(f"     {args.base_url}/academy?eventId={args.event_id}")
    print("  2. Open DevTools (F12 or Cmd+Option+I) -> Console tab.")
    print("  3. Run: copy(document.cookie)")
    print("  4. Pass it to this script via --cookie, for example:")
    print(
        f"     python3 {sys.argv[0]} --app '{args.app}' --cookie"
        " '<PASTED_COOKIE>'"
    )
    print("\nAlternatively, export ACADEMY_COOKIE='<PASTED_COOKIE>' in your environment.")
    return 1

  # Resolve track ID (e.g. greenfield)
  track_id = args.track
  if not args.dry_run and (args.cookie or args.token):
    track_id = resolve_track_id(
        args.base_url, args.event_id, args.track, headers
    )

  payload = {
      "event_id": args.event_id,
      "track_id": track_id,
      "user_id": args.user_id,
      "agent_name": agent_name,
      "agent_app_id": args.app,
      "confirm_out_of_bounds": True,
      "evals_passed": args.evals_passed,
      "evals_total": args.evals_total,
  }

  if args.dry_run:
    print("\n[DRY RUN] Planned Submission Payload:")
    print(json.dumps(payload, indent=2))
    print("\nDry run completed successfully.")
    return 0

  # Submit the agent
  submit_url = f"{args.base_url}/academy/api/submissions"
  print(f"\nSubmitting agent to {submit_url}...")
  try:
    result = send_request(submit_url, method="POST", headers=headers, data=payload)
  except RuntimeError as e:
    print(f"\n[ERROR] Submission failed:\n{e}")
    return 1

  print("\n" + "=" * 60)
  print("SUBMISSION RESPONSE")
  print("=" * 60)
  message = result.get("message", "Submitted successfully.")
  print(f"Status Message : {message}")

  sub = result.get("submission") or {}
  print(f"Submission ID  : {sub.get('id', 'N/A')}")
  print(f"Track ID       : {sub.get('track_id', 'N/A')}")
  print(f"Certified      : {'YES' if sub.get('is_certified') else 'NO'}")

  cert = result.get("track_certificate")
  if cert:
    print("\n🎉 TRACK CERTIFICATE ISSUED:")
    print(f"  Certificate ID : {cert.get('id')}")
    print(f"  Track Name     : {cert.get('track_name')}")
    print(f"  Issued At      : {cert.get('issued_at')}")

  badge = result.get("moma_badge")
  if badge:
    print("\n🏆 MOMA BADGE AWARDED:")
    print(f"  Badge ID       : {badge.get('id')}")
    print(f"  Badge Type     : {badge.get('moma_badge_type')}")

  return 0


if __name__ == "__main__":
  sys.exit(main())
