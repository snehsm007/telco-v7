"""CXAS tool wrapper for check_regional_outage. Before calling this tool, speak a brief conversational pacing phrase."""

from typing import Any



def check_regional_outage(
    postal_code: str | int | float = "",
    service_type: str = "internet",
    subscribe_sms: str | int | float | bool = False,
    language: str = "",
) -> dict[str, Any]:
    """Check network infrastructure status by postal code, returning outage details or normal status.

    Args:
      postal_code: The 6-character Canadian postal code or 5-digit ZIP code.
      service_type: Type of service to inspect, defaulting to 'internet'.
      subscribe_sms: Flag or string indicating whether to subscribe to SMS restoration updates.
      language: Preferred language code such as 'en-US', 'fr-CA', or 'es-US'.

    Returns:
      dict: status, data containing outage status and details, tracking reference, and agent_action on errors.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return check_regional_outage_impl(
        postal_code=postal_code,
        service_type=service_type,
        subscribe_sms=subscribe_sms,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.services import check_regional_outage_impl
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

OUTAGE_POSTAL_PREFIXES: tuple[str, ...] = ("H3Z", "G1R")  # pragma: no cover

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
            "Verify the caller's identity with send_login_code and verify_login, then retry.",
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
            "Vérifier l'identité du client avec send_login_code et verify_login, puis réessayer.",
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
            "Verifique la identidad del cliente con send_login_code y verify_login, luego reintente.",
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
    state: dict[str, Any] | None,
    fact_name: str,
    default: Any = None,
) -> Any:
    """Retrieve a backend fixture fact from session state (checking fx_* and canonical variables),

    falling back to realistic defaults. Treats None and "" as unset.
    """
    eff = state if isinstance(state, dict) else _ACTIVE_FIXTURE_STATE.get()
    if not isinstance(eff, dict) or not fact_name:
        return default

    base = fact_name[3:] if fact_name.startswith("fx_") else fact_name
    candidates = (f"fx_{base}", fact_name, base)
    for k in candidates:
        if k in eff:
            val = eff.get(k)
            if val is not None and val != "":
                return val
    return default

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

def _record_audit(state: dict[str, Any]) -> None:  # pragma: no cover
    """Increment audit log count inside auth, mutation, and handover tools."""
    state["audit_log_count"] = read_count(state, "audit_log_count") + 1

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

def localized_text(language: str | None, en: str, fr: str, es: str = "") -> str:  # pragma: no cover
    """Return text localized for the caller's target language."""
    loc = resolve_copy_locale(language)
    if loc == "fr-CA":
        return fr
    if loc == "es-US":
        return es or en
    return en

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

def check_regional_outage_impl(  # pragma: no cover
    postal_code: str | int | float = "",
    service_type: str = "internet",
    subscribe_sms: str | int | float | bool = False,
    language: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Check network infrastructure status by postal code."""
    state = _get_state(state, session_state)
    _ensure_default_profile(state)
    lang = _session_language(state, language)

    mock_err = _check_mock_error(state, lang)
    if mock_err:
        return mock_err

    _record_audit(state)

    pc = (str(postal_code or state.get("postal_code") or "")).strip().upper()
    reference = tracking_id("check_regional_outage", pc)
    state["last_tracking_id"] = reference

    if not pc:
        return error_reply(
            "MISSING_INPUT",
            reference=reference,
            language=lang,
            data={
                "agent_action": localized_text(
                    lang,
                    "Ask the caller for their 6-character postal code or 5-digit ZIP code.",
                    "Demander au client son code postal à 6 caractères.",
                    "Pida al cliente su código postal.",
                )
            },
        )

    state["postal_code"] = str(pc)
    clean_pc = pc.replace(" ", "")
    is_outage = any(clean_pc.startswith(p) for p in OUTAGE_POSTAL_PREFIXES)
    state["outage_active"] = is_outage

    if is_outage:
        sms_sub = bool(subscribe_sms) and str(subscribe_sms).lower() in {"true", "1", "yes", "oui"}
        if sms_sub:
            state["outage_sms_subscribed"] = True
        out_line = spoken_line("outage_active", lang)
        sub_line = localized_text(
            lang,
            "You have been subscribed to SMS restoration updates.",
            "Vous avez été abonné aux notifications de rétablissement par SMS.",
            "Se ha suscrito a las actualizaciones de restauración por SMS.",
        )
        return ok_reply(
            {
                "outage_active": True,
                "region": "Region-A",
                "estimated_restoration_hours": 4,
                "sms_subscribed": sms_sub,
                "verbatim_outage_message": out_line,
                "spoken_message": sub_line if sms_sub else out_line,
            },
            reference,
            language=lang,
        )

    offer_line = spoken_line("outage_none_offer_sms", lang)
    return ok_reply(
        {
            "outage_active": False,
            "network_status": "normal",
            "next_step": "offer_sms_troubleshooting_guide",
            "spoken_message": offer_line,
            "agent_action": localized_text(
                lang,
                "Say spoken_message; if the caller agrees call run_troubleshooting_and_sms with the on-file or stated mobile.",
                "Dire spoken_message; si le client accepte, appeler run_troubleshooting_and_sms avec le numéro de mobile au dossier ou mentionné.",
                "Diga spoken_message; si el cliente acepta, llame a run_troubleshooting_and_sms con el móvil registrado o mencionado.",
            ),
            "next_step_guidance": localized_text(
                lang,
                "No network outage detected. Proceed with troubleshooting.",
                "Aucune panne réseau détectée. Poursuivre le dépannage.",
                "No se detectó interrupción de red. Continúe con la resolución de problemas.",
            ),
        },
        reference,
        language=lang,
    )
# --- END GENERATED SHARED BUNDLE ---
