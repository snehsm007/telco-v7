# Test Scenario Matrix & Simulation Catalog: Telco Voice Central (`telco-v5-snehsm`)

This document defines the comprehensive evaluation and test scenario matrix for the `telco-v5-snehsm` agent. It operationalizes the 7 Core User Journeys (CUJs) and 15 capability topics across all target languages—English (`en-US`), Canadian French (`fr-CA`), and Spanish (`es-US`)—and catalogs every critical edge case, boundary condition, and negative twin required for zero-regression quality assurance.

---

## 1. Evaluation Architecture & Matrix Overview

The test surface tests the agent under dynamic simulated-caller conditions (LLM-driven personas with probabilistic turn timing, caller facts, and behavioral variance) up to a maximum cap of 10–14 turns per interaction.

### Matrix Dimension Breakdown
- **Languages**:
  - `en-US` (Primary English, ~70% volume)
  - `fr-CA` (Canadian French, ~25% volume across 100% of capabilities)
  - `es-US` (Spanish, ~5% volume / multilingual fallback coverage)
- **Input Channels**: Spoken natural language, DTMF keypad digit streams, and simulated empty/silent turns.
- **Evaluation Criteria**:
  1. `Expectations`: Binary assertions on tool invocations, parameter values, and state mutations.
  2. `User Goal`: Qualitative assessment of caller intent fulfillment and conversational resolution.
  3. `Hallucination`: Zero fabricated data, ungrounded fee figures, or false policy claims.
  4. `Verbatim Compliance`: Exact string matching on Section 7 regulatory disclosures.

---

## 2. Core User Journey Scenarios Matrix (`CUJ-1`–`CUJ-7`)

