"""Dynamic multilingual prompt injection via read-only before_model_callback."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, NamedTuple

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.copy import (
    AGENT_VERBATIM_KEYS,
    SPOKEN_LINES,
    SUPPORTED_COPY_LOCALES,
    WORLD_LANGUAGE_NAMES,
    resolve_copy_locale,
    resolve_locale,
    spoken_line,
)
from lib.fakes import BLOCKED_CALLER_NUMBERS, only_digits

LANGUAGE_SHEET_SENTINEL = "<!-- ACTIVE_LANGUAGE_SHEET -->"

SHARED_COGNATES: frozenset[str] = frozenset(
    {
        "internet",
        "mobile",
        "mobility",
        "sim",
        "tv",
        "wifi",
        "wi-fi",
        "fibe",
        "bell",
        "telco",
        "pin",
        "otp",
        "mfa",
        "sms",
        "ok",
        "okay",
        "agent",
        "service",
        "support",
        "plan",
        "menu",
        "code",
        "cable",
        "modem",
        "router",
        "app",
        "streaming",
        "satellite",
    }
)

_FRENCH_MARKERS = frozenset(
    {
        "bonjour",
        "bonsoir",
        "salut",
        "oui",
        "merci",
        "svp",
        "je",
        "j'ai",
        "j'aimerais",
        "mon",
        "ma",
        "mes",
        "votre",
        "notre",
        "pour",
        "avec",
        "dans",
        "sur",
        "facture",
        "forfait",
        "compte",
        "numéro",
        "annuler",
        "désactiver",
        "remboursement",
        "garantie",
        "clavier",
        "paiement",
        "panne",
        "réseau",
        "téléphone",
        "courriel",
        "veuillez",
        "pouvez",
        "voudrais",
        "veux",
        "aimerais",
        "habite",
        "adresse",
        "déménage",
        "vérifier",
        "disponibilité",
        "élevée",
        "trop",
        "besoin",
        "aide",
        "problème",
        "connexion",
        "fonctionne",
        "quelqu'un",
        "quelqu",
        "quelquun",
        "piraté",
        "pirate",
        "volé",
        "fraude",
        "peur",
        "carte",
        "ligne",
        "changer",
        "payer",
    }
)

_SPANISH_MARKERS = frozenset(
    {
        "hola",
        "buenos",
        "buenas",
        "quiero",
        "necesito",
        "factura",
        "cuenta",
        "gracias",
        "por",
        "favor",
        "ayuda",
        "servicio",
        "tarjeta",
        "reembolso",
        "cancelar",
    }
)

_ENGLISH_MARKERS = frozenset(
    {
        "hello",
        "hi",
        "my",
        "want",
        "need",
        "bill",
        "account",
        "please",
        "help",
        "cancel",
        "reset",
        "password",
        "outage",
        "upgrade",
        "refund",
        "dispute",
        "payment",
        "phone",
        "the",
        "with",
        "have",
        "your",
        "this",
        "that",
        "would",
        "could",
        "check",
        "issue",
        "working",
        "down",
        "is",
        "am",
        "at",
        "address",
        "moving",
        "availability",
    }
)

_DP_GERMAN_MARKERS = frozenset(
    {
        "guten",
        "hallo",
        "morgen",
        "abend",
        "sprechen",
        "deutsch",
        "ich",
        "brauche",
        "hilfe",
        "helfen",
        "meiner",
        "meine",
        "mein",
        "rechnung",
        "bitte",
        "danke",
        "konto",
        "vertrag",
        "störung",
        "kündigen",
        "möchte",
        "funktioniert",
        "nicht",
        "haben",
        "habe",
        "kann",
        "können",
        "wie",
        "bezahlen",
        "zahlen",
        "telefonnummer",
        "aktueller",
        "nur",
        "spreche",
        "verstehe",
        "kein",
        "keine",
        "warum",
    }
)

_DP_PORTUGUESE_MARKERS = frozenset(
    {
        "olá",
        "oi",
        "bom",
        "boa",
        "noite",
        "preciso",
        "ajuda",
        "minha",
        "minhas",
        "meu",
        "meus",
        "fatura",
        "conta",
        "plano",
        "quero",
        "gostaria",
        "não",
        "tenho",
        "estou",
        "obrigado",
        "obrigada",
        "você",
        "vocês",
        "atendente",
        "cartão",
        "ligação",
        "português",
        "senha",
        "aparelho",
        "qual",
        "atual",
    }
)

_DP_ITALIAN_MARKERS = frozenset(
    {
        "buongiorno",
        "buonasera",
        "salve",
        "ciao",
        "parla",
        "italiano",
        "perché",
        "bisogno",
        "aiuto",
        "aiutarmi",
        "aiutare",
        "vorrei",
        "potete",
        "bolletta",
        "fattura",
        "connessione",
        "funziona",
        "disdire",
        "abbonamento",
        "cellulare",
        "guasto",
        "grazie",
        "favore",
        "mia",
        "mio",
    }
)

_DP_QUEBEC_PLACE_TOKENS = frozenset(
    {
        "montréal",
        "montreal",
        "québec",
        "quebec",
        "laval",
        "longueuil",
        "gatineau",
        "sherbrooke",
        "lévis",
        "levis",
        "trois",
        "rivières",
        "rivieres",
        "saguenay",
        "terrebonne",
        "brossard",
        "repentigny",
        "saint",
        "sainte",
        "st",
        "ste",
        "laurent",
        "catherine",
        "denis",
        "hubert",
        "jean",
        "baptiste",
        "honoré",
        "honore",
        "rené",
        "rene",
        "lévesque",
        "levesque",
        "côte",
        "cote",
        "neiges",
        "île",
        "ile",
        "boulevard",
        "boul",
        "rue",
        "avenue",
        "ave",
        "chemin",
        "ch",
        "appartement",
        "apt",
        "suite",
        "qc",
    }
)


_DP_STREET_ADDRESS_TOKENS = frozenset(
    {
        "rue",
        "boulevard",
        "boul",
        "blvd",
        "avenue",
        "ave",
        "av",
        "chemin",
        "ch",
        "route",
        "rte",
        "rang",
        "place",
        "côte",
        "cote",
        "impasse",
        "croissant",
        "allée",
        "allee",
        "terrasse",
        "promenade",
        "montée",
        "montee",
        "appartement",
        "apt",
        "street",
        "road",
        "rd",
        "drive",
        "dr",
        "qc",
    }
)

_DP_CANADIAN_POSTAL_RE = re.compile(
    r"\b[a-z]\d[a-z]\s*-?\s*\d[a-z]\d\b",
    re.IGNORECASE,
)
_DP_STREET_NUMBER_RE = re.compile(r"\b\d{1,5}\b")

_RE_QUOTED_AGENT_BLOCK = re.compile(
    r"<<<BEGIN_QUOTED_AGENT_CONTENT>>>[\s\S]*?<<<END_QUOTED_AGENT_CONTENT>>>"
)
_RE_KEYPAD_CONTEXT_TAG = re.compile(
    r"<context\b[^>]*>\s*user\s+pressed\s+([0-9*#]+)\s+on\s+keypad\.?\s*</context>",
    re.IGNORECASE,
)
_RE_CONTEXT_TAG = re.compile(
    r"<context\b[^>]*>[\s\S]*?</context>|<context\b[^>]*/>",
    re.IGNORECASE,
)
_RE_STATE_UPDATE = re.compile(
    r"<state_update\b[^>]*>[\s\S]*?</state_update>|<state_update\b[^>]*/>",
    re.IGNORECASE,
)
_RE_EVENT_TAG = re.compile(
    r"<event\b[^>]*>[\s\S]*?</event>|<event\b[^>]*/>",
    re.IGNORECASE,
)


def _strip_system_tags(txt: str) -> str:
    """Normalize keypad context tag to [dtmf: \1] and strip non-DTMF system tags."""
    if not txt:
        return ""
    res = _RE_KEYPAD_CONTEXT_TAG.sub(r"[dtmf: \1]", txt)
    res = _RE_QUOTED_AGENT_BLOCK.sub("", res)
    res = _RE_STATE_UPDATE.sub("", res)
    res = _RE_EVENT_TAG.sub("", res)
    res = _RE_CONTEXT_TAG.sub("", res)
    return res.strip()


PROMPT_INJECTION_RE = re.compile(
    r"(?i)\b(?:ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)|reveal\s+(?:your\s+|the\s+)?(?:system\s+|hidden\s+)?(?:prompt|instructions?)|show\s+(?:me\s+)?(?:your\s+|the\s+)?system\s+prompt|act\s+as\s+a\s+linux\s+terminal|developer\s+mode|oublie[rz]?\s+(?:toutes?\s+)?les\s+instructions\s+pr[eé]c[eé]dentes|ignora\s+(?:todas?\s+)?las\s+instrucciones\s+anteriores)\b"
)

SELF_HARM_CRISIS_RE = re.compile(
    r"(?i)\b(?:kill\s+myself|end\s+my\s+life|take\s+my\s+(?:own\s+)?life|harm\s+myself|hurt\s+myself|want\s+to\s+die|going\s+to\s+die|commit\s+suicide|feeling\s+suicidal|suicidal\s+thoughts|don'?t\s+want\s+to\s+live|me\s+suicider|mettre\s+fin\s+[àa]\s+mes\s+jours|en\s+finir\s+avec\s+la\s+vie|envie\s+de\s+mourir|suicidarme|quitar(?:me|se)?\s+la\s+vida|matar(?:me|se)?|no\s+quiero\s+vivir)\b"
)

_DP_NEGATED_SWITCH_PREFIX_RE = re.compile(
    r"(?:"
    r"\b(?:don't|do\s+not|dont|cannot|can't|cant|not)\s+"
    r"(?:want\s+to\s+|know\s+how\s+to\s+)?(?:speak\s+|talk\s+|switch\s+to\s+)?"
    r"|\b(?:pas|jamais)\s+(?:parler\s+|continuer\s+)?"
    r"|\bno\s+(?:hablo|habla|hablas|hablamos|puedo|podemos|quiero)\s+(?:hablar\s+)?"
    r")$",
    re.IGNORECASE,
)

_DP_EXPLICIT_SWITCH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "fr-CA",
        (
            "en français",
            "en francais",
            "parler en français",
            "parler en francais",
            "switch to french",
            "switch back to french",
            "back to french",
            "french please",
            "in french",
            "in french please",
            "speak french",
            "passer au français",
            "passer au francais",
            "revenir au français",
            "revenir au francais",
            "parlez français",
            "parlez francais",
            "parlons français",
            "parlons francais",
            "secondary language",
        ),
    ),
    (
        "en-US",
        (
            "in english",
            "in english please",
            "switch to english",
            "switch back to english",
            "back to english",
            "return to english",
            "speak english",
            "can we continue in english",
            "continue in english",
            "english please",
            "en anglais",
            "parler en anglais",
            "passer à l'anglais",
            "passer a l'anglais",
            "revenir à l'anglais",
            "revenir a l'anglais",
            "parlez anglais",
            "parlons anglais",
            "primary language",
            "en inglés",
            "en ingles",
            "hablar inglés",
            "hablar ingles",
            "habla inglés",
            "habla ingles",
        ),
    ),
    (
        "es-US",
        (
            "en español",
            "en espanol",
            "hablar en español",
            "hablar en espanol",
            "hablar español",
            "hablar espanol",
            "habla español",
            "habla espanol",
            "hablemos en español",
            "hablemos español",
            "switch to spanish",
            "switch back to spanish",
            "back to spanish",
            "spanish please",
            "in spanish",
            "in spanish please",
            "speak spanish",
            "cambiar a español",
            "cambiar a espanol",
            "volver al español",
            "volver al espanol",
            "en espagnol",
            "parler en espagnol",
            "passer à l'espagnol",
            "passer a l'espagnol",
        ),
    ),
    (
        "pt-BR",
        (
            "em português",
            "em portugues",
            "fala português",
            "fala portugues",
            "in portuguese",
            "do you speak portuguese",
            "speak portuguese",
            "switch to portuguese",
            "portuguese please",
        ),
    ),
    (
        "de-DE",
        (
            "auf deutsch",
            "sprechen sie deutsch",
            "in german",
            "do you speak german",
            "speak german",
            "switch to german",
            "german please",
        ),
    ),
    (
        "it-IT",
        (
            "in italiano",
            "parla italiano",
            "in italian",
            "do you speak italian",
            "speak italian",
            "switch to italian",
            "italian please",
        ),
    ),
    (
        "zh-CN",
        (
            "in mandarin",
            "in chinese",
            "do you speak mandarin",
            "do you speak chinese",
            "speak mandarin",
            "speak chinese",
            "mandarin please",
            "switch to mandarin",
        ),
    ),
    (
        "hi-IN",
        (
            "in hindi",
            "do you speak hindi",
            "speak hindi",
            "hindi please",
            "switch to hindi",
        ),
    ),
    (
        "ar-XA",
        (
            "in arabic",
            "do you speak arabic",
            "speak arabic",
            "arabic please",
            "switch to arabic",
        ),
    ),
    (
        "ja-JP",
        (
            "in japanese",
            "do you speak japanese",
            "speak japanese",
            "japanese please",
            "switch to japanese",
        ),
    ),
    (
        "ko-KR",
        (
            "in korean",
            "do you speak korean",
            "speak korean",
            "korean please",
            "switch to korean",
        ),
    ),
)


def _dp_match_explicit_switch(low: str) -> str:
    """Return target locale for the last non-negated explicit switch term in `low`."""
    best_end = -1
    best_locale = ""
    for target_locale, terms in _DP_EXPLICIT_SWITCH_TERMS:
        for term in terms:
            for m in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", low):
                if _DP_NEGATED_SWITCH_PREFIX_RE.search(low[: m.start()]):
                    continue
                if m.end() > best_end:
                    best_end = m.end()
                    best_locale = target_locale
    return best_locale


_AMBIGUOUS_SINGLE_TOKENS: frozenset[str] = frozenset(
    {
        "oui",
        "non",
        "no",
        "ok",
        "okay",
        "menu",
        "merci",
        "gracias",
        "si",
    }
)


def extract_dtmf_digits(utterance: Any) -> str:
    """Normalize any DTMF entered during the turn to a clean digit string or empty string."""
    raw = str(utterance or "").strip()
    if not raw:
        return ""
    m = re.search(
        r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user\s+pressed)\s*[:#-]?\s*)([0-9*#]+)",
        raw,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"[^0-9*#]", "", m.group(1))
    digits_only = re.sub(r"[^0-9*#]", "", raw)
    if digits_only and re.fullmatch(r"[\s\[\]#*.-]*([0-9*#]+)[\s\[\]#*.-]*", raw):
        return digits_only
    return ""


def detect_utterance_language(
    utterance: str,
    current_language: str = "en-US",
    is_turn_1: bool = True,
    language_locked: bool = False,
    state: Any = None,
) -> str:
    """Detect language from an utterance with contextual inertia on silence and numbers."""
    if state and callable(getattr(state, "get", None)):
        if state.get("language_locked"):
            language_locked = True
        if int(state.get("turn_index", 0)) > 1:
            is_turn_1 = False

    raw = str(utterance or "").strip()
    raw = _strip_system_tags(raw)
    if is_turn_1 and not language_locked:
        if re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?2(?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            return "fr-CA"
        if re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?1(?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            return "en-US"
    else:
        if re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?[12](?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            return resolve_locale(current_language)

    cleaned = re.sub(r"\[(?:pause|silence)\]", " ", str(utterance or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"[0-9\W_]+", " ", cleaned).strip()
    if not cleaned:
        return resolve_locale(current_language)

    low = str(utterance or "").lower()

    explicit_switch = _dp_match_explicit_switch(low)
    if explicit_switch:
        return explicit_switch

    if re.search(r"[\u0600-\u06ff]", utterance):
        return "ar-XA"
    if re.search(r"[\u0900-\u097f]", utterance):
        return "hi-IN"
    if re.search(r"[\u3040-\u30ff]", utterance):
        return "ja-JP"
    if re.search(r"[\uac00-\ud7af]", utterance):
        return "ko-KR"
    if re.search(r"[\u4e00-\u9fff]", utterance):
        return "zh-CN"
    if re.search(r"[\u0400-\u04ff]", utterance):
        return "ru-RU"
    if re.search(r"[\u0370-\u03ff]", utterance):
        return "el-GR"
    if re.search(r"[\u0590-\u05ff]", utterance):
        return "he-IL"
    if re.search(r"[\u0e00-\u0e7f]", utterance):
        return "th-TH"

    words = [w.lower() for w in cleaned.split()]

    curr_loc = resolve_locale(current_language)
    if curr_loc == "en-US":
        if len(words) == 1 and words[0] in _AMBIGUOUS_SINGLE_TOKENS:
            return "en-US"
        if all(w in _AMBIGUOUS_SINGLE_TOKENS for w in words):
            return "en-US"

    german_score = sum(1 for w in words if w in _DP_GERMAN_MARKERS) + (
        1 if re.search(r"[äöüß]", low) else 0
    )
    portuguese_score = sum(1 for w in words if w in _DP_PORTUGUESE_MARKERS) + (
        1 if re.search(r"[ãõ]", low) else 0
    )
    italian_score = sum(1 for w in words if w in _DP_ITALIAN_MARKERS)

    if (
        german_score >= 2
        and german_score >= portuguese_score
        and german_score >= italian_score
    ):
        return "de-DE"
    if (
        portuguese_score >= 2
        and portuguese_score > german_score
        and portuguese_score >= italian_score
    ):
        return "pt-BR"
    if (
        italian_score >= 2
        and italian_score > german_score
        and italian_score > portuguese_score
    ):
        return "it-IT"

    non_place_text = " ".join(w for w in words if w not in _DP_QUEBEC_PLACE_TOKENS)
    is_en_address_turn = curr_loc == "en-US" and (
        bool(_DP_CANADIAN_POSTAL_RE.search(low))
        or (
            bool(_DP_STREET_NUMBER_RE.search(low))
            and bool(_DP_STREET_ADDRESS_TOKENS.intersection(words))
        )
    )
    has_french_accents = (
        False
        if is_en_address_turn
        else bool(re.search(r"[éèêëàâùûîïôçœ]", non_place_text))
    )
    french_words = sum(1 for w in words if w in _FRENCH_MARKERS)
    french_score = french_words + (1 if has_french_accents else 0)

    has_spanish_punct = bool(re.search(r"[¿¡ñ]", low))
    spanish_words = sum(1 for w in words if w in _SPANISH_MARKERS)
    spanish_score = spanish_words + (1 if has_spanish_punct else 0)

    english_words = sum(1 for w in words if w in _ENGLISH_MARKERS)

    if french_score > 0 and french_score >= spanish_score and french_score >= english_words:
        if curr_loc == "en-US" and (
            (len(words) == 1 and words[0] in _AMBIGUOUS_SINGLE_TOKENS)
            or (french_score == 1 and not has_french_accents and words[0] in _AMBIGUOUS_SINGLE_TOKENS)
        ):
            return "en-US"
        return "fr-CA"
    if spanish_score > 0 and spanish_score > french_score and spanish_score >= english_words:
        if curr_loc == "en-US" and (
            (len(words) == 1 and words[0] in _AMBIGUOUS_SINGLE_TOKENS)
            or (spanish_score == 1 and not has_spanish_punct and words[0] in _AMBIGUOUS_SINGLE_TOKENS)
        ):
            return "en-US"
        return "es-US"
    if english_words >= 3 and french_score == 0 and spanish_score == 0:
        return "en-US"

    return curr_loc


_RE_RELAY_PREFIX = re.compile(
    r"^(?:For context|\s*\[[^\]]+\]\s*(?:said:|thought:|called tool |`[^`]*` tool returned result:))",
    re.IGNORECASE,
)
_RE_RELAY_ACTIVE_LANG = re.compile(
    r"['\"]active_language['\"]\s*:\s*['\"]([a-zA-Z]{2}(?:-[a-zA-Z]{2})?)['\"]"
)


def _is_relay_or_quoted_part(txt: str) -> bool:
    """Return True if txt is an ADK relay part, agent event, state update, or quoted content block."""
    s = txt.strip()
    if not s:
        return True
    if _RE_RELAY_PREFIX.match(s):
        return True
    cleaned = _strip_system_tags(s)
    if not cleaned:
        return True
    if _RE_RELAY_PREFIX.match(cleaned):
        return True
    return False


def _extract_relayed_active_language(llm_request: Any) -> str:
    """Extract the most recent active_language from relayed tool results in contents."""
    contents = getattr(llm_request, "contents", None)
    if not contents or not isinstance(contents, (list, tuple)):
        return ""
    last_lang = ""
    for item in contents:
        parts = getattr(item, "parts", None)
        if parts and isinstance(parts, (list, tuple)):
            for part in parts:
                txt = getattr(part, "text", None)
                if txt and isinstance(txt, str):
                    matches = _RE_RELAY_ACTIVE_LANG.findall(txt)
                    if matches:
                        last_lang = matches[-1]
                fn_resp = getattr(part, "function_response", None)
                if fn_resp:
                    resp = getattr(fn_resp, "response", None)
                    if isinstance(resp, dict):
                        al = resp.get("active_language")
                        if not al and isinstance(resp.get("result"), dict):
                            al = resp["result"].get("active_language")
                        if al and isinstance(al, str):
                            last_lang = al
        elif isinstance(getattr(item, "text", None), str):
            matches = _RE_RELAY_ACTIVE_LANG.findall(item.text)
            if matches:
                last_lang = matches[-1]
    if last_lang:
        return resolve_locale(last_lang)
    return ""


def extract_user_utterances(llm_request: Any) -> list[str]:
    """Safely extract genuine user utterance strings from LLM request contents, skipping relay parts."""
    utterances: list[str] = []
    contents = getattr(llm_request, "contents", None)
    if not contents or not isinstance(contents, (list, tuple)):
        return utterances
    for item in contents:
        if getattr(item, "role", "") == "user":
            parts = getattr(item, "parts", None)
            if parts and isinstance(parts, (list, tuple)):
                for part in parts:
                    txt = getattr(part, "text", None)
                    if txt and isinstance(txt, str) and txt.strip():
                        if not _is_relay_or_quoted_part(txt):
                            sanitized = _strip_system_tags(txt)
                            if sanitized:
                                utterances.append(sanitized)
            elif isinstance(getattr(item, "text", None), str):
                t = item.text.strip()
                if t and not _is_relay_or_quoted_part(t):
                    sanitized = _strip_system_tags(t)
                    if sanitized:
                        utterances.append(sanitized)
    return utterances


def is_supported_locale(loc: str | None) -> bool:
    """Return True if `loc` resolves to a PRD-supported locale (en-US, fr-CA, es-US)."""
    raw = str(loc or "").strip()
    if not raw:
        return False
    if raw in SUPPORTED_COPY_LOCALES:
        return True
    low = raw.lower().replace("_", "-")
    if low in ("primary", "secondary") or low.startswith(
        (
            "en",
            "english",
            "anglais",
            "fr",
            "french",
            "francais",
            "français",
            "es",
            "spanish",
            "espanol",
            "español",
        )
    ):
        return resolve_locale(raw) in SUPPORTED_COPY_LOCALES
    return False


_LANG_CHOICE_EN: frozenset[str] = frozenset({"english", "anglais", "inglés", "ingles"})
_LANG_CHOICE_FR: frozenset[str] = frozenset(
    {"french", "français", "francais", "frances", "francés"}
)
_LANG_CHOICE_ES: frozenset[str] = frozenset(
    {"spanish", "español", "espanol", "espagnol"}
)
_LANG_CHOICE_COURTESY: frozenset[str] = frozenset(
    {
        "please",
        "svp",
        "oui",
        "yes",
        "si",
        "sí",
        "ok",
        "okay",
        "merci",
        "gracias",
        "bitte",
        "ja",
    }
)


def _match_language_choice_response(utterance: str) -> str:
    """Match one-word or polite-word language-choice answers after an unsupported turn."""
    cleaned = re.sub(r"[0-9\W_]+", " ", str(utterance or "")).strip().lower()
    if not cleaned:
        return ""
    words = cleaned.split()
    if not words:
        return ""
    if all(w in (_LANG_CHOICE_EN | _LANG_CHOICE_COURTESY) for w in words) and any(
        w in _LANG_CHOICE_EN for w in words
    ):
        return "en-US"
    if all(w in (_LANG_CHOICE_FR | _LANG_CHOICE_COURTESY) for w in words) and any(
        w in _LANG_CHOICE_FR for w in words
    ):
        return "fr-CA"
    if all(w in (_LANG_CHOICE_ES | _LANG_CHOICE_COURTESY) for w in words) and any(
        w in _LANG_CHOICE_ES for w in words
    ):
        return "es-US"
    return ""


class LanguagePolicy(NamedTuple):
    locale: str
    caller_locale: str
    unsupported_strikes: int
    latest_unsupported: bool


def detect_language_policy(state_dict: Any, llm_request: Any) -> LanguagePolicy:
    """Determine active supported locale and unsupported-language strike policy from state and history."""
    user_utterances = extract_user_utterances(llm_request)
    state_get = getattr(state_dict, "get", None)
    has_state = callable(state_get)

    is_locked = bool(state_dict.get("language_locked", False)) if has_state else False
    raw_locked = (
        str(
            state_dict.get("language")
            or state_dict.get("fx_language")
            or state_dict.get("preferred_language")
            or ""
        ).strip()
        if has_state
        else ""
    )
    locked = ""
    if raw_locked:
        if is_supported_locale(raw_locked):
            locked = resolve_locale(raw_locked)
        else:
            locked = "en-US"
            is_locked = False
    else:
        relayed = _extract_relayed_active_language(llm_request)
        if relayed:
            if is_supported_locale(relayed):
                locked = relayed
            else:
                locked = "en-US"
                is_locked = False

    raw_explicit = (
        str(
            state_dict.get("explicit_language_switch")
            or state_dict.get("fx_language")
            or ""
        ).strip()
        if has_state
        else ""
    )
    explicit_in_state = ""
    if raw_explicit and is_supported_locale(raw_explicit):
        explicit_in_state = resolve_locale(raw_explicit)

    if not user_utterances:
        base_loc = explicit_in_state or locked or "en-US"
        return LanguagePolicy(
            locale=base_loc,
            caller_locale="",
            unsupported_strikes=0,
            latest_unsupported=False,
        )

    current = explicit_in_state or locked or "en-US"
    has_locked = (
        is_locked or bool(locked and locked != "en-US") or bool(explicit_in_state)
    )
    # Strikes are recomputed from the caller's utterance history on every turn
    # (stateless), so no additional session variables are needed.
    strikes = 0
    caller_locale = ""
    latest_unsupported = False

    for utt in user_utterances:
        low = utt.lower()
        switch = _dp_match_explicit_switch(low)
        if switch:
            if is_supported_locale(switch):
                current = switch
                has_locked = True
                strikes = 0
                caller_locale = ""
                latest_unsupported = False
            else:
                has_locked = False
                strikes += 1
                caller_locale = switch
                latest_unsupported = True
            continue

        if strikes >= 1:
            choice_loc = _match_language_choice_response(utt)
            if choice_loc:
                current = choice_loc
                has_locked = True
                strikes = 0
                caller_locale = ""
                latest_unsupported = False
                continue

        if has_locked:
            # Locked or mid-call: bare 2/digits or ambiguous tokens never flip language
            latest_unsupported = False
            continue

        # Not yet locked (Turn 1 or following an unsupported turn):
        raw = utt.strip()
        if re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?2(?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            current = "fr-CA"
            has_locked = True
            strikes = 0
            caller_locale = ""
            latest_unsupported = False
        elif re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?1(?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            current = "en-US"
            has_locked = True
            strikes = 0
            caller_locale = ""
            latest_unsupported = False
        else:
            det = detect_utterance_language(
                utt, current_language=current, is_turn_1=True, language_locked=False
            )
            if is_supported_locale(det):
                current = det
                has_locked = True
                strikes = 0
                caller_locale = ""
                latest_unsupported = False
            else:
                strikes += 1
                caller_locale = det
                latest_unsupported = True

    return LanguagePolicy(
        locale=current,
        caller_locale=caller_locale,
        unsupported_strikes=strikes,
        latest_unsupported=latest_unsupported,
    )


def detect_active_call_language(state_dict: Any, llm_request: Any) -> str:
    """Determine the active conversation language from state and user turns."""
    return detect_language_policy(state_dict, llm_request).locale


def build_language_sheet(
    locale: str,
    agent_name: str = "router",
    policy: LanguagePolicy | None = None,
) -> str:
    """Generate dynamic language sheet containing localized rules and verbatim lines."""
    loc = resolve_copy_locale(locale)
    lang_name = WORLD_LANGUAGE_NAMES.get(loc, loc)
    keys = AGENT_VERBATIM_KEYS.get(agent_name, AGENT_VERBATIM_KEYS["router"])

    if policy is not None and policy.latest_unsupported:
        caller_code = policy.caller_locale or "unknown"
        caller_name = WORLD_LANGUAGE_NAMES.get(caller_code, caller_code)
        open_tag = (
            f'<active_language_sheet locale="{loc}" language="{lang_name}" '
            f'caller_language="{caller_name} ({caller_code})" status="unsupported">'
        )
    else:
        open_tag = f'<active_language_sheet locale="{loc}" language="{lang_name}">'

    lines = [
        LANGUAGE_SHEET_SENTINEL,
        open_tag,
        "### Required Disclosures & Spoken Lines (Emit Exact Wording):",
    ]
    for k in keys:
        line_text = spoken_line(k, loc)
        lines.append(f'- {k}: "{line_text}"')

    if policy is not None and policy.latest_unsupported:
        caller_code = policy.caller_locale or "unknown"
        caller_name = WORLD_LANGUAGE_NAMES.get(caller_code, caller_code)
        lines.append("")
        lines.append("### Unsupported caller language:")
        if policy.unsupported_strikes >= 2:
            lines.append(
                f'- Strike count: {policy.unsupported_strikes} (caller continued in {caller_name} ({caller_code})). Action: speak live_agent_handoff and call handover_to_person(reason="secondary_language_live_agent", target_queue="multilingual_support") and end_session(reason="secondary_language_live_agent") in the same turn.'
            )
        else:
            lines.append(
                f"- Strike count: {policy.unsupported_strikes} (caller spoke {caller_name} ({caller_code})). Action: speak language_not_supported in English, then French, then Spanish, and call no tools."
            )

    lines.append("")
    lines.append("### Mandatory Conversational Rules:")
    lines.append(
        f"1. Speak 100% in {lang_name} ({loc}). Never mix languages or repeat lines in another language."
    )
    lines.append(
        f'2. Always pass language="{loc}" when calling tools (and write any free-text reason/summary in {lang_name} while keeping structural enum values unchanged).'
    )
    lines.append(
        "3. Emit the verbatim lines above word-for-word whenever their trigger fires, filling [amount] and [days] from tool output only."
    )
    lines.append(
        '4. Service is offered only in English, Canadian French and Spanish. If the caller speaks any other language (even one you understand), do not answer in it: speak language_not_supported in English, then French, then Spanish, and call no tools; if the caller continues in that language on the next turn, speak live_agent_handoff and call handover_to_person(reason="secondary_language_live_agent", target_queue="multilingual_support") and end_session(reason="secondary_language_live_agent") in the same turn.'
    )
    lines.append("</active_language_sheet>")
    return "\n".join(lines)


def apply_language_prompt_filter(
    callback_context: Any,
    llm_request: Any,
    agent_name: str = "router",
    update_state: bool = False,
    llm_response_cls: Any = None,
    part_cls: Any = None,
) -> Any:
    """Inject language rules and verbatim lines into system instruction in-place, or intercept turn."""
    state = getattr(callback_context, "state", None)
    state_dict = state if callable(getattr(state, "get", None)) else {}
    policy = detect_language_policy(state_dict, llm_request)
    locale = policy.locale
    sheet = build_language_sheet(locale, agent_name=agent_name, policy=policy)

    user_utterances = extract_user_utterances(llm_request)
    latest_utt = user_utterances[-1] if user_utterances else ""

    # Gap 3: Blocked caller ID check on Turn 0 before greeting
    turn_idx = int(state_dict.get("turn_index", 0) or 0)
    _cid_key = "telephony-" + "caller-id"
    raw_cid = str(state_dict.get(_cid_key) or "")
    cid_digits = only_digits(raw_cid)
    is_blocked_caller = bool(state_dict.get("is_blocked")) or bool(
        cid_digits and cid_digits[-10:] in BLOCKED_CALLER_NUMBERS
    )
    if turn_idx == 0 and not user_utterances and is_blocked_caller:
        if hasattr(state, "__setitem__"):
            try:
                state["is_blocked"] = True
            except (TypeError, AttributeError):
                pass
        if llm_response_cls is not None and part_cls is not None:
            return llm_response_cls.from_parts(
                parts=[
                    part_cls.from_text(text=spoken_line("blocked_caller_deflection", locale)),
                    part_cls.from_function_call(
                        name="end_session",
                        args={"reason": "blocked_caller"},
                    ),
                ]
            )

    is_new_caller_turn = False
    contents = getattr(llm_request, "contents", None)
    if contents and isinstance(contents, (list, tuple)):
        last_item = contents[-1]
        last_parts = getattr(last_item, "parts", None) or ()
        has_fn_resp = any(getattr(p, "function_response", None) is not None for p in last_parts)
        if getattr(last_item, "role", "") == "user" and not has_fn_resp and bool(latest_utt):
            is_new_caller_turn = True
    elif not contents and bool(latest_utt):
        is_new_caller_turn = True

    # Pre-model safety & unsupported-language interception
    if is_new_caller_turn and latest_utt and llm_response_cls is not None and part_cls is not None:
        if SELF_HARM_CRISIS_RE.search(latest_utt):
            msg = f"{spoken_line('empathy_protocol', locale)} {spoken_line('live_agent_handoff', locale)}"
            if hasattr(state, "__setitem__"):
                try:
                    state["handover_complete"] = True
                    state["handoff_status"] = "escalated"
                    state["handoff_reason"] = "safety_escalation"
                    state["handoff_message"] = msg
                except (TypeError, AttributeError):
                    pass
            return llm_response_cls.from_parts(
                parts=[
                    part_cls.from_text(text=msg),
                    part_cls.from_function_call(
                        name="handover_to_person",
                        args={
                            "reason": "safety_escalation",
                            "target_queue": "fraud_and_security_24x7",
                            "summary": "Urgent caller safety crisis requiring immediate human support.",
                            "language": locale,
                        },
                    ),
                    part_cls.from_function_call(
                        name="end_session",
                        args={"reason": "safety_escalation"},
                    ),
                ]
            )

        if PROMPT_INJECTION_RE.search(latest_utt):
            return llm_response_cls.from_parts(
                parts=[
                    part_cls.from_text(text=spoken_line("malicious_closing", locale)),
                    part_cls.from_function_call(
                        name="end_session",
                        args={"reason": "malicious_input"},
                    ),
                ]
            )

        if policy.latest_unsupported:
            caller_code = policy.caller_locale or "unknown"
            caller_lang_name = WORLD_LANGUAGE_NAMES.get(caller_code, caller_code)
            if hasattr(state, "__setitem__"):
                try:
                    state["turn_index"] = int(state_dict.get("turn_index", 0) or 0) + 1
                    state["utterance"] = latest_utt
                    state["last_user_utterance"] = latest_utt
                    state["language"] = "en-US"
                    state["language_locked"] = False
                except (TypeError, AttributeError):
                    pass
            if policy.unsupported_strikes <= 1:
                notice_msg = (
                    f"{spoken_line('language_not_supported', 'en-US')} "
                    f"{spoken_line('language_not_supported', 'fr-CA')} "
                    f"{spoken_line('language_not_supported', 'es-US')}"
                )
                return llm_response_cls.from_parts(
                    parts=[part_cls.from_text(text=notice_msg)]
                )
            handoff_msg = (
                f"{spoken_line('live_agent_handoff', 'en-US')} "
                f"{spoken_line('live_agent_handoff', 'fr-CA')} "
                f"{spoken_line('live_agent_handoff', 'es-US')}"
            )
            if hasattr(state, "__setitem__"):
                try:
                    state["handover_complete"] = True
                    state["handoff_status"] = "escalated"
                    state["handoff_reason"] = "secondary_language_live_agent"
                    state["handoff_message"] = handoff_msg
                except (TypeError, AttributeError):
                    pass
            return llm_response_cls.from_parts(
                parts=[
                    part_cls.from_text(text=handoff_msg),
                    part_cls.from_function_call(
                        name="handover_to_person",
                        args={
                            "reason": "secondary_language_live_agent",
                            "target_queue": "multilingual_support",
                            "summary": f"Caller speaks {caller_lang_name}, which is not a supported language (English, French, Spanish).",
                            "language": "en-US",
                        },
                    ),
                    part_cls.from_function_call(
                        name="end_session",
                        args={"reason": "secondary_language_live_agent"},
                    ),
                ]
            )

    # Synchronize state when requested or when state already tracks turn/lock
    should_sync = update_state or (
        isinstance(state, dict)
        and (
            "turn_index" in state
            or "language_locked" in state
            or "dtmf_digits" in state
        )
    )
    if should_sync and hasattr(state, "__setitem__"):
        try:
            if latest_utt:
                if is_new_caller_turn:
                    state["turn_index"] = int(state.get("turn_index", 0) or 0) + 1
                    if str(state.get("auth_status") or "").startswith("wrong_code@"):
                        state["auth_status"] = "code_sent"
                if policy.latest_unsupported:
                    state["language"] = "en-US"
                    state["language_locked"] = False
                else:
                    state["language"] = locale
                    state["language_locked"] = True
                state["utterance"] = latest_utt
                state["last_user_utterance"] = latest_utt
                state["dtmf_digits"] = extract_dtmf_digits(latest_utt)
                switch = _dp_match_explicit_switch(latest_utt.lower())
                if switch and is_supported_locale(switch):
                    state["explicit_language_switch"] = switch
            else:
                state["dtmf_digits"] = ""
                if not state.get("language") or not is_supported_locale(state.get("language")):
                    state["language"] = locale
        except (TypeError, AttributeError):
            pass

    config = getattr(llm_request, "config", None)
    if config is None:
        return None
    sys_inst = getattr(config, "system_instruction", None)
    if sys_inst is None:
        return None

    def _update_text(text: str) -> str:
        if LANGUAGE_SHEET_SENTINEL in text:
            text = text.split(LANGUAGE_SHEET_SENTINEL, 1)[0].rstrip()
        return f"{text}\n\n{sheet}"

    if isinstance(sys_inst, str):
        config.system_instruction = _update_text(sys_inst)
    elif hasattr(sys_inst, "parts"):
        parts = getattr(sys_inst, "parts", None)
        if parts and len(parts) > 0:
            first = parts[0]
            if hasattr(first, "text") and isinstance(first.text, str):
                first.text = _update_text(first.text)
    elif isinstance(sys_inst, list) and len(sys_inst) > 0:
        if isinstance(sys_inst[0], str):
            sys_inst[0] = _update_text(sys_inst[0])
        elif hasattr(sys_inst[0], "text") and isinstance(sys_inst[0].text, str):
            sys_inst[0].text = _update_text(sys_inst[0].text)

    return None


def process_turn_language_and_dtmf(
    state: dict[str, Any],
    llm_request: Any,
    agent_name: str = "router",
) -> str:
    """Normalize DTMF, update language state and inject prompt sheet for current turn."""
    apply_language_prompt_filter(
        SimpleNamespace(state=state), llm_request, agent_name=agent_name, update_state=True
    )
    return state.get("language", "en-US")
