# GECX Agent Starter Kit

Drop-in starter kit, reusable tools, and engineering playbook for a developer or coding agent (Antigravity, Jetski, Claude Code, Gemini Command-Line Interface (**CLI**), …) to build, evaluate, and ship a **Google Customer Experience Agent Studio** (**CXAS**, also called **Customer Engagement Suite** (**CES**) or **Gemini Enterprise for Customer Experience** (**GECX**)) conversational agent for chat and voice **from a Product Requirements Document (PRD)**.

---

## Fast-Track Kickstart: PRD to First Cloud Smoke

Instead of spending days on upfront document waterfalls before running a single cloud conversation, use the **Fast-Track Kickstart**:

```bash
# 1. Clone the starter kit into a fresh repo for your agent
git clone git@github.com:snehsm007/gecx-agent-starter.git my-agent
cd my-agent && rm -rf .git && git init

# 2. Drop in your Product Requirements Document (SAMPLE_PRD.md / prd.md is the Telco Voice Central practice PRD) and install dependencies into .venv
cp SAMPLE_PRD.md prd.md   # or: cp <your-prd.md> prd.md
make install       # uv sync from pyproject.toml (cxas-scrapi, google-cloud-ces, pytest); pip fallback without uv
uv run cxas init   # optional: installs SCRAPI's built-in cxas-* skills under .agents/skills/; keep this repo's AGENTS.md

# 3. Scaffold the agent (router + specialist, six tools), shared lib/, unit tests, evals/, docs/, environments/staging.mk and CI in one command
make kickstart NAME=my-agent PRD=prd.md PROJECT_ID=<gcp-project> LOCATION=us

# 4. Run Gate 0 offline checks (bundler, eval contract, cxas lint, pytest >=80% coverage, mutation checks).
#    It fails on any cxas lint warning not listed in lint_waivers.json, and when cxas is not installed.
make ci

# 5. Fill in environments/staging.mk, commit (push refuses uncommitted agent code), then push the agent and its evals
#    to staging and run a 3-case cloud smoke test. `make preflight` checks your Google Cloud login,
#    quota project and permissions automatically before each cloud step (SKIP_PREFLIGHT=1 skips it).
git add -A && git commit -m "Scaffold agent"
make push ENV=staging
make push-evals ENV=staging
make bench-smoke ENV=staging TARGETS=eval_1,eval_2,eval_3

# 6. (Optional) Mask personal data in conversation logs with Cloud DLP, commit the app.json change, then push it
make setup-dlp ENV=staging && git commit -am "Turn on Cloud DLP log redaction" && make push ENV=staging

# 7. (Optional) Provision Google Cloud WIF + Service Account, GitHub Secrets/Variables, and CI/CD workflows
make bootstrap
```

When working with a coding agent, tell it:
> **"Read `AGENTS.md` and run the Fast-Track Kickstart from `prd.md`: present the single-turn decision table with recommended defaults, run `make kickstart` and `make ci`, push to staging, and run a 3-case cloud smoke test."**

---

## What's Inside