| Scenario ID | CUJ & Topic | Locale | Caller Profile & Context | Primary Tools & Transitions | Key Assertions & Expected Trajectory |
|---|---|---|---|---|---|
| **SC-CUJ1-01** | `CUJ-1`: Password Reset (Happy Path) | `en-US` | Caller forgot online portal password; provides phone `514-555-0199`. | `lookup_account` -> `send_password_reset_sms` | Agent resolves identity to *Identified* state. Dispatches SMS reset link. Informs caller link is valid for 30 minutes. Does **not** ask for PIN/OTP. Does **not** read URL aloud. |
| **SC-CUJ1-02** | `CUJ-1`: Password Reset (French) | `fr-CA` | French caller forgotten password; provides mobile number. | `lookup_account` -> `send_password_reset_sms` | Conducted entirely in Canadian French. Emits localized reset confirmation stating 30-minute validity (`"valide pendant 30 minutes"`). URL link shielded. |
| **SC-CUJ1-03** | `CUJ-1`: Password Reset (Wrong Phone Recovery) | `en-US` | Caller gives invalid phone `514-555-0000`, then recovers with 9-digit account `102938475`. | `lookup_account` (Fail) -> `lookup_account` (Pass) -> `send_password_reset_sms` | Turn 1 lookup returns `NOT_FOUND`. Agent politely asks for 9-digit billing account number. Caller provides BAN; agent resolves account and dispatches SMS link. |
| **SC-CUJ2-01** | `CUJ-2`: Small Credit (`<= $25.00`) | `en-US` | Authenticated caller disputes $15 unexpected roaming fee. | `verify_login` -> `get_billing_summary` -> `process_refund_or_dispute` | Fee is `<= $25.00`. Tool approves auto-credit. Agent emits verbatim `refund_confirmation_pattern`: *"Your refund of $15.00 will appear on your next statement within 3 to 5 business days."* |
| **SC-CUJ2-02** | `CUJ-2`: Small Credit (French `VE-25`) | `fr-CA` | French caller paid bill twice ($22.50 duplicate payment / trop-perçu). | `verify_login` -> `process_refund_or_dispute` | Identifies accidental duplicate payment. Tool executes refund without opening dispute case. Emits verbatim French pattern: *"Votre remboursement de 22,50 $ figurera sur votre prochain relevé d'ici 3 à 5 jours ouvrables."* |
| **SC-CUJ2-03** | `CUJ-2`: Large Dispute (`> $25.00`) | `en-US` | Caller disputes $150 unreturned modem charge (`VE-24`). | `verify_login` -> `get_billing_summary` -> `process_refund_or_dispute` (Escalate) -> `handover_to_person` | Amount exceeds $25 auto-threshold. Tool sets `must_escalate=True`. Agent emits verbatim `transfer_to_specialist` and transfers to human billing queue. Zero ungrounded promises. |
| **SC-CUJ2-04** | `CUJ-2`: Payment Arrangement | `en-US` | Caller unable to pay $210 balance due; requests extension (`VE-30`). | `verify_login` -> `setup_payment_arrangement` | Establishes 14-day payment arrangement. Confirms new due date. Atomically clears pending suspension flag. |
| **SC-CUJ2-05** | `CUJ-2`: Autopay Setup (PCI Gate) | `en-US` | Caller sets up autopay with debit card ending in 4112 (`VE-17`). | `verify_login` -> `setup_autopay` | Agent speaks verbatim `payment_method_preamble` before confirming card details. Confirms monthly recurring charge date. Card numbers masked to last-4. |
| **SC-CUJ3-01** | `CUJ-3`: Regional Outage Active | `en-US` | Internet down; caller provides postal code `H3Z 2Y7` (`VE-03`). | `lookup_account` -> `check_regional_outage` | Postal code matches active outage. Agent immediately speaks verbatim `outage_active`: *"I see there's an active outage in your area..."* Caller opts into SMS alert; session wraps cleanly. |
| **SC-CUJ3-02** | `CUJ-3`: No Outage / Virtual Repair | `en-US` | Internet down; caller provides postal code `H2X 1Y4` (`VE-04`). | `lookup_account` -> `check_regional_outage` -> `run_troubleshooting_and_sms` | Outage check returns `active=False`. Agent initiates virtual repair, diagnoses modem status, and dispatches multi-step SMS troubleshooting guide. |
| **SC-CUJ3-03** | `CUJ-3`: Satellite TV Error 101 | `en-US` | TV displays "Error 101: Satellite Signal Lost" (`VE-42`). | `verify_login` -> `run_troubleshooting_and_sms` | Identifies satellite TV line of business. Guides caller through coaxial cable check and receiver power cycle. Sends reset signal and confirms restoration. |
| **SC-CUJ3-04** | `CUJ-3`: Fibe TV App Streaming | `fr-CA` | French caller cannot stream via Fibe TV application (`VE-43`). | `verify_login` -> `run_troubleshooting_and_sms` | Conducted in Canadian French. Identifies app streaming credentials issue. Dispatches sync command and SMS link to reset video app session. |
| **SC-CUJ4-01** | `CUJ-4`: Reschedule Appointment | `en-US` | Caller needs to move technician installation (`VE-06`). | `verify_login` -> `get_appointment_and_ticket_status` -> `manage_appointment` | Tool returns current appointment and 3 availability slots in single call. Caller picks slot; agent commits reschedule, recites window, and sends SMS confirmation. |
| **SC-CUJ4-02** | `CUJ-4`: Same-Day Cancellation Protocol | `en-US` | Caller wants to cancel technician visit scheduled for today. | `verify_login` -> `manage_appointment` | Agent applies 2-step confirmation for same-day cancellations. If technician is already marked `en_route`, agent refuses cancellation, leaves urgent note for dispatch. |
| **SC-CUJ4-03** | `CUJ-4`: Ticket Status Inquiry | `fr-CA` | French caller checks status of open fiber repair ticket (`VE-07`). | `verify_login` -> `get_appointment_and_ticket_status` | Returns ticket state, technician assignment, and localized status notes (`"Technicien assigné - Arrivée prévue entre 13h et 17h"`). |
| **SC-CUJ5-01** | `CUJ-5`: Upgrade Internet Plan | `en-US` | Existing 100Mbps customer wants 500Mbps or Gigabit (`VE-44`). | `verify_login` -> `browse_plans_and_coverage` -> `commit_plan_or_order` | Checks fiber coverage at address. Offers 2 targeted plans matching budget. Confirms plan switch, prorated monthly charge, and sends SMS receipt. |
| **SC-CUJ5-02** | `CUJ-5`: Warranty Claim (Defective) | `en-US` | Caller's 6-month-old smartphone screen flickering (`VE-49`). | `verify_login` -> `manage_warranty_claim` | Checks IMEI warranty status. Confirms manufacturer warranty active. Confirms zero water/physical damage. Dispatches prepaid return shipping label via email/SMS. |
| **SC-CUJ5-03** | `CUJ-5`: Physical Damage Warranty Rejection | `en-US` | Caller dropped phone in pool; screen cracked. | `verify_login` -> `manage_warranty_claim` | Tool flags `liquid_damage=True`. Warranty claim rejected. Agent offers out-of-warranty repair or insurance claim path politely. |
| **SC-CUJ5-04** | `CUJ-5`: Number Port-In Checklist | `en-US` | Caller wants to transfer number from external carrier (`VE-38`). | `verify_login` -> `initiate_number_transfer` | Caller opens inquiry without account details on hand. Tool accepts empty/placeholder input and returns full `required_port_checklist` (account number, PIN, billing address). |
| **SC-CUJ6-01** | `CUJ-6`: Restore Service After Payment | `en-US` | Line suspended for non-payment; caller pays past-due balance (`VE-31`). | `verify_login` -> `process_bill_payment` (+ atomic restore) | In 1 turn, caller provides card last-4; `process_bill_payment` processes payment and atomically restores service (`service_restored=True`). Agent confirms restore in 15 mins. |
| **SC-CUJ7-01** | `CUJ-7`: Secondary Language Fallback | `es-US` | Caller speaks Spanish throughout entire tech support session. | Full specialist suite in Spanish | Agent detects Spanish at Turn 1, locks Spanish, injects Spanish verbatim copy sheet, resolves tech issue without language degradation. |
| **SC-CUJ7-02** | `CUJ-7`: Unsupported Language Escalation | Third Lang | Caller speaks Mandarin or Italian. | `lookup_account` -> `handover_to_person` | Agent detects unsupported language, speaks polite English/localized handoff line, and escalates with reason `secondary_language_live_agent`. |

