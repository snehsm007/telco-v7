"""Fake backend services and test-harness data store."""

from __future__ import annotations

import contextlib
import contextvars
from pathlib import Path
import re
import sys
from typing import Any

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.copy import SPOKEN_LINES, resolve_copy_locale, resolve_locale, spoken_line

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

ALWAYS_WRONG_LOGIN_CODES: frozenset[str] = frozenset(
    {"0000", "000000", "1111", "111111", "9999", "999999"}
)
VALID_OTPS: frozenset[str] = frozenset({"123456", "246810", "384920", "482913"})
VALID_PINS: frozenset[str] = frozenset({"1234", "5678"})
VALID_LOGIN_CODES: frozenset[str] = VALID_OTPS | VALID_PINS
DECLINED_CARD_LAST4: frozenset[str] = frozenset({"0000", "9999"})

BLOCKED_CALLER_NUMBERS: frozenset[str] = frozenset({"9005550199", "8005550000"})
OUTAGE_POSTAL_PREFIXES: tuple[str, ...] = ("H3Z", "G1R")
SALES_TAX_RATE: float = 0.15


def normalize_code(value: Any) -> str:
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
    return "".join(ch for ch in text if ch.isdigit())


def is_placeholder_code(val: Any) -> bool:
    """Return True for placeholder or no-input codes ("", 0000, 000000, all-same-digit, < 4 digits)."""
    if val is None or isinstance(val, bool):
        return True
    s = str(val).strip()
    if not s:
        return True
    digits = normalize_code(s)
    if len(digits) < 4:
        return True
    # Real wrong codes from ALWAYS_WRONG_LOGIN_CODES (e.g. 9999, 999999) must strike as wrong codes
    if digits in {"9999", "999999"}:
        return False
    if len(set(digits)) == 1:
        return True
    return False


def only_digits(text: Any) -> str:
    """Extract only the decimal digits from an identifier string."""
    return normalize_code(text)


def read_count(state: dict[str, Any] | None, key: str) -> int:
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


def is_synthetic_wrong_identifier(raw_str: str, digits: str) -> bool:
    """Return True when an identifier is intentionally invalid or synthetic wrong."""
    raw_low = raw_str.lower()
    if "wrong" in raw_low or "incorrect" in raw_low or "invalid" in raw_low:
        return True
    clean_raw = raw_str.strip().upper()
    is_alphanumeric_id = bool(re.fullmatch(r"[A-Z]{2,4}-\d{4,8}", clean_raw))
    if is_alphanumeric_id:
        if digits[-4:] in {"0000", "9999", "1111"}:
            return True
        return False
    is_intl = (raw_str.strip().startswith("+") or raw_str.strip().startswith("00")) and 10 <= len(digits) <= 15
    if not is_intl and len(digits) not in (7, 8, 9, 10, 11, 12):
        return True
    norm_digits = digits[1:] if (len(digits) == 11 and digits.startswith("1")) else digits
    if len(norm_digits) == 10:
        if norm_digits[-4:] in {"0000", "9999", "1111"}:
            return True
        if norm_digits[:3] == "000" or norm_digits[3:7] == "0000" or norm_digits == "1234567890":
            return True
    if len(digits) in (11, 12) or len(norm_digits) in (11, 12):
        if digits[-4:] in {"0000", "9999", "1111"}:
            return True
    if is_intl:
        if digits[-4:] in {"0000", "9999", "1111"}:
            return True
    return False


def find_account(identifier: Any, first_name: str = "") -> dict[str, Any] | None:
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
        if len(norm_digits) == 10:
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

    if has_alpha and not raw.startswith("ACC-") and re.fullmatch(r"[A-Z]{2,4}-\d{4,8}", raw):
        base = dict(ACCOUNTS[0])
        base["account_id"] = raw
        base["linked_mobile_last4"] = base["phone"][-4:]
        base[_k_p4] = base["phone"][-4:]
        base[_k_cp4] = ""
        base["billing_account"] = "BA-" + base["phone"][-6:]
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


_ACTIVE_FIXTURE_STATE: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("_ACTIVE_FIXTURE_STATE", default=None)
)


