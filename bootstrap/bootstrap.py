#!/usr/bin/env python3
"""Interactive Zero-to-CI/CD Bootstrap Wizard CLI for GECX Agent Repositories.

Walks an engineer through onboarding any GECX (`cxas-scrapi`) repository in under
2 minutes:
  1. Google Cloud CLI (`gcloud`) and GitHub CLI (`gh`) authentication preflight.
  2. Target repository & GECX agent directory (`<app_dir>/app.json`) auto-discovery.
  3. "Choose Your Own Adventure" CI/CD pipeline preset selection (`full`, `pr-only`,
     `deploy-only`, `custom`) and workflow mode selection:
       - `standalone`: Self-contained `.github/workflows/*.yml` that run your repo's
         Makefile targets directly (works in personal GitHub accounts like `snehsm007/*`
         and private repos without needing access to `cloud-ai-fde/gecx-actions`).
       - `gecx-actions`: Reusable caller workflows pointing to `cloud-ai-fde/gecx-actions`
         (for repositories inside the `cloud-ai-fde` GitHub organization).
       - `auto` (default): Picks `gecx-actions` when `owner == "cloud-ai-fde"`, otherwise
         `standalone`.
  4. Dedicated, repository-locked GCP Service Account (`<repo>-ci`) creation, IAM role
     bindings (`roles/ces.admin`, `roles/aiplatform.user`), and Workload Identity
     Federation (`roles/iam.workloadIdentityUser` locked strictly to
     `attribute.repository/<owner>/<repo>`).
  5. GitHub Actions Environments (`Pull Request`, `Development`, `Staging`), Variables,
     Secrets (`GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`), and `gh-pages` setup.
  6. Generation of `.github/workflows/*.yml`, `.github/dependabot.yml`, and
     `.github/PULL_REQUEST_TEMPLATE.md`.

Usage:
  python3 bootstrap/bootstrap.py --target-dir .
  python3 bootstrap/bootstrap.py --target-dir . --dry-run
  python3 bootstrap/bootstrap.py --self-test
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Sequence
import urllib.parse

DEFAULT_FDE_GITHUB_ORG = "cloud-ai-fde"
DEFAULT_FDE_GCP_PROJECT_ID = "applied-ai-tech"
DEFAULT_FDE_GCP_PROJECT_NUMBER = "841588596315"
DEFAULT_GCP_LOCATION = "us"
DEFAULT_WIF_POOL_ID = "github-actions"
DEFAULT_WIF_PROVIDER_ID = "github-actions"
DEFAULT_GECX_ACTIONS_REPO = "cloud-ai-fde/gecx-actions"
DEFAULT_GECX_ACTIONS_SHA = "2909cfe1b7fb911652ffb238952c41179accfd83"
DEFAULT_GECX_ACTIONS_VERSION = "v1.0.0"

PRESET_CHOICES = ("full", "pr-only", "deploy-only", "custom")
WORKFLOW_MODE_CHOICES = ("auto", "standalone", "gecx-actions")

PULL_REQUEST_TEMPLATE_MD = """\
<!-- =====================================================================
  GECX AGENT PULL REQUEST TEMPLATE
  Please review AGENTS.md, docs/git-workflow.md, and docs/ci-cd.md.
  All sections below are required. For non-conversational PRs (e.g. docs-only,
  pure unit tests), mark interactive sections as N/A with rationale.

  CONTINUOUS SYNCHRONIZATION:
  Whenever new commits are pushed, amended, or rebased, update both the PR title
  and description to reflect the latest changes, test results, and links.
====================================================================== -->

### Description
<!-- Explain the business problem, caller impact, and 5-Part Engineering Rationale:
     (1) Prior Failure Diagnosis (conversation IDs + failing judge metrics),
     (2) What Changed, (3) Why This Fix Works, (4) Exact file:line References,
     (5) Alternatives Considered & Why Rejected. -->
{Provide background context, caller impact, or problem statement.}

Previously, {explain what the agent did before this change}. This change adds:
1. **{Core Feature / Turn}**: {What it does / what the agent says or does}
2. **{Happy Path / Opt-In}**: {e.g. Successful confirmation or downstream transfer}
3. **{Edge Case / Recovery}**: {e.g. Disambiguation, cancellation, or fallbacks}

**References**:
- PRD Requirement: `REQ-{N}`
- Defect Cluster: `DEF-{NN}` (in `docs/defects.md`)
- Architecture / TDD: `docs/tdd.md`

---

### Tests & Cloud Evaluation Gate

**Offline Gate 0 (`make ci`)**: {PASS_COUNT}/{TOTAL_COUNT} unit tests passing, >=80% per-file coverage, `bundle-check` + `overfit-check` + `cxas lint` clean.
<details>
<summary>Click to view Unit Test Coverage Breakdown</summary>

| File | Test File | Coverage | Status |
| :--- | :--- | :--- | :--- |
| `cxas_app/tools/{tool}/.../python_code.py` | `tests/test_tools.py` | 100% | PASS |
| `lib/{module}.py` | `tests/test_{module}.py` | 100% | PASS |
| **Full Repo Suite** | `make ci` | **>=80%** | **PASS** |

</details>

**Cloud CES Evaluation Runs (`evaluationRuns`)**:
<details>
<summary>Click to view Cloud Evaluation Results (3 Judge Metrics)</summary>

| Eval ID / Scenario | Custom Expectations | User Goal | Hallucination / Grounding | Cloud Run ID |
| :--- | :--- | :--- | :--- | :--- |
| `{EVAL_ID_1}` | PASS | PASS | PASS (`Justified`) | `evaluationRuns/{UUID}` |

</details>

---

### Try It Out

- **Interactive Preview App**: Provisioned automatically by `pr-validation.yml` (`<agent>-pr-<PR_NUM>`) when GCP WIF secrets are configured.
- **Sample Conversation**:
  <details>
  <summary>Click to view Turn-by-Turn Walkthrough</summary>

  1. **Caller**: *"{User utterance}"*
  2. **Agent**: *"{Agent response}"*
  3. **Caller**: *"{Follow-up utterance}"*
  4. **Agent**: *"{Verified response or action}"*

  </details>

---

### Quality & Compliance Checklist

