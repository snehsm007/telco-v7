from types import SimpleNamespace

import cxas_app.tools.verify_login.python_function.python_code as tool
from lib.fakes import (
    _ACTIVE_FIXTURE_STATE,
    ALWAYS_WRONG_LOGIN_CODES,
    fixture_state_scope,
    is_placeholder_code,
    login_code_accepted,
    secret_pin_accepted,
)

tool._ACTIVE_FIXTURE_STATE = _ACTIVE_FIXTURE_STATE
tool.fixture_state_scope = fixture_state_scope
tool.ALWAYS_WRONG_LOGIN_CODES = ALWAYS_WRONG_LOGIN_CODES
tool.is_placeholder_code = is_placeholder_code
tool._is_placeholder_code = is_placeholder_code
tool.login_code_accepted = login_code_accepted
tool.secret_pin_accepted = secret_pin_accepted


def test_verify_login_happy_path(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0143", "auth_status": "code_sent", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True
    assert reply["data"]["logged_in"] is True
    assert reply["data"]["auth_status"] == "pass"
    assert session.state["auth_status"] == "pass"


def test_verify_login_context_as_dict(monkeypatch) -> None:
    state_dict = {"account_id": "A1001", "auth_status": "code_sent"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True


def test_verify_login_context_none_with_identifier(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.verify_login(code="123456", identifier="202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True


def test_verify_login_already_verified(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "pass", "logged_in": True}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True


def test_verify_login_wrong_code(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0, "fx_otp_on_file": "123456"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="999999")
    assert reply["status"] == "error"
    assert reply["error"] == "WRONG_CODE"


def test_verify_login_placeholder_codes_return_code_not_received_without_strike(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    for placeholder in ("", "   ", "0000", "000000", "12", "123"):
        reply = tool.verify_login(code=placeholder)
        assert reply["status"] == "error"
        assert reply["error"] == "CODE_NOT_RECEIVED"
        assert "say" in reply["agent_action"].lower()
        assert session.state["auth_failure_count"] == 0.0


def test_verify_login_invalid_input(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Codes longer than 10 digits are invalid input
    reply = tool.verify_login(code="1234567890123")
    assert reply["status"] == "error"
    assert reply["error"] == "INVALID_INPUT"


def test_verify_login_too_many_attempts(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_failure_count": 3.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "error"
    assert reply["error"] == "TOO_MANY_ATTEMPTS"


def test_verify_login_mock_system_down(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "error"
    assert reply["error"] == "SERVICE_UNAVAILABLE"


def test_verify_login_localization(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.verify_login(code="123456", language="fr-CA")
    assert reply_fr["status"] == "ok"
    session.state["auth_status"] = "code_sent"
    reply_es = tool.verify_login(code="123456", language="es-US")
    assert reply_es["status"] == "ok"


def test_verify_login_populates_card_and_bank_last4(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "ok"
    assert session.state["card_last4"] == "7742"
    assert session.state["bank_last4"] == "6789"
    # card_last4 and bank_last4 must be omitted from reply payload to avoid premature payment method offer
    assert "card_last4" not in reply.get("data", {})
    assert "bank_last4" not in reply.get("data", {})
    assert "card_last4" not in reply
    assert "bank_last4" not in reply


def test_verify_login_does_not_overwrite_caller_entered_card_last4(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "card_last4": "1111", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "ok"
    assert session.state["card_last4"] == "1111"
    assert session.state["bank_last4"] == "6789"
    assert "card_last4" not in reply.get("data", {})
    assert "bank_last4" not in reply.get("data", {})
    assert "card_last4" not in reply
    assert "bank_last4" not in reply



def test_verify_login_adk_state_three_strike_lockout_and_no_bypass(monkeypatch) -> None:
    class FakeAdkState:
        def __init__(self, initial: dict[str, object]) -> None:
            self._d = dict(initial)

        def get(self, k: str, default: object = None) -> object:
            return self._d.get(k, default)

        def setdefault(self, k: str, default: object = None) -> object:
            return self._d.setdefault(k, default)

        def __getitem__(self, k: str) -> object:
            return self._d[k]

        def __setitem__(self, k: str, v: object) -> None:
            self._d[k] = v

        def __contains__(self, k: object) -> bool:
            return k in self._d

    st = FakeAdkState({"account_id": "A1001", "auth_status": "code_sent", "fx_otp_on_file": "123456"})
    assert not isinstance(st, dict)
    monkeypatch.setattr(tool, "context", SimpleNamespace(state=st), raising=False)

    r1 = tool.verify_login(code="999999")
    assert r1["error"] == "WRONG_CODE" and r1["data"]["attempts_remaining"] == 2
    r2 = tool.verify_login(code="999999")
    assert r2["error"] == "WRONG_CODE" and r2["data"]["attempts_remaining"] == 1
    r3 = tool.verify_login(code="839201")
    assert r3["status"] == "error"
    assert r3["error"] == "TOO_MANY_ATTEMPTS"
    assert r3["data"]["logged_in"] is False
    assert st.get("auth_status") == "locked"


def test_verify_login_pin_after_email_code_sent_does_not_mark_email_verified(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "code_sent",
            "mfa_email_code_sent": True,
            "mfa_email_verified": False,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="1234", method="pin")
    assert reply["status"] == "ok"
    assert session.state["mfa_email_verified"] is False
    assert session.state["login_channel"] == "pin"


def test_verify_login_unidentified_returns_error(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="123456")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_IDENTIFIED"
    assert "agent_action" in reply
    assert "mobile number" in reply["agent_action"].lower() or "10-digit" in reply["agent_action"].lower()


def test_verify_login_scopes_current_active_plans_by_browsed_plan_category(monkeypatch) -> None:
    # Unset browsed_plan_category (Billing / Account / Tech Support): omits current_active_plans on both pass paths
    session_unset = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "language": "en-US"}
    )
    monkeypatch.setattr(tool, "context", session_unset, raising=False)
    r_unset_1 = tool.verify_login(code="1234", language="en-US")
    assert r_unset_1["status"] == "ok"
    assert "current_active_plans" not in r_unset_1["data"]

    r_unset_2 = tool.verify_login(code="1234", language="en-US")
    assert r_unset_2["status"] == "ok"
    assert "current_active_plans" not in r_unset_2["data"]

    # Set browsed_plan_category (Sales pre-auth browse -> verify_login): attaches localized current_active_plans
    session_sales = SimpleNamespace(
        state={
            "account_id": "A1001",
            "auth_status": "code_sent",
            "language": "es-US",
            "browsed_plan_category": "internet",
        }
    )
    monkeypatch.setattr(tool, "context", session_sales, raising=False)
    r_first = tool.verify_login(code="1234", language="es-US")
    assert r_first["status"] == "ok"
    assert r_first["data"]["current_active_plans"]["internet"]["name"] == "Fibra Internet 100"
    assert r_first["data"]["current_active_plans"]["mobility"]["monthly_price"] == "35.00"

    # Already-authenticated pass shortcut also includes localized current_active_plans when browsed_plan_category is set
    r_second = tool.verify_login(code="1234", language="es-US")
    assert r_second["status"] == "ok"
    assert r_second["data"]["current_active_plans"]["mobility"]["name"] == "Movilidad Inicial 10 GB"


def test_verify_login_pin_1111_succeeds_without_fx_pin_on_file(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="1111")
    assert reply["status"] == "ok"
    assert reply["data"]["auth_status"] == "pass"
    assert reply["data"]["verified"] is True
    assert session.state["auth_status"] == "pass"


def test_verify_login_pin_1111_fails_when_fx_pin_on_file_mismatches(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0, "fx_pin_on_file": "8374"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_login(code="1111")
    assert reply["status"] == "error"
    assert reply["error"] == "WRONG_CODE"
    assert session.state["auth_failure_count"] == 1.0

