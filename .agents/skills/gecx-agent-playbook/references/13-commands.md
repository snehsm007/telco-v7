# 13 Makefile targets and raw `cxas` commands

Always run tasks through `make <target>` day to day so local runs and Continuous Integration (**CI**) execute the exact same commands. Use the raw `uv run cxas ...` commands below when adding or debugging a Makefile target. Run `uv run cxas <command> --help` before using an unfamiliar flag, and `make help` for the full target list.
`<APP>` = `projects/<PROJECT_ID>/locations/<LOCATION>/apps/<APP_ID>`.

---

## 1. Fast-Track Kickstart, Bundling & Offline Gate 0 (`make ci`)
```bash
# Scaffold cxas_app/ (router + one specialist, six tools, one speech_hygiene after-model callback), lib/{fakes,replies,services,speech}.py, tests/, evals/, docs/
make kickstart NAME=<agent-name> PRD=prd.md
python3 scripts/kickstart.py --prd prd.md --agent-name <agent-name>

# Scan exported bootcamp/public evals or local evals/ for languages, fact-less callers, and verbatim rubrics
python3 scripts/inspect_evals.py --evals-dir evals/

# Check that lib/fakes.py accepts every first-try caller credential and resolves every caller phone/account ID in the visible evals (Rule 23)
make eval-contract               # runs: python3 scripts/eval_contract.py --evals-dir bench/dev/evaluations --fakes lib/fakes.py (the same step make ci runs)

# Inline shared lib/*.py symbols into standalone tool and callback files
make bundle                      # runs: python3 suite/bundle.py --app cxas_app --lib lib
make bundle-check                # runs: python3 suite/bundle.py --check --app cxas_app --lib lib (includes compile+exec check)
make overfit-check               # runs: python3 suite/overfit_check.py --app cxas_app --lib lib --prd prd.md --eval-dir evals --bench-dir bench/dev

# Run Gate 0 offline verification (seconds, free)
make ci                          # runs: bundle-check + overfit-check + eval contract (when bench/dev/evaluations exists) + cxas lint via scripts/lint_check.py + pytest (>=80% per-file coverage) + grader/gate self-tests + verify_mutations + eval YAML validation
                                 # fails if cxas is missing, on any cxas lint error, and on any lint warning not listed in lint_waivers.json (rule ID -> reason)
make lint                        # runs: bundle-check + python3 scripts/lint_check.py (cxas lint --json, then applies lint_waivers.json; the kit waives T014)
make test                        # runs: pytest + python3 suite/coverage_check.py
make selftest                    # runs --self-test across all suite/*.py and scripts/*.py utilities, plus make skill-assets-check
python3 scripts/verify_mutations.py  # injects deliberate faults into tools/guards and verifies pytest catches 100%

# Keep the playbook's asset copies in sync with the kit root (scripts/, suite/, Makefile, gate_thresholds.json, environments/example.mk, lint_waivers.json)
make skill-assets                # copies the root files into .agents/skills/gecx-agent-playbook/assets/
make skill-assets-check          # fails when the copies drift (part of make selftest)
```

---

## 2. Linting & Gemini Composite V1 Voice Audit
```bash
# Schema and structure lint (must be 0 errors; warnings must be waived in lint_waivers.json with a reason)
uv run cxas lint --app-dir cxas_app

# Gemini Composite V1 voice readiness: app.json checks (gemini-composite-v1, barge-in, noiseSuppressionLevel HIGH),
# then the voice optimizer's audit when the cxas-composite-voice-agent-optimizer skill is installed
make voice-audit
python3 ~/.gemini/config/skills/cxas-composite-voice-agent-optimizer/scripts/audit_agent.py --workspace cxas_app --report --json

# AI instruction lint (advisory)
make llm-lint
uv run cxas llm-lint --agent-dir cxas_app/agents/<agent>

# Optional stricter XML <step><trigger><action> prompt checker (report-only)
python3 <danyals-repo>/linter/cxas_prompt_linter.py cxas_app
```
Note: `cxas lint` passing does not guarantee `cxas push` will accept every resource reference (e.g. `childAgents` must use directory names, not display names). Push to `-staging` early on Day 1.

---

