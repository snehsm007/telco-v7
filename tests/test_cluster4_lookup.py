"""Unit tests for Cluster 4: Lost-Phone Account Identification & Identification-Before-Auth Ordering."""

from types import SimpleNamespace
import pytest

import cxas_app.tools.lookup_account.python_function.python_code as tool
from lib.services import lookup_account_impl


def test_lost_phone_lookup_by_valid_name_and_valid_email_resolves() -> None:
    """An unidentified caller with plausible full name and valid email resolves cleanly."""
    state: dict = {}
    reply = lookup_account_impl(
        full_name="Samantha Hayes",
        email="samantha.hayes@example.org",
        state=state,
    )
    assert reply["status"] == "ok"
    assert reply["data"]["identified"] is True
    assert reply["data"]["account_id"].startswith("ACC-")
    assert reply["data"]["first_name"] == "Samantha"
    assert reply["data"]["phone_last4"] == ""
    assert state["identified"] is True
    assert state["contact_email"] == "samantha.hayes@example.org"
    assert state["customer_type"] == "residential"
    assert state["business_flag"] is False


def test_lost_phone_lookup_by_valid_name_and_valid_postal_code_resolves() -> None:
    """An unidentified caller with plausible full name and valid postal code resolves cleanly."""
    state: dict = {}
    reply = lookup_account_impl(
        full_name="Guillaume Tremblay",
        postal_code="G1R 1A1",
        state=state,
    )
    assert reply["status"] == "ok"
    assert reply["data"]["identified"] is True
    assert reply["data"]["account_id"].startswith("ACC-")
    assert reply["data"]["first_name"] == "Guillaume"
    assert state["identified"] is True
    assert state["postal_code"] == "G1R 1A1"
    # Outage alert for G1R prefix
    assert reply["data"]["regional_alert"] != ""


def test_lost_phone_lookup_by_valid_name_and_us_zip_resolves() -> None:
    """An unidentified caller with plausible full name and US 5-digit ZIP resolves cleanly."""
    state: dict = {}
    reply = lookup_account_impl(
        full_name="Carlos Mendez",
        postal_code="90210",
        state=state,
    )
    assert reply["status"] == "ok"
    assert reply["data"]["identified"] is True
    assert reply["data"]["first_name"] == "Carlos"
    assert state["identified"] is True
    assert state["postal_code"] == "90210"


def test_lost_phone_lookup_name_alone_resolves() -> None:
    """A plausible full name without email or postal code resolves so caller can authenticate (Bug C)."""
    state: dict = {}
    reply = lookup_account_impl(
        full_name="Samantha Hayes",
        state=state,
    )
    assert reply["status"] == "ok"
    assert reply["data"]["identified"] is True
    assert reply["data"]["first_name"] == "Samantha"
    assert state.get("identified") is True


def test_lost_phone_single_word_name_with_email_returns_not_found() -> None:
    """A single-word name (not a full name) with email cannot resolve without full name."""
    state: dict = {}
    reply = lookup_account_impl(
        full_name="Samantha",
        email="samantha@example.org",
        state=state,
    )
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_FOUND"
    assert state.get("identified") is False


def test_negative_input_tokens_in_name_return_not_found() -> None:
    """Explicit negative tokens in name ('wrong', 'invalid', 'unknown', 'nonexistent') return NOT_FOUND."""
    for bad_name in ("wrong name", "incorrect user", "invalid customer", "unknown person", "nonexistent caller"):
        state: dict = {}
        reply = lookup_account_impl(
            full_name=bad_name,
            email="test@example.com",
            state=state,
        )
        assert reply["status"] == "error"
        assert reply["error"] == "NOT_FOUND"
        assert state.get("identified") is False


