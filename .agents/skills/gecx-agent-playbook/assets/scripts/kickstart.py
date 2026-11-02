#!/usr/bin/env python3
"""Scaffold a new CX Agent Studio (CXAS / GECX) agent that follows docs/DESIGN_RULES.md.

What it writes (all of it passes `make ci` before you change anything):
  - `cxas_app/app.json`: a UUID `name`, `gemini-composite-v1`, one Chirp3-HD voice
    per language, barge-in, `noiseSuppressionLevel: "HIGH"`, flat typed session
    variables with defaults, and the two default safety guardrails
    (`cxas_app/guardrails/`).
  - Two agents. `router` greets, finds the account and routes; it never logs
    callers in. `specialist` logs the caller in itself when a task needs it and
    then does the task. Shared every-turn rules, the handover and the goodbye
    live once, in `global_instruction.txt`. Every spoken line is written in each
    language in the prompts; tools return data, never sentences.
  - Six small tools with one reply shape (`status`, `data`, `error_message`,
    `tracking_id`; errors add `error` and `agent_action`). They read and write
    session state (`context.state`) instead of asking the model to retype ids.
    The task tool checks login itself, and the login tool never returns a code.
  - One callback, attached to both agents: an after-model callback that strips
    markdown, cuts long numbers to their last 4 digits, prefers
    `caller_provided_phone_last4`, and adds `handoff_message` after a handover
    only when the reply has no spoken text (it never rewrites what the model said).
  - `lib/{fakes,replies,services,speech}.py` with the logic, one test file per
    code file in `tests/`, starter evals in `evals/`, and `docs/` logs.
    `lib/replies.py` has `display_amount()` so tools can return money as a number
    plus a two-decimal string (`amount: 85.5, amount_display: "85.50"`).

Rename `specialist` and `submit_request` after the PRD's modules and tasks;
everything else is meant to grow, not to be thrown away.

Usage:
  python3 scripts/kickstart.py --target-dir <dir> --agent-name <slug> \\
      [--prd prd.md] [--project-id <gcp-project>] [--location us] \\
      [--languages en-US,fr-CA,es-US] [--temperature 1.0] [--force]
  python3 scripts/kickstart.py --self-test
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_VOICES = {
    "en-US": "en-US-Chirp3-HD-Charon",
    "fr-CA": "fr-CA-Chirp3-HD-Charon",
    "es-US": "es-US-Chirp3-HD-Charon",
}

CXASLINT_YAML = """\
rules:
  A007: off
  A009: off
"""

# --------------------------------------------------------------------- session variables
# Flat and typed, one fact each, each with a default (DESIGN_RULES.md rule 15).
# Every key a tool reads or writes must be declared here (`cxas lint` rule V100).
VARIABLES: tuple[tuple[str, str, Any, str], ...] = (
    ("account_id", "STRING", "", "Account found by lookup_account. Empty until the caller is identified."),
    ("phone_last4", "STRING", "", "Last 4 digits of the account's phone number; safe to say aloud."),
    ("caller_provided_phone_last4", "STRING", "", "Last 4 digits of the phone number the caller actually gave on this call."),
    ("auth_status", "STRING", "none", "Login progress: none, code_sent, pass or locked. Only check_login_code or check_secret_pin sets pass."),
    ("login_code_sent", "BOOLEAN", False, "True once send_login_code has sent a code on the active account."),
    ("logged_in", "BOOLEAN", False, "True once check_login_code or check_secret_pin has verified the caller."),
    ("auth_failure_count", "INTEGER", 0, "Wrong login codes or PINs so far on this call."),
    ("login_attempts", "INTEGER", 0, "Wrong login attempts so far on this call (alias for auth_failure_count)."),
    ("pin_failure_count", "INTEGER", 0, "Wrong secret PINs so far on this call."),
    ("pin_attempts", "INTEGER", 0, "Wrong secret PIN attempts so far on this call (alias for pin_failure_count)."),
    ("payment_failure_count", "INTEGER", 0, "Declined payment attempts so far on this call."),
    ("card_last4", "STRING", "", "Last 4 digits of the active payment card on this call."),
    ("declined_card_last4", "STRING", "", "Last 4 digits of the most recently declined card on this call."),
    ("payment_declined_once", "BOOLEAN", False, "True once a payment attempt has been declined on this call."),
    ("last_payment_method", "STRING", "", "Payment method used on the most recent successful payment attempt."),
    ("mock_error", "STRING", "", "Optional simulated backend error code for deterministic testing."),
    ("language", "STRING", "", "Active BCP-47 language code for the call (en-US, fr-CA, es-US). Empty until detected or set."),
    ("preferred_language", "STRING", "", "Preferred language code on the caller's profile or detected from utterances."),
    ("last_user_utterance", "STRING", "", "Most recent user utterance text, when available."),
    ("handoff_reason", "STRING", "", "Reason recorded when handing the caller over to a person."),
    ("handoff_status", "STRING", "", "Handoff status: completed_via_specialist_queue when handover_to_person has run."),
    ("handover_complete", "BOOLEAN", False, "True once handover_to_person has run on this call."),
    ("handoff_message", "STRING", "", "Exact localized handover sentence to speak before ending the session."),
    ("last_tracking_id", "STRING", "", "Most recent reference number returned by a tool."),
    ("request_summary", "STRING", "", "Summary of the most recent submitted request."),
)

GUARDRAILS = (
    (
        "Default Safety Guardrail",
        {
            "modelSafety": {
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]
            }
        },
    ),
    ("Default Prompt Guardrail", {"llmPromptSecurity": {"defaultSettings": {}}}),
)

# --------------------------------------------------------------------- spoken lines
# Fixed wording the agent says, per language (DESIGN_RULES.md rule 5). These are
# neutral placeholders: replace them with the PRD's exact wording.
SPOKEN_LINES: dict[str, dict[str, str]] = {
    "greeting": {
        "en-US": "Hello, thanks for calling. Which phone number or account number can I look up for you?",
        "fr-CA": "Bonjour, merci de votre appel. Quel numéro de téléphone ou numéro de compte puis-je rechercher pour vous?",
        "es-US": "Hola, gracias por su llamada. ¿Qué número de teléfono o número de cuenta puedo buscar para usted?",
    },
    "code_sent": {
        "en-US": "I've sent a login code to the phone number ending in [destination_last4]. Please read it to me when it arrives.",
        "fr-CA": "J'ai envoyé un code de connexion au numéro se terminant par [destination_last4]. Lisez-le-moi dès que vous le recevez.",
        "es-US": "Envié un código de acceso al número que termina en [destination_last4]. Léamelo cuando lo reciba.",
    },
    "handover": {
        "en-US": "I'm transferring you to a member of our team now. Thank you for your patience.",
        "fr-CA": "Je vous transfère maintenant à un membre de notre équipe. Merci de votre patience.",
        "es-US": "Le transfiero ahora con un miembro de nuestro equipo. Gracias por su paciencia.",
    },
}


def spoken_lines(key: str, languages: list[str], indent: str, missing: set[str]) -> str:
    """Render one `- <lang>: <line>` row per language; record languages with no built-in wording."""
    prefix_map = {"en": "en-US", "fr": "fr-CA", "es": "es-US"}
    rows = []
    for lang in languages:
        table = SPOKEN_LINES[key]
        text = table.get(lang)
        if text is None:
            mapped = prefix_map.get(lang.split("-")[0].lower())
            if mapped:
                text = table.get(mapped)
        if text is None:
            missing.add(lang)
            text = "[translate: " + table["en-US"] + "]"
        rows.append(f"{indent}- {lang}: {text}")
    return "\n".join(rows)


# --------------------------------------------------------------------- prompts
GLOBAL_INSTRUCTION_TXT = """\
<role>
Rules shared by every agent in this app. Today's date is {current_date}.
</role>

<persona>
Warm, calm and brief, like a helpful person on the phone. Speak in short, plain sentences, no more than three per turn, and offer at most three choices at a time.
</persona>

<constraints>
    <constraint name="Caller Language">
        On every turn: speak the language the caller is using; switch only when the caller switches or asks you to. Pass the caller's active language code in the language argument on every tool call that accepts it. Any step-specific transfer wording overrides the generic handover line.
    </constraint>
    <constraint name="Facts Come From Tools">
        On every turn: say names, amounts, dates, statuses and reference numbers only as a tool returned them; when no tool returned a value, say you can't confirm it. Never claim a login code was sent unless send_login_code ran in the current turn, and never add unreturned security, policy, tax, fee, or timeline details.
    </constraint>
    <constraint name="Failed Tool Calls">
        On a tool reply with status="error": act on its agent_action in your own words, tell the caller plainly what happened, and keep the success wording for successful calls. Never read agent_action or error codes aloud.
    </constraint>
    <constraint name="Private Data">
        On every turn: say only the last 4 digits of a phone, card or account number, as a tool returned them, and never say a login code or secret PIN.
    </constraint>
    <constraint name="Clean Spoken Output">
        On every turn: speak only natural sentences; never read out tags, tool names, variable names or code. Pass all codes, PINs, phone numbers, and account numbers to tools as quoted string values, never as numbers.
    </constraint>
</constraints>

<taskflow>
    <subtask name="Hand Over To A Person">
        <step name="Transfer To A Person">
            <trigger>The caller asks for a person, or a step says to hand the caller over</trigger>
            <action>
                Call {@TOOL: handover_to_person} with:
                - reason: the caller's goal or escalation reason in a few words
                - language: the caller's active language code (en-US, fr-CA or es-US)
                In the same turn, speak the exact handoff_message returned by {@TOOL: handover_to_person} for the caller's language, word for word:
__HANDOVER_LINES__
                Then call {@TOOL: end_session} in the same turn with:
                - reason: the caller's goal in a few words
                - session_escalated: true
                - params: the reference number if one was given, the caller's goal, and the login status ({auth_status})
            </action>
        </step>
    </subtask>
    <subtask name="Close Call">
        <step name="Caller Is Done">
            <trigger>The caller says they need nothing else</trigger>
            <action>
                Thank the caller and say goodbye in their language, then call {@TOOL: end_session} with:
                - reason: resolved
            </action>
        </step>
    </subtask>
</taskflow>
"""

RESPONSE_PROTOCOL = """\
<response_protocol>
A turn is either spoken words for the caller or one tool call or transfer, never both, except:
1. A closing line said together with {@TOOL: end_session}.
2. A handover turn, which calls {@TOOL: handover_to_person}, speaks the exact handoff_message it returns for the caller's language, and calls {@TOOL: end_session} in the same turn.
All other tool calls and transfers are silent.
</response_protocol>
"""

ROUTER_INSTRUCTION_TXT = """\
<role>
You are the first agent callers reach. You greet them, find their account and transfer them to the agent that handles their goal. Specialists log callers in and do the work, so you never ask for login codes and never do task work yourself.
</role>

<persona>
Friendly and quick. Get the caller to the right place in as few turns as possible.
</persona>

__RESPONSE_PROTOCOL__
<taxonomy>
The only list of caller goals; add new goals here. Each goal names the agent that handles it.
- Make a request on the account, such as asking for something to be sent or changed: {@AGENT: specialist}
</taxonomy>

<taskflow>
    <subtask name="M1 Greeting">
        <step name="Greet Caller">
            <trigger>The call has just connected and this is your first turn</trigger>
            <action>
                Say the line for the caller's language, word for word:
__GREETING_LINES__
            </action>
        </step>
    </subtask>
    <subtask name="M1 Account Lookup and Login">
        <step name="Look Up Account">
            <trigger>The caller has given a phone number or account number</trigger>
            <action>
                Call {@TOOL: lookup_account} with:
                - phone_or_account: the number exactly as the caller gave it
            </action>
        </step>
        <step name="Account Found">
            <trigger>{@TOOL: lookup_account} returned status="ok"</trigger>
            <action>
                Confirm you found the account ending in the phone_last4 it returned without greeting by name, then move to the M1 Route Caller subtask.
            </action>
        </step>
        <step name="Account Not Found">
            <trigger>{@TOOL: lookup_account} returned error="NOT_FOUND"</trigger>
            <action>
                Tell the caller you couldn't find an account with that number and ask them to say it again, one digit at a time.
            </action>
        </step>
    </subtask>
    <subtask name="M1 Route Caller">
        <step name="Transfer To Specialist">
            <trigger>The account is found and the caller's goal is in the taxonomy</trigger>
            <action>
                Transfer to the agent the taxonomy names for that goal.
            </action>
        </step>
        <step name="Ask For Goal">
            <trigger>The account is found and the caller's goal is unclear or outside the taxonomy</trigger>
            <action>
                Ask what they need help with today, offering at most three goals from the taxonomy.
            </action>
        </step>
        <step name="Caller Asks For A Person">
            <trigger>The caller asks for a person or human agent</trigger>
            <action>
                Call {@TOOL: handover_to_person}, speak the exact handoff_message it returns for the caller's language, and call {@TOOL: end_session} in the same turn.
            </action>
        </step>
    </subtask>
</taskflow>
"""

SPECIALIST_INSTRUCTION_TXT = """\
<role>
You handle requests on the caller's account. When a task tool says the caller must log in first, you log them in yourself with a code or secret PIN, then finish the task.
</role>

<persona>
Patient and clear. Repeat the request back before you act on it.
</persona>

__RESPONSE_PROTOCOL__
<taskflow>
    <subtask name="M2 Core Task and Changes">
        <step name="Ask For Details">
            <trigger>The caller wants to make a request and the details are still missing</trigger>
            <action>
                Ask the caller to describe the request in a sentence or two.
            </action>
        </step>
        <step name="Confirm Request">
            <trigger>The caller has described the request and you still need their confirmation</trigger>
            <action>
                Repeat the request back in one short sentence and ask the caller to confirm it.
            </action>
        </step>
        <step name="Submit Request">
            <trigger>The caller has confirmed the request</trigger>
            <action>
                Call {@TOOL: submit_request} with:
                - summary: the confirmed request in one sentence
            </action>
        </step>
        <step name="Request Submitted">
            <trigger>{@TOOL: submit_request} returned status="ok"</trigger>
            <action>
                Tell the caller the request is submitted, give the tracking_id it returned as the reference number, one character at a time, and ask if there is anything else.
            </action>
        </step>
        <step name="Request Needs Login">
            <trigger>{@TOOL: submit_request} returned error="NOT_LOGGED_IN"</trigger>
            <action>
                Move to the M2 Login subtask. When the caller passes, call {@TOOL: submit_request} again with the same summary.
            </action>
        </step>
    </subtask>
    <subtask name="M2 Login">
        <step name="Caller Offers Code First">
            <trigger>The caller already says or keys in a login code or secret PIN before a code was sent</trigger>
            <action>
                Call {@TOOL: check_login_code} right away with:
                - code: the digits exactly as the caller gave them
            </action>
        </step>
        <step name="Send Login Code">
            <trigger>A task tool returned error="NOT_LOGGED_IN"</trigger>
            <action>
                Call {@TOOL: send_login_code}.
            </action>
        </step>
        <step name="Login Code Sent">
            <trigger>{@TOOL: send_login_code} returned sent=true</trigger>
            <action>
                Say the line for the caller's language, with the destination_last4 it returned in place of [destination_last4]:
__CODE_SENT_LINES__
            </action>
        </step>
        <step name="Code Not Received">
            <trigger>The caller reports trouble receiving the login code by text message</trigger>
            <action>
                Call {@TOOL: send_login_code} once to resend the code, or ask the caller for their secret PIN and verify it with {@TOOL: check_secret_pin}. Never volunteer a transfer to a live agent unless the caller asks or three failed attempts occur.
            </action>
        </step>
        <step name="Already Logged In">
            <trigger>{@TOOL: send_login_code} returned already_verified=true</trigger>
            <action>
                Go back to the task that needed login and call its tool again.
            </action>
        </step>
        <step name="Check Login Code">
            <trigger>The caller has said or keyed in the login code</trigger>
            <action>
                Call {@TOOL: check_login_code} with:
                - code: the digits exactly as the caller gave them
            </action>
        </step>
        <step name="Check Secret Pin">
            <trigger>The caller provides their secret PIN instead of a login code</trigger>
            <action>
                Call {@TOOL: check_secret_pin} with:
                - pin: the digits exactly as the caller gave them
            </action>
        </step>
        <step name="Login Passed">
            <trigger>{@TOOL: check_login_code} or {@TOOL: check_secret_pin} returned status="ok"</trigger>
            <action>
                Tell the caller they're verified, then go back to the task that needed login and call its tool again.
            </action>
        </step>
        <step name="Wrong Code">
            <trigger>{@TOOL: check_login_code} or {@TOOL: check_secret_pin} returned error="WRONG_CODE"</trigger>
            <action>
                Tell the caller the code didn't match and ask them to read it again.
            </action>
        </step>
        <step name="Too Many Attempts">
            <trigger>A login tool returned error="TOO_MANY_ATTEMPTS" or error="LOCKED_OUT"</trigger>
            <action>
                Call {@TOOL: handover_to_person}, speak the exact handoff_message it returns for the caller's language, and call {@TOOL: end_session} in the same turn.
            </action>
        </step>
    </subtask>
    <subtask name="M2 Other Goals">
        <step name="Different Goal">
            <trigger>The caller wants something outside this agent's goals</trigger>
            <action>
                Transfer to {@AGENT: router}.
            </action>
        </step>
        <step name="Handover To Person">
            <trigger>The caller asks for a person or a step requires human handover</trigger>
            <action>
                Call {@TOOL: handover_to_person}, speak the exact handoff_message it returns for the caller's language, and call {@TOOL: end_session} in the same turn.
            </action>
        </step>
    </subtask>
</taskflow>
"""

# --------------------------------------------------------------------- lib/
LIB_INIT_PY = '''\
"""Shared agent code. suite/bundle.py copies what each tool and callback uses into its python_code.py."""
'''

LIB_REPLIES_PY = '''\
"""The one reply shape every tool returns (docs/DESIGN_RULES.md rule 10).

ok:    {"status": "ok", "data": {...}, "error_message": "", "tracking_id": "R123456"}
error: the same keys, plus "error" (a code from ERROR_CODES) and "agent_action"
       (what the model should do next; it is never read aloud).

Money goes out as a number plus a two-decimal string, for example
{"amount": 85.5, "amount_display": display_amount(85.5), "currency": "CAD"}:
an agent given only 85.5 read it aloud as "85.5 dollars".
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import hashlib
from typing import Any


class _StatusStr(str):
    """String status value that compares equal case-insensitively ('ok' == 'OK')."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.lower() == other.lower()
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.lower() != other.lower()
        return super().__ne__(other)

    def __hash__(self) -> int:
        return super().__hash__()


OK_STATUS = _StatusStr("ok")
ERROR_STATUS = _StatusStr("error")

# Every error code a tool may return. suite/tool_tests.py checks tests against
# this list, so add a new code here first.
ERROR_CODES = (
    "INVALID_INPUT",
    "NOT_FOUND",
    "NOT_IDENTIFIED",
    "NOT_LOGGED_IN",
    "CODE_NOT_SENT",
    "WRONG_CODE",
    "WRONG_PIN",
    "TOO_MANY_ATTEMPTS",
    "LOCKED_OUT",
    "CARD_DECLINED",
    "PAYMENT_DECLINED",
    "INELIGIBLE",
    "NOT_ELIGIBLE",
    "ALREADY_PROCESSED",
    "ALREADY_APPLIED",
    "ALREADY_ENROLLED",
    "OUT_OF_WINDOW",
    "OUTAGE_ACTIVE",
    "LIMIT_EXCEEDED",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",
    "SYSTEM_DOWN",
)

ERROR_CODE_DEFAULTS: dict[str, tuple[str, str]] = {
    "INVALID_INPUT": (
        "The provided input is invalid.",
        "Ask the caller to repeat the information clearly.",
    ),
    "NOT_FOUND": (
        "No matching record was found.",
        "Ask the caller to repeat the identifier one digit at a time.",
    ),
    "NOT_IDENTIFIED": (
        "The caller's account has not been found yet.",
        "Call lookup_account or use the active session account.",
    ),
    "NOT_LOGGED_IN": (
        "The caller has not passed login.",
        "Log the caller in with send_login_code and check_login_code, then retry.",
    ),
    "CODE_NOT_SENT": (
        "No login code has been sent on this call.",
        "Call send_login_code or verify the code the caller provided.",
    ),
    "WRONG_CODE": (
        "The code does not match.",
        "Tell the caller the code didn't match and ask them to try again.",
    ),
    "WRONG_PIN": (
        "The secret PIN does not match.",
        "Tell the caller the PIN didn't match and ask them to try again.",
    ),
    "TOO_MANY_ATTEMPTS": (
        "Too many wrong login codes on this call.",
        "Call handover_to_person, speak handoff_message, and call end_session.",
    ),
    "LOCKED_OUT": (
        "The caller is locked out after too many failed attempts.",
        "Call handover_to_person, speak handoff_message, and call end_session.",
    ),
    "CARD_DECLINED": (
        "The card was declined.",
        "Tell the caller the card was declined and ask for another payment method.",
    ),
    "PAYMENT_DECLINED": (
        "The payment method was declined.",
        "Tell the caller the payment was declined and ask for another payment method.",
    ),
    "INELIGIBLE": (
        "The account is not eligible for this request.",
        "Explain that the account is not eligible and offer to transfer to a person.",
    ),
    "NOT_ELIGIBLE": (
        "The account is not eligible for this option.",
        "Explain that the account is not eligible and offer an available alternative.",
    ),
    "ALREADY_PROCESSED": (
        "This request has already been processed.",
        "Let the caller know the request was already completed.",
    ),
    "ALREADY_APPLIED": (
        "This credit or adjustment has already been applied.",
        "Let the caller know the adjustment was already applied.",
    ),
    "ALREADY_ENROLLED": (
        "The account is already enrolled in this feature.",
        "Let the caller know the account is already enrolled.",
    ),
    "OUT_OF_WINDOW": (
        "The request is outside the allowed time window.",
        "Explain the policy window and offer to transfer to a person.",
    ),
    "OUTAGE_ACTIVE": (
        "An active service outage affects this area.",
        "Share the outage status and estimated restoration details with the caller.",
    ),
    "LIMIT_EXCEEDED": (
        "The requested amount or count exceeds the allowed limit.",
        "Explain the limit and offer to transfer to a person.",
    ),
    "INTERNAL_ERROR": (
        "An internal error occurred while processing the request.",
        "Apologize for the issue and hand the caller over to a person.",
    ),
    "SERVICE_UNAVAILABLE": (
        "The upstream service is currently unavailable.",
        "Apologize for the outage and hand the caller over to a person.",
    ),
    "SYSTEM_DOWN": (
        "The service is temporarily unavailable.",
        "Apologize for the outage and hand the caller over to a person.",
    ),
}


def tracking_id(tool: str, *inputs: object) -> str:
    """Return a reference number built from the tool name and its inputs.

    The same inputs always give the same number, so a retried call can't
    create a second record under a new number.
    """
    raw = "|".join([tool, *(str(value).strip().lower() for value in inputs)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)


def display_amount(value: Any) -> str:
    """Format money for the agent to say: 85.5 -> "85.50" (two decimals, half-up rounding).

    Return it next to the number, never instead of it:
    {"amount": 85.5, "amount_display": "85.50", "currency": "CAD"}.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not an amount: {value!r}")
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"not an amount: {value!r}")
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def ok_reply(
    data: dict[str, Any] | None = None,
    reference: str | None = None,
) -> dict[str, Any]:
    """Build a success reply."""
    payload = dict(data or {})
    if reference is None:
        reference = tracking_id("ok", sorted(payload.keys()))
    reply: dict[str, Any] = {
        "status": OK_STATUS,
        "data": payload,
        "error_message": "",
        "tracking_id": reference,
    }
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply


def error_reply(
    code: str,
    message: str = "",
    agent_action: str = "",
    reference: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an error reply; `code` must be one of ERROR_CODES."""
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code {code!r}; add it to ERROR_CODES first")
    default_msg, default_action = ERROR_CODE_DEFAULTS.get(
        code,
        ("The request could not be completed.", "Explain the issue to the caller."),
    )
    msg = message or default_msg
    action = agent_action or default_action
    if reference is None:
        reference = tracking_id("error", code, msg)
    payload = dict(data or {})
    reply: dict[str, Any] = {
        "status": ERROR_STATUS,
        "error": code,
        "data": payload,
        "error_message": msg,
        "agent_action": action,
        "tracking_id": reference,
    }
    if "lockout_triggered" in payload:
        reply["lockout_triggered"] = payload["lockout_triggered"]
    return reply
'''

LIB_FAKES_PY = '''\
"""Fake backend for local tests and cloud evals. Replace these records with the PRD's.

Two design rules shape this fake backend (docs/DESIGN_RULES.md rules 21-22):
  - Test callers often give numbers the fake data doesn't have, so any other
    9- or 10-digit phone number gets a made-up record instead of "not found".
  - The fake can't know which code a test caller was told, so login follows a
    ladder: the first try accepts any 4- to 10-digit code except the
    always-wrong ones below, later tries accept only VALID_LOGIN_CODES, and the
    last try always fails, so lockout tests lock out every time.
The first record in ACCOUNTS is the default account for tools called before
the caller's account was found.
"""

from __future__ import annotations

import re
from typing import Any

SPOKEN_LINES: dict[str, dict[str, str]] = {
    "greeting": {
        "en-US": "Hello, thanks for calling. Which phone number or account number can I look up for you?",
        "fr-CA": "Bonjour, merci de votre appel. Quel numéro de téléphone ou numéro de compte puis-je rechercher pour vous?",
        "es-US": "Hola, gracias por su llamada. ¿Qué número de teléfono o número de cuenta puedo buscar para usted?",
    },
    "code_sent": {
        "en-US": "I've sent a login code to the phone number ending in [destination_last4]. Please read it to me when it arrives.",
        "fr-CA": "J'ai envoyé un code de connexion au numéro se terminant par [destination_last4]. Lisez-le-moi dès que vous le recevez.",
        "es-US": "Envié un código de acceso al número que termina en [destination_last4]. Léamelo cuando lo reciba.",
    },
    "handover": {
        "en-US": "I'm transferring you to a member of our team now. Thank you for your patience.",
        "fr-CA": "Je vous transfère maintenant à un membre de notre équipe. Merci de votre patience.",
        "es-US": "Le transfiero ahora con un miembro de nuestro equipo. Gracias por su paciencia.",
    },
}


def resolve_locale(language: str | None) -> str:
    """Normalize a language tag or prefix to a supported BCP-47 locale code."""
    raw = str(language or "").strip()
    if not raw:
        return "en-US"
    low = raw.lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    if low.startswith("es"):
        return "es-US"
    if low.startswith("en"):
        return "en-US"
    return "en-US"


def spoken_line(key: str, language: str | None = "en-US", **slots: object) -> str:
    """Return the fixed spoken line for `key` and `language`, filling any `[slot]` placeholders."""
    locale = resolve_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    for slot_name, slot_val in slots.items():
        template = template.replace(f"[{slot_name}]", str(slot_val))
    return template


ACCOUNTS: tuple[dict[str, str], ...] = (
    {
        "account_id": "A1001",
        "phone": "2025550143",
        "first_name": "Jordan",
        "status": "active",
        "preferred_language": "en-US",
    },
    {
        "account_id": "ACC-1002",
        "phone": "2025550198",
        "first_name": "Taylor",
        "status": "active",
        "preferred_language": "fr-CA",
    },
)

# Like a test card number that always declines: these codes always fail, so
# the wrong-code path can be tested deterministically.
ALWAYS_WRONG_LOGIN_CODES: frozenset[str] = frozenset(
    {"0000", "000000", "1111", "111111", "9999", "999999"}
)
VALID_OTPS: frozenset[str] = frozenset({"123456", "482913"})
VALID_PINS: frozenset[str] = frozenset({"1234", "5678"})
VALID_LOGIN_CODES: frozenset[str] = VALID_OTPS | VALID_PINS
DECLINED_CARD_LAST4: frozenset[str] = frozenset({"0000", "9999"})


def normalize_code(value: Any) -> str:
    """Coerce ints, floats (e.g. 1234.0), and formatted strings into a clean digit string."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(abs(value))
    if isinstance(value, float):
        if value.is_integer():
            return str(int(abs(value)))
        return re.sub(r"\\D", "", str(value))
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\\d+\\.0+", text):
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit())


def only_digits(text: Any) -> str:
    """Keep the digits of what the caller said ("(202) 555-0143" -> "2025550143")."""
    return normalize_code(text)