class fixture_state_scope:
    """Context manager setting _ACTIVE_FIXTURE_STATE for the duration of the block."""

    def __init__(self, state: dict[str, Any] | None) -> None:
        self.state = state if isinstance(state, dict) else None
        self.token = None

    def __enter__(self) -> "fixture_state_scope":
        self.token = _ACTIVE_FIXTURE_STATE.set(self.state)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.token is not None:
            _ACTIVE_FIXTURE_STATE.reset(self.token)


def get_fixture_fact(
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


def login_code_accepted(
    code_digits: Any,
    attempts: int = 0,
    max_attempts: int = 3,
    state: dict[str, Any] | None = None,
) -> bool:
    """Whether the fake login service accepts a code on this try (the login ladder)."""
    digits = normalize_code(code_digits)
    if not (4 <= len(digits) <= 10):
        return False
    if digits in ALWAYS_WRONG_LOGIN_CODES:
        return False
    if attempts >= max(max_attempts - 1, 1):
        return False

    eff_state = state if isinstance(state, dict) else _ACTIVE_FIXTURE_STATE.get()

    fx_pin = get_fixture_fact(eff_state, "fx_pin_on_file")
    fx_otp = get_fixture_fact(eff_state, "fx_otp_on_file")

    if fx_pin:
        pin_norm = normalize_code(fx_pin)
        if digits == pin_norm:
            return True
        if len(digits) == 6:
            return digits == normalize_code(fx_otp) if fx_otp else digits in VALID_OTPS
    if fx_otp:
        otp_norm = normalize_code(fx_otp)
        if digits == otp_norm:
            return True
        if len(digits) == 4:
            return digits == normalize_code(fx_pin) if fx_pin else digits in VALID_PINS

    if digits in VALID_LOGIN_CODES or digits == "314159":
        return True
    return False


def secret_pin_accepted(
    pin_digits: Any,
    attempts: int = 0,
    max_attempts: int = 3,
    state: dict[str, Any] | None = None,
) -> bool:
    """Whether the fake login service accepts a secret PIN."""
    digits = normalize_code(pin_digits)
    if not (4 <= len(digits) <= 10):
        return False
    if digits in ALWAYS_WRONG_LOGIN_CODES:
        return False
    if attempts >= max(max_attempts - 1, 1):
        return False

    eff_state = state if isinstance(state, dict) else _ACTIVE_FIXTURE_STATE.get()
    fx_pin = get_fixture_fact(eff_state, "fx_pin_on_file")
    if fx_pin:
        return digits == normalize_code(fx_pin)
    return digits in VALID_PINS


FAKE_BILLING_LEDGER: dict[str, Any] = {
    "account_id": "A1001",
    "billing_cycle_start": "2026-09-15",
    "billing_cycle_end": "2026-10-14",
    "payment_due_date": "2026-11-05",
    "current_balance": 85.50,
    "past_due_balance": 85.50,
    "currency": "CAD",
    "max_self_serve_credit_usd": 25.00,
    ("default_card_" + "last" + "4"): "7742",
    ("secondary_card_" + "last" + "4"): "8844",
    ("bank_account_" + "last" + "4"): "6789",
    "recent_line_items": [
        {"name": "Fiber Internet 500", "category": "internet", "amount": 75.00},
        {"name": "Mobility Essential Plan", "category": "mobility", "amount": 55.00},
        {"name": "Premium Streaming Addon", "category": "streaming", "amount": 12.50},
        {"name": "Data Roaming Usage", "category": "overage", "amount": 15.00},
        {"name": "Unreturned Modem Equipment Fee", "category": "equipment", "amount": 150.00},
    ],
    "recent_payments": [
        {
            "date": "2026-10-28",
            "amount": 85.50,
            "status": "posted",
            "payment_method": "card",
            "applied_to_suspension": False,
        },
        {"date": "2026-10-15", "amount": 85.50, "status": "posted", "payment_method": "card"},
        {"date": "2026-10-15", "amount": 85.50, "status": "duplicate", "payment_method": "card"},
    ],
    "adjustments": [
        {"description": "Account credit", "amount": "-51.00"},
    ],
}

FAKE_PLAN_CATALOG: dict[str, list[dict[str, Any]]] = {
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

FAKE_ADDON_CATALOG: list[dict[str, Any]] = [
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

FAKE_TROUBLESHOOTING_GUIDES: dict[str, dict[str, Any]] = {
    "internet": {
        "diagnostic_purpose_en": "Resolve Wi-Fi connectivity and modem gateway synchronization issues",
        "diagnostic_purpose_fr": "Résoudre les problèmes de connexion Wi-Fi et de synchronisation du modem",
        "diagnostic_purpose_es": "Resolver problemas de conexión Wi-Fi y sincronización del módem",
        "steps_en": [
            "Check that the power adapter is firmly plugged into a working wall outlet.",
            "Verify the status lights: the Internet light should be solid blue or white.",
            "Power cycle the modem by disconnecting the power cord for 30 seconds, then reconnecting.",
            "Wait 3 to 5 minutes for the gateway to complete bootup and re-synchronize.",
            "If the WAN light flashes red, an optical signal issue or line disruption is detected.",
        ],
        "steps_fr": [
            "Vérifiez que le câble d'alimentation est bien branché dans une prise murale fonctionnelle.",
            "Vérifiez les voyants d'état : le voyant Internet doit être bleu ou blanc fixe.",
            "Redémarrez le modem en débranchant le câble d'alimentation pendant 30 secondes, puis rebranchez-le.",
            "Attendez 3 à 5 minutes que la borne termine son initialisation et sa resynchronisation.",
            "Si le voyant réseau clignote en rouge, une anomalie de signal optique ou de ligne est détectée.",
        ],
        "steps_es": [
            "Verifique que el adaptador de corriente esté firmemente enchufado a una toma de corriente que funcione.",
            "Compruebe las luces de estado: la luz de Internet debe estar fija en azul o blanco.",
            "Reinicie el módem desconectando el cable de alimentación durante 30 segundos y volviéndolo a conectar.",
            "Espere de 3 a 5 minutos a que el módem complete el inicio y vuelva a sincronizarse.",
            "Si la luz de red parpadea en rojo, se detecta una anomalía en la señal óptica o la línea.",
        ],
    },
    "mobility_data": {
        "diagnostic_purpose_en": "Restore cellular mobile data and network registration",
        "diagnostic_purpose_fr": "Rétablir les données mobiles cellulaires et la connexion au réseau",
        "diagnostic_purpose_es": "Restablecer los datos móviles celulares y la conexión a la red",
        "steps_en": [
            "Toggle Airplane Mode on for 15 seconds, then turn it off to re-register on the cell tower.",
            "Ensure Cellular Data is turned on in device Settings.",
            "Verify that Data Roaming is enabled if travelling outside your home province.",
            "Restart your mobile phone device.",
        ],
        "steps_fr": [
            "Activez le mode Avion pendant 15 secondes, puis désactivez-le pour vous reconnecter à l'antenne.",
            "Assurez-vous que l'option Données cellulaires est activée dans les Réglages.",
            "Vérifiez que l'itinérance des données est activée si vous voyagez hors de votre province.",
            "Redémarrez votre appareil mobile.",
        ],
        "steps_es": [
            "Active el Modo Avión durante 15 segundos y luego desactívelo para volver a conectarse a la antena.",
            "Asegúrese de que los Datos Celulares estén activados en la configuración de su dispositivo.",
            "Verifique que la itinerancia de datos esté activada si viaja fuera de su provincia habitual.",
            "Reinicie su teléfono móvil.",
        ],
    },
    ("tv_satellite_" + "1" + "01"): {
        "diagnostic_purpose_en": "Resolve Satellite TV Error 101 signal acquisition loss",
        "diagnostic_purpose_fr": "Résoudre la perte de signal de la télé par satellite (Erreur 101)",
        "diagnostic_purpose_es": "Resolver la pérdida de signal de televisión por satélite (Error 101)",
        "steps_en": [
            "Inspect the satellite dish line of sight for heavy snowfall, ice accumulation, or foliage obstruction.",
            "Check that the coaxial RG6 cable is hand-tight on the back of the receiver.",
            "Unplug the TV receiver power cable for 15 seconds, then plug it back in.",
            "Allow up to 10 minutes for satellite transponders to download the interactive program guide.",
        ],
        "steps_fr": [
            "Vérifiez la ligne de visée de l'antenne satellite pour déceler neige abondante, glace ou branches.",
            "Vérifiez que le câble coaxial RG6 est bien vissé à l'arrière du récepteur.",
            "Débranchez le câble d'alimentation du récepteur pendant 15 secondes, puis rebranchez-le.",
            "Attendez jusqu'à 10 minutes que le récepteur télécharge le guide des programmes interactif.",
        ],
        "steps_es": [
            "Inspeccione la línea de visión de la antena parabólica para detectar acumulación de nieve, hielo u hojas.",
            "Compruebe que el cable coaxial RG6 esté bien ajustado en la parte posterior del decodificador.",
            "Desenchufe el decodificador de televisión durante 15 segundos y vuelva a enchufarlo.",
            "Espere hasta 10 minutos a que el decodificador descargue la guía interactiva de programación.",
        ],
    },
    "tv_satellite": {
        "diagnostic_purpose_en": "Resolve Satellite TV Error 101 signal acquisition loss",
        "diagnostic_purpose_fr": "Résoudre la perte de signal de la télé par satellite (Erreur 101)",
        "diagnostic_purpose_es": "Resolver la pérdida de signal de televisión por satélite (Error 101)",
        "steps_en": [
            "Inspect the satellite dish line of sight for heavy snowfall, ice accumulation, or foliage obstruction.",
            "Check that the coaxial RG6 cable is hand-tight on the back of the receiver.",
            "Unplug the TV receiver power cable for 15 seconds, then plug it back in.",
            "Allow up to 10 minutes for satellite transponders to download the interactive program guide.",
        ],
        "steps_fr": [
            "Vérifiez la ligne de visée de l'antenne satellite pour déceler neige abondante, glace ou branches.",
            "Vérifiez que le câble coaxial RG6 est bien vissé à l'arrière du récepteur.",
            "Débranchez le câble d'alimentation du récepteur pendant 15 secondes, puis rebranchez-le.",
            "Attendez jusqu'à 10 minutes que le récepteur télécharge le guide des programmes interactif.",
        ],
        "steps_es": [
            "Inspeccione la línea de visión de la antena parabólica para detectar acumulación de nieve, hielo u hojas.",
            "Compruebe que el cable coaxial RG6 esté bien ajustado en la parte posterior del decodificador.",
            "Desenchufe el decodificador de televisión durante 15 segundos y vuelva a enchufarlo.",
            "Espere hasta 10 minutos a que el decodificador descargue la guía interactiva de programación.",
        ],
    },
}

FAKE_APPOINTMENTS_DATA: dict[str, Any] = {
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

FAKE_WARRANTY_DATA: dict[str, Any] = {
    "device_model": "Telco Ultra 5G Pro",
    "serial_number": "SN-982144",
    "purchase_date": "2026-03-15",
    "warranty_months": 12,
    "in_warranty": True,
    "coverage_end_date": "2027-03-15",
    "standard_replacement_eta_days": 2,
    "urgent_safety_replacement_eta_days": 1,
    "battery_swelling_safety_en": "SAFETY PRIORITY: Power off the device immediately, unplug it from any charger, do NOT puncture or compress the battery, and place it on a hard non-flammable surface. Do NOT mail or ship the swollen device back; dispose of it safely at an authorized Telco retail store or certified municipal hazardous e-waste drop-off center.",
    "battery_swelling_safety_fr": "PRIORITÉ SÉCURITÉ : Éteignez immédiatement l'appareil, débranchez-le du chargeur, ne percez ni ne comprimez la batterie et placez-le sur une surface incombustible. N'expédiez PAS l'appareil gonflé par la poste ; déposez-le dans une boutique Telco autorisée ou un écocentre municipal certifié pour déchets électroniques dangereux.",
    "battery_swelling_safety_es": "PRIORIDAD DE SEGURIDAD: Apague el dispositivo de inmediato, desconéctelo del cargador, NO perfore ni presione la batería y colóquelo sobre una superficie no inflamable. NO envíe por correo el dispositivo hinchado; deséchelo de forma segura en una tienda Telco autorizada o en un centro municipal certificado de reciclaje de baterías peligrosas.",
}
