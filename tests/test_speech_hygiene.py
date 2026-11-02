"""Tests for after_model_callbacks/speech_hygiene across all 5 agents."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import pytest

from cxas_app.agents.account.after_model_callbacks.speech_hygiene import python_code as account_callback
from cxas_app.agents.billing.after_model_callbacks.speech_hygiene import python_code as billing_callback
from cxas_app.agents.router.after_model_callbacks.speech_hygiene import python_code as router_callback
from cxas_app.agents.sales_equipment.after_model_callbacks.speech_hygiene import python_code as sales_callback
from cxas_app.agents.tech_support.after_model_callbacks.speech_hygiene import python_code as tech_callback

CALLBACKS = [
    router_callback,
    billing_callback,
    tech_callback,
    sales_callback,
    account_callback,
]


def make_response(*texts: str) -> SimpleNamespace:
    parts = [SimpleNamespace(text=text) for text in texts]
    parts.append(SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session", args={})))
    return SimpleNamespace(content=SimpleNamespace(parts=parts))


class FakePart:
    """Mock Part class supporting from_text."""

    def __init__(self, text: str) -> None:
        self.text = text

    @classmethod
    def from_text(cls, text: str) -> FakePart:
        return cls(text=text)


@pytest.mark.parametrize("callback", CALLBACKS)
def test_cleans_text_parts_and_keeps_tool_calls(callback) -> None:
    response = make_response("**Your number is 2025550143.**", "Anything else?")
    assert callback.after_model_callback(SimpleNamespace(state={}), response) is response
    assert response.content.parts[0].text == "Your number is 0143."
    assert response.content.parts[1].text == "Anything else?"
    assert response.content.parts[2].function_call.name == "end_session"


@pytest.mark.parametrize("callback", CALLBACKS)
def test_injects_handoff_message_when_handover_turn_has_no_spoken_text_simple_namespace(
    callback,
) -> None:
    msg = "Je vous transfère maintenant à un membre de notre équipe. Merci de votre patience."
    state = {"handover_complete": True, "handoff_message": msg}
    tool_only = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session", args={}))]
        )
    )
    res = callback.after_model_callback(SimpleNamespace(state=state), tool_only)
    assert res is tool_only
    assert tool_only.content.parts[0].text == msg


@pytest.mark.parametrize("callback", CALLBACKS)
def test_injects_handoff_message_with_part_from_text(callback, monkeypatch) -> None:
    monkeypatch.setattr(callback, "Part", FakePart, raising=False)
    msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    state = {"handover_complete": True, "handoff_message": msg}
    tool_only = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text="", function_call=None)]
        )
    )
    res = callback.after_model_callback(SimpleNamespace(state=state), tool_only)
    assert res is tool_only
    assert tool_only.content.parts[0].text == msg


@pytest.mark.parametrize("callback", CALLBACKS)
def test_keeps_the_spoken_transfer_line_after_a_handover(callback) -> None:
    msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    state = {"handover_complete": True, "handoff_message": msg}
    step_line = "I'm transferring you to a billing specialist now."
    response = make_response(step_line)
    assert callback.after_model_callback(SimpleNamespace(state=state), response) is None
    assert response.content.parts[0].text == step_line


@pytest.mark.parametrize("callback", CALLBACKS)
def test_returns_none_when_nothing_changes(callback) -> None:
    assert callback.after_model_callback(SimpleNamespace(state={}), SimpleNamespace(content=None)) is None
    assert callback.after_model_callback(SimpleNamespace(state={}), SimpleNamespace(content=SimpleNamespace(parts=None))) is None


@pytest.mark.parametrize("callback", CALLBACKS)
def test_coemitted_handover_and_end_session_preserves_business_handoff(callback) -> None:
    parts = [
        SimpleNamespace(
            text=None,
            function_call=SimpleNamespace(
                name="handover_to_person",
                args={"reason": "business_handoff", "language": "fr-CA"},
            ),
        ),
        SimpleNamespace(
            text=None,
            function_call=SimpleNamespace(
                name="end_session",
                args={"reason": "session_escalated", "session_escalated": True},
            ),
        ),
    ]
    resp = SimpleNamespace(content=SimpleNamespace(parts=parts))
    res = callback.after_model_callback(SimpleNamespace(state={}), resp)
    assert res is resp
    assert "compte affaires" in resp.content.parts[0].text


@pytest.mark.parametrize("callback", CALLBACKS)
def test_paraphrased_spoken_text_enforces_fraud_empathy_and_handoff(callback) -> None:
    parts = [
        SimpleNamespace(text="I understand this is concerning."),
        SimpleNamespace(
            text=None,
            function_call=SimpleNamespace(
                name="handover_to_person",
                args={"reason": "fraud_escalation", "language": "en-US"},
            ),
        ),
    ]
    resp = SimpleNamespace(content=SimpleNamespace(parts=parts))
    res = callback.after_model_callback(SimpleNamespace(state={}), resp)
    assert res is resp
    text = resp.content.parts[0].text
    assert "facing challenges" in text
    assert "representative who can help" in text


@pytest.mark.parametrize("callback", CALLBACKS)
def test_speech_hygiene_mappingproxy_and_adk_state_fidelity(callback) -> None:
    from types import MappingProxyType

    class MockAdkState:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = dict(data)

        def get(self, key: str, default: Any = None) -> Any:
            return self._data.get(key, default)

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

    raw_state = {
        "caller_provided_phone_last4": "0199",
        "card_last4": "4242",
        "bank_last4": "6789",
    }
    for st in (MappingProxyType(raw_state), MockAdkState(raw_state)):
        parts = [SimpleNamespace(text="Your card ending in 0000 and bank ending in 0000.")]
        resp = SimpleNamespace(content=SimpleNamespace(parts=parts))
        res = callback.after_model_callback(SimpleNamespace(state=st), resp)
        assert res is resp
        assert "4242" in resp.content.parts[0].text
        assert "6789" in resp.content.parts[0].text


@pytest.mark.parametrize("callback", CALLBACKS)
def test_multipart_handover_replacement_and_append_across_queues(callback) -> None:
    # 1. Generic 2-part split on business/specialist/fraud replaces cleanly without mid-word slicing
    for reason, queue, expected_sub in (
        ("business_handoff", "business_solutions", "business account"),
        ("refund_threshold_exceeded", "billing_specialist", "billing specialist"),
        ("fraud_escalation", "fraud_and_security_24x7", "facing challenges"),
    ):
        fc_h = SimpleNamespace(
            name="handover_to_person",
            args={"reason": reason, "target_queue": queue, "language": "en-US"},
        )
        fc_e = SimpleNamespace(
            name="end_session",
            args={"reason": "session_escalated", "session_escalated": True},
        )
        parts = [
            SimpleNamespace(text="I'll connect you to a representative who can help.", function_call=None),
            SimpleNamespace(text="Please hold.", function_call=None),
            SimpleNamespace(text=None, function_call=fc_h),
            SimpleNamespace(text=None, function_call=fc_e),
        ]
        resp = SimpleNamespace(content=SimpleNamespace(parts=parts))
        out = callback.after_model_callback(SimpleNamespace(state={"language": "en-US"}), resp)
        assert out is resp
        spoken = " ".join(p.text.strip() for p in resp.content.parts if getattr(p, "text", None) and p.text.strip())
        assert expected_sub in spoken
        assert " nsfer you" not in spoken
        assert len([p for p in resp.content.parts if getattr(p, "function_call", None) is not None]) == 2
        if queue == "fraud_and_security_24x7":
            assert spoken.index("facing challenges") < spoken.index("Please hold")

    # 2. 2-part paraphrased handover where enforced_combined starts with combined_text
    parts_append = [
        SimpleNamespace(text="One moment.", function_call=None),
        SimpleNamespace(text="Hold on.", function_call=None),
        SimpleNamespace(
            text=None,
            function_call=SimpleNamespace(
                name="handover_to_person",
                args={"reason": "business_handoff", "language": "fr-CA"},
            ),
        ),
    ]
    resp_append = SimpleNamespace(content=SimpleNamespace(parts=parts_append))
    assert callback.after_model_callback(SimpleNamespace(state={"language": "fr-CA"}), resp_append) is resp_append
    spoken_fr = " ".join(p.text.strip() for p in resp_append.content.parts if getattr(p, "text", None) and p.text.strip())
    assert spoken_fr.startswith("One moment. Hold on.")
    assert "compte affaires" in spoken_fr

    # 3. Extra part carrying a co-located function_call clears text without popping function_call
    fc_inline = SimpleNamespace(
        name="handover_to_person",
        args={"reason": "business_handoff", "language": "es-US"},
    )
    parts_inline_fc = [
        SimpleNamespace(text="Le comunicaré con un representante que pueda ayudarle.", function_call=None),
        SimpleNamespace(text="Por favor espere.", function_call=fc_inline),
    ]
    resp_inline = SimpleNamespace(content=SimpleNamespace(parts=parts_inline_fc))
    assert callback.after_model_callback(SimpleNamespace(state={"language": "es-US"}), resp_inline) is resp_inline
    assert "cuenta comercial" in resp_inline.content.parts[0].text
    assert resp_inline.content.parts[1].text == ""
    assert resp_inline.content.parts[1].function_call is fc_inline

