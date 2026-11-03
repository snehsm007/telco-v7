"""Tests for lib/speech.py covering speech cleaning, number masking, and handover lines."""

from __future__ import annotations

import lib.speech as speech
from lib.speech import (
    clean_agent_speech,
    clean_speech,
    enforce_handover_utterance,
    mask_long_numbers,
    strip_markdown,
)


def test_long_numbers_keep_only_their_last_4_digits() -> None:
    assert mask_long_numbers("Call 2025550143 now") == "Call 0143 now"
    assert mask_long_numbers("It is (202) 555-0143.") == "It is 0143."
    assert mask_long_numbers("Card 4111 1111 1111 1234 is on file") == "Card 1234 is on file"
    assert mask_long_numbers("10-digit account 1234567890") == "10-digit account 7890"


def test_short_numbers_dates_and_amounts_are_left_alone() -> None:
    text = "Reference R123456, due 2026-10-08 14:30, amount $1,234.56, code 123456."
    assert mask_long_numbers(text) == text
    assert mask_long_numbers("PIN is 1234") == "PIN is 1234"
    assert mask_long_numbers("Port 8080") == "Port 8080"


def test_speakable_numbers_are_kept(monkeypatch) -> None:
    monkeypatch.setattr(speech, "SPEAKABLE_NUMBERS", frozenset({"18005550100"}))
    assert mask_long_numbers("Call 1-800-555-0100.") == "Call 1-800-555-0100."


def test_strip_markdown() -> None:
    assert strip_markdown("**Done.** Use `code`.\n## Next") == "Done. Use code.\nNext"
    assert strip_markdown("Press # to finish") == "Press # to finish"
    assert strip_markdown("# Header 1\n## Header 2\n### Header 3\nText") == "Header 1\nHeader 2\nHeader 3\nText"
    assert strip_markdown("Here is `monospace` and *italics* and ***bold-italics***") == "Here is monospace and italics and bold-italics"


def test_clean_speech() -> None:
    assert clean_speech("**Your number is 2025550143.**") == "Your number is 0143."
    assert clean_speech("`Account 9876543210`") == "Account 3210"


def test_clean_agent_speech_without_dict_params() -> None:
    assert clean_agent_speech("Hello 2025550143", None) == "Hello 0143"
    assert clean_agent_speech("Hello 2025550143", "not a dict") == "Hello 0143"  # type: ignore[arg-type]


def test_clean_agent_speech_caller_last4_and_profile_last4() -> None:
    # When caller gave 0199 but profile says 0143
    params = {"phone_last4": "0143", "caller_provided_phone_last4": "0199"}
    assert (
        clean_agent_speech("Your number ending in 0143 is verified.", params)
        == "Your number ending in 0199 is verified."
    )
    # Profile last4 matches caller last4
    params_same = {"phone_last4": "0143", "caller_provided_phone_last4": "0143"}
    assert (
        clean_agent_speech("Your number ending in 0143 is verified.", params_same)
        == "Your number ending in 0143 is verified."
    )


def test_clean_agent_speech_card_and_bank_last4_en() -> None:
    params = {
        "caller_provided_phone_last4": "0199",
        "phone_last4": "0143",
        "card_last4": "4242",
        "bank_last4": "6789",
    }
    # Credit card context in English
    text_card = "Your Visa credit card ending in 0000 has been charged."
    assert (
        clean_agent_speech(text_card, params)
        == "Your Visa credit card ending in 4242 has been charged."
    )
    # Bank context in English
    text_bank = "Your checking account ending in 0000 has been debited."
    assert (
        clean_agent_speech(text_bank, params)
        == "Your checking account ending in 6789 has been debited."
    )
    # Phone context in English
    text_phone = "Your phone number is 1111."
    assert clean_agent_speech(text_phone, params) == "Your phone number is 0199."


def test_clean_agent_speech_card_and_bank_last4_fr() -> None:
    params = {
        "caller_provided_phone_last4": "0199",
        "phone_last4": "0143",
        "card_last4": "4242",
        "bank_last4": "6789",
    }
    # French carte de crédit context
    text_fr_card = "Votre carte de crédit se terminant par 0000 a été débitée."
    assert (
        clean_agent_speech(text_fr_card, params)
        == "Votre carte de crédit se terminant par 4242 a été débitée."
    )
    # French compte bancaire / chèques context
    text_fr_bank = "Votre compte bancaire chèque se terminant par 0000 est valide."
    assert (
        clean_agent_speech(text_fr_bank, params)
        == "Votre compte bancaire chèque se terminant par 6789 est valide."
    )
    # French phone context
    text_fr_phone = "Votre numéro est 0000."
    assert clean_agent_speech(text_fr_phone, params) == "Votre numéro est 0199."