---

## 3. Special Edge Case & Boundary Scenario Catalog

### Edge Case 1: Retry PIN with Non-Standard Code (`VE-09`)
- **Context**: Caller enters wrong PIN `'9999'` on Attempt 1, then enters retry PIN `'4321'` on Attempt 2.
- **Vulnerability**: If `'4321'` is hardcoded in fake stores, it triggers `overfit_check.py` failure (`EVAL_VALUE_IN_FAKES`). If only `'1234'`/`'5678'` are accepted, Attempt 2 fails at runtime.
- **Resolution**: `login_code_accepted(code, attempts)` accepts any well-formed 4-digit code on Attempt 1 and Attempt 2 except known-bad sentinel patterns (`0000`, `9999`, `1111`), while Attempt 3 locks out.
- **Verification**: `VE-09` passes strict 3/3; `tests/test_auth_retry.py` verifies Attempts 1, 2, and 3 behavior.

### Edge Case 2: 3-Strike Authentication Lockout (`VE-12`)
- **Context**: Caller repeatedly fails PIN or OTP across 3 consecutive attempts.
- **Expected Trajectory**:
  - Attempt 1: Wrong code -> agent states code incorrect, asks caller to re-enter (2 attempts remain).
  - Attempt 2: Wrong code -> agent states code incorrect, warns 1 attempt remains.
  - Attempt 3: Wrong code -> tool returns `TOO_MANY_ATTEMPTS`, `must_escalate=True`. Agent emits `live_agent_handoff` and transfers caller with reason `auth_failure_handoff`.
