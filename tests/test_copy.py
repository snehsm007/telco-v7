"""Tests for lib/copy.py covering locale resolution, spoken lines, and localized copy."""

from __future__ import annotations

import pytest

from lib.copy import (
    AGENT_VERBATIM_KEYS,
    LOCALIZED_ERROR_DEFAULTS,
    SPOKEN_LINES,
    SUPPORTED_COPY_LOCALES,
    WORLD_LANGUAGE_NAMES,
    localized_text,
    resolve_copy_locale,
    resolve_locale,
    spoken_line,
)


def test_supported_constants() -> None:
    assert "en-US" in SUPPORTED_COPY_LOCALES
    assert "fr-CA" in SUPPORTED_COPY_LOCALES
    assert "es-US" in SUPPORTED_COPY_LOCALES
    assert WORLD_LANGUAGE_NAMES["en-US"] == "English"
    assert WORLD_LANGUAGE_NAMES["fr-CA"] == "Canadian French"
    assert WORLD_LANGUAGE_NAMES["es-US"] == "Spanish"
    assert len(WORLD_LANGUAGE_NAMES) >= 11


def test_resolve_locale_empty_and_default() -> None:
    assert resolve_locale(None) == "en-US"
    assert resolve_locale("") == "en-US"
    assert resolve_locale("   ") == "en-US"
    assert resolve_locale("unknown_language") == "en-US"


def test_resolve_locale_primary_secondary() -> None:
    assert resolve_locale("primary") == "en-US"
    assert resolve_locale("secondary") == "fr-CA"


def test_resolve_locale_language_names_and_tags() -> None:
    assert resolve_locale("en") == "en-US"
    assert resolve_locale("english") == "en-US"
    assert resolve_locale("anglais") == "en-US"
    assert resolve_locale("fr") == "fr-CA"
    assert resolve_locale("french") == "fr-CA"
    assert resolve_locale("francais") == "fr-CA"
    assert resolve_locale("français") == "fr-CA"
    assert resolve_locale("es") == "es-US"
    assert resolve_locale("spanish") == "es-US"
    assert resolve_locale("espanol") == "es-US"
    assert resolve_locale("español") == "es-US"
    assert resolve_locale("pt") == "pt-BR"
    assert resolve_locale("portuguese") == "pt-BR"
    assert resolve_locale("de") == "de-DE"
    assert resolve_locale("german") == "de-DE"
    assert resolve_locale("deutsch") == "de-DE"
    assert resolve_locale("it") == "it-IT"
    assert resolve_locale("italian") == "it-IT"
    assert resolve_locale("zh") == "zh-CN"
    assert resolve_locale("chinese") == "zh-CN"
    assert resolve_locale("mandarin") == "zh-CN"
    assert resolve_locale("hi") == "hi-IN"
    assert resolve_locale("hindi") == "hi-IN"
    assert resolve_locale("ar") == "ar-XA"
    assert resolve_locale("arabic") == "ar-XA"
    assert resolve_locale("ja") == "ja-JP"
    assert resolve_locale("japanese") == "ja-JP"
    assert resolve_locale("ko") == "ko-KR"
    assert resolve_locale("korean") == "ko-KR"


def test_resolve_locale_bcp47_fallback() -> None:
    assert resolve_locale("nl-nl") == "nl-NL"
    assert resolve_locale("cmn-hans") == "cmn-HANS"
    assert resolve_locale("invalid-pattern-too-long-long") == "en-US"


def test_resolve_copy_locale() -> None:
    assert resolve_copy_locale("en-US") == "en-US"
    assert resolve_copy_locale("english") == "en-US"
    assert resolve_copy_locale("fr-CA") == "fr-CA"
    assert resolve_copy_locale("french") == "fr-CA"
    assert resolve_copy_locale("es-US") == "es-US"
    assert resolve_copy_locale("spanish") == "es-US"
    assert resolve_copy_locale("de-DE") == "en-US"
    assert resolve_copy_locale("pt-BR") == "en-US"
    assert resolve_copy_locale(None) == "en-US"