def test_clean_agent_speech_card_and_bank_last4_es() -> None:
    params = {
        "caller_provided_phone_last4": "0199",
        "phone_last4": "0143",
        "card_last4": "4242",
        "bank_last4": "6789",
    }
    # Spanish tarjeta de débito context
    text_es_card = "Su tarjeta de débito que termina en 0000 ha sido confirmada."
    assert (
        clean_agent_speech(text_es_card, params)
        == "Su tarjeta de débito que termina en 4242 ha sido confirmada."
    )
    # Spanish cuenta bancaria context
    text_es_bank = "Su cuenta bancaria que termina en 0000 está registrada."
    assert (
        clean_agent_speech(text_es_bank, params)
        == "Su cuenta bancaria que termina en 6789 está registrada."
    )
    # Spanish phone context
    text_es_phone = "Su número es 0000."
    assert clean_agent_speech(text_es_phone, params) == "Su número es 0199."


def test_clean_agent_speech_already_matching_last4_kept() -> None:
    params = {
        "caller_provided_phone_last4": "0199",
        "card_last4": "4242",
        "bank_last4": "6789",
    }
    # Card already matches
    assert "4242" in clean_agent_speech("ending in 4242", params)
    # Bank already matches
    assert "6789" in clean_agent_speech("ending in 6789", params)


def test_enforce_handover_utterance_existing_text() -> None:
    # When text is already non-empty, it is returned intact
    assert enforce_handover_utterance("Please wait a moment.") == "Please wait a moment."
    assert enforce_handover_utterance("Hold on.", {"handover_complete": True}) == "Hold on."


def test_enforce_handover_utterance_from_state_handoff_message() -> None:
    msg_en = "I'm transferring you to a member of our team now. Thank you for your patience."
    state = {"handover_complete": True, "handoff_message": msg_en}
    assert enforce_handover_utterance("", state) == msg_en
    assert enforce_handover_utterance("   ", state) == msg_en

    # Incomplete handover in state
    assert enforce_handover_utterance("", {"handover_complete": False, "handoff_message": msg_en}) == ""


def test_enforce_handover_utterance_called_tools_business() -> None:
    # Business transfer in EN, FR, ES
    for lang, phrase in (
        ("en-US", "business account"),
        ("fr-CA", "compte affaires"),
        ("es-US", "cuenta comercial"),
    ):
        line = enforce_handover_utterance(
            "",
            called_tools=("handover_to_person",),
            tool_args_list=({"reason": "business_handoff", "language": lang},),
        )
        assert phrase in line


def test_enforce_handover_utterance_called_tools_fraud() -> None:
    # Fraud transfer has empathy protocol + live agent handoff
    line_en = enforce_handover_utterance(
        "",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "suspected_fraud_lockout", "language": "en-US"},),
    )
    assert "facing challenges" in line_en
    assert "representative who can help" in line_en

    line_fr = enforce_handover_utterance(
        "",
        called_tools=("execute_live_agent_handover",),
        tool_args_list=({"reason": "fraud", "language": "fr-CA"},),
    )
    assert "difficultés" in line_fr
    assert "représentant" in line_fr


def test_enforce_handover_utterance_called_tools_specialist_and_refund() -> None:
    # Refund threshold / billing specialist
    line_refund = enforce_handover_utterance(
        "",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "refund_threshold_exceeded", "language": "en-US"},),
    )
    assert "billing specialist" in line_refund

    line_queue = enforce_handover_utterance(
        "",
        called_tools=("handover_to_person",),
        tool_args_list=({"target_queue": "billing_specialist", "language": "fr-CA"},),
    )
    assert "spécialiste de la facturation" in line_queue

    line_specialist = enforce_handover_utterance(
        "",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "specialist_required", "language": "es-US"},),
    )
    assert "especialista de facturación" in line_specialist


def test_enforce_handover_utterance_called_tools_default_live_agent() -> None:
    line_default = enforce_handover_utterance(
        "",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "general_inquiry", "language": "en-US"},),
    )
    assert "representative who can help" in line_default

    line_no_tools = enforce_handover_utterance(
        "",
        called_tools=("lookup_account",),
        tool_args_list=({"identifier": "2025550143"},),
    )
    assert line_no_tools == ""


def test_speech_mappingproxy_and_adk_state() -> None:
    from types import MappingProxyType

    class MockAdkState:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = dict(data)

        def get(self, key: str, default: Any = None) -> Any:
            return self._data.get(key, default)

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

    raw = {
        "caller_provided_phone_last4": "0199",
        "card_last4": "4242",
        "bank_last4": "6789",
        "account_id": "A558475",
        "language": "fr-CA",
        "handover_complete": True,
        "handoff_message": "Message de transfert",
    }
    for state_obj in (MappingProxyType(raw), MockAdkState(raw)):
        res = clean_agent_speech("Votre carte terminant par 0000 est valide.", state_obj)
        assert "4242" in res
        res_bank = clean_agent_speech("Votre compte bancaire terminant par 0000 est valide.", state_obj)
        assert "6789" in res_bank
        handover_res = enforce_handover_utterance("", state_obj)
        assert handover_res == "Message de transfert"


