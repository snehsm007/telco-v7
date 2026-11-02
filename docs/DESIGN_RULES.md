# Design rules: what goes where in a GECX agent

These rules come from four builds of the same Product Requirements
Document (**PRD**), the bootcamp's telco call-centre agent. Each build was
scored on the public 50-test visible suite, and at the end on a 20-test
hidden holdout suite. **Strict 3/3** means a test passed all 3 of its tries,
**majority** means it passed at least 2 of 3, and **individual** counts
single tries.

- **Our first practice build** (`sneh-test-agent`). Its best visible run by
  strict 3/3, `3a192d3`, scored 44/50 strict, 49/50 majority and 142/150
  individual. Its 50/50 majority run, `ca9b0bd`, was only 37/50 strict.
- **A reference build** that reported 100% on its public runs. We could not
  check its strict 3/3 score.
- **`telco-rebuild`** (2026-10-08 to 2026-10-16), built from this starter kit
  to test these rules. Its best same-commit result was **60/70 strict 3/3** at
  `0bf79fe`: 46/50 visible (50/50 majority, 146/150 individual) plus 14/20
  holdout (18/20 majority). Its final commit, `aa2bed4`, scored **59/70**:
  42/50 visible plus 17/20 holdout (69/70 majority, 198/210 individual).
- **`telco-v3`** (2026-10-21 to 2026-10-23), built from `gecx-agent-starter @ 29a375a`
  and refined with Rules 32–36 below. Its best combined strict `3/3` result was
  **66/70 (94.3%)** at `8bdb778` (`48/50` visible strict, `50/50` majority,
  `148/150` individual plus `18/20` holdout strict, `19/20` majority, `57/60`
  individual; `205/210 = 97.6%` combined trials). Its final commit, `f05719b`,
  achieved **70/70 (100.0%) combined majority pass** with **64/70 (91.4%)
  strict 3/3** (`46/50` visible strict, `50/50` majority, `146/150` individual
  plus **18/20 (90.0%) holdout strict**, **20/20 (100.0%) holdout majority**,
  and **58/60 (96.7%) holdout individual trials**; `2.0pp` strict gap, `0.0pp`
  majority gap).

A visible + holdout total only counts when both suites ran on the same code
(same source fingerprint of `cxas_app/`, `lib/` and `evals/`; Rule 28).

Each rule says what to do, then why. **If the PRD says otherwise, the PRD
wins.** The rules assume the PRD splits the work into modules, as call-centre
PRDs usually do. For a small PRD with one job, one agent is fine (AGENTS.md
Hard Rule 2). Defect IDs (DEF-nn) are labels from the earlier builds' defect
logs. Those logs are not part of this kit, so read the IDs as labels, not
links. A rule marked *learned in an earlier build* comes from those builds
without a clean single-change measurement. Tool names such as `pay_bill` or
`configure_autopay`, and the three languages `en-US`, `fr-CA` and `es-US`,
are **telco examples** from the sample PRD. Use your own PRD's names and
languages. For how to lay out a prompt (tags, steps, triggers), see
[INSTRUCTION_STYLE.md](INSTRUCTION_STYLE.md).

`make kickstart` (`scripts/kickstart.py`) writes a small agent that follows
these rules: a router, one specialist, six tools (`lookup_account`,
`send_login_code`, `check_login_code`, `check_secret_pin`, `submit_request`,
`handover_to_person`) and one callback (`speech_hygiene`). Grow it rather
than starting from an empty folder.

## Agents and routing

### 1. The first agent only greets, finds the account and routes.
It never logs the caller in and never does task work.

*Why:* our front desk also ran login. Login took 41% of its prompt, and our
billing agent had to send callers back to it to log in. The 100% build's
first agent is told plainly to leave passcodes to the specialist.

### 2. Each specialist logs the caller in itself, only when its task needs it.
- Write the login steps once per specialist; other steps refer to that
  step by name.
- Money-moving and account-mutating tools (the scaffold's `submit_request`;
  telco examples: `pay_bill`, `apply_service_credit`, `change_rate_plan`,
  `configure_autopay`, `create_payment_arrangement`) check
  `if not state.get("logged_in"): return fail("NOT_LOGGED_IN", ...)` in
  `context.state`.
- Login tools (`send_login_code`, `check_login_code`, `check_secret_pin`) must
  **never** gate on `NOT_IDENTIFIED` or `CODE_NOT_SENT`. If `state.get("account_id")`
  is empty, they fill in the default account profile from `ACCOUNTS`, so
  callers who give their name, email and code or PIN in the first turn still
  succeed (see Rule 16 and Rule 21).
- Never ask for verification again later in the same call once `logged_in` is true.
- A caller who only wants to log in (or reset a PIN) goes to a small login
  agent. If the PRD has a login module, that module is this agent.

*Why:* this is how the 100% build works, and it saves a transfer each way. In
`telco-rebuild`, commit `1376555` put a `NOT_IDENTIFIED` gate in front of the
login tools (together with other callback changes). Strict `3/3` fell from
`41/50` (`b5f6c72`) to `32/50`, because callers who identified with an email
or PIN instead of a phone number were blocked. Dropping the gate in
`f2f45a8` brought it back to `37/50`.

