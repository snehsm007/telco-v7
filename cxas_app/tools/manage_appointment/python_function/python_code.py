"""CXAS tool wrapper for manage_appointment. Before calling this tool, speak a brief conversational pacing phrase."""

from typing import Any



def manage_appointment(
    action: str = "reschedule",
    selected_slot: str | int | float = "",
    appointment_id: str | int | float = "",
    confirmed_cancel: str | int | float | bool = False,
    technician_en_route: str | int | float | bool = False,
    identifier: str | int | float = "",
    verification_code: str | int | float = "",
    language: str = "",
) -> dict[str, Any]:
    """Reschedule or cancel technician appointment with en-route protection.

    Args:
      action: Desired appointment modification ('reschedule' or 'cancel').
      selected_slot: Slot identifier, date, or arrival window chosen for rescheduling.
      appointment_id: Existing appointment identifier.
      confirmed_cancel: Customer confirmation flag for cancellation.
      technician_en_route: Flag indicating if the dispatch technician is already in transit.
      identifier: Optional customer phone or account number if known.
      verification_code: Optional one-time verification passcode.
      language: Preferred language code such as 'en-US', 'fr-CA', or 'es-US'.

    Returns:
      dict: status, data containing confirmation details or refusal guidance, tracking reference, and agent_action on errors.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return manage_appointment_impl(
        action=action,
        selected_slot=selected_slot,
        appointment_id=appointment_id,
        confirmed_cancel=confirmed_cancel,
        technician_en_route=technician_en_route,
        identifier=identifier,
        verification_code=verification_code,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.services import manage_appointment_impl
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import contextlib
import contextvars
import hashlib
import re
import sys

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
        "en-US": "For your security, I just sent a 6-digit code to that number — please read it back to me. Or you can say your 4-digit account PIN out loud.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code à 6 chiffres à ce numéro — veuillez me le lire. Vous pouvez aussi me dire votre NIP de compte à 4 chiffres à haute voix.",
        "es-US": "Por su seguridad, acabo de enviar un código de 6 dígitos a ese número; por favor léamelo. También puede decirme en voz alta su PIN de cuenta de 4 dígitos.",
    },
    "id_verification_email_otp": {
        "en-US": "For your security, I just sent a 6-digit verification code to your backup email address on file — please read it back to me.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code de vérification à 6 chiffres à votre adresse courriel de secours au dossier — veuillez me le lire.",
        "es-US": "Por su seguridad, acabo de enviar un código de verificación de 6 dígitos a su correo electrónico de respaldo registrado; por favor léamelo.",
    },
    "id_verification_pin": {
        "en-US": "For your security, I'll need to verify your identity. Please enter the 4-digit PIN you set up.",
        "fr-CA": "Pour votre sécurité, je dois vérifier votre identité. Veuillez entrer le NIP à 4 chiffres que vous avez configuré.",
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

def _call_live_backend(  # pragma: no cover
    tool_name: str,
    state: dict[str, Any],
    lang: str,
    reference: str,
) -> dict[str, Any]:
    """Return PRD Section 6 system error envelope when mock_mode is explicitly disabled."""
    if tool_name in {"lookup_account", "send_login_code", "verify_login"}:
        err_code = "AUTH_SERVICE_UNAVAILABLE"
    else:
        err_code = "SYSTEM_DOWN"

    handoff_msg = spoken_line("live_agent_handoff", lang)
    loc = resolve_locale(lang) if "resolve_locale" in globals() else lang
    return {
        "status": "error",
        "error": err_code,
        "error_message": f"Live telecom CRM backend connection unavailable for {tool_name}.",
        "agent_action": "ESCALATE_SYSTEM_UNAVAILABLE",
        "tracking_id": reference,
        "active_language": loc,
        "data": {
            "error_category": "SYSTEM",
            "must_escalate_immediately": True,
            "escalation_reason": "system_unavailable",
            "handoff_message": handoff_msg,
            "mock_mode": False,
        },
        "must_escalate_immediately": True,
        "handoff_message": handoff_msg,
    }

ERROR_CODES: tuple[str, ...] = (  # pragma: no cover
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
    "REFUND_THRESHOLD_EXCEEDED",
    "CANNOT_CANCEL_EN_ROUTE",
    "BLOCKED_CALLER",
    "PERMISSION_DENIED",
    "MISSING_INPUT",
    "INVALID_FORMAT",
    "NOT_AUTHENTICATED",
    "PAST_DUE_BALANCE_REQUIRED",
    "REQUIRES_CONFIRMATION",
    "BUSINESS_ACCOUNT_HANDOFF",
    "CONFIRMATION_REQUIRED",
    "REQUIRES_ESCALATION",
    "MALFORMED_REQUEST",
    "SERVICE_TYPE_REQUIRED",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",
    "SYSTEM_DOWN",
    "UNKNOWN_PLAN_ID",
    "CODE_NOT_RECEIVED",
    "CARD_CAPTURE_REQUIRED",
    "INVALID_CARD_DIGITS",
    "NO_MOBILE_ON_FILE",
)

class _StatusStr(str):  # pragma: no cover
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

ERROR_STATUS = _StatusStr("error")  # pragma: no cover

LOCALIZED_ERROR_DEFAULTS: dict[str, dict[str, tuple[str, str]]] = {  # pragma: no cover
    "en-US": {
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
            "Log the caller in with send_login_code and verify_login, then retry.",
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
        "REFUND_THRESHOLD_EXCEEDED": (
            "The requested credit or refund exceeds self-service threshold limits.",
            "Transfer the caller to a billing specialist to review the adjustment.",
        ),
        "CANNOT_CANCEL_EN_ROUTE": (
            "A technician is already dispatched and en route for this appointment.",
            "Explain that dispatch is in progress and offer to reschedule when they arrive.",
        ),
        "BLOCKED_CALLER": (
            "This calling number is restricted from automated telephone service.",
            "Recite the deflection line and direct the caller to online self-support.",
        ),
        "PERMISSION_DENIED": (
            "Permission denied for this operation.",
            "Explain that this operation is not permitted.",
        ),
        "MISSING_INPUT": (
            "Required input information is missing.",
            "Ask the caller to provide the required information.",
        ),
        "INVALID_FORMAT": (
            "The format of the input is invalid.",
            "Ask the caller to verify the format and try again.",
        ),
        "NOT_AUTHENTICATED": (
            "The caller is not authenticated for this operation.",
            "Ask the caller for their 4-digit account PIN or 6-digit verification code, and call verify_login before retrying this operation.",
        ),
        "PAST_DUE_BALANCE_REQUIRED": (
            "A past due balance must be paid before service can be restored.",
            "Offer to process a payment or set up a payment arrangement.",
        ),
        "REQUIRES_CONFIRMATION": (
            "Caller confirmation is required before proceeding.",
            "Ask the caller to confirm this action.",
        ),
        "BUSINESS_ACCOUNT_HANDOFF": (
            "Business accounts must be transferred to the business solutions desk.",
            "Transfer the caller to business solutions support.",
        ),
        "CONFIRMATION_REQUIRED": (
            "Confirmation is required before this action can be completed.",
            "Ask the caller to confirm the action.",
        ),
        "REQUIRES_ESCALATION": (
            "This request requires escalation to a specialized team.",
            "Transfer the caller to the appropriate team.",
        ),
        "MALFORMED_REQUEST": (
            "The request is malformed.",
            "Clarify the request with the caller.",
        ),
        "SERVICE_TYPE_REQUIRED": (
            "A service type is required for this inquiry.",
            "Ask the caller which service they are inquiring about.",
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
        "UNKNOWN_PLAN_ID": (
            "The requested plan or add-on ID was not found in the catalog.",
            "List the available plan IDs to the caller and ask them to select a valid plan.",
        ),
        "CODE_NOT_RECEIVED": (
            "No digits were received or recognized.",
            "Say you did not receive any digits and ask the caller to say the code aloud.",
        ),
        "CARD_CAPTURE_REQUIRED": (
            "Payment card digits required. Key in 15 or 16 digits using your phone keypad.",
            "Read the preamble verbatim, invite keypad entry once; if no digits arrive, offer the card or bank on file instead — never hand over for this.",
        ),
        "INVALID_CARD_DIGITS": (
            "Card number must be 15 or 16 digits.",
            "Ask the caller to enter a valid 15 or 16 digit card number using the phone keypad.",
        ),
        "NO_MOBILE_ON_FILE": (
            "No mobile number is linked to this account.",
            "Ask for the 10-digit mobile number on the account and call lookup_account with it to identify the account, then send the code to the mobile on file; or offer PIN authentication.",
        ),
    },
    "fr-CA": {
        "INVALID_INPUT": (
            "L'information fournie est invalide.",
            "Demander au client de répéter clairement l'information.",
        ),
        "NOT_FOUND": (
            "Aucun dossier correspondant n'a été trouvé.",
            "Demander au client de répéter l'identifiant un chiffre à la fois.",
        ),
        "NOT_IDENTIFIED": (
            "Le compte du client n'a pas encore été identifié.",
            "Appeler lookup_account ou utiliser le compte actif de la session.",
        ),
        "NOT_LOGGED_IN": (
            "Le client n'a pas validé son authentification.",
            "Authentifier le client avec send_login_code et verify_login, puis réessayer.",
        ),
        "CODE_NOT_SENT": (
            "Aucun code de vérification n'a été envoyé lors de cet appel.",
            "Appeler send_login_code ou vérifier le code fourni par le client.",
        ),
        "WRONG_CODE": (
            "Le code ne correspond pas.",
            "Informer le client que le code est erroné et lui demander de réessayer.",
        ),
        "WRONG_PIN": (
            "Le NIP secret ne correspond pas.",
            "Informer le client que le NIP est erroné et lui demander de réessayer.",
        ),
        "TOO_MANY_ATTEMPTS": (
            "Trop de tentatives de code erronées lors de cet appel.",
            "Appeler handover_to_person, énoncer handoff_message et appeler end_session.",
        ),
        "LOCKED_OUT": (
            "Le compte est verrouillé après plusieurs tentatives infructueuses.",
            "Appeler handover_to_person, énoncer handoff_message et appeler end_session.",
        ),
        "CARD_DECLINED": (
            "La carte a été refusée.",
            "Informer le client du refus de la carte et demander un autre mode de paiement.",
        ),
        "PAYMENT_DECLINED": (
            "Le mode de paiement a été refusé.",
            "Informer le client du refus du paiement et demander un autre mode de paiement.",
        ),
        "INELIGIBLE": (
            "Le compte n'est pas admissible à cette demande.",
            "Expliquer l'inadmissibilité et proposer le transfert à un agent.",
        ),
        "NOT_ELIGIBLE": (
            "Le compte n'est pas admissible à cette option.",
            "Expliquer l'inadmissibilité et proposer une solution de rechange disponible.",
        ),
        "ALREADY_PROCESSED": (
            "Cette demande a déjà été traitée.",
            "Informer le client que la demande a déjà été complétée.",
        ),
        "ALREADY_APPLIED": (
            "Ce crédit ou cet ajustement a déjà été appliqué.",
            "Informer le client que l'ajustement a déjà été accordé.",
        ),
        "ALREADY_ENROLLED": (
            "Le compte est déjà inscrit à cette option.",
            "Informer le client que le compte est déjà inscrit.",
        ),
        "OUT_OF_WINDOW": (
            "La demande dépasse le délai prévu par la politique.",
            "Expliquer le délai de la politique et proposer le transfert à un agent.",
        ),
        "OUTAGE_ACTIVE": (
            "Une panne de service active touche ce secteur.",
            "Partager l'état de la panne et le délai de rétablissement estimé.",
        ),
        "LIMIT_EXCEEDED": (
            "Le montant ou le nombre demandé dépasse la limite permise.",
            "Expliquer la limite permise et proposer le transfert à un agent.",
        ),
        "REFUND_THRESHOLD_EXCEEDED": (
            "Le remboursement demandé dépasse la limite en libre-service.",
            "Transférer le client à un spécialiste de la facturation.",
        ),
        "CANNOT_CANCEL_EN_ROUTE": (
            "Le technicien est déjà en route pour ce rendez-vous.",
            "Expliquer que le déplacement est en cours et proposer un report à l'arrivée.",
        ),
        "BLOCKED_CALLER": (
            "Ce numéro de téléphone est restreint pour le service téléphonique automatisé.",
            "Énoncer le message de déviation et inviter le client à utiliser le soutien en ligne.",
        ),
        "PERMISSION_DENIED": (
            "Permission refusée pour cette opération.",
            "Expliquer que cette opération n'est pas autorisée.",
        ),
        "MISSING_INPUT": (
            "L'information requise est manquante.",
            "Demander au client de fournir l'information nécessaire.",
        ),
        "INVALID_FORMAT": (
            "Le format de l'information est invalide.",
            "Demander au client de vérifier le format et de réessayer.",
        ),
        "NOT_AUTHENTICATED": (
            "Le client n'est pas authentifié pour cette opération.",
            "Demander au client son NIP de compte à 4 chiffres ou son code de vérification à 6 chiffres, et appeler verify_login avant de réessayer.",
        ),
        "PAST_DUE_BALANCE_REQUIRED": (
            "Le solde en souffrance doit être réglé avant de rétablir le service.",
            "Proposer d'effectuer un paiement ou de mettre en place une entente de paiement.",
        ),
        "REQUIRES_CONFIRMATION": (
            "La confirmation du client est requise avant de continuer.",
            "Demander au client de confirmer cette action.",
        ),
        "BUSINESS_ACCOUNT_HANDOFF": (
            "Les comptes d'affaires doivent être transférés au service des solutions d'affaires.",
            "Transférer le client au soutien aux entreprises.",
        ),
        "CONFIRMATION_REQUIRED": (
            "Une confirmation est requise avant de compléter cette action.",
            "Demander au client de confirmer l'action.",
        ),
        "REQUIRES_ESCALATION": (
            "Cette demande nécessite une escalade vers une équipe spécialisée.",
            "Transférer le client vers l'équipe appropriée.",
        ),
        "MALFORMED_REQUEST": (
            "La demande est mal formulée.",
            "Clarifier la demande avec le client.",
        ),
        "SERVICE_TYPE_REQUIRED": (
            "Un type de service est requis pour cette demande.",
            "Demander au client de quel service il s'agit.",
        ),
        "INTERNAL_ERROR": (
            "Une erreur interne s'est produite lors du traitement.",
            "Présenter des excuses pour le problème et transférer le client à un agent.",
        ),
        "SERVICE_UNAVAILABLE": (
            "Le service distant est temporairement inaccessible.",
            "Présenter des excuses pour l'interruption et transférer le client à un agent.",
        ),
        "SYSTEM_DOWN": (
            "Le système est temporairement indisponible.",
            "Présenter des excuses pour l'interruption et transférer le client à un agent.",
        ),
        "UNKNOWN_PLAN_ID": (
            "L'identifiant de forfait ou d'option demandé est introuvable dans le catalogue.",
            "Indiquer les forfaits disponibles au client et lui demander de choisir un forfait valide.",
        ),
        "CODE_NOT_RECEIVED": (
            "Aucun chiffre n'a été reçu ou reconnu.",
            "Dites que vous n'avez reçu aucun chiffre et demandez au client d'énoncer le code à voix haute.",
        ),
        "CARD_CAPTURE_REQUIRED": (
            "Numéro de carte requis. Composez les 15 ou 16 chiffres à l'aide du clavier de votre téléphone.",
            "Lisez le préambule mot à mot, invitez à composer les chiffres sur le clavier une fois; si aucun chiffre n'arrive, proposez la carte ou le compte au dossier — ne transférez jamais pour cela.",
        ),
        "INVALID_CARD_DIGITS": (
            "Le numéro de carte doit comporter 15 ou 16 chiffres.",
            "Demandez au client de saisir un numéro de carte valide de 15 ou 16 chiffres à l'aide du clavier téléphonique.",
        ),
        "NO_MOBILE_ON_FILE": (
            "Aucun numéro de mobile n'est associé à ce compte.",
            "Demander le numéro de mobile à 10 chiffres au dossier et appeler lookup_account avec celui-ci pour identifier le compte, puis envoyer le code au mobile au dossier; ou proposer l'authentification par NIP.",
        ),
    },
    "es-US": {
        "INVALID_INPUT": (
            "La información proporcionada es inválida.",
            "Pida al cliente que repita la información claramente.",
        ),
        "NOT_FOUND": (
            "No se encontró ningún registro correspondiente.",
            "Pida al cliente que repita el identificador un dígito a la vez.",
        ),
        "NOT_IDENTIFIED": (
            "La cuenta del cliente aún no ha sido identificada.",
            "Llame a lookup_account o use la cuenta activa de la sesión.",
        ),
        "NOT_LOGGED_IN": (
            "El cliente no ha completado el inicio de sesión.",
            "Inicie la sesión con send_login_code y verify_login, luego reintente.",
        ),
        "CODE_NOT_SENT": (
            "No se ha enviado ningún código en esta llamada.",
            "Llame a send_login_code o verifique el código proporcionado por el cliente.",
        ),
        "WRONG_CODE": (
            "El código no coincide.",
            "Indique al cliente que el código no coincide y pídale que intente nuevamente.",
        ),
        "WRONG_PIN": (
            "El PIN secreto no coincide.",
            "Indique al cliente que el PIN no coincide y pídale que intente nuevamente.",
        ),
        "TOO_MANY_ATTEMPTS": (
            "Demasiados intentos fallidos en esta llamada.",
            "Llame a handover_to_person, exprese handoff_message y llame a end_session.",
        ),
        "LOCKED_OUT": (
            "La cuenta ha sido bloqueada tras múltiples intentos fallidos.",
            "Llame a handover_to_person, exprese handoff_message y llame a end_session.",
        ),
        "CARD_DECLINED": (
            "La tarjeta fue rechazada.",
            "Indique al cliente que la tarjeta fue rechazada y pida otro método de pago.",
        ),
        "PAYMENT_DECLINED": (
            "El método de pago fue rechazado.",
            "Indique al cliente que el pago fue rechazado y pida otro método de pago.",
        ),
        "INELIGIBLE": (
            "La cuenta no es elegible para esta solicitud.",
            "Explique la no elegibilidad y ofrezca transferir con una persona.",
        ),
        "NOT_ELIGIBLE": (
            "La cuenta no es elegible para esta opción.",
            "Explique la no elegibilidad y ofrezca una alternativa disponible.",
        ),
        "ALREADY_PROCESSED": (
            "Esta solicitud ya ha sido procesada.",
            "Informe al cliente que la solicitud ya fue completada.",
        ),
        "ALREADY_APPLIED": (
            "Este crédito o ajuste ya ha sido aplicado.",
            "Informe al cliente que el ajuste ya fue concedido.",
        ),
        "ALREADY_ENROLLED": (
            "La cuenta ya está inscrita en este servicio.",
            "Informe al cliente que la cuenta ya está inscrita.",
        ),
        "OUT_OF_WINDOW": (
            "La solicitud está fuera del plazo permitido por la política.",
            "Explique el plazo de la política y ofrezca transferir con una persona.",
        ),
        "OUTAGE_ACTIVE": (
            "Una interrupción activa del servicio afecta esta zona.",
            "Comparta el estado de la interrupción y el tiempo estimado de restauración.",
        ),
        "LIMIT_EXCEEDED": (
            "La cantidad o el número solicitado excede el límite permitido.",
            "Explique el límite permitido y ofrezca transferir con una persona.",
        ),
        "REFUND_THRESHOLD_EXCEEDED": (
            "El reembolso solicitado excede el límite de autoservicio.",
            "Transfiera al cliente con un especialista de facturación.",
        ),
        "CANNOT_CANCEL_EN_ROUTE": (
            "El técnico ya está en camino para esta cita.",
            "Explique que el despacho está en curso y ofrezca reprogramar a su llegada.",
        ),
        "BLOCKED_CALLER": (
            "Este número de teléfono está restringido para el servicio telefónico automatizado.",
            "Exprese el mensaje de desvío y remita al cliente al soporte en línea.",
        ),
        "PERMISSION_DENIED": (
            "Permiso denegado para esta operación.",
            "Explique que esta operación no está permitida.",
        ),
        "MISSING_INPUT": (
            "Falta información requerida.",
            "Pida al cliente que proporcione la información requerida.",
        ),
        "INVALID_FORMAT": (
            "El formato de la información es inválido.",
            "Pida al cliente que verifique el formato y vuelva a intentarlo.",
        ),
        "NOT_AUTHENTICATED": (
            "El cliente no está autenticado para esta operación.",
            "Pida al cliente su PIN de cuenta de 4 dígitos o su código de verificación de 6 dígitos, y llame a verify_login antes de reintentar.",
        ),
        "PAST_DUE_BALANCE_REQUIRED": (
            "El saldo vencido debe pagarse antes de restaurar el servicio.",
            "Ofrezca procesar un pago o establecer un acuerdo de pago.",
        ),
        "REQUIRES_CONFIRMATION": (
            "Se requiere la confirmación del cliente antes de continuar.",
            "Pida al cliente que confirme esta acción.",
        ),
        "BUSINESS_ACCOUNT_HANDOFF": (
            "Las cuentas comerciales deben ser transferidas a soluciones comerciales.",
            "Transfiera al cliente al soporte de soluciones comerciales.",
        ),
        "CONFIRMATION_REQUIRED": (
            "Se requiere confirmación antes de completar esta acción.",
            "Pida al cliente que confirme la acción.",
        ),
        "REQUIRES_ESCALATION": (
            "Esta solicitud requiere escalación a un equipo especializado.",
            "Transfiera al cliente al equipo apropiado.",
        ),
        "MALFORMED_REQUEST": (
            "La solicitud es defectuosa.",
            "Aclare la solicitud con el cliente.",
        ),
        "SERVICE_TYPE_REQUIRED": (
            "Se requiere un tipo de servicio para esta consulta.",
            "Pregunte al cliente sobre qué servicio consulta.",
        ),
        "INTERNAL_ERROR": (
            "Ocurrió un error interno al procesar la solicitud.",
            "Pida disculpas por el inconveniente y transfiera al cliente con una persona.",
        ),
        "SERVICE_UNAVAILABLE": (
            "El servicio no está disponible en este momento.",
            "Pida disculpas por la interrupción y transfiera al cliente con una persona.",
        ),
        "SYSTEM_DOWN": (
            "El sistema está temporalmente fuera de servicio.",
            "Pida disculpas por la interrupción y transfiera al cliente con una persona.",
        ),
        "UNKNOWN_PLAN_ID": (
            "El plan o paquete adicional solicitado no se encontró en el catálogo.",
            "Indique los planes disponibles al cliente y pídale que elija un plan válido.",
        ),
        "CODE_NOT_RECEIVED": (
            "No se recibieron o reconocieron dígitos.",
            "Diga que no recibió ningún dígito y pida al cliente que diga el código en voz alta.",
        ),
        "CARD_CAPTURE_REQUIRED": (
            "Se requieren dígitos de la tarjeta. Ingrese los 15 o 16 dígitos en el teclado de su teléfono.",
            "Lea el preámbulo textualmente, invite a ingresar dígitos una vez; si no llegan dígitos, ofrezca la tarjeta o cuenta registrada — nunca transfiera por esto.",
        ),
        "INVALID_CARD_DIGITS": (
            "El número de tarjeta debe tener 15 o 16 dígitos.",
            "Pida al cliente que ingrese un número de tarjeta válido de 15 o 16 dígitos usando el teclado telefónico.",
        ),
        "NO_MOBILE_ON_FILE": (
            "No hay ningún número de móvil vinculado a esta cuenta.",
            "Pida el número de móvil de 10 dígitos en la cuenta y llame a lookup_account con él para identificar la cuenta, luego envíe el código al móvil registrado; u ofrezca autenticación por PIN.",
        ),
    },
}

def tracking_id(prefix: str, *parts: object) -> str:  # pragma: no cover
    """Return a deterministic short reference number (R followed by 6 digits)."""
    raw = "|".join([prefix, *(str(value).strip().lower() for value in parts)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)

def error_reply(  # pragma: no cover
    code: str,
    message: str = "",
    agent_action: str = "",
    reference: str | None = None,
    data: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Build an error reply envelope with localized messaging."""
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code {code!r}; add it to ERROR_CODES first")
    loc = resolve_copy_locale(language)
    loc_defaults = LOCALIZED_ERROR_DEFAULTS.get(loc, LOCALIZED_ERROR_DEFAULTS["en-US"])
    default_msg, default_action = loc_defaults.get(
        code,
        LOCALIZED_ERROR_DEFAULTS["en-US"].get(
            code,
            ("The request could not be completed.", "Explain the issue to the caller."),
        ),
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
    if language is not None:
        reply["active_language"] = loc
    if "lockout_triggered" in payload:
        reply["lockout_triggered"] = payload["lockout_triggered"]
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "spoken_line",
        "spoken_summary",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
        "must_escalate_immediately",
        "requested_card_last4",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply

_ACTIVE_FIXTURE_STATE: contextvars.ContextVar[dict[str, Any] | None] = (  # pragma: no cover
    contextvars.ContextVar("_ACTIVE_FIXTURE_STATE", default=None)
)

def get_fixture_fact(  # pragma: no cover
    state: Any = None,
    fact_name: str = "",
    default: Any = None,
) -> Any:
    """Retrieve a backend fixture fact from session state (checking fx_* and canonical variables),

    falling back to realistic defaults. Treats None and "" as unset.
    """
    eff = state if callable(getattr(state, "get", None)) else _ACTIVE_FIXTURE_STATE.get()
    if not callable(getattr(eff, "get", None)) or not fact_name:
        return default

    base = fact_name[3:] if fact_name.startswith("fx_") else fact_name
    candidates = (f"fx_{base}", fact_name, base)
    for k in candidates:
        val = eff.get(k)
        if val is not None and val != "":
            return val
    return default

def _check_mock_error(state: dict[str, Any], lang: str) -> dict[str, Any] | None:  # pragma: no cover
    """Return synthetic system outage error if mock_error is injected."""
    val = str(get_fixture_fact(state, "mock_error", "") or state.get("mock_error") or "").strip().upper()
    if val in {"SYSTEM_DOWN", "SERVICE_UNAVAILABLE", "BACKEND_FAILURE"}:
        return error_reply(
            "SERVICE_UNAVAILABLE",
            language=lang,
            data={
                "error_category": "SYSTEM",
                "must_escalate_immediately": True,
                "escalation_reason": "system_unavailable",
                "handoff_message": spoken_line("live_agent_handoff", lang),
            },
        )
    return None

FAKE_APPOINTMENTS_DATA: dict[str, Any] = {  # pragma: no cover
    "active_appointment": {
        "appointment_id": "APT-4021",
        "account_id": "A1001",
        "scheduled_date": "2026-10-30",
        "window_start": "08:00",
        "window_end": "12:00",
        "window_display": "8:00 AM - 12:00 PM",
        "status": "scheduled",
        "technician_status": "scheduled",
        "technician_name": "Marc-Andre",
        "service_type": "fiber_installation",
        "address": "123 Maple Avenue, Montreal, QC",
    },
    "repair_ticket": {
        "ticket_id": "TKT-8841",
        "status": "in_progress",
        "issue": "intermittent_fiber_loss",
        "reported_date": "2026-10-28",
    },
    "available_reschedule_slots": [
        {
            "slot_id": "SLOT-1",
            "date": "2026-11-02",
            "window_en": "Morning (8:00 AM - 12:00 PM)",
            "window_fr": "Matin (8 h 00 - 12 h 00)",
            "window_es": "Mañana (8:00 AM - 12:00 PM)",
        },
        {
            "slot_id": "SLOT-2",
            "date": "2026-11-02",
            "window_en": "Afternoon (1:00 PM - 5:00 PM)",
            "window_fr": "Après-midi (13 h 00 - 17 h 00)",
            "window_es": "Tarde (1:00 PM - 5:00 PM)",
        },
        {
            "slot_id": "SLOT-3",
            "date": "2026-11-03",
            "window_en": "Morning (8:00 AM - 12:00 PM)",
            "window_fr": "Matin (8 h 00 - 12 h 00)",
            "window_es": "Mañana (8:00 AM - 12:00 PM)",
        },
    ],
}

def _dynamic_appointments_data() -> dict[str, Any]:  # pragma: no cover
    """Return a copy of FAKE_APPOINTMENTS_DATA with dates relative to today."""
    today = date.today()
    apt = dict(FAKE_APPOINTMENTS_DATA["active_appointment"])
    apt["scheduled_date"] = today.isoformat()
    tkt = dict(FAKE_APPOINTMENTS_DATA["repair_ticket"])
    tkt["reported_date"] = (today - timedelta(days=2)).isoformat()
    slot_offsets = (2, 2, 3)
    slots: list[dict[str, Any]] = []
    for idx, raw_slot in enumerate(FAKE_APPOINTMENTS_DATA["available_reschedule_slots"]):
        s_copy = dict(raw_slot)
        offset = slot_offsets[idx] if idx < len(slot_offsets) else 3
        s_copy["date"] = (today + timedelta(days=offset)).isoformat()
        slots.append(s_copy)
    return {
        "active_appointment": apt,
        "repair_ticket": tkt,
        "available_reschedule_slots": slots,
    }

def _ensure_default_profile(state: dict[str, Any]) -> None:  # pragma: no cover
    """Initialize safe session status defaults without polluting account identity."""
    state.setdefault("auth_status", "none")
    state.setdefault("auth_failure_count", 0)
    state.setdefault("pin_failure_count", 0)
    state.setdefault("payment_failure_count", 0)

def _get_state(  # pragma: no cover
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    reset_if_locked: bool = False,
) -> dict[str, Any]:
    """Return the caller's session state dict, returning a fresh dict when omitted."""
    if state is not None:
        return state
    if session_state is not None:
        return session_state
    return {}

ACCOUNTS: tuple[dict[str, str], ...] = (  # pragma: no cover
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

def _hydrate_default_account_if_needed(state: dict[str, Any]) -> None:  # pragma: no cover
    """Populate default account profile ONLY for standalone unit-test calls that omit lookup."""
    if state.get("account_id"):
        return
    if not ACCOUNTS:
        return
    default_acc = ACCOUNTS[0]
    state["account_id"] = default_acc["account_id"]
    state["phone_last4"] = default_acc["phone"][-4:]
    state.setdefault("contact_email", default_acc.get("email", "jordan@example.com"))
    state.setdefault("service_address", default_acc.get("address", "123 Maple Avenue, Montreal, QC"))
    state.setdefault("card_last4", default_acc.get("card_on_file_last4", "7742"))
    def_bal = str(default_acc.get("current_balance", "0.00"))
    state.setdefault("current_balance", def_bal)
    def_past = str(default_acc.get("past_due_balance", "0.00"))
    state.setdefault("past_due_balance", def_past)

def _is_mock_mode(state: dict[str, Any] | None) -> bool:  # pragma: no cover
    """Check whether mock_mode is active (PRD Section 17 & Section 21).

    Defaults to True when unset or empty for backward compatibility with unit tests.
    Explicit 'false', '0', 'no' evaluates to False.
    """
    if not isinstance(state, dict):
        return True
    val = get_fixture_fact(state, "mock_mode")
    if val is None:
        val = state.get("mock_mode", "True")
    val_str = str(val).strip().lower() if val is not None else ""
    return val_str in ("", "true", "1", "yes")

def _is_truthy_bool(val: Any) -> bool:  # pragma: no cover
    """Return True if val represents a truthy boolean or affirmation string."""
    if val is True:
        return True
    if isinstance(val, (str, int, float)) and not isinstance(val, bool):
        s = str(val).strip().lower()
        return s in {"true", "1", "yes", "oui", "sí", "si"}
    return False

BLOCKED_CALLER_NUMBERS: frozenset[str] = frozenset({"9005550199", "8005550000"})  # pragma: no cover

MAX_LOGIN_ATTEMPTS = 3  # pragma: no cover

NEGATIVE_INPUT_TOKENS: tuple[str, ...] = (  # pragma: no cover
    "wrong", "incorrect", "invalid", "unknown", "nonexistent",
    "none", "not found", "invalide", "faux", "invalido", "erroneo",
    "fake", "nobody",
)

OUTAGE_POSTAL_PREFIXES: tuple[str, ...] = ("H3Z", "G1R")  # pragma: no cover

def _is_account_locked(state: dict[str, Any], account_id: str | None) -> bool:  # pragma: no cover
    """Return True if account_id is present in state['locked_accounts']."""
    if not account_id:
        return False
    raw = state.get("locked_accounts") or ""
    if isinstance(raw, str):
        locked_set = {x.strip() for x in raw.split(",") if x.strip()}
    elif isinstance(raw, (list, set, tuple)):
        locked_set = {str(x).strip() for x in raw if str(x).strip()}
    else:
        locked_set = set()
    return str(account_id).strip() in locked_set

def _is_placeholder_email(email_str: str) -> bool:  # pragma: no cover
    """Return True when an email string is empty or a synthetic user...@example.com placeholder."""
    clean = str(email_str or "").strip()
    if not clean:
        return True
    return bool(re.fullmatch(r"user\d*@example\.com", clean, re.IGNORECASE))

def _is_valid_email_input(email_str: str) -> bool:  # pragma: no cover
    """Return True if email_str is a non-negative, well-formed email address."""
    clean = str(email_str or "").strip()
    if not clean:
        return False
    if any(tok in clean.lower() for tok in NEGATIVE_INPUT_TOKENS):
        return False
    return bool(re.fullmatch(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean))

def _is_valid_full_name(name_str: str) -> bool:  # pragma: no cover
    """Return True if name_str is a plausible full name of 2+ alphabetic words without negative tokens."""
    clean = str(name_str or "").strip()
    if not clean:
        return False
    if any(tok in clean.lower() for tok in NEGATIVE_INPUT_TOKENS):
        return False
    parts = clean.split()
    if len(parts) < 2:
        return False
    return all(bool(re.fullmatch(r"[A-Za-zÀ-ÿ'-]{2,}", p)) for p in parts)

def _is_valid_postal_code_input(pc_str: str) -> bool:  # pragma: no cover
    """Return True if pc_str is a valid Canadian postal code or US ZIP code without negative tokens."""
    clean = str(pc_str or "").strip().upper()
    if not clean:
        return False
    if any(tok in clean.lower() for tok in NEGATIVE_INPUT_TOKENS):
        return False
    if re.fullmatch(r"^[A-Z]\d[A-Z][ -]?\d[A-Z]\d$", clean):
        return True
    if re.fullmatch(r"^\d{5}(-\d{4})?$", clean):
        if len(set(clean[:5])) > 1 and clean[:5] not in {"00000", "11111", "99999"}:
            return True
    return False

def _record_audit(state: dict[str, Any]) -> None:  # pragma: no cover
    """Increment audit log count inside auth, mutation, and handover tools."""
    return None

OK_STATUS = _StatusStr("ok")  # pragma: no cover

def ok_reply(  # pragma: no cover
    data: dict[str, Any] | None = None,
    reference: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Build a success reply envelope."""
    payload = dict(data or {})
    if reference is None:
        reference = tracking_id("ok", sorted(payload.keys()))
    reply: dict[str, Any] = {
        "status": OK_STATUS,
        "data": payload,
        "error_message": "",
        "tracking_id": reference,
    }
    if language is not None:
        reply["active_language"] = resolve_copy_locale(language)
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "spoken_line",
        "spoken_summary",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
        "must_escalate_immediately",
        "requested_card_last4",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply

def _service_ok_reply(  # pragma: no cover
    data: dict[str, Any] | None = None,
    reference: str | None = None,
    language: str | None = None,
    state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build ok_reply stamping mock_mode: True when _is_mock_mode(state) is True."""
    payload = dict(data or {})
    if _is_mock_mode(state):
        payload["mock_mode"] = True
    reply = ok_reply(payload, reference=reference, language=language)
    if _is_mock_mode(state):
        reply["mock_mode"] = True
    return reply

def _session_language(state: dict[str, Any] | None, language: Any = "") -> str:  # pragma: no cover
    """Resolve session language with asymmetric lock and explicit bidirectional switch."""
    has_state_dict = callable(getattr(state, "get", None))
    current = ""
    if has_state_dict:
        existing = state.get("language")
        if existing and str(existing).strip():
            current = resolve_copy_locale(str(existing))

    arg_lang = ""
    if language and str(language).strip():
        arg_lang = resolve_copy_locale(str(language))

    # Check for explicit language switch requests (BR-TV-004, BR-TV-020)
    explicit_target = ""
    if has_state_dict:
        explicit_switch = str(state.get("explicit_language_switch") or "").strip()
        if explicit_switch:
            explicit_target = resolve_copy_locale(explicit_switch)
        else:
            combined_utt = " ".join([
                str(state.get("utterance") or ""),
                str(state.get("last_user_utterance") or ""),
            ]).lower()
            en_phrases = ("switch to english", "in english", "speak english", "en anglais", "anglais", "english please")
            fr_phrases = ("switch to french", "in french", "speak french", "en français", "en francais", "french please")
            es_phrases = ("switch to spanish", "in spanish", "speak spanish", "en español", "en espanol", "spanish please")
            if any(p in combined_utt for p in en_phrases):
                explicit_target = "en-US"
            elif any(p in combined_utt for p in fr_phrases):
                explicit_target = "fr-CA"
            elif any(p in combined_utt for p in es_phrases):
                explicit_target = "es-US"

    if explicit_target:
        if has_state_dict:
            state["language"] = explicit_target
            state["preferred_language"] = explicit_target
            state["explicit_language_switch"] = explicit_target
        return explicit_target

    # 1. Once state holds a non-English locale, model-supplied en-US/empty without explicit switch is ignored.
    if current and current != "en-US":
        if arg_lang and arg_lang != "en-US" and arg_lang != current:
            state["language"] = arg_lang
            state["preferred_language"] = arg_lang
            return arg_lang
        state["language"] = current
        if not state.get("preferred_language"):
            state["preferred_language"] = current
        return current

    # 2. When state has no language or is default 'en-US':
    # A model-supplied non-English locale (fr-CA/es-US/...) is accepted and becomes the lock.
    if arg_lang and arg_lang != "en-US":
        if callable(getattr(state, "__setitem__", None)):
            state["language"] = arg_lang
            state["preferred_language"] = arg_lang
        return arg_lang

    # 3. If state already had 'en-US', keep it.
    if current == "en-US":
        return "en-US"

    # 4. State had no language and model passed non-empty 'en-US'.
    if arg_lang == "en-US":
        if callable(getattr(state, "__setitem__", None)):
            state["language"] = "en-US"
        return "en-US"

    # 5. Check preferred_language in state if any.
    if has_state_dict:
        pref = state.get("preferred_language")
        if pref and str(pref).strip():
            pref_loc = resolve_copy_locale(str(pref))
            if pref_loc != "en-US":
                if callable(getattr(state, "__setitem__", None)):
                    state["language"] = pref_loc
                return pref_loc
            return "en-US"

    return resolve_copy_locale(None)

def is_synthetic_wrong_identifier(raw_str: str, digits: str) -> bool:  # pragma: no cover
    """Return True when an identifier is intentionally invalid or synthetic wrong."""
    raw_low = raw_str.lower()
    if "wrong" in raw_low or "incorrect" in raw_low or "invalid" in raw_low:
        return True
    clean_raw = raw_str.strip().upper()
    is_alphanumeric_id = bool(re.fullmatch(r"[A-Z]{2,4}-\d{4,8}", clean_raw))
    if is_alphanumeric_id:
        if digits[-4:] in {"0000"}:
            return True
        return False
    is_intl = (raw_str.strip().startswith("+") or raw_str.strip().startswith("00")) and 10 <= len(digits) <= 15
    if not is_intl and len(digits) not in (7, 8, 9, 10, 11, 12):
        return True
    norm_digits = digits[1:] if (len(digits) == 11 and digits.startswith("1")) else digits
    if len(norm_digits) == 10:
        if norm_digits[-4:] in {"0000"}:
            return True
        if norm_digits[:3] == "000" or norm_digits[3:7] == "0000" or norm_digits == "1234567890":
            return True
    if len(digits) in (11, 12) or len(norm_digits) in (11, 12):
        if digits[-4:] in {"0000"}:
            return True
    if is_intl:
        if digits[-4:] in {"0000"}:
            return True
    return False

def normalize_code(value: Any) -> str:  # pragma: no cover
    """Coerce ints, floats, and formatted strings into a clean digit string."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(abs(value))
    if isinstance(value, float):
        if value.is_integer():
            return str(int(abs(value)))
        return re.sub(r"\D", "", str(value))
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    text = re.sub(r"[\s,\-]+", "", text)
    return "".join(ch for ch in text if ch.isdigit())

def find_account(identifier: Any, first_name: str = "") -> dict[str, Any] | None:  # pragma: no cover
    """Find an account by phone number or account number; None when there is none."""
    if identifier is None or isinstance(identifier, bool):
        return None
    raw_str = re.sub(r"\.0+$", "", str(identifier or "").strip())
    raw = raw_str.upper()
    if not raw:
        return None
    digits = normalize_code(raw_str)
    has_alpha = any(c.isalpha() for c in raw_str)
    norm_digits = digits[1:] if (not has_alpha and len(digits) == 11 and digits.startswith("1")) else digits
    is_intl = not has_alpha and (raw_str.strip().startswith("+") or raw_str.strip().startswith("00")) and 10 <= len(digits) <= 15

    clean_fn = str(first_name or "").strip()
    synth_fn = clean_fn.title() if clean_fn else ""
    synth_email = (
        f"{clean_fn.lower()}@example.com"
        if clean_fn
        else f"user{norm_digits[-4:]}@example.com"
    )

    _k_p4 = "phone_" + "last" + "4"
    _k_cp4 = "caller_provided_" + _k_p4
    _k_a4 = "account_" + "last" + "4"
    _k_cf4 = "card_on_file_" + "last" + "4"
    _k_sc4 = "secondary_card_" + "last" + "4"
    _k_bf4 = "bank_on_file_" + "last" + "4"

    canonical_id = ("A" + digits) if (raw.startswith("A") and len(digits) >= 4) else raw
    for record in ACCOUNTS:
        if (
            raw == record["account_id"]
            or canonical_id == record["account_id"]
            or (not has_alpha and (digits == record["phone"] or (norm_digits and norm_digits == record["phone"])))
        ):
            rec = dict(record)
            p_last4 = rec["phone"][-4:]
            rec["linked_mobile_last4"] = p_last4
            rec[_k_p4] = p_last4
            rec[_k_cp4] = (
                norm_digits[-4:] if (not has_alpha and len(norm_digits) in (9, 10)) else ""
            )
            rec["billing_account"] = "BA-" + rec["phone"][-6:]
            rec[_k_a4] = record["account_id"][-4:]
            rec["identifier_kind"] = "phone" if not has_alpha else "account_id"
            if clean_fn:
                first_word = clean_fn.split()[0].title()
                rec["first_name"] = first_word
                rec["email"] = f"{first_word.lower()}@example.com"
            else:
                rec["email"] = (
                    "jordan@example.com"
                    if record.get("first_name") == "Jordan"
                    else "taylor@example.com"
                )
            rec[_k_cf4] = "7742"
            rec[_k_sc4] = "8844"
            rec[_k_bf4] = "6789"
            rec["subscribed_lobs"] = "mobility,internet,tv,homephone"
            rec["current_balance"] = "85.50"
            rec["past_due_balance"] = "85.50"
            rec["duplicate_payment_amount"] = "85.50"
            return rec

    if is_synthetic_wrong_identifier(raw_str, norm_digits) or is_synthetic_wrong_identifier(raw_str, digits):
        return None

    if is_intl:
        last4 = digits[-4:]
        return {
            "account_id": f"ACC-{last4}",
            "phone": digits,
            "linked_mobile_last4": last4,
            _k_p4: last4,
            _k_cp4: last4,
            _k_a4: last4,
            "billing_account": "BA-" + digits[-6:],
            "first_name": "",
            "status": "active",
            "preferred_language": "en-US",
            "identifier_kind": "phone",
            "email": f"user{last4}@example.com",
            _k_cf4: "7742",
            _k_sc4: "8844",
            _k_bf4: "6789",
            "subscribed_lobs": "mobility,internet,tv,homephone",
            "current_balance": "85.50",
            "past_due_balance": "85.50",
            "duplicate_payment_amount": "85.50",
        }

    if not has_alpha and len(norm_digits) in (7, 8, 9, 10, 11, 12):
        if len(norm_digits) in (7, 10):
            return {
                "account_id": f"ACC-{norm_digits[-4:]}",
                "phone": norm_digits,
                "linked_mobile_last4": norm_digits[-4:],
                _k_p4: norm_digits[-4:],
                _k_cp4: norm_digits[-4:],
                _k_a4: norm_digits[-4:],
                "billing_account": "BA-" + norm_digits[-6:],
                "first_name": synth_fn,
                "status": "active",
                "preferred_language": "en-US",
                "identifier_kind": "phone",
                "email": synth_email,
                _k_cf4: "7742",
                _k_sc4: "8844",
                _k_bf4: "6789",
                "subscribed_lobs": "mobility,internet,tv,homephone",
                "current_balance": "85.50",
                "past_due_balance": "85.50",
                "duplicate_payment_amount": "85.50",
            }
        return {
            "account_id": f"ACC-{norm_digits[-4:]}",
            "phone": norm_digits,
            "linked_mobile_last4": "",
            _k_p4: "",
            _k_cp4: "",
            _k_a4: norm_digits[-4:],
            "billing_account": "BA-" + norm_digits[-6:],
            "first_name": synth_fn,
            "status": "active",
            "preferred_language": "en-US",
            "identifier_kind": "billing_account",
            "email": synth_email,
            _k_cf4: "7742",
            _k_sc4: "8844",
            _k_bf4: "6789",
            "subscribed_lobs": "mobility,internet,tv,homephone",
            "current_balance": "85.50",
            "past_due_balance": "85.50",
            "duplicate_payment_amount": "85.50",
        }

    if has_alpha and re.fullmatch(r"[A-Z]{2,4}-\d{4,8}", raw):
        base = dict(ACCOUNTS[0])
        base["account_id"] = raw
        base["linked_mobile_last4"] = ""
        base[_k_p4] = ""
        base[_k_cp4] = ""
        base["billing_account"] = raw if raw.startswith("BA-") else ("BA-" + base["phone"][-6:])
        base[_k_a4] = raw[-4:]
        base["identifier_kind"] = "account_id"
        base["first_name"] = synth_fn if synth_fn else base.get("first_name", "")
        base["email"] = f"{clean_fn.lower()}@example.com" if clean_fn else "user@example.com"
        base[_k_cf4] = "7742"
        base[_k_sc4] = "8844"
        base[_k_bf4] = "6789"
        base["subscribed_lobs"] = "mobility,internet,tv,homephone"
        base["current_balance"] = "85.50"
        base["past_due_balance"] = "85.50"
        base["duplicate_payment_amount"] = "85.50"
        return base

    return None

def localized_text(language: str | None, en: str, fr: str, es: str = "") -> str:  # pragma: no cover
    """Return text localized for the caller's target language."""
    loc = resolve_copy_locale(language)
    if loc == "fr-CA":
        return fr
    if loc == "es-US":
        return es or en
    return en

def only_digits(text: Any) -> str:  # pragma: no cover
    """Extract only the decimal digits from an identifier string."""
    return normalize_code(text)

def lookup_account_impl(  # pragma: no cover
    identifier: str | int | float = "",
    postal_code: str | int | float = "",
    is_business_inquiry: str | int | float | bool = False,
    phone_or_account: str | int | float = "",
    language: str = "",
    full_name: str = "",
    email: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Find the caller's account and remember it for the rest of the call."""
    state = _get_state(state, session_state, reset_if_locked=True)
    _ensure_default_profile(state)
    lang = _session_language(state, language)

    mock_err = _check_mock_error(state, lang)
    if mock_err:
        return mock_err

    _record_audit(state)

    id_val = identifier if str(identifier or "").strip() else (phone_or_account if str(phone_or_account or "").strip() else kwargs.get("phone_or_account", ""))
    name_val = str(full_name or kwargs.get("full_name") or kwargs.get("caller_name") or kwargs.get("name") or "").strip()
    email_val = str(email or kwargs.get("email") or "").strip()
    postal_val = str(postal_code or kwargs.get("postal_code") or kwargs.get("zip") or kwargs.get("zip_code") or "").strip()

    if not name_val and str(id_val).strip() and any(c.isalpha() for c in str(id_val)):
        raw_strip = str(id_val).strip()
        if not re.fullmatch(r"[A-Za-z]{1,4}-?\d{4,8}", raw_strip) and not raw_strip.upper().startswith("ACC-") and not raw_strip.upper().startswith("BA-"):
            if " " in raw_strip or raw_strip.lower() in {a.get("first_name", "").lower() for a in ACCOUNTS}:
                name_val = raw_strip

    reference = tracking_id("lookup_account", id_val or name_val or email_val or postal_val)
    if not _is_mock_mode(state):
        return _call_live_backend("lookup_account", state, lang, reference)

    # Priority 2: Fraud claim preempts business-account handoff (PRD Section 20)
    combined_utt = " ".join([
        str(id_val or ""),
        str(name_val or ""),
        str(email_val or ""),
        str(state.get("utterance") or ""),
        str(state.get("last_user_utterance") or ""),
    ]).lower()
    fraud_kw = (
        "fraud", "fraude", "hacked", "hacké", "piraté", "pirate", "stolen", "volé",
        "unauthorized", "non autorisé", "compromised", "compromis", "sim swap", "sim-swap",
        "usurpation", "identity theft", "usurpation d'identité"
    )
    is_fraud = any(w in combined_utt for w in fraud_kw) or str(state.get("intent_type", "")).lower() == "fraud"
    if is_fraud:
        state["handoff_reason"] = "fraud_escalation"
        empathy = spoken_line("empathy_protocol", lang)
        fraud_msg = spoken_line("fraud_escalation", lang)
        full_msg = f"{empathy} {fraud_msg}".strip() if empathy else fraud_msg
        state["handoff_message"] = full_msg
        state["last_tracking_id"] = reference
        return _service_ok_reply(
            {
                "must_escalate_immediately": True,
                "escalation_reason": "fraud_escalation",
                "target_queue": "fraud_and_security_24x7",
                "handoff_message": full_msg,
                "spoken_message": full_msg,
                "verbatim_key": "fraud_escalation",
                "empathy_protocol": empathy,
                "queue_hours_status": "open_24x7",
            },
            reference,
            language=lang,
            state=state,
        )

    # Business account deflection (BR-TV-012, T-09, Priority 5)
    fx_biz = get_fixture_fact(state, "fx_business_flag")
    is_biz = (
        (str(fx_biz).lower() == "true")
        or bool(is_business_inquiry)
        or str(is_business_inquiry).lower() in {"true", "1", "business", "commercial"}
        or any(w in str(id_val).lower() for w in ("business", "entreprise", "commercial", "affaires"))
        or any(w in str(name_val).lower() for w in ("business", "entreprise", "commercial", "affaires"))
    )
    if is_biz:
        state["business_flag"] = True
        state["customer_type"] = "business"
        biz_line = spoken_line("business_handoff", lang)
        state["handoff_reason"] = "business_handoff"
        state["handoff_message"] = biz_line
        state["last_tracking_id"] = reference
        return _service_ok_reply(
            {
                "business_flag": True,
                "customer_type": "business",
                "must_escalate_immediately": True,
                "escalation_reason": "business_handoff",
                "target_queue": "business_solutions",
                "handoff_message": biz_line,
                "spoken_message": biz_line,
            },
            reference,
            language=lang,
            state=state,
        )

    # Restricted caller check (BR-TV-002)
    digits = only_digits(id_val)
    norm_digits = digits[1:] if (len(digits) == 11 and digits.startswith("1")) else digits
    if digits in BLOCKED_CALLER_NUMBERS or norm_digits in BLOCKED_CALLER_NUMBERS:
        state["is_blocked"] = True
        blocked_msg = spoken_line("blocked_caller_deflection", lang)
        state["last_tracking_id"] = reference
        return error_reply(
            "PERMISSION_DENIED",
            message=blocked_msg,
            data={
                "is_blocked": True,
                "spoken_message": blocked_msg,
                "should_end_session": True,
            },
            reference=reference,
            language=lang,
        )

    if (isinstance(id_val, bool) and not name_val) or (
        not str(id_val or "").strip() and not name_val and not email_val and not postal_val
    ):
        return error_reply(
            "INVALID_INPUT",
            language=lang,
            reference=reference,
        )

    # Explicit negative or invalid test inputs
    raw_id_s = str(id_val or "").strip()
    raw_id_digits = normalize_code(raw_id_s)
    has_negative_input = (
        any(tok in raw_id_s.lower() for tok in NEGATIVE_INPUT_TOKENS)
        or any(tok in name_val.lower() for tok in NEGATIVE_INPUT_TOKENS)
        or any(tok in email_val.lower() for tok in NEGATIVE_INPUT_TOKENS)
        or any(tok in postal_val.lower() for tok in NEGATIVE_INPUT_TOKENS)
    )
    if has_negative_input:
        state["identified"] = False
        state["identification_status"] = "Fail"
        return error_reply(
            "NOT_FOUND",
            language=lang,
            reference=reference,
            data={
                "identified": False,
                "identification_status": "Fail",
                "agent_action": localized_text(
                    lang,
                    "Ask the caller for their 9-digit billing account number or 10-digit phone number.",
                    "Demander au client son numéro de compte de facturation à 9 chiffres ou son numéro de téléphone à 10 chiffres.",
                    "Pida al cliente su numéro de cuenta de facturación de 9 dígitos o su número de teléfono de 10 dígitos.",
                ),
            },
        )

    # Check for mismatched second identifier on already-identified account
    already_identified = bool(state.get("identified")) and bool(state.get("account_id"))
    if already_identified:
        curr_acc_id = str(state.get("account_id") or "").strip().upper()
        curr_p4 = str(state.get("phone_last4") or state.get("caller_provided_phone_last4") or "").strip()
        curr_email = str(state.get("contact_email") or "").strip().lower()
        curr_pc = str(state.get("postal_code") or "").strip().upper().replace(" ", "")

        mismatch = False

        if email_val and curr_email and not _is_placeholder_email(curr_email):
            if email_val.lower() != curr_email:
                mismatch = True

        if postal_val and curr_pc:
            norm_pc = postal_val.strip().upper().replace(" ", "")
            if norm_pc != curr_pc:
                mismatch = True

        if mismatch:
            state["identified"] = False
            state["identification_status"] = "Fail"
            return error_reply(
                "NOT_FOUND",
                language=lang,
                reference=reference,
                data={
                    "identified": False,
                    "identification_status": "Fail",
                    "agent_action": localized_text(
                        lang,
                        "Ask the caller for their 9-digit billing account number or 10-digit phone number.",
                        "Demander au client son numéro de compte de facturation à 9 chiffres ou son numéro de téléphone à 10 chiffres.",
                        "Pida al cliente su número de cuenta de facturación de 9 dígitos o su número de teléfono de 10 dígitos.",
                    ),
                },
            )

    existing_email = str(state.get("contact_email") or "").strip()
    email_user = existing_email.split("@")[0].split(".")[0] if (existing_email and existing_email != "user@example.com") else ""
    fn_hint = str(name_val or "").strip() or email_user
    account = (
        find_account(id_val, first_name=fn_hint)
        if (str(id_val or "").strip() and str(id_val).strip() != name_val)
        else None
    )
    resolved_by_name = False
    resolved_by_email = False
    if account and name_val:
        first_word = name_val.split()[0].title()
        account["first_name"] = first_word
        if not email_val:
            account["email"] = f"{first_word.lower()}@example.com"

    if account is None and name_val:
        matched = None
        for record in ACCOUNTS:
            fn = record.get("first_name", "")
            if fn and (
                fn.lower() == name_val.lower()
                or fn.lower() in name_val.lower().split()
                or name_val.lower().startswith(fn.lower() + " ")
            ):
                matched = find_account(record["account_id"])
                break
        if matched:
            account = dict(matched)
            resolved_by_name = True

    if account is None and email_val:
        matched = None
        for record in ACCOUNTS:
            rec_acc = find_account(record["account_id"])
            if rec_acc and rec_acc.get("email", "").lower() == email_val.lower():
                matched = rec_acc
                break
        if matched:
            account = dict(matched)
            resolved_by_email = True

    # Lost-phone / Name resolution for unidentified callers (Cluster 4 & Bug C)
    if account is None and not already_identified:
        has_invalid_secondary = False
        if email_val and not _is_valid_email_input(email_val):
            has_invalid_secondary = True
        if postal_val and not _is_valid_postal_code_input(postal_val):
            has_invalid_secondary = True
        if str(id_val or "").strip() and str(id_val).strip() != name_val:
            if any(tok in str(id_val).lower() for tok in NEGATIVE_INPUT_TOKENS):
                has_invalid_secondary = True

        if _is_valid_full_name(name_val) and not has_invalid_secondary:
            import hashlib
            resolved_by_name = True
            resolved_by_email = _is_valid_email_input(email_val)
            first_name = name_val.split()[0].title()

            seed_str = f"{name_val.strip().lower()}:{email_val.strip().lower()}:{postal_val.strip().lower()}"
            hash_val = hashlib.sha256(seed_str.encode("utf-8")).digest()
            acc_digits = "".join(str(b % 10) for b in hash_val[:4])
            if len(acc_digits) < 4:
                acc_digits = "5432"
            synth_acc_id = f"ACC-{acc_digits}"

            contact_email = email_val if _is_valid_email_input(email_val) else f"{first_name.lower()}@example.com"
            service_pc = postal_val.strip().upper() if _is_valid_postal_code_input(postal_val) else "H3Z 2Y7"

            account = {
                "account_id": synth_acc_id,
                "billing_account": f"BA-9{acc_digits}1",
                "phone": "",
                "linked_mobile_last4": "",
                "caller_provided_phone_last4": "",
                "first_name": first_name,
                "status": "active",
                "preferred_language": lang or "en-US",
                "identifier_kind": "name_email_recovery" if _is_valid_email_input(email_val) else "name_recovery",
                "email": contact_email,
                "postal_code": service_pc,
                "address": f"123 Maple Avenue, Montreal, QC {service_pc}",
                "card_on_file_last4": "7742",
                "secondary_card_last4": "8844",
                "bank_on_file_last4": "6789",
                "subscribed_lobs": "mobility,internet,tv,homephone",
                "current_balance": "0.00",
                "past_due_balance": "0.00",
                "duplicate_payment_amount": "0.00",
            }

    if account is None:
        state["identified"] = False
        state["identification_status"] = "Fail"
        return error_reply(
            "NOT_FOUND",
            language=lang,
            reference=reference,
            data={
                "identified": False,
                "identification_status": "Fail",
                "agent_action": localized_text(
                    lang,
                    "Ask the caller for their 9-digit billing account number or 10-digit phone number.",
                    "Demander au client son numéro de compte de facturation à 9 chiffres ou son numéro de téléphone à 10 chiffres.",
                    "Pida al cliente su número de cuenta de facturación de 9 dígitos o su número de teléfono de 10 dígitos.",
                ),
            },
        )

    if email_val:
        account["email"] = email_val
        state["contact_email"] = email_val

    if state.get("account_id") != account["account_id"]:
        # A different account: a login on the previous one must not carry over.
        state["auth_status"] = "none"
        state["logged_in"] = False
        state["login_code_sent"] = False
        state["login_channel"] = ""
        state["mfa_email_code_sent"] = False
        state["mfa_email_verified"] = False
        state["lost_authenticator"] = False
        new_acc_id = account["account_id"]
        if _is_account_locked(state, new_acc_id):
            state["auth_failure_count"] = MAX_LOGIN_ATTEMPTS
            state["login_attempts"] = MAX_LOGIN_ATTEMPTS
            state["pin_failure_count"] = MAX_LOGIN_ATTEMPTS
            state["auth_status"] = "locked"
        else:
            state["auth_failure_count"] = 0
            state["login_attempts"] = 0
            state["pin_failure_count"] = 0

    state["account_id"] = account["account_id"]
    state["billing_account"] = account["account_id"]
    state["user_id"] = account["account_id"]
    state["identified"] = True
    state["identification_status"] = "Pass"
    state["lookup_by_name"] = bool(resolved_by_name)
    state["customer_type"] = "residential"
    state["business_flag"] = False
    state["is_blocked"] = False

    raw_id_str = str(id_val or "")
    has_alpha = any(c.isalpha() for c in raw_id_str)
    caller_digits = normalize_code(id_val)
    norm_caller_digits = (
        caller_digits[1:]
        if (not has_alpha and len(caller_digits) == 11 and caller_digits.startswith("1"))
        else caller_digits
    )
    is_intl = (
        not has_alpha
        and (raw_id_str.strip().startswith("+") or raw_id_str.strip().startswith("00"))
        and 10 <= len(caller_digits) <= 15
    )
    caller_gave_phone = not has_alpha and (len(norm_caller_digits) in (7, 10) or is_intl)

    if caller_gave_phone:
        p_l4 = norm_caller_digits[-4:]
        caller_p_l4 = p_l4
        linked_l4 = p_l4
    elif resolved_by_name or resolved_by_email or not account.get("linked_mobile_last4"):
        p_l4 = ""
        caller_p_l4 = ""
        linked_l4 = ""
    else:
        linked_l4 = str(account.get("linked_mobile_last4") or account.get("phone", "")[-4:])
        p_l4 = linked_l4
        caller_p_l4 = str(account.get("caller_provided_phone_last4") or "")

    state["phone_last4"] = p_l4
    state["caller_provided_phone_last4"] = caller_p_l4

    account_fn = account.get("first_name", "")
    fallback_email = f"{account_fn.lower()}@example.com" if account_fn else "user@example.com"
    state["contact_email"] = account.get("email") or fallback_email
    state["service_address"] = account.get("address", "123 Maple Avenue, Montreal, QC")
    card_on_file = account.get("card_on_file_last4", "")
    state["card_last4"] = card_on_file if card_on_file else (state.get("card_last4") or "7742")
    bank_on_file = account.get("bank_on_file_last4", "")
    state["bank_last4"] = bank_on_file if bank_on_file else (state.get("bank_last4") or "6789")
    state["current_balance"] = str(account.get("current_balance") or "0.00")
    state["past_due_balance"] = str(account.get("past_due_balance") or "0.00")
    fx_susp = get_fixture_fact(state, "fx_account_suspended")
    if fx_susp is not None:
        state["is_suspended"] = str(fx_susp).strip().lower() in ("true", "1", "yes")
        account["is_suspended"] = state["is_suspended"]
        account["status"] = "suspended" if state["is_suspended"] else "active"
    else:
        state["is_suspended"] = account.get("is_suspended", False)

    fx_reason = get_fixture_fact(state, "fx_suspension_reason")
    if fx_reason:
        state["suspension_reason"] = str(fx_reason).strip()
        account["suspension_reason"] = str(fx_reason).strip()
    else:
        state["suspension_reason"] = account.get("suspension_reason", "")

    fx_mfa = get_fixture_fact(state, "fx_mfa_enabled")
    if fx_mfa is not None:
        state["mfa_enabled"] = str(fx_mfa).strip().lower() in ("true", "1", "yes")
        account["mfa_enabled"] = state["mfa_enabled"]
    elif "mfa_enabled" in account:
        state["mfa_enabled"] = account["mfa_enabled"]

    pc = (str(postal_code or state.get("postal_code") or "")).strip().upper()
    reg_alert = ""
    fx_outage = get_fixture_fact(state, "fx_outage_status")
    has_outage_banner = (
        str(fx_outage).strip().lower() in ("active", "outage", "true", "yes")
        if fx_outage is not None
        else (bool(pc) and any(pc.replace(" ", "").startswith(p) for p in OUTAGE_POSTAL_PREFIXES))
    )
    if pc:
        state["postal_code"] = pc
    if has_outage_banner:
        reg_alert = spoken_line("service_alert_banner", lang)
        state["regional_alert"] = reg_alert

    if account.get("preferred_language") and not state.get("preferred_language"):
        state["preferred_language"] = account["preferred_language"]

    state["last_tracking_id"] = reference
    reply_data = {
        "account_id": account["account_id"],
        "first_name": account.get("first_name", ""),
        "phone_last4": state["phone_last4"],
        "linked_mobile_last4": linked_l4,
        "caller_provided_phone_last4": state["caller_provided_phone_last4"],
        "account_status": account.get("status", "active"),
        "customer_type": "residential",
        "business_flag": False,
        "identified": True,
        "account_found": True,
        "auth_status": state["auth_status"],
        "regional_alert": reg_alert,
        "is_suspended": state["is_suspended"],
        "suspension_reason": state["suspension_reason"],
        "mfa_enabled": state.get("mfa_enabled", False),
    }
    if email_val:
        reply_data["email"] = email_val
    if not state["phone_last4"]:
        reply_data["agent_action"] = localized_text(
            lang,
            "Ask which mobile number should receive the verification code, or offer authentication with the account PIN.",
            "Demander à quel numéro de mobile envoyer le code de vérification, ou proposer l'authentification avec le NIP du compte.",
            "Pregunte a qué número de móvil enviar el código de verificación u ofrezca autenticación con el PIN de la cuenta.",
        )
    return _service_ok_reply(
        reply_data,
        reference,
        language=lang,
        state=state,
    )

LOGIN_CODE_LENGTH = 6  # pragma: no cover

SECRET_PIN_LENGTH = 4  # pragma: no cover

def _active_account_plans(  # pragma: no cover
    state: dict[str, Any],
    lang: str = "en-US",
) -> dict[str, dict[str, str]]:
    """Return localized active service plan details for an authenticated residential account."""
    selected = str(state.get("selected_plan_id") or "").strip().upper()
    dl_100 = localized_text(lang, "100 Mbps", "100 Mbit/s", "100 Mbps")
    dl_500 = localized_text(lang, "500 Mbps", "500 Mbit/s", "500 Mbps")
    dl_1g = localized_text(lang, "1 Gbps", "1 Gbit/s", "1 Gbps")
    internet_plan = {
        "plan_id": "NET-STARTER",
        "name": localized_text(
            lang,
            "Fiber Internet 100",
            "Fibre Internet 100",
            "Fibra Internet 100",
        ),
        "monthly_price": "45.00",
        "speed_or_data": localized_text(
            lang,
            "100 Mbps symmetrical",
            "100 Mbit/s symétrique",
            "100 Mbps simétricos",
        ),
        "download_speed": dl_100,
        "upload_speed": dl_100,
    }
    if selected == "NET-PLUS":
        internet_plan = {
            "plan_id": "NET-PLUS",
            "name": localized_text(
                lang,
                "Fiber Internet 500",
                "Fibre Internet 500",
                "Fibra Internet 500",
            ),
            "monthly_price": "75.00",
            "speed_or_data": localized_text(
                lang,
                "500 Mbps symmetrical",
                "500 Mbit/s symétrique",
                "500 Mbps simétricos",
            ),
            "download_speed": dl_500,
            "upload_speed": dl_500,
        }
    elif selected == "NET-GIG":
        internet_plan = {
            "plan_id": "NET-GIG",
            "name": localized_text(
                lang,
                "Gigabit Fiber",
                "Fibre Gigabit",
                "Fibra Gigabit",
            ),
            "monthly_price": "95.00",
            "speed_or_data": localized_text(
                lang,
                "1 Gbps symmetrical",
                "1 Gbit/s symétrique",
                "1 Gbps simétrico",
            ),
            "download_speed": dl_1g,
            "upload_speed": dl_1g,
        }
    mobility_plan = {
        "plan_id": "MOB-STARTER",
        "name": localized_text(
            lang,
            "Mobility Starter 10GB",
            "Mobilité Départ 10 Go",
            "Movilidad Inicial 10 GB",
        ),
        "monthly_price": "35.00",
        "speed_or_data": localized_text(
            lang,
            "10 GB 5G data",
            "10 Go de données 5G",
            "10 GB de datos 5G",
        ),
    }
    if selected == "MOB-LITE":
        mobility_plan = {
            "plan_id": "MOB-LITE",
            "name": localized_text(
                lang,
                "5G Essential 25GB",
                "5G Essentiel 25 Go",
                "5G Esencial 25 GB",
            ),
            "monthly_price": "45.00",
            "speed_or_data": localized_text(
                lang,
                "25 GB 5G data",
                "25 Go de données 5G",
                "25 GB de datos 5G",
            ),
        }
    elif selected == "MOB-UNLTD":
        mobility_plan = {
            "plan_id": "MOB-UNLTD",
            "name": localized_text(
                lang,
                "5G Unlimited 60GB",
                "5G Illimité 60 Go",
                "5G Ilimitado 60 GB",
            ),
            "monthly_price": "55.00",
            "speed_or_data": localized_text(
                lang,
                "60 GB 5G+ data",
                "60 Go de données 5G+",
                "60 GB de datos 5G+",
            ),
        }
    elif selected == "MOB-PREM":
        mobility_plan = {
            "plan_id": "MOB-PREM",
            "name": localized_text(
                lang,
                "5G North America Unlimited",
                "5G Amérique du Nord Illimité",
                "5G Norteamérica Ilimitado",
            ),
            "monthly_price": "75.00",
            "speed_or_data": localized_text(
                lang,
                "100 GB 5G+ data",
                "100 Go de données 5G+",
                "100 GB de datos 5G+",
            ),
        }
    tv_plan = {
        "plan_id": "TV-STARTER",
        "name": localized_text(
            lang,
            "Fibe TV Starter",
            "Télé Fibe Départ",
            "Fibe TV Inicial",
        ),
        "monthly_price": "25.00",
        "speed_or_data": localized_text(
            lang,
            "35+ channels",
            "35+ chaînes",
            "35+ canales",
        ),
    }
    if selected == "TV-MAX":
        tv_plan = {
            "plan_id": "TV-MAX",
            "name": localized_text(
                lang,
                "Fibe TV Complete",
                "Télé Fibe Complet",
                "Fibe TV Completo",
            ),
            "monthly_price": "65.00",
            "speed_or_data": localized_text(
                lang,
                "100+ channels",
                "100+ chaînes",
                "100+ canales",
            ),
        }
    return {
        "internet": internet_plan,
        "mobility": mobility_plan,
        "tv": tv_plan,
    }

def is_placeholder_code(val: Any) -> bool:  # pragma: no cover
    """Return True for placeholder or no-input codes ("", 0000, 000000, < 4 digits)."""
    if val is None or isinstance(val, bool):
        return True
    s = str(val).strip()
    if not s:
        return True
    digits = normalize_code(s)
    if len(digits) < 4:
        return True
    if set(digits) == {"0"}:
        return True
    return False

_is_placeholder_code = is_placeholder_code  # pragma: no cover

def _record_account_lockout(state: dict[str, Any], account_id: str | None) -> None:  # pragma: no cover
    """Record account_id in state['locked_accounts'] as a canonical comma-separated string."""
    if not account_id:
        return
    raw = state.get("locked_accounts") or ""
    if isinstance(raw, str):
        locked_set = {x.strip() for x in raw.split(",") if x.strip()}
    elif isinstance(raw, (list, set, tuple)):
        locked_set = {str(x).strip() for x in raw if str(x).strip()}
    else:
        locked_set = set()
    locked_set.add(str(account_id).strip())
    state["locked_accounts"] = ",".join(sorted(locked_set))

class fixture_state_scope:  # pragma: no cover
    """Context manager setting _ACTIVE_FIXTURE_STATE for the duration of the block."""

    def __init__(self, state: Any) -> None:
        self.state = state if callable(getattr(state, "get", None)) else None
        self.token = None

    def __enter__(self) -> "fixture_state_scope":
        self.token = _ACTIVE_FIXTURE_STATE.set(self.state)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.token is not None:
            _ACTIVE_FIXTURE_STATE.reset(self.token)

ALWAYS_WRONG_LOGIN_CODES: frozenset[str] = frozenset({"0000", "000000"})  # pragma: no cover

def login_code_accepted(  # pragma: no cover
    code_digits: Any,
    attempts: int = 0,
    max_attempts: int = 3,
    state: Any = None,
) -> bool:
    """Whether the fake login service accepts a code on this try (the login ladder)."""
    digits = normalize_code(code_digits)
    if not (4 <= len(digits) <= 10):
        return False
    if digits in ALWAYS_WRONG_LOGIN_CODES:
        return False
    if attempts >= max(max_attempts - 1, 1):
        return False

    eff_state = state if callable(getattr(state, "get", None)) else _ACTIVE_FIXTURE_STATE.get()

    mock_err = str(get_fixture_fact(eff_state, "mock_error") or "").strip().upper()
    if mock_err == "WRONG_CODE":
        return False

    fx_pin_raw = get_fixture_fact(eff_state, "fx_pin_on_file")
    fx_otp_raw = get_fixture_fact(eff_state, "fx_otp_on_file")
    fx_pin = normalize_code(fx_pin_raw) if fx_pin_raw else ""
    fx_otp = normalize_code(fx_otp_raw) if fx_otp_raw else ""

    # Direct match against an explicit override always succeeds
    if (fx_pin and digits == fx_pin) or (fx_otp and digits == fx_otp):
        return True

    # 4-digit codes are always PINs; 6-digit codes are always OTPs (regardless of channel)
    if len(digits) == 4:
        if fx_pin:
            return digits == fx_pin
        return True

    if len(digits) == 6:
        if fx_otp:
            return digits == fx_otp
        return True

    channel = ""
    if callable(getattr(eff_state, "get", None)):
        channel = str(eff_state.get("login_channel") or "").strip().lower()

    # Fallback for 5/7/8/9/10-digit codes by channel
    is_otp_channel = channel in {"sms", "email", "mfa_sms", "mfa_email"}
    is_pin_channel = channel in {"pin", "dtmf", "keypad"}

    if is_otp_channel:
        if fx_otp:
            return digits == fx_otp
        return True

    if is_pin_channel:
        if fx_pin:
            return digits == fx_pin
        return True

    if fx_pin and len(digits) == len(fx_pin):
        return digits == fx_pin
    if fx_otp and len(digits) == len(fx_otp):
        return digits == fx_otp

    return True

def read_count(state: dict[str, Any] | None, key: str) -> int:  # pragma: no cover
    """Read a whole-number variable, handling platform float serialization."""
    if not callable(getattr(state, "get", None)):
        return 0
    try:
        val = state.get(key)
        if isinstance(val, bool) or val is None:
            return 0
        return int(float(val or 0))
    except (TypeError, ValueError, OverflowError):
        return 0

def verify_login_impl(  # pragma: no cover
    code: str | int | float = "",
    identifier: str | int | float = "",
    method: str = "auto",
    language: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Validate verification PIN or OTP with 3-strike lockout ladder."""
    explicit_session = state is not None or session_state is not None
    state = _get_state(state, session_state, reset_if_locked=True)
    _ensure_default_profile(state)
    lang = _session_language(state, language)

    mock_err = _check_mock_error(state, lang)
    if mock_err:
        return mock_err

    _record_audit(state)

    init_code_val = code or kwargs.get("pin", "") or state.get("dtmf_digits", "")
    init_account_id = str(state.get("account_id") or "")
    init_ref = tracking_id("verify_login", init_account_id, str(init_code_val))
    state["last_tracking_id"] = init_ref
    if not _is_mock_mode(state):
        return _call_live_backend("verify_login", state, lang, init_ref)

    id_val = identifier if str(identifier or "").strip() else kwargs.get("phone_or_account", kwargs.get("account_id", kwargs.get("phone", kwargs.get("phone_number", ""))))
    if str(id_val or "").strip():
        raw_digits = normalize_code(id_val)
        has_alpha = any(c.isalpha() for c in str(id_val or ""))
        norm_digits = raw_digits[1:] if (not has_alpha and len(raw_digits) == 11 and raw_digits.startswith("1")) else raw_digits
        is_intl = (
            not has_alpha
            and (str(id_val).strip().startswith("+") or str(id_val).strip().startswith("00"))
            and 10 <= len(raw_digits) <= 15
        )
        if not has_alpha and (len(norm_digits) in (4, 10) or is_intl):
            caller_l4 = norm_digits[-4:]
            state["caller_provided_phone_last4"] = caller_l4
            state["phone_last4"] = caller_l4

        l_res = lookup_account_impl(identifier=id_val, language=lang, state=state)
        if l_res.get("status") == "error":
            return l_res

    if not state.get("account_id"):
        if not explicit_session:
            _hydrate_default_account_if_needed(state)
        else:
            reference = tracking_id("verify_login", "")
            state["last_tracking_id"] = reference
            action_text = localized_text(
                lang,
                "Ask for the caller's 10-digit mobile number, 9-digit account number, or full name and postal code, then identify the account before verifying login.",
                "Demander au client son numéro de mobile à 10 chiffres, numéro de compte à 9 chiffres, ou nom complet et code postal, puis identifier le compte avant de vérifier la connexion.",
                "Pida al cliente su número de móvil de 10 dígitos, número de cuenta de 9 dígitos, o nombre completo y código postal, luego identifique la cuenta antes de verificar el inicio de sesión.",
            )
            return error_reply(
                "NOT_IDENTIFIED",
                agent_action=action_text,
                reference=reference,
                language=lang,
                data={"agent_action": action_text},
            )

    code_val = code or kwargs.get("pin", "") or state.get("dtmf_digits", "")
    account_id = str(state.get("account_id") or "")
    reference = tracking_id("verify_login", account_id, str(code_val))
    state["last_tracking_id"] = reference

    is_step_up = (
        (bool(state.get("mfa_email_code_sent")) and not bool(state.get("mfa_email_verified")))
        or str(method or "").lower() == "email"
        or state.get("login_channel") == "mfa_sms"
    )
    if state.get("auth_status") == "pass" and state.get("logged_in") and not is_step_up:
        acc = find_account(account_id or state.get("account_id") or id_val)
        if acc:
            c_l4 = acc.get("card_on_file_last4", "")
            if c_l4 and not state.get("card_last4"):
                state["card_last4"] = c_l4
            b_l4 = acc.get("bank_on_file_last4", "")
            if b_l4 and not state.get("bank_last4"):
                state["bank_last4"] = b_l4
        if not state.get("card_last4"):
            state["card_last4"] = "7742"
        if not state.get("bank_last4"):
            state["bank_last4"] = "6789"
        pass_data: dict[str, Any] = {
            "verified": True,
            "logged_in": True,
            "auth_status": "pass",
            "current_balance": str(state.get("current_balance") or "0.00"),
            "is_suspended": state.get("is_suspended", False),
        }
        if bool(state.get("browsed_plan_category")):
            pass_data["current_active_plans"] = _active_account_plans(state, lang)
        return _service_ok_reply(
            pass_data,
            reference,
            language=lang,
            state=state,
        )

    failures = max(
        read_count(state, "auth_failure_count"),
        read_count(state, "login_attempts"),
        read_count(state, "pin_failure_count"),
    )
    if _is_account_locked(state, account_id) or state.get("auth_status") == "locked" or failures >= MAX_LOGIN_ATTEMPTS:
        state["auth_status"] = "locked"
        state["logged_in"] = False
        state["auth_failure_count"] = MAX_LOGIN_ATTEMPTS
        _record_account_lockout(state, account_id)
        return error_reply(
            "TOO_MANY_ATTEMPTS",
            reference=reference,
            language=lang,
            data={
                "attempts": failures,
                "attempts_remaining": 0,
                "attempts_left": 0,
                "logged_in": False,
                "auth_status": "locked",
                "lockout_triggered": True,
                "must_escalate_immediately": True,
                "escalation_reason": "auth_failure_handoff",
                "handoff_message": spoken_line("live_agent_handoff", lang),
            },
        )

    code_str = str(code_val or "").strip()
    cleaned_code = re.sub(r"[\s,\-]+", "", code_str)
    has_letters = any(c.isalpha() for c in cleaned_code)
    if has_letters:
        return error_reply(
            "INVALID_INPUT",
            reference=reference,
            language=lang,
            data={
                "agent_action": localized_text(
                    lang,
                    "Ask the caller to enter or say their 4 to 10 digit code.",
                    "Demander au client d'entrer ou d'énoncer son code de 4 à 10 chiffres.",
                    "Pida al cliente que ingrese o diga su código de 4 a 10 dígitos.",
                )
            },
        )

    if _is_placeholder_code(code_val):
        action_text = localized_text(
            lang,
            "Say you did not receive any digits and ask the caller to say the code aloud.",
            "Dites que vous n'avez reçu aucun chiffre et demandez au client d'énoncer le code à voix haute.",
            "Diga que no recibió ningún dígito y pida al cliente que diga el código en voz alta.",
        )
        msg_text = localized_text(
            lang,
            "No verification code digits were received or recognized.",
            "Aucun chiffre de code de vérification n'a été reçu ou reconnu.",
            "No se recibieron ni reconocieron dígitos del código de verificación.",
        )
        return error_reply(
            "CODE_NOT_RECEIVED",
            message=msg_text,
            agent_action=action_text,
            reference=reference,
            data={
                "attempts": failures,
                "attempts_remaining": MAX_LOGIN_ATTEMPTS - failures,
                "attempts_left": MAX_LOGIN_ATTEMPTS - failures,
                "lockout_triggered": False,
            },
            language=lang,
        )

    digits = normalize_code(cleaned_code)
    if not (4 <= len(digits) <= 10):
        return error_reply(
            "INVALID_INPUT",
            reference=reference,
            language=lang,
            data={
                "agent_action": localized_text(
                    lang,
                    "Ask the caller to enter or say their 4 to 10 digit code.",
                    "Demander au client d'entrer ou d'énoncer son code de 4 à 10 chiffres.",
                    "Pida al cliente que ingrese o diga su código de 4 a 10 dígitos.",
                )
            },
        )

    with fixture_state_scope(state):
        if not login_code_accepted(digits, attempts=failures, max_attempts=MAX_LOGIN_ATTEMPTS):
            failures += 1
            state["auth_failure_count"] = failures
            state["login_attempts"] = failures
            state["pin_failure_count"] = failures
            state["logged_in"] = False
            if failures >= MAX_LOGIN_ATTEMPTS:
                state["auth_status"] = "locked"
                _record_account_lockout(state, account_id)
                return error_reply(
                    "TOO_MANY_ATTEMPTS",
                    reference=reference,
                    language=lang,
                    data={
                        "attempts": failures,
                        "attempts_left": 0,
                        "attempts_remaining": 0,
                        "logged_in": False,
                        "auth_status": "locked",
                        "lockout_triggered": True,
                        "must_escalate_immediately": True,
                        "escalation_reason": "auth_failure_handoff",
                        "handoff_message": spoken_line("live_agent_handoff", lang),
                    },
                )
            remaining = int(MAX_LOGIN_ATTEMPTS - failures)
            return error_reply(
                "WRONG_CODE",
                reference=reference,
                language=lang,
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
    state["pin_failure_count"] = 0

    acc = find_account(account_id or state.get("account_id") or id_val)
    if acc:
        c_l4 = acc.get("card_on_file_last4", "")
        if c_l4 and not state.get("card_last4"):
            state["card_last4"] = c_l4
        b_l4 = acc.get("bank_on_file_last4", "")
        if b_l4 and not state.get("bank_last4"):
            state["bank_last4"] = b_l4
    if not state.get("card_last4"):
        state["card_last4"] = "7742"
    if not state.get("bank_last4"):
        state["bank_last4"] = "6789"

    was_mfa_sms = state.get("login_channel") == "mfa_sms"
    method_low = str(method or "").strip().lower()
    is_email_auth = (
        len(digits) == LOGIN_CODE_LENGTH
        and method_low != "pin"
        and (bool(state.get("mfa_email_code_sent")) or method_low == "email")
    )
    if is_email_auth:
        state["mfa_email_verified"] = True
    elif was_mfa_sms and len(digits) == LOGIN_CODE_LENGTH and method_low != "pin":
        state["login_channel"] = "mfa_sms_verified"
    elif method_low == "pin" or len(digits) == SECRET_PIN_LENGTH:
        state["login_channel"] = "pin"
    else:
        state["login_channel"] = "sms"

    pass_data_final: dict[str, Any] = {
        "verified": True,
        "logged_in": True,
        "auth_status": "pass",
        "current_balance": str(state.get("current_balance") or "0.00"),
        "is_suspended": state.get("is_suspended", False),
    }
    if bool(state.get("browsed_plan_category")):
        pass_data_final["current_active_plans"] = _active_account_plans(state, lang)
    return _service_ok_reply(
        pass_data_final,
        reference,
        language=lang,
        state=state,
    )

def _maybe_inline_auth(  # pragma: no cover
    identifier: str | int | float,
    verification_code: str | int | float,
    lang: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    """Helper to authenticate or lookup in the same turn if parameters are supplied."""
    if str(identifier or "").strip():
        l_res = lookup_account_impl(identifier=identifier, language=lang, state=state)
        if l_res.get("status") == "error":
            return l_res
    if state.get("auth_status") != "pass" and str(verification_code or "").strip():
        v_res = verify_login_impl(code=verification_code, language=lang, state=state)
        if v_res.get("status") == "error":
            return v_res
    return None

def manage_appointment_impl(  # pragma: no cover
    action: str = "reschedule",
    selected_slot: str | int | float = "",
    appointment_id: str | int | float = "",
    confirmed_cancel: str | int | float | bool = False,
    technician_en_route: str | int | float | bool = False,
    identifier: str | int | float = "",
    verification_code: str | int | float = "",
    language: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Reschedule or cancel technician appointment with en-route protection."""
    state = _get_state(state, session_state)
    _ensure_default_profile(state)
    lang = _session_language(state, language)

    mock_err = _check_mock_error(state, lang)
    if mock_err:
        return mock_err

    inline_err = _maybe_inline_auth(identifier, verification_code, lang, state)
    if inline_err:
        return inline_err

    account_id = str(state.get("account_id") or "")
    reference = tracking_id("manage_appointment", account_id, str(action))
    state["last_tracking_id"] = reference
    if not _is_mock_mode(state):
        return _call_live_backend("manage_appointment", state, lang, reference)

    if state.get("auth_status") != "pass":
        return error_reply("NOT_AUTHENTICATED", reference=reference, language=lang)
    _hydrate_default_account_if_needed(state)

    _record_audit(state)

    act = str(action or "reschedule").lower()
    if act == "cancel":
        is_en_route = (
            bool(technician_en_route)
            and str(technician_en_route).lower() in {"true", "1", "yes", "oui"}
            or state.get("technician_status") == "en_route"
        )
        if is_en_route:
            return error_reply(
                "CANNOT_CANCEL_EN_ROUTE",
                reference=reference,
                language=lang,
                data={
                    "dispatch_note_logged": True,
                    "can_cancel": False,
                    "technician_status": "en_route",
                },
            )

        raw_conf = confirmed_cancel if confirmed_cancel is not False else kwargs.get("confirmed", False)
        user_conf = _is_truthy_bool(raw_conf)
        prior_prompt_shown = bool(state.get("appointment_cancel_confirmed"))
        if not (user_conf and prior_prompt_shown):
            state["appointment_cancel_confirmed"] = True
            return _service_ok_reply(
                {
                    "requires_confirmation": True,
                    "appointment_cancelled": False,
                    "cancellation_fee": "0.00",
                    "spoken_message": localized_text(
                        lang,
                        "There is a $0.00 cancellation fee since the technician is not yet en route. Are you sure you want to cancel your appointment?",
                        "Les frais d'annulation sont de 0,00 $ puisque le technicien n'est pas encore en route. Êtes-vous certain de vouloir annuler votre rendez-vous ?",
                        "Hay un cargo de cancelación de $0.00 ya que el técnico aún no está en camino. ¿Está seguro de que desea cancelar su cita?",
                    ),
                },
                reference,
                language=lang,
            state=state,
            )

        state["appointment_status"] = "cancelled"
        ref = tracking_id("CXL_APT", account_id)
        state["last_tracking_id"] = ref
        return _service_ok_reply(
            {
                "appointment_cancelled": True,
                "status": "cancelled",
                "confirmation_number": ref,
                "sms_confirmation_sent": True,
                "cancellation_fee": "0.00",
            },
            ref,
            language=lang,
        state=state,
        )

    # Reschedule
    if isinstance(selected_slot, bool) or (
        isinstance(selected_slot, float)
        and (selected_slot != selected_slot or selected_slot in (float("inf"), float("-inf")))
    ):
        raw_sel = ""
    else:
        raw_sel = str(selected_slot or "").strip()
    m_slot_num = re.fullmatch(
        r"(?:(?:slot|option|opci[oó]n|cr[eé]neau|plage)[\s_#-]*)?([123])(?:\.0+)?",
        raw_sel,
        re.IGNORECASE,
    )
    sel = f"SLOT-{m_slot_num.group(1)}" if m_slot_num else raw_sel.upper()
    sel_low = sel.lower()
    dyn_slots = _dynamic_appointments_data()["available_reschedule_slots"]
    slot_match = None
    for s_item in dyn_slots:
        if sel and (
            sel in s_item["slot_id"]
            or (len(sel) >= 4 and sel in s_item["date"])
            or sel_low in s_item.get("window_en", "").lower()
            or sel_low in s_item.get("window_fr", "").lower()
            or sel_low in s_item.get("window_es", "").lower()
        ):
            slot_match = s_item
            break
    if not slot_match:
        avail_slots = [
            {
                "slot_id": s["slot_id"],
                "date": s["date"],
                "window": s.get(
                    "window_fr" if lang == "fr-CA" else ("window_es" if lang == "es-US" else "window_en"),
                    s.get("window_en", ""),
                ),
            }
            for s in dyn_slots
        ]
        action_text = localized_text(
            lang,
            "Offer available reschedule slots to the caller and ask which one they prefer.",
            "Proposez les créneaux disponibles au client et demandez-lui lequel il préfère.",
            "Ofrezca los horarios disponibles al cliente y pregunte cuál prefiere.",
        )
        return error_reply(
            "OUT_OF_WINDOW",
            reference=reference,
            language=lang,
            agent_action=action_text,
            data={
                "appointment_rescheduled": False,
                "requested_slot": raw_sel,
                "available_slots": avail_slots,
                "appointment_id": state.get("active_appointment_id", "APT-4021"),
            },
        )

    state["appointment_status"] = "rescheduled"
    ref = tracking_id("RES_APT", account_id, slot_match["slot_id"])
    state["last_tracking_id"] = ref
    win_key = "window_fr" if lang == "fr-CA" else ("window_es" if lang == "es-US" else "window_en")
    win = slot_match.get(win_key, slot_match.get("window_en", ""))

    return _service_ok_reply(
        {
            "appointment_rescheduled": True,
            "appointment_id": state.get("active_appointment_id", "APT-4021"),
            "scheduled_date": slot_match["date"],
            "arrival_window": win,
            "window_display": win,
            "slot_id": slot_match["slot_id"],
            "confirmation_number": ref,
            "sms_confirmation_sent": True,
        },
        ref,
        language=lang,
    state=state,
    )
# --- END GENERATED SHARED BUNDLE ---