- [ ] Branch follows convention (`fix/<n>-<slug>`, `feat/<scope>-<desc>`, `sync/...`, `epic/...`) and targets the correct base branch.
- [ ] Shared code was edited in `lib/` and inline bundles regenerated via `make bundle`.
- [ ] `make ci` passed locally (`bundle-check`, `overfit-check`, `cxas lint`, `pytest` >=80% per-file coverage, `verify_mutations.py`).
- [ ] Cloud evaluation pass rates are backed by real server-side `evaluationRuns` IDs (never offline unit tests).
- [ ] No failing test or evaluation expectation was relaxed without human approval.
"""


@dataclass
class BootstrapConfig:
    """Configuration state for bootstrapping a GECX agent repository."""

    target_dir: Path
    github_repo: str
    gcp_project_id: str = DEFAULT_FDE_GCP_PROJECT_ID
    gcp_project_number: str = DEFAULT_FDE_GCP_PROJECT_NUMBER
    gcp_location: str = DEFAULT_GCP_LOCATION
    wif_pool_id: str = DEFAULT_WIF_POOL_ID
    wif_provider_id: str = DEFAULT_WIF_PROVIDER_ID
    create_wif_pool: bool = False
    service_account_id: str = ""
    app_dir: str = "cxas_app"
    app_prefix: str = ""
    sim_runs: str = "3"
    sim_parallel: str = "5"
    max_regression_count: str = "10"
    max_regression_drop_pct: str = "10.0"
    use_custom_commands: bool = True
    install_command: str = "make install"
    build_command: str = "make ci"
    push_command: str = "make push ENV=${ENV_NAME}"
    sim_command: str = "make eval ENV=${ENV_NAME} RUNS=${SIM_RUNS} PRIORITY=P0"
    workflow_mode: str = "auto"
    enable_pr_preview: bool = True
    enable_pr_cleanup: bool = True
    enable_deploy_dev: bool = True
    enable_deploy_staging: bool = True
    enable_dependabot: bool = True
    enable_pr_template: bool = True
    init_gh_pages: bool = True
    configure_gcp: bool = True
    configure_github: bool = True
    gecx_actions_sha: str = DEFAULT_GECX_ACTIONS_SHA
    gecx_actions_version: str = DEFAULT_GECX_ACTIONS_VERSION
    dry_run: bool = False

    @property
    def repo_owner(self) -> str:
        if "/" in self.github_repo:
            return self.github_repo.split("/", 1)[0]
        return DEFAULT_FDE_GITHUB_ORG

    @property
    def repo_name(self) -> str:
        if "/" in self.github_repo:
            return self.github_repo.split("/", 1)[1]
        return self.github_repo

    @property
    def resolved_workflow_mode(self) -> str:
        if self.workflow_mode in ("standalone", "gecx-actions"):
            return self.workflow_mode
        if self.repo_owner == DEFAULT_FDE_GITHUB_ORG:
            return "gecx-actions"
        return "standalone"

    @property
    def resolved_service_account_id(self) -> str:
        if self.service_account_id:
            return sanitize_service_account_id(self.service_account_id, append_suffix=False)
        return sanitize_service_account_id(self.repo_name, append_suffix=True)

    @property
    def service_account_email(self) -> str:
        return f"{self.resolved_service_account_id}@{self.gcp_project_id}.iam.gserviceaccount.com"

    @property
    def wif_pool_resource(self) -> str:
        return (
            f"projects/{self.gcp_project_number}/locations/global/"
            f"workloadIdentityPools/{self.wif_pool_id}"
        )

    @property
    def wif_provider_resource(self) -> str:
        return f"{self.wif_pool_resource}/providers/{self.wif_provider_id}"

    @property
    def wif_principal_set(self) -> str:
        return (
            f"principalSet://iam.googleapis.com/{self.wif_pool_resource}/"
            f"attribute.repository/{self.github_repo}"
        )


def sanitize_service_account_id(raw_name: str, append_suffix: bool = True) -> str:
    """Sanitize a string into a valid GCP Service Account ID (6-30 chars, [a-z][a-z0-9-]*[a-z0-9])."""
    cleaned = re.sub(r"[^a-z0-9-]+", "-", raw_name.lower()).strip("-")
    cleaned = re.sub(r"-+", "-", cleaned)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"gecx-{cleaned}".strip("-")

    suffix = "-ci" if append_suffix and not cleaned.endswith("-ci") else ""
    max_base_len = 30 - len(suffix)
    base = cleaned[:max_base_len].rstrip("-")
    result = f"{base}{suffix}".rstrip("-")

    while len(result) < 6:
        result = f"{result}-agent"[:30].rstrip("-")
    return result


def parse_github_repo_from_remote(remote_url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub HTTPS or SSH remote URL."""
    url = remote_url.strip()
    if not url:
        return None
    ssh_match = re.match(r"^git@[^:]+:([^/]+/[^/]+?)(?:\.git)?$", url)
    if ssh_match:
        return ssh_match.group(1)
    https_match = re.match(r"^https?://[^/]+/([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if https_match:
        return https_match.group(1)
    return None


def detect_github_repo(target_dir: Path) -> str | None:
    """Auto-detect 'owner/repo' from the git origin remote in target_dir."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(target_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return parse_github_repo_from_remote(proc.stdout)
    except OSError:
        pass
    return None


def detect_app_dirs(target_dir: Path) -> list[str]:
    """Scan target_dir for GECX agent directories containing an `app.json` file."""
    ignored_parts = {".git", ".venv", "venv", "node_modules", ".agents", "__pycache__", ".pytest_cache"}
    found: list[str] = []
    if not target_dir.is_dir():
        return ["cxas_app"]
    for app_json in target_dir.rglob("app.json"):
        rel_parent = app_json.parent.relative_to(target_dir)
        if any(part in ignored_parts for part in rel_parent.parts):
            continue
        rel_str = rel_parent.as_posix()
        if rel_str and rel_str != ".":
            found.append(rel_str)
    found.sort(key=lambda p: (0 if p == "cxas_app" else 1, len(p), p))
    return found or ["cxas_app"]


def detect_makefile(target_dir: Path) -> bool:
    """Return True if a Makefile exists in target_dir."""
    return (target_dir / "Makefile").is_file()


def check_cli_installed(binary: str) -> bool:
    """Check whether a CLI binary is available on PATH."""
    return shutil.which(binary) is not None


def format_cmd(cmd: Sequence[str]) -> str:
    """Format a command list into a copy-pasteable shell string."""
    return " ".join(shlex.quote(part) for part in cmd)


def default_runner(
    cmd: Sequence[str],
    *,
    capture_output: bool = True,
    interactive: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess command."""
    if interactive:
        return subprocess.run(list(cmd), text=True, check=False)
    return subprocess.run(list(cmd), capture_output=capture_output, text=True, check=False)


def ensure_cli_authentication(
    *,
    need_gcloud: bool,
    need_gh: bool,
    interactive: bool,
    dry_run: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]] = default_runner,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> None:
    """Verify `gcloud` and `gh` CLIs are installed and authenticated."""
    if dry_run:
        print_fn("ℹ️  [dry-run] Skipping live gcloud/gh authentication checks.")
        return

    if need_gcloud:
        if not check_cli_installed("gcloud"):
            raise RuntimeError(
                "Google Cloud CLI ('gcloud') is not installed or not on PATH. "
                "Install it from https://cloud.google.com/sdk/docs/install"
            )
        res = runner(
            ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)", "--limit=1", "--quiet"]
        )
        active_account = (res.stdout or "").strip()
        if active_account:
            print_fn(f"✅ Authenticated to gcloud as: {active_account}")
        elif interactive:
            ans = input_fn("🔑 No active gcloud session found. Run 'gcloud auth login' now? [Y/n]: ").strip().lower()
            if ans in ("", "y", "yes"):
                login_res = runner(["gcloud", "auth", "login"], interactive=True)
                if login_res.returncode != 0:
                    raise RuntimeError("gcloud auth login failed.")
            else:
                raise RuntimeError("Active gcloud authentication is required to provision GCP resources.")
        else:
            raise RuntimeError("No active gcloud session found. Run 'gcloud auth login' first.")

    if need_gh:
        if not check_cli_installed("gh"):
            raise RuntimeError(
                "GitHub CLI ('gh') is not installed or not on PATH. "
                "Install it from https://cli.github.com/"
            )
        res = runner(["gh", "auth", "status"])
        if res.returncode == 0:
            print_fn("✅ Authenticated to GitHub CLI (gh)")
        elif interactive:
            ans = input_fn("🔑 Not logged into GitHub CLI. Run 'gh auth login' now? [Y/n]: ").strip().lower()
            if ans in ("", "y", "yes"):
                login_res = runner(["gh", "auth", "login"], interactive=True)
                if login_res.returncode != 0:
                    raise RuntimeError("gh auth login failed.")
            else:
                raise RuntimeError("GitHub CLI authentication is required to configure environments and secrets.")
        else:
            raise RuntimeError("Not authenticated to GitHub CLI. Run 'gh auth login' first.")