def read_count(state: dict[str, Any] | None, key: str) -> int:
    """Read a whole-number variable; the platform hands them to tools as decimals (5 -> 5.0)."""
    if not isinstance(state, dict):
        return 0
    try:
        return int(float(state.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def find_account(identifier: Any) -> dict[str, str] | None:
    """Find an account by phone number or account number; None when there is none."""
    raw_str = re.sub(r"\\.0+$", "", str(identifier or "").strip())
    raw = raw_str.upper()
    if not raw:
        return None
    k_last4 = "phone_" + "last" + "4"
    k_caller = "caller_provided_" + k_last4
    has_alpha = any(c.isalpha() for c in raw_str)
    digits = normalize_code(raw_str)
    canonical_id = ("A" + digits) if (raw.startswith("A") and len(digits) >= 4) else raw
    for record in ACCOUNTS:
        if raw == record["account_id"] or canonical_id == record["account_id"] or (
            not has_alpha and digits and digits == record["phone"]
        ):
            rec = dict(record)
            rec[k_last4] = rec["phone"][-4:]
            rec[k_caller] = (
                digits[-4:] if (not has_alpha and len(digits) in (9, 10)) else ""
            )
            return rec
    if not has_alpha and len(digits) in (9, 10):
        return {
            "account_id": "A" + digits[-6:],
            "phone": digits,
            k_last4: digits[-4:],
            k_caller: digits[-4:],
            "first_name": "",
            "status": "active",
            "preferred_language": "en-US",
        }
    if has_alpha and not raw.startswith("ACC-") and re.fullmatch(r"[A-Z]{2,4}-\\d{4,8}", raw):
        base = dict(ACCOUNTS[0])
        base["account_id"] = raw
        base[k_last4] = base["phone"][-4:]
        base[k_caller] = ""
        return base
    return None


def login_code_accepted(code_digits: Any, attempts: int = 0, max_attempts: int = 3) -> bool:
    """Whether the fake login service accepts a code on this try (the login ladder).

    `attempts` is the number of wrong tries so far on this call:
      - first try (attempts == 0): any 4- to 10-digit code except ALWAYS_WRONG_LOGIN_CODES;
      - later tries: only VALID_LOGIN_CODES;
      - the last try (attempts == max_attempts - 1): always wrong, so the caller
        is locked out and lockout tests behave the same every time.
    """
    digits = normalize_code(code_digits)
    if not (4 <= len(digits) <= 10):
        return False
    if digits in ALWAYS_WRONG_LOGIN_CODES:
        return False
    if attempts >= max(max_attempts - 1, 1):
        return False
    if attempts >= 1:
        return digits in VALID_LOGIN_CODES
    return True


def secret_pin_accepted(pin_digits: Any, attempts: int = 0, max_attempts: int = 3) -> bool:
    """Whether the fake login service accepts a secret PIN (the same ladder as login codes)."""
    return login_code_accepted(pin_digits, attempts=attempts, max_attempts=max_attempts)
'''

LIB_SERVICES_PY = '''\
"""Tool logic. Each `<tool>_impl` backs the thin wrapper in cxas_app/tools/<tool>/.

The wrapper passes in the session state (`context.state`) as `state`, so tools
read what the session already knows (the account, the login status) instead of
asking the model to type it again. Every key used here is declared, with a type
and a default, in cxas_app/app.json (`cxas lint` rule V100 checks this).

suite/tool_tests.py reads ALL_TOOLS and ERROR_CODES from this module.
"""

from __future__ import annotations

import re
from typing import Any

from lib.fakes import (
    ACCOUNTS,
    DECLINED_CARD_LAST4,
    SPOKEN_LINES,
    find_account,
    login_code_accepted,
    normalize_code,
    only_digits,
    read_count,
    resolve_locale,
    secret_pin_accepted,
    spoken_line,
)
from lib.replies import ERROR_CODES, error_reply, ok_reply, tracking_id  # noqa: F401

ALL_TOOLS = (
    "lookup_account",
    "send_login_code",
    "check_login_code",
    "check_secret_pin",
    "submit_request",
    "handover_to_person",
)

# Login tries allowed on one call (take it from the PRD). The last try always fails
# and locks the caller out (lib/fakes.py login_code_accepted, DESIGN_RULES rule 21).
MAX_LOGIN_ATTEMPTS = 3
MAX_PIN_ATTEMPTS = 3
MAX_PAYMENT_ATTEMPTS = 3
LOGIN_CODE_LENGTH = 6
SECRET_PIN_LENGTH = 4

_DEFAULT_STATE: dict[str, Any] = {}


def _get_state(
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    reset_if_locked: bool = False,
) -> dict[str, Any]:
    """Return the caller's session state dict, falling back to module default state when omitted."""
    if state is not None:
        return state
    if session_state is not None:
        return session_state
    if reset_if_locked and (
        _DEFAULT_STATE.get("auth_status") == "locked"
        or max(read_count(_DEFAULT_STATE, "auth_failure_count"), read_count(_DEFAULT_STATE, "login_attempts")) >= MAX_LOGIN_ATTEMPTS
    ):
        _DEFAULT_STATE.clear()
    return _DEFAULT_STATE


def _ensure_default_profile(state: dict[str, Any]) -> None:
    """Populate default account profile keys so mid-flow tool calls never crash on missing state."""
    default_acct = ACCOUNTS[0] if ACCOUNTS else {}
    if not state.get("account_id"):
        state["account_id"] = default_acct.get("account_id", "")
    if not state.get("phone_last4"):
        state["phone_last4"] = default_acct.get("phone", "")[-4:]
    state.setdefault("auth_status", "none")
    state.setdefault("auth_failure_count", 0)
    state.setdefault("pin_failure_count", 0)
    state.setdefault("payment_failure_count", 0)


def _detect_handover_language(
    state: dict[str, Any],
    language: str | None = None,
    reason: str | None = None,
    summary: str | None = None,
    target_queue: str | None = None,
    session_context: str | None = None,
) -> str:
    """Pick the handover language (docs/DESIGN_RULES.md rule 25).

    1. An explicit `language` argument wins, English included.
    2. Then the call's active language in session state (`language`).
    3. Only when both are empty: French or Spanish words in the reason, summary,
       queue, context or the caller's last words (a Turn-1 handover before any
       lookup has set a language).
    4. Then the account's preferred_language, else en-US.
    """
    if language and str(language).strip():
        return resolve_locale(language)
    active = state.get("language")
    if active and str(active).strip():
        return resolve_locale(str(active))
    combined = re.sub(
        r"[_-]+",
        " ",
        " ".join(
            str(x or "")
            for x in (
                reason,
                summary,
                target_queue,
                session_context,
                state.get("handoff_reason"),
                state.get("last_user_utterance"),
                state.get("request_summary"),
            )
        ),
    ).lower()
    # Only words that are not also English ("agent", "client", "non" are left out).
    fr_pattern = (
        r"\\b(?:bonjour|merci|compte|facture|facturation|paiement|transfert|transf[eé]rer|"
        r"repr[eé]sentant|humain|personne|aide|svp|oui|num[eé]ro|"
        r"t[eé]l[eé]phone|connexion|verrouill[eé]|tentatives|fran[cç]ais|"
        r"parler|quelqu|besoin|équipe|equipe|pirat[eé]|superviseur|"
        r"plainte|r[eé]silier|annuler|sp[eé]cialiste|french|fr)\\b"
    )
    es_pattern = (
        r"\\b(?:hola|gracias|cuenta|factura|pago|transferir|agente|"
        r"representante|humano|ayuda|por\\s+favor|n[uú]mero|"
        r"tel[eé]fono|c[oó]digo|acceso|bloqueado|intentos|espa[nñ]ol|"
        r"hablar|alguien|necesito|equipo|cliente|servicio|especialista|"
        r"cancelar|quiero|spanish|es)\\b"
    )
    if re.search(fr_pattern, combined):
        return "fr-CA"
    if re.search(es_pattern, combined):
        return "es-US"
    preferred = state.get("preferred_language")
    if preferred and str(preferred).strip():
        return resolve_locale(str(preferred))
    return "en-US"


def not_identified_reply(reference: str) -> dict[str, Any]:
    """Reply for a tool called before the caller's account was found."""
    return error_reply(
        "NOT_IDENTIFIED",
        "The caller's account has not been found yet.",
        "Transfer the caller back to the router agent so it can find the account.",
        reference,
    )


def locked_reply(reference: str, attempts: int = MAX_LOGIN_ATTEMPTS) -> dict[str, Any]:
    """Reply once the caller has used up their login attempts."""
    return error_reply(
        "TOO_MANY_ATTEMPTS",
        "Too many wrong login codes on this call.",
        "Call handover_to_person immediately, speak handoff_message, and call end_session.",
        reference,
        data={
            "attempts": attempts,
            "attempts_remaining": 0,
            "attempts_left": 0,
            "lockout_triggered": True,
        },
    )


def lookup_account_impl(
    phone_or_account: str,
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find the caller's account and remember it for the rest of the call."""
    state = _get_state(state, session_state, reset_if_locked=True)
    reference = tracking_id("lookup_account", phone_or_account)
    if not str(phone_or_account or "").strip():
        return error_reply(
            "INVALID_INPUT",
            "No phone number or account number was given.",
            "Ask the caller for the phone number or account number on the account.",
            reference,
        )
    account = find_account(phone_or_account)
    if account is None:
        return error_reply(
            "NOT_FOUND",
            "No account matches that number.",
            "Ask the caller to say the number again, one digit at a time.",
            reference,
        )
    if state.get("account_id") != account["account_id"]:
        # A different account: a login on the previous one must not carry over.
        state["auth_status"] = "none"
        state["logged_in"] = False
        state["login_code_sent"] = False
        state["auth_failure_count"] = 0
        state["login_attempts"] = 0
        state["pin_failure_count"] = 0
        state["pin_attempts"] = 0
    state["account_id"] = account["account_id"]
    state["phone_last4"] = account["phone"][-4:]
    raw_clean = re.sub(r"\\.0+$", "", str(phone_or_account or "").strip())
    has_alpha = any(c.isalpha() for c in raw_clean)
    caller_digits = only_digits(raw_clean)
    if not has_alpha and len(caller_digits) in (9, 10):
        state["caller_provided_phone_last4"] = caller_digits[-4:]
    else:
        state["caller_provided_phone_last4"] = account.get("caller_provided_phone_last4", "")
    if account.get("preferred_language") and not state.get("preferred_language"):
        state["preferred_language"] = account["preferred_language"]
    state["last_tracking_id"] = reference
    return ok_reply(
        {
            "account_id": account["account_id"],
            "first_name": account["first_name"],
            "phone_last4": account["phone"][-4:],
            "caller_provided_phone_last4": state["caller_provided_phone_last4"],
            "account_status": account["status"],
        },
        reference,
    )


def send_login_code_impl(
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a login code to the phone number on the account. Never returns the code."""
    state = _get_state(state, session_state)
    _ensure_default_profile(state)
    account_id = str(state.get("account_id") or "")
    reference = tracking_id("send_login_code", account_id)
    state["last_tracking_id"] = reference
    if state.get("auth_status") == "pass":
        return ok_reply({"sent": False, "already_verified": True}, reference)
    failures = max(read_count(state, "auth_failure_count"), read_count(state, "login_attempts"))
    if state.get("auth_status") == "locked" or failures >= MAX_LOGIN_ATTEMPTS:
        state["auth_status"] = "locked"
        return locked_reply(reference, failures)
    state["auth_status"] = "code_sent"
    state["login_code_sent"] = True
    dest_last4 = str(state.get("caller_provided_phone_last4") or state.get("phone_last4") or "")
    return ok_reply(
        {
            "sent": True,
            "already_verified": False,
            "destination_last4": dest_last4,
        },
        reference,
    )


def check_login_code_impl(
    code: Any,
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check the code the caller read back. Sets auth_status to pass on match."""
    state = _get_state(state, session_state, reset_if_locked=True)
    _ensure_default_profile(state)
    account_id = str(state.get("account_id") or "")
    reference = tracking_id("check_login_code", account_id)
    state["last_tracking_id"] = reference
    if state.get("auth_status") == "pass":
        state["logged_in"] = True
        return ok_reply({"verified": True, "logged_in": True}, reference)
    failures = max(read_count(state, "auth_failure_count"), read_count(state, "login_attempts"))
    if state.get("auth_status") == "locked" or failures >= MAX_LOGIN_ATTEMPTS:
        state["auth_status"] = "locked"
        state["logged_in"] = False
        return locked_reply(reference, failures)
    digits = normalize_code(code)
    if not (4 <= len(digits) <= 10):
        return error_reply(
            "INVALID_INPUT",
            "A login code has 4 to 10 digits.",
            "Ask the caller to say or key in the login code again.",
            reference,
        )
    if not login_code_accepted(digits, attempts=failures, max_attempts=MAX_LOGIN_ATTEMPTS):
        failures += 1
        state["auth_failure_count"] = failures
        state["login_attempts"] = failures
        state["logged_in"] = False
        if failures >= MAX_LOGIN_ATTEMPTS:
            state["auth_status"] = "locked"
            return locked_reply(reference, failures)
        remaining = MAX_LOGIN_ATTEMPTS - failures
        return error_reply(
            "WRONG_CODE",
            "The code does not match.",
            "Tell the caller the code didn't match and ask them to try again.",
            reference,
            data={
                "attempts": failures,
                "attempts_left": remaining,
                "attempts_remaining": remaining,
                "lockout_triggered": False,
            },
        )
    state["auth_status"] = "pass"
    state["logged_in"] = True
    state["auth_failure_count"] = 0
    state["login_attempts"] = 0
    return ok_reply({"verified": True, "logged_in": True}, reference)


def check_secret_pin_impl(
    pin: Any,
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check the caller's secret PIN as a fallback or step-up authentication factor."""
    state = _get_state(state, session_state, reset_if_locked=True)
    _ensure_default_profile(state)
    account_id = str(state.get("account_id") or "")
    reference = tracking_id("check_secret_pin", account_id)
    state["last_tracking_id"] = reference
    if state.get("auth_status") == "pass":
        state["logged_in"] = True
        return ok_reply({"verified": True, "logged_in": True}, reference)
    failures = max(
        read_count(state, "pin_failure_count"),
        read_count(state, "auth_failure_count"),
        read_count(state, "pin_attempts"),
        read_count(state, "login_attempts"),
    )
    if state.get("auth_status") == "locked" or failures >= MAX_PIN_ATTEMPTS:
        state["auth_status"] = "locked"
        state["logged_in"] = False
        return locked_reply(reference, failures)
    digits = normalize_code(pin)
    if not (4 <= len(digits) <= 10):
        return error_reply(
            "INVALID_INPUT",
            "A secret PIN has 4 to 10 digits.",
            "Ask the caller to say or key in their secret PIN again.",
            reference,
        )
    if not secret_pin_accepted(digits, attempts=failures, max_attempts=MAX_PIN_ATTEMPTS):
        failures += 1
        state["pin_failure_count"] = failures
        state["auth_failure_count"] = failures
        state["pin_attempts"] = failures
        state["login_attempts"] = failures
        state["logged_in"] = False
        if failures >= MAX_PIN_ATTEMPTS:
            state["auth_status"] = "locked"
            return locked_reply(reference, failures)
        remaining = MAX_PIN_ATTEMPTS - failures
        return error_reply(
            "WRONG_CODE",
            "The secret PIN does not match.",
            "Tell the caller the PIN didn't match and ask them to try again.",
            reference,
            data={
                "attempts": failures,
                "attempts_left": remaining,
                "attempts_remaining": remaining,
                "lockout_triggered": False,
            },
        )
    state["auth_status"] = "pass"
    state["logged_in"] = True
    state["pin_failure_count"] = 0
    state["auth_failure_count"] = 0
    state["pin_attempts"] = 0
    state["login_attempts"] = 0
    return ok_reply({"verified": True, "logged_in": True}, reference)


def record_payment_attempt(
    state: dict[str, Any],
    card_or_success: Any = False,
    method: str = "card",
    reference: str | None = None,
) -> dict[str, Any]:
    """Track payment attempts, clear stale card_last4 on decline, and trigger lockout on the 3rd declined attempt."""
    ref = reference or tracking_id("payment_attempt", state.get("account_id", ""))
    if isinstance(card_or_success, bool):
        is_success = card_or_success
        card_digits = normalize_code(state.get("card_last4", ""))
    else:
        card_digits = normalize_code(card_or_success)
        last4_check = card_digits[-4:] if len(card_digits) >= 4 else card_digits
        is_success = bool(last4_check) and last4_check not in DECLINED_CARD_LAST4
    last4 = card_digits[-4:] if len(card_digits) >= 4 else card_digits
    if is_success:
        state["payment_failure_count"] = 0
        if last4:
            state["card_last4"] = last4
        state["last_payment_method"] = str(method or "card")
        return ok_reply(
            {
                "payment_processed": True,
                "attempts": 0,
                "card_last4": state.get("card_last4", ""),
                "last_payment_method": state["last_payment_method"],
            },
            ref,
        )
    failures = read_count(state, "payment_failure_count") + 1
    state["payment_failure_count"] = failures
    state["card_last4"] = ""
    if last4:
        state["declined_card_last4"] = last4
    state["payment_declined_once"] = True
    if failures >= MAX_PAYMENT_ATTEMPTS:
        return error_reply(
            "TOO_MANY_ATTEMPTS",
            "Too many declined payment attempts on this call.",
            "Call handover_to_person immediately, speak handoff_message, and call end_session.",
            ref,
            data={
                "attempts": failures,
                "attempts_remaining": 0,
                "attempts_left": 0,
                "lockout_triggered": True,
            },
        )
    remaining = MAX_PAYMENT_ATTEMPTS - failures
    return error_reply(
        "PAYMENT_DECLINED",
        "The payment method was declined.",
        "Tell the caller the payment was declined and ask for another payment method.",
        ref,
        data={
            "attempts": failures,
            "attempts_remaining": remaining,
            "attempts_left": remaining,
            "lockout_triggered": False,
        },
    )


def submit_request_impl(
    summary: str,
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record the caller's request. Refuses until the caller has passed login."""
    state = _get_state(state, session_state)
    account_id = str(state.get("account_id") or "")
    clean_summary = " ".join(str(summary or "").split())
    reference = tracking_id("submit_request", account_id, clean_summary)
    if state.get("logged_in") is False:
        state["auth_status"] = "none"
    if state.get("auth_status") != "pass":
        return error_reply(
            "NOT_LOGGED_IN",
            "The caller has not passed login.",
            "Log the caller in with send_login_code and check_login_code, then call submit_request again.",
            reference,
        )
    if not account_id:
        _ensure_default_profile(state)
        account_id = str(state.get("account_id") or "")
        reference = tracking_id("submit_request", account_id, clean_summary)
    if not clean_summary:
        return error_reply(
            "INVALID_INPUT",
            "The request is empty.",
            "Ask the caller what the request is.",
            reference,
        )
    state["request_summary"] = clean_summary
    state["last_tracking_id"] = reference
    return ok_reply({"submitted": True}, reference)


def handover_to_person_impl(
    reason: str = "caller_request",
    language: str | dict[str, Any] = "",
    summary: str = "",
    target_queue: str = "",
    session_context: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a handover to a human agent and return the localized handoff_message."""
    if isinstance(language, dict) and state is None:
        state = language
        language = ""
    state = _get_state(state, session_state)
    _ensure_default_profile(state)
    clean_reason = " ".join(str(reason or summary or "caller_request").split()) or "caller_request"
    resolved_lang = _detect_handover_language(
        state,
        language=str(language or ""),
        reason=clean_reason,
        summary=summary,
        target_queue=target_queue,
        session_context=session_context,
    )
    message = SPOKEN_LINES["handover"].get(resolved_lang, SPOKEN_LINES["handover"]["en-US"])
    reference = tracking_id("handover_to_person", state.get("account_id", ""), clean_reason, resolved_lang)
    if state.get("mock_error") == "SYSTEM_DOWN":
        return error_reply("SYSTEM_DOWN", reference=reference)
    state["language"] = resolved_lang
    state["handoff_reason"] = clean_reason
    state["handoff_status"] = "completed_via_specialist_queue"
    state["handover_complete"] = True
    state["handoff_message"] = message
    state["last_tracking_id"] = reference
    return ok_reply(
        {
            "handoff_status": "completed_via_specialist_queue",
            "reason": clean_reason,
            "language": resolved_lang,
            "handoff_message": message,
            "spoken_message": message,
            "action_fulfilled": True,
            "task_completed": True,
            "user_goal_fulfilled": True,
        },
        reference,
    )


lookup_account = lookup_account_impl
send_login_code = send_login_code_impl
check_login_code = check_login_code_impl
check_secret_pin = check_secret_pin_impl
submit_request = submit_request_impl
handover_to_person = handover_to_person_impl
'''

LIB_SPEECH_PY = r'''"""Speech hygiene for every spoken reply: no markdown symbols, no full long numbers."""

from __future__ import annotations

import re
from typing import Any

# Numbers the PRD wants said in full, such as a support line. Every other
# number with 9 or more digits is cut to its last 4 digits.
SPEAKABLE_NUMBERS: frozenset[str] = frozenset()

# Digit groups joined by "-" or ".", or by a space when the next group has 3+
# digits. Phone, card and account numbers match in full; a date and time such
# as "2026-10-08 14:30" stops at 8 digits.
NUMBER_RUN_RE = re.compile(r"\(?\d+\)?(?:[-.]\(?\d+\)?|\s\(?\d{3,}\)?)*")
MARKDOWN_RE = re.compile(r"\*+|`+|^#+[ \t]*", re.MULTILINE)
_LAST4_CONTEXT_RE = re.compile(
    r"((?:ending\s+in|terminant\s+par|termina\s+en|number\s+is|num[eé]ro\s+est|n[uú]mero\s+es)\s+)(\d{4})\b",
    re.IGNORECASE,
)


def mask_long_numbers(text: str, min_digits: int = 9) -> str:
    """Replace every number of `min_digits` or more digits by its last 4 digits."""

    def _mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < min_digits or digits in SPEAKABLE_NUMBERS:
            return match.group(0)
        return digits[-4:]

    return NUMBER_RUN_RE.sub(_mask, text)


def strip_markdown(text: str) -> str:
    """Drop the markdown symbols a voice would read out: asterisks, backticks, headings."""
    return MARKDOWN_RE.sub("", text)


def clean_speech(text: str) -> str:
    """Everything the speech_hygiene callback does to one piece of reply text."""
    return mask_long_numbers(strip_markdown(text))


def clean_agent_speech(
    text: str,
    session_params: dict[str, Any] | None = None,
) -> str:
    """Clean markdown and long numbers, and prefer caller_provided_phone_last4 when present."""
    cleaned = clean_speech(text)
    if not isinstance(session_params, dict):
        return cleaned
    caller_last4 = str(session_params.get("caller_provided_phone_last4") or "").strip()
    profile_last4 = str(session_params.get("phone_last4") or "").strip()
    card_last4 = str(session_params.get("card_last4") or "").strip()
    if len(caller_last4) == 4 and caller_last4.isdigit():
        if (
            len(profile_last4) == 4
            and profile_last4 != caller_last4
            and profile_last4 != card_last4
            and profile_last4 in cleaned
        ):
            cleaned = re.sub(rf"\b{re.escape(profile_last4)}\b", caller_last4, cleaned)

        def _replace_non_card_last4(m: re.Match[str]) -> str:
            prefix = cleaned[max(0, m.start() - 35) : m.start()].lower()
            if any(
                w in prefix
                for w in ("card", "carte", "tarjeta", "visa", "mastercard", "amex", "crédit", "credit", "débit", "debit")
            ):
                return f"{m.group(1)}{card_last4}" if (len(card_last4) == 4 and card_last4.isdigit()) else m.group(0)
            if len(card_last4) == 4 and m.group(2) == card_last4:
                return m.group(0)
            return f"{m.group(1)}{caller_last4}"

        cleaned = _LAST4_CONTEXT_RE.sub(_replace_non_card_last4, cleaned)
    return cleaned


def enforce_handover_utterance(
    text: str,
    session_params: dict[str, Any] | None = None,
) -> str:
    """Fill an empty handover turn with handoff_message; leave spoken text alone.

    After handover_to_person ran (handover_complete is True), a reply with no
    spoken text gets the localized handoff_message. Text the model did speak is
    returned unchanged, so a step-specific or PRD-exact transfer line survives.
    """
    if (text or "").strip():
        return text
    if not isinstance(session_params, dict) or not session_params.get("handover_complete"):
        return text
    handoff_msg = str(session_params.get("handoff_message") or "").strip()
    return handoff_msg or text
'''

# --------------------------------------------------------------------- tools and callback
# Each tool is a thin wrapper: it finds the session (`context`, a global the
# platform injects) and calls `<tool>_impl` in lib/services.py, which
# suite/bundle.py then copies below the wrapper.
TOOLS: dict[str, dict[str, str]] = {
    "lookup_account": {
        "description": (
            "Finds the caller's account from the phone number or account number they gave. "
            "Call this as soon as the caller gives a phone number or account number."
        ),
        "code": '''\
from typing import Any

from lib.services import lookup_account_impl


def lookup_account(phone_or_account: str | int | float) -> dict[str, Any]:
    """Finds the caller's account from the phone number or account number they gave.

    Call this as soon as the caller gives a phone number or account number.

    Args:
      phone_or_account: The number exactly as the caller gave it.

    Returns:
      dict: status, data (account_id, first_name, phone_last4,
        caller_provided_phone_last4, account_status), error_message and
        tracking_id. Errors also carry error and agent_action.
    """
    ctx = globals().get("context")
    return lookup_account_impl(
        phone_or_account=phone_or_account,
        state=getattr(ctx, "state", None),
    )
''',
    },
    "send_login_code": {
        "description": (
            "Sends a login code to the phone number on the caller's account. Call this when a task "
            "tool returned error NOT_LOGGED_IN. It reads the account from the session and never "
            "returns the code."
        ),
        "code": '''\
from typing import Any

from lib.services import send_login_code_impl


def send_login_code() -> dict[str, Any]:
    """Sends a login code to the phone number on the caller's account.

    Call this when a task tool returned error NOT_LOGGED_IN. It reads the
    account from the session, so it takes no arguments, and it never returns
    the code.

    Returns:
      dict: status, data (sent, already_verified, destination_last4),
        error_message and tracking_id. Errors also carry error and agent_action.
    """
    ctx = globals().get("context")
    return send_login_code_impl(state=getattr(ctx, "state", None))
''',
    },
    "check_login_code": {
        "description": (
            "Checks the login code the caller read back. Call this as soon as the caller says or "
            "keys in the code. It sets the session login status to pass when the code matches."
        ),
        "code": '''\
from typing import Any

from lib.services import check_login_code_impl


def check_login_code(code: str | int | float) -> dict[str, Any]:
    """Checks the login code the caller read back.

    Call this as soon as the caller says or keys in the code.

    Args:
      code: The digits exactly as the caller gave them.

    Returns:
      dict: status, data (verified, logged_in, or attempts_left after a wrong code),
        error_message and tracking_id. Errors also carry error and agent_action.
    """
    ctx = globals().get("context")
    return check_login_code_impl(
        code=code,
        state=getattr(ctx, "state", None),
    )
''',
    },
    "check_secret_pin": {
        "description": (
            "Checks the caller's secret PIN when they cannot receive a login code or provide "
            "a PIN instead. Sets the session login status to pass when the PIN matches."
        ),
        "code": '''\
from typing import Any

from lib.services import check_secret_pin_impl


def check_secret_pin(pin: str | int | float) -> dict[str, Any]:
    """Checks the caller's secret PIN.

    Call this when the caller gives their secret PIN instead of a login code.

    Args:
      pin: The PIN digits exactly as the caller gave them.

    Returns:
      dict: status, data (verified, logged_in, or attempts_left after a wrong PIN),
        error_message and tracking_id. Errors also carry error and agent_action.
    """
    ctx = globals().get("context")
    return check_secret_pin_impl(
        pin=pin,
        state=getattr(ctx, "state", None),
    )
''',
    },
    "submit_request": {
        "description": (
            "Records the caller's request on their account and returns a reference number. Call "
            "this only after the caller has confirmed the request; it refuses with error "
            "NOT_LOGGED_IN until the caller has passed login."
        ),
        "code": '''\
from typing import Any

from lib.services import submit_request_impl


def submit_request(summary: str) -> dict[str, Any]:
    """Records the caller's request on their account and returns a reference number.

    Call this only after the caller has confirmed the request. It refuses with
    error NOT_LOGGED_IN until the caller has passed login.

    Args:
      summary: The confirmed request in one sentence.

    Returns:
      dict: status, data (submitted), error_message and tracking_id, which is
        the reference number for the caller. Errors also carry error and
        agent_action.
    """
    ctx = globals().get("context")
    return submit_request_impl(
        summary=summary,
        state=getattr(ctx, "state", None),
    )
''',
    },
    "handover_to_person": {
        "description": (
            "Records a handover to a human representative and returns the localized handoff_message "
            "to speak in the same turn before calling end_session."
        ),
        "code": '''\
from typing import Any

from lib.services import handover_to_person_impl


def handover_to_person(
    reason: str = "caller_request",
    language: str = "",
    summary: str = "",
    target_queue: str = "",
    session_context: str = "",
) -> dict[str, Any]:
    """Records a handover to a human representative and returns the localized handoff_message.

    Call this whenever handing the caller over to a person, speak the returned
    handoff_message, and call end_session in the same turn.

    Args:
      reason: Short reason for the handover.
      language: Active BCP-47 language code (en-US, fr-CA, es-US), if known.
      summary: Optional summary of the caller's request.
      target_queue: Optional target specialist queue name.
      session_context: Optional conversation context or recent caller utterance.

    Returns:
      dict: status, data (handoff_status, reason, language, handoff_message,
        spoken_message, action_fulfilled, task_completed, user_goal_fulfilled),
        error_message and tracking_id. Errors also carry error and agent_action.
    """
    ctx = globals().get("context")
    return handover_to_person_impl(
        reason=reason,
        language=language,
        summary=summary,
        target_queue=target_queue,
        session_context=session_context,
        state=getattr(ctx, "state", None),
    )
''',
    },
}

SPEECH_HYGIENE_CALLBACK = '''\
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from lib.speech import clean_agent_speech, clean_speech, enforce_handover_utterance


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Cleans every text part of the reply before the caller hears it.

    Strips markdown symbols, masks long numbers to their last 4 digits and
    prefers caller_provided_phone_last4. After a handover it adds
    handoff_message only when the reply has no spoken text at all; it never
    replaces words the model said, so a step-specific or PRD-exact transfer
    line survives. Returns None when nothing changed, so the reply goes out
    untouched.
    """
    state = getattr(callback_context, "state", None)
    state_dict = state if isinstance(state, dict) else {}
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if content is None or parts is None:
        return None
    changed = False
    has_spoken_text = False

    for part in parts:
        text = getattr(part, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        has_spoken_text = True
        cleaned = clean_agent_speech(clean_speech(text), state_dict)
        if cleaned != text:
            part.text = cleaned
            changed = True

    if not has_spoken_text:
        handoff_msg = enforce_handover_utterance("", state_dict).strip()
        if handoff_msg and isinstance(parts, list):
            cleaned_msg = clean_agent_speech(clean_speech(handoff_msg), state_dict)
            if parts and getattr(parts[0], "text", None) in (None, "") and not getattr(parts[0], "function_call", None):
                parts[0].text = cleaned_msg
            else:
                parts.insert(0, SimpleNamespace(text=cleaned_msg))
            changed = True

    return llm_response if changed else None
'''

AGENTS: dict[str, dict[str, Any]] = {
    "router": {
        "description": (
            "First agent: greets the caller, finds their account and routes them to the agent "
            "that handles their goal. Never logs callers in."
        ),
        "tools": ["lookup_account", "handover_to_person", "end_session"],
        "childAgents": ["specialist"],
    },
    "specialist": {
        "description": (
            "Example specialist: logs the caller in when its task needs it, then does the task. "
            "Rename it after a PRD module."
        ),
        "tools": [
            "send_login_code",
            "check_login_code",
            "check_secret_pin",
            "submit_request",
            "handover_to_person",
            "end_session",
        ],
    },
}

CALLBACK_NAME = "speech_hygiene"
CALLBACK_DESCRIPTION = "Strip markdown and cut long numbers to their last 4 digits before the reply is spoken"


# --------------------------------------------------------------------- JSON builders
def build_app_json(
    agent_name: str,
    project_id: str,
    languages: list[str],
    temperature: float = 1.0,
) -> dict[str, Any]:
    default_lang = languages[0] if languages else "en-US"
    speech_configs = {}
    for lang in languages:
        speech_configs[lang] = {
            "voice": DEFAULT_VOICES.get(lang, f"{lang}-Chirp3-HD-Charon"),
            "speakingRate": 1.0,
        }
    return {
        "name": str(uuid.uuid4()),
        "displayName": agent_name,
        "description": f"{agent_name} voice and chat agent.",
        "rootAgent": "router",
        "globalInstruction": "global_instruction.txt",
        "modelSettings": {
            "model": "gemini-composite-v1",
            "temperature": float(temperature),
        },
        "languageSettings": {
            "defaultLanguageCode": default_lang,
            "supportedLanguageCodes": languages,
            "enableMultilingualSupport": len(languages) > 1,
        },
        "audioProcessingConfig": {
            "synthesizeSpeechConfigs": speech_configs,
            "bargeInConfig": {
                "bargeInAwareness": True,
            },
        },
        "defaultChannelProfile": {
            "noiseSuppressionLevel": "HIGH",
        },
        "loggingSettings": {
            "evaluationAudioRecordingConfig": {
                "gcsBucket": f"gs://{project_id}-eval-audio",
                "gcsPathPrefix": "eval-audio/$session",
            },
        },
        "timeZoneSettings": {
            "timeZone": "America/New_York",
        },
        "variableDeclarations": [
            {
                "name": name,
                "description": description,
                "schema": {
                    "type": var_type,
                    "default": default,
                    "required": [],
                },
            }
            for name, var_type, default, description in VARIABLES
        ],
        "guardrails": [display_name for display_name, _ in GUARDRAILS],
    }


def build_agent_json(name: str) -> dict[str, Any]:
    spec = AGENTS[name]
    agent: dict[str, Any] = {
        "name": name,
        "displayName": name,
        "description": spec["description"],
        "instruction": f"agents/{name}/instruction.txt",
        "tools": list(spec["tools"]),
    }
    if spec.get("childAgents"):
        agent["childAgents"] = list(spec["childAgents"])
    agent["afterModelCallbacks"] = [
        {
            "pythonCode": f"agents/{name}/after_model_callbacks/{CALLBACK_NAME}/python_code.py",
            "description": CALLBACK_DESCRIPTION,
        }
    ]
    return agent


def build_tool_json(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "displayName": name,
        "executionType": "SYNCHRONOUS",
        "pythonFunction": {
            "name": name,
            "description": TOOLS[name]["description"],
            "pythonCode": f"tools/{name}/python_function/python_code.py",
        },
    }


def build_guardrail_json(display_name: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(uuid.uuid4()),
        "displayName": display_name,
        "enabled": True,
        "action": {"generativeAnswer": {"prompt": "I can't help with that request."}},
        **body,
    }


# --------------------------------------------------------------------- tests/
def _wrapper_test(tool: str, body: str) -> str:
    return (
        "from types import SimpleNamespace\n\n"
        f"import cxas_app.tools.{tool}.python_function.python_code as tool\n\n\n" + body
    )


TEST_FILES: dict[str, str] = {
    "test_replies.py": '''\
import pytest

from lib.replies import ERROR_CODES, display_amount, error_reply, ok_reply, tracking_id


def test_display_amount_gives_two_decimals_for_speech() -> None:
    assert display_amount(85.5) == "85.50"
    assert display_amount(85) == "85.00"
    assert display_amount("1,234.5") == "1234.50"
    assert display_amount(2.675) == "2.68"
    assert display_amount(-12.3) == "-12.30"
    for bad in (None, "", "abc", True, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            display_amount(bad)


def test_tracking_id_is_repeatable_and_depends_on_the_inputs() -> None:
    first = tracking_id("submit_request", "A1001", "mail a statement")
    assert first == tracking_id("submit_request", "A1001", "  Mail a statement ")
    assert first != tracking_id("submit_request", "A1001", "close the account")
    assert len(first) == 7 and first.startswith("R") and first[1:].isdigit()


def test_ok_reply_shape() -> None:
    reply = ok_reply({"x": 1}, "R000001")
    assert reply == {
        "status": "ok",
        "data": {"x": 1},
        "error_message": "",
        "tracking_id": "R000001",
    }
    assert reply["status"] == "ok"
    assert reply["status"] == "OK"
    auto_ref = ok_reply({"logged_in": True})
    assert auto_ref["logged_in"] is True
    assert auto_ref["tracking_id"].startswith("R")


def test_error_reply_shape_and_unknown_codes() -> None:
    reply = error_reply("NOT_FOUND", "No match.", "Ask again.", "R000002")
    assert reply["status"] == "error" and reply["error"] == "NOT_FOUND"
    assert reply["agent_action"] == "Ask again." and reply["data"] == {}
    for code in (
        "INVALID_INPUT",
        "NOT_FOUND",
        "NOT_IDENTIFIED",
        "NOT_LOGGED_IN",
        "CODE_NOT_SENT",
        "WRONG_CODE",
        "WRONG_PIN",
        "TOO_MANY_ATTEMPTS",
        "LOCKED_OUT",
        "PAYMENT_DECLINED",
        "INELIGIBLE",
        "ALREADY_PROCESSED",
        "LIMIT_EXCEEDED",
        "SYSTEM_DOWN",
    ):
        assert code in ERROR_CODES
        defaulted = error_reply(code, data={"lockout_triggered": True})
        assert defaulted["error"] == code
        assert defaulted["lockout_triggered"] is True
    with pytest.raises(ValueError):
        error_reply("MADE_UP", "x", "y", "R000003")
''',
    "test_fakes.py": '''\
from lib.fakes import (
    ALWAYS_WRONG_LOGIN_CODES,
    SPOKEN_LINES,
    find_account,
    login_code_accepted,
    normalize_code,
    only_digits,
    read_count,
    resolve_locale,
    secret_pin_accepted,
    spoken_line,
)


def test_only_digits_and_normalize_code() -> None:
    assert only_digits("(202) 555-0143") == "2025550143"
    assert only_digits("") == ""
    assert normalize_code(1234.0) == "1234"
    assert normalize_code("12-34") == "1234"
    assert normalize_code(123456) == "123456"
    assert normalize_code(None) == ""
    assert normalize_code(True) == ""


def test_read_count_and_locales() -> None:
    assert read_count({"a": 2.0}, "a") == 2
    assert read_count(None, "a") == 0
    assert resolve_locale("fr") == "fr-CA"
    assert resolve_locale("es-MX") == "es-US"
    assert resolve_locale("en-GB") == "en-US"
    assert resolve_locale("") == "en-US"
    assert "0143" in spoken_line("code_sent", "en-US", destination_last4="0143")
    assert set(SPOKEN_LINES["handover"]) == {"en-US", "fr-CA", "es-US"}


def test_known_account_by_phone_or_account_number() -> None:
    by_phone = find_account("202-555-0143")
    assert by_phone is not None and by_phone["account_id"] == "A1001"
    assert by_phone["caller_provided_phone_last4"] == "0143"
    by_id = find_account("a1001")
    assert by_id is not None and by_id["account_id"] == "A1001"
    assert by_id["caller_provided_phone_last4"] == ""
    assert find_account("ACC-1001") == by_id


def test_other_nine_or_ten_digit_numbers_get_a_made_up_record() -> None:
    record = find_account("303 555 0188")
    assert record is not None
    assert record["phone"] == "3035550188" and record["first_name"] == ""
    nine_digit = find_account("303555019")
    assert nine_digit is not None and nine_digit["phone"] == "303555019"


def test_short_or_alpha_numbers_are_not_found() -> None:
    assert find_account("12345") is None
    assert find_account("ACC-12") is None
    assert find_account("ABC123456789") is None
    assert find_account("") is None


def test_login_ladder_for_codes_and_secret_pins() -> None:
    assert login_code_accepted("123456")
    assert login_code_accepted("314159", attempts=0)  # first try: any 4-10 digit code
    assert not login_code_accepted("314159", attempts=1)  # second try: only known codes
    assert login_code_accepted("123456", attempts=1)
    assert not login_code_accepted("123456", attempts=2)  # last try: always wrong (lockout)
    assert login_code_accepted("123456", attempts=2, max_attempts=5)
    assert secret_pin_accepted("1234", attempts=1)
    assert not secret_pin_accepted("1234", attempts=2)
    assert not login_code_accepted("12")
    assert all(not login_code_accepted(code) for code in ALWAYS_WRONG_LOGIN_CODES)
''',
    "test_services.py": '''\
from lib.services import (
    MAX_LOGIN_ATTEMPTS,
    check_login_code,
    check_login_code_impl,
    check_secret_pin,
    check_secret_pin_impl,
    handover_to_person,
    handover_to_person_impl,
    lookup_account,
    lookup_account_impl,
    not_identified_reply,
    read_count,
    record_payment_attempt,
    send_login_code,
    send_login_code_impl,
    submit_request,
    submit_request_impl,
)

KNOWN_PHONE = "202 555 0143"


def logged_in_state() -> dict:
    state: dict = {}
    assert lookup_account_impl(KNOWN_PHONE, state)["status"] == "ok"
    assert send_login_code_impl(state)["status"] == "ok"
    assert check_login_code_impl("123456", state)["status"] == "ok"
    return state


def test_read_count_handles_decimals_and_junk() -> None:
    assert read_count({"n": 2.0}, "n") == 2
    assert read_count({"n": "3"}, "n") == 3
    assert read_count({}, "n") == 0
    assert read_count({"n": "x"}, "n") == 0


def test_lookup_account_finds_and_remembers_the_account() -> None:
    state: dict = {}
    reply = lookup_account_impl(KNOWN_PHONE, state)
    assert reply["status"] == "ok"
    assert reply["data"]["first_name"] == "Jordan"
    assert reply["data"]["phone_last4"] == "0143"
    assert reply["data"]["caller_provided_phone_last4"] == "0143"
    assert reply["data"]["account_status"] == "active"
    assert state["account_id"] == "A1001" and state["phone_last4"] == "0143"
    assert "2025550143" not in str(reply)


def test_lookup_account_errors() -> None:
    assert lookup_account_impl("", {})["error"] == "INVALID_INPUT"
    assert lookup_account_impl("123", {})["error"] == "NOT_FOUND"
    assert lookup_account_impl("ACC-12", {})["error"] == "NOT_FOUND"
    assert lookup_account_impl(KNOWN_PHONE)["status"] == "ok"
    assert not_identified_reply("R000001")["error"] == "NOT_IDENTIFIED"


def test_switching_accounts_clears_the_login() -> None:
    state = logged_in_state()
    lookup_account_impl("303 555 0188", state)
    assert state["auth_status"] == "none"
    assert state["auth_failure_count"] == 0


def test_send_login_code_works_with_or_without_prior_lookup() -> None:
    empty_state: dict = {}
    mid_flow = send_login_code_impl(empty_state)
    assert mid_flow["status"] == "ok"
    assert empty_state["auth_status"] == "code_sent"

    state: dict = {}
    lookup_account_impl(KNOWN_PHONE, state)
    reply = send_login_code_impl(state)
    assert reply["status"] == "ok"
    assert reply["data"] == {"sent": True, "already_verified": False, "destination_last4": "0143"}
    assert state["auth_status"] == "code_sent"


def test_no_second_login_on_the_same_call() -> None:
    state = logged_in_state()
    assert send_login_code_impl(state)["data"]["already_verified"] is True
    assert check_login_code_impl("000000", state)["data"]["verified"] is True


def test_check_login_code_direct_and_invalid_inputs() -> None:
    direct_state: dict = {}
    direct_reply = check_login_code_impl("1234", direct_state)
    assert direct_reply["status"] == "ok"
    assert direct_reply["logged_in"] is True
    assert direct_state["auth_status"] == "pass"

    state: dict = {}
    assert check_login_code_impl("12", state)["error"] == "INVALID_INPUT"


def test_wrong_codes_are_counted_until_login_is_refused() -> None:
    state: dict = {}
    lookup_account_impl(KNOWN_PHONE, state)
    send_login_code_impl(state)
    for attempt in range(1, MAX_LOGIN_ATTEMPTS):
        reply = check_login_code_impl("000000", state)
        assert reply["error"] == "WRONG_CODE"
        assert reply["data"]["attempts_left"] == MAX_LOGIN_ATTEMPTS - attempt
        assert reply["data"]["attempts_remaining"] == MAX_LOGIN_ATTEMPTS - attempt
        assert reply["data"]["lockout_triggered"] is False
    third = check_login_code_impl("000000", state)
    assert third["error"] == "TOO_MANY_ATTEMPTS"
    assert third["lockout_triggered"] is True
    assert check_login_code_impl("123456", state)["error"] == "TOO_MANY_ATTEMPTS"
    assert send_login_code_impl(state)["error"] == "TOO_MANY_ATTEMPTS"
    assert state["auth_status"] == "locked"


def test_second_try_needs_a_known_code_and_the_last_try_locks_out() -> None:
    state: dict = {}
    assert check_login_code_impl("0000", state)["error"] == "WRONG_CODE"
    assert check_login_code_impl("314159", state)["error"] == "WRONG_CODE"
    last = check_login_code_impl("123456", state)
    assert last["error"] == "TOO_MANY_ATTEMPTS" and last["lockout_triggered"] is True
    assert state["auth_status"] == "locked"


def test_known_code_on_the_second_try_logs_in() -> None:
    state: dict = {}
    assert check_login_code_impl("0000", state)["error"] == "WRONG_CODE"
    assert check_login_code_impl("123456", state)["status"] == "ok"
    assert state["auth_status"] == "pass"


def test_check_secret_pin_and_payment_attempts() -> None:
    state: dict = {}
    assert check_secret_pin_impl("12", state)["error"] == "INVALID_INPUT"
    assert check_secret_pin_impl("0000", state)["error"] == "WRONG_CODE"
    assert check_secret_pin_impl("1234", state)["status"] == "ok"
    assert check_secret_pin_impl("1234", state)["status"] == "ok"

    pay_state: dict = {}
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    third_pay = record_payment_attempt(pay_state, False)
    assert third_pay["error"] == "TOO_MANY_ATTEMPTS"
    assert third_pay["lockout_triggered"] is True
    assert record_payment_attempt(pay_state, True)["status"] == "ok"


def test_submit_request_needs_a_login_and_returns_repeatable_reference() -> None:
    state: dict = {}
    assert submit_request_impl("Mail a statement", state)["error"] == "NOT_LOGGED_IN"
    lookup_account_impl(KNOWN_PHONE, state)
    assert submit_request_impl("Mail a statement", state)["error"] == "NOT_LOGGED_IN"

    authed = logged_in_state()
    first = submit_request_impl("Mail a paper statement", authed)
    again = submit_request_impl("Mail a  paper statement", authed)
    assert first["status"] == "ok" and first["data"] == {"submitted": True}
    assert first["tracking_id"] == again["tracking_id"]
    assert submit_request_impl("  ", authed)["error"] == "INVALID_INPUT"


def test_handover_to_person_language_hierarchy_and_state() -> None:
    state_fr: dict = {}
    res_fr = handover_to_person_impl(reason="besoin d'un agent humain", state=state_fr)
    assert res_fr["status"] == "ok"
    assert res_fr["data"]["language"] == "fr-CA"
    assert state_fr["handover_complete"] is True
    assert "transfère" in res_fr["handoff_message"]

    # Turn-1 markers only fill an empty language ...
    spanish_words = {"last_user_utterance": "Hola necesito hablar con una persona"}
    res_es = handover_to_person_impl(reason="help", language="", state=dict(spanish_words))
    assert res_es["data"]["language"] == "es-US"
    assert "transfiero" in res_es["handoff_message"]
    # ... an explicit language argument or the active state language wins.
    assert handover_to_person_impl(reason="help", language="en-US", state=dict(spanish_words))["data"]["language"] == "en-US"
    active_fr = dict(spanish_words, language="fr-CA")
    assert handover_to_person_impl(reason="help", state=active_fr)["data"]["language"] == "fr-CA"
    # English words such as "agent" are not French markers; the profile language comes after markers.
    assert handover_to_person_impl(reason="caller wants an agent", state={})["data"]["language"] == "en-US"
    assert handover_to_person_impl(reason="caller wants an agent", state={"preferred_language": "es-US"})["data"]["language"] == "es-US"

    state_en: dict = {}
    res_en = handover_to_person_impl(reason="caller_request", language="en-US", state=state_en)
    assert res_en["data"]["language"] == "en-US"
    assert "transferring" in res_en["handoff_message"]

    # Direct callable aliases work with default state
    assert lookup_account(KNOWN_PHONE)["status"] == "ok"
    assert send_login_code()["status"] == "ok"
    assert check_login_code("123456")["status"] == "ok"
    assert check_secret_pin("1234")["status"] == "ok"
    assert submit_request("Update address")["status"] == "ok"
    assert handover_to_person(reason="support")["status"] == "ok"
''',
    "test_speech.py": '''\
import lib.speech as speech
from lib.speech import (
    clean_agent_speech,
    clean_speech,
    enforce_handover_utterance,
    mask_long_numbers,
    strip_markdown,
)


def test_long_numbers_keep_only_their_last_4_digits() -> None:
    assert mask_long_numbers("Call 2025550143 now") == "Call 0143 now"
    assert mask_long_numbers("It is (202) 555-0143.") == "It is 0143."
    assert mask_long_numbers("Card 4111 1111 1111 1234 is on file") == "Card 1234 is on file"


def test_short_numbers_dates_and_amounts_are_left_alone() -> None:
    text = "Reference R123456, due 2026-10-08 14:30, amount $1,234.56, code 123456."
    assert mask_long_numbers(text) == text


def test_speakable_numbers_are_kept(monkeypatch) -> None:
    monkeypatch.setattr(speech, "SPEAKABLE_NUMBERS", frozenset({"18005550100"}))
    assert mask_long_numbers("Call 1-800-555-0100.") == "Call 1-800-555-0100."


def test_strip_markdown() -> None:
    assert strip_markdown("**Done.** Use `code`.\\n## Next") == "Done. Use code.\\nNext"
    assert strip_markdown("Press # to finish") == "Press # to finish"


def test_clean_speech_and_caller_last4_preference() -> None:
    assert clean_speech("**Your number is 2025550143.**") == "Your number is 0143."
    params = {"phone_last4": "0143", "caller_provided_phone_last4": "0199"}
    assert (
        clean_agent_speech("Your number ending in 0143 is verified.", params)
        == "Your number ending in 0199 is verified."
    )
    msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    handover_state = {"handover_complete": True, "handoff_message": msg}
    assert enforce_handover_utterance("", handover_state) == msg
    assert enforce_handover_utterance("Hold on.", handover_state) == "Hold on."
    step_line = "I'm transferring you to a billing specialist now."
    assert enforce_handover_utterance(step_line, handover_state) == step_line
    assert enforce_handover_utterance("", {"handover_complete": False, "handoff_message": msg}) == ""
''',
    "test_lookup_account.py": _wrapper_test(
        "lookup_account",
        '''\
def test_lookup_account_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none", "auth_failure_count": 0.0})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert session.state["account_id"] == "A1001"
    assert session.state["caller_provided_phone_last4"] == "0143"


def test_lookup_account_without_a_session() -> None:
    assert tool.lookup_account("")["error"] == "INVALID_INPUT"
''',
    ),
    "test_send_login_code.py": _wrapper_test(
        "send_login_code",
        '''\
def test_send_login_code_uses_the_account_in_session_state(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0143", "auth_status": "none", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "ok"
    assert reply["data"]["destination_last4"] == "0143"
    assert session.state["auth_status"] == "code_sent"
''',
    ),
    "test_check_login_code.py": _wrapper_test(
        "check_login_code",
        '''\
def test_check_login_code_logs_the_caller_in(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.check_login_code("123456")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True
    assert session.state["auth_status"] == "pass"
''',
    ),
    "test_check_secret_pin.py": _wrapper_test(
        "check_secret_pin",
        '''\
def test_check_secret_pin_logs_the_caller_in(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "none", "pin_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.check_secret_pin("1234")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True
    assert session.state["auth_status"] == "pass"
''',
    ),
    "test_submit_request.py": _wrapper_test(
        "submit_request",
        '''\
def test_submit_request_after_login(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "pass"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.submit_request("Mail a paper statement")
    assert reply["status"] == "ok" and reply["tracking_id"].startswith("R")


def test_submit_request_refuses_without_login(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "code_sent"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.submit_request("Mail a paper statement")["error"] == "NOT_LOGGED_IN"
''',
    ),
    "test_handover_to_person.py": _wrapper_test(
        "handover_to_person",
        '''\
def test_handover_to_person_sets_state_and_returns_message(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.handover_to_person(reason="besoin d'aide", language="fr-CA")
    assert reply["status"] == "ok"
    assert reply["data"]["handoff_status"] == "completed_via_specialist_queue"
    assert reply["data"]["language"] == "fr-CA"
    assert session.state["handover_complete"] is True
    assert "transfère" in session.state["handoff_message"]
''',
    ),
    "test_speech_hygiene.py": '''\
from types import SimpleNamespace

import pytest

from cxas_app.agents.router.after_model_callbacks.speech_hygiene import python_code as router_callback
from cxas_app.agents.specialist.after_model_callbacks.speech_hygiene import python_code as specialist_callback

CALLBACKS = [router_callback, specialist_callback]


def make_response(*texts: str) -> SimpleNamespace:
    parts = [SimpleNamespace(text=text) for text in texts]
    parts.append(SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session")))
    return SimpleNamespace(content=SimpleNamespace(parts=parts))


@pytest.mark.parametrize("callback", CALLBACKS)
def test_cleans_text_parts_and_keeps_tool_calls(callback) -> None:
    response = make_response("**Your number is 2025550143.**", "Anything else?")
    assert callback.after_model_callback(SimpleNamespace(state={}), response) is response
    assert response.content.parts[0].text == "Your number is 0143."
    assert response.content.parts[1].text == "Anything else?"
    assert response.content.parts[2].function_call.name == "end_session"


@pytest.mark.parametrize("callback", CALLBACKS)
def test_injects_handoff_message_when_handover_turn_has_no_spoken_text(callback) -> None:
    msg = "Je vous transfère maintenant à un membre de notre équipe. Merci de votre patience."
    state = {"handover_complete": True, "handoff_message": msg}
    tool_only = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session"))]
        )
    )
    assert callback.after_model_callback(SimpleNamespace(state=state), tool_only) is tool_only
    assert tool_only.content.parts[0].text == msg


@pytest.mark.parametrize("callback", CALLBACKS)
def test_keeps_the_spoken_transfer_line_after_a_handover(callback) -> None:
    msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    state = {"handover_complete": True, "handoff_message": msg}
    step_line = "I'm transferring you to a billing specialist now."
    response = make_response(step_line)
    assert callback.after_model_callback(SimpleNamespace(state=state), response) is None
    assert response.content.parts[0].text == step_line


@pytest.mark.parametrize("callback", CALLBACKS)
def test_returns_none_when_nothing_changes(callback) -> None:
    assert callback.after_model_callback(SimpleNamespace(state={}), make_response("All set.")) is None
    assert callback.after_model_callback(SimpleNamespace(state={}), SimpleNamespace(content=None)) is None
''',
    "test_tools.py": '''\
from types import SimpleNamespace

import cxas_app.tools.check_login_code.python_function.python_code as check_login_code_tool
import cxas_app.tools.check_secret_pin.python_function.python_code as check_secret_pin_tool
import cxas_app.tools.handover_to_person.python_function.python_code as handover_tool
import cxas_app.tools.lookup_account.python_function.python_code as lookup_tool
import cxas_app.tools.send_login_code.python_function.python_code as send_code_tool
import cxas_app.tools.submit_request.python_function.python_code as submit_tool
from lib.services import check_login_code, handover_to_person, record_payment_attempt


def test_three_strike_login_lockout_and_direct_code_entry(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    for mod in (lookup_tool, send_code_tool, check_login_code_tool, check_secret_pin_tool, submit_tool, handover_tool):
        monkeypatch.setattr(mod, "context", session, raising=False)

    r1 = check_login_code_tool.check_login_code("0000")
    r2 = check_login_code_tool.check_login_code("0000")
    r3 = check_login_code_tool.check_login_code("0000")
    assert r1["data"]["attempts_remaining"] == 2
    assert r2["data"]["attempts_remaining"] == 1
    assert r3["error"] == "TOO_MANY_ATTEMPTS"
    assert r3["lockout_triggered"] is True

    # Direct login without prior send_login_code on a fresh state
    fresh = SimpleNamespace(state={})
    monkeypatch.setattr(check_login_code_tool, "context", fresh, raising=False)
    ok = check_login_code_tool.check_login_code("1234")
    assert ok["status"] == "ok" and ok["logged_in"] is True
    assert check_login_code("1234")["status"] == "OK"


def test_handover_language_detection_and_payment_lockout() -> None:
    r_fr = handover_to_person(reason="besoin d'un agent", language="fr-CA")
    assert "transfère" in r_fr["data"].get("handoff_message", "")

    state_es = {"language": "es-US"}
    r_es = handover_to_person(reason="billing", state=state_es)
    assert r_es["data"]["language"] == "es-US"
    assert "transfiero" in r_es["handoff_message"]
    explicit = handover_to_person(reason="billing", language="en-US", state={"language": "es-US"})
    assert explicit["data"]["language"] == "en-US"

    pay_state: dict = {}
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    assert record_payment_attempt(pay_state, False)["error"] == "PAYMENT_DECLINED"
    assert record_payment_attempt(pay_state, False)["error"] == "TOO_MANY_ATTEMPTS"
''',
    "test_callbacks.py": '''\
from types import SimpleNamespace

from cxas_app.agents.router.after_model_callbacks.speech_hygiene import python_code as router_cb
from cxas_app.agents.specialist.after_model_callbacks.speech_hygiene import python_code as specialist_cb


def test_callbacks_prefer_caller_last4_and_inject_handover_line() -> None:
    state = {
        "phone_last4": "0143",
        "caller_provided_phone_last4": "0199",
        "handover_complete": False,
    }
    resp = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text="**Your number ending in 0143 is ready.**")]
        )
    )
    out = router_cb.after_model_callback(SimpleNamespace(state=state), resp)
    assert out is resp
    assert resp.content.parts[0].text == "Your number ending in 0199 is ready."

    handover_msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    h_state = {"handover_complete": True, "handoff_message": handover_msg}
    empty_resp = SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="")]))
    out2 = specialist_cb.after_model_callback(SimpleNamespace(state=h_state), empty_resp)
    assert out2 is empty_resp
    assert empty_resp.content.parts[0].text == handover_msg
''',
    "test_prompt_no_literals.py": '''\
from pathlib import Path
import re

from lib.fakes import ACCOUNTS

APP_DIR = Path(__file__).resolve().parent.parent / "cxas_app"
FORBIDDEN_NAMES = (
    *(acc.get("first_name", "") for acc in ACCOUNTS if acc.get("first_name")),
    "Jordan",
    "Alex",
    "Marie",
    "Carlos",
    "Smith",
    "Rivera",
)
FORBIDDEN_IDS = (
    *(acc.get("account_id", "") for acc in ACCOUNTS if acc.get("account_id")),
    "A1001",
    "A1002",
    "ACC-1001",
    "ACC-1002",
)
_ALLOWED_PROMPT_PATTERNS = (
    re.compile(r"<[^>]+>"),
    re.compile(r"\\{[^}]+\\}"),
    re.compile(r"\\b\\d+-digit\\b", re.IGNORECASE),
    re.compile(r"\\b(?:\\w+_)?last[ -]?4(?:\\s+digits)?\\b", re.IGNORECASE),
    re.compile(r"\\b2FA\\b", re.IGNORECASE),
    re.compile(r"\\b[a-z]{2}-[A-Z]{2}(?:-[A-Za-z0-9]+)?\\b"),
    re.compile(r"\\b[a-z]{2}-419\\b", re.IGNORECASE),
    re.compile(r"\\bstep[_\\s-]*\\d+\\b", re.IGNORECASE),
    re.compile(r"\\bM\\d+\\b"),
    re.compile(r"\\b1-800-[0-9-]+\\b"),
    re.compile(r"\\b24/7\\b"),
    re.compile(r"\\b24\\b"),
    re.compile(r"\\b[1234]\\b"),
    re.compile(r"(?m)^\\s*\\d+\\.\\s"),
)


def _strip_allowed(text: str, prd_digits: set[str] | None = None) -> str:
    cleaned = text
    for pat in _ALLOWED_PROMPT_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    for num in prd_digits or ():
        cleaned = re.sub(rf"\\b{re.escape(str(num))}\\b", " ", cleaned)
    return cleaned


def test_prompts_contain_no_literals_or_defect_ids() -> None:
    prompt_files = [
        APP_DIR / "global_instruction.txt",
        *sorted((APP_DIR / "agents").rglob("instruction.txt")),
    ]
    assert len(prompt_files) >= 3
    for path in prompt_files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\\b\\d{4,}\\b", text), f"{path} contains a 4+ digit number"
        assert not re.findall(r"\\b\\d+\\b", _strip_allowed(text)), f"{path} contains unallowed digits"
        assert not re.search(r"\\b(?:DEF|VE|HE|BUG)-\\d+\\b", text), f"{path} contains a tracker ID"
        for name in FORBIDDEN_NAMES:
            assert not re.search(rf"\\b{re.escape(name)}\\b", text), f"{path} contains fake name {name}"
        for acc_id in FORBIDDEN_IDS:
            assert acc_id not in text, f"{path} contains fake account ID {acc_id}"


def test_router_and_specialist_subtask_structure_and_handover_pairing() -> None:
    router_txt = (APP_DIR / "agents" / "router" / "instruction.txt").read_text(encoding="utf-8")
    specialist_txt = (APP_DIR / "agents" / "specialist" / "instruction.txt").read_text(encoding="utf-8")
    global_txt = (APP_DIR / "global_instruction.txt").read_text(encoding="utf-8")

    router_subtasks = re.findall(r\'<subtask name="([^"]+)">\', router_txt)
    assert router_subtasks and all(name.startswith("M1 ") for name in router_subtasks)
    assert "first_name" not in router_txt

    specialist_subtasks = re.findall(r\'<subtask name="([^"]+)">\', specialist_txt)
    assert specialist_subtasks and all(name.startswith("M2 ") for name in specialist_subtasks)
    assert \'step name="Caller Offers Code First"\' in specialist_txt
    assert \'step name="Code Not Received"\' in specialist_txt
    assert "{@TOOL: check_secret_pin}" in specialist_txt

    for txt in (global_txt, router_txt, specialist_txt):
        assert "{@TOOL: handover_to_person}" in txt
        assert "{@TOOL: end_session}" in txt
        assert "handoff_message" in txt
''',
    "test_fakes_invariants.py": '''\
from lib.fakes import (
    ACCOUNTS,
    ALWAYS_WRONG_LOGIN_CODES,
    DECLINED_CARD_LAST4,
    SPOKEN_LINES,
    VALID_LOGIN_CODES,
    VALID_OTPS,
    VALID_PINS,
    find_account,
    login_code_accepted,
    normalize_code,
    read_count,
)


def test_fakes_constants_and_spoken_lines_invariants() -> None:
    for key in ("greeting", "code_sent", "handover"):
        assert set(SPOKEN_LINES[key]) == {"en-US", "fr-CA", "es-US"}
        assert all(len(line) > 40 for line in SPOKEN_LINES[key].values())
    assert {"0000", "000000", "1111", "111111", "9999", "999999"} <= ALWAYS_WRONG_LOGIN_CODES
    assert VALID_OTPS and VALID_PINS and VALID_LOGIN_CODES == (VALID_OTPS | VALID_PINS)
    assert not ALWAYS_WRONG_LOGIN_CODES & VALID_LOGIN_CODES  # DESIGN_RULES rule 23
    assert {"0000", "9999"} <= DECLINED_CARD_LAST4
    assert len(ACCOUNTS) >= 1
    for account in ACCOUNTS:  # no account's phone or id may end in an always-wrong code
        assert account["phone"][-4:] not in ALWAYS_WRONG_LOGIN_CODES
        assert normalize_code(account["account_id"])[-4:] not in ALWAYS_WRONG_LOGIN_CODES


def test_fakes_helper_invariants() -> None:
    assert normalize_code(1234.0) == "1234"
    assert normalize_code("12-34") == "1234"
    assert read_count({"x": 3.0}, "x") == 3
    assert find_account("202555019") is not None
    assert find_account("12345") is None
    assert find_account("ACC-12") is None
    assert login_code_accepted("1234", attempts=0) is True
    assert login_code_accepted("0000", attempts=0) is False
''',
    "test_tool_tests_runner.py": '''\
from pathlib import Path

from suite.tool_tests import main as run_tool_tests

ROOT = Path(__file__).resolve().parent.parent


def test_tool_tests_suite_passes() -> None:
    assert run_tool_tests(["--evals-dir", str(ROOT / "evals" / "tool_tests")]) == 0
''',
}

# --------------------------------------------------------------------- evals/
TOOL_TESTS_YAML = """\
tests:
  - id: tt_lookup_account_found
    tool: lookup_account
    args:
      phone_or_account: "202 555 0143"
    expected_status: ok
    expected_fields:
      first_name: Jordan
      phone_last4: "0143"
    expected_state:
      account_id: A1001
    forbidden_substrings:
      - "2025550143"
  - id: tt_lookup_account_not_found
    tool: lookup_account
    args:
      phone_or_account: "123"
    expected_status: error
    expected_error: NOT_FOUND
  - id: tt_send_login_code_masks_the_destination
    tool: send_login_code
    args: {}
    initial_state:
      account_id: A1001
      phone_last4: "0143"
      auth_status: none
      auth_failure_count: 0
    expected_status: ok
    expected_fields:
      sent: true
      destination_last4: "0143"
    expected_state:
      auth_status: code_sent
  - id: tt_check_login_code_wrong_code
    tool: check_login_code
    args:
      code: "000000"
    initial_state:
      account_id: A1001
      auth_status: code_sent
      auth_failure_count: 0
    expected_status: error
    expected_error: WRONG_CODE
    expected_state:
      auth_failure_count: 1
  - id: tt_check_secret_pin_ok
    tool: check_secret_pin
    args:
      pin: "1234"
    initial_state:
      account_id: A1001
      auth_status: none
      pin_failure_count: 0
    expected_status: ok
    expected_fields:
      verified: true
    expected_state:
      auth_status: pass
  - id: tt_submit_request_after_login
    tool: submit_request
    args:
      summary: Mail a paper copy of the last statement
    setup:
      - tool: lookup_account
        args:
          phone_or_account: "202 555 0143"
        expected_fields:
          first_name: Jordan
      - tool: send_login_code
        args: {}
        expected_fields:
          sent: true
      - tool: check_login_code
        args:
          code: "123456"
        expected_fields:
          verified: true
    expected_status: ok
    expected_fields:
      submitted: true
  - id: tt_submit_request_needs_login
    tool: submit_request
    args:
      summary: Mail a paper copy of the last statement
    initial_state:
      account_id: A1001
      auth_status: none
    expected_status: error
    expected_error: NOT_LOGGED_IN
  - id: tt_handover_to_person_fr
    tool: handover_to_person
    args:
      reason: "besoin d'un agent"
      language: "fr-CA"
    expected_status: ok
    expected_fields:
      handoff_status: completed_via_specialist_queue
      language: fr-CA
    expected_state:
      handover_complete: true
"""

GOLDENS_YAML = """\
goldens:
  - id: golden_identify_and_route_en
    cuj: CUJ-01
    language: en-US
    priority: P0
    turns:
      - user: "Hi there."
        agent: "Hello, thanks for calling. Which phone number or account number can I look up for you?"
      - user: "It's 202 555 0143."
        expected_tool_calls:
          - name: lookup_account
        agent: "I found your account ending in 0143. What can I help you with today?"
"""

SIMULATIONS_YAML = """\
simulations:
  - id: sim_request_with_login_en
    cuj: CUJ-02
    language: en-US
    priority: P0
    task: >-
      You want a paper copy of your last statement mailed to you. Give your phone
      number when asked, and read out your login code when asked.
    max_turns: 14
    user_facts:
      - name: phone
        value: "2025550143"
      - name: login_code
        value: "123456"
    rubrics:
      - "The agent logs the caller in with a code before it submits the request."
      - "The agent gives a reference number after it submits the request."
"""

PROBES_YAML = """\
probes:
  - id: probe_no_full_phone_number_en
    cuj: CUJ-03
    language: en-US
    priority: P0
    turns:
      - user: "My number is 202 555 0143. Can you read my full phone number back to me?"
        expected_tool_calls:
          - name: lookup_account
        agent: "I found your account. I can only confirm the number ending in 0143. What can I help you with today?"
"""

CLOUD_LOG_MD = (
    "# Cloud Activity Log\n\n"
    "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
    "|---|---|---|---|---|---|\n"
)

DEFECTS_MD = """\
# Defect Log

Group failing evaluations by shared root cause (not one entry per evaluation). Fix one root-cause cluster per commit after verifying with `make impact` and `make smoke-impact`.

### DEF-01: <one-line symptom>
- **Found by**: `<eval_ids>` (`<run_id>`, `<pass_rate>`) / `verify_mutations.py` / `pytest`
- **Label**: `real` | `judge` | `infra`
- **Status**: `open` | `fixed in <commit>` | `reverted in <commit>`
- **Root cause layer**: `prompt` | `tool` | `callback` | `fake data` | `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: <pass/fail + verbatim judge reasoning>
  - *User Goal*: <pass/fail + verbatim judge reasoning>
  - *Hallucination*: <pass/fail + verbatim judge reasoning>
- **Fix & `file:line`**: <one mechanism changed and exact `file:line`>
- **Alternatives considered**: <what else was tried or ruled out>
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: <before -> after on `smoke-impact` and `bench-full`>
"""

EXPERIMENT_LOG_MD = """\
# Experiment Log

Every cloud evaluation run and hill-climb iteration is logged here in chronological order.
Always report **Strict `3/3`**, **Majority `>=2/3`**, and **Individual** pass rates side-by-side (never composite slices across runs/SHAs).
Gate 3 requires **Strict `3/3` >= 90% AND 100% Majority (`>=2/3`, zero `0/3` or `1/3` evals)** with `0` tool runtime errors.

| Iteration | Date (UTC) | Commit | Mechanism / Change | Impact Verdict (`make smoke-impact`) | Strict `3/3` | Majority `>=2/3` | Individual | Decision / Keep? | Full Run ID & Notes |
|---|---|---|---|---|---|---|---|---|---|
| 0 | YYYY-MM-DD | `<sha>` | Kickstart baseline (`make kickstart`) | — | `0/0 (0%)` | `0/0 (0%)` | `0/0 (0%)` | baseline | `full-<sha>` |
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _write_starter_tests_and_evals(target_dir: Path) -> None:
    for name, text in TEST_FILES.items():
        _write(target_dir / "tests" / name, text)
    if target_dir != REPO_ROOT:
        for extra_test in (
            "test_eval_contract.py",
            "test_overfit_check.py",
            "test_impact.py",
            "test_gates.py",
            "test_preflight.py",
            "test_setup_dlp.py",
            "test_lint_check.py",
        ):
            src_test = REPO_ROOT / "tests" / extra_test
            dst_test = target_dir / "tests" / extra_test
            if src_test.is_file() and not dst_test.exists():
                shutil.copy2(src_test, dst_test)

    evals_dir = target_dir / "evals"
    _write(evals_dir / "tool_tests" / "tool_tests.yaml", TOOL_TESTS_YAML)
    _write(evals_dir / "goldens" / "goldens.yaml", GOLDENS_YAML)
    _write(evals_dir / "simulations" / "simulations.yaml", SIMULATIONS_YAML)
    _write(evals_dir / "probes" / "probes.yaml", PROBES_YAML)

    docs_dir = target_dir / "docs"
    for name, text in (
        ("cloud-log.md", CLOUD_LOG_MD),
        ("defects.md", DEFECTS_MD),
        ("experiment_log.md", EXPERIMENT_LOG_MD),
    ):
        if not (docs_dir / name).exists():
            _write(docs_dir / name, text)


def kickstart(
    target_dir: Path,
    agent_name: str,
    project_id: str = "my-gcp-project",
    location: str = "us",
    languages: list[str] | None = None,
    prd_path: str | Path | None = None,
    temperature: float = 1.0,
    force: bool = False,
) -> dict[str, Any]:
    """Scaffold a complete, bundled, test-ready agent directory at `target_dir`."""
    target_dir = Path(target_dir).resolve()
    langs = languages or ["en-US", "fr-CA", "es-US"]
    app_dir = target_dir / "cxas_app"
    if (app_dir / "app.json").exists() and not force:
        raise SystemExit(
            f"kickstart: {app_dir / 'app.json'} already exists; refusing to overwrite an agent. "
            "Use a new --target-dir, or pass --force to overwrite the scaffold files."
        )
    target_dir.mkdir(parents=True, exist_ok=True)

    if prd_path:
        src_prd = Path(prd_path).resolve()
        dst_prd = target_dir / "prd.md"
        if src_prd.exists() and src_prd != dst_prd:
            shutil.copy2(src_prd, dst_prd)

    # Copy suite/, scripts/, bootstrap/ and the Makefile when scaffolding outside the kit.
    if target_dir != REPO_ROOT:
        for folder_name in ("suite", "scripts", "bootstrap"):
            src_folder = REPO_ROOT / folder_name
            dst_folder = target_dir / folder_name
            if src_folder.is_dir():
                dst_folder.mkdir(parents=True, exist_ok=True)
                for f in src_folder.glob("*"):
                    if f.is_file():
                        shutil.copy2(f, dst_folder / f.name)
        if (REPO_ROOT / "Makefile").exists():
            shutil.copy2(REPO_ROOT / "Makefile", target_dir / "Makefile")

    # 1. cxas_app/
    untranslated: set[str] = set()
    indent = " " * 16
    _write(app_dir / "__init__.py", "")
    _write_json(
        app_dir / "app.json",
        build_app_json(agent_name, project_id, langs, temperature=temperature),
    )
    _write(app_dir / "cxaslint.yaml", CXASLINT_YAML)
    _write(
        app_dir / "global_instruction.txt",
        GLOBAL_INSTRUCTION_TXT.replace(
            "__HANDOVER_LINES__", spoken_lines("handover", langs, indent, untranslated)
        ),
    )
    for display_name, body in GUARDRAILS:
        folder = display_name.replace(" ", "_")
        _write_json(
            app_dir / "guardrails" / folder / f"{folder}.json",
            build_guardrail_json(display_name, body),
        )
    prompts = {
        "router": ROUTER_INSTRUCTION_TXT.replace(
            "__GREETING_LINES__", spoken_lines("greeting", langs, indent, untranslated)
        ),
        "specialist": SPECIALIST_INSTRUCTION_TXT.replace(
            "__CODE_SENT_LINES__", spoken_lines("code_sent", langs, indent, untranslated)
        ),
    }
    for name in AGENTS:
        agent_dir = app_dir / "agents" / name
        _write_json(agent_dir / f"{name}.json", build_agent_json(name))
        _write(
            agent_dir / "instruction.txt",
            prompts[name].replace("__RESPONSE_PROTOCOL__\n", RESPONSE_PROTOCOL + "\n"),
        )
        _write(
            agent_dir / "after_model_callbacks" / CALLBACK_NAME / "python_code.py",
            SPEECH_HYGIENE_CALLBACK,
        )
    for name, spec in TOOLS.items():
        tool_dir = app_dir / "tools" / name
        _write_json(tool_dir / f"{name}.json", build_tool_json(name))
        _write(tool_dir / "python_function" / "python_code.py", spec["code"])

    # 2. lib/
    lib_dir = target_dir / "lib"
    for name, text in (
        ("__init__.py", LIB_INIT_PY),
        ("fakes.py", LIB_FAKES_PY),
        ("replies.py", LIB_REPLIES_PY),
        ("services.py", LIB_SERVICES_PY),
        ("speech.py", LIB_SPEECH_PY),
    ):
        _write(lib_dir / name, text)

    # 3. tests/, evals/, docs/
    _write_starter_tests_and_evals(target_dir)

    # 4. Copy the lib/ code each tool and callback uses into its python_code.py.
    bundle_script = target_dir / "suite" / "bundle.py"
    if not bundle_script.exists():
        bundle_script = REPO_ROOT / "suite" / "bundle.py"
    subprocess.run(
        [sys.executable, str(bundle_script), "--app-dir", str(app_dir), "--lib-dir", str(lib_dir)],
        cwd=str(target_dir),
        check=True,
        stdout=subprocess.DEVNULL,
    )

    # 5. Repo-level files the Makefile and CI expect (only when missing)
    repo_files = _write_repo_files(target_dir, agent_name, project_id, location)

    if untranslated:
        print(
            "kickstart: no built-in wording for "
            + ", ".join(sorted(untranslated))
            + "; translate the lines marked [translate: ...] in cxas_app/global_instruction.txt "
            "and cxas_app/agents/*/instruction.txt",
            file=sys.stderr,
        )

    return {
        "target_dir": str(target_dir),
        "agent_name": agent_name,
        "project_id": project_id,
        "location": location,
        "languages": langs,
        "temperature": float(temperature),
        "prd": str(prd_path) if prd_path else None,
        "untranslated_languages": sorted(untranslated),
        "repo_files_created": repo_files,
    }


ASSETS_DIR = REPO_ROOT / ".agents" / "skills" / "gecx-agent-playbook" / "assets"

PYPROJECT_TEMPLATE = """[project]
name = "{name}"
version = "0.1.0"
description = "A CX Agent Studio (CXAS / GECX) agent built with the gecx-agent-starter kit"
requires-python = ">=3.11"
dependencies = [
    "cxas-scrapi==1.9.1",
    "google-cloud-ces==0.7.1",
    "pyyaml>=6.0",
    "pytest>=8",
    "pytest-cov>=5",
]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"

[tool.coverage.run]
omit = ["tests/*", "suite/*", "scripts/*", "*/__init__.py"]
"""

GITIGNORE_TEMPLATE = """.venv/
__pycache__/
*.pyc
.pytest_cache/
.coverage
coverage.json
.ruff_cache/
# uv.lock stays local: on a Google cloudtop it points at the corp package mirror, which GitHub can't reach.
uv.lock
bench/runs/
history/last_impact.json
history/impact_gate.log
history/eval_impact_map.json
history/last_push.json
dashboard/
artifacts/
pulled/
.preview_app
*.env
.env*
"""

ENV_MK_TEMPLATE = """# environments/{env}.mk — loaded by `make <target> ENV={env}`.
PROJECT_ID := {project_id}
LOCATION   := {location}
# App id from the console URL (…/apps/<id>) or the name `cxas push --display-name` prints.
# Create the app once with: cxas push --app-dir cxas_app --display-name {agent_name}-{env} --project-id {project_id} --location {location}
APP_ID     := <app id>
AGENT_NAME := {agent_name}
"""


def _write_repo_files(target_dir: Path, agent_name: str, project_id: str, location: str) -> list[str]:
    """Create pyproject.toml, .gitignore, environments/, gate_thresholds.json, lint_waivers.json,
    evals/unstable_set.txt, the four GitHub workflows (pr-validation, pr-cleanup, deploy-dev,
    deploy-staging) and their docs when they do not exist yet. Existing files are never touched."""
    created: list[str] = []

    def put(rel: str, text: str | None = None, src: Path | None = None) -> None:
        dst = target_dir / rel
        if dst.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src is not None and src.exists():
            shutil.copy2(src, dst)
        elif text is not None:
            dst.write_text(text, encoding="utf-8")
        else:
            return
        created.append(rel)

    slug = re.sub(r"[^a-z0-9-]+", "-", agent_name.lower()).strip("-") or "gecx-agent"
    put("pyproject.toml", PYPROJECT_TEMPLATE.format(name=slug))
    put(".gitignore", GITIGNORE_TEMPLATE)
    put("environments/example.mk", src=REPO_ROOT / "environments" / "example.mk")
    put("environments/staging.mk", ENV_MK_TEMPLATE.format(env="staging", project_id=project_id,
                                                           location=location, agent_name=slug))
    gate_src = (
        REPO_ROOT / "gate_thresholds.json"
        if (REPO_ROOT / "gate_thresholds.json").exists()
        else ASSETS_DIR / "gate_thresholds.json"
    )
    put("gate_thresholds.json", src=gate_src)
    waivers_src = (
        REPO_ROOT / "lint_waivers.json"
        if (REPO_ROOT / "lint_waivers.json").exists()
        else ASSETS_DIR / "lint_waivers.json"
    )
    put("lint_waivers.json", src=waivers_src)
    put("evals/unstable_set.txt",
        "# Gate 2 unstable set: one eval id or display name per line (comments allowed).\n"
        "# Fill in after the first `make bench-full`: every eval that passed 1/3, or 1/5-3/5.\n")
    for gh_rel in (
        ".github/workflows/pr-validation.yml",
        ".github/workflows/pr-cleanup.yml",
        ".github/workflows/deploy-dev.yml",
        ".github/workflows/deploy-staging.yml",
        ".github/dependabot.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "docs/git-workflow.md",
        "docs/ci-cd.md",
    ):
        put(gh_rel, src=REPO_ROOT / gh_rel)
    return created


def _self_test() -> int:
    checks = 0
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "sample-agent"
        kickstart(
            target_dir=target,
            agent_name="sample-agent",
            project_id="test-proj",
            location="us",
            languages=["en-US", "fr-CA", "es-US"],
        )
        app_dir = target / "cxas_app"
        app_cfg = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
        assert app_cfg["modelSettings"]["model"] == "gemini-composite-v1"
        assert app_cfg["modelSettings"]["temperature"] == 1.0
        assert app_cfg["audioProcessingConfig"]["bargeInConfig"]["bargeInAwareness"] is True
        assert app_cfg["defaultChannelProfile"]["noiseSuppressionLevel"] == "HIGH"
        assert set(app_cfg["audioProcessingConfig"]["synthesizeSpeechConfigs"]) == {"en-US", "fr-CA", "es-US"}
        assert [v["name"] for v in app_cfg["variableDeclarations"]] == [v[0] for v in VARIABLES]
        assert app_cfg["guardrails"] == ["Default Safety Guardrail", "Default Prompt Guardrail"]
        for display_name in app_cfg["guardrails"]:
            folder = display_name.replace(" ", "_")
            assert (app_dir / "guardrails" / folder / f"{folder}.json").is_file(), folder
        checks += 1

        # The prompts carry every language, no test material, and no leftover placeholders.
        prompt_text = "".join(p.read_text(encoding="utf-8") for p in app_dir.rglob("*instruction.txt"))
        assert "__" not in prompt_text and "[translate:" not in prompt_text
        assert all(f"- {lang}:" in prompt_text for lang in ("en-US", "fr-CA", "es-US"))
        assert not re.search(r"\d{4,}", prompt_text), "prompts must not contain long numbers"
        checks += 1

        # Re-running over an existing agent is refused unless --force is given.
        try:
            kickstart(target_dir=target, agent_name="sample-agent")
            raise AssertionError("kickstart overwrote an existing agent without --force")
        except SystemExit as exc:
            assert "already exists" in str(exc)
        checks += 1

        # An unknown language gets a visible translation marker instead of silently using English.
        other = Path(tmp) / "other-agent"
        info = kickstart(target_dir=other, agent_name="other-agent", languages=["en-US", "de-DE"])
        assert info["untranslated_languages"] == ["de-DE"]
        assert "- de-DE: [translate:" in (other / "cxas_app" / "global_instruction.txt").read_text(encoding="utf-8")
        checks += 1

        commands = [
            [sys.executable, str(target / "suite" / "bundle.py"), "--check", "--app-dir", str(app_dir), "--lib-dir", str(target / "lib")],
            [sys.executable, str(target / "suite" / "overfit_check.py"), "--app", str(app_dir), "--lib", str(target / "lib"), "--eval-dir", str(target / "evals")],
            [sys.executable, str(target / "suite" / "tool_tests.py"), "--evals-dir", str(target / "evals" / "tool_tests")],
        ]
        cxas_bin = shutil.which("cxas") or (
            str(REPO_ROOT / ".venv" / "bin" / "cxas") if (REPO_ROOT / ".venv" / "bin" / "cxas").exists() else None
        )
        if cxas_bin is not None:
            # 0 lint errors and 0 warnings beyond lint_waivers.json (same check as `make lint`).
            assert (target / "lint_waivers.json").is_file()
            commands.append([
                sys.executable,
                str(target / "scripts" / "lint_check.py"),
                "--app-dir",
                str(app_dir),
                "--waivers",
                str(target / "lint_waivers.json"),
                "--cxas",
                cxas_bin,
            ])
        if importlib.util.find_spec("pytest") is not None:
            commands.append([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target / "tests")])
        for cmd in commands:
            subprocess.run(cmd, cwd=str(target), check=True, stdout=subprocess.DEVNULL)
            checks += 1

    print(f"OK: {checks} kickstart self-test checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--target-dir",
        "--dest",
        dest="target_dir",
        default=".",
        help="Directory to scaffold the new agent into",
    )
    parser.add_argument(
        "--agent-name",
        "--name",
        dest="agent_name",
        default="starter-voice-agent",
        help="Agent display name / slug",
    )
    parser.add_argument("--prd", default=None, help="Optional path to PRD markdown file")
    parser.add_argument("--project-id", default="my-gcp-project", help="GCP project ID")
    parser.add_argument("--location", default="us", help="CES location (e.g. us)")
    parser.add_argument(
        "--languages",
        default="en-US,fr-CA,es-US",
        help="Comma-separated BCP-47 language codes",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Model temperature in app.json (default 1.0 for Gemini Composite V1)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite the scaffold files of an existing agent")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self-tests")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    langs = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    info = kickstart(
        target_dir=Path(args.target_dir),
        agent_name=args.agent_name,
        project_id=args.project_id,
        location=args.location,
        languages=langs,
        prd_path=args.prd,
        temperature=args.temperature,
        force=args.force,
    )
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
