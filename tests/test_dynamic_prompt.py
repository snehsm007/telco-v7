"""Tests for lib/dynamic_prompt.py covering language detection and dynamic prompt filter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import pytest

from lib.dynamic_prompt import (
    LANGUAGE_SHEET_SENTINEL,
    SHARED_COGNATES,
    apply_language_prompt_filter,
    build_language_sheet,
    detect_active_call_language,
    detect_utterance_language,
    extract_user_utterances,
)


def test_shared_cognates_set() -> None:
    assert "internet" in SHARED_COGNATES
    assert "wifi" in SHARED_COGNATES
    assert "router" in SHARED_COGNATES
    assert len(SHARED_COGNATES) > 20


def test_detect_utterance_language_empty_and_digits_inertia() -> None:
    assert detect_utterance_language("", "en-US") == "en-US"
    assert detect_utterance_language("[pause]", "fr-CA") == "fr-CA"
    assert detect_utterance_language("[silence] 123456 [pause]", "es-US") == "es-US"
    assert detect_utterance_language("123-456-7890", "fr-CA") == "fr-CA"
    assert detect_utterance_language("... --- ...", "en-US") == "en-US"


def test_detect_utterance_language_dtmf_digit_selection() -> None:
    # Standalone DTMF digit 2 selects French
    assert detect_utterance_language("2", "en-US") == "fr-CA"
    assert detect_utterance_language(" 2 ", "en-US") == "fr-CA"
    assert detect_utterance_language("2.", "en-US") == "fr-CA"
    assert detect_utterance_language("2#", "en-US") == "fr-CA"
    assert detect_utterance_language("User: 2", "en-US") == "fr-CA"
    assert detect_utterance_language("[dtmf: 2]", "en-US") == "fr-CA"
    assert detect_utterance_language("[keypad: 2]", "en-US") == "fr-CA"
    assert detect_utterance_language("option 2", "en-US") == "fr-CA"
    assert detect_utterance_language("touche 2", "en-US") == "fr-CA"

    # Standalone DTMF digit 1 selects English
    assert detect_utterance_language("1", "en-US") == "en-US"
    assert detect_utterance_language("User: 1", "en-US") == "en-US"
    assert detect_utterance_language("[dtmf: 1]", "en-US") == "en-US"
    assert detect_utterance_language("option 1", "en-US") == "en-US"


def test_detect_utterance_language_explicit_switches() -> None:
    # French
    assert detect_utterance_language("je voudrais parler en français", "en-US") == "fr-CA"
    assert detect_utterance_language("switch to french please", "en-US") == "fr-CA"
    assert detect_utterance_language("passer au français svp", "en-US") == "fr-CA"
    assert detect_utterance_language("in french", "en-US") == "fr-CA"

    # English
    assert detect_utterance_language("in english please", "fr-CA") == "en-US"
    assert detect_utterance_language("switch to english", "es-US") == "en-US"
    assert detect_utterance_language("parler en anglais", "fr-CA") == "en-US"
    assert detect_utterance_language("passer à l'anglais", "fr-CA") == "en-US"

    # Spanish
    assert detect_utterance_language("en español por favor", "en-US") == "es-US"
    assert detect_utterance_language("hablar en español", "en-US") == "es-US"
    assert detect_utterance_language("switch to spanish", "en-US") == "es-US"
    assert detect_utterance_language("en espanol", "en-US") == "es-US"

    # Other world languages
    assert detect_utterance_language("em português por favor", "en-US") == "pt-BR"
    assert detect_utterance_language("switch to portuguese", "en-US") == "pt-BR"
    assert detect_utterance_language("auf deutsch bitte", "en-US") == "de-DE"
    assert detect_utterance_language("switch to german", "en-US") == "de-DE"
    assert detect_utterance_language("in italiano per favore", "en-US") == "it-IT"
    assert detect_utterance_language("switch to italian", "en-US") == "it-IT"
    assert detect_utterance_language("in mandarin please", "en-US") == "zh-CN"
    assert detect_utterance_language("switch to mandarin", "en-US") == "zh-CN"
    assert detect_utterance_language("in hindi please", "en-US") == "hi-IN"
    assert detect_utterance_language("switch to hindi", "en-US") == "hi-IN"
    assert detect_utterance_language("in arabic please", "en-US") == "ar-XA"
    assert detect_utterance_language("switch to arabic", "en-US") == "ar-XA"
    assert detect_utterance_language("in japanese please", "en-US") == "ja-JP"
    assert detect_utterance_language("switch to japanese", "en-US") == "ja-JP"
    assert detect_utterance_language("in korean please", "en-US") == "ko-KR"
    assert detect_utterance_language("switch to korean", "en-US") == "ko-KR"


def test_detect_utterance_language_scripts() -> None:
    # Arabic script
    assert detect_utterance_language("مرحبا كيف حالك", "en-US") == "ar-XA"
    # Devanagari script (Hindi)
    assert detect_utterance_language("नमस्ते आप कैसे हैं", "en-US") == "hi-IN"
    # Japanese kana
    assert detect_utterance_language("こんにちは", "en-US") == "ja-JP"
    # Korean hangul
    assert detect_utterance_language("안녕하세요", "en-US") == "ko-KR"
    # Chinese CJK
    assert detect_utterance_language("你好我想查账单", "en-US") == "zh-CN"


def test_detect_utterance_language_isolated_courtesy_words_keep_inertia() -> None:
    assert detect_utterance_language("merci", "en-US") == "en-US"
    assert detect_utterance_language("gracias", "en-US") == "en-US"


def test_detect_utterance_language_markers_and_scoring() -> None:
    # French markers and accents
    assert detect_utterance_language("Bonjour j'aimerais voir ma facture", "en-US") == "fr-CA"
    assert detect_utterance_language("J'ai une panne de réseau", "en-US") == "fr-CA"

    # Spanish markers and punctuation
    assert detect_utterance_language("Hola necesito ayuda con mi cuenta", "en-US") == "es-US"
    assert detect_utterance_language("¿Cuánto debo en mi tarjeta?", "en-US") == "es-US"

    # English markers (at least 3 markers with no fr/es score)
    assert detect_utterance_language("Hello I want help with my account", "fr-CA") == "en-US"
    assert detect_utterance_language("Need to reset password please", "es-US") == "en-US"

    # Ambiguous or cognates fall back to current language
    assert detect_utterance_language("router modem wifi", "fr-CA") == "fr-CA"


def test_extract_user_utterances() -> None:
    # None and empty
    assert extract_user_utterances(None) == []
    assert extract_user_utterances(SimpleNamespace(contents=None)) == []
    assert extract_user_utterances(SimpleNamespace(contents=[])) == []

    # Non-user roles ignored
    req1 = SimpleNamespace(
        contents=[
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Hello")]),
            SimpleNamespace(role="system", parts=[SimpleNamespace(text="System instructions")]),
        ]
    )
    assert extract_user_utterances(req1) == []

    # User role with parts list
    req2 = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(text="My bill is high"),
                    SimpleNamespace(text="  "),
                    SimpleNamespace(text=None),
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Can you check it?")],
            ),
        ]
    )
    assert extract_user_utterances(req2) == ["My bill is high", "Can you check it?"]

    # User role with direct text attribute
    req3 = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", text="I need tech support"),
            SimpleNamespace(role="user", text="   "),
        ]
    )
    assert extract_user_utterances(req3) == ["I need tech support"]


def test_detect_active_call_language() -> None:
    req_fr = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'aimerais de l'aide pour ma facture")],
            )
        ]
    )
    # No locked language -> detects fr-CA
    assert detect_active_call_language({}, req_fr) == "fr-CA"

    # Locked language fr-CA
    assert detect_active_call_language({"language": "fr-CA"}, SimpleNamespace(contents=[])) == "fr-CA"

    # Locked en-US switches if caller speaks French
    assert detect_active_call_language({"language": "en-US"}, req_fr) == "fr-CA"

    # Locked en-US remains en-US if user utterance is English
    req_en = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Hello I want help with my account bill")],
            )
        ]
    )
    assert detect_active_call_language({"language": "en-US"}, req_en) == "en-US"


def test_build_language_sheet_supported_locales() -> None:
    for loc in ("en-US", "fr-CA", "es-US"):
        sheet = build_language_sheet(loc, agent_name="router")
        assert LANGUAGE_SHEET_SENTINEL in sheet
        assert f'<active_language_sheet locale="{loc}"' in sheet
        assert "### Required Disclosures & Spoken Lines" in sheet
        assert "### Mandatory Conversational Rules:" in sheet
        assert "</active_language_sheet>" in sheet


def test_build_language_sheet_world_languages() -> None:
    sheet_de = build_language_sheet("de-DE", agent_name="billing")
    assert LANGUAGE_SHEET_SENTINEL in sheet_de
    assert 'locale="de-DE"' in sheet_de
    assert "German" in sheet_de
    assert "### Canonical Templates:" in sheet_de
    assert "secondary_language_live_agent" in sheet_de
    assert "</active_language_sheet>" in sheet_de


def test_build_language_sheet_agents() -> None:
    for agent in ("router", "billing", "tech_support", "sales_equipment", "account"):
        sheet = build_language_sheet("fr-CA", agent_name=agent)
        assert LANGUAGE_SHEET_SENTINEL in sheet


def test_apply_language_prompt_filter_zero_writes_to_state() -> None:
    state_original = {"account_id": "A1001", "phone_last4": "0143", "auth_status": "pass"}
    state_copy = dict(state_original)
    context = SimpleNamespace(state=state_copy)

    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base agent instructions."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'ai une question sur ma facture")],
            )
        ],
    )

    result = apply_language_prompt_filter(context, req, agent_name="billing")
    assert result is None
    # Crucial assertion: ZERO writes to state!
    assert state_copy == state_original
    assert req.config.system_instruction.startswith("Base agent instructions.\n\n")
    assert LANGUAGE_SHEET_SENTINEL in req.config.system_instruction
    assert 'locale="fr-CA"' in req.config.system_instruction


def test_apply_language_prompt_filter_idempotence() -> None:
    context = SimpleNamespace(state={"language": "es-US"})
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Instructions here"),
        contents=[],
    )

    # First call
    apply_language_prompt_filter(context, req, agent_name="router")
    inst1 = req.config.system_instruction
    assert inst1.count(LANGUAGE_SHEET_SENTINEL) == 1

    # Second call - should not duplicate the sentinel or sheet!
    apply_language_prompt_filter(context, req, agent_name="router")
    inst2 = req.config.system_instruction
    assert inst2.count(LANGUAGE_SHEET_SENTINEL) == 1
    assert inst1 == inst2


def test_apply_language_prompt_filter_instruction_variants() -> None:
    context = SimpleNamespace(state={})

    # Case 1: config is None
    req_no_config = SimpleNamespace(config=None, contents=[])
    assert apply_language_prompt_filter(context, req_no_config) is None

    # Case 2: system_instruction is None
    req_no_sys = SimpleNamespace(config=SimpleNamespace(system_instruction=None), contents=[])
    assert apply_language_prompt_filter(context, req_no_sys) is None

    # Case 3: system_instruction has parts attribute with text
    part = SimpleNamespace(text="Instructions with parts")
    req_parts = SimpleNamespace(
        config=SimpleNamespace(system_instruction=SimpleNamespace(parts=[part])),
        contents=[],
    )
    apply_language_prompt_filter(context, req_parts)
    assert LANGUAGE_SHEET_SENTINEL in part.text

    # Case 4: system_instruction is list of strings
    sys_list_str = ["Instructions in list string"]
    req_list_str = SimpleNamespace(
        config=SimpleNamespace(system_instruction=sys_list_str),
        contents=[],
    )
    apply_language_prompt_filter(context, req_list_str)
    assert LANGUAGE_SHEET_SENTINEL in sys_list_str[0]

    # Case 5: system_instruction is list of objects with text attribute
    part_in_list = SimpleNamespace(text="Instructions in list object")
    sys_list_obj = [part_in_list]
    req_list_obj = SimpleNamespace(
        config=SimpleNamespace(system_instruction=sys_list_obj),
        contents=[],
    )
    apply_language_prompt_filter(context, req_list_obj)
    assert LANGUAGE_SHEET_SENTINEL in part_in_list.text


def test_multiturn_chronology_switches() -> None:
    # state has language en-US, turn 1 is French, turn 2 is English switch
    req_en = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour, j'ai besoin d'aide")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Actually, switch to English please")]),
        ]
    )
    assert detect_active_call_language({"language": "en-US"}, req_en) == "en-US"

    # state has language en-US, turn 1 is French, turn 2 is Spanish switch
    req_es = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour, j'ai besoin d'aide")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="En español por favor")]),
        ]
    )
    assert detect_active_call_language({"language": "en-US"}, req_es) == "es-US"


def test_english_call_with_quebec_address_stays_english() -> None:
    req = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with my internet plan")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="123 Rue Saint-Laurent, Montréal, Québec")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Which plan is fastest?")]),
        ]
    )
    assert detect_active_call_language({"language": "en-US"}, req) == "en-US"


def test_native_turn1_german_portuguese_italian_classification() -> None:
    de_utt = "Guten Tag, sprechen Sie Deutsch? Ich brauche Hilfe mit meiner Rechnung."
    assert detect_utterance_language(de_utt, "en-US") == "de-DE"

    pt_utt = "Olá, preciso de ajuda com a minha fatura por favor."
    assert detect_utterance_language(pt_utt, "en-US") == "pt-BR"

    it_utt = "Buongiorno, parla italiano? Perché ho bisogno di aiuto."
    assert detect_utterance_language(it_utt, "en-US") == "it-IT"


def test_quebec_street_addresses_on_english_calls_do_not_flip_to_french() -> None:
    en_turns = [
        "450 Rue Saint-André, Montréal, QC H2L 3V3",
        "My address is 450 Boulevard Crémazie Est, Montréal, QC H2P 1E7",
        "Check fiber availability at 800 Rue de la Gauchetière Ouest, Montréal",
        "I am moving to 1250 Rue Bélanger, Montréal, QC H2S 1H9",
        "Can you verify service at 550 Rue Saint-Denis, Montréal, QC H2J 2L5",
        "Moving to 1200 Boulevard Saint-Martin Ouest, Laval, QC H7S 2E4",
        "Check availability at 100 Rue Principale, Gatineau, QC J8X 2J7",
        "Service address is 250 Rue King Ouest, Sherbrooke, QC J1H 1R1",
        "Please check 1500 Boulevard Guillaume-Couture, Lévis, QC G6W 5M6",
        "Looking for coverage at 200 Rue Racine Est, Chicoutimi, QC G7H 1R9",
        "Moving to 50 Boulevard d'Youville, Châteauguay, QC J6J 4Z2",
        "320 Rue Sainte-Thérèse, Saint-Jérôme, QC J7Z 1A2",
        "75 Boulevard des Récollets, Trois-Rivières, Québec G9A 4N9",
    ]
    for utt in en_turns:
        assert detect_utterance_language(utt, "en-US") == "en-US"
        req = SimpleNamespace(
            contents=[
                SimpleNamespace(
                    role="user",
                    parts=[SimpleNamespace(text="Hi, I need to check internet availability.")],
                ),
                SimpleNamespace(role="user", parts=[SimpleNamespace(text=utt)]),
            ]
        )
        assert detect_active_call_language({"language": "en-US"}, req) == "en-US"

    # Bare Quebec street address on an active French session preserves fr-CA inertia
    assert detect_utterance_language("450 Rue Saint-André, Montréal, QC H2L 3V3", "fr-CA") == "fr-CA"

    # Genuine Turn-1 French utterances with Quebec street addresses or cities detect fr-CA
    fr_twins = [
        "Bonjour, j'habite au 450 rue Saint-André et ma facture est trop élevée",
        "J'habite au 450 rue Saint-André, Montréal, QC H2L 3V3",
        "J'aimerais vérifier la disponibilité au 800 rue de la Gauchetière Ouest",
        "La télé est brisée depuis 2 jours à Montréal",
    ]
    for fr_utt in fr_twins:
        assert detect_utterance_language(fr_utt, "en-US") == "fr-CA"


def test_native_phrased_multiturn_switches_and_negation_guards() -> None:
    assert detect_utterance_language("Peut-on continuer en anglais s'il vous plaît?", "fr-CA") == "en-US"
    assert detect_utterance_language("Can you speak English?", "fr-CA") == "en-US"
    assert detect_utterance_language("¿Podemos hablar en inglés por favor?", "es-US") == "en-US"
    assert detect_utterance_language("¿Podemos hablar en ingles por favor?", "es-US") == "en-US"
    assert detect_utterance_language("¿Habla inglés?", "es-US") == "en-US"
    assert detect_utterance_language("Quiero hablar inglés por favor.", "es-US") == "en-US"
    assert detect_utterance_language("In Spanish please.", "fr-CA") == "es-US"
    assert detect_utterance_language("Can you speak Spanish?", "en-US") == "es-US"
    assert detect_utterance_language("Peut-on parler en espagnol?", "fr-CA") == "es-US"
    assert detect_utterance_language("Can we speak French?", "en-US") == "fr-CA"
    assert detect_utterance_language("En francais s'il vous plait", "en-US") == "fr-CA"
    assert detect_utterance_language("Sorry, I don't speak French, can you speak English?", "fr-CA") == "en-US"
    assert detect_utterance_language("I don't speak French.", "en-US") == "en-US"
    assert detect_utterance_language("No puedo hablar inglés, en español por favor.", "en-US") == "es-US"
    assert detect_utterance_language("Non, en anglais s'il vous plaît.", "fr-CA") == "en-US"
    assert detect_utterance_language("No, en español por favor.", "en-US") == "es-US"


def test_turn1_pt_it_de_markers_and_spanish_negative_twins() -> None:
    assert (
        detect_utterance_language(
            "Bom dia, quero pagar a minha conta de internet, por favor.", "en-US"
        )
        == "pt-BR"
    )
    assert (
        detect_utterance_language(
            "Oi, gostaria de cancelar o meu plano de celular.", "en-US"
        )
        == "pt-BR"
    )
    assert (
        detect_utterance_language(
            "Buenos días, quiero pagar mi cuenta de internet, por favor", "en-US"
        )
        == "es-US"
    )
    assert (
        detect_utterance_language(
            "Hola, me gustaría cancelar mi plan de celular", "en-US"
        )
        == "es-US"
    )
    assert (
        detect_utterance_language(
            "Salve, la mia connessione internet non funziona, potete aiutarmi?", "en-US"
        )
        == "it-IT"
    )
    assert (
        detect_utterance_language(
            "Hallo, mein Internet hat eine Störung, bitte helfen Sie mir.", "en-US"
        )
        == "de-DE"
    )
    assert detect_utterance_language("Ich möchte meinen Vertrag kündigen.", "en-US") == "de-DE"


def test_extract_user_utterances_skips_relayed_agent_context_and_fences() -> None:
    req = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'aimerais de l'aide")],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "For context: below is a transcript of what another agent did, quoted "
                            "between <<<BEGIN_QUOTED_AGENT_CONTENT>>> and <<<END_QUOTED_AGENT_CONTENT>>>."
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "[router] said:\n<<<BEGIN_QUOTED_AGENT_CONTENT>>>\n"
                            "Cet appel peut être enregistré.\n"
                            "<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="D'accord. Mon numéro de téléphone est le 514-555-0123."
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "[router] called tool `lookup_account` with parameters:\n"
                            "<<<BEGIN_QUOTED_AGENT_CONTENT>>>\n"
                            "{'identifier': '514-555-0123', 'language': 'fr-CA'}\n"
                            "<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "[router] `lookup_account` tool returned result:\n"
                            "<<<BEGIN_QUOTED_AGENT_CONTENT>>>\n"
                            "{'status': 'ok', 'active_language': 'fr-CA', 'data': {'account_id': 'ACC-0123'}}\n"
                            "<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "[router] called tool `transfer_to_agent` with parameters:\n"
                            "<<<BEGIN_QUOTED_AGENT_CONTENT>>>\n"
                            "{'agent_name': 'account'}\n"
                            "<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "[router] `transfer_to_agent` tool returned result:\n"
                            "<<<BEGIN_QUOTED_AGENT_CONTENT>>>\n"
                            "{'result': None}\n"
                            "<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
        ]
    )

    extracted = extract_user_utterances(req)
    assert extracted == [
        "Bonjour j'aimerais de l'aide",
        "D'accord. Mon numéro de téléphone est le 514-555-0123.",
    ]


def test_detect_active_call_language_ve15_r3_replay() -> None:
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base account instructions."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "Bonjour. J'aimerais désactiver l'authentification multifacteur "
                            "sur mon compte, s'il vous plaît."
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="For context: below is a transcript of what another agent did..."
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="[router] said:\n<<<BEGIN_QUOTED_AGENT_CONTENT>>>\nMerci\n<<<END_QUOTED_AGENT_CONTENT>>>"
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="D'accord. Mon numéro de téléphone est le 514-555-0123."
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "[router] `lookup_account` tool returned result:\n"
                            "<<<BEGIN_QUOTED_AGENT_CONTENT>>>\n"
                            "{'status': 'ok', 'active_language': 'fr-CA', 'data': {'account_id': 'ACC-0123'}}\n"
                            "<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="[router] called tool `transfer_to_agent` with parameters:\n{'agent_name': 'account'}"
                    )
                ],
            ),
        ],
    )

    # 1. With state carrying French lock
    assert detect_active_call_language({"language": "fr-CA"}, req) == "fr-CA"

    # 2. With state empty (relayed active_language in contents resolves to fr-CA)
    assert detect_active_call_language({}, req) == "fr-CA"

    # 3. Before-model prompt filter injects fr-CA language sheet for account agent
    context_fr = SimpleNamespace(state={"language": "fr-CA"})
    apply_language_prompt_filter(context_fr, req, agent_name="account")
    assert 'locale="fr-CA"' in req.config.system_instruction


def test_detect_active_call_language_explicit_switch_from_french() -> None:
    req = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'ai besoin d'aide")],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Can we continue in English please?")],
            ),
        ]
    )
    # Locked French switches to English on explicit switch request
    assert detect_active_call_language({"language": "fr-CA"}, req) == "en-US"