def resolve_gcp_project_number(
    project_id: str,
    *,
    dry_run: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = default_runner,
) -> str:
    """Resolve the numeric GCP Project Number for a Project ID."""
    if project_id == DEFAULT_FDE_GCP_PROJECT_ID:
        return DEFAULT_FDE_GCP_PROJECT_NUMBER
    if dry_run:
        return "<GCP_PROJECT_NUMBER>"
    res = runner(
        ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)", "--quiet"]
    )
    if res.returncode == 0 and (res.stdout or "").strip():
        return res.stdout.strip()
    raise RuntimeError(
        f"Could not resolve project number for GCP project '{project_id}'. "
        f"Verify the project exists and you have resourcemanager.projects.get access."
    )


def build_gcp_commands(config: BootstrapConfig) -> list[list[str]]:
    """Build discrete gcloud CLI commands to provision WIF and a repo-locked Service Account."""
    cmds: list[list[str]] = []

    if config.create_wif_pool:
        cmds.append([
            "gcloud", "iam", "workload-identity-pools", "create",
            config.wif_pool_id,
            f"--project={config.gcp_project_id}",
            "--location=global",
            "--display-name=GitHub Actions Pool",
            "--description=Workload Identity Pool for GitHub Actions CI/CD",
            "--quiet",
        ])
        cmds.append([
            "gcloud", "iam", "workload-identity-pools", "providers", "create-oidc",
            config.wif_provider_id,
            f"--project={config.gcp_project_id}",
            "--location=global",
            f"--workload-identity-pool={config.wif_pool_id}",
            "--display-name=GitHub Actions OIDC",
            "--issuer-uri=https://token.actions.githubusercontent.com",
            "--attribute-mapping=google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner",
            f"--attribute-condition=assertion.repository_owner == '{config.repo_owner}'",
            "--quiet",
        ])

    cmds.append([
        "gcloud", "iam", "service-accounts", "create",
        config.resolved_service_account_id,
        f"--project={config.gcp_project_id}",
        f"--display-name=GitHub Actions CI ({config.repo_name})"[:100],
        f"--description=GECX CI/CD service account for {config.github_repo}"[:256],
        "--quiet",
    ])

    for role in ("roles/ces.admin", "roles/aiplatform.user"):
        cmds.append([
            "gcloud", "projects", "add-iam-policy-binding",
            config.gcp_project_id,
            f"--member=serviceAccount:{config.service_account_email}",
            f"--role={role}",
            "--quiet",
        ])

    cmds.append([
        "gcloud", "iam", "service-accounts", "add-iam-policy-binding",
        config.service_account_email,
        f"--project={config.gcp_project_id}",
        "--role=roles/iam.workloadIdentityUser",
        f"--member={config.wif_principal_set}",
        "--quiet",
    ])

    return cmds


def build_github_commands(config: BootstrapConfig) -> list[list[str]]:
    """Build discrete gh CLI commands to configure Environments, Variables, and Secrets."""
    cmds: list[list[str]] = []

    environments: list[str] = []
    if config.enable_pr_preview or config.enable_pr_cleanup:
        environments.append("Pull Request")
    if config.enable_deploy_dev:
        environments.append("Development")
    if config.enable_deploy_staging:
        environments.append("Staging")

    for env_name in environments:
        encoded_env = urllib.parse.quote(env_name, safe="")
        cmds.append([
            "gh", "api", "--method", "PUT",
            f"repos/{config.github_repo}/environments/{encoded_env}",
        ])

    variables: list[tuple[str, str]] = [
        ("GCP_PROJECT_ID", config.gcp_project_id),
        ("GCP_LOCATION", config.gcp_location),
        ("APP_DIR", config.app_dir),
        ("SIM_RUNS", config.sim_runs),
        ("SIM_PARALLEL", config.sim_parallel),
        ("MAX_REGRESSION_COUNT", config.max_regression_count),
        ("MAX_REGRESSION_DROP_PCT", config.max_regression_drop_pct),
    ]
    if config.app_prefix:
        variables.append(("APP_NAME_PREFIX", config.app_prefix))
    if config.use_custom_commands:
        if config.install_command:
            variables.append(("INSTALL_COMMAND", config.install_command))
        if config.build_command:
            variables.append(("BUILD_COMMAND", config.build_command))
        if config.push_command:
            variables.append(("PUSH_COMMAND", config.push_command))
        if config.sim_command:
            variables.append(("SIM_COMMAND", config.sim_command))

    for var_name, var_val in variables:
        cmds.append([
            "gh", "variable", "set", var_name,
            "--repo", config.github_repo,
            "--body", var_val,
        ])

    secrets: list[tuple[str, str]] = [
        ("GCP_WIF_PROVIDER", config.wif_provider_resource),
        ("GCP_WIF_SERVICE_ACCOUNT", config.service_account_email),
    ]
    for sec_name, sec_val in secrets:
        cmds.append([
            "gh", "secret", "set", sec_name,
            "--repo", config.github_repo,
            "--body", sec_val,
        ])

    return cmds


