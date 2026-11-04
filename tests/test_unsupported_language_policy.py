"""Unit tests for ADR-36 PRD-strict unsupported-language policy."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lib.copy import (
    AGENT_VERBATIM_KEYS,
    SPOKEN_LINES,
    SUPPORTED_COPY_LOCALES,
    WORLD_LANGUAGE_NAMES,
    spoken_line,
)
from lib.dynamic_prompt import (
    LANGUAGE_SHEET_SENTINEL,
    LanguagePolicy,
    apply_language_prompt_filter,
    build_language_sheet,
    detect_active_call_language,
    detect_language_policy,
    detect_utterance_language,
    is_supported_locale,
)
from suite import grader


class _MockPart:
    def __init__(self, text: str | None = None, function_call: Any = None) -> None:
        self.text = text
        self.function_call = function_call

    @classmethod
    def from_text(cls, text: str) -> _MockPart:
        return cls(text=text)

    @classmethod
    def from_function_call(cls, name: str, args: dict[str, Any]) -> _MockPart:
        return cls(function_call=SimpleNamespace(name=name, args=args))


class _MockResponse:
    def __init__(self, parts: list[_MockPart]) -> None:
        self.parts = parts

    @classmethod
    def from_parts(cls, parts: list[_MockPart]) -> _MockResponse:
        return cls(parts=parts)


def test_copy_language_not_supported_and_world_language_names() -> None:
    """Verify exact language_not_supported copy and new script language names."""
    assert "language_not_supported" in SPOKEN_LINES
    assert (
        spoken_line("language_not_supported", "en-US")
        == "I'm sorry, I can only help you in English, French, or Spanish. Which language would you like to continue in?"
    )
    assert (
        spoken_line("language_not_supported", "fr-CA")
        == "Je suis désolé, je peux seulement vous aider en anglais, en français ou en espagnol. Dans quelle langue souhaitez-vous continuer?"
    )
    assert (
        spoken_line("language_not_supported", "es-US")
        == "Lo siento, solo puedo ayudarle en inglés, francés o español. ¿En qué idioma desea continuar?"
    )
    assert "language_not_supported" in AGENT_VERBATIM_KEYS["router"]
    for code, expected_name in (
        ("ru-RU", "Russian"),
        ("el-GR", "Greek"),
        ("he-IL", "Hebrew"),
        ("th-TH", "Thai"),
    ):
        assert WORLD_LANGUAGE_NAMES.get(code) == expected_name


def test_script_detection_and_is_supported_locale() -> None:
    """Verify Cyrillic, Greek, Hebrew, Thai script rules and is_supported_locale."""
    assert (
        detect_utterance_language("Здравствуйте, я хочу оплатить счёт.", "en-US")
        == "ru-RU"
    )
    assert (
        detect_utterance_language("Γεια σας, θέλω να πληρώσω τον λογαριασμό μου.", "en-US")
        == "el-GR"
    )
    assert (
        detect_utterance_language("שלום, אני רוצה לשלם את החשבון שלי.", "en-US")
        == "he-IL"
    )
    assert (
        detect_utterance_language("สวัสดี ฉันต้องการชำระบิลของฉัน", "en-US")
        == "th-TH"
    )

    # German, Hindi, Portuguese still detected by utterance detector
    assert (
        detect_utterance_language(
            "Guten Tag, ich möchte meine Rechnung bezahlen.", "en-US"
        )
        == "de-DE"
    )
    assert (
        detect_utterance_language("नमस्ते, मुझे अपना बिल भरना है।", "en-US")
        == "hi-IN"
    )
    assert (
        detect_utterance_language(
            "Olá, eu quero pagar a minha conta.", "en-US"
        )
        == "pt-BR"
    )

    for sup in SUPPORTED_COPY_LOCALES:
        assert is_supported_locale(sup) is True

    for unsup in (
        "de-DE",
        "hi-IN",
        "pt-BR",
        "it-IT",
        "ar-XA",
        "ja-JP",
        "ko-KR",
        "zh-CN",
        "ru-RU",
        "el-GR",
        "he-IL",
        "th-TH",
        "",
    ):
        assert is_supported_locale(unsup) is False


def test_telephony_german_turn_1_interception_and_turn_2_handover() -> None:
    """Verify Turn 0 session start + Turn 1 German notice + Turn 2 German handover."""
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    ctx = SimpleNamespace(state=state)

    # Turn 0: telephony session start
    req_t0 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base router prompt."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="<event>session start</event>")],
            )
        ],
    )
    resp_t0 = apply_language_prompt_filter(
        ctx,
        req_t0,
        agent_name="router",
        update_state=True,
        llm_response_cls=_MockResponse,
        part_cls=_MockPart,
    )
    assert resp_t0 is None
    assert state["turn_index"] == 0
    assert state["language_locked"] is False

    # Turn 1: German caller utterance
    de_t1 = "Guten Tag, ich möchte meine Rechnung bezahlen. Meine Telefonnummer ist 202-555-0143."
    req_t1 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base router prompt."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="<event>session start</event>")],
            ),
            SimpleNamespace(
                role="model",
                parts=[SimpleNamespace(text=spoken_line("greeting_main", "en-US"))],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text=de_t1)],
            ),
        ],
    )
    resp_t1 = apply_language_prompt_filter(
        ctx,
        req_t1,
        agent_name="router",
        update_state=True,
        llm_response_cls=_MockResponse,
        part_cls=_MockPart,
    )
    assert resp_t1 is not None
    expected_notice = (
        f"{spoken_line('language_not_supported', 'en-US')} "
        f"{spoken_line('language_not_supported', 'fr-CA')} "
        f"{spoken_line('language_not_supported', 'es-US')}"
    )
    assert len(resp_t1.parts) == 1
    assert resp_t1.parts[0].text == expected_notice
    assert resp_t1.parts[0].function_call is None
    assert state["language"] == "en-US"
    assert state["language_locked"] is False
    assert state["unsupported_language"] == "de-DE"
    assert state["unsupported_language_strikes"] == 1
    assert state["turn_index"] == 1

    # Turn 2: caller continues in German -> trilingual handoff + handover_to_person + end_session
    de_t2 = "Ja, bitte. Wie hoch ist mein aktueller Saldo?"
    req_t2 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base router prompt."),
        contents=[
            *req_t1.contents,
            SimpleNamespace(
                role="model",
                parts=[SimpleNamespace(text=expected_notice)],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text=de_t2)],
            ),
        ],
    )
    resp_t2 = apply_language_prompt_filter(
        ctx,
        req_t2,
        agent_name="router",
        update_state=True,
        llm_response_cls=_MockResponse,
        part_cls=_MockPart,
    )
    assert resp_t2 is not None
    expected_handoff = (
        f"{spoken_line('live_agent_handoff', 'en-US')} "
        f"{spoken_line('live_agent_handoff', 'fr-CA')} "
        f"{spoken_line('live_agent_handoff', 'es-US')}"
    )
    assert resp_t2.parts[0].text == expected_handoff
    fn_calls = [
        p.function_call for p in resp_t2.parts if getattr(p, "function_call", None)
    ]
    assert len(fn_calls) == 2
    assert fn_calls[0].name == "handover_to_person"
    assert fn_calls[0].args == {
        "reason": "secondary_language_live_agent",
        "target_queue": "multilingual_support",
        "summary": "Caller speaks German, which is not a supported language (English, French, Spanish).",
        "language": "en-US",
    }
    assert fn_calls[1].name == "end_session"
    assert fn_calls[1].args == {"reason": "secondary_language_live_agent"}
    assert state["language"] == "en-US"
    assert state["language_locked"] is False
    assert state["unsupported_language"] == "de-DE"
    assert state["unsupported_language_strikes"] == 2
    assert state["handover_complete"] is True
    assert state["handoff_status"] == "escalated"
    assert state["handoff_reason"] == "secondary_language_live_agent"
    assert state["handoff_message"] == expected_handoff


def test_german_then_switch_to_french_locks_french() -> None:
    """Verify German Turn 1 followed by French Turn 2 locks fr-CA with no interception."""
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    ctx = SimpleNamespace(state=state)

    de_t1 = "Guten Tag, ich möchte meine Rechnung bezahlen."
    fr_t2 = "Oui, en français s'il vous plaît, je veux payer ma facture"
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base router prompt."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text=de_t1)]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Notice")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text=fr_t2)]),
        ],
    )
    policy = detect_language_policy(state, req)
    assert policy.locale == "fr-CA"
    assert policy.latest_unsupported is False
    assert policy.unsupported_strikes == 0

    resp = apply_language_prompt_filter(
        ctx,
        req,
        agent_name="router",
        update_state=True,
        llm_response_cls=_MockResponse,
        part_cls=_MockPart,
    )
    assert resp is None
    assert state["language"] == "fr-CA"
    assert state["language_locked"] is True
    assert 'locale="fr-CA"' in req.config.system_instruction


@pytest.mark.parametrize(
    "choice_word,expected_locale",
    [
        ("English", "en-US"),
        ("anglais", "en-US"),
        ("inglés", "en-US"),
        ("ingles", "en-US"),
        ("French", "fr-CA"),
        ("français", "fr-CA"),
        ("francais", "fr-CA"),
        ("frances", "fr-CA"),
        ("francés", "fr-CA"),
        ("Spanish", "es-US"),
        ("español", "es-US"),
        ("espanol", "es-US"),
        ("espagnol", "es-US"),
    ],
)
def test_unsupported_then_one_word_language_choice(
    choice_word: str, expected_locale: str
) -> None:
    """Verify one-word language choices after an unsupported turn lock the chosen locale."""
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base router prompt."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Guten Tag, ich brauche Hilfe.")],
            ),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Notice")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text=choice_word)]),
        ],
    )
    state: dict[str, Any] = {}
    policy = detect_language_policy(state, req)
    assert policy.locale == expected_locale
    assert policy.latest_unsupported is False
    assert policy.unsupported_strikes == 0


def test_explicit_switch_to_unsupported_never_locks() -> None:
    """Verify explicit switch phrase 'auf deutsch bitte' counts as unsupported and never locks de-DE."""
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base router prompt."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="auf deutsch bitte")],
            )
        ],
    )
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    policy = detect_language_policy(state, req)
    assert policy.locale == "en-US"
    assert policy.caller_locale == "de-DE"
    assert policy.unsupported_strikes == 1
    assert policy.latest_unsupported is True
    assert detect_active_call_language(state, req) == "en-US"

    resp = apply_language_prompt_filter(
        SimpleNamespace(state=state),
        req,
        agent_name="router",
        update_state=True,
        llm_response_cls=_MockResponse,
        part_cls=_MockPart,
    )
    assert resp is not None
    assert state["language"] == "en-US"
    assert state["language_locked"] is False

    # Unsupported state language/preferred_language coerced to en-US and not locked
    assert detect_active_call_language({"language": "de-DE"}, SimpleNamespace(contents=[])) == "en-US"
    assert detect_active_call_language({"preferred_language": "pt-BR"}, SimpleNamespace(contents=[])) == "en-US"


def test_supported_languages_and_sheet_invariants() -> None:
    """Verify French, Spanish, English Turn 1 regressions and sheet never says Speak 100% natively."""
    for utt, expected_loc in (
        ("Bonjour, j'ai une question sur ma facture.", "fr-CA"),
        ("Hola, necesito ayuda con mi factura.", "es-US"),
        ("Hello, I need help with my bill.", "en-US"),
    ):
        state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
        req = SimpleNamespace(
            config=SimpleNamespace(system_instruction="Base router prompt."),
            contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text=utt)])],
        )
        resp = apply_language_prompt_filter(
            SimpleNamespace(state=state),
            req,
            agent_name="router",
            update_state=True,
            llm_response_cls=_MockResponse,
            part_cls=_MockPart,
        )
        assert resp is None
        assert state["language"] == expected_loc
        assert state["language_locked"] is True
        assert f'locale="{expected_loc}"' in req.config.system_instruction
        assert "Speak 100% natively" not in req.config.system_instruction
        assert "Service is offered only in English, Canadian French and Spanish." in req.config.system_instruction

    # Even if build_language_sheet is called with de-DE or an unsupported policy
    sheet_de = build_language_sheet("de-DE", agent_name="billing")
    assert "Speak 100% natively" not in sheet_de
    assert 'locale="en-US"' in sheet_de

    unsup_policy = LanguagePolicy(
        locale="en-US",
        caller_locale="de-DE",
        unsupported_strikes=1,
        latest_unsupported=True,
    )
    sheet_with_policy = build_language_sheet("en-US", agent_name="router", policy=unsup_policy)
    assert LANGUAGE_SHEET_SENTINEL in sheet_with_policy
    assert 'caller_language="German (de-DE)" status="unsupported"' in sheet_with_policy
    assert "Unsupported caller language" in sheet_with_policy


def test_grader_exempts_trilingual_notice_and_handoff() -> None:
    """Verify suite/grader.py exempts trilingual language_not_supported and live_agent_handoff turns."""
    trilingual_notice = (
        f"{spoken_line('language_not_supported', 'en-US')} "
        f"{spoken_line('language_not_supported', 'fr-CA')} "
        f"{spoken_line('language_not_supported', 'es-US')}"
    )
    trilingual_handoff = (
        f"{spoken_line('live_agent_handoff', 'en-US')} "
        f"{spoken_line('live_agent_handoff', 'fr-CA')} "
        f"{spoken_line('live_agent_handoff', 'es-US')}"
    )
    transcript = {
        "id": "test-unsup-de",
        "language": "en",
        "turns": [
            {"role": "user", "text": "Guten Tag, ich möchte meine Rechnung bezahlen."},
            {"role": "agent", "text": trilingual_notice, "tool_calls": []},
            {"role": "user", "text": "Ja, bitte. Wie hoch ist mein aktueller Saldo?"},
            {
                "role": "agent",
                "text": trilingual_handoff,
                "tool_calls": [
                    {
                        "name": "handover_to_person",
                        "args": {
                            "reason": "secondary_language_live_agent",
                            "target_queue": "multilingual_support",
                        },
                    },
                    {
                        "name": "end_session",
                        "args": {"reason": "secondary_language_live_agent"},
                    },
                ],
            },
        ],
    }
    res = grader.grade(transcript)
    assert res["verdict"] == "pass", f"Unexpected findings: {res['findings']}"
