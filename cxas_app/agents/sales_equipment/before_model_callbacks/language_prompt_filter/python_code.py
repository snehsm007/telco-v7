from __future__ import annotations

from typing import Optional



def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Inject active language rules and verbatim lines before model invocation."""
    apply_language_prompt_filter(
        callback_context,
        llm_request,
        agent_name="sales_equipment",
    )
    return None


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.dynamic_prompt import apply_language_prompt_filter
from pathlib import Path
from typing import Any
import re
import sys

LANGUAGE_SHEET_SENTINEL = "<!-- ACTIVE_LANGUAGE_SHEET -->"  # pragma: no cover

_DP_EXPLICIT_SWITCH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (  # pragma: no cover
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

_DP_NEGATED_SWITCH_PREFIX_RE = re.compile(  # pragma: no cover
    r"(?:"
    r"\b(?:don't|do\s+not|dont|cannot|can't|cant|not)\s+"
    r"(?:want\s+to\s+|know\s+how\s+to\s+)?(?:speak\s+|talk\s+|switch\s+to\s+)?"
    r"|\b(?:pas|jamais)\s+(?:parler\s+|continuer\s+)?"
    r"|\bno\s+(?:hablo|habla|hablas|hablamos|puedo|podemos|quiero)\s+(?:hablar\s+)?"
    r")$",
    re.IGNORECASE,
)

def _dp_match_explicit_switch(low: str) -> str:  # pragma: no cover
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

AGENT_VERBATIM_KEYS: dict[str, tuple[str, ...]] = {  # pragma: no cover
    "router": (
        "recording_notice",
        "greeting_main",
        "live_agent_handoff",
        "business_handoff",
        "empathy_protocol",
        "malicious_closing",
    ),
    "billing": (
        "recording_notice",
        "id_verification_otp",
        "id_verification_pin",
        "payment_method_preamble",
        "refund_confirmation_pattern",
        "transfer_to_specialist",
        "live_agent_handoff",
        "business_handoff",
        "empathy_protocol",
    ),
    "tech_support": (
        "recording_notice",
        "id_verification_otp",
        "id_verification_pin",
        "outage_active",
        "outage_none_offer_sms",
        "live_agent_handoff",
        "business_handoff",
        "empathy_protocol",
    ),
    "sales_equipment": (
        "recording_notice",
        "id_verification_otp",
        "id_verification_pin",
        "payment_method_preamble",
        "contract_cancellation_fee_disclosure",
        "live_agent_handoff",
        "business_handoff",
        "empathy_protocol",
    ),
    "account": (
        "recording_notice",
        "id_verification_otp",
        "id_verification_email_otp",
        "id_verification_pin",
        "contract_cancellation_fee_disclosure",
        "live_agent_handoff",
        "business_handoff",
        "empathy_protocol",
    ),
}

WORLD_LANGUAGE_NAMES: dict[str, str] = {  # pragma: no cover
    "en-US": "English",
    "fr-CA": "Canadian French",
    "es-US": "Spanish",
    "pt-BR": "Portuguese",
    "de-DE": "German",
    "it-IT": "Italian",
    "zh-CN": "Mandarin Chinese",
    "hi-IN": "Hindi",
    "ar-XA": "Arabic",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
}

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag, name, or code into a canonical BCP-47 locale."""
    raw = str(language or "").strip()
    if not raw:
        return "en-US"
    low = raw.lower().replace("_", "-")
    if low in ("primary",) or low.startswith(("en", "english", "anglais")):
        return "en-US"
    if low in ("secondary",) or low.startswith(("fr", "french", "francais", "français")):
        return "fr-CA"
    if low.startswith(("es", "spanish", "espanol", "español")):
        return "es-US"
    if low.startswith(("pt", "portug")):
        return "pt-BR"
    if low.startswith(("de", "german", "deutsch")):
        return "de-DE"
    if low.startswith(("it", "ital")):
        return "it-IT"
    if low.startswith(("zh", "chin", "mandarin")):
        return "zh-CN"
    if low.startswith(("hi", "hindi")):
        return "hi-IN"
    if low.startswith(("ar", "arab")):
        return "ar-XA"
    if low.startswith(("ja", "japan")):
        return "ja-JP"
    if low.startswith(("ko", "korean")):
        return "ko-KR"
    m = re.match(r"^([a-zA-Z]{2,3})-([a-zA-Z0-9]{2,4})$", raw)
    if m:
        return f"{m.group(1).lower()}-{m.group(2).upper()}"
    return "en-US"