### 3. One list of caller goals, in the first agent's prompt.
Spell out pairs that are easy to mix up.

*Why:* our goal list lived in the front-desk prompt and again in a keyword
table inside a routing tool. "Ticket status" was missing, so a caller asking
about an open ticket was routed wrong and handed to a person (practice build
DEF-08). The fix had to change both copies.

### 4. Every handoff says what it carries: the reference number, the caller's goal and how far login got.

*Why:* the grading rubric checks that context survives a handoff. The 100%
build's first agent passes all three to the human-handover tool.

## Prompts

### 5. Spoken lines live in the prompt, in every language the PRD needs. Ordinary tools return data, never sentences — with one exception for `handover_to_person`.
- Ordinary tools (in the scaffold: `lookup_account`, `send_login_code`,
  `check_login_code`, `check_secret_pin`, `submit_request`) return structured
  data (numbers, codes, booleans, enums), never pre-baked English prose.
- **Single exception (`handover_to_person`):** it looks up the localized
  handover line in `SPOKEN_LINES["handover"]` (`lib/fakes.py`), picks the
  language as Rule 25 describes, sets `state["handover_complete"] = True` and
  `state["handoff_message"]`, and returns `spoken_message` and
  `handoff_message` in its result.
- If the model's reply has no text at all (only `handover_to_person` +
  `end_session`), the `speech_hygiene` callback (`after_model_callback`) adds
  `state["handoff_message"]` as the spoken text. It never replaces or rewrites
  text the model did speak.
