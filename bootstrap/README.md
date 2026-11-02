# Zero-to-CI/CD Interactive Bootstrap Guide (`bootstrap/bootstrap.py`)

The **Continuous Integration / Continuous Delivery** (**CI/CD**) bootstrap wizard ([`bootstrap/bootstrap.py`](bootstrap.py)) takes any **Google Customer Experience Agent Studio** (**CXAS**, also called **Customer Engagement Suite** (**CES**) or **Gemini Enterprise for Customer Experience** (**GECX**)) conversational agent repository from **zero to a configured CI/CD pipeline**.

It is a standalone, zero-dependency Python 3 script that walks you through an interactive wizard to:
1. Verify (or initiate) your **Google Cloud Command-Line Interface** (**`gcloud`**) and **GitHub Command-Line Interface** (**`gh`**) login sessions.
2. Auto-detect your GitHub repository (`owner/repo`), GECX agent directory (`cxas_app/app.json`), and `Makefile`.
3. Provision a **dedicated, repository-locked Google Cloud Service Account** (`<repo-name>-ci@<project>.iam.gserviceaccount.com`), grant `roles/ces.admin` and `roles/aiplatform.user`, and bind **Workload Identity Federation** (**WIF**, keyless login between GitHub and Google Cloud via **OpenID Connect** (**OIDC**)) scoped strictly to `attribute.repository/<owner>/<repo>`.
4. Create your **GitHub Actions Environments** (`Pull Request`, `Development`, `Staging`), **Repository Variables**, and **Repository Secrets** (`GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`).
5. Generate `.github/workflows/*.yml`, `.github/dependabot.yml`, and `.github/PULL_REQUEST_TEMPLATE.md` in the right mode for your repository:
   - **`standalone` mode (automatic for personal or non-`cloud-ai-fde` repos like `snehsm007/*`):** Writes self-contained workflows that run your repository's `Makefile` targets (`make install`, `make ci`, `make preview-up`, `make push`, `make bench-smoke`, `make bench-unstable`, `make bench-full`) directly without needing cross-organization access to `cloud-ai-fde/gecx-actions`. Check that your release workflow also runs `make gate3` after `make bench-full`; this kit's own `deploy-staging.yml` does.
   - **`gecx-actions` mode (automatic for `cloud-ai-fde/*` organization repos):** Writes 40-character Secure Hash Algorithm (**SHA**) commit-pinned caller workflows pointing to `cloud-ai-fde/gecx-actions`.

---

## 1. Prerequisites

Ensure the following tools are installed:
- **Python 3.10+**
- **Google Cloud CLI (`gcloud`)** — logged in via `gcloud auth login`. The kit's cloud targets (`make push`, `make bench-*`) use Application Default Credentials (ADC), so also run `gcloud auth application-default login`.
- **GitHub CLI (`gh`)** — logged in via `gh auth login`

---

## 2. Quick Start

### Option A: Interactive Wizard (Recommended)
```bash
make bootstrap
# or directly:
python3 bootstrap/bootstrap.py --target-dir .
```

### Option B: Preview Every Command First (`--dry-run`)
```bash
make bootstrap-dry
# or directly:
python3 bootstrap/bootstrap.py --target-dir . --dry-run
```

### Option C: Non-Interactive One-Liner

For a personal GitHub repository (e.g., `snehsm007/sneh-test-gcex-agent`) backed by your own Google Cloud Platform (**GCP**) project (e.g., `sneh-antigravity-test`):
```bash
python3 bootstrap/bootstrap.py \
  --non-interactive \
  --target-dir . \
  --gcp-project sneh-antigravity-test \
  --gcp-location us \
  --create-wif-pool
```

For a bootcamp repository inside the `cloud-ai-fde` GitHub organization backed by the bootcamp project `applied-ai-tech` (bootcamp-specific; use your own project otherwise):
```bash
python3 bootstrap/bootstrap.py \
  --non-interactive \
  --target-dir . \
  --gcp-project applied-ai-tech \
  --gcp-location us
```

### Option D: Generate Workflow Files Only (No `gcloud` or `gh` Calls)
If you want to generate `.github/workflows/*.yml`, `.github/dependabot.yml`, and `.github/PULL_REQUEST_TEMPLATE.md` locally before logging into `gh` or `gcloud`:
```bash
python3 bootstrap/bootstrap.py \
  --non-interactive \
  --target-dir . \
  --skip-gcp \
  --skip-github
```

---

## 3. CLI Flags Reference

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--target-dir` | `.` | Path to the target GECX agent repository root |
| `--repo` | *(auto-detected)* | GitHub repository in `owner/repo` format |
| `--preset` | `full` | Pipeline preset: `full`, `pr-only`, `deploy-only`, or `custom` |
| `--workflow-mode` | `auto` | `auto` (`gecx-actions` for `cloud-ai-fde/*`, `standalone` otherwise), `standalone`, or `gecx-actions` |
| `--app-dir` | `cxas_app` | Relative path to the GECX agent directory containing `app.json` |
| `--app-prefix` | `""` | Optional `APP_NAME_PREFIX` override |
| `--gcp-project` | `applied-ai-tech` (bootcamp-specific) | Target Google Cloud Project ID. With `--non-interactive` the default is the bootcamp project `applied-ai-tech`; the interactive wizard suggests `applied-ai-tech` for `cloud-ai-fde/*` repos and `sneh-antigravity-test` otherwise. Pass your own project. |
| `--gcp-location` | `us` | Target GECX location (`us`, `global`, `eu`) |
| `--service-account` | `<repo-name>-ci` | Dedicated GCP Service Account ID (6–30 chars) |
| `--wif-pool` | `github-actions` | Workload Identity Pool ID |
| `--wif-provider` | `github-actions` | Workload Identity Provider ID |
| `--create-wif-pool` | `false` | Create the WIF Pool and OIDC Provider in the target GCP project |
| `--sim-runs` | `3` | Simulation runs per scenario (`SIM_RUNS`) |
| `--sim-parallel` | `5` | Concurrent simulation workers (`SIM_PARALLEL`) |
| `--skip-gcp` | `false` | Skip `gcloud` provisioning (only configure GitHub and/or write workflows) |
| `--skip-github` | `false` | Skip `gh` CLI configuration (only configure GCP and/or write workflows) |
| `--non-interactive` | `false` | Run without prompts using CLI flags and defaults |
| `--dry-run` | `false` | Print all `gcloud`/`gh` commands and files without executing changes |
| `--self-test` | `false` | Run built-in unit self-tests |