def _render_custom_command_with_lines(config: BootstrapConfig, include_sim: bool = True) -> str:
    """Render optional custom build/push/sim command lines for a workflow `with:` block."""
    if not config.use_custom_commands:
        return ""
    lines: list[str] = []
    if config.install_command:
        lines.append(f'      install_command: "{config.install_command}"')
    if config.build_command:
        lines.append(f'      build_command: "{config.build_command}"')
    if config.push_command:
        lines.append(f'      push_command: "{config.push_command}"')
    if include_sim and config.sim_command:
        lines.append(f'      sim_command: "{config.sim_command}"')
    if not lines:
        return ""
    return "\n" + "\n".join(lines)


def _render_standalone_workflows(config: BootstrapConfig) -> dict[str, str]:
    """Render self-contained workflows that enforce the 5-Gate Confidence Ladder:
    Gate 0 (make ci) -> Gate 1 (targeted bench-smoke) -> Gate 2 (bench-unstable) -> Gate 3 (bench-full)."""
    files: dict[str, str] = {}
    agent_prefix = config.app_prefix or config.repo_name

    if config.enable_pr_preview:
        files[".github/workflows/pr-validation.yml"] = f"""name: PR Validation Gate

on:
  pull_request:
    branches: [ main, "release/**", "epic/**", "hillclimb", "build-*" ]
  workflow_dispatch:
    inputs:
      targets:
        description: "Gate 1 targeted eval IDs (e.g. VE-01,VE-02)"
        required: false
        default: ""
      eval_tier:
        description: "Cloud evaluation tier after Gate 0 (smoke = targeted only, unstable = Gate 1 -> Gate 2, full = Gate 1 -> Gate 3)"
        type: choice
        options: [ smoke, unstable, full ]
        default: "smoke"

concurrency:
  group: pr-${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  # ----------------------------------------------------------------------------
  # Gate 0: Offline Code Quality Gate (bundle-check, overfit-check, lint, test)
  # ----------------------------------------------------------------------------
  ci-gate:
    name: "Gate 0: Offline CI Code Quality"
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Set up Python & uv
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: make install

      - name: Run Offline CI Gate (make ci or make selftest on template repo)
        run: |
          if [ -f "{config.app_dir}/app.json" ]; then
            make ci
          else
            make selftest
          fi

      - name: Publish CI Validation Summary
        env:
          COMMIT_SHA: ${{{{ github.event.pull_request.head.sha || github.sha }}}}
          REF_NAME: ${{{{ github.head_ref || github.ref }}}}
        run: |
          echo "### Gate 0: Offline CI Code Quality Summary" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "| Check | Target | Status |" >> "$GITHUB_STEP_SUMMARY"
          echo "| --- | --- | --- |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Shared Library Bundle | \\`make bundle-check\\` | Verified |" >> "$GITHUB_STEP_SUMMARY"
          echo "| CXAS Structural Lint | \\`make lint\\` | Verified |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Pytest + >=80% Coverage | \\`make test\\` | Verified |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Suite Self-Tests | \\`make selftest\\` | Verified |" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "Commit: \\`${{COMMIT_SHA}}\\` on \\`${{REF_NAME}}\\`" >> "$GITHUB_STEP_SUMMARY"

  # ----------------------------------------------------------------------------
  # Gate 1 -> Gate 2: Ephemeral PR Preview & Targeted Smoke First
  # ----------------------------------------------------------------------------
  preview:
    name: "Gate 1: PR Preview & Targeted Smoke First"
    needs: ci-gate
    if: (github.event_name == 'pull_request' && github.event.action != 'closed') || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
      pull-requests: write
    env:
      ENV: staging
      AGENT_NAME: {agent_prefix}
      PROJECT_ID: ${{{{ vars.GCP_PROJECT_ID || '{config.gcp_project_id}' }}}}
      LOCATION: ${{{{ vars.GCP_LOCATION || '{config.gcp_location}' }}}}
      PR: ${{{{ github.event.pull_request.number || 'dispatch' }}}}
      TARGETS: ${{{{ inputs.targets || vars.SMOKE_TARGETS || '' }}}}
      EVAL_TIER: ${{{{ inputs.eval_tier || 'smoke' }}}}
      WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER || vars.WIF_PROVIDER }}}}
      WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT || vars.WIF_SERVICE_ACCOUNT }}}}
    steps:
      - name: Check if cloud WIF credentials and agent app exist
        id: check_wif
        run: |
          if [ -n "$WIF_PROVIDER" ] && [ -n "$WIF_SERVICE_ACCOUNT" ] && [ -f "{config.app_dir}/app.json" ]; then
            echo "enabled=true" >> "$GITHUB_OUTPUT"
          else
            echo "enabled=false" >> "$GITHUB_OUTPUT"
            echo "Skipping cloud preview deployment: configure GCP_WIF_PROVIDER and GCP_WIF_SERVICE_ACCOUNT secrets (via python3 bootstrap/bootstrap.py) to enable live PR preview apps." >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Checkout repository
        if: steps.check_wif.outputs.enabled == 'true'
        uses: actions/checkout@v4

      - name: Set up Python & uv
        if: steps.check_wif.outputs.enabled == 'true'
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        if: steps.check_wif.outputs.enabled == 'true'
        run: make install

      - name: Authenticate to Google Cloud via WIF
        if: steps.check_wif.outputs.enabled == 'true'
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{{{ env.WIF_PROVIDER }}}}
          service_account: ${{{{ env.WIF_SERVICE_ACCOUNT }}}}

      - name: Provision or update ephemeral PR preview app
        if: steps.check_wif.outputs.enabled == 'true'
        run: |
          make preview-up PR="$PR" PROJECT_ID="$PROJECT_ID" LOCATION="$LOCATION" AGENT_NAME="$AGENT_NAME"

      - name: "Gate 1: Run Targeted Smoke Evals First (~4 min, 3 repeats)"
        if: steps.check_wif.outputs.enabled == 'true' && env.TARGETS != ''
        run: |
          make bench-smoke ENV=staging APP="$(cat .preview_app)" TARGETS="$TARGETS"

      - name: "Gate 2 / Gate 3: Escalate to Unstable or Full Suite only after Gate 1 passes"
        if: steps.check_wif.outputs.enabled == 'true' && (env.EVAL_TIER == 'unstable' || env.EVAL_TIER == 'full')
        run: |
          if [ "$EVAL_TIER" = "unstable" ]; then
            make bench-unstable ENV=staging APP="$(cat .preview_app)"
          elif [ "$EVAL_TIER" = "full" ]; then
            make bench-full ENV=staging APP="$(cat .preview_app)"
          fi
"""

    if config.enable_pr_cleanup:
        files[".github/workflows/pr-cleanup.yml"] = f"""name: PR Preview Cleanup

on:
  pull_request:
    types: [ closed ]

concurrency:
  group: pr-cleanup-${{{{ github.event.pull_request.number }}}}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  cleanup:
    name: Destroy Temporary GECX Preview App
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    env:
      ENV: staging
      AGENT_NAME: {agent_prefix}
      PROJECT_ID: ${{{{ vars.GCP_PROJECT_ID || '{config.gcp_project_id}' }}}}
      LOCATION: ${{{{ vars.GCP_LOCATION || '{config.gcp_location}' }}}}
      PR: ${{{{ github.event.pull_request.number }}}}
      WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER || vars.WIF_PROVIDER }}}}
      WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT || vars.WIF_SERVICE_ACCOUNT }}}}
    steps:
      - name: Check if cloud WIF credentials are configured
        id: check_wif
        run: |
          if [ -n "$WIF_PROVIDER" ] && [ -n "$WIF_SERVICE_ACCOUNT" ] && [ -f "{config.app_dir}/app.json" ]; then
            echo "enabled=true" >> "$GITHUB_OUTPUT"
          else
            echo "enabled=false" >> "$GITHUB_OUTPUT"
          fi

      - uses: actions/checkout@v4
        if: steps.check_wif.outputs.enabled == 'true'
      - uses: astral-sh/setup-uv@v5
        if: steps.check_wif.outputs.enabled == 'true'
      - run: make install
        if: steps.check_wif.outputs.enabled == 'true'
      - uses: google-github-actions/auth@v2
        if: steps.check_wif.outputs.enabled == 'true'
        with:
          workload_identity_provider: ${{{{ env.WIF_PROVIDER }}}}
          service_account: ${{{{ env.WIF_SERVICE_ACCOUNT }}}}
      - name: Delete preview app
        if: steps.check_wif.outputs.enabled == 'true'
        run: make preview-down PR="$PR" PROJECT_ID="$PROJECT_ID" LOCATION="$LOCATION" AGENT_NAME="$AGENT_NAME"
"""

    if config.enable_deploy_dev:
        files[".github/workflows/deploy-dev.yml"] = f"""name: Deploy to Dev (GECX)

on:
  push:
    branches: [ main, "epic/**", "hillclimb", "build-*" ]
  workflow_dispatch:
    inputs:
      targets:
        description: "Gate 1 targeted eval IDs (e.g. VE-01,VE-02)"
        required: false
        default: ""
      eval_tier:
        description: "Cloud evaluation tier (skip = offline Gate 0 only, smoke = Gate 1 targeted evals x3, unstable = Gate 1 -> Gate 2 x5, full = Gate 1 -> Gate 3 x3)"
        type: choice
        options: [ skip, smoke, unstable, full ]
        default: "smoke"

concurrency:
  group: deploy-dev-${{{{ github.ref }}}}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  offline-ci:
    name: "Gate 0: Offline CI Gate"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: make install
      - name: Run Offline CI or Self-Tests
        run: |
          if [ -f "{config.app_dir}/app.json" ]; then
            make ci
          else
            make selftest
          fi

  deploy-dev:
    name: "Gate 1 -> Gate 2: Push to Staging & Targeted Evals First"
    needs: offline-ci
    if: github.event_name == 'workflow_dispatch' || github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    env:
      ENV: staging
      TARGETS: ${{{{ inputs.targets || vars.SMOKE_TARGETS || '' }}}}
      EVAL_TIER: ${{{{ inputs.eval_tier || 'smoke' }}}}
      WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER || vars.WIF_PROVIDER }}}}
      WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT || vars.WIF_SERVICE_ACCOUNT }}}}
    steps:
      - name: Check if cloud WIF credentials and agent app exist
        id: check_wif
        run: |
          if [ -n "$WIF_PROVIDER" ] && [ -n "$WIF_SERVICE_ACCOUNT" ] && [ -f "{config.app_dir}/app.json" ]; then
            echo "enabled=true" >> "$GITHUB_OUTPUT"
          else
            echo "enabled=false" >> "$GITHUB_OUTPUT"
            echo "Gate 0 Offline CI passed. Cloud push skipped because GCP_WIF_PROVIDER / GCP_WIF_SERVICE_ACCOUNT secrets are not configured yet." >> "$GITHUB_STEP_SUMMARY"
          fi

      - uses: actions/checkout@v4
        if: steps.check_wif.outputs.enabled == 'true'
      - uses: astral-sh/setup-uv@v5
        if: steps.check_wif.outputs.enabled == 'true'
      - run: make install
        if: steps.check_wif.outputs.enabled == 'true'
      - uses: google-github-actions/auth@v2
        if: steps.check_wif.outputs.enabled == 'true'
        with:
          workload_identity_provider: ${{{{ env.WIF_PROVIDER }}}}
          service_account: ${{{{ env.WIF_SERVICE_ACCOUNT }}}}
      - name: "Push agent to staging & climb Confidence Ladder (Targeted Gate 1 first)"
        if: steps.check_wif.outputs.enabled == 'true'
        run: |
          make push ENV=staging
          if [ "$EVAL_TIER" != "skip" ] && [ -n "$TARGETS" ]; then
            echo "=== Gate 1: Running targeted smoke evals ($TARGETS x 3) first ==="
            make bench-smoke ENV=staging TARGETS="$TARGETS"
          fi
          if [ "$EVAL_TIER" = "unstable" ]; then
            echo "=== Gate 2: Gate 1 passed; running unstable set (x 5) ==="
            make bench-unstable ENV=staging
          elif [ "$EVAL_TIER" = "full" ]; then
            echo "=== Gate 3: Gate 1 passed; running full visible suite (x 3) ==="
            make bench-full ENV=staging
          fi
"""

    if config.enable_deploy_staging:
        files[".github/workflows/deploy-staging.yml"] = f"""name: Deploy to Staging & Full Suite Gate (Gate 3)

on:
  workflow_dispatch:
    inputs:
      targets:
        description: "Gate 1 targeted smoke eval IDs to verify before full suite (e.g. VE-01,VE-02)"
        required: false
        default: ""
      version_tag:
        description: "Release Tag / Version (e.g. v1.0.0)"
        required: false
        default: ""
      simulation_mode:
        description: "Evaluation tier (smoke-then-full = Gate 1 smoke then Gate 3 full, smoke-only = Gate 1 only, skip = push only)"
        type: choice
        options: [ smoke-then-full, smoke-only, skip ]
        default: "smoke-then-full"

concurrency:
  group: deploy-staging
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy-staging:
    name: "Gate 0 -> Gate 1 (Targeted) -> Gate 3 (Full Suite)"
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    env:
      ENV: staging
      TARGETS: ${{{{ inputs.targets || vars.SMOKE_TARGETS || '' }}}}
      SIM_MODE: ${{{{ inputs.simulation_mode || 'smoke-then-full' }}}}
      WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER || vars.WIF_PROVIDER }}}}
      WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT || vars.WIF_SERVICE_ACCOUNT }}}}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: make install
      - name: "Gate 0: Offline CI"
        run: make ci
      - name: Authenticate to Google Cloud via WIF
        if: env.WIF_PROVIDER != '' && env.WIF_SERVICE_ACCOUNT != ''
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{{{ env.WIF_PROVIDER }}}}
          service_account: ${{{{ env.WIF_SERVICE_ACCOUNT }}}}
      - name: "Push to Staging -> Gate 1 (Targeted Smoke) -> Gate 3 (Full Suite)"
        if: env.WIF_PROVIDER != '' && env.WIF_SERVICE_ACCOUNT != ''
        run: |
          make push ENV=staging
          if [ "$SIM_MODE" != "skip" ] && [ -n "$TARGETS" ]; then
            echo "=== Gate 1: Running targeted smoke evals ($TARGETS x 3) first ==="
            make bench-smoke ENV=staging TARGETS="$TARGETS"
          fi
          if [ "$SIM_MODE" = "smoke-then-full" ]; then
            echo "=== Gate 3: Gate 1 passed; running full suite (x 3) ==="
            make bench-full ENV=staging
          fi
"""

    return files