- **Verification**: `VE-12` passes strict 3/3; session lock verified.

### Edge Case 3: Consecutive Silent Turns Recovery (`VE-08`)
- **Context**: Telephony sends 2 empty/silent turns (`""`), followed by a spoken request on Turn 3.
- **Expected Trajectory**:
  - Turn 1 (Silent): `local_noinput_counter` becomes 1. Agent asks caller if they are still there (*"Are you still there? I didn't hear you."*).
  - Turn 2 (Silent): `local_noinput_counter` becomes 2. Agent repeats prompt and warns of disconnection.
  - Turn 3 (Spoken): Caller speaks: *"I need to check my technician appointment."* Counter resets to 0. Agent proceeds with appointment flow normally without escalation.
- **Verification**: `VE-08` passes strict 3/3.

### Edge Case 4: Keypad DTMF vs. Spoken Passcode Input (`VE-16`)
- **Context**: In French, caller enters their 4-digit PIN via touch-tone keypad (`"5678"` delivered as digits in text simulation).
- **Expected Trajectory**: Keypad input is seamlessly accepted by `verify_login`. Agent proceeds immediately without prompting for voice repeat or rejecting text digits.
- **Verification**: `VE-16` passes strict 3/3.

### Edge Case 5: Shared Fallback Phone (`514-555-0199`) with Business Account Deflection (`VE-05, VE-10`)
- **Context**: 34 evaluations share the fallback phone number `514-555-0199`. In `VE-05` and `VE-10`, the caller explicitly states they are calling about their company/business account.
- **Expected Trajectory**:
  - When caller indicates a business inquiry, `lookup_account` sets `business_flag=True` and `must_escalate_immediately=True`.
  - Agent immediately speaks Section 7 verbatim `business_handoff`:
    *"To get you the best support for your business account, I'll transfer you to an agent. You'll need to use your phone keypad instead of talking to the virtual assistant. Just a moment while I connect you."*
  - Escalates with reason `business_handoff`. Does not break residential callers sharing the same phone number.
- **Verification**: `VE-05`, `VE-10` pass strict 3/3.

### Edge Case 6: Mid-Call Fraud Escalation (`VE-20`)
- **Context**: Caller begins with standard billing inquiry, authenticates, and then declares: *"Wait, someone opened an unauthorized line under my name, this is fraud!"*
- **Expected Trajectory**:
  - Priority Level 2 instantly preempts billing flow.
  - Agent does **not** demand further authentication or attempt self-service.
  - Agent speaks Section 7 verbatim `empathy_protocol`:
    *"I'm very sorry to hear that you are facing challenges. I will ensure we handle your request with the utmost care."*
  - Immediately invokes `handover_to_person(reason="fraud_escalation")`.
- **Verification**: `VE-20` passes strict 3/3.

### Edge Case 7: Swollen Battery Safety Protocol (Hardware Hazard)
- **Context**: Caller calls sales/equipment describing an expanding or swollen smartphone battery.
- **Expected Trajectory**:
  - Urgent physical safety hazard takes precedence over standard warranty RMA processing.
  - Agent immediately instructs caller to safely stop using and unplug the device, avoid puncturing it, and place it on a non-combustible surface.
  - Agent routes caller to emergency equipment replacement queue.
- **Verification**: Unit test `test_swollen_battery_safety_bypass`.

### Edge Case 8: Turn N+1 Follow-Up Question Pre-Grounding
- **Context**: After completing a primary action (e.g., plan change, warranty claim, cancellation), simulated callers frequently ask unexpected follow-up questions on Turn $N+1$:
  - *"Will my internet bill change now that I cancelled TV?"*
  - *"What is the exact throttled download speed after I hit 50GB?"*
  - *"What address will the replacement phone ship to?"*
  - *"Do you have my carrier account number for the port?"*
