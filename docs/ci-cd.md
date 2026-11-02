# CI/CD & GitHub Actions Setup Guide

This guide explains how **Continuous Integration** (**CI**, automatic code and test checks on every change) and **Continuous Delivery** (**CD**, automatic deployment to cloud environments) work in this repository, and how to set them up.

---

## 1. Quick Setup with the Bootstrap Wizard (`make bootstrap`)

Our [`bootstrap/bootstrap.py`](../bootstrap/bootstrap.py) wizard automates Google Cloud **Workload Identity Federation** (**WIF**, keyless login from GitHub Actions to Google Cloud using **OpenID Connect** (**OIDC**) tokens—no JSON key files needed), GitHub Secrets/Variables, and `.github/workflows/*.yml` generation.

### Step 1: Log in to Google Cloud (`gcloud`) and GitHub (`gh`)
```bash
gcloud auth login
gcloud auth application-default login   # Application Default Credentials (ADC), used by the kit's cloud targets
gh auth login
```

### Step 2: Preview What the Bootstrap Wizard Will Do (`--dry-run`)
```bash
make bootstrap-dry
```

### Step 3: Run the Bootstrap Wizard
```bash
make bootstrap
```
Or non-interactively for your Google Cloud Platform (**GCP**) project (for example `sneh-antigravity-test`):
```bash
python3 bootstrap/bootstrap.py \
  --non-interactive \
  --target-dir . \
  --gcp-project sneh-antigravity-test \
  --gcp-location us \
  --create-wif-pool
```

### What `bootstrap.py` Provisions Automatically
1. **Google Cloud WIF Pool & OIDC Provider** (`github-actions`, when `--create-wif-pool` is passed).
2. **Dedicated Service Account** (`<repo-name>-ci@<project>.iam.gserviceaccount.com`) with:
   - `roles/ces.admin` (to create/update **Customer Engagement Suite** (**CES**) preview and staging apps and run cloud evaluations)
   - `roles/aiplatform.user` (for Vertex AI model and simulation calls)
   - `roles/iam.workloadIdentityUser` locked strictly to your GitHub repository (`attribute.repository/<owner>/<repo>`)
3. **GitHub Actions Environments** (`Pull Request`, `Development`, `Staging`), **Repository Variables** (`GCP_PROJECT_ID`, `GCP_LOCATION`, `APP_DIR`, `SIM_RUNS`, `SIM_PARALLEL`), and **Repository Secrets** (`GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`).
4. **Workflow Files in `.github/workflows/`** plus `.github/dependabot.yml` and `.github/PULL_REQUEST_TEMPLATE.md`.

---

## 2. How the Two Workflow Modes Work (`standalone` vs. `gecx-actions`)

`bootstrap/bootstrap.py` automatically selects the right workflow mode based on where your GitHub repository lives:

| Mode | When Used | How It Works |
| :--- | :--- | :--- |
| **`standalone`** | Personal GitHub accounts (e.g., `snehsm007/*`) or any repo outside `cloud-ai-fde` | Generates self-contained `.github/workflows/*.yml` files that call your repo's `Makefile` targets directly (`make install`, `make ci`, `make preview-up`, `make push`, `make bench-smoke`, `make bench-unstable`, `make bench-full`). Works in any personal or private repo without needing cross-org permissions. |
| **`gecx-actions`** | Repositories inside the `cloud-ai-fde` GitHub organization | Generates caller workflows that invoke `cloud-ai-fde/gecx-actions/.github/workflows/{preview,cleanup,deploy}.yml@<40-char-sha>`, matching `cloud-ai-fde/bryankelly-gecx-agent-blueprint`. They pass `make push` and `make eval` as the push and simulation commands. |

Whichever mode you use, check that your release workflow runs `make gate3` after `make bench-full`. This kit's own `deploy-staging.yml` does; workflows generated earlier may not.

---

## 3. What Each Workflow File in `.github/workflows/` Does

All workflows call the exact same [`Makefile`](../Makefile) targets you run locally, guaranteeing 100% parity between your terminal and GitHub Actions:

### 1. `.github/workflows/pr-validation.yml` (Runs on every Pull Request)
- **Job 1 — Gate 0 offline CI (`make ci`):**
  - Checks out the code, installs Python and `uv`, and runs `make install`.
  - Runs `make ci` (`bundle-check`, `overfit-check` including `NUMBER_IN_PROMPT` and `EVAL_VALUE_IN_FAKES`, `eval-contract` via `scripts/eval_contract.py` when `bench/dev/evaluations` exists, `cxas lint` with 0 errors and 0 warnings not listed in `lint_waivers.json`, `pytest` with $\ge 80\%$ coverage per file, `verify_mutations.py`, and local eval schema validation; it fails if `cxas` is missing), or `make selftest` if the repo is the un-scaffolded starter template.
  - Writes a markdown summary table to the GitHub Actions job summary.
