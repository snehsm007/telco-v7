"""Tests for lib/fakes.py covering test data stores, account lookups, and login ladders."""

from __future__ import annotations

from lib.fakes import (
    ACCOUNTS,
    ALWAYS_WRONG_LOGIN_CODES,
    BLOCKED_CALLER_NUMBERS,
    DECLINED_CARD_LAST4,
    FAKE_ADDON_CATALOG,
    FAKE_APPOINTMENTS_DATA,
    FAKE_BILLING_LEDGER,
    FAKE_PLAN_CATALOG,
    FAKE_TROUBLESHOOTING_GUIDES,
    FAKE_WARRANTY_DATA,
    OUTAGE_POSTAL_PREFIXES,
    SPOKEN_LINES,
    VALID_LOGIN_CODES,
    find_account,
    fixture_state_scope,
    is_placeholder_code,
    is_synthetic_wrong_identifier,
    login_code_accepted,
    normalize_code,
    only_digits,
    read_count,
    resolve_locale,
    secret_pin_accepted,
    spoken_line,
)


def test_only_digits_and_normalize_code() -> None:
    assert only_digits("(202) 555-0143") == "2025550143"
    assert only_digits("") == ""
    assert normalize_code(1234.0) == "1234"
    assert normalize_code(12.34) == "1234"
    assert normalize_code("12-34") == "1234"
    assert normalize_code("1234.000") == "1234"
    assert normalize_code("+5678.0") == "5678"
    assert normalize_code(123456) == "123456"
    assert normalize_code(None) == ""
    assert normalize_code(True) == ""
    assert normalize_code(False) == ""


def test_read_count_and_locales() -> None:
    assert read_count({"a": 2.0}, "a") == 2
    assert read_count({"a": "5"}, "a") == 5
    assert read_count({"a": "not_a_number"}, "a") == 0
    assert read_count(None, "a") == 0
    assert resolve_locale("fr") == "fr-CA"
    assert resolve_locale("es-MX") == "es-US"
    assert resolve_locale("en-GB") == "en-US"
    assert resolve_locale("") == "en-US"
    assert "0143" in spoken_line("code_sent", "en-US", destination_last4="0143")
    assert set(SPOKEN_LINES["handover"]) == {"en-US", "fr-CA", "es-US"}


def test_known_account_by_phone_or_account_number() -> None:
    by_phone = find_account("202-555-0143")
    assert by_phone is not None and by_phone["account_id"] == "A1001"
    assert by_phone["caller_provided_phone_last4"] == "0143"
    by_id = find_account("a1001")
    assert by_id is not None and by_id["account_id"] == "A1001"
    assert by_id["caller_provided_phone_last4"] == ""
    assert find_account("ACC-1001") == by_id

    # Secondary account
    acc2 = find_account("202-555-0198")
    assert acc2 is not None and acc2["account_id"] == "ACC-1002"
    assert acc2["first_name"] == "Taylor"


def test_other_nine_or_ten_digit_numbers_get_a_made_up_record() -> None:
    record = find_account("303 555 0188")
    assert record is not None
    assert record["phone"] == "3035550188" and record["first_name"] == ""
    nine_digit = find_account("303555019")
    assert nine_digit is not None and nine_digit["phone"] == "303555019"


def test_custom_account_identifier_pattern() -> None:
    custom = find_account("TEL-1234567")
    assert custom is not None
    assert custom["account_id"] == "TEL-1234567"
    assert custom["identifier_kind"] == "account_id"


def test_synthetic_wrong_identifiers() -> None:
    assert find_account("wrong_number") is None
    assert find_account("incorrect_id") is None
    assert find_account("invalid_account") is None
    assert find_account("1234567890") is None
    assert find_account("5550000000") is None
    assert find_account("2020000123") is None
    assert find_account("2025550000") is None
    assert find_account("+33 6 00 00 00 00") is None
    assert find_account("+33 6 12 34 wrong") is None


def test_seven_digit_local_phone_number_lookup() -> None:
    rec = find_account("555-0199")
    assert rec is not None
    assert rec["identifier_kind"] == "phone"
    assert rec["phone"] == "5550199"
    assert rec["phone_last4"] == "0199"
    assert rec["caller_provided_phone_last4"] == "0199"
    assert rec["linked_mobile_last4"] == "0199"
    assert rec["account_id"] == "ACC-0199"