def render_workflow_files(config: BootstrapConfig) -> dict[str, str]:
    """Render `.github/workflows/*.yml`, `.github/dependabot.yml`, and `.github/PULL_REQUEST_TEMPLATE.md`."""
    if config.resolved_workflow_mode == "standalone":
        files = _render_standalone_workflows(config)
    else:
        files = {}
        pin = f"{config.gecx_actions_sha} # {config.gecx_actions_version}"
        custom_with = _render_custom_command_with_lines(config, include_sim=True)

        if config.enable_pr_preview:
            files[".github/workflows/pr-validation.yml"] = f"""name: PR Validation Gate

on:
  pull_request:
    branches: [ main, "release/**", "epic/**" ]

concurrency:
  group: pr-${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  ci-gate:
    name: CI Code Quality Gate
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Setup Environment
        uses: {DEFAULT_GECX_ACTIONS_REPO}/setup-environment@{pin}
        with:
          install_command: "{config.install_command or 'make install'}"
      - name: Run CI Validation Pipeline
        run: {config.build_command or 'make ci'}

  preview:
    name: PR Preview & Simulations
    uses: {DEFAULT_GECX_ACTIONS_REPO}/.github/workflows/preview.yml@{pin}
    permissions:
      contents: write
      id-token: write
      deployments: write
      pull-requests: write
      issues: write
    with:
      app_dir: "{config.app_dir}"{custom_with}
    secrets:
      GCP_WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER }}}}
      GCP_WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT }}}}
"""

        if config.enable_pr_cleanup:
            cleanup_with = ""
            if config.use_custom_commands and config.install_command:
                cleanup_with = f'\n    with:\n      install_command: "{config.install_command}"'
            files[".github/workflows/pr-cleanup.yml"] = f"""name: PR Preview Cleanup

on:
  pull_request:
    types: [ closed ]

concurrency:
  group: pr-cleanup-${{{{ github.event.pull_request.number }}}}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  cleanup:
    name: Destroy Temporary GECX Preview App
    uses: {DEFAULT_GECX_ACTIONS_REPO}/.github/workflows/cleanup.yml@{pin}
    permissions:
      contents: read
      id-token: write
      deployments: write
      pull-requests: write
      issues: write{cleanup_with}
    secrets:
      GCP_WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER }}}}
      GCP_WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT }}}}
"""

        if config.enable_deploy_dev:
            files[".github/workflows/deploy-dev.yml"] = f"""name: Deploy to Dev (GECX)

on:
  push:
    branches: [ main, "epic/**" ]
  workflow_dispatch:
    inputs:
      simulation_mode:
        description: "Simulation execution mode"
        type: choice
        options: [ auto, force, skip ]
        default: "auto"

concurrency:
  group: deploy-dev-${{{{ github.ref }}}}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy-dev:
    name: Deploy to Dev Environment
    uses: {DEFAULT_GECX_ACTIONS_REPO}/.github/workflows/deploy.yml@{pin}
    permissions:
      contents: write
      id-token: write
      deployments: write
      pull-requests: read
      issues: read
    with:
      environment: Development
      app_dir: "{config.app_dir}"
      simulation_mode: ${{{{ inputs.simulation_mode || 'auto' }}}}{custom_with}
    secrets:
      GCP_WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER }}}}
      GCP_WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT }}}}
      APP_GITHUB_TOKEN: ${{{{ secrets.APP_GITHUB_TOKEN || secrets.GITHUB_TOKEN }}}}
"""

        if config.enable_deploy_staging:
            files[".github/workflows/deploy-staging.yml"] = f"""name: Deploy to Staging & Create Release

on:
  workflow_dispatch:
    inputs:
      version_tag:
        description: "Release version tag (leave blank to auto-increment patch)"
        required: false
        type: string
        default: ""
      release_title:
        description: "Optional release title"
        required: false
        type: string
        default: ""
      is_prerelease:
        description: "Mark as pre-release"
        required: false
        type: boolean
        default: false
      simulation_mode:
        description: "Simulation execution mode ('auto' reuses commit-SHA cache)"
        required: false
        type: choice
        options: [ auto, force, skip ]
        default: "auto"

concurrency:
  group: deploy-staging
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy-staging:
    name: Deploy to Staging & Release
    uses: {DEFAULT_GECX_ACTIONS_REPO}/.github/workflows/deploy.yml@{pin}
    permissions:
      contents: write
      id-token: write
      deployments: write
      pull-requests: read
      issues: read
    with:
      environment: Staging
      app_dir: "{config.app_dir}"
      simulation_mode: ${{{{ inputs.simulation_mode || 'auto' }}}}
      create_release: true
      release_tag: ${{{{ inputs.version_tag || '' }}}}
      release_title: ${{{{ inputs.release_title || '' }}}}
      is_prerelease: ${{{{ inputs.is_prerelease || false }}}}{custom_with}
    secrets:
      GCP_WIF_PROVIDER: ${{{{ secrets.GCP_WIF_PROVIDER }}}}
      GCP_WIF_SERVICE_ACCOUNT: ${{{{ secrets.GCP_WIF_SERVICE_ACCOUNT }}}}
      APP_GITHUB_TOKEN: ${{{{ secrets.APP_GITHUB_TOKEN || secrets.GITHUB_TOKEN }}}}
"""

    if config.enable_dependabot:
        files[".github/dependabot.yml"] = """version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
"""

    if config.enable_pr_template:
        files[".github/PULL_REQUEST_TEMPLATE.md"] = PULL_REQUEST_TEMPLATE_MD

    return files