- **Job 2 — PR preview app and targeted smoke (Gate 1 first):**
  - Runs after Job 1 passes, when `GCP_WIF_PROVIDER` and `GCP_WIF_SERVICE_ACCOUNT` are configured and the agent app exists.
  - Authenticates keyless to Google Cloud via `google-github-actions/auth@v2`.
  - Runs `make preview-up PR=<number>` to create or update an isolated temporary CES agent (`<agent>-pr-<number>`); it also records the pushed commit in `history/last_push.json` for that app.
  - Runs the targeted smoke first (`make bench-smoke APP=<preview app> TARGETS=...`, 3 repeats; the targets come from the workflow input or the `SMOKE_TARGETS` repository variable), and only then, if you picked the `unstable` or `full` tier when starting the workflow by hand, `make bench-unstable` or `make bench-full` on the preview app.

### 2. `.github/workflows/pr-cleanup.yml` (Runs when a Pull Request is closed or merged)
- Automatically runs `make preview-down PR=<number>` (`cxas delete`) to delete the temporary `<agent>-pr-<number>` preview app so old PR apps do not clutter your Google Cloud project.

### 3. `.github/workflows/deploy-dev.yml` (Runs on push to `main`, `epic/**`, `hillclimb`, `build-*`)
- **Job 1 — offline CI:** Runs `make install` and `make ci` (or `make selftest` on the starter template) on every push, so you always get an immediate green/red check in GitHub Actions even before cloud secrets are configured.
- **Job 2 — push to staging and climb the ladder:** Runs on pushes to `main` or when started by hand, if `GCP_WIF_PROVIDER` and `GCP_WIF_SERVICE_ACCOUNT` are configured and the app exists. It runs `make push ENV=staging`, then the targeted smoke (`make bench-smoke ENV=staging TARGETS=...`), and, depending on the tier you pick, `make bench-unstable` or `make bench-full`.

### 4. `.github/workflows/deploy-staging.yml` (Manual Release Button — `workflow_dispatch`)
- Triggered manually from the GitHub **Actions** tab when promoting a tested release. Runs `make ci`, pushes a versioned snapshot to staging (`make push ENV=staging`), runs Gate 1 (`make smoke-impact` when an impact map exists, otherwise `make bench-smoke` with the `TARGETS` you give), then Gate 3: `make bench-full ENV=staging` followed by `make gate3`, which fails the release unless `strict 3/3 >= 90%` AND `100%` majority `>=2/3` hold with `0` tool runtime errors on a complete, single-commit run.

The kit has no nightly or live-deploy workflow; add one if you need it.

---

## 4. Local Pre-Push Verification

Before pushing a branch or running cloud evaluations, run the offline checks, commit, and climb the ladder locally:
```bash
make ci                       # Offline Gate 0 (bundle-check, overfit-check, eval-contract, cxas lint with lint_waivers.json, pytest, verify_mutations)
make impact                   # List evaluation IDs impacted by your change, plus a Verdict: line
git add -A && git commit -m "<area>: <what changed>"   # cloud steps refuse uncommitted cxas_app/, lib/ or evals/
make push ENV=staging         # runs make preflight first (ADC identity, quota project, CES permissions; alias: make auth-check)
make smoke-impact ENV=staging # Gate 1: 3x cloud smoke on the impacted evaluations of the pushed code
make bench-full ENV=staging && make gate3   # Gate 3; from the second full run on, only after the smoke passes
```
`make bench-full` rebuilds `history/eval_impact_map.json` after every full run, so the smoke requirement applies from the second full run on; the first full run on a fresh repo or CI runner (where that gitignored map doesn't exist yet) is the bootstrap exception. `make preflight` runs automatically before every cloud target (`SKIP_PREFLIGHT=1` skips it). ADC refreshes its own access tokens; the failure to watch for is the login itself expiring, which preflight catches. On google.com projects, scripts must use ADC: plain `gcloud auth print-access-token` user tokens are rejected (`401 ACCESS_TOKEN_TYPE_UNSUPPORTED`).

To test all infrastructure, contract, impact, and bootstrap utilities in the starter kit:
```bash
make selftest
```
