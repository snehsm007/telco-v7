from lib.fakes import (
    ACCOUNTS,
    ALWAYS_WRONG_LOGIN_CODES,
    DECLINED_CARD_LAST4,
    SPOKEN_LINES,
    VALID_LOGIN_CODES,
    VALID_OTPS,
    VALID_PINS,
    find_account,
    login_code_accepted,
    normalize_code,
    read_count,
)


def test_fakes_constants_and_spoken_lines_invariants() -> None:
    for key in ("greeting", "code_sent", "handover"):
        assert set(SPOKEN_LINES[key]) == {"en-US", "fr-CA", "es-US"}
        assert all(len(line) > 40 for line in SPOKEN_LINES[key].values())
    assert {"0000", "000000"} <= ALWAYS_WRONG_LOGIN_CODES
    assert VALID_OTPS and VALID_PINS and VALID_LOGIN_CODES == (VALID_OTPS | VALID_PINS)
    assert not ALWAYS_WRONG_LOGIN_CODES & VALID_LOGIN_CODES  # DESIGN_RULES rule 23
    assert {"0000", "9999"} <= DECLINED_CARD_LAST4
    assert len(ACCOUNTS) >= 1
    for account in ACCOUNTS:  # no account's phone or id may end in an always-wrong code
        assert account["phone"][-4:] not in ALWAYS_WRONG_LOGIN_CODES
        assert normalize_code(account["account_id"])[-4:] not in ALWAYS_WRONG_LOGIN_CODES


def test_fakes_helper_invariants() -> None:
    assert normalize_code(1234.0) == "1234"
    assert normalize_code("12-34") == "1234"
    assert read_count({"x": 3.0}, "x") == 3
    assert find_account("202555019") is not None
    assert find_account("12345") is None
    assert find_account("ACC-12") is None
    assert login_code_accepted("1234", attempts=0) is True
    assert login_code_accepted("0000", attempts=0) is False