SPOKEN_LINES: dict[str, dict[str, str]] = {  # pragma: no cover
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
    "greeting_main": {
        "en-US": "Welcome to Telco. I can help with billing, technical support, or managing your account. To get started, could you tell me the phone number or account number associated with your service?",
        "fr-CA": "Bienvenue chez Telco. Je peux vous aider avec la facturation, le soutien technique ou la gestion de votre compte. Pour commencer, pourriez-vous m'indiquer le numéro de téléphone ou le numéro de compte associé à votre service?",
        "es-US": "Bienvenido a Telco. Puedo ayudarle con facturación, soporte técnico o la gestión de su cuenta. Para comenzar, ¿podría indicarme el número de teléfono o el número de cuenta asociado a su servicio?",
    },
    "recording_notice": {
        "en-US": "This call may be recorded for quality and training purposes.",
        "fr-CA": "Cet appel peut être enregistré à des fins de qualité et de formation.",
        "es-US": "Esta llamada puede ser grabada con fines de calidad y capacitación.",
    },
    "id_verification_otp": {
        "en-US": "For your security, I just sent a 6-digit code to that number — please read it back to me.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code à 6 chiffres à ce numéro — veuillez me le lire.",
        "es-US": "Por su seguridad, acabo de enviar un código de 6 dígitos a ese número; por favor léamelo.",
    },
    "id_verification_email_otp": {
        "en-US": "For your security, I just sent a 6-digit verification code to your backup email address on file — please read it back to me.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code de vérification à 6 chiffres à votre adresse courriel de secours au dossier — veuillez me le lire.",
        "es-US": "Por su seguridad, acabo de enviar un código de verificación de 6 dígitos a su correo electrónico de respaldo registrado; por favor léamelo.",
    },
    "id_verification_pin": {
        "en-US": "For your security, I'll need to verify your identity. Please enter the 4-digit PIN you set up.",
        "fr-CA": "Pour votre sécurité, je dois vérifier votre identité. Veuillez composer le NIP à 4 chiffres que vous avez configuré.",
        "es-US": "Por su seguridad, necesito verificar su identidad. Por favor ingrese el PIN de 4 dígitos que configuró.",
    },
    "live_agent_handoff": {
        "en-US": "I'll connect you to a representative who can help. Please hold.",
        "fr-CA": "Je vais vous mettre en communication avec un représentant qui pourra vous aider. Veuillez patienter.",
        "es-US": "Le comunicaré con un representante que pueda ayudarle. Por favor espere.",
    },
    "business_handoff": {
        "en-US": "To get you the best support for your business account, I'll transfer you to an agent. You'll need to use your phone keypad instead of talking to the virtual assistant. Just a moment while I connect you.",
        "fr-CA": "Pour vous offrir le meilleur soutien pour votre compte affaires, je vais vous transférer à un agent. Vous devrez utiliser le clavier de votre téléphone plutôt que de parler à l'assistant virtuel. Un instant pendant que je vous transfère.",
        "es-US": "Para brindarle la mejor asistencia con su cuenta comercial, le transferiré con un agente. Deberá usar el teclado de su teléfono en lugar de hablar con el asistente virtual. Un momento mientras le comunico.",
    },
    "payment_method_preamble": {
        "en-US": "For your security, please do not read your full card number or security code out loud; we only confirm the last four digits on file.",
        "fr-CA": "Pour votre sécurité, veuillez ne pas lire votre numéro de carte complet ni votre code de sécurité à haute voix; nous confirmons uniquement les quatre derniers chiffres au dossier.",
        "es-US": "Por su seguridad, no lea en voz alta el número completo de su tarjeta ni el código de seguridad; solo confirmamos los últimos cuatro dígitos registrados.",
    },
    "contract_cancellation_fee_disclosure": {
        "en-US": "Please note that cancelling or transferring your line ends any active term agreement, and any applicable early cancellation fee and prorated charges from your account terms will appear on your final statement.",
        "fr-CA": "Veuillez noter que l'annulation ou le transfert de votre ligne met fin à toute entente active, et que les frais de résiliation anticipée applicables ainsi que le solde calculé au prorata figureront sur votre dernière facture.",
        "es-US": "Tenga en cuenta que cancelar o transferir su línea finaliza cualquier contrato vigente, y cualquier cargo aplicable por cancelación anticipada y cargos prorrateados aparecerán en su estado de cuenta final.",
    },
    "refund_confirmation_pattern": {
        "en-US": "Your refund of $[amount] will appear on your next statement within [days] business days.",
        "fr-CA": "Votre remboursement de [amount] $ figurera sur votre prochain relevé d'ici [days] jours ouvrables.",
        "es-US": "Su reembolso de $[amount] aparecerá en su próximo estado de cuenta dentro de [days] días hábiles.",
    },
    "confirmation_number_line": {
        "en-US": "Your confirmation number is [ref].",
        "fr-CA": "Votre numéro de confirmation est le [ref].",
        "es-US": "Su número de confirmación es [ref].",
    },
    "empathy_protocol": {
        "en-US": "I'm very sorry to hear that you are facing challenges. I will ensure we handle your request with the utmost care.",
        "fr-CA": "Je suis vraiment désolé d'apprendre que vous rencontrez ces difficultés. Je veillerai à ce que nous traitions votre demande avec le plus grand soin.",
        "es-US": "Lamento mucho saber que está pasando por dificultades. Me aseguraré de que atendamos su solicitud con el mayor cuidado.",
    },
    "outage_active": {
        "en-US": "I see there's an active outage in your area. We're working on it. Would you like me to text you when it's restored?",
        "fr-CA": "Je constate qu'une panne est en cours dans votre secteur. Nous travaillons à la résoudre. Voulez-vous que je vous envoie un texto dès que le service sera rétabli?",
        "es-US": "Veo que hay una interrupción activa en su área. Estamos trabajando para resolverla. ¿Desea que le envíe un mensaje de texto cuando se restablezca el servicio?",
    },
    "outage_none_offer_sms": {
        "en-US": "There's no outage reported in your area. I can text step-by-step troubleshooting steps to your mobile — would you like that?",
        "fr-CA": "Aucune panne n'est signalée dans votre secteur. Je peux vous envoyer les étapes de dépannage par texto sur votre mobile — le souhaitez-vous?",
        "es-US": "No se reporta ninguna interrupción en su área. Puedo enviarle los pasos de resolución de problemas por mensaje de texto a su móvil — ¿le gustaría eso?",
    },
    "transfer_to_specialist": {
        "en-US": "I'll connect you to a billing specialist now — they'll have everything we've already discussed.",
        "fr-CA": "Je vous mets maintenant en communication avec un spécialiste de la facturation — il aura déjà tout ce dont nous avons discuté.",
        "es-US": "Le comunicaré ahora con un especialista de facturación; tendrá toda la información que ya conversamos.",
    },
    "service_alert_banner": {
        "en-US": "Please note: there is an active regional service advisory in parts of Montreal today.",
        "fr-CA": "Veuillez noter qu'un avis de service régional est actuellement en vigueur dans certains secteurs de Montréal.",
        "es-US": "Tenga en cuenta que hoy hay un aviso de servicio regional activo en partes de Montreal.",
    },
    "blocked_caller_deflection": {
        "en-US": "We're unable to complete this call from your current number. Please visit telco.example.com/support for assistance. Goodbye.",
        "fr-CA": "Nous ne sommes pas en mesure de traiter cet appel à partir de ce numéro. Veuillez consulter telco.example.com/support pour obtenir de l'aide. Au revoir.",
        "es-US": "No podemos completar esta llamada desde este número. Visite telco.example.com/support para recibir asistencia. Hasta luego.",
    },
    "malicious_closing": {
        "en-US": "I'm only able to assist with Telco telecommunications services and account requests. Thank you for calling, goodbye.",
        "fr-CA": "Je peux uniquement vous aider avec les services de télécommunications et les demandes de compte Telco. Merci de votre appel, au revoir.",
        "es-US": "Solo puedo ayudarle con servicios de telecomunicaciones y solicitudes de cuenta de Telco. Gracias por llamar, hasta luego.",
    },
}

