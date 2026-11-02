from types import SimpleNamespace

import pytest
import cxas_app.tools.setup_autopay.python_function.python_code as tool
from lib.services import setup_autopay_impl


def test_setup_autopay_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="card", last4="4242", billing_day=15)
    assert reply["status"] == "ok"
    assert reply["data"]["autopay_enrolled"] is True
    assert reply["data"]["payment_method"] == "card"
    assert reply["data"]["billing_day"] == 15
    assert session.state["autopay_enrolled"] is True


def test_setup_autopay_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "auth_status": "pass"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.setup_autopay(payment_method="card", last4="4242")
    assert reply["status"] == "ok"
    assert reply["data"]["autopay_enrolled"] is True


def test_setup_autopay_context_none_with_inline_auth(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.setup_autopay(
        identifier="202 555 0143",
        verification_code="123456",
        last4="4242",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["autopay_enrolled"] is True


def test_setup_autopay_cancel(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "autopay_enrolled": True}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(action="cancel")
    assert reply["status"] == "ok"
    assert reply["data"]["autopay_enrolled"] is False
    assert reply["data"]["cancelled"] is True
    assert session.state["autopay_enrolled"] is False


def test_setup_autopay_bank_account(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="bank", last4="6789")
    assert reply["status"] == "ok"
    assert reply["data"]["payment_method"] == "bank"
    assert session.state["bank_last4"] == "6789"


def test_setup_autopay_declined_card(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="card", last4="0000")
    assert reply["status"] == "error"
    assert reply["error"] == "PAYMENT_DECLINED"


def test_setup_autopay_not_authenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay()
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_setup_autopay_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay()
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_setup_autopay_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.setup_autopay(language="fr-CA")
    assert reply_fr["status"] == "ok"
    reply_es = tool.setup_autopay(language="es-US")
    assert reply_es["status"] == "ok"


def test_setup_autopay_payment_methods_on_file(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "7742", "bank_last4": "6789"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="card_on_file")
    assert reply["status"] == "ok"
    assert "payment_methods_on_file" in reply["data"]
    methods = reply["data"]["payment_methods_on_file"]
    assert any(m.get("type") == "card" and m.get("last4") == "7742" for m in methods)
    assert any(m.get("type") == "card" and m.get("last4") == "8844" for m in methods)
    assert any(m.get("type") == "bank" and m.get("last4") == "6789" for m in methods)


def test_setup_autopay_new_card_first_call_capture_required(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="new_card", card_last4="4321")
    assert reply["status"] == "error"
    assert reply["error"] == "CARD_CAPTURE_REQUIRED"
    assert reply["requested_card_last4"] == "4321"
    assert reply["data"]["requested_card_last4"] == "4321"
    assert "payment_methods_on_file" not in reply["data"]
    assert "payment_methods_on_file" not in reply
    assert "spoken_line" in reply["data"]
    assert "security" in reply["data"]["spoken_line"].lower()
    assert "agent_action" in reply["data"]
    assert "confirm the card ending 4321 the caller named; do not mention other cards" in reply["data"]["agent_action"]
    assert session.state.get("card_capture_prompted") is True
    assert session.state.get("preamble_spoken") is True
    assert session.state.get("pending_card_last4") == "4321"


def test_setup_autopay_new_card_capture_required_no_card_last4(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="new_card")
    assert reply["status"] == "error"
    assert reply["error"] == "CARD_CAPTURE_REQUIRED"
    assert reply["requested_card_last4"] == ""
    assert reply["data"]["requested_card_last4"] == ""
    assert "ask for the last four digits of the new card, then call again" in reply["data"]["agent_action"]


def test_setup_autopay_new_card_second_call_completes_enrollment(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    # First call: prompts capture
    r1 = tool.setup_autopay(payment_method="new_card", card_last4="4321")
    assert r1["error"] == "CARD_CAPTURE_REQUIRED"

    # Second call: simulated DTMF completion (agent passes card_digits="4321" or no digits)
    r2 = tool.setup_autopay(payment_method="new_card", card_digits="4321", card_last4="4321")
    assert r2["status"] == "ok"
    assert r2["data"]["autopay_enrolled"] is True
    assert r2["data"]["card_last4"] == "4321"
    assert "payment_methods_on_file" not in r2["data"]
    assert "payment_methods_on_file" not in r2
    assert session.state["card_last4"] == "4321"
    assert session.state["card_token"] == "tok_card_4321"
    assert "spoken_summary" in r2["data"]
    assert "4321" in r2["data"]["spoken_summary"]
    assert "confirm the card ending 4321 the caller named; do not mention other cards" in r2["data"]["agent_action"]


def test_setup_autopay_new_card_second_call_no_digits_named_last4(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    # First call prompts capture
    tool.setup_autopay(payment_method="new_card")
    assert session.state["card_capture_prompted"] is True

    # Second call caller names last-4 without digits
    r2 = tool.setup_autopay(payment_method="new_card", card_last4="4321")
    assert r2["status"] == "ok"
    assert r2["data"]["card_last4"] == "4321"
    assert session.state["card_last4"] == "4321"


def test_setup_autopay_preamble_spoken_once(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242", "preamble_spoken": True}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Second reply omits the preamble
    reply = tool.setup_autopay(payment_method="new_card")
    assert reply["status"] == "error"
    assert reply["error"] == "CARD_CAPTURE_REQUIRED"
    assert reply["data"]["spoken_line"] == ""


def test_setup_autopay_new_card_capture_required_french(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="new_card", card_last4="9999", language="fr-CA")
    assert reply["status"] == "error"
    assert reply["error"] == "CARD_CAPTURE_REQUIRED"
    assert reply["requested_card_last4"] == "9999"
    assert "payment_methods_on_file" not in reply["data"]
    assert "payment_methods_on_file" not in reply
    assert "sécurité" in reply["data"]["spoken_line"].lower()
    assert "confirmez la carte se terminant par 9999 nommée par le client; ne mentionnez pas d'autres cartes" in reply["data"]["agent_action"]


def test_setup_autopay_new_card_invalid_digits(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="new_card", card_digits="12345678")
    assert reply["status"] == "error"
    assert reply["error"] == "INVALID_CARD_DIGITS"


def test_setup_autopay_new_card_valid_16_digits(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    raw_digits = "4111222233335555"
    reply = tool.setup_autopay(payment_method="new_card", card_digits=raw_digits)
    assert reply["status"] == "ok"
    assert reply["data"]["autopay_enrolled"] is True
    assert reply["data"]["card_last4"] == "5555"
    assert session.state["card_last4"] == "5555"
    assert session.state["card_token"] == "tok_card_5555"
    # Invariant: never echo full raw card number
    assert raw_digits not in str(reply)
    assert raw_digits not in str(session.state)


def test_setup_autopay_new_card_valid_15_digits(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    raw_digits = "378282246310005"
    reply = tool.setup_autopay(payment_method="new_card", dtmf_digits=raw_digits)
    assert reply["status"] == "ok"
    assert reply["data"]["autopay_enrolled"] is True
    assert reply["data"]["card_last4"] == "0005"
    assert session.state["card_last4"] == "0005"
    assert raw_digits not in str(reply)


def test_setup_autopay_impl_new_card_lifecycle() -> None:
    st = {"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    # Prompt capture without last4
    r0 = setup_autopay_impl(payment_method="new_card", state=st)
    assert r0["error"] == "CARD_CAPTURE_REQUIRED"
    assert r0["requested_card_last4"] == ""
    assert "ask for the last four digits" in r0["agent_action"]

    # Prompt capture with last4
    st2 = {"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    r1 = setup_autopay_impl(payment_method="new_card", card_last4="7890", state=st2)
    assert r1["error"] == "CARD_CAPTURE_REQUIRED"
    assert r1["requested_card_last4"] == "7890"
    assert "confirm the card ending 7890 the caller named; do not mention other cards" in r1["agent_action"]
    assert "payment_methods_on_file" not in r1
    assert "payment_methods_on_file" not in r1.get("data", {})
    assert st2["card_capture_prompted"] is True

    # Invalid digits
    st_inv = {"account_id": "A1001", "auth_status": "pass", "card_last4": "4242"}
    r_inv = setup_autopay_impl(payment_method="new_card", card_digits="123", state=st_inv)
    assert r_inv["error"] == "INVALID_CARD_DIGITS"

    # Second call completes enrollment
    r2 = setup_autopay_impl(
        payment_method="new_card", card_digits="7890", card_last4="7890", state=st2
    )
    assert r2["status"] == "ok"
    assert r2["data"]["autopay_enrolled"] is True
    assert "payment_methods_on_file" not in r2
    assert "payment_methods_on_file" not in r2.get("data", {})
    assert st2["card_last4"] == "7890"

    # Direct 16 digits
    st16 = {"account_id": "A1001", "auth_status": "pass"}
    r16 = setup_autopay_impl(
        payment_method="new_card", card_digits="4111222233334444", state=st16
    )
    assert r16["status"] == "ok"
    assert st16["card_last4"] == "4444"


@pytest.mark.parametrize("locale,expected_phrase", [
    ("en-US", "confirm the card ending 4321 the caller named; do not mention other cards"),
    ("fr-CA", "confirmez la carte se terminant par 4321 nommée par le client; ne mentionnez pas d'autres cartes"),
    ("es-US", "confirme la tarjeta que termina en 4321 que el cliente nombró; no mencione otras tarjetas"),
])
def test_setup_autopay_new_card_3_locales_omits_on_file(locale: str, expected_phrase: str) -> None:
    st = {"account_id": "A1001", "auth_status": "pass"}
    # Capture required
    rep1 = setup_autopay_impl(payment_method="new_card", card_last4="4321", language=locale, state=st)
    assert rep1["error"] == "CARD_CAPTURE_REQUIRED"
    assert rep1["requested_card_last4"] == "4321"
    assert "payment_methods_on_file" not in rep1
    assert "payment_methods_on_file" not in rep1.get("data", {})
    assert expected_phrase in rep1["agent_action"]

    # Completion
    rep2 = setup_autopay_impl(payment_method="new_card", card_digits="4321", card_last4="4321", language=locale, state=st)
    assert rep2["status"] == "ok"
    assert rep2["card_last4"] == "4321"
    assert "payment_methods_on_file" not in rep2
    assert "payment_methods_on_file" not in rep2.get("data", {})
    assert expected_phrase in rep2["agent_action"]


@pytest.mark.parametrize("locale", ["en-US", "fr-CA", "es-US"])
def test_setup_autopay_on_file_path_includes_methods_3_locales(locale: str) -> None:
    st = {"account_id": "A1001", "auth_status": "pass"}
    rep = setup_autopay_impl(payment_method="card_on_file", language=locale, state=st)
    assert rep["status"] == "ok"
    assert rep["autopay_enabled"] is True
    assert rep["data"]["autopay_enabled"] is True
    assert "payment_methods_on_file" in rep
    assert "payment_methods_on_file" in rep.get("data", {})
    assert len(rep["payment_methods_on_file"]) == 3


def test_setup_autopay_new_card_updates_state_card_last4_on_capture_prompt() -> None:
    st = {"account_id": "A1001", "auth_status": "pass", "card_last4": "7742"}
    rep = setup_autopay_impl(payment_method="new_card", card_last4="4321", state=st)
    assert rep["error"] == "CARD_CAPTURE_REQUIRED"
    assert rep["requested_card_last4"] == "4321"
    assert rep["card_last4"] == "4321"
    assert rep["data"]["requested_card_last4"] == "4321"
    assert rep["data"]["card_last4"] == "4321"
    assert st["card_last4"] == "4321"
    assert st["pending_card_last4"] == "4321"


@pytest.mark.parametrize("locale", ["en-US", "fr-CA", "es-US"])
def test_setup_autopay_new_card_completion_confirms_autopay_enabled_3_locales(locale: str) -> None:
    st = {"account_id": "A1001", "auth_status": "pass", "card_last4": "7742"}
    # Call 1: capture required
    rep1 = setup_autopay_impl(payment_method="new_card", card_last4="4321", language=locale, state=st)
    assert rep1["error"] == "CARD_CAPTURE_REQUIRED"
    assert st["card_last4"] == "4321"

    # Call 2: completion
    rep2 = setup_autopay_impl(payment_method="new_card", card_last4="4321", language=locale, state=st)
    assert rep2["status"] == "ok"
    assert rep2["autopay_enabled"] is True
    assert rep2["data"]["autopay_enabled"] is True
    assert rep2["autopay_enrolled"] is True
    assert rep2["data"]["autopay_enrolled"] is True
    assert rep2["card_last4"] == "4321"
    assert rep2["data"]["card_last4"] == "4321"
    assert rep2["confirmation_number"] != ""
    assert rep2["data"]["confirmation_number"] != ""


def test_setup_autopay_action_confirm_completes_enrollment() -> None:
    st = {"account_id": "A1001", "auth_status": "pass", "card_last4": "7742"}
    rep = setup_autopay_impl(payment_method="new_card", card_last4="4321", action="confirm", state=st)
    assert rep["status"] == "ok"
    assert rep["autopay_enabled"] is True
    assert rep["data"]["autopay_enabled"] is True
    assert rep["card_last4"] == "4321"



