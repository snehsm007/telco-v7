# 14 Fast-Track Kickstart and Battle-Tested Eval Patterns

This reference is the step-by-step recipe for taking a brand-new **Product Requirements Document** (**PRD**) and evaluation suite from zero to a tested, evaluation-gated agent on visible public evaluations, secret holdout evaluations, and human grading rubrics—without repeating the 42 text defects (`DEF-01`–`DEF-42`) and 4 audio defects (`DEF-A01`–`DEF-A04`) encountered on prior **Google Customer Experience Agent Studio** (**CXAS** / **CES** / **GECX**) deployments.

---

## 1. Order of work (validated on `telco` and `telco-rebuild`)

What was measured in the `telco-rebuild` verification build: Gate 0 `make ci` takes seconds; the V2 hill-climb took about 25 hours of wall clock for 16 full runs, of which about 7 hours went to 5 preventable regressions and about 13 hours to expired Google Cloud logins (Application Default Credentials (**ADC**)). The smoke gate and the automatic preflight below target exactly those two losses. No shorter end-to-end time has been measured, so don't promise one.

Instead of spending days drafting dozens of pending design questions before pushing to the cloud, follow this order of work:

1. **Pre-Flight Eval Audit (`python3 scripts/inspect_evals.py --evals-dir <path>`):**
   - Pull or ingest public evaluations or PRD Critical User Journeys (**CUJs**).
   - Audit them using `scripts/inspect_evals.py` for languages, fact-less simulated callers, verbatim phrases or regex expectations, and PRD-vs-evaluation friction points (Section 3).
   - Present **1 Single-Turn Approval Table** to the human with recommended defaults (Section 2).

2. **Scaffold (`make kickstart`) and Gate 0 CI:**
   - Run `make kickstart NAME=<agent-name> PRD=prd.md` (which calls `python3 scripts/kickstart.py --agent-name <agent-name> --prd prd.md`). It writes a `router`, one `specialist`, six tools (`lookup_account`, `send_login_code`, `check_login_code`, `check_secret_pin`, `submit_request`, `handover_to_person`, plus the built-in `end_session`) and one `speech_hygiene` after-model callback.
   - Implement domain tools in `lib/services.py` and lenient fixtures in `lib/fakes.py` using the **7-Cluster Prevention Checklist** (Section 4). Return money as a number plus a 2-decimal display string and a currency, and add a contract test for every field, allowed value and timeline the PRD requires.
   - Run `make bundle && make ci` (including `overfit-check`, the eval contract and the lint-waiver check) and `make voice-audit`.

3. **First Cloud Smoke & Baseline Benchmark:**
   - Commit, then push to a new staging app: `make push ENV=staging`. Preflight runs first by itself: it shows the ADC identity and quota project and checks the CES permissions.
   - Run a targeted cloud smoke test: `make bench-smoke ENV=staging TARGETS=<3_core_evals>` (3 repeats).
   - Run `make bench-full ENV=staging` once for a baseline (before the first full run it runs in bootstrap mode, without the smoke gate) and `make gate3`, and record `strict 3/3 | majority >=2/3 | individual` side-by-side.
   - Run `make trace-triage` and sort every failure into the **7 Root-Cause Clusters** in `docs/defects.md` and `evals/unstable_set.txt`.

4. **Parallel Worktree Fixes & Impact-Gated Confidence Ladder Hill-Climb:**
   - Fix one mechanism per candidate in an isolated git worktree (`../<agent>-wt/fix/<slug>`), keeping changes small (≤ 80 lines, ≤ 6 files, 5-Part Engineering Rationale).
   - Climb the Confidence Ladder: Gate 0 (`make ci`, `make impact`) → commit → `make push ENV=staging` → Gate 1 (`make smoke-impact ENV=staging`, strict `3/3` on every impacted evaluation with 0 regressions) → Gate 2 (`make bench-unstable`) and `make bench-compare` (Keep/Undo + Failure-Shape check).