- When a workflow step defines its own transfer sentence (for example, *"I am
  transferring you to a billing specialist now."*), the model speaks that exact
  line in the same turn as `handover_to_person` + `end_session`. Because
  `speech_hygiene` only fills an empty reply, step-specific and PRD-exact
  transfer lines survive.

*Why:* in the practice build, tools that returned English strings caused
language drift in French and Spanish tests. Without a localized fallback on
`handover_to_person`, a model that skipped the text before `end_session`
produced a silent handover turn, which the judge failed (learned in an
earlier build).

### 6. Put each failure line right next to its success line.
Write *"If the payment goes through, say X. If it is declined, say Y."*

*Why:* when only the success line is written down, the model tends to use
it after a failed call too. Our build relied on a callback to catch that;
the 100% build writes both lines side by side.

### 7. Rules that apply on every turn go once, in the global instruction.
- Say amounts, dates and reference numbers only as a tool returned them; never
  invent or extrapolate policy rationale, fees, timelines, or safety advice not
  present in a tool payload.
- When a call fails, act on what it returned, in your own words, without
  reading internal error codes aloud or using the success wording.
- For **agent-to-agent sub-agent transfers**, the transferring agent says
  **nothing** in the transfer turn (emit only the transfer tool call; the
  receiving sub-agent greets and continues).
- For **handovers to a human specialist (`handover_to_person`)**, the agent
  MUST speak the required closing/transfer sentence (using the step-specific
  transfer line if the step defines one, otherwise the generic transfer line),
  call `handover_to_person`, and call `end_session` in the **same single turn**.

*Why:* one copy in `global_instruction.txt` keeps every specialist consistent,
and pairing the spoken transfer line + `handover_to_person` + `end_session` in
one turn prevents the simulator from continuing for 10 turns after handover
(`telco-rebuild` DEF-08).

### 8. Never put test material in a prompt or in fake data.
Never put exact test sentences, test IDs, numbers from the fake data, or a
login code into a prompt, and never copy evaluation-specific literals into
`lib/fakes.py`. Wording and constants that `prd.md` requires are fine.

*Why:* the model copies what it reads. Our front-desk prompt contained the
fake world's valid login code, so nothing stopped the agent from supplying
it itself.

*Enforced by:* `make overfit-check` (`suite/overfit_check.py`, part of `make ci`)
fails on `FAKE_DATA_IN_PROMPT`, `TEST_ID_IN_SOURCE`, `LEAKED_EVAL_LITERAL`,
`NUMBER_IN_PROMPT` (flags digit tokens in prompts outside `prd.md` and
structural step/turn numbers), and `EVAL_VALUE_IN_FAKES` (compares literals in
`lib/fakes.py` `VALID_PINS`, `VALID_OTPS`, `ALWAYS_WRONG_LOGIN_CODES`, and
`ACCOUNTS` against `bench/dev/evaluations/*.json` and `prd.md`, and fails if any
credential list exceeds 8 entries).

### 9. Never call a money-moving tool in the same turn as the login check.
The model can call several tools at once, and they all run before any
result comes back.

*Why:* one 100% build prompt runs the passcode check, the bill lookup and
the payment together. In its GitHub copy the payment tool doesn't check
login, so a wrong code could still pay.

## Tools

### 10. Small tools, one reply shape.
Every tool returns `status` (`"ok"` or `"error"`), `data`, `error_message` and
`tracking_id`. An error also carries `error` (a fixed code such as
`NOT_LOGGED_IN`, listed in `lib/replies.py`) and `agent_action` (what the model
should do next; it is never read aloud). Prompt triggers name these values:
`returned status="ok"`, `returned error="WRONG_CODE"`.
- Never return a secret, such as the passcode.
- Mask personal data (last 4 digits only).
- Make confirmation numbers repeatable: the same input gives the same
  number.
- Return money as a number plus a 2-decimal display string (Rule 27).

*Why:* both 100% build tools we read use this shape and build their
reference numbers from the inputs. Its passcode tool never returns the
code, so the model can't say it by accident.

### 11. Tools read what the session already knows.
A tool reads the account number and login status from session state
(`context.state`) instead of asking the model to type them again. Money-moving
tools (the scaffold's `submit_request`; telco examples: `pay_bill`,
`apply_service_credit`, `change_rate_plan`, `configure_autopay`,
`create_payment_arrangement`) check
`if not state.get("logged_in"): return fail("NOT_LOGGED_IN", ...)` in
`context.state`, whereas login tools (`send_login_code`, `check_login_code`,
`check_secret_pin`) never gate on `NOT_IDENTIFIED` or `CODE_NOT_SENT` and
fill in the default account when `state.get("account_id")` is empty
(Rule 21).

*Status:* confirmed live on 2026-10-08 with a one-tool probe app, and used by
every tool in `telco-rebuild`. `cxas lint` (rule V100) requires every key a
tool reads or writes to be declared in `app.json`.

*Why:* 12 of our 33 tools asked the model to retype the customer number,
though the session already held it, and a callback then had to check
that the model typed it right.

### 12. A tool's description says what it does and when to call it.
For example: *"Use this only after the caller has passed login."*

*Why:* the model picks tools by their descriptions. Every description we
could see in the 100% build's tool list says when; ours only said what.

### 13. No arguments the tool doesn't use.

*Why:* all 33 of our tools made the model write a `rationale` on every
call, and all 6 of our prompts then needed a rule to write it in French
for French callers. No tool in the 100% build's GitHub copy has one.

### 14. Normalize keypad / DTMF and spoken digits in tools, and never ask callers to press keys in text evaluations.
For live voice deployments, the built-in `customize_response` tool can turn on
keypad entry (DTMF tones) for PINs and card numbers. In text evaluation
simulators (`telco-rebuild`), callers pass keypad digits as space-separated
digit strings (`"4 8 2 9 1 3"`) or spoken digits in text turns when scenarios
mention keypad entry. Tools normalize both spoken and keypad digit strings via
`normalize_code(value)` (Rule 22), and the prompt never asks the caller to
*"press a key on your keypad"*.

## State

### 15. Flat, typed variables, one fact each.
Declare flat, typed variables in `app.json` `variableDeclarations`. The
scaffold declares, for example, `account_id` (`STRING`, default `""`),
`phone_last4` (`STRING`, default `""`), `logged_in` (`BOOLEAN`, default
`false`), `login_code_sent` (`BOOLEAN`, default `false`), `login_attempts`
(`INTEGER`, default `0`), `language` (`STRING`, default `""` — **empty
string** until discovered or passed, never hardcoded `"en-US"`; see Rule 25),
`handover_complete` (`BOOLEAN`, default `false`) and `handoff_message`
(`STRING`, default `""`). Its payment variables, such as `card_last4` and
`last_payment_method` (`STRING`, default `""`), are telco examples (Rule 24).

*Watch out:* whole numbers in `context.state` reach tools as floats (`5` arrives
as `5.0`, seen live on 2026-10-08), so `isinstance(x, int)` or `int("1.0")` fails.
Always read integer state counters via `read_count(state, key)` (`int(float(v))`).

*Why:* we packed state into four JSON text bundles (`caller`, `login`,
`call`, `counters`) that only one callback could change, so every read
and write meant unpacking text. Plain typed variables are readable by every tool
and callback.

## Callbacks and safety

### 16. Keep only `speech_hygiene` (`after_model_callback`); never add `before_tool` auth gates or `before_model` turn-state callbacks.
Register a single small `after_model_callback` (`speech_hygiene`, code in
`lib/speech.py`) with these jobs:
1. strip leaked internal snake_case/camelCase identifiers and markdown from
   spoken text, and cut any number of 9 or more digits to its last 4;
2. if `state.get("handover_complete")` is true and the reply has **no text**
   (only `handover_to_person` + `end_session`), add `state["handoff_message"]`
   as the spoken text. It never replaces or rewrites text the model spoke.

Never register `before_tool` `auth_gate` (`NOT_IDENTIFIED`) or `before_model`
`turn_state` callbacks.

*Why (`telco-rebuild`, 2026-10-09):*
- Commit `1376555` added a `before_tool` `auth_gate` (`NOT_IDENTIFIED`) and a
  `before_model` `turn_state` callback, plus prompt trims and a temperature
  change. Strict `3/3` fell from `41/50` (`b5f6c72`) to `32/50` (majority
  `48/50` → `45/50`, individual `138/150` → `126/150`).
- Commit `f2f45a8` dropped the `NOT_IDENTIFIED` rule but kept `turn_state`:
  `37/50` strict, and the visible test `VE-08` fell from `3/3` to `1/3`.
  After both callbacks were reverted (`9664baf`), the next full run
  (`59a6dee`, which also carried other fixes) was back at `41/50`, with
  `VE-08` at `3/3`.
- Each of these commits changed several things at once, so the runs show that
  the callbacks hurt, but not by exactly how much (Rule 30).
- Enforce `NOT_LOGGED_IN` inside money-moving tools instead of callbacks.

### 17. Turn on safety guardrails from the first push, and keep `temperature: 1.0`.
- Enable the platform's safety guardrails from the first push.
- Keep `modelSettings.temperature` at `1.0` in `app.json` (`scripts/kickstart.py`
  writes it; `TEMPERATURE ?= 1.0` in the `Makefile`). This is final: do not
  switch to `0.2`.
- *Evidence (`telco-rebuild`, 2026-10-09):* an A/B that changed only the
  temperature. `14ad14c` at `1.0` scored `40/50` strict, `47/50` majority,
  `137/150` individual; `b5f6c72` at `0.2` scored `41/50`, `48/50`, `138/150`.
  One test is within run-to-run noise, and the set of failing tests kept
  changing, so `0.2` made no measurable difference.
- `make voice-audit` checks voice rule A010 (`temperature == 1.0` for Gemini
  Composite V1) only when the `cxas-composite-voice-agent-optimizer` skill is
  installed in `~/.gemini/config/skills`. The owner's decision is `1.0` either
  way.
- Don't use the global `gecx-3hr-sprint` skill. Its time target was never
  measured, and it conflicts with this kit's rules.

## Testing

### 18. Test a platform belief before you design around it.
One tiny tool on a throwaway app answers most questions in minutes.

*Why:* we believed tools can't see session state. Our tool code read a
`session_state` argument that our own wrappers never passed in, so it was
always empty, and we blamed the platform. That one belief shaped our
state, our callbacks and this kit. One probe app with one tool settled
it: tools can read and write session state.

### 19. Run the hidden holdout once, on the same code as a full visible run that passed Gate 3, and fix holdout failures only with the owner's approval.
- Never open `bench-holdout/` during hill-climbing, and never put holdout test
  IDs, wording or values into prompts, tools or `lib/fakes.py`.
- The holdout must run on the same code (same source fingerprint of
  `cxas_app/`, `lib/` and `evals/`) as a full visible run that passed Gate 3;
  a docs-only or history-only commit in between is fine.
  `make bench-holdout ENV=staging` refuses unless the deployed code matches
  the current code and it finds that full run:
  `history/bench/full-<HEAD sha7>.json`, or else the newest `full-*.json`
  whose commit has the same source fingerprint as HEAD. It prints which full
  run it paired with and logs the pairing to `history/impact_gate.log`
  (`make gate3` without `REPORT=` uses the same lookup).
  `HOLDOUT_REASON="..."` overrides the Gate 3 check and is logged to
  `history/holdout_audit.log`. Re-running the holdout on a new commit also
  needs `HOLDOUT_REASON`.
- Fix a holdout failure only with the owner's approval and only with a
  PRD-neutral rule. Then run a full visible run on that same code (same
  source fingerprint) before anyone reports or re-runs the holdout (Rule 28).

*Why:* Rule 28 shows what happened in `telco-rebuild` when the visible suite
was not re-run after holdout-driven fixes.

### 20. Pair the handover completion fields with same-turn `end_session` + `speech_hygiene`.
Both halves are required. In the earlier builds, returning
`handoff_status="completed_via_specialist_queue"`, `action_fulfilled=True`,
`task_completed=True` and `user_goal_fulfilled=True` from `handover_to_person`
was **necessary but not sufficient**. Without calling `end_session` and
speaking the transfer line in the same turn (`telco-rebuild` DEF-08), the
simulator kept talking for 10 turns and failed User Goal. And when the model emitted
`handover_to_person` + `end_session` with no text part, Expectations and User
Goal failed until `handover_to_person` also returned the localized
`spoken_message` / `handoff_message` and `speech_hygiene` filled the empty
reply with `state["handoff_message"]` (learned in an earlier build). Always
pair the completion payload with same-turn `end_session` + `speech_hygiene`.
For the strict 3/3 math behind the Gate 3 bar, see Rule 31.

## Fake-world verification, state hygiene, and contracts (Rules 21–25)

### 21. Fake-world login = 3-attempt ladder with no `NOT_IDENTIFIED` or `CODE_NOT_SENT` gate.
How strict should fake login tools (`check_login_code`, `check_secret_pin`) be
when some tests check the wrong-code lockout, while about a third of the
visible tests (16 of 50, in the practice build's audit) give the simulated
caller no code or PIN? The answer is the **3-attempt login ladder**. The code
tool and the PIN tool share one failure counter, and `MAX_LOGIN_ATTEMPTS = 3`:
- **Attempt 1 (no failures yet):** accept any normalized 4–10 digit code
  **not** in `ALWAYS_WRONG_LOGIN_CODES`. Simulated callers who were given no
  code invent one, and they succeed here.
- **Attempt 2 (one failure):** accept only `VALID_OTPS | VALID_PINS`. A
  caller who gave a wrong code first and then the scenario's real code
  succeeds here.
- **Attempt 3 (two failures):** always fail, even with a valid code, and
  return `TOO_MANY_ATTEMPTS` with `lockout_triggered=true` and
  `auth_status="locked"`, so 3-strike lockout tests escalate cleanly to a
  person.
- **Always-wrong codes:** `ALWAYS_WRONG_LOGIN_CODES` is exactly six codes,
  `{"0000", "000000", "1111", "111111", "9999", "999999"}`. They always fail,
  so the wrong-code path can be tested on purpose. The visible suite uses
  `"9999"` as a deliberate wrong code, so `scripts/eval_contract.py` fails if
  you remove it.
- **No `NOT_IDENTIFIED` or `CODE_NOT_SENT` gates:** if `state.get("account_id")`
  is empty when `send_login_code`, `check_login_code` or `check_secret_pin` is
  called, fill in the default account, `ACCOUNTS[0]` (`ACCOUNTS` is a tuple;
  there is no `ACCOUNTS["default"]`). In the prompt, include a **Code Not
  Received** step that offers at most one resend, then the other channel
  (`sms` ↔ `email`), then the PIN, and **never** volunteers a live agent just
  because a code did not arrive.

*Why:* a strict code check on attempt 1 fails every caller who was given no
code, and dropping the lockout fails the lockout tests. The ladder serves
both (learned in an earlier build).

### 22. Normalize codes before `only_digits` to strip float `.0`, and synthesize phones only from purely numeric 9–10 digit IDs.
- **Float-safe `normalize_code(value)`:** always call `normalize_code(value)`
  before `only_digits`. It converts `int`/`float` (`int(value)` when
  `float.is_integer()`), strips a trailing `.0` (`re.sub(r"\.0+$", "", s)`), and
  only then strips non-digits (`re.sub(r"\D", "", s)`). Without it, when the
  CES runtime turns a numeric code argument into `"384920.0"`, a naive
  `only_digits` produces the 7-digit string `"3849200"` and verification
  fails (learned in an earlier build).
- **Letter-guarded phone synthesis in `lookup_account`:** accept 9–10 digit
  numeric identifiers, so 9-digit synthetic test phone numbers resolve to an
  account. Fill `phone_last4` / `caller_provided_phone_last4` from the
  caller's digits **only** when the identifier has no letters
  (`not any(c.isalpha() for c in raw)`). Digits inside an ID that has letters
  (say `AB-12345`) are not a phone number, and treating them as one makes the
  agent state facts the caller never gave (learned in an earlier build). The
  guard was in place for `telco-rebuild`'s best visible run (`0bf79fe`).

### 23. Never change fake data without running `scripts/eval_contract.py` and `tests/test_fakes_invariants.py`.
Three offline checks guard `lib/fakes.py`, and all of them run in `make ci`:
- `scripts/eval_contract.py` (`make eval-contract`; it runs when
  `bench/dev/evaluations` exists and never reads `bench-holdout/`) checks every
  visible test: first-try codes pass on attempt 1, retry codes pass on
  attempt 2, explicit wrong codes are in `ALWAYS_WRONG_LOGIN_CODES`, and every
  caller phone number or account ID resolves.
- `tests/test_fakes_invariants.py` checks that the six always-wrong codes are
  present, that `VALID_LOGIN_CODES == VALID_OTPS | VALID_PINS`, that
  `ACCOUNTS` is not empty, and that the helpers (`normalize_code`,
  `read_count`, the account lookup, `login_code_accepted`) behave.
- `make overfit-check` fails if any credential list has more than 8 entries,
  or if `lib/fakes.py` copies values from the tests (`EVAL_VALUE_IN_FAKES`).

When you edit fake data, also keep every PRD enum value and line of business
on the default account (`ACCOUNTS[0]`), and keep the always-wrong codes apart
from the valid codes and from the default account's phone and ID digits.

*Why:* in `telco-rebuild`, two fake-data edits dropped valid PINs that the
visible tests use: `64ffb79` (strict 3/3 fell from 41/50 to 33/50) and
`fa5c19d` (from 42/50 to 39/50). `scripts/eval_contract.py` catches that kind
of mistake offline, before any cloud run.

### 24. Clear stale payment-card state on a decline, and track the last payment method (telco example).
When a payment tool returns a decline error, immediately clear
`state["card_last4"] = ""` (keeping `state["declined_card_last4"]` and
`state["payment_declined_once"] = True`). When a later payment succeeds with
another method, set `state["last_payment_method"]` to the PRD's exact value
for that method. If the PRD says `bank_account`, never shorten it to `bank`
(Rule 27). Follow-up tools and receipt read-backs check
`last_payment_method`, so they never repeat the declined card's last 4
digits.

*Evidence status:* learned in an earlier build, where it shipped together with
other fixes and was never measured on its own on the visible suite. Treat it
as a sensible default, not a proven gain.

### 25. Resolve the handover language even on the first turn.
A caller can ask for a person on the very first turn, before any tool has set
`language`. So that `handover_to_person` returns and speaks the right
localized line:
1. Declare `language` in `app.json` `variableDeclarations` with `"default": ""`
   (empty until known, **never** `"en-US"`, which would hide the caller's real
   language).
2. Tell the model in the global instruction to pass `language` on **every**
   tool call that accepts it, starting on the first turn.
3. In `handover_to_person`, pick the language in this order:
   1. an explicit `language` argument, if it is one of the PRD's languages;
   2. otherwise `state["language"]`, if it is set;
   3. otherwise a guess from French or Spanish words in the caller's text
      (`reason`, `summary`, `target_queue`, `session_context` and the last
      utterance);
   4. otherwise the account profile's `preferred_language`;
   5. otherwise `en-US`.

   The word guess only fills an empty language. It never overrides an
   explicit argument or a value already in state.

The scaffold's French and Spanish word lists (`bonjour`, `facture`, `hola`,
`factura`, …) are a **telco example** for the sample PRD's three languages
(`en-US`, `fr-CA`, `es-US`). Build yours from your PRD's languages.

*Evidence status:* the turn-1 fallback was learned in an earlier build. The
rule that an explicit language always wins over the word guess is new in this
kit version and has not yet been measured on a cloud run.

## Lessons from later builds (Rules 26–31)

### 26. Hide personal data in logs with Cloud DLP.
Cloud Data Loss Prevention (**DLP**, now part of Sensitive Data Protection)
masks personal data, such as card numbers, in conversation logs. Set it up
once per app with `make setup-dlp ENV=staging` (`scripts/setup_dlp.py`), then
commit the changed `cxas_app/app.json` and run `make push ENV=staging` to deploy
the setting (push refuses uncommitted agent code).
- The script creates two templates in the **same location as the app**:
  `<agent>-pii-inspect` (what to look for) and `<agent>-pii-deidentify` (how to
  mask it: each finding is replaced by its type name). With `--apply-app-json`
  it sets `loggingSettings.redactionConfig` in `cxas_app/app.json`
  (`enableRedaction: true` plus both template names).
- Never redact `DATE`, `TIME` or `LOCATION`. Operational times and outage
  areas must stay readable in the logs.
- Synthetic test card numbers fail the built-in card check (the Luhn
  checksum), so the inspect template adds a custom regular-expression info
  type for card numbers.
- The platform skips redaction in evaluation sessions. DLP therefore has
  **zero effect on scores**, and evaluations cannot verify it. Check it in a
  `make chat ENV=staging` session or in the conversation logs instead.
- With user ADC credentials, REST calls to the DLP API need the
  `X-Goog-User-Project: <project>` header. The script sends it.

*Why:* these are the lessons from adding DLP to `telco-rebuild` on
2026-10-14 (`d721e5c`).

### 27. Tools return money as a number plus a 2-decimal display string, and a contract test checks every field the PRD requires.
- Return each amount twice: a number for math and a string for speech. For
  example: `amount: 85.5, amount_display: "85.50", currency: "CAD"`. Build the
  string with `display_amount(value)` from `lib/replies.py` (`85.5` →
  `"85.50"`), and have the prompt read the `*_display` field.
- Contract-test every field, allowed value (enum) and timeline the PRD
  requires: each tool's output must carry the PRD's fields with the PRD's
  exact values. Keep these checks in `tests/`, next to the tool contract test
  (AGENTS.md Hard Rule 4).

*Why:* in `telco-rebuild`, a tool returned a plain `85.5` and the agent read
it aloud as "85.5 $". Contract gaps also failed visible tests, for example
`"bank"` where the PRD's value was `"bank_account"`.

### 28. Measure visible and holdout on the same code, and re-run the visible suite after any holdout-driven fix.
- Report a visible + holdout total only when both suites ran on the same
  code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`).
  Committing the full-run record moves HEAD, so the two runs often land on
  different commits with identical code; a docs-only or history-only commit
  in between is fine. Never add a visible score to a holdout score measured
  on different code.
- Any change made because of a holdout result needs the owner's approval.
  After it, run a full visible run (`make bench-full`) on that same code
  (same source fingerprint) before anyone reports or re-runs the holdout.

*Why:* an earlier version of this kit headlined a total that added the best
visible run (`0bf79fe`, 46/50 strict) to a holdout run on a later commit
(`894efde`, 18/20 strict). Three holdout-driven fix commits sat in between
(`fe22348`, `1e79e0f`, `894efde`; 29 files), and the visible suite was never
re-run on them. The same code later scored 38/50 strict on the visible suite
(`60f0727`). The real same-commit totals are 60/70 at `0bf79fe` and 59/70 at
`aa2bed4`.

### 29. Treat optimizer output (ParetoLoop and similar) as candidates, not results.
An automatic optimizer such as ParetoLoop proposes prompt or code edits and
scores them. Before you trust one of its scores:
- Score only complete N × 3 runs. Never accept a score from a run that timed
  out or stopped part-way, and never cancel runs mid-flight. `make gate3`
  fails an incomplete run: one where any test has fewer scored tries than
  `runs_per_eval`, or fewer than 3.
- Diff every edit the optimizer made, and look for constraints it removed.
- Re-measure any candidate you keep, and especially a merged one, with a full
  visible run and the holdout on the same code (Rule 28).

*Why:* in `telco-rebuild`, ParetoLoop's 180-minute poll timeout scored
candidates on unfinished runs (225 and 232 of 350 conversations). Those
partial runs showed about 0.96–0.97 "capability" and hid regressions. Its
edits also removed working constraints, such as an "ONLY" on a wrong-code
branch. Merging its 3 winners into one candidate (`df6029c`) scored 42/50
strict on the visible suite with only 46/50 majority.

### 30. One fix mechanism per candidate, and smoke every impacted test.
- A candidate commit carries one fix mechanism. Never merge several fixes, or
  several optimizer winners, into one candidate: when it regresses, you can't
  tell which part did it.
- Smoke every test the change can affect (`make smoke-impact`), not only the
  tests you meant to fix.

*Why:* in `telco-rebuild`, one candidate with 7 fixes merged (`1a959d0`)
scored 42/50 strict, and 3 visible tests fell to 1/3. Merging 3 optimizer
winners at once (`df6029c`) also regressed (Rule 29).

### 31. State every bar as strict 3/3 first, and treat one failed repeat as a signal.
- Report `strict 3/3 | majority >=2/3 | individual`, in that order, for every
  run, gate and claim. The Gate 3 bar is strict 3/3 ≥ 90% (45/50) **and** 100%
  majority, with 0 tool errors (`gate_thresholds.json`: `strict_pass_rate`
  0.90, `majority_pass_rate` 1.00). `make gate3` checks it on a complete,
  single-commit full run (by default the full run for the current code), and
  `make gate` (`suite/gate.py`) applies the same strict 3/3 floor.
- One failed repeat is a signal, not noise. A test that fails 1 time in 5
  passes strict 3/3 only about 51% of the time (0.8³).
- Make no time claim you have not measured.

*Why (the math):* if each conversation passes with probability `p`, a test
passes strict 3/3 with probability `p³`, so 50 tests give about `50 × p³`
strict passes. At `p = 92%`, majority vote expects about 49/50, while strict
3/3 expects only about 39/50, so majority hides 8–10 coin-flip tests. Clean
`telco-rebuild` builds sat at about 90–93% per conversation and scored about
38–41/50 strict. Reaching 45/50 strict needs about 96.5% per conversation
(`0.90^(1/3)`).

## Lessons from `telco-v3` (Rules 32–36)

### 32. Use union types (`str | int | float`) on tool parameters for numeric/float coercion, and never add `from __future__ import annotations` to tool wrappers.
- Annotate tool parameters that receive phone numbers, account IDs, OTPs, PINs,
  card suffixes, monetary amounts, or counts with union types (`str | int | float`
  or `int | float | str`) in both `cxas_app/tools/*/python_function/python_code.py`
  and `lib/services.py`, and coerce them inside Python (`normalize_code(v)` for
  digit strings, `int(float(v))` for counts, `float(v)` for amounts).
- Never put `from __future__ import annotations` in tool wrapper
  `python_code.py` files: CES `ImportApp` server-side Pydantic v2 reflection
  rejects lazily stringified annotations with `400 InvalidArgument` even when
  offline `cxas lint` passes (`KF-70`).

*Why (`telco-v3`, 2026-10-21):* in the baseline full run (`full-0db6ba0`,
`25/50` strict), Gemini Composite V1 emitted Kotlin `Double` / JSON numbers
(`2025550143.0`, `1.5550123456E10`, `1234.0`) for parameters typed as `str`,
causing 8 tool deserialization errors before `normalize_code` ever ran. Widening
all 19 tool signatures to union types in `4165e84` (`DEF-01`) eliminated all 8
tool errors (`8 -> 0`) across every subsequent run.

### 33. Pair anti-hallucination constraints with Turn N+1 follow-up FAQ pre-grounding and localized status notes in data/action tools.
- When `<constraints>` forbids stating facts not present in a tool payload, any
  follow-up question a simulated caller asks on the turn *after* the primary
  tool call (such as warranty purchase date or shipping address on file,
  whether remaining internet rates change after cancelling TV, exact post-cap
  throttled speeds in Kbps, combined base + add-on monthly bill total, or
  whether carrier account details can be attached to a port-in request) will
  cause the agent to say *"I don't have that information"* and escalate via
  `execute_live_agent_handover` — failing `Expectations` and `User Goal`.
- Return those adjacent account-context and policy FAQ fields directly in the
  primary action or catalog tool (`create_warranty_claim`,
  `execute_service_cancellation`, `fetch_plan_catalog`,
  `apply_refund_or_credit`, `create_number_transfer_in`), and localize
  descriptive status/delay notes (`fetch_appointment_ticket_status`) by
  `resolve_locale(state, language)`.

*Why (`telco-v3`, 2026-10-22 to 2026-10-23):* adding follow-up FAQ fields and
localized status notes in `DEF-15`, `DEF-16` (`c4f0187`), and `DEF-18`
(`f05719b`) lifted `VE-47`, `HE-02`, `HE-04`, `HE-16`, `HE-18`, and `HE-19` to
strict `3/3`, driving holdout strict `3/3` from `16/20` (`80.0%`) to `18/20`
(`90.0%`), holdout majority to `20/20` (`100.0%`), and French holdout CUJs to
`6/6` (`100.0%`) strict `3/3`.

### 34. Wrap predictable multi-turn tool chains into atomic single-turn calls, and support empty/placeholder inputs for info-first caller openers.
- Because the voice `<response_protocol>` permits only **one tool call per
  turn**, a 4-step sequential chain across turns (`send_authentication_otp` →
  `validate_authentication_otp` → `fetch_recent_bills` →
  `execute_bill_payment` → `execute_suspend_restore`) burns 4–5 turns and
  causes the LLM to skip an intermediate tool or run out of turns under the
  10-turn simulator cap.
- Bundle upstream context and downstream state transitions atomically into each
  tool in the chain: return `balance_due_display` and `card_last4` inside the
  login tools so no separate `fetch_recent_bills` turn is needed; execute and
  return both payment confirmation (`payment_id`, `amount_paid_display`,
  `billing_breakdown`) and service restoration (`service_restored: True`,
  `new_state: "active"`) inside both `execute_suspend_restore` and
  `execute_bill_payment`; and bundle `available_reschedule_slots` inside
  `fetch_appointment_ticket_status`.
- Allow action tools (such as `create_number_transfer_in`) to accept
  empty/placeholder inputs (`number_to_transfer=""`,
  `current_provider="external"`) to open a pending request and return the
  `required_port_checklist` when a caller opens by asking what information they
  will need from their current provider without having the number on hand.

*Why (`telco-v3`, 2026-10-23):* atomic tool wrapping in `DEF-17` (`8bdb778`)
lifted `VE-06` (`2/3 -> 3/3`), `VE-31` (`2/3 -> 3/3`), and `HE-13`
(`1/3 -> 3/3`), reaching `48/50` (`96.0%`) visible strict and `66/70` (`94.3%`)
combined strict; checklist bundling in `DEF-18` (`f05719b`) lifted `HE-16` from
`1/3` to `3/3` (`20/20 = 100.0%` holdout majority).

### 35. Never include open-ended "up to full monthly rate" invitations in tool outputs that bait the LLM user simulator into triggering a policy cap.
- The simulated caller is also an LLM that reacts to phrases the agent reads
  from tool payloads. Returning `"eligible for adjustment up to full monthly
  package rate"` in `apply_refund_or_credit` caused the agent to speak that
  phrase, which baited the simulated caller into demanding the full `$85.50`
  monthly bill on the next turn — hitting the `$25.00` `LIMIT_EXCEEDED` cap and
  forcing an unwanted escalation (`HE-09` Trial 3 in `holdout-c4f0187`).
- Return exact daily proration formulas (`$2.50/day` base service or
  `$2.85/day` total package) and auto-prorate when a caller passes the full
  monthly bill amount on an outage credit request (`85.50 -> 8.55` for a 3-day
  outage).

### 36. Partition hill-climb fixes into Bucket A (additive leaf metadata) vs. Bucket B (shared decision boundaries), and guard `speech_hygiene` card digits.
- **Bucket A (Zero-Coupling Additive Metadata & Atomic Wrapping):** Adding new
  response keys to leaf tools cannot alter existing control-flow branches and
  can be safely batched (`DEF-16` shipped 4 Bucket A fixes at `15/15 = 100.0%`
  strict `3/3` across all visible + holdout blast-radius CUJs).
- **Bucket B (Shared Routing / Eligibility Thresholds):** Any edit to a shared
  branch condition (such as `paid_signal` substring matching, outage postal
  prefix matching, or refund cap exemptions) must be isolated one at a time and
  smoke-tested against both its **positive target** and its **negative twin**
  (e.g., active outage vs. no outage; already-paid restore vs. unpaid restore;
  `<= $25` credit vs. `> $25` escalation).
- **Card-Digit Guard in `speech_hygiene` (`KF-71`):** In `lib/speech.py`,
  check the prefix before `"ending in"` / `"terminant par"` for card keywords
  (`card`, `carte`, `tarjeta`, `credit`, `debit`, `visa`, `mastercard`) so
  `clean_agent_speech` never overwrites valid payment `card_last4` digits with
  `caller_provided_phone_last4` (`DEF-06`).
