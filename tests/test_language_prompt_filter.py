"""Tests for before_model_callbacks/language_prompt_filter across all 5 agents."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import pytest

from cxas_app.agents.account.before_model_callbacks.language_prompt_filter import python_code as account_lpf
from cxas_app.agents.billing.before_model_callbacks.language_prompt_filter import python_code as billing_lpf
from cxas_app.agents.router.before_model_callbacks.language_prompt_filter import python_code as router_lpf
from cxas_app.agents.sales_equipment.before_model_callbacks.language_prompt_filter import python_code as sales_lpf
from cxas_app.agents.tech_support.before_model_callbacks.language_prompt_filter import python_code as tech_lpf

AGENT_CALLBACKS = [
    ("router", router_lpf),
    ("billing", billing_lpf),
    ("tech_support", tech_lpf),
    ("sales_equipment", sales_lpf),
    ("account", account_lpf),
]


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_injects_sentinel_and_zero_state_writes(
    agent_name: str, callback_mod: Any
) -> None:
    initial_state = {
        "account_id": "A1001",
        "phone_last4": "0143",
        "language": "fr-CA",
        "auth_status": "pass",
    }
    state_copy = dict(initial_state)
    context = SimpleNamespace(state=state_copy)

    initial_instruction = f"Base prompt for {agent_name}."
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction=initial_instruction),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'ai une question")],
            )
        ],
    )

    result = callback_mod.before_model_callback(context, req)

    # 1. Must return None
    assert result is None

    # 2. Injects <!-- ACTIVE_LANGUAGE_SHEET -->
    assert "<!-- ACTIVE_LANGUAGE_SHEET -->" in req.config.system_instruction
    assert f'<active_language_sheet locale="fr-CA"' in req.config.system_instruction

    # 3. ZERO writes to callback_context.state
    assert state_copy == initial_state


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_english_default_and_parts_structure(
    agent_name: str, callback_mod: Any
) -> None:
    state = {"language": "en-US"}
    part = SimpleNamespace(text="System instructions here.")
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction=SimpleNamespace(parts=[part])),
        contents=[],
    )

    result = callback_mod.before_model_callback(SimpleNamespace(state=state), req)
    assert result is None
    assert "<!-- ACTIVE_LANGUAGE_SHEET -->" in part.text
    assert 'locale="en-US"' in part.text


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_mappingproxy_and_adk_state_with_digits(
    agent_name: str, callback_mod: Any
) -> None:
    from types import MappingProxyType

    class MockAdkState:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = dict(data)

        def get(self, key: str, default: Any = None) -> Any:
            return self._data.get(key, default)

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

    raw_state = {"language": "fr-CA"}
    for st in (MappingProxyType(raw_state), MockAdkState(raw_state)):
        req = SimpleNamespace(
            config=SimpleNamespace(system_instruction="Base prompt."),
            contents=[
                SimpleNamespace(
                    role="user",
                    parts=[SimpleNamespace(text="4242")],
                )
            ],
        )
        res = callback_mod.before_model_callback(SimpleNamespace(state=st), req)
        assert res is None
        assert '<active_language_sheet locale="fr-CA"' in req.config.system_instruction

