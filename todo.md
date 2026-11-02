# Project Implementation Checklist: Telco Voice Central (`telco-v5-snehsm`)

This document tracks the phased implementation, verification gates, and evaluation progression for the `telco-v5-snehsm` agent.

---

## Component Status Tracker

### [x] Component C1: Pre-Flight Audit, Requirements & Architecture
- [x] **Audit & Discrepancy Analysis**: Audited all 50 visible evaluations (`VE-01`–`VE-50`) against `prd.md`; produced `step0_prd_eval_discrepancy_table.md`.
- [x] **Requirements Register**: Created `docs/requirements.md` mapping all 20 business requirements (`BR-TV-001`–`BR-TV-020`), 8 capability modules (`M1`–`M8`), 7 CUJs, and 10-level priority hierarchy to concrete enforcement mechanisms.
- [x] **Scenario Matrix**: Created `docs/scenarios.md` detailing test scenarios across English (`en-US`), Canadian French (`fr-CA`), and Spanish (`es-US`), covering boundary conditions, retry PINs, 3-strike lockouts, silent turns, and Turn N+1 FAQ follow-ups.
- [x] **Technical Design Document**: Created `docs/tdd.md` defining `gemini-composite-v2` runtime parameters, Chirp3-HD voices, Cloud DLP templates, 5-agent specialist topology, Strategy B dynamic prompt injection, speech hygiene pipeline, and 22 union-typed tool contracts.

---

### [ ] Component C2: Strategy B Dynamic Prompting & Speech Hygiene Engine *(In Progress)*
- [ ] **Copy & Verbatim Registry (`lib/copy.py`)**: Author canonical strings for `en-US`, `fr-CA`, and `es-US` across all Section 7 categories with zero hardcoded amounts/dates.
- [ ] **Dynamic Language Filter (`before_model_callback`)**: Implement read-only `language_prompt_filter` (zero state writes) with Contextual Inertia + 3-word Cognate Guard to inject active language copy sheet (`<!-- ACTIVE_LANGUAGE_SHEET -->`) in memory.
- [ ] **Speech Hygiene Pipeline (`after_model_callback`)**: Implement markdown stripping, 9+ digit PII masking, card/bank last-4 protection (`KF-71`), and deterministic verbatim handoff injection on empty text.

---

### [ ] Component C3: Atomic Sequential Tool Suite (`lib/services.py`, `lib/security.py`) *(In Progress)*
- [ ] **Type Safety & Reflection Standards**: Enforce union types (`str | int | float = ""`) on all numeric/code parameters (`Rule 32`); omit `from __future__ import annotations`.
- [ ] **Anti-Baiting Proration (`Rule 35`)**: Enforce exact daily proration without open-ended "up to full monthly rate" phrases in refund/dispute tools.
- [ ] **Atomic Operation Bundling (`Rule 34`)**: Bundle bill payment + service restoration (`process_bill_payment`), and ticket lookup + 3 reschedule slots (`get_appointment_and_ticket_status`).
- [ ] **Turn N+1 FAQ Grounding (`Rule 33`)**: Pre-ground follow-up answers in primary tool returns (throttled speeds, post-cancellation rates, port checklists, warranty shipping addresses).
- [ ] **Auth & Security Logic (`lib/security.py`)**: Implement `login_code_accepted` accepting valid 4-digit codes on Attempts 1 & 2 while locking out on Attempt 3; wire restricted caller blocklist.

---

### [ ] Component C4: 5-Agent Specialist Tree Topology (`cxas_app/agents/*`) *(In Progress)*
- [ ] **Root Agent (`cxas_app/agents/router`)**: Front-door greeting, recording notice, language detection, account lookup, and immediate deflection (safety, fraud, business, human).
- [ ] **Billing Specialist (`cxas_app/agents/billing`)**: Balance review, bill payment, autopay with PCI preamble, dispute tickets, and refund cap enforcement (`<= $25.00` vs `> $25.00` vs duplicate payments).
- [ ] **Tech Support Specialist (`cxas_app/agents/tech_support`)**: Postal code outage checking, virtual repair diagnostics, appointment rescheduling, and cancellation with 2-step confirm.
- [ ] **Sales & Equipment Specialist (`cxas_app/agents/sales_equipment`)**: Curated plan recommendations, order placement, warranty processing, swollen battery safety deflection, and port-in checklists.
- [ ] **Account Specialist (`cxas_app/agents/account`)**: Identified-only password reset SMS, MFA administration with email step-up, voluntary suspensions, and cancellation with fee disclosure.

---

### [ ] Component C5: Offline Verification, Testing & CI Gates *(In Progress)*
- [ ] **Unit Test Suite**: Run `pytest tests/` covering copy registry, speech hygiene, tool contracts, auth ladders, and error tri-state handling.
- [ ] **Anti-Overfit Audit**: Run `python3 suite/overfit_check.py` to ensure zero hardcoded evaluation values or credentials in fake stores.
- [ ] **Contract Validation**: Run `python3 scripts/eval_contract.py` to verify tool signature alignment.
- [ ] **Static Linting**: Execute `cxas lint` to verify app schema, callback signatures, and agent wiring pass offline validation with 0 errors.

---

### [ ] Component C6: Cloud Deployment, Benchmarking & Hill-Climb
- [ ] **Step 6.1: Cloud Push**: Deploy isolated application `telco-v5-snehsm-staging` to Google Cloud project `google.com:nextgen-sandbox` in region `us` via `make push`.
- [ ] **Step 6.2: Baseline 50-Eval Benchmark**: Run `make bench-full` across all 50 visible evaluations (`VE-01` through `VE-50`) to establish baseline strict 3/3, majority, and individual pass rates.
- [ ] **Step 6.3: Two-Bucket Hill-Climb**:
  - Triage failures using `scripts/triage_failures.py`.
  - Batch Bucket A fixes (zero-coupling additive metadata & atomic tool wrapping).
  - Isolate Bucket B fixes (shared routing / eligibility thresholds) with positive target and negative twin verification.
  - Achieve Gate 3 requirements: Strict 3/3 >= 90% (>= 45/50) and Majority = 100% (50/50).
- [ ] **Step 6.4: Holdout 20-Eval Benchmark**: Run `make bench-holdout` on the exact same git commit SHA to verify generalization across hidden evaluations (Strict 3/3 >= 85%, Majority >= 95%).
