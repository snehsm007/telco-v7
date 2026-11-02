"""Integration tests for agent callbacks across all 5 agents."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import pytest

from cxas_app.agents.account.after_model_callbacks.speech_hygiene import python_code as account_cb
from cxas_app.agents.billing.after_model_callbacks.speech_hygiene import python_code as billing_cb
from cxas_app.agents.router.after_model_callbacks.speech_hygiene import python_code as router_cb
from cxas_app.agents.sales_equipment.after_model_callbacks.speech_hygiene import python_code as sales_cb
from cxas_app.agents.tech_support.after_model_callbacks.speech_hygiene import python_code as tech_cb

ALL_AGENT_CALLBACKS = [
    router_cb,
    billing_cb,
    tech_cb,
    sales_cb,
    account_cb,
]


class MockPart:
    """Mock Part for testing Part.from_text branch."""

    def __init__(self, text: str) -> None:
        self.text = text

    @classmethod
    def from_text(cls, text: str) -> MockPart:
        return cls(text=text)


@pytest.mark.parametrize("cb", ALL_AGENT_CALLBACKS)
def test_callbacks_prefer_caller_last4_and_strip_markdown(cb) -> None:
    state = {
        "phone_last4": "0143",
        "caller_provided_phone_last4": "0199",
        "handover_complete": False,
    }
    resp = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text="**Your number ending in 0143 is ready.**")]
        )
    )
    out = cb.after_model_callback(SimpleNamespace(state=state), resp)
    assert out is resp
    assert resp.content.parts[0].text == "Your number ending in 0199 is ready."


@pytest.mark.parametrize("cb", ALL_AGENT_CALLBACKS)
def test_callbacks_inject_handover_line_simplenamespace(cb) -> None:
    handover_msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    h_state = {"handover_complete": True, "handoff_message": handover_msg}
    empty_resp = SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="")]))
    out = cb.after_model_callback(SimpleNamespace(state=h_state), empty_resp)
    assert out is empty_resp
    assert empty_resp.content.parts[0].text == handover_msg


@pytest.mark.parametrize("cb", ALL_AGENT_CALLBACKS)
def test_callbacks_inject_handover_line_mock_part(cb, monkeypatch) -> None:
    monkeypatch.setattr(cb, "Part", MockPart, raising=False)
    handover_msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    h_state = {"handover_complete": True, "handoff_message": handover_msg}
    tool_only = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session", args={}))]
        )
    )
    out = cb.after_model_callback(SimpleNamespace(state=h_state), tool_only)
    assert out is tool_only
    assert tool_only.content.parts[0].text == handover_msg


@pytest.mark.parametrize("cb", ALL_AGENT_CALLBACKS)
def test_callbacks_coemitted_handover_and_end_session(cb) -> None:
    parts = [
        SimpleNamespace(
            text=None,
            function_call=SimpleNamespace(
                name="handover_to_person",
                args={"reason": "business_solutions", "language": "es-US"},
            ),
        ),
        SimpleNamespace(
            text=None,
            function_call=SimpleNamespace(
                name="end_session",
                args={"reason": "session_escalated"},
            ),
        ),
    ]
    resp = SimpleNamespace(content=SimpleNamespace(parts=parts))
    out = cb.after_model_callback(SimpleNamespace(state={}), resp)
    assert out is resp
    assert "cuenta comercial" in resp.content.parts[0].text