```
AGENTS.md                              # Hard rules, Fast-Track Kickstart, Confidence Ladder & Hill-Climb rules
.github/
  PULL_REQUEST_TEMPLATE.md             # PR template with 5-Part Engineering Rationale, coverage & cloud eval tables
  dependabot.yml                       # Weekly GitHub Actions SHA update schedule
  workflows/
    pr-validation.yml                  # PR Gate: offline `make ci` + ephemeral `<agent>-pr-<n>` preview & cloud evals
    pr-cleanup.yml                     # PR Close/Merge: deletes the temporary `<agent>-pr-<n>` preview app
    deploy-dev.yml                     # Push to main/epic/hillclimb: offline `make ci`; on main, staging push + smoke/unstable/full runs
    deploy-staging.yml                 # Manual release workflow (`workflow_dispatch`): push, smoke, full run, then `make gate3`
bootstrap/
  bootstrap.py                         # Interactive wizard: GCP Service Account + WIF + GitHub Secrets + workflows
  README.md                            # Step-by-step guide to running `make bootstrap` (`standalone` vs `gecx-actions`)
docs/
  BEST_PRACTICES.md                    # Plain-English guide to every architectural, judge, and eval lesson
  WHY_IT_TOOK_SO_LONG.md               # Retrospective: Part I (earlier builds, 5 bottlenecks) & Part II (telco-rebuild, same-commit numbers)
  DESIGN_RULES.md                      # What goes where: agents, prompts, tools, state, callbacks (31 rules with evidence)
  INSTRUCTION_STYLE.md                 # Structured XML instruction layout (<role>, <persona>, <constraints>, <taskflow>)
  git-workflow.md                      # Git branching strategy (Mode A: worktree fix/* loop; Mode B: epic/feat/sync streams)
  ci-cd.md                             # CI/CD setup, Workload Identity Federation (WIF), and workflow reference
Makefile                               # Single entry point: install, kickstart, bootstrap, ci, eval-contract, preflight, setup-dlp, impact, push, smoke-impact, bench-*, gate3, eval/gate, dashboard
pyproject.toml                         # Pinned dependencies (cxas-scrapi, google-cloud-ces, pytest) for `make install`
environments/example.mk                # Per-app settings loaded by `make <target> ENV=<name>` (including TEMPERATURE ?= 1.0)
gate_thresholds.json                   # Gate bars (strict_pass_rate 0.90, majority_pass_rate 1.00) and model lock: fill in measured_on_model and judge_model
lint_waivers.json                      # cxas lint warning rule ID -> reason (for example T014); `make ci` fails on any other warning
scripts/
  kickstart.py                         # Generates cxas_app/, lib/{fakes,replies,services,speech}.py, tests/, docs/
  inspect_evals.py                     # Pre-flight reconnaissance on public/exported evals (languages, fact-less callers, rubrics)
  eval_contract.py                     # Verifies lib/fakes.py credentials & identifiers against the visible tests in bench/dev/evaluations/ (`make eval-contract`)
  preflight.py                         # `make preflight`: ADC identity, quota project and CES permissions before any cloud step
  setup_dlp.py                         # `make setup-dlp`: Cloud DLP inspect/deidentify templates + loggingSettings.redactionConfig
  lint_check.py                        # Runs `cxas lint --json` and applies lint_waivers.json (used by `make lint` and `make ci`)
  impact.py                            # Static git-diff -> tool/function -> evaluation ID impact analyzer and smoke gate (`make impact`, `make smoke-impact`)
  run_evals.py                         # Gate 0 validation (--mode local), --push evals to the app, cloud runs -> history/runs.jsonl
  run_bench.py                         # Server-side evaluation runner: evaluationRuns, polling, Gate 1 verdict, reports, version guard
  bench_summary.py                     # Keep/Undo verdict calculator and Gate 3 check (`make gate3`), reporting Strict 3/3 | Majority >=2/3 | Individual
  build_dashboard.py                   # 5-tab static HTML Hill-Climb & Telemetry dashboard generator
  verify_mutations.py                  # Gate 0 offline mutation & tool-breakage verifier
  publish_zipline.py                   # Publishes dashboard/ to Zipline
suite/
  grader.py                            # Deterministic code checks on transcripts (overrides the LLM judge)
  gate.py                              # PASS / FAIL / INCONCLUSIVE release gate calculator (enforces strict 3/3 via strict_pass_rate)
  bundle.py                            # Dependency-aware AST bundler inlining lib/*.py into single-file tools/callbacks
  overfit_check.py                     # Anti-overfitting & prompt-bloat scanner (NUMBER_IN_PROMPT, EVAL_VALUE_IN_FAKES, banned literals, >=12k char cap)
  coverage_check.py                    # Enforces >=80% coverage per Python file + 1 test file per code file
  preview_app.py                       # Per-Pull-Request throwaway preview app helper
  cloud_log.py                         # Appends every cloud call to docs/cloud-log.md (`cloud_log.py exec -- <cmd>`)
  regression.py                        # Merges evals/regression/ cases (from real failures) into the suite
  tool_tests.py                        # Offline tool tests from evals/tool_tests/*.yaml against lib/ fakes
.agents/skills/gecx-agent-playbook/
  SKILL.md                             # Step-by-step procedure, Confidence Ladder, and 7 Root-Cause Clusters
  references/01..14-*.md               # Phase-by-phase deep references & fast-kickstart patterns
  assets/                              # Reusable templates and copies of the root scripts/suite/Makefile (`make skill-assets` refreshes them; `make skill-assets-check` in `make selftest` fails on drift)
```