def test_negative_input_tokens_in_email_return_not_found() -> None:
    """Explicit negative tokens in email return NOT_FOUND."""
    for bad_email in ("wrong@example.com", "incorrect@test.com", "invalid-user@domain.com", "unknown@mail.com"):
        state: dict = {}
        reply = lookup_account_impl(
            full_name="Samantha Hayes",
            email=bad_email,
            state=state,
        )
        assert reply["status"] == "error"
        assert reply["error"] == "NOT_FOUND"
        assert state.get("identified") is False


def test_malformed_email_returns_not_found() -> None:
    """Malformed emails without proper domain structure return NOT_FOUND."""
    for bad_email in ("notanemail", "samantha@", "@domain.com", "user@domain", "user@.com"):
        state: dict = {}
        reply = lookup_account_impl(
            full_name="Samantha Hayes",
            email=bad_email,
            state=state,
        )
        assert reply["status"] == "error"
        assert reply["error"] == "NOT_FOUND"
        assert state.get("identified") is False


def test_invalid_postal_code_returns_not_found() -> None:
    """Invalid or negative postal codes return NOT_FOUND."""
    for bad_pc in ("00000", "99999", "11111", "wrong", "invalid", "123"):
        state: dict = {}
        reply = lookup_account_impl(
            full_name="Samantha Hayes",
            postal_code=bad_pc,
            state=state,
        )
        assert reply["status"] == "error"
        assert reply["error"] == "NOT_FOUND"
        assert state.get("identified") is False


def test_mismatched_second_identifier_on_already_identified_account_resets_identified() -> None:
    """Mismatched second identifiers on an already identified account return NOT_FOUND and set identified=False."""
    # First identify the account as Jordan (A1001, phone 2025550143, email jordan@example.com, postal H3Z 2Y7)
    state: dict = {}
    r1 = lookup_account_impl(identifier="2025550143", state=state)
    assert r1["status"] == "ok"
    assert state["identified"] is True
    assert state["account_id"] == "A1001"

    # Mismatched phone on subsequent lookup
    r_phone = lookup_account_impl(identifier="5145559999", state=state)
    assert r_phone["status"] == "error"
    assert r_phone["error"] == "NOT_FOUND"
    assert state["identified"] is False

    # Re-identify
    lookup_account_impl(identifier="2025550143", state=state)
    assert state["identified"] is True

    # Mismatched email on subsequent lookup
    r_email = lookup_account_impl(email="attacker@example.com", state=state)
    assert r_email["status"] == "error"
    assert r_email["error"] == "NOT_FOUND"
    assert state["identified"] is False

    # Re-identify
    lookup_account_impl(identifier="2025550143", state=state)
    state["postal_code"] = "H3Z 2Y7"
    assert state["identified"] is True

    # Mismatched postal code on subsequent lookup
    r_pc = lookup_account_impl(postal_code="M5V 2T6", state=state)
    assert r_pc["status"] == "error"
    assert r_pc["error"] == "NOT_FOUND"
    assert state["identified"] is False


def test_matching_second_identifier_on_already_identified_account_preserves_identified() -> None:
    """Matching second identifiers on an already identified account preserve identified=True."""
    state: dict = {}
    r1 = lookup_account_impl(identifier="2025550143", state=state)
    assert r1["status"] == "ok"
    assert state["identified"] is True

    # Matching phone
    r2 = lookup_account_impl(identifier="202-555-0143", state=state)
    assert r2["status"] == "ok"
    assert state["identified"] is True

    # Matching account ID
    r3 = lookup_account_impl(identifier="A1001", state=state)
    assert r3["status"] == "ok"
    assert state["identified"] is True


def test_cxas_tool_wrapper_name_and_email(monkeypatch) -> None:
    """CXAS tool wrapper invokes lookup_account_impl and resolves cleanly."""
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account(
        full_name="Dominique Leblanc",
        email="dominique.leblanc@example.qc.ca",
    )
    assert reply["status"] == "ok"
    assert session.state["identified"] is True
    assert reply["data"]["first_name"] == "Dominique"
    assert reply["data"]["account_id"].startswith("ACC-")
