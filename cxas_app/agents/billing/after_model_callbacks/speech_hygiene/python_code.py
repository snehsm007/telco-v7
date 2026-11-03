from __future__ import annotations

from types import SimpleNamespace
from typing import Optional


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Clean speech, mask long numbers, and ensure valid handover lines."""
    state = getattr(callback_context, "state", None)
    state_dict = state if callable(getattr(state, "get", None)) else {}
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if content is None or parts is None:
        return None

    changed = False
    called_tools: list[str] = []
    tool_args_list: list[dict] = []
    end_session_args: dict = {}
    spoken_indices: list[int] = []

    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc is not None:
            fc_name = str(getattr(fc, "name", "") or "")
            if fc_name:
                called_tools.append(fc_name)
            fc_args = getattr(fc, "args", None)
            if fc_args is not None:
                if fc_name in (
                    "handover_to_person",
                    "execute_live_agent_handover",
                ):
                    tool_args_list.append(dict(fc_args))
                elif fc_name == "end_session":
                    end_session_args = dict(fc_args)

    for idx, part in enumerate(parts):
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            spoken_indices.append(idx)
            cleaned = clean_agent_speech(text, state_dict)
            if cleaned != text:
                part.text = cleaned
                changed = True

    has_handover_tool = any(
        t in ("handover_to_person", "execute_live_agent_handover")
        for t in called_tools
    )
    if spoken_indices and has_handover_tool:
        last_idx = spoken_indices[-1]
        combined_text = " ".join(
            str(getattr(parts[i], "text", "") or "").strip() for i in spoken_indices
        ).strip()
        enforced_combined = enforce_handover_utterance(
            combined_text,
            state_dict,
            called_tools=called_tools,
            tool_args_list=tool_args_list,
        )
        if enforced_combined != combined_text:
            if len(spoken_indices) == 1:
                new_last = clean_agent_speech(enforced_combined, state_dict)
                if new_last != getattr(parts[last_idx], "text", None):
                    parts[last_idx].text = new_last
                    changed = True
            elif enforced_combined.startswith(combined_text):
                suffix = enforced_combined[len(combined_text) :].strip()
                base_last = str(getattr(parts[last_idx], "text", "") or "").rstrip()
                new_last = clean_agent_speech(
                    f"{base_last} {suffix}".strip() if suffix else base_last,
                    state_dict,
                )
                if new_last != getattr(parts[last_idx], "text", None):
                    parts[last_idx].text = new_last
                    changed = True
            else:
                first_idx = spoken_indices[0]
                new_first = clean_agent_speech(enforced_combined, state_dict)
                if new_first != getattr(parts[first_idx], "text", None):
                    parts[first_idx].text = new_first
                    changed = True
                for extra_idx in reversed(spoken_indices[1:]):
                    extra_part = parts[extra_idx]
                    if (
                        isinstance(parts, list)
                        and getattr(extra_part, "function_call", None) is None
                        and getattr(extra_part, "function_response", None) is None
                        and getattr(extra_part, "inline_data", None) is None
                    ):
                        parts.pop(extra_idx)
                    else:
                        extra_part.text = ""
                    changed = True

    if not spoken_indices:
        msg = enforce_handover_utterance(
            "",
            state_dict,
            called_tools=called_tools,
            tool_args_list=tool_args_list,
        ).strip()
        if not msg and "end_session" in called_tools and not has_handover_tool:
            reason = str(end_session_args.get("reason", "") or "").lower()
            lang = state_dict.get("language") or end_session_args.get("language")
            msg = enforce_closing_utterance(reason=reason, language=lang).strip()
        if msg and isinstance(parts, list):
            cleaned_msg = clean_agent_speech(msg, state_dict)
            if (
                parts
                and getattr(parts[0], "text", None) == ""
                and not getattr(parts[0], "function_call", None)
            ):
                parts.pop(0)
            _part_cls = globals().get("Part")
            new_part = (
                _part_cls.from_text(text=cleaned_msg)
                if _part_cls is not None and hasattr(_part_cls, "from_text")
                else SimpleNamespace(text=cleaned_msg)
            )
            parts.insert(0, new_part)
            changed = True

    return llm_response if changed else None


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.speech import clean_agent_speech, enforce_closing_utterance, enforce_handover_utterance
from pathlib import Path
from typing import Any
import re
import sys

_FALLBACK_LEAKAGE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (  # pragma: no cover
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

_LAST4_CONTEXT_RE = re.compile(  # pragma: no cover
    r"((?:ending\s+in|terminant\s+par|terminad?[oa]?\s+en|number\s+is|num[eé]ro\s+est|n[uú]mero\s+es)\s+)(\d{4})\b",
    re.IGNORECASE,
)

_SP_BANK_KWS: tuple[str, ...] = (  # pragma: no cover
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

_SP_CARD_KWS: tuple[str, ...] = (  # pragma: no cover
    "card",
    "carte",
    "tarjeta",
    "visa",
    "mastercard",
    "amex",
    "crédit",
    "credit",
)

_SP_EXPLICIT_BANK_KWS: tuple[str, ...] = (  # pragma: no cover
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

_SP_PHONE_KWS: tuple[str, ...] = (  # pragma: no cover
    "phone",
    "mobile",
    "cell",
    "téléphone",
    "cellulaire",
    "teléfono",
    "celular",
    "móvil",
)

def _sp_term_pos(segment: str, terms: tuple[str, ...]) -> int:  # pragma: no cover
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

NUMBER_RUN_RE = re.compile(r"\(?\d+\)?(?:[-.]\(?\d+\)?|\s\(?\d{3,}\)?)*")  # pragma: no cover

SPEAKABLE_NUMBERS: frozenset[str] = frozenset()  # pragma: no cover

def mask_long_numbers(text: str, min_digits: int = 9) -> str:  # pragma: no cover
    """Replace every number of min_digits or more digits by its last 4 digits."""

    def _mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < min_digits or digits in SPEAKABLE_NUMBERS:
            return match.group(0)
        return digits[-4:]

    return NUMBER_RUN_RE.sub(_mask, text)

MARKDOWN_RE = re.compile(  # pragma: no cover
    r"```[a-zA-Z0-9_-]*[ \t]*\n?|\*+|`+|^#+[ \t]*|^[ \t]*[-•][ \t]+",
    re.MULTILINE,
)

_SP_EVENT_TAG = re.compile(  # pragma: no cover
    r"<event\b[^>]*>[\s\S]*?</event>|<event\b[^>]*/>",
    re.IGNORECASE,
)

def strip_markdown(text: str) -> str:  # pragma: no cover
    """Drop markdown formatting characters and event tags from spoken text."""
    return MARKDOWN_RE.sub("", _SP_EVENT_TAG.sub("", text))

def clean_speech(text: str) -> str:  # pragma: no cover
    """Clean markdown formatting and long numbers from spoken text."""
    return mask_long_numbers(strip_markdown(text))

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

def resolve_copy_locale(language: str | None) -> str:  # pragma: no cover
    """Pick one of the three primary supported copy locales."""
    loc = resolve_locale(language)
    if loc == "fr-CA":
        return "fr-CA"
    if loc == "es-US":
        return "es-US"
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
        "en-US": "I just sent a 6-digit code to your mobile on file — please read it back to me out loud. You can also say your 4-digit account PIN instead.",
        "fr-CA": "Je viens d'envoyer un code à 6 chiffres à votre cellulaire au dossier — veuillez me le lire à haute voix. Vous pouvez aussi me dire votre NIP de compte à 4 chiffres.",
        "es-US": "Acabo de enviar un código de 6 dígitos a su móvil registrado — por favor léamelo en voz alta. También puede decirme su PIN de cuenta de 4 dígitos.",
    },
    "id_verification_email_otp": {
        "en-US": "For your security, I just sent a 6-digit verification code to your backup email address on file — please read it back to me.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code de vérification à 6 chiffres à votre adresse courriel de secours au dossier — veuillez me le lire.",
        "es-US": "Por su seguridad, acabo de enviar un código de verificación de 6 dígitos a su correo electrónico de respaldo registrado; por favor léamelo.",
    },
    "id_verification_pin": {
        "en-US": "For your security, I'll need to verify your identity. Please say your 4-digit account PIN out loud, or say 'text me a code' and I'll send a 6-digit code to your mobile on file.",
        "fr-CA": "Pour votre sécurité, je dois vérifier votre identité. Veuillez me dire votre NIP de compte à 4 chiffres à haute voix, ou dites « textez-moi un code » et j'enverrai un code à 6 chiffres à votre cellulaire au dossier.",
        "es-US": "Por su seguridad, necesito verificar su identidad. Por favor dígame su PIN de cuenta de 4 dígitos en voz alta, o diga 'envíeme un código' y le enviaré un código de 6 dígitos a su móvil registrado.",
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
    "no_input_reprompt": {
        "en-US": "I didn't hear anything. Could you please repeat that?",
        "fr-CA": "Je n'ai rien entendu. Pourriez-vous répéter s'il vous plaît?",
        "es-US": "No escuché nada. ¿Podría repetir por favor?",
    },
    "no_match_reprompt": {
        "en-US": "I'm sorry, I didn't catch that. Could you please rephrase your request?",
        "fr-CA": "Je m'excuse, je n'ai pas bien compris. Pourriez-vous reformuler votre demande s'il vous plaît?",
        "es-US": "Lo siento, no entendí bien. ¿Podría reformular su solicitud por favor?",
    },
    "tool_error_apology": {
        "en-US": "I apologize, our system is currently having trouble processing that request. Let me connect you with a representative who can assist.",
        "fr-CA": "Je m'excuse, notre système a actuellement de la difficulté à traiter cette demande. Laissez-moi vous mettre en communication avec un représentant qui pourra vous aider.",
        "es-US": "Le pido disculpas, nuestro sistema tiene problemas para procesar esa solicitud en este momento. Permítame comunicarle con un representante que pueda ayudarle.",
    },
    "keypad_recovery": {
        "en-US": "I'm sorry — the keypad entry didn't come through on my end. Please say the number out loud, one digit at a time.",
        "fr-CA": "Je m'excuse — la saisie au clavier n'a pas été captée de mon côté. Veuillez me dire le numéro à haute voix, un chiffre à la fois.",
        "es-US": "Lo siento, la marcación en el teclado no se registró de mi lado. Por favor diga el número en voz alta, un dígito a la vez.",
    },
    "guardrail_rephrase": {
        "en-US": "I apologize, could you please rephrase your request or share your account details so I can assist you?",
        "fr-CA": "Je vous présente mes excuses, pourriez-vous reformuler votre demande ou partager les détails de votre compte afin que je puisse vous aider ?",
        "es-US": "Le pido disculpas, ¿podría reformular su solicitud o compartir los detalles de su cuenta para que pueda ayudarle?",
    },
}

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

def clean_agent_speech(  # pragma: no cover
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

def enforce_closing_utterance(  # pragma: no cover
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

_SP_BIZ_TERMS: frozenset[str] = frozenset(  # pragma: no cover
    {"business", "entreprise", "affaires", "commercial", "comercial"}
)

_SP_FRAUD_TERMS: frozenset[str] = frozenset(  # pragma: no cover
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

_SP_HOLD_TAILS: tuple[str, ...] = (  # pragma: no cover
    "please hold",
    "veuillez patienter",
    "por favor espere",
)

_SP_SPECIALIST_TERMS: frozenset[str] = frozenset(  # pragma: no cover
    {
        "refund",
        "remboursement",
        "reembolso",
        "threshold",
        "specialist",
        "billing_specialist",
    }
)

def _norm_ws(s: str) -> str:  # pragma: no cover
    return " ".join(s.lower().split())

def enforce_handover_utterance(  # pragma: no cover
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
# --- END GENERATED SHARED BUNDLE ---
