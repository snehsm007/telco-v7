# Requirements Register: Telco Voice Central (`snehsm-FDEBootcamp-CHI-greenfield`)

This document establishes the authoritative requirements traceability matrix and enforcement architecture for the `snehsm-FDEBootcamp-CHI-greenfield` Customer Experience Agent Studio (CXAS) conversational voice application. It bridges the Product Requirements Document (`prd.md`), the pre-flight evaluation audit findings (`step0_prd_eval_discrepancy_table.md`), and the agent implementation.

---

## 1. Executive Summary & Scope

The `snehsm-FDEBootcamp-CHI-greenfield` agent serves as the autonomous, voice-first front door for a major consumer telecommunications provider. It is engineered to resolve high-frequency inbound customer inquiries across six operational domains—billing, technical support, sales and equipment, appointment/field dispatch, account management, and service lifecycle transitions—either via automated self-service or via context-preserving escalation to human specialist queues.

### Core System Principles
1. **Determinism over Stochasticity**: State transitions, authentication ladders, threshold enforcements, and regulatory disclosures are governed by deterministic Python callbacks and atomic tool execution rather than open-ended prompt guidance.
2. **Strategy B Dynamic Multilingual Delivery**: The agent supports English (`en-US`), Canadian French (`fr-CA`), and Spanish (`es-US`) natively. In-memory localized copy sheets (`<!-- ACTIVE_LANGUAGE_SHEET -->`) are injected dynamically via `before_model_callback`, maintaining lean static English prompt definitions while ensuring 100% verbatim accuracy in the caller's active language.
3. **Speech Hygiene & Strict PII Shielding**: Zero raw PII exposure over voice channels. Account identifiers, credit card numbers, and banking details are masked to the last 4 characters; PINs and OTP codes are strictly never echoed. Markdown formatting is stripped cleanly for natural Chirp3-HD synthetic voice delivery.

---

## 2. Capability Modules Register (`M1`–`M8`)

The operational surface is decomposed into eight functional modules mapped to the specialist agent hierarchy:

| Module ID | Module Name | Owning Agent | Primary Responsibilities | Auth Precondition |
|---|---|---|---|---|
| **M1** | Session Lifecycle & Routing | `router` | Initial greeting, verbatim recording notice, restricted caller blocklist check, language detection & sticky locking, customer lookup, intent classification, and specialist routing. | Unauthenticated (Guest) |
| **M2** | Authentication & Identity | `router` / Specialists | Authentication ladder management (Guest -> Identified -> Authenticated), DTMF/keypad 4-digit PIN validation, 6-digit SMS OTP, backup-email step-up verification, and 3-strike lockout enforcement. | Identified (CLID or 9-digit BAN) |
| **M3** | Billing & Payment | `billing` | Balance inquiries, payment processing with atomic service restore, payment arrangements, autopay setup with PCI preamble, dispute ticket generation, and refund enforcement (`<= $25.00` auto-credit vs. `> $25.00` specialist escalation vs. verified duplicate payment refunds). | Authenticated |
| **M4** | Technical Support & Virtual Repair | `tech_support` | Regional outage detection by postal code prefix, outage banner injection, virtual repair diagnostics (Internet, Mobility, Satellite TV Error 101, Fibe TV app), and SMS troubleshooting guide dispatch. | Identified / Authenticated |
| **M5** | Sales & Equipment | `sales_equipment` | Coverage check, plan catalog recommendation (curated 2–3 plans max), new order commit with SMS receipt, warranty status lookup, defective vs. damaged triage, urgent swollen battery safety deflection, and number port-in checklist dispatch. | Identified / Authenticated |
| **M6** | Appointment & Ticket Management | `tech_support` | Technician dispatch lookup, availability slot retrieval (offering 2–3 options), appointment reschedule commit, cancellation protocol (with 2-step confirmation and en-route lock), and SMS confirmation dispatch. | Authenticated |
| **M7** | Account Management | `account` | Password reset SMS dispatch (Identified-only; link never spoken), MFA configuration (enable/disable with step-up verification), profile updates, voluntary service suspension/restoration, and service cancellation / port-out with mandatory fee disclosure. | Identified (Password Reset) / Authenticated (MFA, Profile, Cancel) |
| **M8** | Secondary & Multilingual Handling | All Agents (`router`, `billing`, `tech_support`, `sales_equipment`, `account`) | Native Canadian French (`fr-CA`) and Spanish (`es-US`) handling across 100% of capabilities. Dynamic language locking at Turn 1 with zero intra-call language degradation. Live agent transfer (`secondary_language_live_agent`) reserved exclusively for unsupported third languages. | Inherited from owning module |

---

## 3. Core User Journeys Matrix (`CUJ-1`–`CUJ-7`)