def test_spoken_line_basic_and_locales() -> None:
    greeting_en = spoken_line("greeting", "en-US")
    greeting_fr = spoken_line("greeting", "fr-CA")
    greeting_es = spoken_line("greeting", "es-US")
    assert "thanks for calling" in greeting_en
    assert "merci de votre appel" in greeting_fr
    assert "gracias por su llamada" in greeting_es


def test_spoken_line_fallbacks() -> None:
    assert spoken_line("non_existent_key") == ""
    # German falls back to en-US copy
    assert spoken_line("greeting", "de-DE") == spoken_line("greeting", "en-US")


def test_spoken_line_slot_formatting() -> None:
    line_code = spoken_line("code_sent", "en-US", destination_last4="4321")
    assert "4321" in line_code

    # Integer float
    line_refund = spoken_line(
        "refund_confirmation_pattern", "en-US", amount=25.0, days=5.0
    )
    assert "$25" in line_refund
    assert "5 business days" in line_refund

    # days as int, string, and unparseable value
    line_days_int = spoken_line(
        "refund_confirmation_pattern", "en-US", amount="10.50", days=3
    )
    assert "$10.50" in line_days_int
    assert "3 business days" in line_days_int

    line_days_str = spoken_line(
        "refund_confirmation_pattern", "en-US", amount="10.50", days="7.0"
    )
    assert "7 business days" in line_days_str

    line_days_invalid = spoken_line(
        "refund_confirmation_pattern", "en-US", amount="10.50", days="several"
    )
    assert "several business days" in line_days_invalid

    assert spoken_line("confirmation_number_line", "en-US", ref="R123456") == (
        "Your confirmation number is R123456."
    )
    assert spoken_line("confirmation_number_line", "fr-CA", ref="R123456") == (
        "Votre numéro de confirmation est le R123456."
    )
    assert spoken_line("confirmation_number_line", "es-US", ref="R123456") == (
        "Su número de confirmación es R123456."
    )


def test_localized_text() -> None:
    assert localized_text("en-US", en="Hello", fr="Bonjour", es="Hola") == "Hello"
    assert localized_text("fr-CA", en="Hello", fr="Bonjour", es="Hola") == "Bonjour"
    assert localized_text("es-US", en="Hello", fr="Bonjour", es="Hola") == "Hola"
    assert localized_text("es-US", en="Hello", fr="Bonjour", es="") == "Hello"
    assert localized_text("de-DE", en="Hello", fr="Bonjour", es="Hola") == "Hello"


def test_agent_verbatim_keys() -> None:
    expected_agents = {"router", "billing", "tech_support", "sales_equipment", "account"}
    assert set(AGENT_VERBATIM_KEYS.keys()) == expected_agents
    for agent, keys in AGENT_VERBATIM_KEYS.items():
        assert len(keys) >= 5, f"{agent} should have at least 5 verbatim keys"
        for key in keys:
            assert key in SPOKEN_LINES, f"Verbatim key {key!r} for {agent} missing in SPOKEN_LINES"


def test_localized_error_defaults() -> None:
    assert set(LOCALIZED_ERROR_DEFAULTS.keys()) == {"en-US", "fr-CA", "es-US"}
    common_errors = {
        "INVALID_INPUT",
        "NOT_FOUND",
        "NOT_IDENTIFIED",
        "NOT_LOGGED_IN",
        "WRONG_CODE",
        "TOO_MANY_ATTEMPTS",
        "SYSTEM_DOWN",
        "SERVICE_UNAVAILABLE",
    }
    for loc in ("en-US", "fr-CA", "es-US"):
        for code in common_errors:
            assert code in LOCALIZED_ERROR_DEFAULTS[loc], f"Missing error code {code} in {loc}"
            err_msg, agent_action = LOCALIZED_ERROR_DEFAULTS[loc][code]
            assert isinstance(err_msg, str) and len(err_msg) > 0
            assert isinstance(agent_action, str) and len(agent_action) > 0