def test_synthetic_account_and_billing_relookup() -> None:
    # Synthetic ACC-XXXX re-lookup on Turn 2+
    acc = find_account("ACC-0199")
    assert acc is not None
    assert acc["account_id"] == "ACC-0199"
    assert acc["identifier_kind"] == "account_id"
    assert acc["phone_last4"] == ""
    assert acc["caller_provided_phone_last4"] == ""
    assert acc["linked_mobile_last4"] == ""

    # Synthetic BA-XXXXXX re-lookup on Turn 2+
    ba = find_account("BA-555019")
    assert ba is not None
    assert ba["account_id"] == "BA-555019"
    assert ba["identifier_kind"] == "account_id"
    assert ba["phone_last4"] == ""
    assert ba["caller_provided_phone_last4"] == ""
    assert ba["linked_mobile_last4"] == ""

    # Billing account numbers (8/9/12 digits) keep phone_last4 empty
    ban9 = find_account("928374651")
    assert ban9 is not None
    assert ban9["identifier_kind"] == "billing_account"
    assert ban9["phone_last4"] == ""
    assert ban9["caller_provided_phone_last4"] == ""
    assert ban9["linked_mobile_last4"] == ""

    ban12 = find_account("882944105572")
    assert ban12 is not None
    assert ban12["identifier_kind"] == "billing_account"
    assert ban12["phone_last4"] == ""
    assert ban12["caller_provided_phone_last4"] == ""
    assert ban12["linked_mobile_last4"] == ""


def test_placeholder_code_and_zero_hardcoded_wrong_pin() -> None:
    # Placeholder codes: None, bool, empty, <4 digits, or all zeros
    assert is_placeholder_code(None) is True
    assert is_placeholder_code(True) is True
    assert is_placeholder_code("") is True
    assert is_placeholder_code("   ") is True
    assert is_placeholder_code("12") is True
    assert is_placeholder_code("123") is True
    assert is_placeholder_code("0000") is False
    assert is_placeholder_code("000000") is False
    # Non-zero repeated digits are valid codes, not placeholders
    assert is_placeholder_code("1111") is False
    assert is_placeholder_code("2222") is False
    assert is_placeholder_code("9999") is False

    # When no fx_pin_on_file override is set, 1111 and 9999 succeed on attempt 0
    assert login_code_accepted("1111", attempts=0) is True
    assert login_code_accepted("9999", attempts=0) is True
    assert secret_pin_accepted("1111", attempts=0) is True
    assert secret_pin_accepted("9999", attempts=0) is True

    # When fx_pin_on_file is set, non-matching PINs fail
    state = {"fx_pin_on_file": "8374"}
    assert login_code_accepted("1111", attempts=0, state=state) is False
    assert login_code_accepted("9999", attempts=0, state=state) is False
    assert login_code_accepted("8374", attempts=0, state=state) is True
    assert secret_pin_accepted("1111", attempts=0, state=state) is False
    assert secret_pin_accepted("8374", attempts=0, state=state) is True


def test_international_phone_numbers_resolve() -> None:
    acc_fr = find_account("+33 6 12 34 56 78")
    assert acc_fr is not None
    assert acc_fr["account_id"] == "ACC-5678"
    assert acc_fr["phone"] == "33612345678"
    assert acc_fr["linked_mobile_last4"] == "5678"
    assert acc_fr["phone_last4"] == "5678"
    assert acc_fr["caller_provided_phone_last4"] == "5678"
    assert acc_fr["identifier_kind"] == "phone"

    acc_00 = find_account("0033612345678")
    assert acc_00 is not None
    assert acc_00["account_id"] == "ACC-5678"
    assert acc_00["linked_mobile_last4"] == "5678"

    acc_uk = find_account("+44 7700 900123")
    assert acc_uk is not None
    assert acc_uk["account_id"] == "ACC-0123"
    assert acc_uk["linked_mobile_last4"] == "0123"

    acc_nanp = find_account("202-555-0143")
    assert acc_nanp is not None and acc_nanp["account_id"] == "A1001"
    assert is_synthetic_wrong_identifier("wrong", "1234567") is True
    assert is_synthetic_wrong_identifier("1234", "1234") is True  # short digits


def test_short_or_alpha_numbers_are_not_found() -> None:
    assert find_account("12345") is None
    assert find_account("ACC-12") is None
    assert find_account("ABC123456789") is None
    assert find_account("") is None
    assert find_account(None) is None