## 3. Apps, Pushes, Auth Preflight, Cloud DLP & Version Guards
```bash
# Preflight: runs automatically before push, push-evals, setup-dlp, smoke-impact, bench-smoke, bench-unstable, bench-full and bench-holdout
make preflight                   # alias: make auth-check; runs: python3 scripts/preflight.py --project-id <PROJECT_ID>
                                 # mints an ADC token, prints the ADC identity and quota project (warns if it differs from the target project),
                                 # checks ces.apps.get, ces.apps.update, ces.apps.runEvaluation and ces.evaluations.create (fails with the missing ones),
                                 # and warns if gcertstatus reports an expired certificate. SKIP_PREFLIGHT=1 skips it.

# Push to staging and create an immutable, restorable version git-<sha7>
make push ENV=staging            # ENV loads environments/staging.mk (PROJECT_ID, LOCATION, APP_ID, AGENT_NAME)
                                 # refuses uncommitted changes in cxas_app/, lib/ or evals/ ("commit first"); runs bundle-check and preflight;
                                 # writes history/last_push.json (commit, source_fingerprint, app, version, pushed_at). Not blocked by the smoke gate.
uv run cxas push --app-dir cxas_app --to <APP> --create-version --version-name git-<sha7>

# Create or update the evaluations themselves (goldens, simulations, probes from evals/*.yaml)
make push-evals ENV=staging      # runs: python3 scripts/run_evals.py --push --app <APP> --eval-dir evals  (SCRAPI Evaluations.update_evaluation)
uv run cxas push-eval --app-name <APP> --file evals/goldens/<file>.yaml   # goldens only, SCRAPI `conversations:` format

# Cloud DLP log redaction (templates in the app's location + loggingSettings.redactionConfig in cxas_app/app.json); commit, then make push deploys it
make setup-dlp ENV=staging       # runs scripts/setup_dlp.py for the ENV's project, location and agent name, and updates cxas_app/app.json
make setup-dlp ENV=staging DRY_RUN=1                                                          # print the plan only
python3 scripts/setup_dlp.py --project-id <P> --location <L> --agent-name <agent> --app-dir cxas_app --apply-app-json
python3 scripts/setup_dlp.py --self-test                                                      # offline check

# Create / delete per-PR throwaway preview apps
make preview-up PR=12
make preview-down PR=12
uv run cxas create --project-id <P> --location <L> "<name>-staging"
uv run cxas pull <APP> --target-dir pulled [--version-id <v>] --overwrite
uv run cxas versions create --app-name <APP> --display-name <name>
uv run cxas versions list --app-name <APP>
uv run cxas versions compare --app-name <APP> --source <v1> --target <v2>
```
- **Temperature:** `make kickstart` writes `modelSettings.temperature` (default `1.0` from `TEMPERATURE ?= 1.0`) into `cxas_app/app.json`; `make push` deploys whatever `app.json` says. Keep `1.0`: it is the owner's decision, voice-audit rule A010 requires it, and 0.2 made no measurable difference.
- **Overwriting push warning:** `cxas push` resets app-level settings (model, audio recording bucket, noise suppression, logging) unless they are configured in `app.json`, and deletes platform-stored evaluation runs. Always push **first**, then run evaluations.
- **Concurrent push guard:** Never push to `-staging` while an evaluation benchmark is running. The evaluation runners read `get_app().update_time` before and after the run and stop if another process modified the app mid-run.

---