---

## The Confidence Ladder (How Changes Are Verified)

Every change climbs five gates in order and stops at the first gate it fails. The `Makefile` enforces the cloud order: commit, `make push`, `make smoke-impact`, then `make bench-full`. `make bench-full` rebuilds `history/eval_impact_map.json` after every full run, so the smoke requirement applies from the second full run on; the first full run on a fresh repo or CI runner is the bootstrap exception.

| Gate | Command | Runtime | Purpose |
|---|---|---|---|
| **Gate 0: Offline Proof** | `make ci` | Offline, no cloud cost | `bundle-check`, `overfit-check` (`NUMBER_IN_PROMPT`, `EVAL_VALUE_IN_FAKES`), `eval-contract` (`scripts/eval_contract.py`), `cxas lint` (0 errors, and 0 warnings not listed in `lint_waivers.json`; fails if `cxas` is missing), `pytest` (≥80% per-file coverage), suite self-tests, and `verify_mutations.py` (run `make voice-audit` separately for voice readiness). |
| **Gate 1: Cloud Smoke** | commit, `make impact`, `make push ENV=staging`, `make smoke-impact ENV=staging` | Median about 6 min across 33 `telco-rebuild` smoke runs | `make preflight` runs first automatically (login identity, quota project, permissions). `make impact` maps changed code to impacted evaluations and prints a `Verdict:` line. `make smoke-impact` runs them × 3 on the pushed code and refuses unless the current code (its source fingerprint) is the pushed code (`3/3` strict with `0` tool errors required; a `FULL` verdict sends you to Gate 3). |
| **Gate 2: Unstable Set** | `make bench-unstable ENV=staging` | Longer than a smoke (5 repeats) | Runs `evals/unstable_set.txt` × 5 repeats; judge it with `make bench-compare` (keep a fix only if the targets reach `3/3` and nothing else regresses). |
| **Gate 3: Full Suite** | `make bench-full ENV=staging`, then `make gate3` | 11–29 min in 15 of 16 logged `telco-rebuild` full runs | Runs all visible evaluations × 3 before merging to `main`. From the second full run on, it needs a passing smoke for the pushed code (or a `FULL` verdict; override `SKIP_SMOKE_GATE=1 REASON="..."`). Requires **both `strict 3/3 >= 90%` (`45/50`) AND `100%` majority (`>=2/3`, zero `0/3` or `1/3` evaluations)** with `0` tool errors on a complete, single-commit run, printing `strict 3/3 \| majority >=2/3 \| individual`. |
| **Gate 4: Holdout & Audio** | `make bench-holdout ENV=staging` and `make eval ENV=staging LAYERS=audio_golden,audio_sim PRIORITY=P0 MODALITY=audio RUN_ID=<id>` then `make gate RUN_ID=<id>` | Release only | Runs the hidden holdout set (`bench-holdout/`) × 3 once. The holdout must run on the same code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3; a docs-only or history-only commit in between is fine (otherwise it needs `HOLDOUT_REASON="..."`). It also runs naturalness-graded audio simulations + noise variants; `suite/gate.py` turns `history/runs.jsonl` into PASS / FAIL / INCONCLUSIVE and enforces the same strict 3/3 floor. |

Visible and holdout scores are only added together when both ran on the same code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`). Runtimes come from the `telco-rebuild` cloud log (first to last logged call per run); one full run there took 50 minutes.

---

## Self-Test the Starter Kit

Verify all suite and tooling scripts offline (every check prints `OK`):

```bash
make selftest
```

`make selftest` also runs `make skill-assets-check`, which fails if the copies under `.agents/skills/gecx-agent-playbook/assets/` drift from the root files.

Credits: the Makefile-first workflow, `lib/` bundling, fakes behind service interfaces, per-file coverage, and per-PR preview apps build upon `cloud-ai-fde/bryankelly-gecx-agent-blueprint` and battle-tested lessons from production GECX deployments.