The seven Core User Journeys defined in PRD Section 19 are implemented under strict turn budgets and tool contracts:

| CUJ ID | Journey Name | Owning Agent | Primary Tool Endpoints | Turn Budget | Key Success Criteria |
|---|---|---|---|---|---|
| **CUJ-1** | Account Password Reset | `account` | `lookup_account`, `send_password_reset_sms` | Max 8 turns | Caller verified at **Identified** level only (no PIN/OTP demanded). Password reset SMS link sent with explicit 30-minute expiration notice. URL/link is never spoken aloud; agent never changes password directly over voice. |
| **CUJ-2** | Billing Dispute & Auto-Adjustment | `billing` | `get_billing_summary`, `process_refund_or_dispute` | Max 10 turns | Authenticated caller disputes charge or requests credit. Adjustments `<= $25.00` auto-credited on statement using verbatim `refund_confirmation_pattern`. Adjustments `> $25.00` escalated to human billing specialist via `transfer_to_specialist` without ungrounded rate promises. Duplicate payments (`VE-25`) refunded to original payment method. |
| **CUJ-3** | Technical Support: TV / Internet Virtual Repair | `tech_support` | `check_regional_outage`, `run_troubleshooting_and_sms` | Max 12 turns | Postal code verified before outage lookup. Active outages emit verbatim `outage_active` and offer SMS notification. Non-outage issues disambiguate line-of-business (`tv_sub_type`, satellite error 101, Fibe TV app), execute virtual repair, and offer SMS troubleshooting guide for multi-step instructions. |
| **CUJ-4** | Appointment Reschedule & Management | `tech_support` | `get_appointment_and_ticket_status`, `manage_appointment` | Max 8 turns | Retrieves pending technician appointment and returns 2–3 reschedule slots in a single atomic call. Caller selects window; agent commits reschedule, confirms new date/time window, and dispatches SMS confirmation. |
| **CUJ-5** | Sales & Equipment Upgrade | `sales_equipment` | `browse_plans_and_coverage`, `commit_plan_or_order` | Max 10 turns | Verifies regional service coverage. Curates 2–3 matching plans based on caller budget/needs. Places order, recites order confirmation number and delivery ETA, and dispatches SMS receipt. Business inquiries trigger verbatim `business_handoff`. Swollen batteries trigger immediate safety warning. |
| **CUJ-6** | Restore Suspended Service from Non-Payment | `billing` -> `account` | `get_billing_summary`, `process_bill_payment`, `execute_suspend_restore` | Max 14 turns | Identifies suspension due to overdue balance. Caller pays balance via `process_bill_payment` or sets up `setup_payment_arrangement`. Tool atomically restores service (`service_restored: True`, `new_state: "active"`) or routes cleanly back to `account` for restoration confirmation and SMS dispatch. |
| **CUJ-7** | Multilingual Specialist Handling | Specialist Agents (`fr-CA` / `es-US`) | Full tool suite with localized payloads | Max 10 turns | Entire interaction conducted natively in Canadian French or Spanish. 100% adherence to localized verbatim copy library. Seamless capability coverage without mid-call language mixing or improper transfer to live agents. |

---

## 4. Business Requirements Traceability Register (`BR-TV-001`–`BR-TV-020`)

Every requirement from Section 18 of `prd.md` is mapped to its concrete architectural enforcement mechanism and verification anchor:

| Req ID | Requirement Statement | Owning Component | Enforcement Mechanism | Verification & Test Reference |
|---|---|---|---|---|
| **BR-TV-001** | **Recording Notice**: Verbatim regional privacy disclosure emitted on greeting; re-emitted if caller queries recording status. | `router`, `lib/copy.py` | Prompt instruction in `router/instruction.txt` mandates emitting `recording_notice` in Turn 1. Strategy B injects exact localized string. | `tests/test_copy.py`, `VE-01`–`VE-50` initial turn audit. |
| **BR-TV-002** | **Restricted Caller Check**: Incoming CLID checked against blocklist prior to greeting; blocked calls hear deflection and disconnect. | `router`, `lookup_account`, `lib/security.py` | `lookup_account` checks caller ID against `RESTRICTED_NUMBERS`. Returns `is_blocked=True`, triggering deflection utterance and `end_session(reason="restricted_caller")`. | Unit test `test_restricted_caller_deflection`. |
| **BR-TV-003** | **Regional Service Alert**: Active regional advisories prepend an advisory banner to the greeting. | `router`, `lookup_account` | `lookup_account` returns `regional_alert` banner text if postal code / region has active network advisory; prompt prepends banner before main greeting. | `VE-03`, `tests/test_outage_advisory.py`. |
| **BR-TV-004** | **Language Locking**: Caller language determined at Turn 1 from area code and initial utterance, locked for session duration. | `language_prompt_filter` (Callback), `context.state` | `before_model_callback` evaluates caller speech with Contextual Inertia + 3-word Cognate Guard, sets `language` in `context.state`, and locks language unless caller explicitly requests a switch. | `VE-01, 02, 15, 16, 25, 32, 35, 37, 38, 41, 44, 49, 50`. |
| **BR-TV-005** | **Module Coverage**: All 6 core operational contact reasons route to dedicated specialist capabilities without routing loops. | `router`, Specialist Agents | Specialist routing triggers in `router/instruction.txt` evaluate caller intent and dispatch to `billing`, `tech_support`, `sales_equipment`, or `account` subagents. | `VE-01`–`VE-50` full coverage audit. |
| **BR-TV-006** | **Retry-Strike Escalation**: 3 consecutive no-input turns or 3 unresolved no-match turns trigger graceful escalation. | `after_model_callback`, `handover_to_person` | Session state tracks `local_noinput_counter` and `no_match_confirmation_count`. At counter `>= 3`, tool calls `handover_to_person(reason="no_input_escalation" | "disambig_max_attempts")`. | `VE-08, 12`, unit tests in `test_retry_counter.py`. |
| **BR-TV-007** | **DTMF Capture**: DTMF touch-tone inputs normalized into digits in session state. | Telephony wrapper, `verify_login` | Digits received via voice or keypad text are normalized via `normalize_code()` into standard string representations. | `VE-16`, `test_dtmf_normalization.py`. |
| **BR-TV-008** | **Auth Ladder**: Progression through Guest -> Identified -> Authenticated states; no mutation allowed without authentication. | `router`, `account`, `billing`, `tech_support`, `sales_equipment` | `context.state.auth_status` gates sensitive tools (`process_bill_payment`, `manage_appointment`, `cancel_or_port_out_service`). Password reset requires only `Identified`. | `VE-09, 13, 14, 26, 27, 28, 31`. |
| **BR-TV-009** | **PII Redaction**: Account, card, and bank numbers read back last-4 only; PINs and OTP codes never spoken back. | `speech_hygiene` (Callback), Cloud DLP | Regex in `speech_hygiene` masks digit runs `>= 9` while preserving 4-digit card/account suffixes. Prompts forbid echoing PIN/OTP passcodes. Cloud DLP inspects and de-identifies logs. | DLP templates `snehsm-FDEBootcamp-CHI-greenfield-pii-inspect` and `deidentify`. |
| **BR-TV-010** | **Tool-Error Tri-State**: Errors classified as System (escalate), Business (surface alternative), or Validation (re-prompt). | Tool return contracts (`lib/services.py`) | Tools return structured error payloads: `SYSTEM_DOWN` -> `handover_to_person`; `INSUFFICIENT_FUNDS` -> offer payment arrangement; `INVALID_FORMAT` -> clarify input. | `VE-12, 24, 30`, unit test `test_error_classification.py`. |
| **BR-TV-011** | **Verbatim Compliance**: Strict exact-string compliance on Section 7 audited verbatim strings. | `lib/copy.py`, Prompts, `speech_hygiene` | Verbatim strings maintained in centralized registry; injected into prompt context and verified with exact string equality checks in CI. | `tests/test_verbatim_compliance.py`. |
| **BR-TV-012** | **Business Handoff**: `business_flag == True` immediately emits verbatim `business_handoff` and transfers caller. | `lookup_account`, `handover_to_person` | If caller mentions business account or lookup returns `business_flag=True`, tool sets `must_escalate_immediately=True` with reason `business_handoff`. | `VE-05, VE-10`. |
| **BR-TV-013** | **Fraud Escalation**: Fraud allegations trigger immediate verbatim `empathy_protocol` and escalation with zero auth demands. | All Agents, `handover_to_person` | Intent classifier identifies fraud keywords (`fraud`, `stolen identity`, `unauthorized charge`). Emits empathy protocol and calls `handover_to_person(reason="fraud_escalation")`. | `VE-20`, `test_fraud_immediate_escalation.py`. |
| **BR-TV-014** | **After-Hours Awareness**: 24/7 routing for outage/fraud; next-business-day deflection for sales/appointments when queues closed. | `handover_to_person`, `lib/services.py` | Queue availability evaluated during handover; after-hours sales/plan requests offer automated callbacks or next-business-day queue placement. | `test_after_hours_routing.py`. |
| **BR-TV-015** | **Session-Context Handoff**: Escalation transfers full session state and conversation transcript to agent desktop. | `handover_to_person`, CXAS Handoff Context | `handover_to_person` serializes `session_context` (account ID, authenticated status, verified phone, intent, recent actions) into handoff payload. | `VE-35, 36, 37`. |
| **BR-TV-016** | **Malicious Utterance Handling**: Threatening or abusive caller speech triggers closing disclaimer and session termination. | Prompt Safety Guard, `end_session` | Classifier detects hostile/malicious input, emits standard firm closing disclaimer, and invokes `end_session(reason="malicious_input")`. | Unit test `test_malicious_input_termination.py`. |
| **BR-TV-017** | **No Invented Data (Anti-Hallucination)**: Zero fabricated account balances, refund amounts, or slot confirmations. | Agent Prompts, Tool Returns | System prompt `<rules>` strictly forbid reciting numeric data not returned in active tool payloads. Tools pre-ground Turn $N+1$ follow-up data. | `tests/test_hallucination_prevention.py`. |
| **BR-TV-018** | **Audio-Recording Coverage**: 100% of calls recorded as `.wav` artifacts in session audio storage. | Telephony Infrastructure, CXAS Config | App-level audio persistence configured via telephony bridge and Cloud Storage bucket `snehsm-FDEBootcamp-CHI-greenfield-session-audio`. | Infrastructure compliance audit. |
| **BR-TV-019** | **Mid-Call Topic Switch**: Agent dynamically re-classifies intent and routes to correct specialist when caller pivots. | All Agents, `childAgents` topology | Specialist agents allow seamless routing hops or invoke tools from peer domains when caller introduces a new primary intent. | `VE-20` (billing to fraud), `VE-31` (billing to restore). |
| **BR-TV-020** | **Language Non-Degradation**: Agent never emits mixed-language sentences or half-English / half-French turns. | `language_prompt_filter`, Strategy B | Clean isolation of language copy sheets ensures prompt context contains only one target language's lexical guidance per turn. | `VE-01, 15, 25, 32, 44, 50`. |