## 4. The Confidence Ladder: Impact Smoke, Unstable Set, Full Benchmark, Holdout & Comparison
```bash
# Print the plan (selected evals, repeats) without cloud calls
make bench-dry ENV=staging TARGETS=VE-01
python3 scripts/run_bench.py --app <APP> --evals VE-01 --dry-run

# Gate 1: push the committed candidate, then smoke exactly what is deployed (must score strict 3/3 on every impacted eval)
make impact                      # runs: python3 scripts/impact.py [--base <sha>]  (diff since the last clean full run; BASE=<sha> overrides)
                                 # ends with a "Verdict:" line; FULL when global_instruction.txt, app.json, lib/speech.py, lib/replies.py,
                                 # a shared lib/services.py helper or the shared login/fake-account code changed, or every eval is impacted
make push ENV=staging
make smoke-impact ENV=staging    # refuses while cxas_app/, lib/ or evals/ have uncommitted changes ("commit, then make push") and unless
                                 # history/last_push.json matches the current source fingerprint ("push this commit first: make push");
                                 # runs the impacted evals x 3 and records the verdict (history/last_impact.json, history/impact_gate.log);
                                 # 0 impacted evals counts as a pass; exits 2 with "run make bench-full" when the verdict is FULL
make bench-smoke ENV=staging TARGETS=VE-01,VE-02   # ad-hoc smoke of named evals x 3 (for example the first smoke on a new app)
python3 scripts/run_evals.py --app <APP> --smoke --targets VE-01,VE-02 --repeats 3

# Gate 2: Unstable Set Measurement (evals/unstable_set.txt x 5 repeats)
make bench-unstable ENV=staging
python3 scripts/run_evals.py --app <APP> --unstable --repeats 5 --label unstable-<sha7>   # report: bench/runs/unstable-<sha7>.json

# Gate 3: Full Visible Suite Merge Gate (all visible evals x 3 repeats)
make bench-full ENV=staging      # refuses on the holdout folder, while the source folders have uncommitted changes, and unless the deployed
                                 # fingerprint matches. Before the first full run it runs in bootstrap mode (no smoke gate); after every full
                                 # run it rebuilds history/eval_impact_map.json, so from the second full run on it needs one of: impact verdict
                                 # FULL, no source change since the last full run, or a passing smoke-impact for this fingerprint (0 impacted = pass).
                                 # Override: SKIP_SMOKE_GATE=1 REASON="..." (logged to history/impact_gate.log; SKIP_IMPACT=1 is an alias).
                                 # Writes history/bench/full-<sha7>.json and prints the Gate 3 verdict.
make bench-record REPORT=bench/runs/full-<sha7>.json   # manual: summarise a report into history/bench/ for the dashboard (no composite runs!)
make gate3                       # runs: python3 scripts/bench_summary.py --gate3 <report>; REPORT=... picks the file, else it reads
                                 # history/bench/full-<HEAD sha7>.json, or the newest full-*.json with the same source fingerprint as HEAD
                                 # exit 0 only if strict 3/3 >= strict_pass_rate (0.90), majority = 100%, 0 tool errors, is_full_run is true,
                                 # and the run is complete (every eval scored on all runs_per_eval tries, at least 3)

# Gate 4: Hidden Holdout & Audio Release Gate (Rule 19). Always use the make target; it carries the guard.
make bench-holdout ENV=staging   # the holdout must run on the same code (same source fingerprint of cxas_app/, lib/ and evals/) as a full
                                 # visible run that passed Gate 3; a docs-only or history-only commit in between is fine.
                                 # Refuses while the source folders have uncommitted changes or the deployed fingerprint doesn't match.
                                 # Pairs with history/bench/full-<HEAD sha7>.json, or else the newest full-*.json with the same source
                                 # fingerprint as HEAD; prints the pairing and logs it to history/impact_gate.log. Refuses without such a run,
                                 # or when it did not pass Gate 3 unless HOLDOUT_REASON="..." is given (logged to history/holdout_audit.log).
                                 # Re-running the holdout on a new commit also needs HOLDOUT_REASON. Never use bench-full BENCH_DIR=bench-holdout.

# Compare two benchmark runs across strict 3/3 | majority >=2/3 | individual
make bench-compare FROM=history/bench/before.json TO=history/bench/after.json
python3 scripts/bench_summary.py --before history/bench/before.json --after history/bench/after.json

# Run Audio Simulations (Phase 8, after text gate is green)
make eval ENV=staging LAYERS=audio_golden,audio_sim PRIORITY=P0 MODALITY=audio RUNS=1 RUN_ID=audio-<sha7>
python3 scripts/run_evals.py --mode staging --app <APP> --modality audio --layers audio_sim --repeats 1

# CI-style eval + Release Gate on history/runs.jsonl (one record per test x repeat)
make eval ENV=staging PRIORITY=P0 RUNS=3 RUN_ID=<id>   # TARGETS=... or LAYERS=golden,sim,probe
make gate RUN_ID=<id>                                  # suite/gate.py: strict 3/3 rate from strict_pass_rate + majority floors; exit 0 PASS / 1 FAIL / 3 INCONCLUSIVE
make smoke ENV=live RUN_ID=smoke-<sha7>                # P0 probes x 1 after a deploy
```

---

## 5. Telemetry, Trace Triage, Local Replay & Hill-Climb Dashboard
```bash
# Categorize one conversation's failure
make trace-triage ENV=staging CONV=<conversation-id>
uv run cxas trace triage <CONV_ID> --app-name <APP> --app-dir cxas_app
# Run-level triage (TOOL_MISSING, EXPECTATION_FAIL, HALLUCINATION, SCORES_PASS_BUT_FAIL) with SCRAPI's cxas-agent-foundry skill
uv run python .agents/skills/cxas-agent-foundry/scripts/triage-results.py --app-name <APP> --run-id <id>

# Replay a failed cloud conversation locally against your current code and diff tool/callback outputs
make trace-replay ENV=staging CONV=<conversation-id>
uv run cxas trace replay <CONV_ID> --app-name <APP> --app-dir cxas_app   # diff is on by default (--no-diff to skip)

# Search and inspect conversation traces
make inspect Q="text"
uv run cxas trace search "<text>" --app-name <APP> --match all --snippets
uv run cxas trace get <CONV_ID> --app-name <APP>
uv run cxas trace triage <CONV_ID> --app-name <APP>

# Interactive terminal chat with the agent (also the place to check Cloud DLP redaction, which evals skip)
make chat ENV=staging
uv run cxas run-session text <APP>

# Render the 5-tab static HTML Hill-Climb & Telemetry Dashboard and publish it
make dashboard                   # runs: python3 scripts/build_dashboard.py --bench-dir bench --app-dir cxas_app --app <APP> --title <agent>  -> dashboard/
make publish-dashboard ZIPLINE_PROJECT=<p> ZIPLINE_ASSET=<a>   # runs: python3 scripts/publish_zipline.py --project <p> --asset <a> --dir dashboard
```
Note: Always use `gcloud storage cp` rather than legacy `gsutil cp` when uploading dashboards or inspecting audio artifacts. Scripts authenticate with Application Default Credentials (**ADC**); on google.com projects, plain `gcloud auth print-access-token` user tokens are rejected with 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED`.