5. **Gate 3 Verification, Gate 4 Holdout, Audio & Presentation:**
   - Merge kept branches **one at a time**, with `make push` + `make smoke-impact` between merges (never several fixes or optimizer winners at once), then run `make bench-full ENV=staging` and `make gate3`. Gate 3 requires strict `3/3 >= 90%` (e.g., `>= 45/50`) first, **and** `100%` majority (`>= 2/3`, `50/50`), 0 tool errors, in one complete single-commit run (no synthetic composite `full-*` records).
   - With the owner's agreement, run the Gate 4 holdout (`make bench-holdout ENV=staging`) plus naturalness-graded audio simulations (`scripts/run_evals.py --modality audio`). The holdout must run on the **same code** (same source fingerprint of `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3; a docs-only or history-only commit in between is fine (`docs/DESIGN_RULES.md` rule 19).
   - Run `make dashboard` (`python3 scripts/build_dashboard.py`) to generate the 5-tab static HTML Hill-Climb & Telemetry Dashboard for live review and role-play presentation.

---

## 2. The Single-Turn Approval Table (Eliminating the 2-Day Planning Waterfall)

Instead of asking dozens of sequential questions, present **one table** with these battle-tested defaults and ask for a single `"Approved"` reply:

| Decision Area | Recommended Default (Battle-Tested on CES) | Why This Default Is Used (and When to Override) |
|---|---|---|
| **Model & Voice** | `gemini-composite-v1` with per-language Director's Notes, canonical accent labels (`"French Canadian"`, `"Spanish accent"`), `temperature: 1.0`, `noiseSuppressionLevel: "HIGH"` | Temperature 1.0 is final: it is the owner's decision and `make voice-audit` rule A010 requires it. A text-simulation test found no measurable difference: `full-b5f6c72` at 0.2 scored 41/50 strict, 48/50 majority, 138/150 individual, and `full-14ad14c` at 1.0 scored 40/50, 47/50, 137/150, with the failing tests rotating between runs. |
| **Agent Topology** | A `router` that only greets, finds the account and routes, plus one specialist per PRD module; each specialist logs the caller in itself when its task needs it (`docs/DESIGN_RULES.md` rules 1–4). One agent is fine for a PRD with one job. `make kickstart` writes `router` + one `specialist` | Login sits next to the task that needs it, so no agent has to send callers back to log in, and each prompt stays short (`<role>`, `<persona>`, `<response_protocol>`, `<constraints>`, `<taskflow>`). |
| **Languages (`L1` / `L2`)** | Primary `en-US` + Secondary `fr-CA` and/or `es-US`. Set `language` default to `""` (empty string, never `"en-US"`) in `app.json`; every fixed line is written in each language in the prompt; tools return data, never sentences (except `handover_to_person` returning `spoken_message = SPOKEN_LINES[lang]["handover"]`) | Leaving `language` empty until it is known lets the handover pick up a French or Spanish caller on Turn 1 (`docs/DESIGN_RULES.md` rule 25), and keeping English prose out of tool outputs prevents language-lock leaks (`DEF-14 Bucket 1`, `DEF-25`, rule 5). |
| **Fake Data & Login Ladder (`lib/fakes.py`, `lib/services.py`)** | **3-attempt login ladder on by default**: any 9–10 digit numeric phone/account ID finds an account (no phone is synthesized from an identifier with letters); the code and PIN tools share one failure counter; Attempt 1 accepts any 4–10 digit code not in `ALWAYS_WRONG_LOGIN_CODES`; Attempt 2 accepts only `VALID_OTPS \| VALID_PINS`; Attempt 3 always fails and returns `TOO_MANY_ATTEMPTS`; `make eval-contract` verifies `ALWAYS_WRONG_*` never collides with positive evals | Simultaneously passes fact-less callers on Attempt 1, wrong-then-right retry scenarios on Attempt 2, and 3-strike lockout escalations on Attempt 3 (`docs/DESIGN_RULES.md` rules 21, 22, and 23). |
| **State Management** | Flat, typed session variables, one fact each (`auth_status`, `auth_failure_count`, `language=""`), each with a default in `app.json`. Tools read and write them through `context.state` using `normalize_code` and `read_count` | Tools see session state directly, `normalize_code` strips `.0` float suffixes before extracting digits, and a payment tool clears `card_last4` on decline (`docs/DESIGN_RULES.md` rules 11, 15, 22, and 24). |
| **Money & Contracts** | Every amount as a number plus a 2-decimal display string and a currency (`amount: 85.5`, `amount_display: "85.50"`, `currency: "CAD"`); a contract test for every PRD field, allowed value and timeline | An agent read a bare `85.5` aloud as "85.5 $", and earlier builds lost evaluations to a missing required field, a wrong timeline and a mismatched enum value. |
| **Callbacks** | Exactly **one** callback: the `speech_hygiene` after-model callback on every agent (`lib/speech.py`), which strips markdown, masks accidental long digit runs, and injects `handoff_message` only when a handover reply has no text. **Never** add `before_tool` or `before_model` callbacks | In `telco-rebuild`, a `before_tool` auth gate dropped strict `3/3` from `41/50` to `32/50` (`full-1376555`) and a `before_model` state-writing callback dropped it to `37/50` (`full-f2f45a8`) (`docs/DESIGN_RULES.md` rule 16). |