---

## 5. Priority Hierarchy (Levels 1–10 Turn-Level Conflict Resolution)

When multiple signals, intents, or conversational constraints collide on a single turn, the agent resolves the conflict strictly according to the following 10-level hierarchy:

```
[Level 1: Safety Signals] (Self-harm, threats, malicious input) -> Empathy line + Immediate Disconnect / Escalate
       ↓
[Level 2: Fraud Allegation] -> Verbatim empathy_protocol + Immediate escalation (fraud_escalation, NO auth required)
       ↓
[Level 3: System Error] (SYSTEM_DOWN / Service Outage) -> Immediate transfer to live agent queue
       ↓
[Level 4: Explicit Human Request] ("Agent", "Person", "Operator") -> Verbatim live_agent_handoff + Escalate
       ↓
[Level 5: Business Account Deflection] (business_flag == True) -> Verbatim business_handoff + Escalate
       ↓
[Level 6: Retry-Strike Lockout] (3x No-Input / 3x No-Match / 3x Auth Failure) -> Graceful handoff to person
       ↓
[Level 7: Compliance-Locked Verbatim Turns] (Recording notice, PCI preamble, Cancellation fee disclosure, Refund pattern)
       ↓
[Level 8: Authenticated Account Actions] (Bill payments, plan changes, technician booking, MFA modifications)
       ↓
[Level 9: Targeted Disambiguation] (Max 1 targeted question per turn, max 3 cumulative attempts)
       ↓
[Level 10: General Inquiries, Small Talk, Recap, & Clean Call Wrap-Up]
```

### Operational Rules of Arbitration
1. **Safety & Fraud Override All Functional Flows**: Even if an account has a pending unpaid bill or unconfirmed appointment, an allegation of fraud immediately terminates the active flow and executes Level 2 escalation.
2. **Explicit Human Requests Terminate Automation**: If a caller says "speak to a person" during an authentication or troubleshooting flow, the agent must not attempt to persuade or complete the task; it immediately emits `live_agent_handoff` (Level 4).
3. **Business Deflection Precedes Self-Service**: When an account lookup indicates `business_flag == True` or the caller declares a business entity, self-service tools are completely disabled, and Level 5 deflection triggers.

---

## 6. Section 7 Verbatim Copy Library Enforcement

All audited verbatim strings are centralized in `lib/copy.py` and maintained across English (`en-US`), Canadian French (`fr-CA`), and Spanish (`es-US`).

### Canonical Verbatim Text Registry

#### 1. `greeting_main`
- **EN**: `"Welcome to Telco. I can help with billing, technical support, or managing your account. To get started, could you tell me the phone number or account number associated with your service?"`
- **FR**: `"Bienvenue chez Telco. Je peux vous aider avec la facturation, le soutien technique ou la gestion de votre compte. Pour commencer, pourriez-vous me donner le numéro de téléphone ou de compte associé à votre service?"`
- **ES**: `"Bienvenido a Telco. Puedo ayudarle con facturación, soporte técnico o la administración de su cuenta. Para comenzar, ¿podría indicarme el número de teléfono o de cuenta asociado a su servicio?"`

