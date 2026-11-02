import pytest

from lib.replies import ERROR_CODES, display_amount, error_reply, ok_reply, tracking_id


def test_display_amount_gives_two_decimals_for_speech() -> None:
    assert display_amount(85.5) == "85.50"
    assert display_amount(85) == "85.00"
    assert display_amount("1,234.5") == "1234.50"
    assert display_amount(2.675) == "2.68"
    assert display_amount(-12.3) == "-12.30"
    for bad in (None, "", "abc", True, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            display_amount(bad)


def test_tracking_id_is_repeatable_and_depends_on_the_inputs() -> None:
    first = tracking_id("submit_request", "A1001", "mail a statement")
    assert first == tracking_id("submit_request", "A1001", "  Mail a statement ")
    assert first != tracking_id("submit_request", "A1001", "close the account")
    assert len(first) == 7 and first.startswith("R") and first[1:].isdigit()


def test_ok_reply_shape() -> None:
    reply = ok_reply({"x": 1}, "R000001")
    assert reply == {
        "status": "ok",
        "data": {"x": 1},
        "error_message": "",
        "tracking_id": "R000001",
    }
    assert reply["status"] == "ok"
    assert reply["status"] == "OK"
    auto_ref = ok_reply({"logged_in": True})
    assert auto_ref["logged_in"] is True
    assert auto_ref["tracking_id"].startswith("R")


def test_error_reply_shape_and_unknown_codes() -> None:
    reply = error_reply("NOT_FOUND", "No match.", "Ask again.", "R000002")
    assert reply["status"] == "error" and reply["error"] == "NOT_FOUND"
    assert reply["agent_action"] == "Ask again." and reply["data"] == {}
    for code in (
        "INVALID_INPUT",
        "NOT_FOUND",
        "NOT_IDENTIFIED",
        "NOT_LOGGED_IN",
        "CODE_NOT_SENT",
        "WRONG_CODE",
        "WRONG_PIN",
        "TOO_MANY_ATTEMPTS",
        "LOCKED_OUT",
        "PAYMENT_DECLINED",
        "INELIGIBLE",
        "ALREADY_PROCESSED",
        "LIMIT_EXCEEDED",
        "SYSTEM_DOWN",
    ):
        assert code in ERROR_CODES
        defaulted = error_reply(code, data={"lockout_triggered": True})
        assert defaulted["error"] == code
        assert defaulted["lockout_triggered"] is True
    with pytest.raises(ValueError):
        error_reply("MADE_UP", "x", "y", "R000003")