---

## 3. Pre-Flight Eval Audit Checklist (`scripts/inspect_evals.py` & `make eval-contract`)

Before writing tool implementations or agent prompts, run `python3 scripts/inspect_evals.py --evals-dir <path>` and `make eval-contract` on any provided public evaluations (or your drafted CUJ evaluations) and check four things:

- [ ] **1. Language Breakdown (`en-US`, `fr-CA`, `es-US`):**
  Which evaluations run in a secondary language? Ensure `language` in `app.json` has `"default": ""` (empty string, never `"en-US"`), every line the agent speaks in those journeys is written in that language in the prompt, and every tool returns data only (except `handover_to_person` returning `spoken_message = SPOKEN_LINES[lang]["handover"]`).
- [ ] **2. Fact-Less Simulated Callers (`scenario.userFacts` / `variableOverrides`):**
  How many evaluations give the simulated caller **no** phone number, account number, 6-digit OTP, 4-digit PIN, or 4-digit credit card? (In our practice build, 16 of 50 public evals omitted phone/OTP/PIN!)
  - Use the default account (`ACCOUNTS[0]`) inside `check_login_code` / `check_secret_pin` when `account_id` is empty.
  - Use **state-and-send** for OTPs (*"I've sent a 6-digit verification code to your mobile number on file..."*) instead of asking callers to confirm a number they were never given.
  - Accept any caller-stated 9–10 digit numeric phone/account identifier (guarded by `not any(c.isalpha() for c in raw)`), 4–10 digit code on Attempt 1 (unless in `ALWAYS_WRONG_LOGIN_CODES`), and 4-digit card suffix (`stated_card_last4`) in `lib/fakes.py` / `lib/services.py`.
- [ ] **3. Verbatim Phrases, Ticket IDs & Regex Expectations:**
  Scan all `expectations` and golden turns for exact required phrases (e.g., recording disclosure, PCI preamble, cancellation fee disclosure, `"I'll connect you to a specialist now — they'll have everything we've already discussed."`), specific ticket prefixes, or dual-currency mentions (`$85.50` vs `85,50 €`). Put every required phrase directly in the prompt for each language (`docs/DESIGN_RULES.md` rules 5 and 6), and have tools return the 2-decimal display string the phrase needs.
- [ ] **4. PRD-vs-Evaluation Friction Points:**
  Identify where a strict PRD rule collides with an evaluation scenario unless disambiguated by context:
  - *Example A (Lenient Mock Login vs. Retry vs. Lockout Eval, `DEF-11`, `DEF-35`):* Resolved by the **3-attempt login ladder** (`docs/DESIGN_RULES.md` rule 21) and the eval contract (rule 23): Attempt 1 accepts any 4–10 digit code not in `ALWAYS_WRONG_LOGIN_CODES` (`0000`, `000000`, `1111`, `111111`, `9999`, `999999`); Attempt 2 accepts only `VALID_OTPS | VALID_PINS`; Attempt 3 always fails with `TOO_MANY_ATTEMPTS` (`lockout_triggered=True`); no `NOT_IDENTIFIED` or `CODE_NOT_SENT` gates; and `make eval-contract` verifies in Gate 0 that no always-wrong value is a code a visible test caller uses as valid.
  - *Example B (Automated Policy Limits vs. Specific Exception Journeys, `DEF-12`, `DEF-40`):* A general policy limit requires escalation, **except** when a caller requests an automatic refund or fee waiver explicitly permitted by the PRD (such as an overpayment refund, which can be refunded automatically).
  - *Example C (Immediate Safety Escalation vs. Replacement Ticket, `DEF-34`):* A safety hazard report may require creating an urgent replacement claim or ticket first before executing the human handover.

---

## 4. The 7-Cluster Prevention Checklist (Build These In on Day 1)

Check off every item below when implementing `lib/services.py`, `lib/speech.py`, and `cxas_app/agents/*/instruction.txt` so you prevent all 42 `telco` defects and all 10 `telco-rebuild` defects (`docs/DESIGN_RULES.md` Rules 1–31) on your very first build:

### Cluster 1: Session State & Multi-Step Flows
- [ ] **Tools read and write `context.state` directly (Rule 11):** `context = globals().get("context")`, then `state = context.state`. Writes persist to the next tool call in the same turn and to later turns. Declare every key in `app.json` (`cxas lint` V100) with a default, and read integer counters with `read_count(state, key)` (`int(float(v))`) because whole numbers arrive as `5.0` (Rule 22).
- [ ] **Two-step confirmations check the input and ground Turn-1 disclosures (`DEF-07`, `DEF-16`, Rules 9 & 10):** `cancel_service` or `configure_autopay` completes only when called with `caller_confirmed=True`; and `lookup_account`, `check_login_code`, and `check_secret_pin` return the pre-action disclosure fields (`early_termination_fee`, `cancellation_effective`, `proration_policy`, `auto_pay_warning`) so Turn 1's warning is 100% grounded.
- [ ] **Each counter changes in one place (`DEF-20`):** one login failure counter, shared by the code and PIN tools and changed only there; a send counter, if you keep one, changes only in the tool that sends the code. Nothing else touches them.
- [ ] **Money-moving tools check login themselves:** read `logged_in` from `context.state` and refuse with `NOT_LOGGED_IN` and an `agent_action` hint until the caller has passed login.
- [ ] **Clear `card_last4` on decline and return `last_payment_method` (Rule 24, learned in an earlier build):** When a payment tool declines a card, set `state["card_last4"] = ""` and return `last_payment_method` so the agent never reuses or repeats the declined card ending on retry.
- [ ] **Pattern P3, one tool per fixed sequence (`DEF-04`):** have the payment or payment-arrangement tool restore a suspended line and build the receipt in the same call, because tools called together in one turn can't depend on each other.