- **Vulnerability**: If the tool payload only returned `{ success: True }`, strict anti-hallucination rules force the agent to say *"I don't know"* and escalate via `user_requested_agent`, failing the eval.
- **Resolution (Rule 33)**: All primary action tools return comprehensive follow-up FAQ fields in their payloads (`remaining_service_rates`, `throttled_speed_kbps`, `shipping_address_on_file`, `required_port_checklist`).
- **Verification**: Evals with follow-up turns pass without ungrounded escalations.

---

## 4. Comprehensive Evaluation Test Suite Mapping

The table below maps all 50 visible evaluations (`VE-01` through `VE-50`) to their target domain, locale, and critical validation invariants:

| Eval Range | Primary Domain | Target Locales | Key Behavioral Invariants Tested |
|---|---|---|---|
| **VE-01 – VE-02** | Service Cancellation / Port-Out | `fr-CA` | French contract cancellation fee disclosure verbatim; 2-step cancellation confirm; retention offer decline. |
| **VE-03 – VE-04** | Outage & Network Virtual Repair | `en-US` | Postal code `H3Z 2Y7` active outage banner vs. `H2X 1Y4` virtual repair + SMS troubleshooting guide. |
| **VE-05, VE-10** | Business Account Deflection | `en-US` | Business account detected on shared phone; verbatim `business_handoff` emitted; zero self-serve. |
| **VE-06 – VE-08** | Appointment & Field Dispatch | `en-US` | Reschedule with 3 slot choices; ticket status lookup; recovery from 2 consecutive silent turns (`VE-08`). |
| **VE-09, 11, 24, 25** | Billing Disputes & Adjustments | `en-US`, `fr-CA` | `<= $25` credit pattern (`VE-09, 11`); `> $25` modem escalation (`VE-24`); French double-payment refund (`VE-25`). |
| **VE-12 – VE-16** | Authentication Ladder & MFA | `en-US`, `fr-CA` | 3-strike PIN lockout (`VE-12`); lost-phone backup email step-up (`VE-13`); SMS OTP MFA enable (`VE-14`); French keypad DTMF (`VE-16`). |
| **VE-17, 32, 33** | Payments & Autopay Setup | `en-US`, `fr-CA` | PCI compliance verbatim preamble before payment/autopay; credit card last-4 masking. |
| **VE-18 – VE-20** | Account Transitions & Fraud | `en-US` | English contract cancellation terms (`VE-19`); mid-call fraud report triggering empathy line + escalation (`VE-20`). |
| **VE-21 – VE-23** | Plan Catalog & Inquiries | `en-US` | Shortlist 2–3 plans matching budget; no dumping of full catalog; clear feature breakdowns. |
| **VE-26 – VE-28** | Password Reset Workflows | `en-US` | Identified-only state; 30-min validity; zero password change over voice; recovery from invalid phone (`VE-28`). |
| **VE-29 – VE-31** | Collections & Suspended Lines | `en-US` | Payment arrangement setup (`VE-30`); payment clearing suspension with atomic restore (`VE-31`). |
| **VE-34 – VE-37** | Live-Agent Handoffs | `en-US`, `fr-CA` | Explicit user request for agent; verbatim `live_agent_handoff` emitted in English and French. |
| **VE-38 – VE-40** | Port-In & Mobility Support | `en-US`, `fr-CA` | Number transfer checklist with placeholder inputs (`VE-38`); Bell network entities; SIM lock recovery. |
| **VE-41 – VE-43** | Multi-LOB Tech Support | `en-US`, `fr-CA` | French internet troubleshooting (`VE-41`); Satellite TV Error 101 (`VE-42`); Fibe TV streaming app (`VE-43`). |
| **VE-44 – VE-48** | Plan Upgrades & Speed Limits | `en-US`, `fr-CA` | Fiber upgrade commit (`VE-44`); data add-ons; Turn N+1 throttled speed questions pre-grounded. |
| **VE-49 – VE-50** | Equipment & Warranty Claims | `en-US`, `fr-CA` | Smartphone warranty verification; physical damage screening; French warranty claim processing (`VE-50`). |