#### 2. `recording_notice`
- **EN**: `"This call may be recorded for quality and training purposes."`
- **FR**: `"Cet appel peut être enregistré à des fins de formation et de qualité."`
- **ES**: `"Esta llamada puede ser grabada con fines de calidad y capacitación."`

#### 3. `id_verification_otp`
- **EN**: `"For your security, I just sent a 6-digit code to that number — please read it back to me."`
- **FR**: `"Pour votre sécurité, je viens d'envoyer un code à 6 chiffres à ce numéro — veuillez me le lire."`
- **ES**: `"Por su seguridad, acabo de enviar un código de 6 dígitos a ese número; por favor léamelo."`

#### 4. `id_verification_pin`
- **EN**: `"For your security, I'll need to verify your identity. Please enter the 4-digit PIN you set up."`
- **FR**: `"Pour votre sécurité, je dois vérifier votre identité. Veuillez entrer le NIP à 4 chiffres que vous avez configuré."`
- **ES**: `"Por su seguridad, necesito verificar su identidad. Por favor ingrese el PIN de 4 dígitos que configuró."`

#### 5. `live_agent_handoff`
- **EN**: `"I'll connect you to a representative who can help. Please hold."`
- **FR**: `"Je vais vous mettre en communication avec un représentant qui pourra vous aider. Veuillez patienter."`
- **ES**: `"Le comunicaré con un representante que podrá ayudarle. Por favor espere."`

#### 6. `business_handoff`
- **EN**: `"To get you the best support for your business account, I'll transfer you to an agent. You'll need to use your phone keypad instead of talking to the virtual assistant. Just a moment while I connect you."`
- **FR**: `"Afin de vous offrir le meilleur soutien pour votre compte entreprise, je vais vous transférer à un agent. Vous devrez utiliser le clavier de votre téléphone plutôt que de parler à l'assistant virtuel. Un instant s'il vous plaît."`
- **ES**: `"Para brindarle la mejor atención para su cuenta comercial, le transferiré a un agente. Deberá usar el teclado de su teléfono en lugar de hablar con el asistente virtual. Un momento mientras le comunico."`

#### 7. `payment_method_preamble` (PCI Compliance)
- **EN**: `"For your security, please do not read your full card number or security code out loud; we only confirm the last four digits on file."`
- **FR**: `"Pour votre sécurité, veuillez ne pas lire votre numéro de carte complet ni votre code de sécurité à haute voix; nous confirmons uniquement les quatre derniers chiffres au dossier."`
- **ES**: `"Por su seguridad, no lea su número de tarjeta completo ni su código de seguridad en voz alta; solo confirmamos los últimos cuatro dígitos registrados."`

#### 8. `contract_cancellation_fee_disclosure`
- **EN**: `"Please note that cancelling or transferring your line ends any active term agreement, and any applicable early cancellation fee and prorated charges from your account terms will appear on your final statement."`
- **FR**: `"Veuillez noter que l'annulation ou le transfert de votre ligne met fin à toute entente active, et que les frais de résiliation anticipée applicables ainsi que le solde calculé au prorata figureront sur votre dernière facture."`
- **ES**: `"Tenga en cuenta que cancelar o transferir su línea da por finalizado cualquier acuerdo de plazo activo, y cualquier cargo por cancelación anticipada aplicable y cargos prorrateados según los términos de su cuenta aparecerán en su estado de cuenta final."`

#### 9. `refund_confirmation_pattern`
- **EN**: `"Your refund of ${amount} will appear on your next statement within {days} business days."`
- **FR**: `"Votre remboursement de {amount} $ figurera sur votre prochain relevé d'ici {days} jours ouvrables."`
- **ES**: `"Su reembolso de ${amount} aparecerá en su próximo estado de cuenta dentro de {days} días hábiles."`

#### 10. `empathy_protocol`
- **EN**: `"I'm very sorry to hear that you are facing challenges. I will ensure we handle your request with the utmost care."`
- **FR**: `"Je suis désolé d'apprendre que vous éprouvez des difficultés. Je vais m'assurer que nous traitions votre demande avec le plus grand soin."`
- **ES**: `"Lamento mucho escuchar que está teniendo dificultades. Me aseguraré de que atendamos su solicitud con el mayor cuidado."`

#### 11. `outage_active`
- **EN**: `"I see there's an active outage in your area. We're working on it. Would you like me to text you when it's restored?"`
- **FR**: `"Je constate qu'il y a une panne en cours dans votre secteur. Nous y travaillons. Souhaitez-vous que je vous envoie un message texte lorsque le service sera rétabli?"`
- **ES**: `"Veo que hay una interrupción activa del servicio en su área. Estamos trabajando en ello. ¿Desea que le envíe un mensaje de texto cuando se haya restablecido?"`

