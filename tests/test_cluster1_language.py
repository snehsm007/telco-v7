"""Unit tests for Cluster 1: Language Detection, <state_update> Stripping & Double-Brace Templates.

Verifies:
1. <state_update> injection before Turn 1 (French and Spanish) does not lock language or block detection.
2. Mixed <state_update> and caller text in the same turn strips <state_update> and preserves caller text.
3. Empty connect turns (no user utterance) never lock language_locked or advance turn_index.
4. Turn 1 accurately detects and locks French (fr-CA) and Spanish (es-US).
5. Mid-call bare '2', 'oui', 'si', and keypad digits do not drift or flip locked language.
6. Bidirectional explicit language switching works across all pairs:
   - English <-> French
   - English <-> Spanish
   - French <-> Spanish
7. Double-brace template variable in global_instruction.txt does not leak single braces.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest

from lib.dynamic_prompt import (
    apply_language_prompt_filter,
    detect_active_call_language,
    detect_utterance_language,
    extract_user_utterances,
    _is_relay_or_quoted_part,
)

ROOT = Path(__file__).resolve().parent.parent
GLOBAL_INST_PATH = ROOT / "cxas_app" / "global_instruction.txt"


def test_global_instruction_uses_double_brace_date() -> None:
    """Verify global_instruction.txt uses {{current_date}} rather than single-brace {current_date}."""
    content = GLOBAL_INST_PATH.read_text(encoding="utf-8")
    assert "{{current_date}}" in content, "Expected {{current_date}} in global_instruction.txt"
    assert "{current_date}" not in content.replace("{{current_date}}", ""), (
        "Found legacy single-brace {current_date} in global_instruction.txt"
    )


def test_is_relay_or_quoted_part_state_update() -> None:
    """Verify _is_relay_or_quoted_part identifies pure state_update blocks as system/relay content."""
    pure_update = '<state_update>{"current_date": "2026-11-02"}</state_update>'
    assert _is_relay_or_quoted_part(pure_update) is True

    update_with_whitespace = '  <state_update>\n{"key": "value"}\n</state_update>  '
    assert _is_relay_or_quoted_part(update_with_whitespace) is True

    self_closing = '<state_update type="date" />'
    assert _is_relay_or_quoted_part(self_closing) is True

    # When user text is present alongside state_update, it is not a pure relay part
    mixed = '<state_update>{"current_date": "2026-11-02"}</state_update> Bonjour, je voudrais de l\'aide'
    assert _is_relay_or_quoted_part(mixed) is False


def test_extract_user_utterances_strips_state_update() -> None:
    """Verify extract_user_utterances ignores pure state_update turns and sanitizes mixed turns."""
    req_pure = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text='<state_update>{"current_date": "2026-11-02"}</state_update>')],
            )
        ]
    )
    assert extract_user_utterances(req_pure) == []

    req_mixed = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text='<state_update>{"current_date": "2026-11-02"}</state_update>\nBonjour, je veux annuler mon forfait'
                    )
                ],
            )
        ]
    )
    assert extract_user_utterances(req_mixed) == ["Bonjour, je veux annuler mon forfait"]

    # Injected state_update as user turn 0 followed by real caller turn 1
    req_seq = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text='<state_update>{"current_date": "2026-11-02"}</state_update>')],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Hola, necesito ayuda con mi cuenta")],
            ),
        ]
    )
    assert extract_user_utterances(req_seq) == ["Hola, necesito ayuda con mi cuenta"]


def test_state_update_injection_before_french_turn_1() -> None:
    """Verify that an injected <state_update> before Turn 1 does not lock language or prevent French detection."""
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base agent instructions."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text='<state_update>{"current_date": "2026-11-02"}</state_update>')],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'aimerais annuler mon forfait mobile")],
            ),
        ],
    )
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    context = SimpleNamespace(state=state)

    lang = detect_active_call_language(state, req)
    assert lang == "fr-CA", f"Expected fr-CA, got {lang}"

    apply_language_prompt_filter(context, req, agent_name="router", update_state=True)
    assert state["language"] == "fr-CA"
    assert state["language_locked"] is True
    assert state["turn_index"] == 1
    assert "Bonjour j'aimerais annuler mon forfait mobile" in state["utterance"]


def test_state_update_injection_before_spanish_turn_1() -> None:
    """Verify that an injected <state_update> before Turn 1 does not lock language or prevent Spanish detection."""
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base agent instructions."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text='<state_update>{"current_date": "2026-11-02"}</state_update>')],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Hola necesito ayuda con el pago de mi factura")],
            ),
        ],
    )
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    context = SimpleNamespace(state=state)

    lang = detect_active_call_language(state, req)
    assert lang == "es-US", f"Expected es-US, got {lang}"

    apply_language_prompt_filter(context, req, agent_name="billing", update_state=True)
    assert state["language"] == "es-US"
    assert state["language_locked"] is True
    assert state["turn_index"] == 1


def test_empty_connect_turn_does_not_lock_language() -> None:
    """Verify that an empty connect turn does not set language_locked to True or advance turn_index."""
    req_connect = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base agent instructions."),
        contents=[],
    )
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    context = SimpleNamespace(state=state)

    lang = detect_active_call_language(state, req_connect)
    assert lang == "en-US"

    apply_language_prompt_filter(context, req_connect, agent_name="router", update_state=True)
    # language_locked MUST remain False, and turn_index MUST remain 0!
    assert state.get("language_locked") is False
    assert state.get("turn_index") == 0

    # On the subsequent turn, French caller speaks and correctly locks fr-CA
    req_turn1 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base agent instructions."),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour, j'ai un problème avec mon téléphone")],
            )
        ],
    )
    lang_t1 = detect_active_call_language(state, req_turn1)
    assert lang_t1 == "fr-CA"

    apply_language_prompt_filter(context, req_turn1, agent_name="router", update_state=True)
    assert state["language"] == "fr-CA"
    assert state["language_locked"] is True
    assert state["turn_index"] == 1


def test_empty_connect_turn_followed_by_dtmf_2() -> None:
    """Verify that an empty connect turn followed by DTMF '2' accurately selects and locks French."""
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    context = SimpleNamespace(state=state)

    # Empty connect turn
    req_connect = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[],
    )
    apply_language_prompt_filter(context, req_connect, agent_name="router", update_state=True)
    assert state.get("language_locked") is False
    assert state.get("turn_index") == 0

    # Turn 1: user presses 2
    req_dtmf = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="2")]),
        ],
    )
    lang = detect_active_call_language(state, req_dtmf)
    assert lang == "fr-CA"

    apply_language_prompt_filter(context, req_dtmf, agent_name="router", update_state=True)
    assert state["language"] == "fr-CA"
    assert state["language_locked"] is True
    assert state["turn_index"] == 1


def test_mid_call_bare_tokens_no_drift() -> None:
    """Verify that mid-call bare '2', 'oui', 'si', or numbers never flip a locked language."""
    # French session: bare '2' or 'oui' does not flip to English
    fr_state: dict[str, Any] = {"language": "fr-CA", "language_locked": True, "turn_index": 2}
    req_fr_mid = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Comment puis-je vous aider?")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="oui")]),
        ]
    )
    assert detect_active_call_language(fr_state, req_fr_mid) == "fr-CA"

    req_fr_digits = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Entrez votre NIP.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="1234")]),
        ]
    )
    assert detect_active_call_language(fr_state, req_fr_digits) == "fr-CA"

    # English session: bare '2' (menu option 2) or 'merci' does not flip to French
    en_state: dict[str, Any] = {"language": "en-US", "language_locked": True, "turn_index": 2}
    req_en_mid = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Press 2 for technical support.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="2")]),
        ]
    )
    assert detect_active_call_language(en_state, req_en_mid) == "en-US"

    # Spanish session: bare 'si' or '2' does not flip
    es_state: dict[str, Any] = {"language": "es-US", "language_locked": True, "turn_index": 2}
    req_es_mid = SimpleNamespace(
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hola")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="¿Desea continuar?")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="si")]),
        ]
    )
    assert detect_active_call_language(es_state, req_es_mid) == "es-US"


def test_bidirectional_switch_english_to_french_and_back() -> None:
    """Verify bidirectional switching: EN -> FR -> EN -> FR."""
    state: dict[str, Any] = {"turn_index": 0, "language_locked": False}
    context = SimpleNamespace(state=state)

    # 1. Start in English
    req1 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with my bill")])],
    )
    apply_language_prompt_filter(context, req1, update_state=True)
    assert state["language"] == "en-US"
    assert state["language_locked"] is True

    # 2. Switch to French
    req2 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with my bill")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Sure.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Can we switch to French please?")]),
        ],
    )
    apply_language_prompt_filter(context, req2, update_state=True)
    assert state["language"] == "fr-CA"
    assert state["explicit_language_switch"] == "fr-CA"

    # 3. Intermediate French turn (stays French)
    req3 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with my bill")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Sure.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Can we switch to French please?")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Certainement.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="oui")]),
        ],
    )
    apply_language_prompt_filter(context, req3, update_state=True)
    assert state["language"] == "fr-CA"

    # 4. Switch back to English
    req4 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with my bill")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Sure.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Can we switch to French please?")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Certainement.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="oui")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="D'accord.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Please switch back to English")]),
        ],
    )
    apply_language_prompt_filter(context, req4, update_state=True)
    assert state["language"] == "en-US"
    assert state["explicit_language_switch"] == "en-US"

    # 5. Switch to French once more
    req5 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello, I need help with my bill")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Sure.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Can we switch to French please?")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Certainement.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="oui")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="D'accord.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Please switch back to English")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Switched.")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="revenir au français svp")]),
        ],
    )
    apply_language_prompt_filter(context, req5, update_state=True)
    assert state["language"] == "fr-CA"
    assert state["explicit_language_switch"] == "fr-CA"


def test_bidirectional_switch_english_to_spanish_and_back() -> None:
    """Verify bidirectional switching: EN -> ES -> EN."""
    state: dict[str, Any] = {"language": "en-US", "language_locked": True, "turn_index": 1}
    context = SimpleNamespace(state=state)

    # 1. Switch to Spanish
    req_to_es = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Hi")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="por favor hablar en español")]),
        ],
    )
    apply_language_prompt_filter(context, req_to_es, update_state=True)
    assert state["language"] == "es-US"
    assert state["explicit_language_switch"] == "es-US"

    # 2. Switch back to English
    req_to_en = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Hi")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="por favor hablar en español")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Hola")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="in english please")]),
        ],
    )
    apply_language_prompt_filter(context, req_to_en, update_state=True)
    assert state["language"] == "en-US"
    assert state["explicit_language_switch"] == "en-US"


def test_bidirectional_switch_french_to_spanish_and_back() -> None:
    """Verify bidirectional switching between non-English pairs: FR -> ES -> FR."""
    state: dict[str, Any] = {"language": "fr-CA", "language_locked": True, "turn_index": 1}
    context = SimpleNamespace(state=state)

    # 1. Switch from French to Spanish
    req_to_es = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="pouvez-vous parler en espagnol svp")]),
        ],
    )
    apply_language_prompt_filter(context, req_to_es, update_state=True)
    assert state["language"] == "es-US"
    assert state["explicit_language_switch"] == "es-US"

    # 2. Switch from Spanish back to French
    req_to_fr = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Bonjour")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="pouvez-vous parler en espagnol svp")]),
            SimpleNamespace(role="model", parts=[SimpleNamespace(text="Hola")]),
            SimpleNamespace(role="user", parts=[SimpleNamespace(text="switch to french please")]),
        ],
    )
    apply_language_prompt_filter(context, req_to_fr, update_state=True)
    assert state["language"] == "fr-CA"
    assert state["explicit_language_switch"] == "fr-CA"
