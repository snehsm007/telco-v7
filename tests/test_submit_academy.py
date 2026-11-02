"""Unit tests for scripts/submit_academy.py.

Tests cover:
- Auto-resolution of agent_name and agent_app_id (CLI, env, staging.mk, last_push.json, dry-run pending)
- Benchmark record discovery and score parsing from history/bench/full-*.json (newest selection, schemas, validations)
- Score resolution rules (refusing live submission on missing bench, CLI overrides, dry-run fallback)
- Payload construction for fde-bootcamp-chi / greenfield
- Submission response and user progress parsing & formatting
- Cloud activity logging (dry-run and live, isolated to tmp_path)
- Main CLI execution paths (dry-run, auth required, mocked live submission)
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict
import pytest

from scripts import submit_academy


# ---------------------------------------------------------------------------
# 1. Agent Name & App ID Resolution
# ---------------------------------------------------------------------------


def test_resolve_agent_name_explicit():
  assert submit_academy.resolve_agent_name("custom-agent") == "custom-agent"


def test_resolve_agent_name_from_env(monkeypatch):
  monkeypatch.setenv("AGENT_NAME", "env-agent-name")
  assert submit_academy.resolve_agent_name() == "env-agent-name"


def test_resolve_agent_name_from_staging_mk(tmp_path: Path, monkeypatch):
  monkeypatch.delenv("AGENT_NAME", raising=False)
  mk = tmp_path / "staging.mk"
  mk.write_text("AGENT_NAME := custom-mk-agent\nPROJECT_ID := fde-bootcamp\n")
  assert submit_academy.resolve_agent_name(staging_mk_path=mk) == "custom-mk-agent"


def test_resolve_agent_name_default(tmp_path: Path, monkeypatch):
  monkeypatch.delenv("AGENT_NAME", raising=False)
  empty_mk = tmp_path / "staging.mk"
  empty_mk.write_text("PROJECT_ID := fde-bootcamp\n")
  assert submit_academy.resolve_agent_name(staging_mk_path=empty_mk) == "snehsm-FDEBootcamp-CHI-greenfield"


def test_resolve_agent_app_id_explicit_uuid():
  resolved = submit_academy.resolve_agent_app_id(explicit_app="12345678-abcd-1234-abcd-1234567890ab")
  assert resolved == "projects/fde-bootcamp/locations/us/apps/12345678-abcd-1234-abcd-1234567890ab"


def test_resolve_agent_app_id_explicit_full_path():
  path = "projects/my-proj/locations/global/apps/my-app"
  assert submit_academy.resolve_agent_app_id(explicit_app=path) == path


def test_resolve_agent_app_id_from_env(monkeypatch):
  monkeypatch.setenv("APP_ID", "env-app-id")
  assert submit_academy.resolve_agent_app_id() == "projects/fde-bootcamp/locations/us/apps/env-app-id"


def test_resolve_agent_app_id_from_last_push_json(tmp_path: Path, monkeypatch):
  monkeypatch.delenv("APP_ID", raising=False)
  monkeypatch.delenv("APP", raising=False)
  push_json = tmp_path / "last_push.json"
  push_json.write_text(json.dumps({
      "app": "projects/fde-bootcamp/locations/us/apps/pushed-app-id",
      "commit": "abcdef1",
  }))
  assert submit_academy.resolve_agent_app_id(last_push_path=push_json) == "projects/fde-bootcamp/locations/us/apps/pushed-app-id"


def test_resolve_agent_app_id_from_staging_mk(tmp_path: Path, monkeypatch):
  monkeypatch.delenv("APP_ID", raising=False)
  monkeypatch.delenv("APP", raising=False)
  mk = tmp_path / "staging.mk"
  mk.write_text("APP_ID := mk-app-id-999\nAGENT_NAME := foo\n")
  assert submit_academy.resolve_agent_app_id(staging_mk_path=mk) == "projects/fde-bootcamp/locations/us/apps/mk-app-id-999"


def test_resolve_agent_app_id_dry_run_pending(tmp_path: Path, monkeypatch):
  monkeypatch.delenv("APP_ID", raising=False)
  monkeypatch.delenv("APP", raising=False)
  empty_mk = tmp_path / "staging.mk"
  empty_mk.write_text("APP_ID ?=\nAGENT_NAME := foo\n")
  resolved = submit_academy.resolve_agent_app_id(
      staging_mk_path=empty_mk,
      last_push_path=tmp_path / "nonexistent.json",
      is_dry_run=True,
  )
  assert resolved == "projects/fde-bootcamp/locations/us/apps/<pending-cloud-push>"


def test_resolve_agent_app_id_live_error_when_missing(tmp_path: Path, monkeypatch):
  monkeypatch.delenv("APP_ID", raising=False)
  monkeypatch.delenv("APP", raising=False)
  empty_mk = tmp_path / "staging.mk"
  empty_mk.write_text("APP_ID ?=\nAGENT_NAME := foo\n")
  with pytest.raises(ValueError, match="CES Agent App ID could not be resolved"):
    submit_academy.resolve_agent_app_id(
        staging_mk_path=empty_mk,
        last_push_path=tmp_path / "nonexistent.json",
        is_dry_run=False,
    )


# ---------------------------------------------------------------------------
# 2. Benchmark Record Discovery & Score Parsing
# ---------------------------------------------------------------------------


def test_find_latest_bench_record_picks_newest(tmp_path: Path):
  old_file = tmp_path / "full-1111111.json"
  old_file.write_text('{"majority_pass": 65}')
  time.sleep(0.02)
  new_file = tmp_path / "full-2222222.json"
  new_file.write_text('{"majority_pass": 70}')

  latest = submit_academy.find_latest_bench_record(tmp_path)
  assert latest == new_file


def test_find_latest_bench_record_empty(tmp_path: Path):
  assert submit_academy.find_latest_bench_record(tmp_path) is None


def test_parse_bench_scores_explicit_evals_keys(tmp_path: Path):
  p = tmp_path / "full-test.json"
  p.write_text(json.dumps({"evals_passed": 68, "evals_total": 70}))
  passed, total = submit_academy.parse_bench_scores(p)
  assert passed == 68
  assert total == 70


def test_parse_bench_scores_majority_pass(tmp_path: Path):
  p = tmp_path / "full-test.json"
  p.write_text(json.dumps({
      "majority_pass": 70,
      "eval_count": 70,
      "strict_pass": 66,
  }))
  passed, total = submit_academy.parse_bench_scores(p)
  assert passed == 70
  assert total == 70


def test_parse_bench_scores_individual_passed(tmp_path: Path):
  p = tmp_path / "full-test.json"
  p.write_text(json.dumps({
      "individual_passed": 208,
      "individual_total": 210,
  }))
  passed, total = submit_academy.parse_bench_scores(p)
  assert passed == 208
  assert total == 210


def test_parse_bench_scores_invalid_total(tmp_path: Path):
  p = tmp_path / "full-zero.json"
  p.write_text(json.dumps({"evals_passed": 0, "evals_total": 0}))
  with pytest.raises(ValueError, match="Invalid total evaluations count"):
    submit_academy.parse_bench_scores(p)


def test_parse_bench_scores_invalid_passed_exceeds_total(tmp_path: Path):
  p = tmp_path / "full-bad.json"
  p.write_text(json.dumps({"evals_passed": 75, "evals_total": 70}))
  with pytest.raises(ValueError, match="Invalid passed evaluations count"):
    submit_academy.parse_bench_scores(p)


def test_parse_bench_scores_unparseable(tmp_path: Path):
  p = tmp_path / "full-empty.json"
  p.write_text(json.dumps({"foo": "bar"}))
  with pytest.raises(ValueError, match="Could not parse pass/total evaluation counts"):
    submit_academy.parse_bench_scores(p)


# ---------------------------------------------------------------------------
# 3. Score Resolution Logic
# ---------------------------------------------------------------------------


def test_resolve_scores_cli_overrides(tmp_path: Path):
  passed, total, src = submit_academy.resolve_scores(
      cli_passed=70,
      cli_total=70,
      bench_dir=tmp_path,
      is_dry_run=False,
  )
  assert passed == 70
  assert total == 70
  assert src == "cli_override"


def test_resolve_scores_cli_overrides_incomplete():
  with pytest.raises(ValueError, match="Both --evals-passed and --evals-total must be specified"):
    submit_academy.resolve_scores(
        cli_passed=70,
        cli_total=None,
        bench_dir=Path("/nonexistent"),
        is_dry_run=False,
    )


def test_resolve_scores_from_bench_dir(tmp_path: Path):
  record = tmp_path / "full-abc.json"
  record.write_text(json.dumps({"majority_pass": 69, "evals": 70}))
  passed, total, src = submit_academy.resolve_scores(
      cli_passed=None,
      cli_total=None,
      bench_dir=tmp_path,
      is_dry_run=False,
  )
  assert passed == 69
  assert total == 70
  assert src == "history_bench:full-abc.json"


def test_resolve_scores_live_refusal_when_no_bench_record(tmp_path: Path):
  with pytest.raises(RuntimeError, match="No benchmark record found"):
    submit_academy.resolve_scores(
        cli_passed=None,
        cli_total=None,
        bench_dir=tmp_path,
        is_dry_run=False,
    )


def test_resolve_scores_dry_run_pending_fallback(tmp_path: Path):
  passed, total, src = submit_academy.resolve_scores(
      cli_passed=None,
      cli_total=None,
      bench_dir=tmp_path,
      is_dry_run=True,
  )
  assert passed == 0
  assert total == 70
  assert src == "dry_run_pending_bench"


# ---------------------------------------------------------------------------
# 4. Payload Construction
# ---------------------------------------------------------------------------


def test_build_submission_payload():
  payload = submit_academy.build_submission_payload(
      event_id="fde-bootcamp-chi",
      track_id="greenfield",
      user_id="snehsm@google.com",
      agent_name="snehsm-FDEBootcamp-CHI-greenfield",
      agent_app_id="projects/fde-bootcamp/locations/us/apps/test-app",
      evals_passed=70,
      evals_total=70,
      score_source="history_bench:full-xyz.json",
  )
  assert payload["event_id"] == "fde-bootcamp-chi"
  assert payload["track_id"] == "greenfield"
  assert payload["user_id"] == "snehsm@google.com"
  assert payload["agent_name"] == "snehsm-FDEBootcamp-CHI-greenfield"
  assert payload["agent_app_id"] == "projects/fde-bootcamp/locations/us/apps/test-app"
  assert payload["confirm_out_of_bounds"] is True
  assert payload["evals_passed"] == 70
  assert payload["evals_total"] == 70
  assert payload["score_source"] == "history_bench:full-xyz.json"


# ---------------------------------------------------------------------------
# 5. Response Formatting & User Progress
# ---------------------------------------------------------------------------


def test_format_submission_summary():
  resp = {
      "message": "Submission evaluated successfully.",
      "submission": {
          "id": "sub-12345",
          "track_id": "greenfield",
          "is_certified": True,
          "grade": "A+",
          "pass_rate": "100.0%",
          "feedback": "Outstanding agent implementation!",
      },
      "track_certificate": {
          "id": "cert-999",
          "track_name": "Greenfield Challenge",
          "issued_at": "2026-11-02T21:00:00Z",
          "certificate_url": "https://academy.corp.google.com/cert/999",
      },
      "moma_badge": {
          "id": "badge-777",
          "moma_badge_type": "CXAS_GREENFIELD_MASTER",
          "awarded_at": "2026-11-02T21:00:00Z",
      },
  }
  summary = submit_academy.format_submission_summary(resp)
  assert "Submission ID  : sub-12345" in summary
  assert "Certified      : YES" in summary
  assert "Grade          : A+" in summary
  assert "TRACK CERTIFICATE ISSUED" in summary
  assert "Certificate ID : cert-999" in summary
  assert "MOMA BADGE AWARDED" in summary
  assert "Badge ID       : badge-777" in summary


def test_format_user_progress_summary():
  progress = {
      "user_id": "snehsm@google.com",
      "event_id": "fde-bootcamp-chi",
      "completion_percentage": 100,
      "tracks": [
          {"id": "greenfield", "name": "Greenfield Challenge", "completed": True, "is_certified": True},
      ],
      "submissions": [
          {"id": "sub-1", "track_id": "greenfield", "grade": "A+", "is_certified": True},
      ],
  }
  summary = submit_academy.format_user_progress_summary(progress)
  assert "User ID        : snehsm@google.com" in summary
  assert "Event ID       : fde-bootcamp-chi" in summary
  assert "Completion     : 100%" in summary
  assert "Greenfield Challenge [greenfield]: COMPLETED (Certified)" in summary
  assert "Sub #sub-1: Track greenfield, Grade=A+, Certified=YES" in summary


# ---------------------------------------------------------------------------
# 6. Cloud Logging
# ---------------------------------------------------------------------------


def test_log_cloud_activity_isolated(tmp_path: Path):
  log_file = tmp_path / "cloud-log.md"
  log_file.write_text(
      "# Cloud Activity Log\n\n"
      "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
      "|---|---|---|---|---|---|\n"
  )

  submit_academy.log_cloud_activity(
      op="READ",
      method="Academy.submit_dry_run",
      target="https://cxas-labs-api-6mnjcet6bq-uc.a.run.app/academy/api/submissions",
      notes="Dry run test",
      outcome="DRY_RUN_OK",
      log_path=log_file,
  )

  content = log_file.read_text(encoding="utf-8")
  assert "| 0 |" in content
  assert "`READ`" in content
  assert "`Academy.submit_dry_run`" in content
  assert "outcome: DRY_RUN_OK" in content


# ---------------------------------------------------------------------------
# 7. Main CLI Execution Paths
# ---------------------------------------------------------------------------


def test_main_dry_run_success(tmp_path: Path, capsys):
  log_file = tmp_path / "cloud-log.md"
  log_file.write_text(
      "# Cloud Activity Log\n\n"
      "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
      "|---|---|---|---|---|---|\n"
  )
  staging_mk = tmp_path / "staging.mk"
  staging_mk.write_text("AGENT_NAME := snehsm-FDEBootcamp-CHI-greenfield\nAPP_ID ?=\n")
  bench_dir = tmp_path / "bench"
  bench_dir.mkdir()

  ret = submit_academy.main([
      "--dry-run",
      "--cloud-log", str(log_file),
      "--staging-mk", str(staging_mk),
      "--bench-history-dir", str(bench_dir),
  ])
  assert ret == 0
  captured = capsys.readouterr()
  assert "CXAS AGENT ACADEMY SUBMISSION AUTOMATION" in captured.out
  assert "projects/fde-bootcamp/locations/us/apps/<pending-cloud-push>" in captured.out
  assert "dry_run_pending_bench" in captured.out

  log_text = log_file.read_text(encoding="utf-8")
  assert "Academy.submit_dry_run" in log_text


def test_main_live_requires_auth(tmp_path: Path, monkeypatch, capsys):
  monkeypatch.delenv("ACADEMY_COOKIE", raising=False)
  monkeypatch.delenv("ACADEMY_TOKEN", raising=False)

  bench_dir = tmp_path / "bench"
  bench_dir.mkdir()
  record = bench_dir / "full-test.json"
  record.write_text(json.dumps({"majority_pass": 70, "evals": 70}))

  ret = submit_academy.main([
      "--app", "projects/fde-bootcamp/locations/us/apps/test-app",
      "--bench-history-dir", str(bench_dir),
      "--no-cloud-log",
  ])
  assert ret == 1
  captured = capsys.readouterr()
  assert "AUTHENTICATION REQUIRED" in captured.out


def test_main_live_mocked_success(tmp_path: Path, monkeypatch, capsys):
  log_file = tmp_path / "cloud-log.md"
  log_file.write_text(
      "# Cloud Activity Log\n\n"
      "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
      "|---|---|---|---|---|---|\n"
  )
  bench_dir = tmp_path / "bench"
  bench_dir.mkdir()
  record = bench_dir / "full-test.json"
  record.write_text(json.dumps({"majority_pass": 70, "evals": 70}))

  # Mock send_request to simulate Academy API
  def mock_send_request(url: str, method: str = "GET", headers=None, data=None):
    if "/academy/api/events/" in url:
      return {"tracks": [{"id": "greenfield", "name": "Greenfield Challenge"}]}
    if "/academy/api/submissions" in url and method == "POST":
      return {
          "message": "Submission evaluated successfully.",
          "submission": {
              "id": "sub-live-1",
              "track_id": "greenfield",
              "is_certified": True,
              "grade": "A+",
              "pass_rate": "100.0%",
          },
          "track_certificate": {
              "id": "cert-101",
              "track_name": "Greenfield Challenge",
              "issued_at": "2026-11-02T21:00:00Z",
          },
          "moma_badge": {
              "id": "badge-202",
              "moma_badge_type": "CXAS_GREENFIELD_MASTER",
          },
      }
    if "/progress" in url:
      return {
          "user_id": "snehsm@google.com",
          "event_id": "fde-bootcamp-chi",
          "completion_percentage": 100,
          "tracks": [{"id": "greenfield", "name": "Greenfield Challenge", "completed": True}],
      }
    return {}

  monkeypatch.setattr(submit_academy, "send_request", mock_send_request)

  ret = submit_academy.main([
      "--token", "test-auth-token",
      "--app", "projects/fde-bootcamp/locations/us/apps/test-app",
      "--bench-history-dir", str(bench_dir),
      "--cloud-log", str(log_file),
  ])
  assert ret == 0
  captured = capsys.readouterr()
  assert "TRACK CERTIFICATE ISSUED" in captured.out
  assert "MOMA BADGE AWARDED" in captured.out
  assert "CXAS AGENT ACADEMY USER PROGRESS" in captured.out

  log_text = log_file.read_text(encoding="utf-8")
  assert "POST /academy/api/submissions" in log_text
  assert "GET /academy/api/users/<user>/events/<event>/progress" in log_text