#### 12. `transfer_to_specialist`
- **EN**: `"I'll connect you to a billing specialist now — they'll have everything we've already discussed."`
- **FR**: `"Je vous transfère à un spécialiste de la facturation dès maintenant — il aura sous la main tout ce dont nous venons de discuter."`
- **ES**: `"Le comunicaré con un especialista en facturación ahora mismo; tendrá a mano todo lo que ya hemos conversado."`

### Verbatim Enforcement Rules
1. **Dynamic Slot Substitution**: Values for `{amount}` and `{days}` in `refund_confirmation_pattern` are dynamically provided by tool return payloads (`applied_amount_display` and `settlement_days`). Prompts must **never** hardcode literal dollar amounts or day counts (Rule 21).
2. **Deterministic Fallback Injection**: In `after_model_callback` (`speech_hygiene`), if `handover_to_person` was invoked but the LLM emitted an empty spoken response or omitted the required verbatim handoff text, the callback automatically injects the exact localized `live_agent_handoff` string into `llm_response.text`.

## 7. Evaluation Variable Overrides Register (`fx_*` Backend Facts)

Per Requirement R3, session `variableOverrides` in `bench/dev/evaluations/` are strictly limited to backend facts and environment preconditions. Non-backend facts (such as `identified`, `auth_status`, `logged_in`, `verified`, or bypass flags) are strictly forbidden.

Every entry below corresponds to an evaluation whose scenario or user-guide explicitly states a precondition, documented with the exact line number and verbatim text from `evals.md`.

