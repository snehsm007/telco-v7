from types import SimpleNamespace

import cxas_app.tools.lookup_account.python_function.python_code as tool
from lib.fakes import find_account, is_synthetic_wrong_identifier
from lib.services import lookup_account_impl

tool.find_account = find_account
tool.is_synthetic_wrong_identifier = is_synthetic_wrong_identifier


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
    reply = tool.lookup_account("2025550000")
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
    # Negative/invalid name returns NOT_FOUND
    reply = tool.lookup_account(full_name="Marcus Thorne wrong")
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
    # Valid full name + valid email from unidentified caller resolves cleanly (Cluster 4)
    reply = tool.lookup_account(full_name="Marcus Thorne", email="marcus@example.com")
    assert reply["status"] == "ok"
    assert reply["data"]["first_name"] == "Marcus"
    assert session.state["identified"] is True
    assert session.state["contact_email"] == "marcus@example.com"

    # Known name with email succeeds
    session_known = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_known, raising=False)
    reply_known = tool.lookup_account(full_name="Jordan", email="jordan@example.com")
    assert reply_known["status"] == "ok"
    assert reply_known["data"]["first_name"] == "Jordan"

    # Negative/invalid email returns NOT_FOUND
    session_err = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_err, raising=False)
    reply_err = tool.lookup_account(full_name="Marcus Thorne", email="wrong@example.com")
    assert reply_err["status"] == "error"
    assert reply_err["error"] == "NOT_FOUND"


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
    # Valid full name + valid postal code from unidentified caller resolves cleanly (Cluster 4)
    reply = tool.lookup_account(full_name="Marcus Thorne", postal_code="H3Z 2Y7")
    assert reply["status"] == "ok"
    assert reply["data"]["first_name"] == "Marcus"
    assert session.state["identified"] is True
    assert session.state["postal_code"] == "H3Z 2Y7"

    # Known name with postal code succeeds and surfaces regional alert
    session_known = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_known, raising=False)
    reply_known = tool.lookup_account(full_name="Jordan", postal_code="H3Z 2Y7")
    assert reply_known["status"] == "ok"
    assert session_known.state["postal_code"] == "H3Z 2Y7"
    assert reply_known["data"]["regional_alert"] != ""

    # Negative/invalid postal code returns NOT_FOUND
    session_err = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_err, raising=False)
    reply_err = tool.lookup_account(full_name="Marcus Thorne", postal_code="wrong")
    assert reply_err["status"] == "error"
    assert reply_err["error"] == "NOT_FOUND"


def test_lookup_account_digits_only_behaves_as_before(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "A1001"

    session_err = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_err, raising=False)
    reply_err = tool.lookup_account("2025550000")
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

    # Negative name Marcus Thorne invalid must return NOT_FOUND
    state2: dict = {}
    reply2 = lookup_account_impl(full_name="Marcus Thorne invalid", state=state2)
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

    # Synthetic wrong 12-digit numbers ending in 0000 remain rejected
    session_wrong = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_wrong, raising=False)
    reply_wrong = tool.lookup_account("8829-4410-0000")
    assert reply_wrong["status"] == "error"
    assert reply_wrong["error"] == "NOT_FOUND"

    # 12-digit number ending in 9999 is valid since 9999 is not globally blocklisted
    session_9999 = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_9999, raising=False)
    reply_9999 = tool.lookup_account("8829-4410-9999")
    assert reply_9999["status"] == "ok"
    assert reply_9999["data"]["account_id"] == "ACC-9999"


def test_lookup_account_seven_digit_local_phone(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("555-0199")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "ACC-0199"
    assert reply["data"]["phone_last4"] == "0199"
    assert reply["data"]["caller_provided_phone_last4"] == "0199"
    assert reply["data"]["linked_mobile_last4"] == "0199"
    assert session.state["account_id"] == "ACC-0199"
    assert session.state["phone_last4"] == "0199"
    assert session.state["caller_provided_phone_last4"] == "0199"


def test_lookup_account_synthetic_relookup_turn_two(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("ACC-0199")
    assert reply["status"] == "ok"
    assert reply["data"]["account_id"] == "ACC-0199"
    assert reply["data"]["phone_last4"] == ""
    assert session.state["account_id"] == "ACC-0199"

    session_ba = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session_ba, raising=False)
    reply_ba = tool.lookup_account("BA-555019")
    assert reply_ba["status"] == "ok"
    assert reply_ba["data"]["account_id"] == "BA-555019"
    assert session_ba.state["account_id"] == "BA-555019"


def test_lookup_account_unauthorized_charge_billing_dispute_not_fraud(monkeypatch) -> None:
    # Call #76: caller explicitly asks to dispute a charge on their bill
    session = SimpleNamespace(
        state={
            "utterance": "My account number is 8849201. I see an unauthorized charge on my latest bill that I need to dispute.",
            "last_user_utterance": "My account number is 8849201. I see an unauthorized charge on my latest bill that I need to dispute.",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("8849201")
    assert reply["status"] == "ok"
    # Must NOT escalate to fraud; billing agent handles dispute
    assert reply.get("must_escalate_immediately") is not True
    assert reply["data"].get("must_escalate_immediately") is not True
    assert reply["data"]["account_id"] == "ACC-9201"


def test_lookup_account_unauthorized_service_escalates_to_fraud(monkeypatch) -> None:
    # Call #98 pattern: unauthorized service or charge without explicit dispute intent
    session = SimpleNamespace(
        state={
            "utterance": "I have been looking at my account and there are unauthorized charges on file.",
            "last_user_utterance": "I have been looking at my account and there are unauthorized charges on file.",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["must_escalate_immediately"] is True
    assert reply["data"]["escalation_reason"] == "fraud_escalation"
    assert reply["data"]["target_queue"] == "fraud_and_security_24x7"


def test_lookup_account_fraud_with_hacked_takeover_preempts_dispute(monkeypatch) -> None:
    # sim__report_fraud_standard: even if dispute is mentioned, hack/takeover forces fraud escalation
    session = SimpleNamespace(
        state={
            "utterance": "I want to dispute charges because someone hacked my account and committed identity theft",
            "last_user_utterance": "I want to dispute charges because someone hacked my account and committed identity theft",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0143")
    assert reply["status"] == "ok"
    assert reply["data"]["must_escalate_immediately"] is True
    assert reply["data"]["escalation_reason"] == "fraud_escalation"
    assert reply["data"]["target_queue"] == "fraud_and_security_24x7"


def test_lookup_account_french_billing_dispute_not_fraud(monkeypatch) -> None:
    # sim__dispute_billing_charge_french pattern
    session = SimpleNamespace(
        state={
            "utterance": "Je veux contester des frais d'appels non autorisés sur ma facture",
            "last_user_utterance": "Je veux contester des frais d'appels non autorisés sur ma facture",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("514-555-0199", language="fr-CA")
    assert reply["status"] == "ok"
    assert reply.get("must_escalate_immediately") is not True
    assert reply["data"].get("must_escalate_immediately") is not True




