"""CXAS tool wrapper for browse_plans_and_coverage. Before calling this tool, speak a brief conversational pacing phrase."""

from typing import Any



def browse_plans_and_coverage(
    category: str = "internet",
    postal_code: str | int | float = "",
    service_address: str = "",
    address: str = "",
    max_budget: str | int | float = "",
    language: str = "",
) -> dict[str, Any]:
    """Retrieve curated plans and verify network coverage without requiring PIN or OTP login.

    Args:
      category: Plan service category ('internet', 'tv', 'mobility').
      postal_code: The 6-character Canadian postal code or 5-digit ZIP code.
      service_address: Customer street address for coverage check.
      address: Alternative customer street address.
      max_budget: Maximum monthly price ceiling to filter plans.
      language: Preferred language code such as 'en-US', 'fr-CA', or 'es-US'.

    Returns:
      dict: status, data containing shortlisted plans, coverage availability, contract terms, tracking reference, and agent_action on errors.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return browse_plans_and_coverage_impl(
        category=category,
        postal_code=postal_code,
        service_address=service_address,
        address=address,
        max_budget=max_budget,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.services import browse_plans_and_coverage_impl
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

FAKE_ADDON_CATALOG: list[dict[str, Any]] = [  # pragma: no cover
    {
        "id": "ADDON-SPORTS",
        "name": "Sports Ultimate Pack",
        "monthly_price": 18.00,
        "price_display": "18.00",
        "category": "tv",
        "description_en": "Full access to live professional sports coverage, games, and replays including TSN 1-5, Sportsnet, ESPN, FS1, RDS, NBA TV, MLB Network, NFL Network, Golf Channel, and regional sports networks in 4K/HD",
        "description_fr": "Accès complet aux matchs sportifs professionnels en direct et rediffusions comprenant TSN 1-5, Sportsnet, ESPN, FS1, RDS, NBA TV, MLB Network, NFL Network, Golf Channel et les réseaux sportifs régionaux en 4K/HD",
        "description_es": "Acceso completo a cobertura deportiva profesional en vivo y repeticiones incluyendo TSN 1-5, Sportsnet, ESPN, FS1, RDS, NBA TV, MLB Network, NFL Network, Golf Channel y redes deportivas regionales en 4K/HD",
        "included_channels": "TSN 1-5, Sportsnet, ESPN, FS1, RDS, NBA TV, MLB Network, NFL Network, Golf Channel, and regional sports networks in 4K/HD",
        "combined_monthly_with_tv_starter": "43.00",
    },
    {
        "id": "ADDON-ROAM",
        "name": "Roam USA Daily Pass",
        "monthly_price": 14.00,
        "price_display": "14.00",
        "category": "mobility",
        "description_en": "Use your plan data and talk daily while travelling across the United States",
        "description_fr": "Utilisez vos données et vos appels lors de vos déplacements aux États-Unis",
        "description_es": "Use los datos y minutos de su plan mientras viaja por los Estados Unidos",
    },
    {
        "id": "ADDON-SECURITY",
        "name": "Advanced Online Protection",
        "monthly_price": 6.00,
        "price_display": "6.00",
        "category": "internet",
        "description_en": "Real-time threat blocking, identity monitoring, and parental controls",
        "description_fr": "Blocage des cybermenaces, surveillance de l'identité et contrôle parental",
        "description_es": "Bloqueo de amenazas, monitoreo de identidad y control parental",
    },
]

FAKE_PLAN_CATALOG: dict[str, list[dict[str, Any]]] = {  # pragma: no cover
    "internet": [
        {
            "id": "NET-STARTER",
            "name": "Fiber Internet 100",
            "monthly_price": 45.00,
            "price_display": "45.00",
            "speed_or_data": "100 Mbps",
            "download_speed": "100 Mbps",
            "upload_speed": "100 Mbps",
            "included_modem": "Wi-Fi 6 Gateway (included at $0/month)",
            "modem_compatibility": "Wi-Fi 6 Giga Hub gateway (included at $0/month); compatible with all standard Wi-Fi devices and whole-home mesh pods",
            "features_en": "Unlimited downloads, Wi-Fi 6 gateway included, no annual contract",
            "features_fr": "Téléchargements illimités, borne Wi-Fi 6 incluse, sans contrat annuel",
            "features_es": "Descargas ilimitadas, módem Wi-Fi 6 incluido, sin contrato anual",
            "latency_en": "sub-15ms typical latency with <2ms jitter",
            "latency_fr": "latence typique inférieure à 15 ms avec gigue inférieure à 2 ms",
            "latency_es": "latencia típica inferior a 15 ms con fluctuación inferior a 2 ms",
            "technical_specifications_en": "Symmetrical fiber speeds, sub-15ms low latency, <2ms jitter, 99.9% network availability with no business SLA required",
            "technical_specifications_fr": "Vitesses symétriques par fibre, faible latence inférieure à 15 ms, gigue inférieure à 2 ms, disponibilité réseau de 99,9 % sans entente de niveau de service commerciale requise",
            "technical_specifications_es": "Velocidades simétricas por fibra, baja latencia inferior a 15 ms, fluctuación inferior a 2 ms, disponibilidad de red del 99.9 % sin necesidad de acuerdo comercial",
            "sla_or_guarantee_en": "99.9% network availability during peak hours",
            "sla_or_guarantee_fr": "Disponibilité du réseau de 99,9 % pendant les heures de pointe",
            "sla_or_guarantee_es": "Disponibilidad de red del 99.9 % durante horas pico",
            "contract_required": False,
            "activation_fee": 0.0,
        },
        {
            "id": "NET-PLUS",
            "name": "Fiber Internet 500",
            "monthly_price": 75.00,
            "price_display": "75.00",
            "speed_or_data": "500 Mbps",
            "download_speed": "500 Mbps",
            "upload_speed": "500 Mbps",
            "included_modem": "Wi-Fi 6 Gateway (included at $0/month)",
            "modem_compatibility": "Wi-Fi 6 Giga Hub gateway (included at $0/month); compatible with all standard Wi-Fi devices and whole-home mesh pods",
            "features_en": "Ultra-fast streaming and gaming, Wi-Fi 6 gateway, zero activation fee",
            "features_fr": "Diffusion et jeux ultra-rapides, borne Wi-Fi 6, aucuns frais d'activation",
            "features_es": "Transmisión y juegos ultra rápidos, módem Wi-Fi 6, cero costo de activación",
            "latency_en": "sub-15ms typical latency with <2ms jitter",
            "latency_fr": "latence typique inférieure à 15 ms avec gigue inférieure à 2 ms",
            "latency_es": "latencia típica inferior a 15 ms con fluctuación inferior a 2 ms",
            "technical_specifications_en": "Symmetrical fiber speeds, sub-15ms low latency, <2ms jitter, 99.9% network availability with no business SLA required",
            "technical_specifications_fr": "Vitesses symétriques par fibre, faible latence inférieure à 15 ms, gigue inférieure à 2 ms, disponibilité réseau de 99,9 % sans entente de niveau de service commerciale requise",
            "technical_specifications_es": "Velocidades simétricas por fibra, baja latencia inferior a 15 ms, fluctuación inferior a 2 ms, disponibilidad de red del 99.9 % sin necesidad de acuerdo comercial",
            "sla_or_guarantee_en": "99.9% network availability during peak hours",
            "sla_or_guarantee_fr": "Disponibilité du réseau de 99,9 % pendant les heures de pointe",
            "sla_or_guarantee_es": "Disponibilidad de red del 99.9 % durante horas pico",
            "contract_required": False,
            "activation_fee": 0.0,
        },
        {
            "id": "NET-GIG",
            "name": "Gigabit Fiber",
            "monthly_price": 95.00,
            "price_display": "95.00",
            "speed_or_data": "1 Gbps",
            "download_speed": "1 Gbps",
            "upload_speed": "1 Gbps",
            "included_modem": "Wi-Fi 6 Giga Hub with whole-home mesh pod (included at $0/month)",
            "modem_compatibility": "Wi-Fi 6 Giga Hub gateway (included at $0/month); compatible with all standard Wi-Fi devices and whole-home mesh pods",
            "features_en": "Gigabit symmetrical speed, whole-home mesh pod, 24/7 priority support",
            "features_fr": "Vitesse symétrique gigabit, relais maillé pour toute la maison, soutien prioritaire",
            "features_es": "Velocidad simétrica de un gigabit, extensor de malla, soporte prioritario",
            "latency_en": "sub-15ms typical latency with <2ms jitter",
            "latency_fr": "latence typique inférieure à 15 ms avec gigue inférieure à 2 ms",
            "latency_es": "latencia típica inferior a 15 ms con fluctuación inferior a 2 ms",
            "technical_specifications_en": "Symmetrical fiber speeds, sub-15ms low latency, <2ms jitter, 99.9% network availability with no business SLA required",
            "technical_specifications_fr": "Vitesses symétriques par fibre, faible latence inférieure à 15 ms, gigue inférieure à 2 ms, disponibilité réseau de 99,9 % sans entente de niveau de service commerciale requise",
            "technical_specifications_es": "Velocidades simétricas por fibra, baja latencia inferior a 15 ms, fluctuación inferior a 2 ms, disponibilidad de red del 99.9 % sin necesidad de acuerdo comercial",
            "sla_or_guarantee_en": "99.9% network availability during peak hours",
            "sla_or_guarantee_fr": "Disponibilité du réseau de 99,9 % pendant les heures de pointe",
            "sla_or_guarantee_es": "Disponibilidad de red del 99.9 % durante horas pico",
            "contract_required": False,
            "activation_fee": 0.0,
        },
    ],
    "mobility": [
        {
            "id": "MOB-LITE",
            "name": "5G Essential 25GB",
            "monthly_price": 45.00,
            "price_display": "45.00",
            "speed_or_data": "25 GB 5G data",
            "download_speed": "Up to 250 Mbps (5G)",
            "upload_speed": "Up to 50 Mbps",
            "included_modem": "SIM / eSIM card (included at $0)",
            "modem_compatibility": "Compatible with all unlocked 4G LTE and 5G smartphones",
            "features_en": "Unlimited Canada-wide talk and text, 25GB full-speed 5G data",
            "features_fr": "Appels et textos illimités partout au Canada, 25 Go de données 5G pleine vitesse",
            "features_es": "Llamadas y mensajes ilimitados en todo Canadá, 25GB de datos 5G de alta velocidad",
            "contract_required": False,
            "activation_fee": 0.0,
        },
        {
            "id": "MOB-UNLTD",
            "name": "5G Unlimited 60GB",
            "monthly_price": 55.00,
            "price_display": "55.00",
            "speed_or_data": "60 GB 5G+ data",
            "download_speed": "Up to 1 Gbps (5G+)",
            "upload_speed": "Up to 100 Mbps",
            "included_modem": "SIM / eSIM card (included at $0)",
            "modem_compatibility": "Compatible with all unlocked 4G LTE and 5G smartphones",
            "features_en": "Unlimited talk, text and 60GB data, hotspot sharing, visual voicemail",
            "features_fr": "Appels, textos et 60 Go de données illimitées, partage de connexion, messagerie vocale visuelle",
            "features_es": "Llamadas, mensajes y 60GB de datos ilimitados, compartir internet, buzón de voz visual",
            "contract_required": False,
            "activation_fee": 0.0,
        },
        {
            "id": "MOB-PREM",
            "name": "5G North America Unlimited",
            "monthly_price": 75.00,
            "price_display": "75.00",
            "speed_or_data": "100 GB 5G+ data",
            "download_speed": "Up to 1 Gbps (5G+ ultra)",
            "upload_speed": "Up to 100 Mbps",
            "included_modem": "SIM / eSIM card (included at $0)",
            "modem_compatibility": "Compatible with all unlocked 4G LTE and 5G smartphones",
            "features_en": "Seamless roaming across Canada and the US, 100GB high speed",
            "features_fr": "Itinérance fluide partout au Canada et aux États-Unis, 100 Go haute vitesse",
            "features_es": "Itinerancia sin interrupciones en Canadá y EE. UU., 100GB de alta velocidad",
            "contract_required": False,
            "activation_fee": 0.0,
        },
    ],
    "tv": [
        {
            "id": "TV-STARTER",
            "name": "Fibe TV Starter",
            "monthly_price": 25.00,
            "price_display": "25.00",
            "speed_or_data": "35+ channels",
            "download_speed": "N/A",
            "upload_speed": "N/A",
            "included_modem": "4K TV Terminal (included)",
            "modem_compatibility": "Compatible with Fibe TV 4K receiver and mobile TV app",
            "features_en": "Major national networks, local news, TV app access on all devices",
            "features_fr": "Principaux réseaux nationaux, nouvelles locales, accès à l'application télé",
            "features_es": "Principales cadenas nacionales, noticias locales, acceso a la app de televisión",
            "contract_required": False,
            "activation_fee": 0.0,
        },
        {
            "id": "TV-MAX",
            "name": "Fibe TV Complete",
            "monthly_price": 65.00,
            "price_display": "65.00",
            "speed_or_data": "100+ channels",
            "download_speed": "N/A",
            "upload_speed": "N/A",
            "included_modem": "4K TV Terminal (included)",
            "modem_compatibility": "Compatible with Fibe TV 4K receiver and mobile TV app",
            "features_en": "Includes premium entertainment, specialty lifestyle, and 4K recording",
            "features_fr": "Comprend divertissement premium, chaînes spécialisées et enregistreur 4K",
            "features_es": "Incluye entretenimiento premium, canales especializados y grabador 4K",
            "contract_required": False,
            "activation_fee": 0.0,
        },
    ],
    "homephone": [
        {
            "id": "PHONE-CAN",
            "name": "Home Phone Unlimited Canada",
            "monthly_price": 20.00,
            "price_display": "20.00",
            "speed_or_data": "Unlimited local & nationwide",
            "download_speed": "N/A",
            "upload_speed": "N/A",
            "included_modem": "Home Phone Terminal",
            "modem_compatibility": "Standard analog phone jack compatible",
            "features_en": "Caller ID, call waiting, voicemail to email, crystal-clear voice",
            "features_fr": "Afficheur, appel en attente, messagerie vocale par courriel, voix limpide",
            "features_es": "Identificador de llamadas, llamada en espera, correo de voz por email",
            "contract_required": False,
            "activation_fee": 0.0,
        },
    ],
    "smarthome": [
        {
            "id": "SMART-PROTECT",
            "name": "Smart Home Security Essentials",
            "monthly_price": 30.00,
            "price_display": "30.00",
            "speed_or_data": "Monitored security",
            "download_speed": "N/A",
            "upload_speed": "N/A",
            "included_modem": "Smart Security Hub",
            "modem_compatibility": "Compatible with Telco smart security sensors and mobile app",
            "features_en": "24/7 central station monitoring, door sensors, motion detector, smartphone control",
            "features_fr": "Surveillance centrale 24/7, capteurs de porte, détecteur de mouvement, contrôle mobile",
            "features_es": "Monitoreo central 24/7, sensores de puerta, detector de movimiento, control móvil",
            "contract_required": False,
            "activation_fee": 0.0,
        },
    ],
}

SALES_TAX_RATE: float = 0.15  # pragma: no cover

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

def localized_text(language: str | None, en: str, fr: str, es: str = "") -> str:  # pragma: no cover
    """Return text localized for the caller's target language."""
    loc = resolve_copy_locale(language)
    if loc == "fr-CA":
        return fr
    if loc == "es-US":
        return es or en
    return en

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
    if not language and data and callable(getattr(data, "get", None)):
        language = data.get("language") or data.get("fx_language") or data.get("preferred_language")
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

