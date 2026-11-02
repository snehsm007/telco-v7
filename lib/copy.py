"""Canonical multilingual copy and error wording dictionary."""

from __future__ import annotations

import re
from typing import Any

SUPPORTED_COPY_LOCALES: tuple[str, ...] = ("en-US", "fr-CA", "es-US")

WORLD_LANGUAGE_NAMES: dict[str, str] = {
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


def resolve_locale(language: str | None) -> str:
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


def resolve_copy_locale(language: str | None) -> str:
    """Pick one of the three primary supported copy locales."""
    loc = resolve_locale(language)
    if loc == "fr-CA":
        return "fr-CA"
    if loc == "es-US":
        return "es-US"
    return "en-US"


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


def spoken_line(key: str, language: str | None = "en-US", *args: object, **slots: object) -> str:
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


LOCALIZED_ERROR_DEFAULTS: dict[str, dict[str, tuple[str, str]]] = {
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


def localized_text(language: str | None, en: str, fr: str, es: str = "") -> str:
    """Return text localized for the caller's target language."""
    loc = resolve_copy_locale(language)
    if loc == "fr-CA":
        return fr
    if loc == "es-US":
        return es or en
    return en


AGENT_VERBATIM_KEYS: dict[str, tuple[str, ...]] = {
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

CATALOG_COPY: dict[str, dict[str, str]] = {
    "Account credit": {
        "en-US": "Account credit",
        "fr-CA": "Crédit au compte",
        "es-US": "Crédito en cuenta",
    },
    "Wi-Fi 6 Gateway (included at $0/month)": {
        "en-US": "Wi-Fi 6 Gateway (included at $0/month)",
        "fr-CA": "Borne Wi-Fi 6 (incluse à 0 $/mois)",
        "es-US": "Módem Wi-Fi 6 (incluido a $0/mes)",
    },
    "Wi-Fi 6 Giga Hub with whole-home mesh pod (included at $0/month)": {
        "en-US": "Wi-Fi 6 Giga Hub with whole-home mesh pod (included at $0/month)",
        "fr-CA": "Borne Wi-Fi 6 Giga Hub avec capsule Wi-Fi intégrale (incluse à 0 $/mois)",
        "es-US": "Módem Wi-Fi 6 Giga Hub con repetidor mesh para todo el hogar (incluido a $0/mes)",
    },
    "4K TV Terminal (included)": {
        "en-US": "4K TV Terminal (included)",
        "fr-CA": "Terminal Télé 4K (inclus)",
        "es-US": "Terminal de TV 4K (incluido)",
    },
    "Home Phone Terminal": {
        "en-US": "Home Phone Terminal",
        "fr-CA": "Terminal de téléphonie résidentielle",
        "es-US": "Terminal de telefonía residencial",
    },
    "SIM / eSIM card (included at $0)": {
        "en-US": "SIM / eSIM card (included at $0)",
        "fr-CA": "Carte SIM / eSIM (incluse à 0 $)",
        "es-US": "Tarjeta SIM / eSIM (incluida a $0)",
    },
    "Smart Security Hub": {
        "en-US": "Smart Security Hub",
        "fr-CA": "Centrale de sécurité intelligente",
        "es-US": "Centro de seguridad inteligente",
    },
    "Wi-Fi 6 Giga Hub gateway (included at $0/month); compatible with all standard Wi-Fi devices and whole-home mesh pods": {
        "en-US": "Wi-Fi 6 Giga Hub gateway (included at $0/month); compatible with all standard Wi-Fi devices and whole-home mesh pods",
        "fr-CA": "Borne Wi-Fi 6 Giga Hub (incluse à 0 $/mois); compatible avec tous les appareils Wi-Fi standard et les capsules Wi-Fi",
        "es-US": "Módem Wi-Fi 6 Giga Hub (incluido a $0/mes); compatible con todos los dispositivos Wi-Fi estándar y repetidores mesh",
    },
    "Compatible with all unlocked 4G LTE and 5G smartphones": {
        "en-US": "Compatible with all unlocked 4G LTE and 5G smartphones",
        "fr-CA": "Compatible avec tous les téléphones intelligents 4G LTE et 5G déverrouillés",
        "es-US": "Compatible con todos los teléfonos inteligentes 4G LTE y 5G desbloqueados",
    },
    "Compatible with Fibe TV 4K receiver and mobile TV app": {
        "en-US": "Compatible with Fibe TV 4K receiver and mobile TV app",
        "fr-CA": "Compatible avec le récepteur Télé Fibe 4K et l'application mobile",
        "es-US": "Compatible con el receptor Fibe TV 4K y la aplicación móvil de TV",
    },
    "Standard analog phone jack compatible": {
        "en-US": "Standard analog phone jack compatible",
        "fr-CA": "Compatible avec les prises téléphoniques analogiques standard",
        "es-US": "Compatible con conector telefónico analógico estándar",
    },
    "Compatible with Telco smart security sensors and mobile app": {
        "en-US": "Compatible with Telco smart security sensors and mobile app",
        "fr-CA": "Compatible avec les capteurs de sécurité intelligents Telco et l'application mobile",
        "es-US": "Compatible con los sensores de seguridad inteligentes de Telco y la aplicación móvil",
    },
}


def localize_catalog_copy(text: str, language: str | None = "en-US") -> str:
    """Return catalog copy localized for the caller's target language."""
    loc = resolve_copy_locale(language)
    entry = CATALOG_COPY.get(text)
    if entry:
        return entry.get(loc, text)
    return text

