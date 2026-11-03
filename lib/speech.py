"""Speech hygiene for spoken replies: markdown stripping and number masking."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.copy import SPOKEN_LINES, resolve_copy_locale, resolve_locale, spoken_line

SPEAKABLE_NUMBERS: frozenset[str] = frozenset()

NUMBER_RUN_RE = re.compile(r"\(?\d+\)?(?:[-.]\(?\d+\)?|\s\(?\d{3,}\)?)*")
MARKDOWN_RE = re.compile(
    r"```[a-zA-Z0-9_-]*[ \t]*\n?|\*+|`+|^#+[ \t]*|^[ \t]*[-•][ \t]+",
    re.MULTILINE,
)
_SP_EVENT_TAG = re.compile(
    r"<event\b[^>]*>[\s\S]*?</event>|<event\b[^>]*/>",
    re.IGNORECASE,
)
_LAST4_CONTEXT_RE = re.compile(
    r"((?:ending\s+in|terminant\s+par|terminad?[oa]?\s+en|number\s+is|num[eé]ro\s+est|n[uú]mero\s+es)\s+)(\d{4})\b",
    re.IGNORECASE,
)

_FALLBACK_LEAKAGE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"I apologize,?\s+could you please rephrase your request or share your account details so I can assist you\??",
            re.IGNORECASE,
        ),
        "guardrail_rephrase",
    ),
    (
        re.compile(
            r"I'm sorry\s*—?\s*(?:the )?keypad entry didn't come through(?: on my end)?\.?\s*(?:Please say the number out loud,?\s*one digit at a time\.?)?",
            re.IGNORECASE,
        ),
        "keypad_recovery",
    ),
    (
        re.compile(
            r"I didn't hear anything\.?\s*(?:Could you please repeat that\??)?",
            re.IGNORECASE,
        ),
        "no_input_reprompt",
    ),
    (
        re.compile(
            r"(?:I'm sorry,?\s*)?(?:I didn't (?:quite )?catch that\.?\s*)?(?:Could you )?please rephrase (?:your request|that)\??",
            re.IGNORECASE,
        ),
        "no_match_reprompt",
    ),
    (
        re.compile(
            r"I apologize,?\s+our system is currently having trouble processing that request\.?\s*(?:Let me connect you with a representative who can assist\.?)?",
            re.IGNORECASE,
        ),
        "tool_error_apology",
    ),
)

_SP_CARD_KWS: tuple[str, ...] = (
    "card",
    "carte",
    "tarjeta",
    "visa",
    "mastercard",
    "amex",
    "crédit",
    "credit",
)

_SP_EXPLICIT_BANK_KWS: tuple[str, ...] = (
    "bank",
    "banking",
    "bancaire",
    "bancaria",
    "banco",
    "checking",
    "chequing",
    "chèques",
    "chèque",
    "cheques",
    "savings",
    "épargne",
    "ahorros",
    "corriente",
    "routing",
    "transit",
    "pad",
    "dpa",
    "pre-authorized",
    "preauthorized",
    "préautorisé",
    "preautorise",
    "prélèvement",
    "prelevement",
    "preautorizado",
    "domiciliación",
    "domiciliacion",
)

_SP_BANK_KWS: tuple[str, ...] = (
    "bank",
    "banking",
    "bancaire",
    "bancaria",
    "banco",
    "checking",
    "chequing",
    "chèques",
    "chèque",
    "cheques",
    "savings",
    "épargne",
    "ahorros",
    "corriente",
    "routing",
    "transit",
    "pad",
    "dpa",
    "pre-authorized",
    "preauthorized",
    "préautorisé",
    "preautorise",
    "prélèvement",
    "prelevement",
    "preautorizado",
    "domiciliación",
    "domiciliacion",
    "automático",
    "automatico",
    "débit",
    "debit",
    "débito",
    "debito",
)

_SP_PHONE_KWS: tuple[str, ...] = (
    "phone",
    "mobile",
    "cell",
    "téléphone",
    "cellulaire",
    "teléfono",
    "celular",
    "móvil",
)

_SP_HOLD_TAILS: tuple[str, ...] = (
    "please hold",
    "veuillez patienter",
    "por favor espere",
)

_SP_BIZ_TERMS: frozenset[str] = frozenset(
    {"business", "entreprise", "affaires", "commercial", "comercial"}
)
_SP_FRAUD_TERMS: frozenset[str] = frozenset(
    {
        "fraud",
        "fraude",
        "unauthorized",
        "security",
        "compromis",
        "compromise",
        "sim_swap",
        "abuse",
    }
)
_SP_SPECIALIST_TERMS: frozenset[str] = frozenset(
    {
        "refund",
        "remboursement",
        "reembolso",
        "threshold",
        "specialist",
        "billing_specialist",
    }
)


def _sp_term_pos(segment: str, terms: tuple[str, ...]) -> int:
    """Return last word-start match offset of any term in segment, or -1."""
    best = -1
    for term in terms:
        pat = (
            rf"(?<!\w){re.escape(term)}(?!\w)"
            if len(term) <= 3
            else rf"(?<!\w){re.escape(term)}"
        )
        for match in re.finditer(pat, segment):
            if match.start() > best:
                best = match.start()
    return best


def mask_long_numbers(text: str, min_digits: int = 9) -> str:
    """Replace every number of min_digits or more digits by its last 4 digits."""

    def _mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < min_digits or digits in SPEAKABLE_NUMBERS:
            return match.group(0)
        return digits[-4:]

    return NUMBER_RUN_RE.sub(_mask, text)


def strip_markdown(text: str) -> str:
    """Drop markdown formatting characters and event tags from spoken text."""
    return MARKDOWN_RE.sub("", _SP_EVENT_TAG.sub("", text))


def clean_speech(text: str) -> str:
    """Clean markdown formatting and long numbers from spoken text."""
    return mask_long_numbers(strip_markdown(text))


def clean_agent_speech(
    text: str,
    session_params: Any = None,
) -> str:
    """Clean speech and preserve caller phone, card, bank, and account last-4 numbers."""
    cleaned = clean_speech(text)
    if not callable(getattr(session_params, "get", None)):
        return cleaned
    caller_last4 = str(session_params.get("caller_provided_phone_last4") or "").strip()
    profile_last4 = str(session_params.get("phone_last4") or "").strip()
    card_last4 = str(session_params.get("card_last4") or "").strip()
    bank_last4 = str(session_params.get("bank_last4") or "").strip()
    declined_last4 = str(session_params.get("declined_card_last4") or "").strip()
    acc_digits = re.sub(r"\D", "", str(session_params.get("account_id") or ""))
    account_last4 = acc_digits[-4:] if len(acc_digits) >= 4 else ""

    valid_caller = len(caller_last4) == 4 and caller_last4.isdigit()
    valid_profile = len(profile_last4) == 4 and profile_last4.isdigit()
    valid_card = len(card_last4) == 4 and card_last4.isdigit()
    valid_bank = len(bank_last4) == 4 and bank_last4.isdigit()
    valid_declined = len(declined_last4) == 4 and declined_last4.isdigit()
    effective_phone_last4 = (
        caller_last4 if valid_caller else (profile_last4 if valid_profile else "")
    )

    if valid_caller:
        if (
            valid_profile
            and profile_last4 != caller_last4
            and profile_last4 != card_last4
            and profile_last4 != bank_last4
            and profile_last4 != declined_last4
            and profile_last4 != account_last4
            and profile_last4 in cleaned
        ):
            cleaned = re.sub(
                rf"(?<![-$/.\d])\b{re.escape(profile_last4)}\b(?![-/\d]|\.\d)",
                caller_last4,
                cleaned,
            )

    if effective_phone_last4 or valid_card or valid_bank or valid_declined:

        def _replace_non_card_last4(m: re.Match[str]) -> str:
            raw_prefix = cleaned[max(0, m.start() - 35) : m.start()].lower()
            prev_end = max(
                (pm.end() for pm in _LAST4_CONTEXT_RE.finditer(raw_prefix)),
                default=0,
            )
            prefix = raw_prefix[prev_end:]
            cue = m.group(1).lower()
            digits4 = m.group(2)

            card_pos = _sp_term_pos(prefix, _SP_CARD_KWS)
            bank_pos = _sp_term_pos(prefix, _SP_BANK_KWS)
            if (
                card_pos >= 0
                and bank_pos >= 0
                and _sp_term_pos(prefix, _SP_EXPLICIT_BANK_KWS) < 0
            ):
                bank_pos = -1
            phone_pos = _sp_term_pos(prefix, _SP_PHONE_KWS)
            is_number_is_cue = any(
                c in cue
                for c in (
                    "number is",
                    "numéro est",
                    "numero est",
                    "número es",
                    "numero es",
                )
            )
            explicit_phone_only = (
                is_number_is_cue and card_pos < 0 and bank_pos < 0
            ) or (phone_pos >= 0 and phone_pos > max(card_pos, bank_pos))

            if not explicit_phone_only:
                if card_pos >= 0 and valid_declined and digits4 == declined_last4:
                    return m.group(0)
                if (valid_card and digits4 == card_last4) or (
                    valid_bank and digits4 == bank_last4
                ):
                    return m.group(0)
                if card_pos < 0 and bank_pos < 0:
                    if effective_phone_last4 and digits4 == effective_phone_last4:
                        return m.group(0)
                    if account_last4 and digits4 == account_last4:
                        return m.group(0)

            if phone_pos >= 0 and phone_pos > max(card_pos, bank_pos):
                return (
                    f"{m.group(1)}{effective_phone_last4}"
                    if effective_phone_last4
                    else m.group(0)
                )
            if card_pos >= 0 and card_pos > bank_pos:
                return f"{m.group(1)}{card_last4}" if valid_card else m.group(0)
            if bank_pos >= 0 and bank_pos > card_pos:
                return f"{m.group(1)}{bank_last4}" if valid_bank else m.group(0)
            if effective_phone_last4:
                return f"{m.group(1)}{effective_phone_last4}"
            return m.group(0)

        cleaned = _LAST4_CONTEXT_RE.sub(_replace_non_card_last4, cleaned)

    session_lang = ""
    if callable(getattr(session_params, "get", None)):
        session_lang = (
            str(session_params.get("language") or "").strip()
            or str(session_params.get("fx_language") or "").strip()
            or str(session_params.get("preferred_language") or "").strip()
        )
    loc = resolve_copy_locale(session_lang)
    if loc in ("fr-CA", "es-US"):
        for pattern, key in _FALLBACK_LEAKAGE_REPLACEMENTS:
            if pattern.search(cleaned):
                replacement = spoken_line(key, loc)
                cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _norm_ws(s: str) -> str:
    return " ".join(s.lower().split())


def enforce_handover_utterance(
    text: str,
    session_params: Any = None,
    called_tools: tuple[str, ...] | list[str] = (),
    tool_args_list: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
) -> str:
    """Ensure a handover turn produces a valid localized transfer line."""
    params = session_params if callable(getattr(session_params, "get", None)) else {}
    has_handover_call = any(
        name in ("handover_to_person", "execute_live_agent_handover")
        for name in called_tools
    )
    existing = (text or "").strip()

    if not has_handover_call:
        if existing:
            return text
        if params.get("handover_complete") and params.get("handoff_message"):
            handoff_msg = str(params.get("handoff_message") or "").strip()
            if handoff_msg:
                return handoff_msg
        return text

    reason = ""
    target_queue = ""
    lang = (
        params.get("language")
        or params.get("fx_language")
        or params.get("preferred_language")
    )
    is_business = bool(params.get("business_flag"))
    for args in tool_args_list:
        if callable(getattr(args, "get", None)):
            if args.get("reason"):
                reason = str(args.get("reason")).lower()
            if args.get("target_queue"):
                target_queue = str(args.get("target_queue")).lower()
            if args.get("language"):
                lang = args.get("language")
            if args.get("is_business"):
                is_business = True

    full_loc = resolve_locale(lang)
    loc = resolve_copy_locale(lang)

    is_biz = (
        is_business
        or target_queue == "business_solutions"
        or any(term in reason for term in _SP_BIZ_TERMS)
    )
    is_fraud = target_queue == "fraud_and_security_24x7" or any(
        term in reason for term in _SP_FRAUD_TERMS
    )
    is_specialist = target_queue == "billing_specialist" or any(
        term in reason for term in _SP_SPECIALIST_TERMS
    )

    if is_biz:
        required_lines = [spoken_line("business_handoff", loc)]
    elif is_fraud:
        required_lines = [
            spoken_line("empathy_protocol", loc),
            spoken_line("live_agent_handoff", loc),
        ]
    elif is_specialist:
        required_lines = [spoken_line("transfer_to_specialist", loc)]
    else:
        required_lines = [spoken_line("live_agent_handoff", loc)]

    if not existing:
        return " ".join(required_lines)

    # Do not append English fallback copy onto already-translated secondary world languages
    if (
        full_loc not in ("en-US", "fr-CA", "es-US")
        or "secondary_language" in reason
        or target_queue == "multilingual_support"
    ):
        return text

    generic_line = spoken_line("live_agent_handoff", loc)
    if (is_biz or is_specialist or is_fraud) and _norm_ws(existing) == _norm_ws(
        generic_line
    ):
        return " ".join(required_lines)

    norm_existing = _norm_ws(existing)
    missing = [line for line in required_lines if _norm_ws(line) not in norm_existing]
    if not missing:
        return text
    empathy_line = spoken_line("empathy_protocol", loc) if is_fraud else ""
    if (
        is_fraud
        and empathy_line in missing
        and (
            _norm_ws(generic_line) in norm_existing
            or any(
                hold_tail in norm_existing
                for hold_tail in _SP_HOLD_TAILS
            )
        )
    ):
        other_missing = [line for line in missing if line != empathy_line]
        merged = f"{empathy_line} {existing}"
        if other_missing:
            merged = f"{merged} {' '.join(other_missing)}"
        return merged
    return f"{existing} {' '.join(missing)}"


def enforce_closing_utterance(
    reason: str = "resolved",
    language: str | None = "en-US",
) -> str:
    """Return a warm, localized spoken closing line when ending a session."""
    loc = resolve_copy_locale(language)
    clean_reason = str(reason or "").strip().lower()
    if clean_reason == "malicious_input":
        return spoken_line("malicious_closing", loc)
    if clean_reason == "blocked_caller":
        return spoken_line("blocked_caller_deflection", loc)
    if loc == "fr-CA":
        return "Merci d'avoir choisi Telco. Bonne journée!"
    if loc == "es-US":
        return "¡Gracias por llamar a Telco! Que tenga un excelente día."
    return "Thank you for contacting Telco. Have a wonderful day!"