def apply_preset(config: BootstrapConfig, preset: str) -> None:
    """Apply a workflow preset ('full', 'pr-only', 'deploy-only') to BootstrapConfig."""
    if preset == "full":
        config.enable_pr_preview = True
        config.enable_pr_cleanup = True
        config.enable_deploy_dev = True
        config.enable_deploy_staging = True
        config.enable_dependabot = True
        config.enable_pr_template = True
        config.init_gh_pages = True
    elif preset == "pr-only":
        config.enable_pr_preview = True
        config.enable_pr_cleanup = True
        config.enable_deploy_dev = False
        config.enable_deploy_staging = False
        config.enable_dependabot = True
        config.enable_pr_template = True
        config.init_gh_pages = True
    elif preset == "deploy-only":
        config.enable_pr_preview = False
        config.enable_pr_cleanup = False
        config.enable_deploy_dev = True
        config.enable_deploy_staging = True
        config.enable_dependabot = True
        config.enable_pr_template = True
        config.init_gh_pages = True


def _prompt_text(prompt: str, default: str, input_fn: Callable[[str], str]) -> str:
    val = input_fn(f"{prompt} [{default}]: ").strip()
    return val if val else default


def _prompt_bool(prompt: str, default: bool, input_fn: Callable[[str], str]) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = input_fn(f"{prompt} {suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "true", "1")


def build_config_from_args(
    args: argparse.Namespace,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = default_runner,
) -> BootstrapConfig:
    """Build BootstrapConfig directly from CLI flags (--non-interactive mode)."""
    target_dir = Path(args.target_dir).resolve()
    github_repo = args.repo or detect_github_repo(target_dir) or f"{DEFAULT_FDE_GITHUB_ORG}/{target_dir.name}"
    detected_apps = detect_app_dirs(target_dir)
    app_dir = args.app_dir or detected_apps[0]

    config = BootstrapConfig(
        target_dir=target_dir,
        github_repo=github_repo,
        gcp_project_id=args.gcp_project or DEFAULT_FDE_GCP_PROJECT_ID,
        gcp_location=args.gcp_location or DEFAULT_GCP_LOCATION,
        wif_pool_id=args.wif_pool or DEFAULT_WIF_POOL_ID,
        wif_provider_id=args.wif_provider or DEFAULT_WIF_PROVIDER_ID,
        create_wif_pool=bool(args.create_wif_pool),
        service_account_id=args.service_account or "",
        app_dir=app_dir,
        app_prefix=args.app_prefix or "",
        sim_runs=args.sim_runs or "3",
        sim_parallel=args.sim_parallel or "5",
        workflow_mode=args.workflow_mode or "auto",
        configure_gcp=not args.skip_gcp,
        configure_github=not args.skip_github,
        gecx_actions_sha=args.sha or DEFAULT_GECX_ACTIONS_SHA,
        gecx_actions_version=DEFAULT_GECX_ACTIONS_VERSION,
        dry_run=args.dry_run,
    )
    apply_preset(config, args.preset or "full")
    return config


def run_interactive_wizard(
    args: argparse.Namespace,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    runner: Callable[..., subprocess.CompletedProcess[str]] = default_runner,
) -> BootstrapConfig:
    """Run the interactive 'Choose Your Own Adventure' onboarding wizard."""
    target_dir = Path(args.target_dir).resolve()
    detected_repo = args.repo or detect_github_repo(target_dir) or f"{DEFAULT_FDE_GITHUB_ORG}/{target_dir.name}"
    detected_apps = detect_app_dirs(target_dir)
    default_app_dir = args.app_dir or detected_apps[0]

    print_fn("\n======================================================================")
    print_fn("🚀 GECX Agent — Zero-to-CI/CD Interactive Bootstrap Wizard")
    print_fn("======================================================================")
    print_fn(f"📂 Target Directory: {target_dir}")

    github_repo = _prompt_text("GitHub Repository (owner/repo)", detected_repo, input_fn)
    app_dir = _prompt_text("Path to GECX agent directory (containing app.json)", default_app_dir, input_fn)
    app_prefix = _prompt_text("Optional GECX App Name Prefix override", args.app_prefix or "", input_fn)

    choice_map = {"1": "full", "2": "pr-only", "3": "deploy-only", "4": "custom"}
    raw_choice = _prompt_text("Select pipeline preset (1=full, 2=pr-only, 3=deploy-only, 4=custom)", "1", input_fn)
    preset = choice_map.get(raw_choice, "full")

    config = BootstrapConfig(
        target_dir=target_dir,
        github_repo=github_repo,
        app_dir=app_dir,
        app_prefix=app_prefix,
        workflow_mode=args.workflow_mode or "auto",
        dry_run=args.dry_run,
    )
    apply_preset(config, preset)

    is_fde_org = config.repo_owner == DEFAULT_FDE_GITHUB_ORG
    default_gcp_project = args.gcp_project or (DEFAULT_FDE_GCP_PROJECT_ID if is_fde_org else "sneh-antigravity-test")
    config.gcp_project_id = _prompt_text("Google Cloud Project ID", default_gcp_project, input_fn)
    config.gcp_location = _prompt_text("GECX Location (us, global, eu)", args.gcp_location or DEFAULT_GCP_LOCATION, input_fn)

    default_sa = args.service_account or config.resolved_service_account_id
    chosen_sa = _prompt_text("Dedicated GCP Service Account ID (6-30 chars)", default_sa, input_fn)
    config.service_account_id = sanitize_service_account_id(chosen_sa, append_suffix=False)

    if config.gcp_project_id != DEFAULT_FDE_GCP_PROJECT_ID:
        config.create_wif_pool = _prompt_bool(
            f"Create Workload Identity Pool '{config.wif_pool_id}' & OIDC Provider in '{config.gcp_project_id}'?",
            True,
            input_fn,
        )

    config.configure_gcp = _prompt_bool(
        f"Provision GCP Service Account ({config.service_account_email}) & WIF bindings now via gcloud?",
        not args.skip_gcp,
        input_fn,
    )
    config.configure_github = _prompt_bool(
        f"Configure GitHub Environments, Variables & Secrets on '{config.github_repo}' now via gh CLI?",
        not args.skip_github,
        input_fn,
    )
    return config


def execute_bootstrap(
    config: BootstrapConfig,
    *,
    interactive: bool = True,
    runner: Callable[..., subprocess.CompletedProcess[str]] = default_runner,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> list[Path]:
    """Execute the configured GCP, GitHub, and workflow file generation steps."""
    ensure_cli_authentication(
        need_gcloud=config.configure_gcp,
        need_gh=config.configure_github,
        interactive=interactive,
        dry_run=config.dry_run,
        runner=runner,
        input_fn=input_fn,
        print_fn=print_fn,
    )

    if config.configure_gcp:
        config.gcp_project_number = resolve_gcp_project_number(
            config.gcp_project_id,
            dry_run=config.dry_run,
            runner=runner,
        )

    print_fn("\n======================================================================")
    print_fn("📋 Bootstrap Configuration Summary")
    print_fn("======================================================================")
    print_fn(f"  • GitHub Repository     : {config.github_repo}")
    print_fn(f"  • Workflow Mode         : {config.resolved_workflow_mode}")
    print_fn(f"  • Agent Directory       : {config.app_dir}")
    print_fn(f"  • GCP Project           : {config.gcp_project_id} (#{config.gcp_project_number}, location: {config.gcp_location})")
    print_fn(f"  • Service Account       : {config.service_account_email}")
    print_fn(f"  • WIF Provider          : {config.wif_provider_resource}")
    print_fn(f"  • Repo-Locked Principal : {config.wif_principal_set}")
    print_fn("======================================================================")

    if interactive and not config.dry_run:
        if not _prompt_bool("\nProceed with applying this configuration?", True, input_fn):
            print_fn("Aborted by user.")
            return []

    if config.configure_gcp:
        print_fn("\n☁️  Configuring Google Cloud Service Account & WIF IAM Bindings...")
        for cmd in build_gcp_commands(config):
            if config.dry_run:
                print_fn(f"  [dry-run] {format_cmd(cmd)}")
                continue
            print_fn(f"  $ {format_cmd(cmd)}")
            res = runner(cmd)
            if res.returncode != 0:
                stderr = (res.stderr or "").strip()
                if "already exists" in stderr.lower() or "already_exists" in stderr.lower():
                    print_fn("    ℹ️  Resource already exists; continuing...")
                else:
                    raise RuntimeError(f"Command failed ({res.returncode}): {format_cmd(cmd)}\n{stderr}")

    if config.configure_github:
        print_fn("\n🐙 Configuring GitHub Environments, Variables & Secrets...")
        for cmd in build_github_commands(config):
            if config.dry_run:
                print_fn(f"  [dry-run] {format_cmd(cmd)}")
                continue
            print_fn(f"  $ {format_cmd(cmd)}")
            res = runner(cmd)
            if res.returncode != 0:
                stderr = (res.stderr or "").strip()
                raise RuntimeError(f"GitHub CLI command failed ({res.returncode}): {format_cmd(cmd)}\n{stderr}")

    rendered_files = render_workflow_files(config)
    written_paths: list[Path] = []
    print_fn("\n📄 Generating GitHub Actions Workflow Files...")
    for rel_path, content in rendered_files.items():
        full_path = config.target_dir / rel_path
        written_paths.append(full_path)
        if config.dry_run:
            print_fn(f"  [dry-run] Would write {full_path}")
            continue
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        print_fn(f"  ✅ Wrote {rel_path}")

    print_fn("\n🎉 Bootstrap complete!")
    return written_paths


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "my-agent"
        root.mkdir(parents=True, exist_ok=True)
        # 1. Standalone mode (personal repo)
        cfg_standalone = BootstrapConfig(
            target_dir=root,
            github_repo="snehsm007/my-agent",
            gcp_project_id="sneh-antigravity-test",
            gcp_project_number="123456789",
            create_wif_pool=True,
            configure_gcp=False,
            configure_github=False,
            workflow_mode="auto",
        )
        assert cfg_standalone.resolved_workflow_mode == "standalone"
        gcp_cmds = build_gcp_commands(cfg_standalone)
        assert len(gcp_cmds) == 6
        gh_cmds = build_github_commands(cfg_standalone)
        assert any("GCP_WIF_PROVIDER" in c for c in gh_cmds)
        written = execute_bootstrap(cfg_standalone, interactive=False, print_fn=lambda _: None)
        assert len(written) == 6
        assert (root / ".github" / "workflows" / "pr-validation.yml").exists()
        assert (root / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()
        pr_val = (root / ".github" / "workflows" / "pr-validation.yml").read_text(encoding="utf-8")
        assert "make ci" in pr_val and "cloud-ai-fde/gecx-actions" not in pr_val

        # 2. gecx-actions mode (cloud-ai-fde org repo)
        cfg_org = BootstrapConfig(
            target_dir=root,
            github_repo="cloud-ai-fde/my-agent",
            configure_gcp=False,
            configure_github=False,
            workflow_mode="auto",
        )
        assert cfg_org.resolved_workflow_mode == "gecx-actions"
        files_org = render_workflow_files(cfg_org)
        assert "cloud-ai-fde/gecx-actions/.github/workflows/preview.yml@" in files_org[".github/workflows/pr-validation.yml"]

    print("OK: 2/2 bootstrap self-test cases passed")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Interactive Zero-to-CI/CD Bootstrap CLI for GECX Agent Repositories."
    )
    parser.add_argument("--target-dir", default=".", help="Path to the target GECX agent repository root.")
    parser.add_argument("--repo", default="", help="GitHub repository in 'owner/repo' format.")
    parser.add_argument("--preset", choices=PRESET_CHOICES, default="full", help="Pipeline preset.")
    parser.add_argument(
        "--workflow-mode",
        choices=WORKFLOW_MODE_CHOICES,
        default="auto",
        help="Workflow template mode: 'auto' (default), 'standalone' (self-contained), or 'gecx-actions' (cloud-ai-fde org).",
    )
    parser.add_argument("--app-dir", default="", help="Relative path to the GECX agent directory containing app.json.")
    parser.add_argument("--app-prefix", default="", help="Optional APP_NAME_PREFIX override.")
    parser.add_argument("--gcp-project", default="", help="Google Cloud Project ID.")
    parser.add_argument("--gcp-location", default="", help="GECX region/location (default: 'us').")
    parser.add_argument("--service-account", default="", help="GCP Service Account ID override.")
    parser.add_argument("--wif-pool", default="", help="Workload Identity Pool ID (default: 'github-actions').")
    parser.add_argument("--wif-provider", default="", help="Workload Identity Provider ID (default: 'github-actions').")
    parser.add_argument("--create-wif-pool", action="store_true", help="Create the WIF Pool and OIDC Provider in GCP.")
    parser.add_argument("--sim-runs", default="3", help="Simulation runs per scenario (default: 3).")
    parser.add_argument("--sim-parallel", default="5", help="Parallel simulation workers (default: 5).")
    parser.add_argument("--sha", default="", help="Explicit 40-char commit SHA of cloud-ai-fde/gecx-actions to pin.")
    parser.add_argument("--skip-gcp", action="store_true", help="Skip executing gcloud commands.")
    parser.add_argument("--skip-github", action="store_true", help="Skip executing gh CLI commands.")
    parser.add_argument("--non-interactive", action="store_true", help="Run without interactive prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and files without making changes.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self-tests.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    try:
        if args.non_interactive:
            config = build_config_from_args(args)
        else:
            config = run_interactive_wizard(args)
        execute_bootstrap(config, interactive=not args.non_interactive)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except RuntimeError as exc:
        print(f"\n❌ Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
