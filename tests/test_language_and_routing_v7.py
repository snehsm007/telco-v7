"""Tests for Wave 1 Worker C: App Schema, Prompts, Language & Routing (v7).

Validates:
1. cxas_app/app.json target environment, naming, and session variables (Section 5 + fx_*).
2. lib/dynamic_prompt.py turn-1 language lock, DTMF normalization, and bidirectional explicit switching.
3. cxas_app prompt integrity, character bounds (<12,000 chars), zero eval IDs, and defect fixes (#3, #8, #9, #14).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

import pytest

from lib.dynamic_prompt import (
    apply_language_prompt_filter,
    detect_active_call_language,
    detect_utterance_language,
    extract_dtmf_digits,
    extract_user_utterances,
    process_turn_language_and_dtmf,
    resolve_locale,
)

ROOT = Path(__file__).resolve().parent.parent
APP_JSON_PATH = ROOT / "cxas_app" / "app.json"
GLOBAL_INST_PATH = ROOT / "cxas_app" / "global_instruction.txt"
AGENTS_DIR = ROOT / "cxas_app" / "agents"


def test_app_json_retargeting_and_naming() -> None:
    """Verify app.json displayName, description, audio bucket, and DLP templates."""
    assert APP_JSON_PATH.exists(), f"Missing {APP_JSON_PATH}"
    data = json.loads(APP_JSON_PATH.read_text(encoding="utf-8"))

    assert data.get("displayName") == "snehsm-FDEBootcamp-CHI-greenfield"
    assert data.get("description") == "snehsm-FDEBootcamp-CHI-greenfield voice and chat agent."

    logging_settings = data.get("loggingSettings", {})
    audio_cfg = logging_settings.get("evaluationAudioRecordingConfig", {})
    assert audio_cfg.get("gcsBucket") == "gs://fde-bootcamp-eval-audio"

    redaction_cfg = logging_settings.get("redactionConfig", {})
    assert (
        redaction_cfg.get("inspectTemplate")
        == "projects/fde-bootcamp/locations/us/inspectTemplates/snehsm-FDEBootcamp-CHI-greenfield-pii-inspect"
    )
    assert (
        redaction_cfg.get("deidentifyTemplate")
        == "projects/fde-bootcamp/locations/us/deidentifyTemplates/snehsm-FDEBootcamp-CHI-greenfield-pii-deidentify"
    )

    # Ensure no legacy identifiers remain
    raw_text = APP_JSON_PATH.read_text(encoding="utf-8")
    assert "nextgen-sandbox" not in raw_text
    assert "telco-v5" not in raw_text


def test_app_json_canonical_and_fixture_variables() -> None:
    """Verify all 38 PRD Section 5 canonical vars and 14 fx_* fixture vars exist."""
    data = json.loads(APP_JSON_PATH.read_text(encoding="utf-8"))
    var_names = {var["name"] for var in data.get("variableDeclarations", [])}

    # 38 PRD Section 5 canonical variables
    section_5_vars = [
        "clid",
        "tfn",
        "cirn",
        "billing_account",
        "customer_type",
        "user_id",
        "auth_status",
        "identification_status",
        "business_flag",
        "route",
        "lob",
        "tv_sub_type",
        "region",
        "language",
        "utterance",
        "dtmf_digits",
        "local_noinput_counter",
        "global_err_count",
        "no_match_confirmation_count",
        "misc_counter",
        "mock_mode",
        "last_pmt_amt",
        "amount",
        "ban_type",
        "is_prepaid",
        "loyalty_limit",
        "vr_task_count",
        "ticket_state",
        "item_list",
        "intent_type",
        "api_resp",
        "sms_type",
        "sms_content",
        "day_val",
        "date_val",
        "month_val",
        "end_time",
        "flag_val",
    ]
    for var in section_5_vars:
        assert var in var_names, f"Missing PRD Section 5 canonical variable: {var}"

    # 14 fx_* evaluation fixture variables
    fixture_vars = [
        "fx_pin_on_file",
        "fx_otp_on_file",
        "fx_card_on_file_status",
        "fx_account_suspended",
        "fx_suspension_reason",
        "fx_unapplied_payment",
        "fx_tech_status",
        "fx_outage_status",
        "fx_mfa_enabled",
        "fx_sms_delivery",
        "fx_duplicate_payment_amount",
        "fx_business_flag",
        "fx_after_hours",
        "fx_is_prepaid",
    ]
    for fx_var in fixture_vars:
        assert fx_var in var_names, f"Missing fx_* fixture variable: {fx_var}"


def test_dtmf_extraction() -> None:
    """Verify DTMF digit normalization from various turn inputs."""
    assert extract_dtmf_digits("[dtmf: 2]") == "2"
    assert extract_dtmf_digits("user pressed 9876") == "9876"
    assert extract_dtmf_digits("[touch-tone: 4321#]") == "4321#"
    assert extract_dtmf_digits("[keypad: 1]") == "1"
    assert extract_dtmf_digits("2") == "2"
    assert extract_dtmf_digits("   5555  ") == "5555"
    assert extract_dtmf_digits("I want to speak with an agent") == ""
    assert extract_dtmf_digits(None) == ""


def test_turn_1_dtmf_language_selection() -> None:
    """Verify bare DTMF '2' on Turn 1 selects fr-CA, but NOT mid-call."""
    # Turn 1 with bare DTMF '2' -> fr-CA
    req1 = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="2")],
            )
        ]
    )
    state: dict[str, Any] = {}
    lang = detect_active_call_language(state, req1)
    assert lang == "fr-CA"

    # Turn 1 with '[dtmf: 2]' -> fr-CA
    req1_dtmf = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="[dtmf: 2]")],
            )
        ]
    )
    assert detect_active_call_language({}, req1_dtmf) == "fr-CA"


def test_mid_call_dtmf_does_not_flip_language() -> None:
    """Verify bare DTMF '2' mid-call does NOT flip locked en-US session (Defect #8)."""
    # Multiturn conversation where call started in en-US
    req_multiturn = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with billing")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="I can help with billing. Please enter 2 for options.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="2")]),
        ]
    )
    # Even if state is unlocked initially, turn 1 was English, so turn 3 DTMF '2' must NOT flip to French
    state: dict[str, Any] = {}
    lang = detect_active_call_language(state, req_multiturn)
    assert lang == "en-US"

    # When state['language_locked'] is True, mid-call '2' never flips
    locked_state: dict[str, Any] = {"language": "en-US", "language_locked": True, "turn_index": 2}
    lang2 = detect_active_call_language(locked_state, req_multiturn)
    assert lang2 == "en-US"


