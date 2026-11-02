# 08 CI/CD: the pipeline, the gate, and how to read a run

**CI** (continuous integration) runs checks on every change. **CD**
(continuous delivery) ships the change when the checks pass. The **gate** is
the rule that decides pass / fail.

## Quick Setup (`make bootstrap`, `docs/ci-cd.md`, `docs/git-workflow.md`)
Run `make bootstrap` (`python3 bootstrap/bootstrap.py --target-dir .`) to automatically provision a repository-locked Google Cloud Service Account + Workload Identity Federation (WIF), configure GitHub Environments/Variables/Secrets via `gh`, and generate `.github/workflows/{pr-validation,pr-cleanup,deploy-dev,deploy-staging}.yml` + `.github/PULL_REQUEST_TEMPLATE.md` (choosing `standalone` mode for personal repos and `gecx-actions` mode for `cloud-ai-fde/*` org repos). See `docs/ci-cd.md` and `docs/git-workflow.md` for full guides.

## Pipeline (`pr-validation.yml`, `pr-cleanup.yml`, `deploy-dev.yml`, `deploy-staging.yml`; every step is a `make` target)
| When | What runs | Blocks? |
|---|---|---|
| Before commit | `make ci`: stale-bundle check, `overfit-check`, the eval contract (`make eval-contract`, when `bench/dev/evaluations` exists), `cxas lint` through `scripts/lint_check.py` (fails if `cxas` is missing, on lint errors, and on warnings not waived in `lint_waivers.json`), pytest + per-file coverage, suite self-tests, `verify_mutations.py` | Yes, locally |
| Automatically before `push`, `push-evals`, `setup-dlp`, `smoke-impact`, `bench-smoke`, `bench-unstable`, `bench-full`, `bench-holdout` | `make preflight` (`scripts/preflight.py`; alias `make auth-check`): mints an Application Default Credentials (ADC) token, prints the ADC identity and quota project (warns when the quota project differs from the target project), checks `ces.apps.get`, `ces.apps.update`, `ces.apps.runEvaluation` and `ces.evaluations.create` on the project and fails with the missing ones, and warns if `gcertstatus` reports an expired certificate. `SKIP_PREFLIGHT=1` skips it | Yes |
| Every PR (`pr-validation.yml`) | `make ci` → `make preview-up PR=<n>` (a throwaway app `<agent>-pr-<n>`, created or updated; it writes `history/last_push.json` for that app) → `make eval` (tool + callback tests, goldens, **every P0 sim and probe**, safety + escalation, 3 repeats, text) → `make gate` | Yes |
| PR closed (`pr-cleanup.yml`) | `make preview-down PR=<n>` deletes the throwaway app | No |
| Push to main (`deploy-dev.yml`) | `make ci` → `make push ENV=staging` → same evals → `make gate` | Yes |
| By hand (`deploy-staging.yml`, Actions tab → Run workflow) | `make ci` → `make push ENV=staging` → Gate 1 `make smoke-impact` (or `make bench-smoke TARGETS=…` when there is no impact map yet) → Gate 3 `make bench-full` → `make gate3` | Yes |
| Nightly (no workflow; run by hand) | Full text suite ×5, audio goldens, 3-5 P0 audio sims, judge calibration re-grade | No |
| Release | Holdout set (`make bench-holdout ENV=staging`; the holdout must run on the same code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3, and a docs-only or history-only commit in between is fine; `HOLDOUT_REASON` is the logged exception), full audio suite, model A/B if the model changed | Human sign-off |