def test_login_ladder_for_codes_and_secret_pins() -> None:
    # Any valid code on attempt 0
    assert login_code_accepted("123456", attempts=0)
    assert login_code_accepted("314159", attempts=0)  # first try: any 4-10 digit code

    # Lenient retry allows attempt 1
    assert login_code_accepted("314159", attempts=1) is True
    assert login_code_accepted("123456", attempts=1) is True

    # Lockout on attempt 2 (max_attempts = 3)
    assert login_code_accepted("314159", attempts=2) is False
    assert login_code_accepted("123456", attempts=2) is False

    # Higher max_attempts allows attempt 2
    assert login_code_accepted("123456", attempts=2, max_attempts=5) is True

    # Secret PIN uses same ladder
    assert secret_pin_accepted("1234", attempts=0) is True
    assert secret_pin_accepted("1234", attempts=1) is True
    assert secret_pin_accepted("1234", attempts=2) is False

    # Length constraints (< 4 or > 10 digits)
    assert not login_code_accepted("12")
    assert not login_code_accepted("123456789012")

    # Always wrong codes
    assert all(not login_code_accepted(code) for code in ALWAYS_WRONG_LOGIN_CODES)


def test_fake_catalogs_and_data_stores() -> None:
    assert len(ACCOUNTS) >= 2
    assert len(BLOCKED_CALLER_NUMBERS) >= 2
    assert "H3Z" in OUTAGE_POSTAL_PREFIXES
    assert "0000" in DECLINED_CARD_LAST4
    assert len(FAKE_PLAN_CATALOG["internet"]) >= 2
    assert len(FAKE_PLAN_CATALOG["mobility"]) >= 2
    assert len(FAKE_ADDON_CATALOG) >= 1
    assert "active_appointment" in FAKE_APPOINTMENTS_DATA
    assert "device_model" in FAKE_WARRANTY_DATA
    assert "internet" in FAKE_TROUBLESHOOTING_GUIDES
    assert FAKE_BILLING_LEDGER["account_id"] == "A1001"


def test_read_count_duck_typed_adk_state_and_edge_cases() -> None:
    class FakeAdkState:
        def __init__(self, initial: dict[str, object]) -> None:
            self._data = dict(initial)

        def get(self, key: str, default: object = None) -> object:
            return self._data.get(key, default)

    adk_state = FakeAdkState({"attempts": 2, "float_str": "3.0", "flag": True, "inf": float("inf")})
    assert not isinstance(adk_state, dict)
    assert read_count(adk_state, "attempts") == 2  # type: ignore[arg-type]
    assert read_count(adk_state, "float_str") == 3  # type: ignore[arg-type]
    assert read_count(adk_state, "flag") == 0  # type: ignore[arg-type]
    assert read_count(adk_state, "inf") == 0  # type: ignore[arg-type]
    assert read_count(adk_state, "missing") == 0  # type: ignore[arg-type]
    assert read_count(object(), "attempts") == 0  # type: ignore[arg-type]


def test_fake_on_file_primary_card_is_non_canonical_7742() -> None:
    from lib.fakes import FAKE_BILLING_LEDGER, find_account

    acc1 = find_account("2025550143")
    assert acc1 is not None
    assert acc1["card_on_file_last4"] == "7742"
    assert acc1["secondary_card_last4"] == "8844"
    assert acc1["bank_on_file_last4"] == "6789"

    acc_synth = find_account("5145550199")
    assert acc_synth is not None
    assert acc_synth["card_on_file_last4"] == "7742"

    assert FAKE_BILLING_LEDGER["default_card_last4"] == "7742"
    assert FAKE_BILLING_LEDGER["secondary_card_last4"] == "8844"
    assert FAKE_BILLING_LEDGER["bank_account_last4"] == "6789"


def test_find_account_synthesized_email_mirrors_caller_or_last4() -> None:
    rec_default = find_account("555-012-8844")
    assert rec_default is not None
    assert rec_default["email"] == "user8844@example.com"
    assert rec_default["first_name"] == ""

    rec_david = find_account("555-012-8844", first_name="David")
    assert rec_david is not None
    assert rec_david["email"] == "david@example.com"
    assert rec_david["first_name"] == "David"

    rec_ban = find_account("928374651")
    assert rec_ban is not None
    assert rec_ban["email"] == "user4651@example.com"

    rec_ban_sam = find_account("928374651", first_name="Sam")
    assert rec_ban_sam is not None
    assert rec_ban_sam["email"] == "sam@example.com"

    rec_alpha = find_account("TEL-1234567", first_name="Riley")
    assert rec_alpha is not None
    assert rec_alpha["email"] == "riley@example.com"
    assert rec_alpha["first_name"] == "Riley"