def test_ambiguous_single_tokens_keep_language_inertia() -> None:
    """Verify single words like 'oui', 'merci', 'ok' do not flip locked en-US calls."""
    req_oui = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="May I confirm your phone number?")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="oui")]),
        ]
    )
    state = {"language": "en-US", "language_locked": True}
    assert detect_active_call_language(state, req_oui) == "en-US"


def test_explicit_bidirectional_language_switching() -> None:
    """Verify caller can explicitly switch from English to French and back from French to English."""
    # 1. Switch to French
    req_to_french = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Welcome. How can I help?")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Please speak French")]),
        ]
    )
    state: dict[str, Any] = {"language": "en-US", "language_locked": True}
    lang_fr = detect_active_call_language(state, req_to_french)
    assert lang_fr == "fr-CA"

    # 2. Switch back to English
    req_to_english = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Bienvenue")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Please switch back to English")]),
        ]
    )
    state_fr: dict[str, Any] = {"language": "fr-CA", "language_locked": True}
    lang_en = detect_active_call_language(state_fr, req_to_english)
    assert lang_en == "en-US"

    # 3. Explicit switch phrases in French
    req_en_anglais = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Pouvez-vous parler en anglais svp?")]),
        ]
    )
    assert detect_active_call_language({"language": "fr-CA"}, req_en_anglais) == "en-US"