ADC refreshes its own access tokens; what expires is the login itself, which stalled unattended runs for about 13 hours in the `telco-rebuild` V2 hill-climb. Preflight catches that before a run starts. On google.com projects, scripts must use ADC: plain `gcloud auth print-access-token` user tokens are rejected by certificate-based access with 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED`.

## Gate rule (implemented by `scripts/bench_summary.py --gate3` for full runs & `suite/gate.py` for CI runs)
1. **Gate 3 bar (`make gate3`, visible dev suite):** a full visible benchmark run (`make bench-full`, which writes `history/bench/full-<sha7>.json`) passes Gate 3 only when strict `3/3 >= 90%` (`strict_pass_rate: 0.90` in `gate_thresholds.json`, e.g., `>= 45/50` evals passing all `3/3` repeats) **and** `100%` majority (`>= 2/3`, `majority_pass_rate: 1.00`, `50/50`) pass with **0 tool errors**, in a single unsplit, single-commit, complete run (`is_full_run: true`; every evaluation scored on all its tries; no composite `full-*` records). `make gate3` exits 1 otherwise, including for an incomplete run; without `REPORT=` it reads `history/bench/full-<HEAD sha7>.json`, or else the newest `full-*.json` whose commit has the same source fingerprint as HEAD. Always report `strict 3/3 | majority >=2/3 | individual` side-by-side, strict first.
2. Per test in `suite/gate.py` (`make gate RUN_ID=…`), evaluate both **strict (`3/3` decided repeats)**, whose rate must reach `strict_pass_rate`, and **strict majority of decided repeats (`>=2/3`)** against layer floors (infra errors don't count as decided; ties fail).
3. **Must-pass**: any P0 test that fails → gate FAIL, whatever the overall %.
4. **Floors per layer** from `gate_thresholds.json` (e.g. goldens 0.90, sims 0.80 majority + `strict_pass_rate: 0.90` strict on dev, tools 1.0, callbacks 1.0).
5. **INCONCLUSIVE** (exit 3) when infra errors are high enough to flip the result. Re-run; never treat it as PASS.
6. **Model check**: fail if the model being shipped differs from `measured_on_model` in the thresholds. While `measured_on_model` is still the template placeholder, `suite/gate.py` prints a message asking you to fill it in instead of failing. After a model change, re-measure floors and update the file in the same PR.
7. Every P0 requirement has a gated test. Don't gate a hand-picked subset.

Exit codes: `0` pass, `1` fail, `3` inconclusive.

## Keep the test apps honest
- **One throwaway app per PR** means two PRs never overwrite each other's app
  mid-run. Delete it when the PR closes. Watch the project's app count and
  quota; preview apps share the per-model token quota with staging.
- Staging is used only by `main` and nightly, under one CI concurrency group.
  Never push staging by hand during a run.
- `make push` creates a version before the evals, so results point to a
  restorable version, not a moving draft. It refuses uncommitted changes in
  `cxas_app/`, `lib/` or `evals/` and records what it deployed in
  `history/last_push.json`, so `make smoke-impact`, `make bench-full` and
  `make bench-holdout` can refuse to measure code that isn't deployed.
- An overwriting push resets app settings (model, audio, logging) and deletes
  platform eval runs. Keep settings in `cxas_app/app.json` (for example
  `loggingSettings.evaluationAudioRecordingConfig` and the Cloud DLP
  `loggingSettings.redactionConfig` that `make setup-dlp` writes) so every push
  deploys them; run evals after the push.
- Authenticate CI to Google Cloud with Workload Identity Federation (no JSON
  keys in secrets).

## How to read a run (in this order)
1. **Verdict and reasons** in the job summary: PASS / FAIL / INCONCLUSIVE, and
   which rule fired (must-pass, floor, model check, infra).
2. **Per-test table**: test, `REQ-n`, priority, repeat results
   (e.g. `✓✗✓`), label.
3. For each failure, open the record/transcript:
   - `[check:<name>] evidence` lines come from the code grader. Trust these
     first.
   - `[judge] NOT MET: <expectation> — <reason>` comes from the LLM judge.
   - `[infra] ...` is quota/timeouts.
4. **Read the transcript before the verdict** (so the verdict doesn't bias
   you), then label it `real` / `judge` / `infra`.
5. Transcript smells: double greeting, fields the tool doesn't return, leaked
   tags or "Say:", filler while a tool runs, action claimed without a tool
   call, facts with no source, ran out of turns.

A green run you can't explain is not a green run. If the summary doesn't say
which tests ran and how many repeats, fix the summary first.