def resolve_copy_locale(language: str | None) -> str:  # pragma: no cover
    """Pick one of the three primary supported copy locales."""
    loc = resolve_locale(language)
    if loc == "fr-CA":
        return "fr-CA"
    if loc == "es-US":
        return "es-US"
    return "en-US"

def spoken_line(key: str, language: str | None = "en-US", *args: object, **slots: object) -> str:  # pragma: no cover
    """Return the spoken template for key and language, formatting all placeholders."""
    locale = resolve_copy_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    if args and "ref" not in slots:
        slots["ref"] = args[0]
        slots["confirmation_number"] = args[0]
    for slot_name, slot_val in slots.items():
        if isinstance(slot_val, float) and slot_val.is_integer():
            val_str = str(int(slot_val))
        elif slot_name == "days" and isinstance(slot_val, (int, float, str)):
            try:
                val_str = str(int(float(slot_val)))
            except (ValueError, TypeError):
                val_str = str(slot_val)
        else:
            val_str = str(slot_val)
        template = template.replace(f"[{slot_name}]", val_str).replace(f"{{{slot_name}}}", val_str)
        if slot_name in ("ref", "confirmation_number"):
            template = template.replace("[ref]", val_str).replace("{ref}", val_str)
            template = template.replace("[confirmation_number]", val_str).replace("{confirmation_number}", val_str)
    return template