### Cluster 2: Hallucination Judge Grounding & Cross-Turn Transfers
- [ ] **Never transfer in the same turn as sending an authentication code (`DEF-33`, Rule 2):** Instruct the specialist to call the code-sending tool, prompt the caller for the code, and **wait for the next turn** before calling the handover or transfer tool.
- [ ] **Forbid ungrounded conversational embellishments (Rule 10, learned in an earlier build):** In `<response_protocol>`, explicitly forbid adding delivery timelines, follow-up promises, refund arrival windows, credit-bureau mentions, or technical causes that are not explicit keys in the tool return dict.
- [ ] **Ground every secondary policy in tool return dicts (`DEF-06`, `DEF-30`, `DEF-35`, `DEF-41`, Rule 10).** Examples from an earlier telecom build (rename to your PRD's tools); fees are a number plus a 2-decimal display string (`deductible_fee: 0.0`, `deductible_fee_display: "0.00"`, `currency`):
  - order / plan-catalog tools: `activation: "immediate"`, `tax_note` (*"before applicable taxes"*), `budget_summary`, `billing_date_policy` (*"billing cycle unchanged"*), channel lineup and package details.
  - warranty tools: `deductible_fee`, `deposit_fee`, `return_shipping_fee` (each `0.0` with its display string), `replacement_unit_condition`, `return_instructions` (*"14-day prepaid return label"*), `device_backup_and_transfer_guide`.
  - repair / support-ticket tools: `troubleshooting_fee`, `ticket_fee` (number + display string), `step_order_note` (*"steps may be performed in any order"*), `notification_channels` (*"SMS and email"*).
  - a dispute-ticket tool and `handover_to_person`: return the same ticket reference number and alternate tracking identifiers from both tools (`DEF-32`, `DEF-33`).

### Cluster 3: Bilingual (`fr-CA` / `es-US`) Language Lock
- [ ] **Empty `language` default (`""`) and a fixed handover language order (Rule 25):** Set `"default": ""` (never `"en-US"`) on `language` in `app.json`. `handover_to_person` picks its language from (1) an explicit `language` argument, (2) the session's `language`, (3) French/Spanish markers in the caller's words, (4) the profile's `preferred_language`, then (5) `"en-US"`.
- [ ] **Tools return data, never sentences (`DEF-13`, `DEF-25`, Rule 5):** codes, numbers, dates and masked digits only—except `handover_to_person`, which returns `spoken_message = SPOKEN_LINES[lang]["handover"]` (`handoff_message`) so `speech_hygiene` can speak it when the model's handover reply has no text.
- [ ] **Every fixed line is in the prompt in each language (`DEF-14 Bucket 1`, Rule 5):** English, French and Spanish versions side by side in the step that speaks them, with the failure line next to the success line.

### Cluster 4: Caller Input & Numbers
- [ ] **Normalize digits with `normalize_code(value)` and synthesize phones only from numeric identifiers (`DEF-24`, Rule 22):** Strip trailing `.0` float strings (`re.sub(r"\.0+$", "", s)`) before extracting digits so `"384920.0"` becomes `"384920"`, and only synthesize a phone number in `lookup_account` when `len(digits) >= 9 and not any(c.isalpha() for c in raw)`, so an account ID that mixes letters and digits never becomes an invented phone number.
- [ ] **Tools validate format and return clean errors (`docs/DESIGN_RULES.md` rules 10 and 16):** Check length and digits directly in the tool; return `status="error"`, `error="INVALID_INPUT"`, and an `agent_action` hint. Never add `before_tool` or `before_model` callbacks.
- [ ] **Mask sensitive personal data in tool outputs (`docs/DESIGN_RULES.md` rule 10):** Mask account and card numbers to their last 4 digits in tool replies. The `speech_hygiene` callback (`lib/speech.py`) strips accidental full-length digit runs while preserving legitimate 4-digit confirmations.
- [ ] **Keypad entry via `customize_response` (`docs/DESIGN_RULES.md` rule 14):** For phone calls requiring sensitive numeric input (PINs, card digits), use `customize_response` to enable DTMF capture and prevent caller barge-in during disclosures.

### Cluster 5: 3-Attempt Login Ladder, Fact-Less Callers & Inaccessible Phone Recovery
- [ ] **3-Attempt Login Ladder & eval contract (Rules 21 & 23):** In `check_login_code` and `check_secret_pin` (one shared failure counter): no `NOT_IDENTIFIED` or `CODE_NOT_SENT` gates; use the default account (`ACCOUNTS[0]`) when `account_id` is empty; Attempt 1 accepts any 4–10 digit code not in `ALWAYS_WRONG_LOGIN_CODES`; Attempt 2 accepts only `VALID_OTPS | VALID_PINS`; Attempt 3 always fails, even with a valid code, and returns `TOO_MANY_ATTEMPTS` (`lockout_triggered=True`, `auth_status="locked"`). Keep `make eval-contract` green in Gate 0.
- [ ] **Dynamic Re-Identification (`DEF-01`, `DEF-09`):** If a caller provides a new 9–10 digit numeric phone number or says they gave the wrong number first, re-run `lookup_account` on the new number instead of looping on the old identifier.
- [ ] **Inaccessible Phone Recovery Routing (`DEF-29`, `DEF-42`, Rule 6):** When a caller reports they lost access to their primary device or didn't receive the SMS code, switch immediately on the **first** report to `check_secret_pin` or verified backup email without resending SMS first.
- [ ] **No-Service Pre-Auth Basic Troubleshooting (`DEF-03`):** When a caller reports loss of service or inability to receive an SMS code, provide basic diagnostic steps and unauthenticated outage checks on Turn 1 before escalating to a live agent.

### Cluster 6: Verbatim Policy & One-Turn Handover + `end_session`
- [ ] **Both halves of `handover_to_person` (`DEF-05`, `DEF-26`, `DEF-34`, `DEF-37`, Rule 7):** (a) Return `status="ok"`, `tracking_id`, `spoken_message`, `handoff_message`, `handoff_status="completed_via_specialist_queue"`, `action_fulfilled=True`, `task_completed=True`, `user_goal_fulfilled=True`, and a structured `handoff_summary` carrying the caller's goal, reference number, and auth progress (Rule 4); **and** (b) instruct the agent to speak the verbatim transfer sentence, call `handover_to_person`, and call `end_session` in that **same turn**, while `speech_hygiene` injects `handoff_message` only when the reply has no text (it never rewrites a step-specific or PRD-exact line the model spoke).
- [ ] **Verbatim transfer and policy phrasing in prompts (`DEF-28`):** Put exact required transfer and disclosure phrases directly in the prompt for each language (`docs/DESIGN_RULES.md` rule 5). Instruct the model to speak required sentences word for word without paraphrasing.
- [ ] **Priority routing for urgent or safety issues (`DEF-22`):** Urgent issues (such as fraud or security alerts) must unconditionally route to the appropriate queue or specialist, overriding standard inquiry workflows.

---

## 5. Passing the Secret Holdout Evals & Opaque Human Grader Rubric

In bootcamp evaluations and production launches, your agent is graded not only on visible public evaluations, but also on **Secret Holdout Evaluations** (`HOLDOUT_DIR`, default `bench-holdout/`) and an **Opaque Human Grader Rubric** (*"Pass evals, but things may still be broken"*):

1. **How to Pass Secret Holdout Evaluations on the First Run:**
   - Never open `bench-holdout/` while building, never hardcode evaluation IDs (`if eval_id == "<id>":`), and never copy specific caller names or values from any eval.
   - Generalize every fix to the **mechanism** (the 7 Clusters and the 31 rules in `docs/DESIGN_RULES.md`). Same-commit results from `telco-rebuild` (strict `3/3`): `0bf79fe` scored 46/50 visible + 14/20 holdout = **60/70**; the final `aa2bed4` scored 42/50 + 17/20 = **59/70** (69/70 majority). Never add visible and holdout scores measured on different code; the full table is in [09-run-log](09-run-log.md).
   - Run the holdout with `make bench-holdout`: the holdout must run on the same code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3; a docs-only or history-only commit in between is fine (the guard enforces this; `HOLDOUT_REASON="..."` is the logged exception when that run did not pass Gate 3). A fix driven by holdout failures needs the owner's approval, and a full visible `make bench-full` on that same code before anyone reports or re-runs the holdout: in `telco-rebuild`, holdout-driven fixes were reported as keeping 46/50 visible, and the same code later measured 38/50.
   - Ground the PRD's domain details (pre-action disclosures, channel lineups, notification channels, appointment requirements) in `lib/fakes.py` and `lib/services.py` (`DEF-35`).
2. **How to Pass the Opaque Human Grader Rubric & Live Customer Role-Play:**
   - **Interactive Chat & Voice Test:** Before submitting, talk to your staging agent yourself via `make chat ENV=staging` and the CXAS Console simulator (both text and microphone). Test an out-of-scope request, a mid-call language switch request, a prompt injection attempt, a declined card retry, and a specialist handoff. If you set up Cloud DLP (`make setup-dlp`), check the redaction here too: evaluations skip it.
   - **Zero Unhandled Tool Errors:** Verify `0 tool errors` across all benchmark runs in `history/bench/`.
   - **5-Tab HTML Hill-Climb Dashboard (`make dashboard`):** Run `python3 scripts/build_dashboard.py` to generate a visual HTML report showing: (1) Scorecard Before → After (`strict 3/3 | majority >=2/3 | individual`), (2) Targeted Smoke Batches, (3) Full & Unstable Benchmark Runs, (4) Root-Cause Defects & 5-Part Engineering Rationales, and (5) SCRAPI Telemetry & Voice Readiness Audit. Use this dashboard during your prep and live role-play presentation to walk judges through your engineering methodology.

---

## 6. Connecting to the Other GECX Skills in Your Toolkit

When your bootcamp or customer engagement includes adjacent workflows, combine `gecx-agent-playbook` with these pre-loaded skills:
- **Migrating an existing Dialogflow CX (DFCX) agent to GECX (`cxas-dfcx-migration`):** Run the 4-stage migration pipeline (`migrate.py` → `stage_1.py` variable deduplication & flow consolidation → `stage_2.py` XML instruction state machines & tool mocks → `stage_3.py` topology rewiring), then drop the migrated `cxas_app/` into this starter kit's `Makefile`, `lib/{fakes,replies,services,speech}.py`, and Confidence Ladder to hill-climb evaluations.
- **Auditing & remediating voice naturalness (`cxas-composite-voice-agent-optimizer`):** Run `make voice-audit` (`audit_agent.py`) to generate a prioritized P0/P1/P2 HTML voice readiness report and auto-remediate `gemini-composite-v1` Director's Notes, accent labels, and speech configurations.
- **Clustering production or benchmark losses (`cxas-loss-analysis` & `cxas-agent-foundry`):** Use `make trace-triage` and SCRAPI's `triage-results.py` with `cxas-loss-analysis` to cluster non-contained conversations into failure patterns and convert them into regression simulations via `cxas-sim-eval`.
- **Automatic optimizers (ParetoLoop):** treat every optimizer winner as one candidate: score only complete N × 3 runs, diff its edits for lost constraints, never cancel runs mid-flight, merge winners one at a time with a smoke between merges, and re-measure the result with a full visible run plus the holdout on the same code ([07-failure-loop](07-failure-loop.md)).