def test_speech_account_last4_never_rewritten_to_bank() -> None:
    params = {
        "caller_provided_phone_last4": "0199",
        "card_last4": "4242",
        "bank_last4": "6789",
        "account_id": "A558475",
    }
    # Account ending in 0199 (same as caller phone)
    assert clean_agent_speech("I found your account ending in 0199.", params) == "I found your account ending in 0199."
    assert clean_agent_speech("J'ai trouvé votre compte se terminant par 0199.", params) == "J'ai trouvé votre compte se terminant par 0199."
    # Account ending in 8475 (matches account_id last 4)
    assert clean_agent_speech("I found your billing account ending in 8475.", params) == "I found your billing account ending in 8475."
    assert "6789" not in clean_agent_speech("I found your billing account ending in 8475.", params)


def test_speech_dual_card_bank_and_pad_debit() -> None:
    params = {
        "card_last4": "4242",
        "bank_last4": "6789",
        "caller_provided_phone_last4": "0199",
    }
    # Dual in one sentence
    en_both = "Would you like to use Visa ending in 4242 or bank ending in 6789?"
    assert clean_agent_speech(en_both, params) == en_both

    # Pre-authorized debit on bank account
    en_pad = "Pre-authorized debit on your bank account ending in 6789 is active."
    assert clean_agent_speech(en_pad, params) == en_pad

    fr_pad = "Le débit sur votre compte bancaire terminant par 6789 est confirmé."
    assert clean_agent_speech(fr_pad, params) == fr_pad

    es_pad = "El débito en su cuenta bancaria que termina en 6789 está activo."
    assert clean_agent_speech(es_pad, params) == es_pad


def test_speech_strip_markdown_bullets_and_codefence() -> None:
    raw = "Options:\n- Plan Starter\n- Plan Plus\n• Plan Gig\nHere is code:\n```json\nRef R123456\n```\nContact 514-555-0199 for pre-authorized debit."
    cleaned = clean_speech(raw)
    assert "- " not in cleaned
    assert "• " not in cleaned
    assert "```" not in cleaned
    assert "json" not in cleaned
    assert "pre-authorized" in cleaned
    assert "0199" in cleaned


def test_enforce_handover_utterance_paraphrased_and_secondary_language() -> None:
    # Paraphrased existing text with business handoff
    res = enforce_handover_utterance(
        "I will transfer you now.",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "business_handoff", "language": "en-US"},),
    )
    assert "business account" in res
    assert "I will transfer you now." in res

    # Fraud handoff with existing text
    res_fraud = enforce_handover_utterance(
        "Please hold.",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "fraud_investigation", "language": "en-US"},),
    )
    assert "challenges" in res_fraud
    assert "representative who can help" in res_fraud

    # Specialist handoff
    res_spec = enforce_handover_utterance(
        "Attendez un instant.",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "refund_threshold", "language": "fr-CA"},),
    )
    assert "spécialiste de la facturation" in res_spec

    # Secondary language (de-DE): should NOT append English fallback copy onto existing text
    res_de = enforce_handover_utterance(
        "Moment bitte, ich verbinde Sie.",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "secondary_language_live_agent", "language": "de-DE"},),
    )
    assert res_de == "Moment bitte, ich verbinde Sie."


def test_speech_joint_4_last4_all_orders_en_fr_es() -> None:
    params = {
        "account_id": "ACC-8475",
        "phone_last4": "0143",
        "caller_provided_phone_last4": "0199",
        "card_last4": "4242",
        "bank_last4": "6789",
        "declined_card_last4": "9999",
    }
    en_1 = "Your phone ending in 0199, account ending in 8475, Visa card ending in 4242, and bank account ending in 6789 are verified."
    assert clean_agent_speech(en_1, params) == en_1

    en_2 = "Your Visa ending in 4242, phone ending in 0199, bank ending in 6789, and account ending in 8475 are on file."
    assert clean_agent_speech(en_2, params) == en_2

    fr_1 = "Votre carte terminant par 4242, téléphone terminant par 0199, compte bancaire terminant par 6789 et compte terminant par 8475 sont actifs."
    assert clean_agent_speech(fr_1, params) == fr_1

    es_1 = "Su tarjeta terminada en 4242, teléfono terminado en 0199, banco que termina en 6789 y cuenta que termina en 8475 están listos."
    assert clean_agent_speech(es_1, params) == es_1


