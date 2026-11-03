#!/usr/bin/env python3
"""Deterministic transcript checks. A FAIL here overrides an LLM-judge PASS.

Input: a transcript JSON file:
{
  "id": "conv-123",                      # optional
  "modality": "text" | "audio",          # audio enables voice checks
  "language": "en",                      # expected reply language (optional)
  "internal_names": ["billing_agent"],   # optional extra names that must not be said
  "max_reply_chars": 600,                # optional; default 400 for audio, off for text
  "fact_patterns": ["\\b\\d{1,2}:\\d{2}\\b"],  # optional; overrides the default fact regexes
  "turns": [
    {"role": "user", "text": "..."},
    {"role": "agent", "text": "...",
     "tool_calls": [{"name": "lookup_order", "args": {...}, "result": {...}}]}
  ]
}

Usage:
  python suite/grader.py --transcript t.json        # prints JSON, exit 1 on FAIL
  python suite/grader.py --self-test                # prints OK

Standard library plus optional repo `lib/copy.py` when present, so it runs in CI,
pre-commit, starter kit self-tests, or a coding agent from any working directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from lib import copy as copy_lib  # type: ignore
except ImportError:
    copy_lib = None

CODE_LEAK = re.compile(
    r"default_api\.|```|\btransfer_to_agent\b|\bend_session\s*\(|"
    r"\b[a-z]+(?:_[a-z0-9]+)+\s*\(\s*[a-z_]+\s*=",
)
PLATFORM_FALLBACK = re.compile(
    r"I'?m having (?:some )?trouble (?:with that|understanding)|"
    r"Do you want me to try again\?|something went wrong on my end",
    re.IGNORECASE,
)
FILLER = re.compile(
    r"^\W*(?:ok(?:ay)?[,.]?\s*)?(?:let me (?:check|look|see|find|get|pull)|"
    r"one moment|just a (?:moment|second|sec)|hold on|please hold|"
    r"i'?ll (?:check|look|transfer|connect)|i'?m (?:checking|looking|transferring|connecting)|"
    r"transferring you|connecting you)\b[^.?!]*[.?!…]*\s*$",
    re.IGNORECASE,
)
EXEMPT_HANDOFF_PHRASES = (
    "i'll connect you to a representative who can help. please hold.",
    "to get you the best support for your business account, i'll transfer you to an agent.",
    "i'll connect you to a billing specialist now — they'll have everything we've already discussed.",
    "je vous mets immédiatement en relation avec un conseiller",
    "je vous mets en relation avec un conseiller",
    "je vous mets en ligne avec un conseiller spécialisé",
    "enseguida lo pongo en línea con un representante",
    "lo comunico con un representante para asistirle",
    "ahora mismo lo comunico con un asesor especializado",
)

INTERNAL_NAME = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)*_(?:agent|tool)\b")
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
MARKDOWN = re.compile(
    r"\*\*|__|^\s*#{1,6}\s|^\s*[-*]\s+\S|\[[^\]]+\]\([^)]+\)", re.MULTILINE
)
EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf]")
GOODBYE = re.compile(
    r"\b(?:bye|goodbye|thanks|thank you|that'?s all|no,? that'?s it|"
    r"adi[oó]s|gracias|tsch[uü]ss|danke|merci|au revoir|grazie|obrigad[oa])\b",
    re.IGNORECASE,
)
UNMASKED_PII_DIGITS = re.compile(r"(?<!\*)\b\d{7,19}\b|\b(?:\d{4}[-\s]){2,3}\d{4}\b")
CREDENTIAL_ECHO_PHRASE = re.compile(
    r"\b(?:your\s+(?:pin|code|otp|passcode)\s+is|code\s+you\s+entered\s+is|"
    r"pin\s+you\s+entered\s+is)\s*[:=-]?\s*\b(\d{4}|\d{6})\b",
    re.IGNORECASE,
)
ALTERED_RECORDING_NOTICE = re.compile(
    r"this call (?:might|could|will) be recorded for quality",
    re.IGNORECASE,
)
VERBATIM_SNIPPETS = {
    "recording_notice": "This call may be recorded for quality and training purposes.",
    "greeting_main": (
        "Welcome to Telco. I can help with billing, technical support, or managing your account. "
        "To get started, could you tell me the phone number or account number associated with your service?"
    ),
    "id_verification_otp": (
        "I just sent a 6-digit code to your mobile on file — please read it back to me out loud. "
        "You can also say your 4-digit account PIN instead."
    ),
    "id_verification_pin": (
        "For your security, I'll need to verify your identity. "
        "Please say your 4-digit account PIN out loud, or say 'text me a code' and I'll send a 6-digit code to your mobile on file."
    ),
    "live_agent_handoff": "I'll connect you to a representative who can help. Please hold.",
    "business_handoff": (
        "To get you the best support for your business account, I'll transfer you to an agent. "
        "You'll need to use your phone keypad instead of talking to the virtual assistant. "
        "Just a moment while I connect you."
    ),
    "empathy_protocol": (
        "I'm very sorry to hear that you are facing challenges. "
        "I will ensure we handle your request with the utmost care."
    ),
    "outage_active": (
        "I see there's an active outage in your area. We're working on it. "
        "Would you like me to text you when it's restored?"
    ),
    "transfer_to_specialist": (
        "I'll connect you to a billing specialist now — they'll have everything we've already discussed."
    ),
}

DEFAULT_FACT_PATTERNS = [
    r"\b\d{1,2}:\d{2}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    r"[$€£¥]\s?\d|\b\d+(?:[.,]\d+)?\s?(?:usd|eur|gbp|dollars|euros)\b",
    r"\b(?:order|ticket|booking|case|confirmation)\s*(?:number|no\.?|#|id)?\s*[A-Z0-9-]{5,}\b",
]
STOPWORDS = {
    "en": {
        "the",
        "and",
        "is",
        "you",
        "your",
        "to",
        "of",
        "it",
        "for",
        "with",
        "that",
        "are",
        "this",
        "can",
    },
    "es": {
        "el",
        "la",
        "los",
        "las",
        "y",
        "es",
        "de",
        "que",
        "para",
        "con",
        "tu",
        "su",
        "por",
        "una",
        "está",
    },
    "de": {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "sie",
        "ich",
        "nicht",
        "mit",
        "für",
        "ein",
        "eine",
        "zu",
        "auf",
    },
    "fr": {
        "le",
        "la",
        "les",
        "et",
        "est",
        "vous",
        "de",
        "que",
        "pour",
        "avec",
        "une",
        "des",
        "pas",
        "sur",
    },
    "it": {
        "il",
        "lo",
        "la",
        "gli",
        "e",
        "è",
        "di",
        "che",
        "per",
        "con",
        "una",
        "sono",
        "non",
        "del",
    },
    "pt": {
        "o",
        "os",
        "as",
        "e",
        "é",
        "de",
        "que",
        "para",
        "com",
        "uma",
        "não",
        "você",
        "seu",
        "do",
    },
}


def detect_language(text):
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœäöß]+", text.lower())
    if len(words) < 6:
        return None
    scores = {lang: sum(w in sw for w in words) for lang, sw in STOPWORDS.items()}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] < 3 or ranked[0] < 2 * ranked[1]:
        return None
    return best


def _is_exempt_handoff(text: str) -> bool:
    norm = " ".join((text or "").lower().split())
    return any(phrase in norm for phrase in EXEMPT_HANDOFF_PHRASES)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _get_english_copy(key: str) -> str:
    if copy_lib is not None and hasattr(copy_lib, "get_copy"):
        try:
            return str(copy_lib.get_copy(key, "en"))
        except Exception:
            pass
    return VERBATIM_SNIPPETS.get(key, "")


def is_english_opening(text: str) -> bool:
    """True if `text` contains the English `recording_notice` and `greeting_main` lines."""
    norm = " ".join((text or "").lower().split())
    lines = [_get_english_copy(key) for key in ("recording_notice", "greeting_main")]
    wanted = [" ".join(line.lower().split()) for line in lines if line]
    return bool(norm) and bool(wanted) and all(w in norm for w in wanted)


def grade(transcript):
    turns = transcript.get("turns", [])
    audio = transcript.get("modality") == "audio"
    language = transcript.get("language")
    names = [n.lower() for n in transcript.get("internal_names", [])]
    max_chars = transcript.get("max_reply_chars", 400 if audio else None)
    max_agent_turns = transcript.get("max_agent_turns", 20)
    forbid_urls = bool(
        transcript.get("forbid_urls", False) or transcript.get("telco_p0", False)
    )
    expected_copy_keys = transcript.get("expected_copy_keys") or []
    fact_res = [
        re.compile(p, re.IGNORECASE)
        for p in transcript.get("fact_patterns", DEFAULT_FACT_PATTERNS)
    ]

    findings = []

    def add(check, i, evidence):
        findings.append({"check": check, "turn": i, "evidence": evidence[:200]})

    tool_called = False
    outage_checked = False
    authenticated_once = False
    mfa_step_up_context = False
    known_credentials = set()
    agent_turn_count = 0
    all_agent_texts = []

    for turn in turns:
        if turn.get("role") == "user":
            utext = turn.get("text") or ""
            if re.search(r"\b(?:mfa|two[- ]factor|2fa)\b", utext, re.IGNORECASE):
                mfa_step_up_context = True

    for i, turn in enumerate(turns):
        if turn.get("role") != "agent":
            continue
        agent_turn_count += 1
        text = turn.get("text") or ""
        all_agent_texts.append((i, text))
        calls = turn.get("tool_calls") or []
        call_names = [c.get("name", "") for c in calls]
        tool_called = tool_called or any(
            n not in ("transfer_to_agent", "end_session") for n in call_names
        )

        for c in calls:
            cname = c.get("name", "")
            cargs = c.get("args") if isinstance(c.get("args"), dict) else None
            cres = c.get("result") if isinstance(c.get("result"), dict) else {}

            if (
                cname in ("validate_authentication_otp", "validate_authentication_pin")
                and cargs
            ):
                for k in ("code", "pin"):
                    if cargs.get(k):
                        known_credentials.add(str(cargs[k]).strip())

            if cname == "check_regional_outage":
                outage_checked = True
            elif (
                cname in ("start_virtual_repair", "create_support_ticket")
                and not outage_checked
            ):
                add(
                    "outage_check_first",
                    i,
                    f"{cname} called before check_regional_outage",
                )

            if cname == "manage_mfa":
                mfa_step_up_context = True

            if cname in (
                "send_authentication_otp",
                "validate_authentication_otp",
                "validate_authentication_pin",
            ):
                if authenticated_once and not mfa_step_up_context:
                    add(
                        "no_second_login",
                        i,
                        f"{cname} called after caller was already authenticated",
                    )

            if cname in ("validate_authentication_otp", "validate_authentication_pin"):
                data = cres.get("data") if isinstance(cres.get("data"), dict) else cres
                if data.get("auth_status") == "Pass" or (cargs and not cres):
                    if data.get("auth_status", "Pass") == "Pass":
                        authenticated_once = True

            if (
                cname == "execute_live_agent_handover"
                and cargs is not None
                and "session_context" in cargs
            ):
                ctx = cargs.get("session_context")
                if not isinstance(ctx, dict) or not ctx:
                    add(
                        "session_context_on_handover",
                        i,
                        "execute_live_agent_handover called with empty session_context",
                    )

            if cname == "set_call_language" and cargs and cargs.get("language"):
                language = str(cargs["language"]).strip().lower()[:2]

        m = CODE_LEAK.search(text)
        if m:
            add("code_leak", i, text[max(0, m.start() - 40) : m.end() + 60])

        if not tool_called:
            for fr in fact_res:
                m = fr.search(text)
                if m:
                    add(
                        "fact_before_tool",
                        i,
                        f"'{m.group(0)}' stated before any tool call",
                    )
                    break

        next_role = turns[i + 1].get("role") if i + 1 < len(turns) else None
        if next_role != "agent":
            if (FILLER.match(text) and not _is_exempt_handoff(text)) or (
                not text.strip() and "transfer_to_agent" in call_names
            ):
                add("dead_air_handoff", i, text or "<empty reply after transfer>")

        turn_mismatch_added = False
        opening_turn = agent_turn_count == 1 and is_english_opening(text)
        effective_lang = "en" if opening_turn else language
        if effective_lang:
            got = detect_language(text)
            if got and got != effective_lang:
                add(
                    "language_mismatch",
                    i,
                    f"expected {effective_lang}, reply looks {got}: {text[:80]}",
                )
                turn_mismatch_added = True

        sentences = _split_sentences(text)
        if len(sentences) >= 2:
            detected_langs = [detect_language(s) for s in sentences]
            confident_langs = [l for l in detected_langs if l]
            if len(set(confident_langs)) > 1:
                add(
                    "language_lock_per_sentence",
                    i,
                    f"mixed languages in one turn: {confident_langs}",
                )
            elif (
                effective_lang
                and confident_langs
                and any(l != effective_lang for l in confident_langs)
                and not turn_mismatch_added
            ):
                add(
                    "language_lock_per_sentence",
                    i,
                    f"sentence language {confident_langs} != {effective_lang}",
                )

        lowered = text.lower()
        leaked = [n for n in names if n in lowered] + INTERNAL_NAME.findall(lowered)
        if leaked:
            add("internal_names", i, ", ".join(sorted(set(leaked))))

        if audio:
            for label, rx in (("url", URL), ("markdown", MARKDOWN), ("emoji", EMOJI)):
                m = rx.search(text)
                if m:
                    add(
                        "tts_unfriendly",
                        i,
                        f"{label}: {text[max(0, m.start() - 20) : m.end() + 20]}",
                    )
        else:
            em = EMOJI.search(text)
            if em:
                add("no_urls_or_emojis", i, f"emoji: {em.group(0)}")
            elif (
                forbid_urls or "send_password_reset_sms" in call_names
            ) and URL.search(text):
                add(
                    "no_urls_or_emojis", i, f"url in reply: {URL.search(text).group(0)}"
                )

        pii_match = UNMASKED_PII_DIGITS.search(text)
        if pii_match:
            add("last4_only_pii", i, f"unmasked digits: {pii_match.group(0)}")

        cred_match = CREDENTIAL_ECHO_PHRASE.search(text)
        if cred_match:
            add("no_credential_echo", i, cred_match.group(0))
        else:
            for secret in sorted(known_credentials):
                if secret and re.search(rf"(?<!\*)\b{re.escape(secret)}\b", text):
                    add("no_credential_echo", i, f"echoed credential '{secret}'")
                    break

        if ALTERED_RECORDING_NOTICE.search(text):
            add("verbatim_copy_match", i, "altered recording_notice wording")

        if any(
            n in ("fetch_plan_catalog", "fetch_availability_slots") for n in call_names
        ):
            numbered_items = re.findall(r"(?:^|\s)[1-9][.)]\s+\S", text)
            price_mentions = re.findall(r"\$\d+(?:\.\d{2})?", text)
            if len(numbered_items) > 3 or len(price_mentions) > 3:
                add(
                    "max_3_options",
                    i,
                    f"more than 3 options offered in one turn ({max(len(numbered_items), len(price_mentions))})",
                )

        if max_chars and len(text) > max_chars:
            add("reply_too_long", i, f"{len(text)} chars > {max_chars}")

        if PLATFORM_FALLBACK.search(text):
            add("platform_fallback", i, text)

        if "end_session" in call_names:
            prev_user = next(
                (
                    t.get("text") or ""
                    for t in reversed(turns[:i])
                    if t.get("role") == "user"
                ),
                "",
            )
            if not text.strip() and not GOODBYE.search(prev_user):
                add(
                    "session_end_without_answer",
                    i,
                    f"ended after user said: {prev_user[:80]}",
                )

    if expected_copy_keys:
        combined_text = " ".join(t for _, t in all_agent_texts)
        for key in expected_copy_keys:
            expected_str = _get_english_copy(key) or VERBATIM_SNIPPETS.get(key, key)
            if expected_str not in combined_text:
                add("verbatim_copy_match", 0, f"missing verbatim copy for '{key}'")

    if max_agent_turns and agent_turn_count > max_agent_turns:
        add(
            "journey_turn_cap",
            len(turns) - 1,
            f"{agent_turn_count} agent turns > cap {max_agent_turns}",
        )

    return {
        "id": transcript.get("id"),
        "verdict": "fail" if findings else "pass",
        "findings": findings,
    }


def _t(*turns, **kw):
    out = {"turns": []}
    out.update(kw)
    for role, text, *calls in turns:
        turn = {"role": role, "text": text}
        if calls:
            raw_calls = calls[0]
            turn["tool_calls"] = [
                c if isinstance(c, dict) else {"name": c} for c in raw_calls
            ]
        out["turns"].append(turn)
    return out


def self_test():
    cases = [
        (
            "clean",
            _t(
                ("user", "Where is my order?"),
                ("agent", "It arrives on March 3.", ["lookup_order"]),
            ),
            set(),
        ),
        (
            "code_leak",
            _t(("user", "hi"), ("agent", "default_api.lookup_order(order_id='1')")),
            {"code_leak"},
        ),
        (
            "code_leak_kwarg",
            _t(("user", "hi"), ("agent", 'get_schedule(category="all")')),
            {"code_leak"},
        ),
        (
            "fact_before_tool",
            _t(("user", "When?"), ("agent", "Your delivery is on March 3.")),
            {"fact_before_tool"},
        ),
        (
            "fact_after_tool_ok",
            _t(
                ("user", "When?"),
                ("agent", "", ["lookup_order"]),
                ("agent", "On March 3."),
            ),
            set(),
        ),
        (
            "dead_air",
            _t(
                ("user", "Refund?"),
                ("agent", "Let me check that for you."),
                ("user", "hello?"),
            ),
            {"dead_air_handoff"},
        ),
        (
            "dead_air_end",
            _t(("user", "Refund?"), ("agent", "One moment please...")),
            {"dead_air_handoff"},
        ),
        (
            "empty_transfer",
            _t(("user", "Billing"), ("agent", "", ["transfer_to_agent"])),
            {"dead_air_handoff"},
        ),
        (
            "filler_then_answer_ok",
            _t(
                ("user", "Refund?"),
                ("agent", "Let me check."),
                ("agent", "Your refund was issued.", ["get_refund"]),
            ),
            set(),
        ),
        (
            "prd_handoff_exempt_ok",
            _t(
                ("user", "Representative"),
                (
                    "agent",
                    VERBATIM_SNIPPETS["live_agent_handoff"],
                    ["execute_live_agent_handover"],
                ),
            ),
            set(),
        ),
        (
            "language",
            _t(
                ("user", "Hola"),
                (
                    "agent",
                    "Sure, the store is open and you can visit it with your family today.",
                ),
            ),
            set(),
        ),
        (
            "language_mismatch",
            {
                **_t(
                    ("user", "Hola"),
                    (
                        "agent",
                        "Sure, the store is open and you can visit it with your family today.",
                    ),
                ),
                "language": "es",
            },
            {"language_mismatch"},
        ),
        (
            "language_ok",
            {
                **_t(
                    ("user", "Hola"),
                    (
                        "agent",
                        "Claro, la tienda está abierta y puedes visitarla con tu familia para comprar.",
                    ),
                ),
                "language": "es",
            },
            set(),
        ),
        (
            "language_lock_sentence",
            _t(
                ("user", "Bonjour"),
                (
                    "agent",
                    "Bonjour, le magasin est ouvert et vous pouvez venir avec une facture. Sure, the store is open and you can visit it with your family today.",
                ),
            ),
            {"language_lock_per_sentence"},
        ),
        (
            "internal_names",
            _t(
                ("user", "hi"),
                ("agent", "I'll hand you to the billing_agent now, it knows."),
            ),
            {"internal_names"},
        ),
        (
            "tts",
            {
                **_t(("user", "link?"), ("agent", "Go to **https://example.com** 🙂")),
                "modality": "audio",
            },
            {"tts_unfriendly"},
        ),
        (
            "tts_text_ok",
            _t(("user", "link?"), ("agent", "Go to https://example.com")),
            set(),
        ),
        (
            "no_urls_or_emojis_check",
            _t(
                ("user", "reset"),
                (
                    "agent",
                    "Sent link https://telco.example/reset",
                    ["send_password_reset_sms"],
                ),
            ),
            {"no_urls_or_emojis"},
        ),
        (
            "last4_only_pii_check",
            _t(
                ("user", "acct?"),
                (
                    "agent",
                    "Your account number is 100000101.",
                    ["fetch_customer_profile"],
                ),
            ),
            {"last4_only_pii"},
        ),
        (
            "no_credential_echo_check",
            _t(
                ("user", "4829"),
                (
                    "agent",
                    "Thanks, your PIN is 4829.",
                    [{"name": "validate_authentication_pin", "args": {"pin": "4829"}}],
                ),
            ),
            {"no_credential_echo"},
        ),
        (
            "verbatim_copy_match_check",
            _t(("user", "hi"), ("agent", "This call might be recorded for quality.")),
            {"verbatim_copy_match"},
        ),
        (
            "outage_check_first_check",
            _t(
                ("user", "internet down"),
                ("agent", "Running repair.", ["start_virtual_repair"]),
            ),
            {"outage_check_first"},
        ),
        (
            "max_3_options_check",
            _t(
                ("user", "plans?"),
                (
                    "agent",
                    "1. Plan A 2. Plan B 3. Plan C 4. Plan D",
                    ["fetch_plan_catalog"],
                ),
            ),
            {"max_3_options"},
        ),
        (
            "journey_turn_cap_check",
            {
                **_t(
                    ("user", "1"),
                    ("agent", "a"),
                    ("user", "2"),
                    ("agent", "b"),
                    ("user", "3"),
                    ("agent", "c"),
                ),
                "max_agent_turns": 2,
            },
            {"journey_turn_cap"},
        ),
        (
            "no_second_login_check",
            _t(
                ("user", "482913"),
                (
                    "agent",
                    "Verified.",
                    [
                        {
                            "name": "validate_authentication_otp",
                            "result": {"data": {"auth_status": "Pass"}},
                        }
                    ],
                ),
                ("user", "pay bill"),
                ("agent", "Code sent.", ["send_authentication_otp"]),
            ),
            {"no_second_login"},
        ),
        (
            "session_context_handover_check",
            _t(
                ("user", "person"),
                (
                    "agent",
                    VERBATIM_SNIPPETS["live_agent_handoff"],
                    [
                        {
                            "name": "execute_live_agent_handover",
                            "args": {
                                "reason": "user_requested_agent",
                                "session_context": {},
                            },
                        }
                    ],
                ),
            ),
            {"session_context_on_handover"},
        ),
        (
            "too_long",
            {**_t(("user", "tell me"), ("agent", "word " * 100)), "modality": "audio"},
            {"reply_too_long"},
        ),
        (
            "fallback",
            _t(("user", "hi"), ("agent", "Hmm, I'm having trouble with that.")),
            {"platform_fallback"},
        ),
        (
            "fallback_retry_offer",
            _t(("user", "hi"), ("agent", "Do you want me to try again?")),
            {"platform_fallback"},
        ),
        (
            "end_no_answer",
            _t(("user", "What is my balance?"), ("agent", "", ["end_session"])),
            {"session_end_without_answer"},
        ),
        (
            "end_after_bye_ok",
            _t(("user", "Thanks, bye"), ("agent", "", ["end_session"])),
            set(),
        ),
    ]
    failures = []
    for name, transcript, want in cases:
        got = {f["check"] for f in grade(transcript)["findings"]}
        if got != want:
            failures.append(f"{name}: want {sorted(want)}, got {sorted(got)}")
    if failures:
        print("FAIL\n" + "\n".join(failures))
        return 1
    print(f"OK ({len(cases)} cases)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--transcript", help="transcript JSON file")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not a.transcript:
        p.error("--transcript or --self-test is required")
    with open(a.transcript, encoding="utf-8") as f:
        result = grade(json.load(f))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