def normalize_money_str(amount: str | int | float | Decimal) -> str:  # pragma: no cover
    """Parse human/ASR money input (including French decimal comma) into a canonical decimal string."""
    if amount is None or isinstance(amount, bool):
        raise ValueError(f"Unsupported amount: {amount!r}")
    if isinstance(amount, float) and (amount != amount or amount in (float("inf"), float("-inf"))):
        raise ValueError(f"Non-finite amount: {amount!r}")
    if isinstance(amount, (int, float, Decimal)):
        d = Decimal(str(amount))
        if not d.is_finite():
            raise ValueError(f"Non-finite amount: {amount!r}")
        return str(d)
    s = str(amount).strip()
    if not s:
        raise ValueError("Empty amount")
    # Strip currency symbols and codes ($, CAD, USD, EUR) at edges
    s = re.sub(r"(?i)\b(?:cad|usd|eur|dollars?)\b", "", s)
    s = s.replace("$", "").replace("\u00a0", " ").strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(" ", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+", s):
            # 1,000 -> 1000
            s = s.replace(",", "")
        elif re.search(r",\d{1,2}$", s):
            # 15,00 or 9 876,50 -> comma as decimal separator
            s = s.replace(" ", "")
            idx = s.rfind(",")
            s = s[:idx].replace(",", "") + "." + s[idx + 1 :]
        else:
            raise ValueError(f"Invalid comma amount: {amount!r}")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        raise ValueError(f"Malformed numeric amount: {amount!r}")
    return s

def _parse_positive_money(val: Any) -> Decimal | None:  # pragma: no cover
    """Parse positive money amount, returning Decimal or None on invalid input."""
    try:
        norm = normalize_money_str(val)
        d = Decimal(norm)
        if not d.is_finite() or d <= 0:
            return None
        return d
    except Exception:
        return None

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
        existing = (
            state.get("language")
            or state.get("fx_language")
            or state.get("preferred_language")
        )
        if existing and str(existing).strip():
            current = resolve_copy_locale(str(existing))
            if not state.get("language") and current != "en-US":
                state["language"] = current

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

def display_amount(value: Any) -> str:  # pragma: no cover
    """Format money for speech: 12.5 -> "12.50" (two decimals, half-up rounding)."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not an amount: {value!r}")
    try:
        norm = normalize_money_str(value)
        amount = Decimal(norm)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"not an amount: {value!r}")
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

CATALOG_COPY: dict[str, dict[str, str]] = {  # pragma: no cover
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

def localize_catalog_copy(text: str, language: str | None = "en-US") -> str:  # pragma: no cover
    """Return catalog copy localized for the caller's target language."""
    loc = resolve_copy_locale(language)
    entry = CATALOG_COPY.get(text)
    if entry:
        return entry.get(loc, text)
    return text

def browse_plans_and_coverage_impl(  # pragma: no cover
    category: str = "internet",
    postal_code: str | int | float = "",
    service_address: str = "",
    address: str = "",
    max_budget: str | int | float = "",
    language: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retrieve 2-3 curated plans and check network coverage without PIN/OTP."""
    state = _get_state(state, session_state)
    _ensure_default_profile(state)
    lang = _session_language(state, language)

    mock_err = _check_mock_error(state, lang)
    if mock_err:
        return mock_err

    cat = str(category or "internet").lower()
    pc = (str(postal_code or state.get("postal_code") or "")).strip().upper()
    reference = tracking_id("browse_plans_and_coverage", cat, pc)
    state["last_tracking_id"] = reference
    if not _is_mock_mode(state):
        return _call_live_backend("browse_plans_and_coverage", state, lang, reference)

    _record_audit(state)

    pc = (str(postal_code or state.get("postal_code") or "")).strip().upper()
    if pc:
        state["postal_code"] = pc
    s_addr = str(service_address or address or kwargs.get("address") or state.get("service_address") or "").strip()
    if s_addr:
        state["service_address"] = s_addr

    cat = str(category or "internet").lower()
    state["browsed_plan_category"] = cat
    catalog = FAKE_PLAN_CATALOG.get(cat, FAKE_PLAN_CATALOG["internet"])

    max_b = _parse_positive_money(max_budget)
    tax_rate = Decimal(str(SALES_TAX_RATE))

    feat_lang = "fr" if lang == "fr-CA" else ("es" if lang == "es-US" else "en")
    desc_lang = "fr" if lang == "fr-CA" else ("es" if lang == "es-US" else "en")

    shortlist = []
    for p in catalog:
        try:
            p_price = Decimal(str(p.get("monthly_price", 0)))
        except Exception:
            p_price = Decimal(0)
        p_tax = (p_price * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        p_total = p_price + p_tax
        if max_b is not None and p_price > max_b:
            continue
        p_copy = {k: v for k, v in p.items() if not k.endswith(("_en", "_fr", "_es"))}
        p_copy["features"] = p.get(f"features_{feat_lang}", p.get("features_en", ""))
        if f"latency_{feat_lang}" in p or "latency_en" in p:
            p_copy["latency"] = p.get(f"latency_{feat_lang}", p.get("latency_en", ""))
        if f"technical_specifications_{feat_lang}" in p or "technical_specifications_en" in p:
            p_copy["technical_specifications"] = p.get(f"technical_specifications_{feat_lang}", p.get("technical_specifications_en", ""))
        if f"sla_or_guarantee_{feat_lang}" in p or "sla_or_guarantee_en" in p:
            p_copy["sla_or_guarantee"] = p.get(f"sla_or_guarantee_{feat_lang}", p.get("sla_or_guarantee_en", ""))
        if "included_modem" in p_copy:
            p_copy["included_modem"] = localize_catalog_copy(p_copy["included_modem"], lang)
        if "modem_compatibility" in p_copy:
            p_copy["modem_compatibility"] = localize_catalog_copy(p_copy["modem_compatibility"], lang)
        p_copy["estimated_tax"] = str(p_tax)
        p_copy["estimated_total_monthly"] = str(p_total)
        p_copy["monthly_total_with_tax"] = str(p_total)
        if max_b is not None:
            p_copy["within_budget_before_tax"] = bool(p_price <= max_b)
            p_copy["within_budget_after_tax"] = bool(p_total <= max_b)
        p_copy.setdefault("contract_required", False)
        shortlist.append(p_copy)
        if len(shortlist) >= 3:
            break
    # A stated budget is a monthly ceiling the caller pays, so when any plan
    # fits after tax, offer only those (a $55 plan is $63.25 with tax).
    if max_b is not None and any(p.get("within_budget_after_tax") for p in shortlist):
        shortlist = [p for p in shortlist if p.get("within_budget_after_tax")]
    if not shortlist:
        for p in catalog[:2]:
            p_copy = {k: v for k, v in p.items() if not k.endswith(("_en", "_fr", "_es"))}
            p_price = Decimal(str(p.get("monthly_price", 0)))
            p_tax = (p_price * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            p_total = p_price + p_tax
            p_copy["features"] = p.get(f"features_{feat_lang}", p.get("features_en", ""))
            if f"latency_{feat_lang}" in p or "latency_en" in p:
                p_copy["latency"] = p.get(f"latency_{feat_lang}", p.get("latency_en", ""))
            if f"technical_specifications_{feat_lang}" in p or "technical_specifications_en" in p:
                p_copy["technical_specifications"] = p.get(f"technical_specifications_{feat_lang}", p.get("technical_specifications_en", ""))
            if f"sla_or_guarantee_{feat_lang}" in p or "sla_or_guarantee_en" in p:
                p_copy["sla_or_guarantee"] = p.get(f"sla_or_guarantee_{feat_lang}", p.get("sla_or_guarantee_en", ""))
            if "included_modem" in p_copy:
                p_copy["included_modem"] = localize_catalog_copy(p_copy["included_modem"], lang)
            if "modem_compatibility" in p_copy:
                p_copy["modem_compatibility"] = localize_catalog_copy(p_copy["modem_compatibility"], lang)
            p_copy["estimated_tax"] = str(p_tax)
            p_copy["estimated_total_monthly"] = str(p_total)
            p_copy["monthly_total_with_tax"] = str(p_total)
            if max_b is not None:
                p_copy["within_budget_before_tax"] = bool(p_price <= max_b)
                p_copy["within_budget_after_tax"] = bool(p_total <= max_b)
            p_copy.setdefault("contract_required", False)
            shortlist.append(p_copy)

    cat_addons = [a for a in FAKE_ADDON_CATALOG if a.get("category") == cat]
    if not cat_addons:
        cat_addons = list(FAKE_ADDON_CATALOG)
    addons_enriched = []
    for a in cat_addons:
        a_copy = {k: v for k, v in a.items() if not k.endswith(("_en", "_fr", "_es"))}
        a_copy["description"] = a.get(f"description_{desc_lang}", a.get("description_en", ""))
        a_copy["contract_required"] = False
        a_price = Decimal(str(a.get("monthly_price", 0)))
        a_tax = (a_price * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        a_total = a_price + a_tax
        a_copy["estimated_tax"] = str(a_tax)
        a_copy["estimated_total_monthly"] = str(a_total)
        a_copy["monthly_total_with_tax"] = str(a_total)
        if a.get("included_channels"):
            a_copy["included_channels"] = a["included_channels"]
            tv_plans = FAKE_PLAN_CATALOG.get("tv", [])
            base_tv_plan = next((p for p in tv_plans if "starter" in p.get("id", "").lower() or "starter" in p.get("name", "").lower()), tv_plans[0] if tv_plans else None)
            base_price = Decimal(str(base_tv_plan.get("monthly_price", 25.00))) if base_tv_plan else Decimal("25.00")
            comb_before_tax = (base_price + a_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            comb_tax = (comb_before_tax * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            comb_with_tax = (comb_before_tax + comb_tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            a_copy["combined_monthly_with_tv_starter"] = display_amount(comb_before_tax)
            a_copy["combined_monthly_with_tv_starter_before_tax"] = display_amount(comb_before_tax)
            a_copy["combined_monthly_with_tv_starter_with_tax"] = display_amount(comb_with_tax)
        addons_enriched.append(a_copy)

    ref = tracking_id("browse_plans_and_coverage", cat, pc)
    state["last_tracking_id"] = ref

    contract_term = localized_text(
        lang,
        "Month-to-month, no annual contract, $0 activation fee",
        "Mensuel sans contrat annuel, frais d'activation de 0 $",
        "Mes a mes sin contrato anual, cargo de activación de $0",
    )

    browse_payload = {
        "category": cat,
        "shortlisted_plans": shortlist,
        "available_add_ons": addons_enriched,
        "add_ons": addons_enriched,
        "fiber_coverage_available": True,
        "five_g_coverage_available": True,
        "throttled_speed_after_cap": "512 kbps",
        "contract_term": contract_term,
    }
    if cat == "tv":
        browse_payload["included_channels"] = "TSN 1-5, Sportsnet, ESPN, FS1, RDS, NBA TV, MLB Network, NFL Network, Golf Channel, and regional sports networks in 4K/HD"
        browse_payload["combined_monthly_with_tv_starter"] = "43.00"
        browse_payload["combined_monthly_with_tv_starter_before_tax"] = "43.00"
        browse_payload["combined_monthly_with_tv_starter_with_tax"] = "49.45"
    elif cat == "internet":
        browse_payload["latency"] = localized_text(
            lang,
            "sub-15ms typical latency with <2ms jitter",
            "latence typique inférieure à 15 ms avec gigue inférieure à 2 ms",
            "latencia típica inferior a 15 ms con fluctuación inferior a 2 ms",
        )
        browse_payload["technical_specifications"] = localized_text(
            lang,
            "Pure fiber symmetrical bandwidth with sub-15ms low latency, minimal jitter under 2ms, and 99.9% uptime reliability across all residential tiers",
            "Bande passante symétrique pure fibre avec faible latence inférieure à 15 ms, gigue minimale inférieure à 2 ms et fiabilité de disponibilité de 99,9 % pour tous les forfaits résidentiels",
            "Banda ancha simétrica por fibra pura con baja latencia inferior a 15 ms, fluctuación mínima inferior a 2 ms y fiabilidad de 99.9 % en todos los planes residenciales",
        )
        browse_payload["sla_or_guarantee"] = localized_text(
            lang,
            "99.9% network availability during peak hours with no business contract required",
            "Disponibilité du réseau de 99,9 % pendant les heures de pointe sans contrat commercial requis",
            "Disponibilidad de red del 99.9 % durante horas pico sin necesidad de contrato comercial",
        )
        browse_payload["work_from_home_recommended_tier"] = localized_text(
            lang,
            "Fiber Internet 500 or Gigabit Fiber",
            "Fibre Internet 500 ou Fibre Gigabit",
            "Fibra Internet 500 o Fibra Gigabit",
        )

    if state.get("auth_status") == "pass":
        browse_payload["current_active_plans"] = _active_account_plans(state, lang)

    return _service_ok_reply(
        browse_payload,
        ref,
        language=lang,
    state=state,
    )
# --- END GENERATED SHARED BUNDLE ---