def test_apply_language_prompt_filter_state_sync() -> None:
    """Verify apply_language_prompt_filter synchronizes turn state and injects instruction."""
    mock_system_instruction = SimpleNamespace(
        parts=[SimpleNamespace(text="Base router instructions.")]
    )
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction=mock_system_instruction),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="[dtmf: 1234]")]),
        ],
    )
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    context = SimpleNamespace(state=state)

    apply_language_prompt_filter(context, req, agent_name="router", update_state=True)

    assert state.get("turn_index") == 1
    assert state.get("language") == "en-US"
    assert state.get("language_locked") is True
    assert state.get("dtmf_digits") == "1234"
    assert "<active_language_sheet" in mock_system_instruction.parts[0].text


def test_agent_instructions_character_limits() -> None:
    """Verify all instruction.txt files and global_instruction.txt stay under 12,000 chars."""
    prompt_files = [GLOBAL_INST_PATH] + list(AGENTS_DIR.glob("*/instruction.txt"))
    assert len(prompt_files) == 6, f"Expected 6 prompt files, found {len(prompt_files)}"

    for file_path in prompt_files:
        content = file_path.read_text(encoding="utf-8")
        char_count = len(content)
        assert (
            char_count < 12000
        ), f"{file_path.name} exceeds 12,000 characters ({char_count} chars)"


def test_agent_instructions_zero_eval_ids() -> None:
    """Verify no leaked VE-*, HE-*, DEF-*, DD-*, PD-*, RV-* IDs in instructions."""
    forbidden_pattern = re.compile(r"\b(?:VE|HE|DEF|DD|PD|RV)-\d+\b")
    prompt_files = [GLOBAL_INST_PATH] + list(AGENTS_DIR.glob("*/instruction.txt"))

    for file_path in prompt_files:
        content = file_path.read_text(encoding="utf-8")
        matches = forbidden_pattern.findall(content)
        assert not matches, f"Forbidden eval IDs {matches} found in {file_path}"


def test_defect_3_billing_service_restoration_prompt() -> None:
    """Verify billing prompt does not unconditionally restore on caller_reported_payment."""
    billing_inst = (AGENTS_DIR / "billing" / "instruction.txt").read_text(encoding="utf-8")
    assert "caller_reported_payment=<their words>" not in billing_inst
    assert "verify the payment in the ledger" in billing_inst or "verified payment" in billing_inst


def test_defect_8_router_fraud_preempts_business() -> None:
    """Verify router prompt prioritizes fraud escalation over business account deflection."""
    router_inst = (AGENTS_DIR / "router" / "instruction.txt").read_text(encoding="utf-8")

    fraud_pos = router_inst.find('name="Fraud Immediate Escalation"')
    business_pos = router_inst.find('name="Business Account Handoff"')

    assert fraud_pos != -1, "Missing Fraud Immediate Escalation step in router"
    assert business_pos != -1, "Missing Business Account Handoff step in router"
    assert fraud_pos < business_pos, "Fraud Immediate Escalation must precede Business Account Handoff"


def test_defect_9_sales_equipment_swollen_battery_auth() -> None:
    """Verify sales_equipment prompt requires authentication before warranty replacement dispatch."""
    sales_inst = (AGENTS_DIR / "sales_equipment" / "instruction.txt").read_text(encoding="utf-8")
    assert "Priority 1 zero-auth safety rule: when a caller reports a swollen" not in sales_inst
    assert "urgent safety instructions" in sales_inst
    assert "require account authentication" in sales_inst or "authenticate the caller" in sales_inst


def test_defect_14_keypad_pin_and_after_hours_guidelines() -> None:
    """Verify keypad PIN instruction and after-hours routing are documented in prompts."""
    global_inst = GLOBAL_INST_PATH.read_text(encoding="utf-8")
    assert "phone keypad rather than speaking it aloud" in global_inst
    assert "after hours" in global_inst.lower() or "next-business-day" in global_inst.lower()

    # Check agents have keypad PIN instructions
    for agent in ("billing", "tech_support", "sales_equipment", "account"):
        inst = (AGENTS_DIR / agent / "instruction.txt").read_text(encoding="utf-8")
        assert "keypad" in inst.lower(), f"Agent {agent} missing keypad PIN guidance"