def build_language_sheet(locale: str, agent_name: str = "router") -> str:  # pragma: no cover
    """Generate dynamic language sheet containing localized rules and verbatim lines."""
    loc = resolve_locale(locale)
    lang_name = WORLD_LANGUAGE_NAMES.get(loc, loc)
    keys = AGENT_VERBATIM_KEYS.get(agent_name, AGENT_VERBATIM_KEYS["router"])

    lines = [
        LANGUAGE_SHEET_SENTINEL,
        f'<active_language_sheet locale="{loc}" language="{lang_name}">',
    ]

    if loc in ("en-US", "fr-CA", "es-US"):
        lines.append("### Required Disclosures & Spoken Lines (Emit Exact Wording):")
        for k in keys:
            line_text = spoken_line(k, loc)
            lines.append(f'- {k}: "{line_text}"')
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
    else:
        lines.append("### Canonical Templates:")
        for k in keys:
            line_text = spoken_line(k, "en-US")
            lines.append(f'- {k}: "{line_text}"')
        lines.append("")
        lines.append("### Mandatory Conversational Rules:")
        lines.append(
            f"1. Speak 100% natively and fluently in {lang_name} ({loc}), translating the canonical Telco disclosures faithfully into {lang_name} with zero English mixing."
        )
        lines.append(
            f'2. Pass language="{loc}" to tools; if a request cannot be completed accurately without language degradation, politely offer to connect a specialist via handover_to_person(reason="secondary_language_live_agent", language="{loc}").'
        )

    lines.append("</active_language_sheet>")
    return "\n".join(lines)