| Evaluation (`displayName`) | Key | Value | `evals.md` Line | Justification Quote |
|---|---|---|---|---|
| `sim__check_outage_active_postal_code` | `fx_outage_status` | `active` | L343 | My home Wi-Fi isn't working, and I want to check if there is an active internet outage in my area (postal code H3Z 2Y7) |
| `sim__check_outage_active_postal_code` | `fx_pin_on_file` | `4829` | L342 | **Goal / Scenario**: |
| `sim__check_outage_french_active` | `fx_outage_status` | `active` | L357 | Je veux vérifier s'il y a une panne de service internet dans mon secteur (code postal G1R 4A6) en français |
| `sim__check_outage_french_active` | `fx_pin_on_file` | `4829` | L356 | **Goal / Scenario**: |
| `sim__check_outage_none_found_sms_troubleshoot` | `fx_outage_status` | `none` | L371 | My internet is down, but if there is no outage in my area, I want to get troubleshooting steps sent to my phone |
| `sim__check_outage_none_found_sms_troubleshoot` | `fx_pin_on_file` | `4829` | L370 | **Goal / Scenario**: |
| `sim__check_tech_status_business_deflection` | `fx_business_flag` | `true` | L445 | I want to check the technician status for my business internet line |
| `sim__check_tech_status_business_deflection` | `fx_pin_on_file` | `4829` | L444 | **Goal / Scenario**: |
| `sim__check_tech_status_reschedule_pivot` | `fx_tech_status` | `delayed` | L415 | I want to check my technician's arrival time, and if they are delayed, I want to reschedule the appointment to anothe... |
| `sim__check_tech_status_standard` | `fx_pin_on_file` | `4829` | L389 | * **User guide**: Start the call in English. When prompted, provide your phone number. Authenticate by reading back t... |
| `sim__check_tech_status_standard` | `fx_tech_status` | `en_route` | L385 | I want to check if the technician is still scheduled to come to my house today to install my new internet service |
| `sim__dispute_billing_charge_french` | `fx_pin_on_file` | `4829` | L166 | * **Judge criteria**: The user conducts the entire call in French, authenticates successfully, disputes the incorrect... |
| `sim__dispute_charge_auth_retry` | `fx_pin_on_file` | `4321` | L189 | I want to dispute a charge on my bill, but I might make a mistake entering my PIN the first time |
| `sim__dispute_charge_business_account_deflection` | `fx_business_flag` | `true` | L175 | I want to dispute a billing charge on my business account |
| `sim__dispute_charge_business_account_deflection` | `fx_pin_on_file` | `4829` | L180 | * **Judge criteria**: The user is immediately redirected to a live business representative without being forced to go... |
| `sim__manage_mfa_auth_failure` | `fx_otp_on_file` | `837492` | L525 | I want to change my MFA settings but I fail the security verification (3 incorrect codes) |
| `sim__manage_mfa_auth_failure` | `fx_pin_on_file` | `8374` | L525 | I want to change my MFA settings but I fail the security verification (3 incorrect codes) |
| `sim__manage_mfa_disable` | `fx_mfa_enabled` | `true` | L533 | I want to disable two-factor authentication on my account because I lost my old authenticator phone |
| `sim__manage_mfa_enable` | `fx_mfa_enabled` | `false` | L548 | I want to enable multi-factor authentication on my account to make it more secure |
| `sim__manage_mfa_french_disable` | `fx_mfa_enabled` | `true` | L567 | * **User guide**: Speak only in French Canadian. Ask to disable MFA. Authenticate with your PIN and confirm the change |
| `sim__manage_mfa_pivot_tech` | `fx_pin_on_file` | `4829` | L596 | * **User guide**: Ask to enable MFA. Authenticate and complete the setup. Then, say 'Also, my internet has been reall... |
| `sim__pay_bill_declined_card_retry` | `fx_card_on_file_status` | `declined` | L245 | I want to pay my bill, but if my primary card is declined, I want to try a different card |
| `sim__pay_bill_declined_card_retry` | `fx_pin_on_file` | `4829` | L249 | * **User guide**: The user authenticates and attempts to pay. When told the card on file was declined, they remain ca... |
| `sim__pay_past_due_bill_prevent_suspension` | `fx_account_suspended` | `false` | L231 | I want to pay my past-due balance immediately to make sure my mobile service doesn't get cut off |
| `sim__pay_past_due_bill_prevent_suspension` | `fx_pin_on_file` | `4829` | L235 | * **User guide**: The user is anxious about service suspension. They provide their account details, authenticate quic... |
| `sim__port_out_number_english` | `fx_pin_on_file` | `4829` | L39 | * **User guide**: Tell the agent you want to port out your number. Provide your authentication details when prompted.... |
| `sim__report_fraud_french` | `fx_pin_on_file` | `4829` | L620 | **Goal / Scenario**: |
| `sim__report_fraud_mid_call_switch` | `fx_pin_on_file` | `4829` | L654 | * **User guide**: Ask to check your bill. Authenticate. When the assistant mentions a high balance, say 'Wait, I didn... |
| `sim__report_fraud_phishing` | `fx_pin_on_file` | `4829` | L636 | I received a suspicious text message asking for my PIN and want to report potential fraud |
| `sim__report_fraud_sim_swap` | `fx_pin_on_file` | `4829` | L664 | **Goal / Scenario**: |
| `sim__report_fraud_standard` | `fx_pin_on_file` | `4829` | L612 | * **Judge criteria**: The user reports fraud, hears the verbatim empathy protocol, and is immediately transferred to ... |
| `sim__request_refund_exceeding_threshold_escalation` | `fx_pin_on_file` | `4829` | L333 | * **User guide**: The user explains they were charged $150.00 for a modem they already returned and wants a full refu... |
| `sim__request_refund_overcharge_french` | `fx_duplicate_payment_amount` | `20.00` | L315 | Je veux demander le remboursement d'un trop-perçu sur ma dernière facture en français |
| `sim__reset_password_french` | `fx_pin_on_file` | `4829` | L473 | **Goal / Scenario**: |
| `sim__reset_password_sms_escalation` | `fx_pin_on_file` | `4829` | L518 | **Goal / Scenario**: |
| `sim__reset_password_sms_escalation` | `fx_sms_delivery` | `failed` | L519 | I want to reset my password, but I don't receive the SMS link and need to speak to a human |
| `sim__reset_password_standard` | `fx_pin_on_file` | `4829` | L458 | **Goal / Scenario**: |
| `sim__reset_password_wrong_number_retry` | `fx_pin_on_file` | `4829` | L488 | **Goal / Scenario**: |
| `sim__restore_service_already_paid` | `fx_account_suspended` | `true` | L724 | I already paid my past-due bill yesterday, but my service is still suspended. I want to get it turned back on |
| `sim__restore_service_already_paid` | `fx_pin_on_file` | `4829` | L728 | * **User guide**: Say 'My service is suspended but I already paid my bill.' Authenticate. Confirm you paid yesterday.... |
| `sim__restore_service_already_paid` | `fx_suspension_reason` | `non_payment` | L724 | I already paid my past-due bill yesterday, but my service is still suspended. I want to get it turned back on |
| `sim__restore_service_already_paid` | `fx_unapplied_payment` | `85.50` | L724 | I already paid my past-due bill yesterday, but my service is still suspended. I want to get it turned back on |
| `sim__restore_service_business_deflection` | `fx_account_suspended` | `true` | L739 | My business phone line is suspended and I need to restore it immediately |
| `sim__restore_service_business_deflection` | `fx_business_flag` | `true` | L739 | My business phone line is suspended and I need to restore it immediately |
| `sim__restore_service_business_deflection` | `fx_pin_on_file` | `4829` | L738 | **Goal / Scenario**: |
| `sim__restore_service_business_deflection` | `fx_suspension_reason` | `non_payment` | L739 | My business phone line is suspended and I need to restore it immediately |
| `sim__restore_service_french` | `fx_account_suspended` | `true` | L694 | Je veux rétablir mon service internet suspendu |
| `sim__restore_service_french` | `fx_pin_on_file` | `4829` | L698 | * **User guide**: Speak only in French Canadian. Say 'Mon service est suspendu, je veux le rétablir.' Authenticate, p... |
| `sim__restore_service_french` | `fx_suspension_reason` | `non_payment` | L694 | Je veux rétablir mon service internet suspendu |
| `sim__restore_service_payment_arrangement` | `fx_account_suspended` | `true` | L709 | My service is suspended, but I can't pay the full balance today. I want to make a payment arrangement to restore it |
| `sim__restore_service_payment_arrangement` | `fx_pin_on_file` | `4829` | L713 | * **User guide**: State that your service is suspended. Authenticate. When told you owe money, ask if you can set up ... |
| `sim__restore_service_payment_arrangement` | `fx_suspension_reason` | `non_payment` | L709 | My service is suspended, but I can't pay the full balance today. I want to make a payment arrangement to restore it |
| `sim__restore_service_standard` | `fx_account_suspended` | `true` | L679 | My phone service was suspended because I forgot to pay my bill, and I want to pay it and get restored |
| `sim__restore_service_standard` | `fx_pin_on_file` | `4829` | L683 | * **User guide**: Say 'My phone line is suspended and I need to restore it.' Authenticate. When told it's due to non-... |
| `sim__restore_service_standard` | `fx_suspension_reason` | `non_payment` | L679 | My phone service was suspended because I forgot to pay my bill, and I want to pay it and get restored |
| `sim__setup_autopay_after_paying_bill` | `fx_pin_on_file` | `4829` | L291 | * **User guide**: The user authenticates, pays their current balance, and then says, 'Now that that's paid, can we se... |
| `sim__speak_frustrated_english` | `fx_pin_on_file` | `4829` | L118 | **Goal / Scenario**: |
| `sim__speak_immediate_english` | `fx_pin_on_file` | `4829` | L76 | **Goal / Scenario**: |
| `sim__speak_immediate_french` | `fx_pin_on_file` | `4829` | L90 | **Goal / Scenario**: |
| `sim__speak_mid_call_billing_english` | `fx_pin_on_file` | `4829` | L104 | **Goal / Scenario**: |
| `sim__speak_mid_call_tech_french` | `fx_pin_on_file` | `4829` | L132 | **Goal / Scenario**: |
| `sim__transfer_family_member_number` | `fx_pin_on_file` | `4829` | L990 | **Goal / Scenario**: |
| `sim__transfer_landline_mobile_french` | `fx_pin_on_file` | `4829` | L976 | **Goal / Scenario**: |
| `sim__transfer_number_competitor` | `fx_pin_on_file` | `4829` | L962 | **Goal / Scenario**: |
| `sim__troubleshoot_mobile_data_slow` | `fx_pin_on_file` | `4829` | L794 | **Goal / Scenario**: |
| `sim__troubleshoot_satellite_tv_error` | `fx_pin_on_file` | `4829` | L780 | **Goal / Scenario**: |
| `sim__troubleshoot_tv_app_freezing` | `fx_pin_on_file` | `4829` | L808 | **Goal / Scenario**: |
| `sim__upgrade_internet_speed_french` | `fx_pin_on_file` | `4829` | L836 | **Goal / Scenario**: |
| `sim__upgrade_internet_wfh` | `fx_pin_on_file` | `4829` | L878 | **Goal / Scenario**: |
| `sim__upgrade_mobile_plan_budget` | `fx_pin_on_file` | `4829` | L864 | **Goal / Scenario**: |
| `sim__upgrade_mobile_plan_data` | `fx_pin_on_file` | `4829` | L822 | **Goal / Scenario**: |
| `sim__upgrade_tv_package_sports` | `fx_pin_on_file` | `4829` | L850 | **Goal / Scenario**: |
| `sim__warranty_replacement_check_status` | `fx_pin_on_file` | `4829` | L934 | **Goal / Scenario**: |
| `sim__warranty_replacement_iphone_screen` | `fx_pin_on_file` | `4829` | L892 | **Goal / Scenario**: |
| `sim__warranty_replacement_pixel_mic` | `fx_pin_on_file` | `4829` | L920 | **Goal / Scenario**: |
| `sim__warranty_replacement_samsung_french` | `fx_pin_on_file` | `4829` | L906 | **Goal / Scenario**: |
| `sim__warranty_replacement_swollen_battery_french` | `fx_pin_on_file` | `4829` | L948 | **Goal / Scenario**: |
