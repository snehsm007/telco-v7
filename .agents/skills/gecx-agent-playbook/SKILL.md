---
name: gecx-agent-playbook
description: >-
  Step-by-step playbook for building, testing and shipping a Google CX Agent
  Studio (CXAS / CES / GECX) conversational agent for chat and voice from a
  PRD: Fast-Track Kickstart (`scripts/kickstart.py`), numbering
  requirements, expanding them into test scenarios (CUJs), writing the design
  doc (TDD), writing SCRAPI evals (goldens, simulations, tool and callback
  tests), keeping the LLM judge honest across all 3 metrics (Expectations,
  User Goal, Hallucination), climbing the 5-Gate Confidence Ladder (push,
  impact smoke, full run, holdout on the same code), resolving the 7
  Root-Cause Clusters, eval-gated CI/CD, Cloud DLP log redaction, run history
  logging, and naturalness-graded audio simulation evals. Use when starting
  an agent from a PRD, adding scenarios, writing or reviewing a TDD or eval
  YAML, debugging a failing eval, setting up or reading CI gates, or planning
  voice testing. Don't use for Dialogflow CX flow/page agents or for LLM apps
  not built on CX Agent Studio.
---

# GECX Agent Playbook

Turns a **Product Requirements Document** (**PRD**) into a tested, evaluation-gated **Google Customer Experience Agent Studio** (**CXAS**, also called **Customer Engagement Suite** (**CES**) or **Gemini Enterprise for Customer Experience** (**GECX**)) conversational agent for chat and voice. `AGENTS.md` at the repository root holds the hard rules, Confidence Ladder, and approval gates. This skill holds the procedure. Load the reference for a phase when you start that phase; do not load them all up front.

---

## Fast-Track Kickstart (PRD to First Cloud Smoke Test)

