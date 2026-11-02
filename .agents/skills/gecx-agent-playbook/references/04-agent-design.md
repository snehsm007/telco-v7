# 04: Agent design rules (instructions, tools, callbacks, voice)

`docs/DESIGN_RULES.md` is the short list of what goes where, with the evidence
for each rule. This page adds the how-to detail. `make kickstart` writes a
scaffold that already follows both.

## Architecture
- **A router plus one specialist per PRD module.** The first agent (`router` in the scaffold) only greets, finds the account and routes. Each specialist owns complete journeys and logs the caller in itself when its task needs it (`docs/DESIGN_RULES.md` rules 1–2). For a Product Requirements Document (**PRD**) with one job, one agent is fine.
- **Keep the number of agents small.** Every extra agent adds:
  - extra handoff turns and multi-intent failures;
  - lost context across transfers, unless the handoff carries it (rule 4);
  - leaked internal agent names;
  - cross-turn **Hallucination Judge penalties** when a receiving agent speaks about an earlier turn's action without calling a tool on its first turn;
  - slower turns (~1–3 seconds extra per handoff in voice calls).
- Fold single-tool agents back into their parent, and avoid specialist → specialist handoffs: send the caller back to the router instead.
- Keep one list of caller goals, in the router's `<taxonomy>`, each naming the agent that handles it (rule 3).
- `childAgents` entries in agent JSON manifests must use the target agent's **directory name** (not display name), or `cxas push` will fail even if `cxas lint` passes.
- **Never transfer in the same turn as sending a login code (`DEF-33`).** In our first build, the front desk sent a code and transferred in one turn; the specialist then asked for the code on the next turn without calling a tool, and the Hallucination Judge scored that turn `Not Justified (0)`. With login inside the specialist (`docs/DESIGN_RULES.md` rule 2) and silent sub-agent transfers (while `handover_to_person` is a one-turn spoken handover + `end_session`, rule 7), this can't happen.

---