_RE_RELAY_ACTIVE_LANG = re.compile(  # pragma: no cover
    r"['\"]active_language['\"]\s*:\s*['\"]([a-zA-Z]{2}(?:-[a-zA-Z]{2})?)['\"]"
)

def _extract_relayed_active_language(llm_request: Any) -> str:  # pragma: no cover
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

_AMBIGUOUS_SINGLE_TOKENS: frozenset[str] = frozenset(  # pragma: no cover
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

_DP_CANADIAN_POSTAL_RE = re.compile(  # pragma: no cover
    r"\b[a-z]\d[a-z]\s*-?\s*\d[a-z]\d\b",
    re.IGNORECASE,
)

_DP_GERMAN_MARKERS = frozenset(  # pragma: no cover
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
    }
)

_DP_ITALIAN_MARKERS = frozenset(  # pragma: no cover
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

_DP_PORTUGUESE_MARKERS = frozenset(  # pragma: no cover
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
    }
)

_DP_QUEBEC_PLACE_TOKENS = frozenset(  # pragma: no cover
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

_DP_STREET_ADDRESS_TOKENS = frozenset(  # pragma: no cover
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

_DP_STREET_NUMBER_RE = re.compile(r"\b\d{1,5}\b")  # pragma: no cover

_ENGLISH_MARKERS = frozenset(  # pragma: no cover
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

_FRENCH_MARKERS = frozenset(  # pragma: no cover
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

_RE_EVENT_TAG = re.compile(  # pragma: no cover
    r"<event\b[^>]*>[\s\S]*?</event>|<event\b[^>]*/>",
    re.IGNORECASE,
)

_RE_STATE_UPDATE = re.compile(  # pragma: no cover
    r"<state_update\b[^>]*>[\s\S]*?</state_update>|<state_update\b[^>]*/>",
    re.IGNORECASE,
)

_SPANISH_MARKERS = frozenset(  # pragma: no cover
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

def detect_utterance_language(  # pragma: no cover
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
    raw = _RE_EVENT_TAG.sub("", _RE_STATE_UPDATE.sub("", raw)).strip()
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

_RE_QUOTED_AGENT_BLOCK = re.compile(  # pragma: no cover
    r"<<<BEGIN_QUOTED_AGENT_CONTENT>>>[\s\S]*?<<<END_QUOTED_AGENT_CONTENT>>>"
)

_RE_RELAY_PREFIX = re.compile(  # pragma: no cover
    r"^(?:For context|\s*\[[^\]]+\]\s*(?:said:|thought:|called tool |`[^`]*` tool returned result:))",
    re.IGNORECASE,
)

def _is_relay_or_quoted_part(txt: str) -> bool:  # pragma: no cover
    """Return True if txt is an ADK relay part, agent event, state update, or quoted content block."""
    s = txt.strip()
    if not s:
        return True
    if _RE_RELAY_PREFIX.match(s):
        return True
    cleaned = _RE_QUOTED_AGENT_BLOCK.sub("", s)
    cleaned = _RE_STATE_UPDATE.sub("", cleaned)
    cleaned = _RE_EVENT_TAG.sub("", cleaned).strip()
    if not cleaned:
        return True
    if _RE_RELAY_PREFIX.match(cleaned):
        return True
    return False

def extract_user_utterances(llm_request: Any) -> list[str]:  # pragma: no cover
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
                            sanitized = _RE_EVENT_TAG.sub("", _RE_STATE_UPDATE.sub("", _RE_QUOTED_AGENT_BLOCK.sub("", txt))).strip()
                            if sanitized:
                                utterances.append(sanitized)
            elif isinstance(getattr(item, "text", None), str):
                t = item.text.strip()
                if t and not _is_relay_or_quoted_part(t):
                    sanitized = _RE_EVENT_TAG.sub("", _RE_STATE_UPDATE.sub("", _RE_QUOTED_AGENT_BLOCK.sub("", t))).strip()
                    if sanitized:
                        utterances.append(sanitized)
    return utterances

def detect_active_call_language(state_dict: Any, llm_request: Any) -> str:  # pragma: no cover
    """Determine the active conversation language from state and user turns."""
    user_utterances = extract_user_utterances(llm_request)
    state_get = getattr(state_dict, "get", None)
    has_state = callable(state_get)

    is_locked = bool(state_dict.get("language_locked", False)) if has_state else False
    locked = (
        str(state_dict.get("language") or "").strip()
        if has_state
        else ""
    )
    if locked:
        locked = resolve_locale(locked)
    else:
        relayed = _extract_relayed_active_language(llm_request)
        if relayed:
            locked = relayed

    explicit_in_state = (
        str(state_dict.get("explicit_language_switch") or "").strip()
        if has_state
        else ""
    )
    if explicit_in_state:
        explicit_in_state = resolve_locale(explicit_in_state)

    if not user_utterances:
        if explicit_in_state:
            return explicit_in_state
        return locked if locked else "en-US"

    current = explicit_in_state or locked or "en-US"
    has_locked = is_locked or bool(locked and locked != "en-US") or bool(explicit_in_state)

    for idx, utt in enumerate(user_utterances):
        low = utt.lower()
        switch = _dp_match_explicit_switch(low)
        if switch:
            current = switch
            has_locked = True
            continue

        if has_locked or idx > 0:
            # Locked or mid-call: bare 2/digits or ambiguous tokens never flip language
            continue

        # Turn 1 (idx == 0) and not yet locked:
        raw = utt.strip()
        if re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?2(?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            current = "fr-CA"
            has_locked = True
        elif re.fullmatch(
            r"(?:\[?(?:dtmf|touch-?tone|keypad|option|choice|touche|user)?\s*[:#-]?\s*)?1(?:[.#*]|\]|\s)*",
            raw,
            re.IGNORECASE,
        ):
            current = "en-US"
            has_locked = True
        else:
            det = detect_utterance_language(
                utt, current_language=current, is_turn_1=True, language_locked=False
            )
            current = det
            has_locked = True

    return current

def extract_dtmf_digits(utterance: Any) -> str:  # pragma: no cover
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

def apply_language_prompt_filter(  # pragma: no cover
    callback_context: Any,
    llm_request: Any,
    agent_name: str = "router",
    update_state: bool = False,
) -> None:
    """Inject language rules and verbatim lines into system instruction in-place."""
    state = getattr(callback_context, "state", None)
    state_dict = state if callable(getattr(state, "get", None)) else {}
    locale = detect_active_call_language(state_dict, llm_request)
    sheet = build_language_sheet(locale, agent_name=agent_name)

    user_utterances = extract_user_utterances(llm_request)
    latest_utt = user_utterances[-1] if user_utterances else ""

    # Synchronize state when requested or when state already tracks turn/lock
    should_sync = update_state or (
        isinstance(state, dict)
        and ("turn_index" in state or "language_locked" in state or "dtmf_digits" in state)
    )
    if should_sync and hasattr(state, "__setitem__"):
        try:
            if latest_utt:
                state["turn_index"] = int(state.get("turn_index", 0)) + 1
                state["language"] = locale
                state["language_locked"] = True
                state["utterance"] = latest_utt
                state["last_user_utterance"] = latest_utt
                state["dtmf_digits"] = extract_dtmf_digits(latest_utt)
                switch = _dp_match_explicit_switch(latest_utt.lower())
                if switch:
                    state["explicit_language_switch"] = switch
            else:
                state["dtmf_digits"] = ""
                if not state.get("language"):
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
# --- END GENERATED SHARED BUNDLE ---