Instead of spending days drafting dozens of pending micro-decisions before writing code, start every new agent with [14-fast-kickstart-and-eval-patterns](references/14-fast-kickstart-and-eval-patterns.md):
1. **Pre-Flight Eval Audit (`python3 scripts/inspect_evals.py --evals-dir <path>`):** Before writing tool code, scan the public evaluations (or PRD Critical User Journeys (**CUJs**)) for: (a) languages (`en-US`, `fr-CA`, `es-US`), (b) fact-less simulated callers lacking phone/One-Time Passcode (**OTP**)/Personal Identification Number (**PIN**)/card digits in `userFacts` (use the 3-attempt login ladder in `lib/fakes.py` per `docs/DESIGN_RULES.md` Rule 21, send a login code without asking the caller to confirm a number, accept caller-named card last-4, and never greet by `first_name`), (c) verbatim phrases or regex patterns checked by expectations, and (d) PRD-vs-evaluation friction points (verified offline by `make eval-contract`, Rule 23).
2. **Single-Turn Approval Table:** Batch all open PRD ambiguities into **one compact table** with sensible defaults: `gemini-composite-v1`; `temperature: 1.0` (final: it is the owner's decision and `make voice-audit` rule A010 requires it, and a 0.2 vs 1.0 test made no measurable difference); a router plus one specialist per PRD module; the 3-attempt login ladder in `lib/fakes.py`; flat typed session variables with `language` defaulting to `""`; union types (`str | int | float`) on tool parameters without `from __future__ import annotations` in tool wrappers (rule 32); tools that return money as a number plus a 2-decimal display string (rule 27), pre-ground Turn N+1 follow-up FAQ fields and localized status notes (rule 33), wrap sequential tool chains atomically (rule 34), and avoid open-ended `"up to full monthly rate"` simulator-baiting wording (rule 35); and only the `speech_hygiene` after-model callback with card-digit context guarding (see `docs/DESIGN_RULES.md` Rules 1–36).
3. **One-Command Scaffold (`make kickstart`):** Run `make kickstart NAME=<agent-name> PRD=prd.md` (it calls `scripts/kickstart.py --agent-name <agent-name> --prd prd.md`). It generates `cxas_app/` (a `router`, one `specialist`, six tools — `lookup_account`, `send_login_code`, `check_login_code`, `check_secret_pin`, `submit_request`, `handover_to_person` — and one `speech_hygiene` after-model callback on both agents), `lib/{fakes,replies,services,speech}.py`, `tests/`, `evals/` and `docs/`, with `make bundle` and `make ci` passing immediately. Every tool replies with `status`, `data`, `error_message` and `tracking_id`.
4. **Order of work:**
   - Commit the scaffold, push it to a **new** staging app (`make push ENV=staging`; it refuses uncommitted changes in `cxas_app/`, `lib/` or `evals/`), and run a 3-eval cloud smoke (`make bench-smoke ENV=staging TARGETS=<3 core evals>`, 3 repeats each). A preflight check runs automatically before every cloud target: it shows which Google account your Application Default Credentials (**ADC**) belong to and their quota project, and checks the four CES permissions that pushes and evaluations need.
   - Run `make bench-full ENV=staging` once for a baseline (before the first full run it runs in bootstrap mode, without the smoke gate), then `make gate3`. Sort the failures into the **7 Root-Cause Clusters** below.
   - Fix **one mechanism per candidate**, each in its own git worktree (`../<agent>-wt/fix/<slug>`): `make ci` → commit → `make push ENV=staging` → `make smoke-impact ENV=staging` (impacted evaluations × 3, strict `3/3`) → `make bench-full ENV=staging` → `make gate3`. Merge one candidate at a time and smoke again between merges.
   - Once Gate 3 passes, and the owner agrees, run the holdout (`make bench-holdout ENV=staging`): the holdout must run on the **same code** (same source fingerprint of `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3; a docs-only or history-only commit in between is fine. Then test by chat and voice (`make chat`) and build the HTML dashboard (`make dashboard`).
   - **Time:** no end-to-end duration for this order has been measured. The one measured hill-climb (`telco-rebuild` V2) took about 25 hours of wall clock for 16 full runs; about 7 hours went to 5 preventable regressions and about 13 hours to expired Google Cloud logins. The smoke gate and the automatic preflight exist to remove those two losses.
5. **Adjacent Bootcamp Skills:** Combine with `cxas-dfcx-migration` (`migrate.py` → `stage_1.py` → `stage_2.py` → `stage_3.py`) for Dialogflow CX (**DFCX**) → GECX migrations, `cxas-composite-voice-agent-optimizer` (`make voice-audit`) for voice readiness, and `cxas-loss-analysis` for clustering non-contained transcripts.

---

## Phase Map

| Phase | Do | Reference | Template / Script |
|---|---|---|---|
| **0 Fast Kickstart** | Batch PRD questions into 1 table, run `make kickstart` + `make ci`, commit, `make push ENV=staging` (preflight runs first), run a 3-eval smoke | [14-fast-kickstart-and-eval-patterns](references/14-fast-kickstart-and-eval-patterns.md) | `scripts/kickstart.py`, `Makefile` |
| **1 Requirements** | Number every PRD requirement `REQ-n`, set P0/P1/P2, list open questions and defaults, and list every field, allowed value and timeline the PRD fixes | [01-requirements](references/01-requirements.md) | `assets/requirements.md` |
| **2 Scenarios** | Expand each `REQ-n` across Critical User Journey (**CUJ**) scenario buckets, near-twins, and failure modes | [02-scenarios](references/02-scenarios.md) | `assets/scenarios.md` |
| **3 Design (TDD)** | Write the Technical Design Document (**TDD**): architecture, tool contracts, session variables, callbacks, routing, voice rules (follow `docs/DESIGN_RULES.md` Rules 1–31) | [03-tdd](references/03-tdd.md), [04-agent-design](references/04-agent-design.md) | `assets/tdd.md` |
| **4 Tests first** | Tool tests, callback tests, goldens, simulations, probes, contract tests for every PRD field, allowed value and timeline, fakes-invariants tests, grader, mutation check; 1 test file per code file | [05-evals](references/05-evals.md), [06-judge](references/06-judge.md) | `assets/evals/*`, `suite/*`, `scripts/eval_contract.py`, `scripts/verify_mutations.py` |
| **5 Build** | Shared code + 3-attempt login ladder fakes in `lib/`, `make bundle`, `make ci` green, `make voice-audit`, optional `make setup-dlp ENV=staging`, commit, `make push ENV=staging` | [04-agent-design](references/04-agent-design.md), [13-commands](references/13-commands.md) | `Makefile`, `suite/bundle.py` |
| **6-7 Evaluate + Hill-Climb** | Gate 0 (`make ci` + `make impact`) → Gate 1 (commit, `make push`, `make smoke-impact`) → Gate 2 (`bench-unstable`) → Gate 3 (`bench-full` + `make gate3`: strict `3/3` ≥ 90% first, then 100% majority) | [07-failure-loop](references/07-failure-loop.md), [14-fast-kickstart-and-eval-patterns](references/14-fast-kickstart-and-eval-patterns.md) | `scripts/impact.py`, `scripts/run_evals.py`, `scripts/bench_summary.py`, `assets/defects.md`, `assets/experiment_log.md` |
| **8 Audio** | After the text gate is green: run naturalness-graded audio simulations + noise-variant sims | [10-audio-evals](references/10-audio-evals.md) | `scripts/run_evals.py --modality audio` |
| **9 Ship & Dashboard** | Pull Request (**PR**) preview app gate → `main` staging gate → Gate 4 holdout on the same code as the passing Gate 3 run (`make bench-holdout`) → live version → smoke; render the 5-tab HTML dashboard | [08-ci-cd](references/08-ci-cd.md), [09-run-log](references/09-run-log.md) | `scripts/build_dashboard.py`, `make bootstrap` (writes `.github/workflows/`), `assets/gate_thresholds.json` |

Before writing any prompt, tool, callback, or evaluation, read [11-gotchas](references/11-gotchas.md) and [14-fast-kickstart-and-eval-patterns](references/14-fast-kickstart-and-eval-patterns.md). Every item there prevented or resolved a real stall in an earlier build. [12-sources](references/12-sources.md) lists upstream docs and tools; [13-commands](references/13-commands.md) lists the Makefile targets and raw `cxas` commands.

---

## The 5-Gate Confidence Ladder

Every code or instruction change climbs five verification gates in order and stops at the first gate it fails. Every bar is stated **strict `3/3` first** (all 3 tries pass), then majority (at least 2 of 3), then individual conversations (rule 31).
1. **Gate 0 (offline, free, seconds):** `make ci` — `bundle-check`, `overfit-check` (including `NUMBER_IN_PROMPT` and `EVAL_VALUE_IN_FAKES`), the eval contract (`make eval-contract`: `scripts/eval_contract.py` checks `bench/dev/evaluations` against `lib/fakes.py`, when that folder exists), `cxas lint` through `scripts/lint_check.py` (`make ci` fails if `cxas` is missing, on any lint error, and on any warning not listed in `lint_waivers.json` with a reason), `pytest` with ≥80% per-file coverage, suite self-tests and `verify_mutations.py` — plus `make voice-audit` and a local regression test on the failed conversation's recorded tool inputs and outputs.
2. **Gate 1 (push, then impact smoke):** `make impact`, commit, `make push ENV=staging`, then `make smoke-impact ENV=staging`.
   - `make impact` lists the evaluations touched by the change since the last clean full run (`BASE=<sha>` overrides) and prints a `Verdict:` line. The verdict is `FULL` when the change touches `global_instruction.txt`, `app.json`, `lib/speech.py`, `lib/replies.py`, a shared helper in `lib/services.py`, or the shared login/fake-account code, or when the impacted set covers every evaluation.
   - `make push` refuses if `cxas_app/`, `lib/` or `evals/` have uncommitted changes ("commit first"), runs `bundle-check` and preflight, creates version `git-<sha7>`, and writes `history/last_push.json` (commit, source fingerprint, app, version, time). The **source fingerprint** is a hash of the committed `cxas_app/`, `lib/` and `evals/` folders, so docs-only commits don't change it.
   - `make smoke-impact` refuses while those folders have uncommitted changes and unless the last push matches the current fingerprint ("push this commit first: make push"), runs the impacted evaluations × 3, and records the verdict for that fingerprint. Zero impacted evaluations counts as a pass. When the verdict is `FULL`, it exits 2 and tells you to run `make bench-full`.
   - Advance only when every impacted evaluation passes **strict `3/3`** with `0` tool errors.
3. **Gate 2 (unstable set):** `make bench-unstable ENV=staging` (5 repeats) + `make bench-compare FROM=before.json TO=after.json` (Keep/Undo with the Failure-Shape check).
4. **Gate 3 (full suite, merge gate):** `make bench-full ENV=staging` (3 repeats), then `make gate3`.
   - `make bench-full` refuses to run on the holdout folder ("use make bench-holdout"), while `cxas_app/`, `lib/` or `evals/` have uncommitted changes, and unless the deployed fingerprint matches. Before the first full run it runs in bootstrap mode, without the smoke gate. After every full run it rebuilds `history/eval_impact_map.json`, so from the second full run on it runs only if one of these holds: the impact verdict is `FULL`, no source change since the last full run, or a passing `make smoke-impact` (including one with zero impacted evaluations) for this fingerprint. Otherwise it says "run make smoke-impact first". The only override is `SKIP_SMOKE_GATE=1 REASON="..."` (alias `SKIP_IMPACT=1`), which is logged to `history/impact_gate.log`. After the run it writes `history/bench/full-<sha7>.json` and prints the Gate 3 verdict.
   - **Pass bar:** strict `3/3` ≥ 90% (`45/50`, which needs an individual pass rate `p` of about 96.5%), **and** 100% majority (zero `0/3` or `1/3` evaluations), `0` tool errors, from one complete, single-commit full run (`is_full_run: true`, every evaluation scored on all its tries). `make gate3` checks exactly this from `gate_thresholds.json` (`strict_pass_rate` 0.90, `majority_pass_rate` 1.00) and exits 1 when any part fails, including an incomplete run. Without `REPORT=`, it reads `history/bench/full-<HEAD sha7>.json`, or else the newest `full-*.json` whose commit has the same source fingerprint as HEAD (committing the run record or a docs change moves HEAD but not the code). Report `strict 3/3 | majority ≥2/3 | individual` side by side (plus `p` and `N × p³`), and never log synthetic composite `full-*` runs in `history/runs.jsonl`.
5. **Gate 4 (holdout and audio, release):** `make bench-holdout ENV=staging` (`HOLDOUT_DIR`, default `bench-holdout/`, × 3 repeats) + naturalness-graded audio simulations. The holdout must run on the **same code** (same source fingerprint of `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3; a docs-only or history-only commit in between is fine. The guard refuses while the source folders have uncommitted changes or the deployed fingerprint doesn't match. It pairs with `history/bench/full-<HEAD sha7>.json`, or else the newest `full-*.json` whose commit has the same source fingerprint as HEAD, prints which full run it paired with, and logs the pairing to `history/impact_gate.log`. It refuses when there is no such run, and when that run did not pass Gate 3 — that last check can be overridden only with `HOLDOUT_REASON="..."`, logged to `history/holdout_audit.log`. Re-running the holdout on a new commit also needs `HOLDOUT_REASON`.

## Holdout Rules (Hidden Tests; `docs/DESIGN_RULES.md` rules 19 and 28)
- Never open `bench-holdout/` while building. The holdout measures behavior the builder never saw.
- A visible + holdout total is valid only when both ran on the **same code** (same source fingerprint; a docs-only or history-only commit in between is fine). Never add visible and holdout scores measured on different code.
- A fix driven by holdout failures needs the **owner's approval** first. After it, run a full visible `make bench-full` on that same code before anyone reports or re-runs the holdout (in `telco-rebuild`, holdout-driven fixes were reported as keeping 46/50 visible; the same code later measured 38/50).
- Never run the holdout through `make bench-full BENCH_DIR=bench-holdout`: it is refused, because it would skip the guard and label the run as a visible full run.
- Fix holdout failures only with general, PRD-neutral rules. Never copy holdout IDs or values into prompts, tools or `lib/fakes.py`.
- The measured record, same-commit pairs only: in `telco-rebuild`, `0bf79fe` 46/50 visible + 14/20 holdout = **60/70** strict `3/3` (final `aa2bed4` 42/50 + 17/20 = **59/70** strict `3/3`, 69/70 majority); in `telco-v3`, `8bdb778` 48/50 visible + 18/20 holdout = **66/70 (94.3%)** strict `3/3` (`205/210 = 97.6%` trials), and final `f05719b` 46/50 visible (`50/50` majority) + 18/20 holdout (`20/20` majority, `58/60 = 96.7%` trials) = **70/70 (100.0%) combined majority** and **64/70 (91.4%) strict `3/3`** (`2.0pp` strict gap, `0.0pp` majority gap). Full table: [09-run-log](references/09-run-log.md).

## Optimizers, Two-Bucket Triage, and Merging (rules 29, 30, and 36)
- **Automatic optimizers such as ParetoLoop:** score only complete N × 3 runs, diff every optimizer prompt edit for lost constraints, never cancel runs mid-flight, and re-measure any merged candidate with a full visible run plus the holdout on the same code. In `telco-rebuild`, a 180-minute poll timeout scored candidates on partly finished runs (225/350 and 232/350 conversations), showing about 0.96–0.97 "capability" that hid regressions; its prompt edits removed working constraints (for example an "ONLY" on a wrong-code branch).
- **Two-Bucket Triage (Bucket A vs. Bucket B):** Partition fixes into **Bucket A** (zero-coupling additive leaf tool metadata and atomic sequential tool wrapping, which cannot alter existing control-flow branches and can be safely batched into one commit) vs. **Bucket B** (shared routing or eligibility thresholds, which must be isolated one at a time and smoke-tested against both the positive target and its negative twin via `make smoke-impact` before `make bench-full`).

## Cloud DLP (Log Redaction; rule 26)
Cloud Data Loss Prevention (**DLP**, now Sensitive Data Protection) hides personal data such as card and phone numbers in conversation logs.
- `make setup-dlp ENV=staging` (`scripts/setup_dlp.py`; preflight runs first; add `DRY_RUN=1` to only print the plan) creates or updates `<agent>-pii-inspect` and `<agent>-pii-deidentify` templates in the app's location, tests them on a neutral sample, and sets `loggingSettings.redactionConfig` (`enableRedaction: true` plus both template names) in `cxas_app/app.json`. Commit, then `make push ENV=staging` deploys it.
- CES skips redaction in evaluation sessions, so it has **zero effect on scores** and evaluations cannot verify it. Check it in a `make chat` session or in the logs.
- The templates must not redact `DATE`, `TIME` or `LOCATION`, so operational times and outage areas stay readable. Synthetic test card numbers fail the built-in Luhn checksum, so the inspect template adds a custom regex info type for card numbers. With ADC user credentials, DLP REST calls need the `X-Goog-User-Project` header. More: [11-gotchas](references/11-gotchas.md).

---

## The 7 Root-Cause Clusters

When diagnosing failures in Phase 6–7, classify each failure into one of the **7 Root-Cause Clusters** (detailed in [07-failure-loop](references/07-failure-loop.md); rule numbers refer to `docs/DESIGN_RULES.md`):
- **Cluster 1: Session State & Multi-Step Flows** (tools read and write `context.state` directly, rule 11, using `read_count(state, key)` (`int(float(v))`) for integer counters, rule 15; two-step tools finish only when called again with `caller_confirmed=True`; money-moving tools check `logged_in` themselves while login tools never gate on `NOT_IDENTIFIED` or `CODE_NOT_SENT`, rule 21; clear `state["card_last4"] = ""` on payment decline and track `state["last_payment_method"]`, rule 24).
- **Cluster 2: Hallucination Judge Grounding & Prompt Anti-Embellishment** (return domain policy fields from the tool that owns the workflow, and pre-ground two-step confirmation fees and rules in lookup/login tools; forbid unreturned security, fee and timeline embellishments in `<constraints>`; return money as a number plus a 2-decimal display string and currency; never call a money-moving tool in the same turn as the login check, rule 9; every handoff carries the reference number, goal and login progress, rule 4).
- **Cluster 3: Language Lock & Turn-1 Multilingual Handover** (ordinary tools return data only, **except** `handover_to_person`, which returns a localized `spoken_message`/`handoff_message` from `SPOKEN_LINES[lang]`; its language comes from an explicit `language` argument, then the session's `language`, then French/Spanish markers in the caller's words, then the profile's `preferred_language`, then `en-US`; `app.json` default `language=""`, rules 5 and 25).
- **Cluster 4: Premature, Silent, or Unterminated Human Handover** (sub-agent transfers are silent, whereas for `handover_to_person` the agent must speak the step-specific or generic transfer line, call `handover_to_person` (returning `spoken_message`, `handoff_message`, `handoff_status="completed_via_specialist_queue"`, `action_fulfilled=True`, `task_completed=True`, `user_goal_fulfilled=True`), and call `end_session` in the **same turn**; `speech_hygiene` injects `state["handoff_message"]` only when the reply has no text and never rewrites text the model spoke, rules 5, 7, 20).
- **Cluster 5: Verification, Fake-Data Contract & Input Normalization** (the **3-attempt login ladder** in `lib/fakes.py`, Rule 21: the code and PIN tools share one failure counter; Attempt 1 accepts any 4–10 digit code not in `ALWAYS_WRONG_LOGIN_CODES` (`0000`, `000000`, `1111`, `111111`, `9999`, `999999`); Attempt 2 accepts only `VALID_OTPS | VALID_PINS`; Attempt 3 always fails, even with a valid code, and locks the caller out (`TOO_MANY_ATTEMPTS`, `lockout_triggered=true`, `auth_status=locked`); strip float `.0` via `normalize_code(value)` and let `lookup_account` synthesize a phone only from a 9–10 digit identifier with no letters, Rule 22; never greet by profile `first_name`, `DEF-06`; include a `Code Not Received` prompt step, `DEF-09`; and keep `make eval-contract` green, Rule 23).
- **Cluster 6: Fixed Wording & Two-Step Disclosures** (fixed lines live in the prompt, word for word, each failure line next to its success line, rules 5 and 6; pre-ground two-step confirmation rules in lookup/login tools so they are in the transcript before the agent asks for confirmation).
- **Cluster 7: Bundler, Callback, Runner & Audio Platform Traps** (keep only the `speech_hygiene` after-model callback — never add a `before_tool` `auth_gate` (`-9` strict in `full-1376555`), a `before_model` `turn_state` callback (`-4` strict in `full-f2f45a8`), or a separate deterministic login agent with a task queue (not measured; see the dead ends in [04-agent-design](references/04-agent-design.md)), rule 16; `bundle.py` import alias stripping and helper collisions; expired Google Cloud logins, caught by the automatic preflight; `DEF-A01` audio runner dropping 1-word scripted openers).

---

## Scaffolding a New Repository

1. **Automated 1-Command Kickstart (recommended):**
   ```bash
   make kickstart NAME=<agent-name> PRD=prd.md   # runs python3 scripts/kickstart.py --agent-name <agent-name> --prd prd.md --temperature $(TEMPERATURE)
   make selftest    # verifies all suite/ and scripts/ utilities print OK (includes make skill-assets-check)
   make ci          # bundle-check, overfit-check, eval-contract, cxas lint (+ lint waivers), pytest + >=80% coverage, verify_mutations
   ```
2. **Manual template setup (if customizing layout):**
   - Copy `assets/requirements.md`, `scenarios.md`, `tdd.md`, `defects.md`, and `experiment_log.md` → `docs/`, and `assets/evals/` → `evals/`.
   - Take the code from the kit root: `scripts/`, `suite/`, `Makefile`, `gate_thresholds.json`, `lint_waivers.json` and `environments/example.mk` (→ `environments/staging.mk` and `environments/live.mk`). The copies under `assets/` mirror those root files: `make skill-assets` refreshes them, and `make skill-assets-check` (part of `make selftest`) fails when they drift.
   - Copy the kit's `.github/` folder, or run `make bootstrap-dry` then `make bootstrap` to write `.github/workflows/` for your repo ([08-ci-cd](references/08-ci-cd.md)).
3. Optional: run `uv run cxas init` to install SCRAPI's built-in `cxas-*` skills into `.agents/skills/`. **Keep this repository's `AGENTS.md`** when prompted.

---

## How to Talk to the Human
- **Plain English.** Define every acronym on first use (CUJ = Critical User Journey, TDD = Technical Design Document, OTP = One-Time Passcode, PIN = Personal Identification Number, DTMF = Dual-Tone Multi-Frequency keypad digits, ADC = Application Default Credentials).
- **Report `strict 3/3 | majority ≥2/3 | individual` side by side, strict first** (plus individual pass rate `p` and `N × p³`), and break down failures across all 3 judge metrics (Custom Expectations, User Goal Satisfaction, Hallucination/Grounding), never just a single headline percentage.
- **Include the 5-Part Engineering Rationale** for every fix: (1) Prior Failure Diagnosis with conversation IDs, (2) What Changed, (3) Why This Fix Works, (4) Exact `file:line` References, and (5) Alternatives Considered & Why Rejected.
- Never call a local unit test or keyword check an "evaluation pass rate", never record synthetic composite `full-*` runs in `history/runs.jsonl`, never combine visible and holdout scores measured on different code, and never state a duration nobody measured.