## Instructions (`instruction.txt`)
- Use the structured XML layout (`<role>`, `<persona>`, `<response_protocol>`, `<constraints>`, `<taskflow>`). Every step inside `<taskflow>` is `<subtask name="…">` → `<step name="…">` with **exactly one `<trigger>` (when) and one `<action>` (what)**. Full specification: `docs/INSTRUCTION_STYLE.md`.
- Note: `cxas lint` (rules I001/I002) only checks that `<step>` tags exist; it does not verify `<trigger>` and `<action>` children. Run `make llm-lint`, `make voice-audit`, and `cxas_prompt_linter.py` (see [13-commands](13-commands.md)) to enforce strict structure.
- Write triggers positively (`cxas lint` I004 warns on "not" in a trigger; the scaffold's triggers are already positive, and `make ci` fails on unwaived lint warnings): "the details are still missing", not "the caller has not described it".
- `<constraints>` holds invariants and prohibitions only—never multi-step procedures or tool call sequences. Explicitly forbid inventing or extrapolating any unreturned security rationale, fee/tax breakdown, timeline, or safety advice (learned in an earlier build).
- Put shared rules (persona, language, private data, handover, goodbye) in `global_instruction.txt` so they apply to every agent, and instruct the model to pass `language` (`en-US`, `fr-CA`, `es-US`) on every tool call from Turn 1 (`docs/DESIGN_RULES.md` rule 25).
- Refer to tools as `{@TOOL: name}` and agents as `{@AGENT: name}`.
- **Zero realistic example data in instructions, and never greet by `first_name` (`DEF-06`):** Never write example order numbers, dates, dollar amounts, card suffixes, or "e.g." sentences in `instruction.txt` (enforced by `overfit-check` `NUMBER_IN_PROMPT`). Never address, greet, or thank the caller by the `first_name` returned by `lookup_account` or login tools—fact-less simulated callers invent their own persona names and get derailed when addressed by the fake profile's `first_name`.
- **Design for fact-less simulated callers (`DEF-01`, `DEF-07`, `DEF-09`, Rule 21):**
  In the visible evaluation suites we have seen, roughly 30% of simulated callers (16 of 50 in one build) are given **no phone number, PIN, OTP, or credit card digits** in their scenario prompt:
  - **Send a code; don't ask callers to confirm mock data.** Never ask *"Is your phone number ending in [last 4] correct?"* or volunteer a card suffix before the caller states one. State the action (*"I've sent a code to the number on the account"*) or ask an open question, and accept whatever well-formed identifier or card suffix the caller gives.
  - **Include a `Code Not Received` step (`DEF-09`):** If the caller says they did not receive the login code, offer to resend once (`send_login_code`), then offer the alternate channel (`sms` ↔ `email`), then offer secret PIN verification (`check_secret_pin`) — never volunteer a live agent just because a code was not received.
  - **Re-identify when a caller corrects their phone or account number:** call `lookup_account` again with the new number at once rather than insisting on the first record (`lookup_account` accepts 9–10 digit numeric identifiers and synthesizes a phone number only when the identifier contains no letters, `not any(c.isalpha() for c in raw)`, Rule 22).
- **Act on explicit Turn-1 requests (`DEF-08`, `DEF-12`, `DEF-31`, `DEF-34`, `DEF-39`):** if a caller asks for a person on Turn 1 (*"Representative, please!"*), in a **single turn** speak the required transfer sentence (step-specific transfer wording if defined by the step, otherwise the generic closing line), call `handover_to_person`, and call `end_session` without forcing login first (`docs/DESIGN_RULES.md` rules 5, 7, 20, 25).

---

## Tools (Python) and session state
- **The model understands, Python decides.** The model converts caller speech into structured arguments (`intent="bill_dispute"`, `account_type="business"`). Python executes the business rules, fee calculations, and eligibility checks deterministically.
- **Tools read and write session state (confirmed live on 2026-10-08).** CES runs each tool file (`cxas_app/tools/*/python_function/python_code.py`) with a global `context` object whose `context.state` is a plain dictionary of the session's variables. What a tool writes there persists: the next tool call in the same turn sees it, and so do later turns. What does *not* survive is the tool's own Python memory (module globals, caches): each call starts fresh.
  - Read it as `context = globals().get("context")`, so a local test can set a module-level `context`. Don't declare a `context` parameter; the executor then calls the function in an unusual way. The scaffold's wrappers pass `state=getattr(context, "state", None)` to their `<tool>_impl`.
  - Declare every key a tool reads or writes in `app.json` `variableDeclarations` (`cxas lint` rule V100), with a type and a default (`language` MUST default to `""`, never `"en-US"`, Rule 25).
  - Whole numbers arrive as decimals (`5` reaches the tool as `5.0`). Convert with `read_count(state, key)` (`int(float(state.get("key") or 0))`).
  - Clear stale payment card state on decline (`state["card_last4"] = ""`, setting `state["declined_card_last4"] = last4` and `state["payment_declined_once"] = True`), and when a retry succeeds with another method, set `state["last_payment_method"]` to the PRD's exact value for that method (if the PRD says `"bank_account"`, never shorten it to `"bank"`), so follow-up tools never echo a declined card (Rules 24 and 27, learned in an earlier build).
- **One reply shape (`lib/replies.py`, rule 10).** `ok_reply(data, reference)` and `error_reply(code, message, agent_action, reference)` give every tool the same keys: `status`, `data`, `error_message`, `tracking_id`, plus `error` and `agent_action` on errors. Prompt triggers match `returned status="ok"` or `returned error="WRONG_CODE"`. A wrong answer is an error, never `status="ok"` with `verified=false`, so the model can't reach for the success line.
- **Money is a number plus a 2-decimal display string.** Return `amount: 85.5`, `amount_display: "85.50"` and `currency: "CAD"` (the generated `lib/replies.py` has `display_amount(value)` for the string), and have the prompt speak the display string. An agent once read a bare `85.5` aloud as "85.5 $".
- **Three deterministic patterns:**
  1. **P1: check inputs before acting.** Each tool validates its own arguments against the contract (9–10 digit numeric phone/account ID in `lookup_account`, with no phone synthesized from an identifier that contains letters; 3-attempt login ladder for 4–10 digit codes in `check_login_code`/`check_secret_pin` per Rule 21) and returns an error with an `agent_action` hint instead of acting.
  2. **P2: confirm only after success.** A state-changing tool returns `status: "ok"` plus the facts to confirm (reference number, amount), never a sentence, and nothing confirmable on error. The prompt holds the success line with the failure line right next to it (`docs/DESIGN_RULES.md` rules 5–6).
  3. **P3: one tool per fixed sequence (`DEF-04`).** When the model calls several tools in one turn, they all run before any result comes back, so a later call can't depend on an earlier one's outcome. When a workflow needs a fixed order `A → B → C` (pay a past-due balance → restore service → send the receipt), chain it inside tool `A`. Money-moving tools check `logged_in` in `context.state` themselves (`NOT_LOGGED_IN`), while login tools never gate on `NOT_IDENTIFIED` or `CODE_NOT_SENT` and auto-populate the default profile when `account_id` is empty (Rule 21).
- **Two-step confirmations check their input (`DEF-07`, `DEF-16`).** A tool such as cancel-service completes only when called with `caller_confirmed=True`; the first call (or preceding lookup/auth tool) returns the disclosure facts so they are grounded in the transcript before the agent asks for confirmation.
- **Float-safe digit normalization (`normalize_code`, Rule 22):** text simulators send keypad digits with spaces (`"4 8 2 9 1 3"`), and CES can coerce numeric string arguments to floats (`"384920.0"`). Always call `normalize_code(value)` (which converts ints/floats and strips trailing `.0` via `re.sub(r"\.0+$", "", s)` before `re.sub(r"\D", "", s)`) so `"384920.0"` becomes `"384920"`, not `"3849200"` (`DEF-04`).

---

## Ground every spoken fact in tool output (domain-scoped, no embellishments)
The CES Hallucination Judge compares every factual statement spoken by the agent against the tool responses in the conversation. A true PRD policy that no tool returned still scores `Not Justified (0)` (`DEF-06`, `DEF-30`, `DEF-35`, `DEF-41`).
- Have each tool return the fee, tax note, timeline, eligibility result, and channel list that belong to its own domain workflow (`fee: 0.0`, `fee_display: "0.00"`, `currency: "USD"`, `resolution_business_days: 5`, `activation: "immediate"`), and pre-ground two-step confirmation policies in the lookup/login tool when disclosed before the action tool. Never dump unrelated constants into every tool.
- Keep separate facts in separate fields (a plan's `activation` apart from a device's `delivery_eta`), so the model never merges them into a date nobody returned.
- When two tools mention the same reference number (a ticket and the handover that carries it), make both return the same value (`DEF-32`, `DEF-33`).
- In `<constraints>`, forbid inventing or extrapolating any security explanation, fee/tax breakdown, timeline, or safety advice not returned in a tool payload.

---

## Bilingual (`fr-CA` / `es-US`) calls: prompt owns sentences, with the `handover_to_person` exception
In bilingual evaluations (such as Canadian French `fr-CA` or US Spanish `es-US`), one English phrase the agent repeats from a tool output—like `"mobile number ending in …"` or `"text message"` instead of `"texto"`—fails the strict language-lock expectation (`DEF-13`, `DEF-14 Bucket 1`, `DEF-25`).
1. **Ordinary tools return data, never sentences — with the single exception of `handover_to_person` (`docs/DESIGN_RULES.md` rules 5 and 25).** Ordinary tools return codes, numbers, dates and masked digits (`destination_last4: "1234"`, `amount: 85.5` with `amount_display: "85.50"`, `status: "declined"`). **Single exception:** `handover_to_person` looks up `SPOKEN_LINES[lang]["handover"]` (`en-US`, `fr-CA`, `es-US`). The language comes from, in order: an explicit `language` argument, the session's `language` value, French/Spanish markers in the caller's words (`session_context`, `reason`, `target_queue`), the profile's `preferred_language`, then `en-US`. It sets `state["handover_complete"] = True` and `state["handoff_message"] = spoken`, and returns `spoken_message` and `handoff_message` so `speech_hygiene` can speak it if the model emits a tool-only turn (`DEF-12`). Always declare `language` with `"default": ""` in `app.json` (never `"en-US"`).
2. **Every fixed line lives in the prompt, in every language the PRD needs.** Write the English, French and Spanish versions of each required sentence next to each other in the step that speaks it, with its failure line beside its success line, and tell the model to keep them word for word (`docs/DESIGN_RULES.md` rules 5–6). `make kickstart LANGUAGES=…` writes one line per language and marks any language it has no wording for with `[translate: …]`.
3. **Regional and currency details (`DEF-14`, `DEF-40`):** handle regional rules in tool logic, and return amounts as a number plus a 2-decimal display string and a currency code so the prompt can say them correctly in the caller's language.

---

## Shared code and bundling (`lib/` + `suite/bundle.py`)
Each tool and callback executes as a single standalone Python file on CES. Write shared code in `lib/` (the scaffold has `fakes.py`, `replies.py`, `services.py`, `speech.py`) and run `make bundle` (`suite/bundle.py`), which copies the `lib.*` code each file uses into a generated block below `# DO NOT MODIFY CODE BELOW THIS LINE`.
- **Three bundler rules that prevent runtime `NameError` / `TypeError` crashes:**
  1. **Import alias rewriting:** If a tool uses `from lib.services import foo_impl as _foo_impl`, `suite/bundle.py` binds the alias `_foo_impl = foo_impl` after inlining `def foo_impl(...)`. Always run `make ci` after adding imports.
  2. **No duplicate helper names across `lib/*.py`:** when bundled into one file, a later definition would silently overwrite an earlier one, so `suite/bundle.py` fails on duplicates (`DEF-15`).
  3. **Match wrapper signatures:** each tool wrapper above the marker must take the same parameters as its `<tool>_impl` in `lib/services.py`, apart from the injected `state`. `make bundle-check` fails on a mismatch, with a message and exit code 1.

---

## Callbacks: keep only `speech_hygiene` (`after_model_callback`)
- The scaffold attaches one after-model callback, `speech_hygiene`, to every agent. It performs two jobs:
  1. Runs `clean_speech` from `lib/speech.py` on each text part of the reply (stripping markdown symbols and leaked snake_case identifiers, and cutting numbers of 9 or more digits to their last 4).
  2. When `state.get("handover_complete")` is true and the model emitted a tool-only turn (`handover_to_person` + `end_session` with no text part), injects `state["handoff_message"]` into `llm_response.content.parts` (`DEF-12`). It only fills an empty reply: it never replaces or rewrites text the model spoke, so step-specific or PRD-exact transfer lines survive.
- **Attach `speech_hygiene` to every agent.** Root-agent callbacks do **not** run while a sub-agent is active.
- **Never add `before_tool` `auth_gate` (`NOT_IDENTIFIED`) or `before_model` `turn_state` callbacks (`docs/DESIGN_RULES.md` rule 16).** See the dead ends below. Enforce `NOT_LOGGED_IN` inside money-moving tools instead.
- Callback signatures must be typed as `cxas lint` expects, with the typing import (rule C008): `after_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> Optional[LlmResponse]`.

---

## Three Dead Ends (Don't Build These)
Each of these looked like a safety improvement and was removed again.
1. **A `before_tool` gate that blocks login tools until the account is found (`NOT_IDENTIFIED`).** Measured in `telco-rebuild`: strict `3/3` fell from `41/50` (`full-b5f6c72`) to `32/50` (`full-1376555`), majority `48/50` → `45/50`, individual `138/150` → `126/150`. It trapped fact-less callers (about a third of the visible tests give the caller no phone or account number) in a loop asking for an identifier they didn't have. Instead, login tools fall back to the default fake account, and money-moving tools check `logged_in` themselves.
2. **A `before_model` callback that writes session state on every turn (a turn counter).** Measured in `telco-rebuild`: `37/50` strict (`full-f2f45a8`), still `-4` below the `41/50` baseline. The judge scored the state-change events it wrote into the conversation as "silent turns". Instead, change state only inside tools, next to the tool result that explains it.
3. **A separate deterministic login agent driven by a task queue** (the router only sets an intent, callbacks push a login task and transfer every caller to a dedicated login agent first). **Not measured** — no run backs this; it was rejected on design grounds. It would block callers whose request needs no login (fraud reports, outage checks, transfers to a person on Turn 1), and every extra agent-to-agent transfer adds a turn where the receiving agent speaks without calling a tool (`DEF-33`). Keep the thin router and specialist-owned login (rules 1–2), and enforce login inside the tools.

---

## Voice Rules (`gemini-composite-v1`)
- Keep spoken replies concise (1–3 sentences), plain text only, with numbers grouped naturally (`"2 0 2, 5 5 5, 0 1 4 3"`).
- Always reply audibly to short acknowledgements (`"okay"`, `"yeah"`), and resume cleanly after barge-in interruptions.
- Set `noiseSuppressionLevel: "HIGH"` on both the app's default channel profile and phone deployments to prevent line noise from triggering false barge-ins.
- Configure a per-language **Director's Note** and SCRAPI-compliant accent label (`"French Canadian"` for `fr-CA`, `"Spanish accent"` for `es-US`) on `gemini-composite-v1`, verified via `make voice-audit`.
- `cxas lint` warns (T014) when a tool's description has no spoken pacing phrase (a short filler line said before a slow tool runs). The kit waives T014 in `lint_waivers.json` because a pre-tool filler line made the model skip the tool call. `make ci` (through `scripts/lint_check.py`) fails on any `cxas lint` warning that is not listed in `lint_waivers.json` (rule ID → reason), and a fresh scaffold passes with 0 unwaived warnings. Add a waiver only with a written reason.
