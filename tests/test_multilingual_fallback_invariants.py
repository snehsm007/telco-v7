"""Unit tests verifying that all fallback, reprompt, silence, and error templates

are strictly language-aware with zero English-only leakage on non-English calls (ADR-28).
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from lib.copy import (
    AGENT_VERBATIM_KEYS,
    LOCALIZED_ERROR_DEFAULTS,
    SPOKEN_LINES,
    SUPPORTED_COPY_LOCALES,
    resolve_copy_locale,
    spoken_line,
)
from lib.dynamic_prompt import build_language_sheet, detect_active_call_language
from lib.replies import error_reply
from lib.services import _session_language
from lib.speech import clean_agent_speech, enforce_closing_utterance, enforce_handover_utterance

APP_DIR = Path(__file__).resolve().parent.parent / "cxas_app"

CORE_FALLBACK_KEYS = (
    "no_input_reprompt",
    "no_match_reprompt",
    "tool_error_apology",
    "keypad_recovery",
    "guardrail_rephrase",
)


def test_spoken_lines_all_languages_populated() -> None:
    """Verify that every fallback key in SPOKEN_LINES is populated for all supported locales without English-only leakage."""
    for key in CORE_FALLBACK_KEYS:
        assert key in SPOKEN_LINES, f"Missing {key} in SPOKEN_LINES"
        entry = SPOKEN_LINES[key]
        for loc in SUPPORTED_COPY_LOCALES:
            assert loc in entry, f"Missing locale {loc} for key {key}"
            text = entry[loc].strip()
            assert len(text) > 5, f"Locale {loc} text for {key} is too short: {text!r}"
            assert "[translate:" not in text, f"Unfinished translation placeholder in {key}[{loc}]"

        # French and Spanish must differ from English
        en_text = entry["en-US"].strip().lower()
        fr_text = entry["fr-CA"].strip().lower()
        es_text = entry["es-US"].strip().lower()
        assert fr_text != en_text, f"{key} fr-CA is identical to en-US: {fr_text}"
        assert es_text != en_text, f"{key} es-US is identical to en-US: {es_text}"


def test_agent_verbatim_keys_include_fallbacks() -> None:
    """Verify all 5 agents include the core fallback keys in their dynamic language sheet."""
    required_keys = {"no_input_reprompt", "no_match_reprompt", "tool_error_apology", "keypad_recovery"}
    for agent_name in ("router", "billing", "tech_support", "sales_equipment", "account"):
        agent_keys = set(AGENT_VERBATIM_KEYS.get(agent_name, ()))
        for rk in required_keys:
            assert rk in agent_keys, f"Agent {agent_name} missing verbatim key {rk}"

        # Verify dynamic language sheet in French and Spanish
        for loc in ("fr-CA", "es-US"):
            sheet = build_language_sheet(loc, agent_name=agent_name)
            for rk in required_keys:
                expected_line = spoken_line(rk, loc)
                assert expected_line in sheet, f"Sheet for {agent_name} ({loc}) missing {expected_line}"


def test_clean_agent_speech_intercepts_french_english_fallbacks() -> None:
    """Verify clean_agent_speech catches and replaces English fallback phrases in French sessions."""
    params_fr = {"language": "fr-CA"}

    # Guardrail rephrase fallback
    leaked_guardrail = "I apologize, could you please rephrase your request or share your account details so I can assist you?"
    cleaned_guardrail = clean_agent_speech(leaked_guardrail, params_fr)
    assert "apologize" not in cleaned_guardrail.lower()
    assert "excuses" in cleaned_guardrail.lower() or "reformuler" in cleaned_guardrail.lower()

    # Keypad missing digits fallback
    leaked_keypad = "I'm sorry — the keypad entry didn't come through on my end. Please say the number out loud, one digit at a time."
    cleaned_keypad = clean_agent_speech(leaked_keypad, params_fr)
    assert "keypad" not in cleaned_keypad.lower()
    assert "clavier" in cleaned_keypad.lower()

    # Silence reprompt
    leaked_silence = "I didn't hear anything. Could you please repeat that?"
    cleaned_silence = clean_agent_speech(leaked_silence, params_fr)
    assert "hear anything" not in cleaned_silence.lower()
    assert "entendu" in cleaned_silence.lower()

    # Generic rephrase
    leaked_rephrase = "Please rephrase your request."
    cleaned_rephrase = clean_agent_speech(leaked_rephrase, params_fr)
    assert "rephrase" not in cleaned_rephrase.lower()
    assert "reformuler" in cleaned_rephrase.lower()

    # Tool error apology
    leaked_tool_err = "I apologize, our system is currently having trouble processing that request. Let me connect you with a representative who can assist."
    cleaned_tool_err = clean_agent_speech(leaked_tool_err, params_fr)
    assert "trouble" not in cleaned_tool_err.lower()
    assert "difficulté" in cleaned_tool_err.lower() or "système" in cleaned_tool_err.lower()


def test_clean_agent_speech_intercepts_spanish_english_fallbacks() -> None:
    """Verify clean_agent_speech catches and replaces English fallback phrases in Spanish sessions."""
    params_es = {"language": "es-US"}

    leaked_keypad = "I'm sorry — the keypad entry didn't come through on my end. Please say the number out loud, one digit at a time."
    cleaned_keypad = clean_agent_speech(leaked_keypad, params_es)
    assert "keypad" not in cleaned_keypad.lower()
    assert "teclado" in cleaned_keypad.lower()

    leaked_rephrase = "Could you please rephrase your request?"
    cleaned_rephrase = clean_agent_speech(leaked_rephrase, params_es)
    assert "rephrase" not in cleaned_rephrase.lower()
    assert "reformular" in cleaned_rephrase.lower()


def test_guardrail_configs_contain_no_unconstrained_english_defaults() -> None:
    """Verify guardrail configurations mandate localized output and protect credential inputs."""
    prompt_gr_file = APP_DIR / "guardrails" / "Default_Prompt_Guardrail" / "Default_Prompt_Guardrail.json"
    safety_gr_file = APP_DIR / "guardrails" / "Default_Safety_Guardrail" / "Default_Safety_Guardrail.json"

    for gr_file in (prompt_gr_file, safety_gr_file):
        data = json.loads(gr_file.read_text(encoding="utf-8"))
        ans_prompt = data.get("action", {}).get("generativeAnswer", {}).get("prompt", "")
        assert "French" in ans_prompt
        assert "Spanish" in ans_prompt
        assert "English" in ans_prompt
        # Must strictly mandate French for French calls
        assert "Je vous présente mes excuses" in ans_prompt
        assert "Le pido disculpas" in ans_prompt

    prompt_gr_data = json.loads(prompt_gr_file.read_text(encoding="utf-8"))
    sec_policy = prompt_gr_data.get("llmPromptSecurity", {}).get("customPolicy", {}).get("prompt", "")
    # Must permit callers providing credentials/PINs in response to authentication prompts
    assert "PIN" in sec_policy
    assert "credentials" in sec_policy or "authentication" in sec_policy


def test_adr28_prompt_guardrail_disabled_pinned() -> None:
    """Pin ADR-28 decision: Default Prompt Guardrail must remain disabled on Round 8."""
    prompt_gr_file = APP_DIR / "guardrails" / "Default_Prompt_Guardrail" / "Default_Prompt_Guardrail.json"
    data = json.loads(prompt_gr_file.read_text(encoding="utf-8"))
    assert data.get("enabled") is False, "Default Prompt Guardrail must remain disabled (enabled: false) per ADR-28"

    # Default Safety Guardrail must remain enabled
    safety_gr_file = APP_DIR / "guardrails" / "Default_Safety_Guardrail" / "Default_Safety_Guardrail.json"
    safety_data = json.loads(safety_gr_file.read_text(encoding="utf-8"))
    assert safety_data.get("enabled") is True, "Default Safety Guardrail must remain enabled"


def test_error_reply_preserves_target_language() -> None:
    """Verify error_reply returns localized message and action for fr-CA and es-US."""
    rep_fr = error_reply("SERVICE_UNAVAILABLE", language="fr-CA")
    assert rep_fr["active_language"] == "fr-CA"
    assert "inaccessible" in rep_fr["error_message"] or "temporairement" in rep_fr["error_message"]
    assert "agent" in rep_fr["agent_action"] or "excuses" in rep_fr["agent_action"]

    rep_es = error_reply("CARD_DECLINED", language="es-US")
    assert rep_es["active_language"] == "es-US"
    assert "rechazada" in rep_es["error_message"]
    assert "pago" in rep_es["agent_action"]

    # Inferred from data dictionary
    rep_inferred = error_reply("NOT_FOUND", data={"fx_language": "fr-CA"})
    assert rep_inferred["active_language"] == "fr-CA"
    assert "trouvé" in rep_inferred["error_message"]


def test_session_language_respects_fixture_and_preferred_language() -> None:
    """Verify _session_language and detect_active_call_language respect fx_language and preferred_language."""
    state_fr = {"fx_language": "fr-CA"}
    assert _session_language(state_fr, language="") == "fr-CA"
    # An empty or default en-US passed by model does not override fx_language
    assert _session_language(state_fr, language="en-US") == "fr-CA"

    state_es = {"preferred_language": "es-US"}
    assert _session_language(state_es, language="") == "es-US"

    # dynamic prompt detection
    assert detect_active_call_language(state_fr, None) == "fr-CA"
    assert detect_active_call_language(state_es, None) == "es-US"


def test_enforce_handover_and_closing_utterance_localized() -> None:
    """Verify enforce_handover_utterance and enforce_closing_utterance produce localized lines."""
    # Handover in French with fx_language
    handover_fr = enforce_handover_utterance(
        "",
        session_params={"fx_language": "fr-CA"},
        called_tools=["handover_to_person"],
        tool_args_list=[{"reason": "user_requested_agent"}],
    )
    assert "représentant" in handover_fr or "patienter" in handover_fr

    # Handover in Spanish with preferred_language
    handover_es = enforce_handover_utterance(
        "",
        session_params={"preferred_language": "es-US"},
        called_tools=["handover_to_person"],
        tool_args_list=[{"reason": "business_handoff"}],
    )
    assert "comercial" in handover_es or "agente" in handover_es

    # Closing utterance in French and Spanish
    closing_fr = enforce_closing_utterance("resolved", language="fr-CA")
    assert "merci" in closing_fr.lower() or "bonne journée" in closing_fr.lower()

    closing_es = enforce_closing_utterance("resolved", language="es-US")
    assert "gracias" in closing_es.lower() or "excelente" in closing_es.lower()


def test_no_english_only_fallback_templates_exist() -> None:
    """Verify that no English-only fallback, silence, or error template exists for non-English locales."""
    for loc in ("fr-CA", "es-US"):
        # 1. Spoken fallback and reprompt templates
        for key in CORE_FALLBACK_KEYS:
            text = spoken_line(key, loc)
            en_text = spoken_line(key, "en-US")
            assert text, f"Empty fallback template for {key} in {loc}"
            assert text != en_text, f"English-only fallback template for {key} in {loc}: {text!r}"
            # Ensure no common untranslated English leakage phrases
            low = text.lower()
            assert "i apologize" not in low, f"Untranslated English in {key}[{loc}]: {text}"
            assert "please hold" not in low, f"Untranslated English in {key}[{loc}]: {text}"
            assert "our system" not in low, f"Untranslated English in {key}[{loc}]: {text}"

        # 2. Localized error defaults for every known error code
        assert loc in LOCALIZED_ERROR_DEFAULTS, f"Missing {loc} in LOCALIZED_ERROR_DEFAULTS"
        for code, (en_msg, en_act) in LOCALIZED_ERROR_DEFAULTS["en-US"].items():
            loc_tuple = LOCALIZED_ERROR_DEFAULTS[loc].get(code)
            assert loc_tuple is not None, f"Missing localized error default for {code} in {loc}"
            loc_msg, loc_act = loc_tuple
            assert loc_msg, f"Empty error message for {code} in {loc}"
            assert loc_act, f"Empty agent action for {code} in {loc}"
            assert loc_msg != en_msg, f"English-only error message for {code} in {loc}: {loc_msg!r}"

        # 3. error_reply helper returns localized defaults and active_language
        rep_from_lang = error_reply("WRONG_PIN", language=loc)
        assert rep_from_lang["active_language"] == loc
        assert rep_from_lang["error_message"] != LOCALIZED_ERROR_DEFAULTS["en-US"]["WRONG_PIN"][0]

        rep_from_data = error_reply("WRONG_PIN", data={"fx_language": loc})
        assert rep_from_data["active_language"] == loc
        assert rep_from_data["error_message"] != LOCALIZED_ERROR_DEFAULTS["en-US"]["WRONG_PIN"][0]

        rep_from_state = error_reply("WRONG_PIN", state={"fx_language": loc})
        assert rep_from_state["active_language"] == loc
        assert rep_from_state["error_message"] != LOCALIZED_ERROR_DEFAULTS["en-US"]["WRONG_PIN"][0]


def test_french_canadian_register_in_dynamic_sheet() -> None:
    """Verify that build_language_sheet injects authentic French-Canadian register and vocabulary without overfitting."""
    sheet_fr = build_language_sheet("fr-CA", agent_name="router")
    assert '<active_language_sheet locale="fr-CA" language="Canadian French">' in sheet_fr
    assert "Canadian French Register and Vocabulary (fr-CA)" in sheet_fr

    # French-Canadian regional terminology
    assert "courriel" in sheet_fr
    assert "cellulaire" in sheet_fr
    assert "forfait" in sheet_fr
    assert "facture" in sheet_fr
    assert "NIP" in sheet_fr

    # Openings and register
    assert "Bonjour" in sheet_fr
    assert "Allô" in sheet_fr
    assert "vous" in sheet_fr

    # Tolerated caller idioms
    assert "c'est-tu" in sheet_fr
    assert "merci ben" in sheet_fr
    assert "mon cell" in sheet_fr

    # Anti-overfitting: no phone numbers, account IDs, prices, or hardcoded balances in instruction
    assert not re.search(r"\$\d+", sheet_fr), "Found hardcoded price in language sheet"
    assert not re.search(r"\b\d{3}-\d{3}-\d{4}\b", sheet_fr), "Found hardcoded phone in language sheet"
    assert not re.search(r"\bACC-\d+\b", sheet_fr), "Found hardcoded account ID in language sheet"

    # English sheet must not contain French-Canadian register rule
    sheet_en = build_language_sheet("en-US", agent_name="router")
    assert "Canadian French Register" not in sheet_en


def test_contract_cancellation_disclosure_exact_wording_and_ordering() -> None:
    """Verify exact PRD verbatim wording for contract disclosure and strict speech-hygiene pass-through."""
    # PRD exact strings
    en_expected = (
        "Please note that cancelling or transferring your line ends any active term agreement, "
        "and any applicable early cancellation fee and prorated charges from your account terms "
        "will appear on your final statement."
    )
    fr_expected = (
        "Veuillez noter que l'annulation ou le transfert de votre ligne met fin à toute entente active, "
        "et que les frais de résiliation anticipée applicables ainsi que le solde calculé au prorata "
        "figureront sur votre dernière facture."
    )

    assert spoken_line("contract_cancellation_fee_disclosure", "en-US") == en_expected
    assert spoken_line("contract_cancellation_fee_disclosure", "fr-CA") == fr_expected

    # Speech hygiene must not truncate or alter either disclosure
    cleaned_en = clean_agent_speech(en_expected, session_params={"language": "en-US"})
    assert cleaned_en == en_expected, f"clean_agent_speech mutated EN disclosure: {cleaned_en}"

    cleaned_fr = clean_agent_speech(fr_expected, session_params={"language": "fr-CA"})
    assert cleaned_fr == fr_expected, f"clean_agent_speech mutated FR disclosure: {cleaned_fr}"

    # Verify account agent instruction mandates reciting disclosure FIRST before asking confirmation
    account_instruction = (APP_DIR / "agents" / "account" / "instruction.txt").read_text(encoding="utf-8")
    assert "FIRST before asking the confirmation question" in account_instruction
    assert "FIRST before anything else" in account_instruction

