from types import SimpleNamespace

import cxas_app.tools.lookup_account.python_function.python_code as tool
from lib.services import lookup_account_impl


def test_lookup_account_happy_path_simplenamespace(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none", "auth_failure_count": 0.0})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "A1001"
    assert session.state["account_id"] == "A1001"
    assert session.state["caller_provided_phone_last4"] == "0143"


def test_lookup_account_context_as_dict(monkeypatch) -> None:
    state_dict = {"auth_status": "none"}
    monkeypatch.setattr(tool, "context", state_dict, raising=False)
    reply = tool.lookup_account("202-555-0143")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "A1001"
    assert state_dict["account_id"] == "A1001"


def test_lookup_account_context_none(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "A1001"


def test_lookup_account_invalid_empty_input(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("")
    assert reply["status"] == "error"
    assert reply["error"] == "INVALID_INPUT"


def test_lookup_account_not_found(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("9999999999")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_FOUND"


def test_lookup_account_business_inquiry(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account(
        identifier="202 555 0143",
        is_business_inquiry=True,
    )
    assert reply["status"] == "ok"
    assert reply["data"]["business_flag"] is True
    assert reply["data"]["must_escalate_immediately"] is True


def test_lookup_account_blocked_caller(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("8005550000")
    assert reply["status"] == "error"
    assert reply["error"] == "PERMISSION_DENIED"


def test_lookup_account_localization(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply_fr = tool.lookup_account("202 555 0143", language="fr-CA")
    assert reply_fr["status"] == "ok"
    reply_es = tool.lookup_account("202 555 0143", language="es-US")
    assert reply_es["status"] == "ok"


def test_lookup_account_populates_card_and_bank_last4(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert session.state["card_last4"] == "7742"
    assert session.state["bank_last4"] == "6789"



def test_lookup_account_blocked_caller_11_digit_nanp(monkeypatch) -> None:
    for raw_blocked in ("+1 (900) 555-0199", "1-800-555-0000", 19005550199):
        session = SimpleNamespace(state={})
        monkeypatch.setattr(tool, "context", session, raising=False)
        reply = tool.lookup_account(raw_blocked)
        assert reply["status"] == "error"
        assert reply["error"] == "PERMISSION_DENIED"
        assert session.state["is_blocked"] is True
        assert "account_id" not in session.state


def test_lookup_account_by_full_name_found(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account(full_name="Taylor")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "ACC-1002"
    assert reply["data"]["first_name"] == "Taylor"
    assert session.state["account_id"] == "ACC-1002"
    assert session.state["identified"] is True


def test_lookup_account_by_full_name_unknown_synthesis(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Unmatched name returns NOT_FOUND per Defect 5 remediation
    reply = tool.lookup_account(full_name="Marcus Thorne")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_FOUND"
    assert session.state.get("identified") is False


def test_lookup_account_by_name_with_caller_phone(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account(full_name="Marcus Thorne", identifier="514-555-0199")
    assert reply["status"] == "ok"
    assert reply["data"]["phone_last4"] == "0199"
    assert session.state["phone_last4"] == "0199"
    assert session.state["caller_provided_phone_last4"] == "0199"


def test_lookup_account_by_name_with_email(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Unrecognized name returns NOT_FOUND (Defect 5)
    reply = tool.lookup_account(full_name="Marcus Thorne", email="marcus@example.com")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_FOUND"

    # Known name with email succeeds
    reply_known = tool.lookup_account(full_name="Jordan", email="jordan@example.com")
    assert reply_known["status"] == "ok"
    assert reply_known["data"]["first_name"] == "Jordan"


def test_lookup_account_nine_digit_ban_has_no_invented_phone(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account(identifier="928374651")
    assert reply["status"] == "ok"
    assert reply["data"]["phone_last4"] == ""
    assert reply["data"]["linked_mobile_last4"] == ""
    assert session.state["phone_last4"] == ""
    assert session.state["current_balance"] == "85.50"
    assert session.state["past_due_balance"] == "85.50"


def test_lookup_account_by_full_name_and_postal_code(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    # Unrecognized name returns NOT_FOUND (Defect 5)
    reply = tool.lookup_account(full_name="Marcus Thorne", postal_code="H3Z 2Y7")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_FOUND"

    # Known name with postal code succeeds and surfaces regional alert
    reply_known = tool.lookup_account(full_name="Jordan", postal_code="H3Z 2Y7")
    assert reply_known["status"] == "ok"
    assert session.state["postal_code"] == "H3Z 2Y7"
    assert reply_known["data"]["regional_alert"] != ""


def test_lookup_account_digits_only_behaves_as_before(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "A1001"

    session_err = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_err, raising=False)
    reply_err = tool.lookup_account("9999999999")
    assert reply_err["status"] == "error"
    assert reply_err["error"] == "NOT_FOUND"


def test_lookup_account_impl_direct_name() -> None:
    state: dict = {}
    reply = lookup_account_impl(full_name="Taylor", state=state)
    assert reply["status"] == "ok"
    assert state["account_id"] == "ACC-1002"
    assert state["lookup_by_name"] is True

    # Known first name Jordan resolves to A1001
    state_known: dict = {}
    reply_known = lookup_account_impl(full_name="Jordan", state=state_known)
    assert reply_known["status"] == "ok"
    assert state_known["account_id"] == "A1001"
    assert state_known["lookup_by_name"] is True

    # Unrecognized name Marcus Thorne must return NOT_FOUND (Defect 5 remediation)
    state2: dict = {}
    reply2 = lookup_account_impl(full_name="Marcus Thorne", state=state2)
    assert reply2["status"] == "error"
    assert reply2["error"] == "NOT_FOUND"
    assert state2.get("identified") is False

    # Identifier as known name
    state3: dict = {}
    reply3 = lookup_account_impl(identifier="Jordan", state=state3)
    assert reply3["status"] == "ok"
    assert state3["lookup_by_name"] is True
    assert state3["account_id"] == "A1001"

    # Identifier as phone
    state4: dict = {}
    reply4 = lookup_account_impl(identifier="202-555-0143", state=state4)
    assert reply4["status"] == "ok"
    assert state4["lookup_by_name"] is False


def test_lookup_account_international_phone(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("+33 6 12 34 56 78")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "ACC-5678"
    assert reply["data"]["phone_last4"] == "5678"
    assert reply["data"]["linked_mobile_last4"] == "5678"
    assert session.state["phone_last4"] == "5678"
    assert session.state["caller_provided_phone_last4"] == "5678"

    session_uk = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_uk, raising=False)
    reply_uk = tool.lookup_account("+44 7700 900123")
    assert reply_uk["status"] == "ok"
    assert reply_uk["data"]["account_id"] == "ACC-0123"


def test_lookup_account_alphanumeric_identifiers(monkeypatch) -> None:
    # 4 to 8 digit alphanumeric identifiers (e.g. ACT-992841, CUST-88291)
    session_act = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_act, raising=False)
    reply_act = tool.lookup_account("ACT-992841")
    assert reply_act["status"] == "ok"
    assert reply_act["data"]["account_id"] == "ACT-992841"
    assert session_act.state["account_id"] == "ACT-992841"

    session_cust = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_cust, raising=False)
    reply_cust = tool.lookup_account("CUST-88291")
    assert reply_cust["status"] == "ok"
    assert reply_cust["data"]["account_id"] == "CUST-88291"
    assert session_cust.state["account_id"] == "CUST-88291"

    # Intentional wrong identifiers with synthetic suffixes remain rejected
    session_wrong = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_wrong, raising=False)
    reply_wrong = tool.lookup_account("ACT-0000")
    assert reply_wrong["status"] == "error"
    assert reply_wrong["error"] == "NOT_FOUND"

    session_short = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_short, raising=False)
    reply_short = tool.lookup_account("ACT-123")
    assert reply_short["status"] == "error"
    assert reply_short["error"] == "NOT_FOUND"


def test_lookup_account_12_digit_billing_account(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("8829-4410-5572")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "ACC-5572"
    assert session.state["account_id"] == "ACC-5572"

    # Synthetic wrong 12-digit numbers ending in 0000, 9999, 1111 remain rejected
    session_wrong = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_wrong, raising=False)
    reply_wrong = tool.lookup_account("8829-4410-0000")
    assert reply_wrong["status"] == "error"
    assert reply_wrong["error"] == "NOT_FOUND"

    session_9999 = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_9999, raising=False)
    reply_9999 = tool.lookup_account("8829-4410-9999")
    assert reply_9999["status"] == "error"
    assert reply_9999["error"] == "NOT_FOUND"