def test_speech_pad_vs_debit_card_and_word_boundaries() -> None:
    params = {
        "caller_provided_phone_last4": "0199",
        "phone_last4": "0143",
        "card_last4": "4242",
        "bank_last4": "6789",
        "account_id": "ACC-8475",
    }
    # PAD phrases without "bank" noun bind to bank_last4 (6789)
    assert (
        clean_agent_speech("Your pre-authorized debit ending in 0000 is set up.", params)
        == "Your pre-authorized debit ending in 6789 is set up."
    )
    assert (
        clean_agent_speech("Your bank account for pre-authorized debit ending in 0000 is active.", params)
        == "Your bank account for pre-authorized debit ending in 6789 is active."
    )
    assert (
        clean_agent_speech("Votre débit préautorisé se terminant par 0000 est confirmé.", params)
        == "Votre débit préautorisé se terminant par 6789 est confirmé."
    )
    assert (
        clean_agent_speech("Votre prélèvement préautorisé se terminant par 0000 est actif.", params)
        == "Votre prélèvement préautorisé se terminant par 6789 est actif."
    )
    assert (
        clean_agent_speech("Su débito preautorizado que termina en 0000 está activo.", params)
        == "Su débito preautorizado que termina en 6789 está activo."
    )
    # Debit card phrases still bind to card_last4 (4242)
    assert (
        clean_agent_speech("Your debit card ending in 0000 was charged.", params)
        == "Your debit card ending in 4242 was charged."
    )
    assert (
        clean_agent_speech("Votre carte de débit se terminant par 0000 est active.", params)
        == "Votre carte de débit se terminant par 4242 est active."
    )
    assert (
        clean_agent_speech("Su tarjeta de débito terminada en 0000 está activa.", params)
        == "Su tarjeta de débito terminada en 4242 está activa."
    )
    # Word boundaries: "cancelled" != "cell" and "keypad" != "pad"
    assert (
        clean_agent_speech("Your cancelled account ending in 8475 is closed.", params)
        == "Your cancelled account ending in 8475 is closed."
    )
    assert (
        clean_agent_speech("Use your phone keypad for the line ending in 0000.", params)
        == "Use your phone keypad for the line ending in 0199."
    )
    assert (
        clean_agent_speech("Thank you for your card payment. Your phone ending in 0000 is verified.", params)
        == "Thank you for your card payment. Your phone ending in 0199 is verified."
    )


def test_speech_declined_card_and_iso_date_collision_guard() -> None:
    params = {
        "account_id": "ACC-8475",
        "phone_last4": "2026",
        "caller_provided_phone_last4": "0199",
        "card_last4": "4242",
        "bank_last4": "6789",
        "declined_card_last4": "9999",
    }
    declined_txt = "Your Visa card ending in 9999 was declined, so we charged your card ending in 4242."
    assert clean_agent_speech(declined_txt, params) == declined_txt

    date_txt = "Your payment is scheduled for 2026-10-15 on your phone ending in 2026."
    assert (
        clean_agent_speech(date_txt, params)
        == "Your payment is scheduled for 2026-10-15 on your phone ending in 0199."
    )


def test_enforce_handover_fraud_empathy_precedes_hold_line() -> None:
    for loc, generic, emp_sub, hold_sub in (
        (
            "en-US",
            "I'll connect you to a representative who can help. Please hold.",
            "facing challenges",
            "Please hold",
        ),
        (
            "fr-CA",
            "Je vais vous mettre en communication avec un représentant qui pourra vous aider. Veuillez patienter.",
            "ces difficultés",
            "Veuillez patienter",
        ),
        (
            "es-US",
            "Le comunicaré con un representante que pueda ayudarle. Por favor espere.",
            "pasando por dificultades",
            "Por favor espere",
        ),
    ):
        out = enforce_handover_utterance(
            generic,
            called_tools=("handover_to_person",),
            tool_args_list=({"reason": "fraud_escalation", "language": loc},),
        )
        assert emp_sub in out and hold_sub in out
        assert out.index(emp_sub) < out.index(hold_sub)

    lead_in_out = enforce_handover_utterance(
        "I see unauthorized activity. I'll connect you to a representative who can help. Please hold.",
        called_tools=("handover_to_person",),
        tool_args_list=({"reason": "fraud_escalation", "language": "en-US"},),
    )
    assert lead_in_out.index("facing challenges") < lead_in_out.index("Please hold")


def test_enforce_closing_utterance_localizations() -> None:
    from lib.speech import enforce_closing_utterance

    assert "Thank you for contacting Telco" in enforce_closing_utterance("resolved", "en-US")
    assert "Merci d'avoir choisi Telco" in enforce_closing_utterance("resolved", "fr-CA")
    assert "¡Gracias por llamar a Telco!" in enforce_closing_utterance("resolved", "es-US")
    assert "only able to assist with Telco" in enforce_closing_utterance("malicious_input", "en-US")
    assert "unable to complete this call" in enforce_closing_utterance("blocked_caller", "en-US")

