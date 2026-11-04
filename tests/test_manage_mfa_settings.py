from types import SimpleNamespace

import cxas_app.tools.manage_mfa_settings.python_function.python_code as tool


def test_manage_mfa_settings_unauthenticated(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa_settings(action="enable")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_manage_mfa_settings_placeholder_code_returns_code_not_received(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none", "auth_failure_count": 0})
    monkeypatch.setattr(tool, "context", session, raising=False)
    r_short = tool.manage_mfa_settings(verification_code="12")
    assert r_short["status"] == "error"
    assert r_short["error"] == "CODE_NOT_RECEIVED"
    assert session.state["auth_failure_count"] == 0

    r_three = tool.manage_mfa_settings(verification_code="123")
    assert r_three["status"] == "error"
    assert r_three["error"] == "CODE_NOT_RECEIVED"
    assert "say" in r_three["agent_action"].lower()
    assert session.state["auth_failure_count"] == 0

    r_stepup = tool.manage_mfa_settings(step_up_code="12")
    assert r_stepup["status"] == "error"
    assert r_stepup["error"] == "CODE_NOT_RECEIVED"
    assert session.state["auth_failure_count"] == 0


def test_manage_mfa_settings_wrong_code_and_lockout(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none", "auth_failure_count": 0, "fx_pin_on_file": "4321"})
    monkeypatch.setattr(tool, "context", session, raising=False)

    r1 = tool.manage_mfa_settings(verification_code="9999")
    assert r1["status"] == "error"
    assert r1["error"] == "WRONG_CODE"
    assert r1["data"]["attempts_remaining"] == 2

    r2 = tool.manage_mfa_settings(verification_code="9999")
    assert r2["status"] == "error"
    assert r2["error"] == "WRONG_CODE"

    r3 = tool.manage_mfa_settings(verification_code="9999")
    assert r3["status"] == "error"
    assert r3["error"] == "TOO_MANY_ATTEMPTS"
    assert session.state["auth_status"] == "locked"


def test_manage_mfa_settings_case1_enable_mfa(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "pass", "mfa_enabled": False})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa_settings(action="enable", preferred_mfa_channel="sms")
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_updated"] is True
    assert reply["data"]["mfa_enabled"] is True
    assert reply["data"]["preferred_mfa_channel"] == "sms"
    assert session.state["mfa_enabled"] is True


def test_manage_mfa_settings_case2_disable_mfa_session_auth_satisfies_stepup(monkeypatch) -> None:
    # A login completed in this session satisfies step-up when lost_device is false
    session = SimpleNamespace(state={"auth_status": "pass", "mfa_enabled": True, "login_channel": "pin"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa_settings(action="disable")
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_updated"] is True
    assert reply["data"]["mfa_enabled"] is False
    assert session.state["mfa_enabled"] is False


def test_manage_mfa_settings_case2_disable_mfa_sms_session_satisfies_stepup(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"auth_status": "pass", "mfa_enabled": True, "login_channel": "sms"}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa_settings(action="disable")
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_updated"] is True
    assert reply["data"]["mfa_enabled"] is False
    assert session.state["mfa_enabled"] is False


def test_manage_mfa_settings_case3_lost_authenticator_email_stepup(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "contact_email": "alex.doe@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa_settings(lost_authenticator=True)
    assert reply["status"] == "ok"
    assert reply["data"]["requires_email_step_up"] is True
    assert reply["data"]["mfa_updated"] is False
    assert "a***@example.com" == reply["data"]["masked_backup_email"]
    assert session.state.get("mfa_email_code_sent") is True


def test_manage_mfa_settings_case4_lost_authenticator_email_code_verified(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "lost_authenticator": True,
            "mfa_email_code_sent": True,
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa_settings(step_up_code="123456", lost_authenticator=True)
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_updated"] is True
    assert reply["data"]["mfa_enabled"] is False
    assert session.state["mfa_enabled"] is False


def test_manage_mfa_settings_dict_context(monkeypatch) -> None:
    ctx = {"auth_status": "pass", "login_code_sent": True}
    monkeypatch.setattr(tool, "context", ctx, raising=False)
    reply = tool.manage_mfa_settings(action="disable", step_up_code="123456")
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_updated"] is True


def test_manage_mfa_settings_none_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.manage_mfa_settings(action="enable")
    assert reply["status"] == "error"
    assert reply["error"] == "NOT_AUTHENTICATED"


def test_manage_mfa_settings_localization_fr_and_es(monkeypatch) -> None:
    session_fr = SimpleNamespace(state={"auth_status": "pass", "mfa_enabled": True})
    monkeypatch.setattr(tool, "context", session_fr, raising=False)
    reply_fr = tool.manage_mfa_settings(action="disable", step_up_code="123456", language="fr-CA")
    assert reply_fr["status"] == "ok"
    assert reply_fr["data"]["mfa_updated"] is True
    assert "désactivée" in reply_fr["data"]["spoken_message"]

    session_es = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "lost_authenticator": True,
            "mfa_email_verified": True,
        }
    )
    monkeypatch.setattr(tool, "context", session_es, raising=False)
    reply_es = tool.manage_mfa_settings(lost_authenticator=True, language="es-US")
    assert reply_es["status"] == "ok"
    assert "desactivado" in reply_es["data"]["spoken_message"]


def test_manage_mfa_settings_pin_login_after_email_send_still_requires_email_stepup(
    monkeypatch,
) -> None:
    import cxas_app.tools.send_login_code.python_function.python_code as send_tool
    import cxas_app.tools.verify_login.python_function.python_code as verify_tool

    session = SimpleNamespace(state={"account_id": "A1001", "mfa_enabled": True})
    monkeypatch.setattr(send_tool, "context", session, raising=False)
    monkeypatch.setattr(verify_tool, "context", session, raising=False)
    monkeypatch.setattr(tool, "context", session, raising=False)

    send_tool.send_login_code(channel="email")
    verify_tool.verify_login(code="1234", method="pin")

    step1 = tool.manage_mfa_settings(action="disable", lost_authenticator=True)
    assert step1["status"] == "ok"
    assert step1["data"]["requires_email_step_up"] is True
    assert step1["data"]["mfa_updated"] is False

    step2 = tool.manage_mfa_settings(
        action="disable", lost_authenticator=True, step_up_code="384920"
    )
    assert step2["status"] == "ok"
    assert step2["data"]["mfa_updated"] is True
    assert step2["data"]["mfa_enabled"] is False


def test_manage_mfa_settings_contact_mirrors_caller_backup_email(monkeypatch) -> None:
    session_marcus = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "first_name": "Marcus",
            "contact_email": "marcus@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session_marcus, raising=False)
    reply_marcus = tool.manage_mfa_settings(lost_authenticator=True)
    assert reply_marcus["status"] == "ok"
    assert reply_marcus["data"]["masked_backup_email"] == "m***@example.com"
    assert "starting with 'm'" in reply_marcus["data"]["spoken_message"]
    assert "starting with m" in reply_marcus["data"]["agent_action"]

    session_riley = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "first_name": "Riley",
            "contact_email": "riley.t.design@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session_riley, raising=False)
    reply_riley = tool.manage_mfa_settings(lost_authenticator=True)
    assert reply_riley["status"] == "ok"
    assert reply_riley["data"]["masked_backup_email"] == "r***@example.com"


def test_manage_mfa_settings_spoken_phrases_locales(monkeypatch) -> None:
    # Named emails include starting initial across en-US / fr-CA / es-US
    for locale, expected_spoken, expected_action in (
        ("en-US", "starting with 'c'", "starting with c"),
        ("fr-CA", "commençant par « c »", "commençant par c"),
        ("es-US", "comienza con 'c'", "comenzando con c"),
    ):
        session_named = SimpleNamespace(
            state={
                "auth_status": "pass",
                "mfa_enabled": True,
                "contact_email": "claire@example.com",
            }
        )
        monkeypatch.setattr(tool, "context", session_named, raising=False)
        res_named = tool.manage_mfa_settings(lost_authenticator=True, language=locale)
        assert res_named["data"]["masked_backup_email"] == "c***@example.com"
        assert expected_spoken in res_named["data"]["spoken_message"]
        assert expected_action in res_named["data"]["agent_action"]
        res_named_resend = tool.manage_mfa_settings(lost_authenticator=True, language=locale)
        assert res_named_resend["data"]["code_resent"] is True
        assert res_named_resend["data"]["masked_backup_email"] == "c***@example.com"

    # Synthetic placeholder emails omit fake initial 'u' while allowing domain confirmation
    session_en = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "contact_email": "user0198@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session_en, raising=False)
    res_en = tool.manage_mfa_settings(lost_authenticator=True, language="en-US")
    assert res_en["data"]["masked_backup_email"] == "***@example.com"
    assert res_en["data"]["email_domain"] == "example.com"
    assert "to the email address on file" in res_en["data"]["spoken_message"]
    assert "starting with" not in res_en["data"]["spoken_message"]
    assert "@example.com" in res_en["data"]["agent_action"]
    res_en_resend = tool.manage_mfa_settings(lost_authenticator=True, language="en-US")
    assert res_en_resend["data"]["code_resent"] is True
    assert res_en_resend["data"]["masked_backup_email"] == "***@example.com"
    assert res_en_resend["data"]["email_domain"] == "example.com"
    assert "starting with" not in res_en_resend["data"]["spoken_message"]

    session_fr = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "contact_email": "user0198@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session_fr, raising=False)
    res_fr = tool.manage_mfa_settings(lost_authenticator=True, language="fr-CA")
    assert res_fr["data"]["masked_backup_email"] == "***@example.com"
    assert res_fr["data"]["email_domain"] == "example.com"
    assert "à l'adresse courriel au dossier" in res_fr["data"]["spoken_message"]
    assert "commençant par" not in res_fr["data"]["spoken_message"]
    assert "@example.com" in res_fr["data"]["agent_action"]

    session_es = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "contact_email": "user0198@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session_es, raising=False)
    res_es = tool.manage_mfa_settings(lost_authenticator=True, language="es-US")
    assert res_es["data"]["masked_backup_email"] == "***@example.com"
    assert res_es["data"]["email_domain"] == "example.com"
    assert "al correo electrónico registrado" in res_es["data"]["spoken_message"]
    assert "comienza con" not in res_es["data"]["spoken_message"]
    assert "@example.com" in res_es["data"]["agent_action"]

    # Caller-provided email in identifier updates contact_email without overwriting existing account_id
    session_mfa_email = SimpleNamespace(
        state={
            "account_id": "ACC-0987",
            "auth_status": "pass",
            "mfa_enabled": True,
            "contact_email": "user0987@example.com",
        }
    )
    monkeypatch.setattr(tool, "context", session_mfa_email, raising=False)
    res_mfa_email = tool.manage_mfa_settings(
        lost_authenticator=True,
        identifier="jl.dubois@example.fr",
        language="fr-CA",
    )
    assert session_mfa_email.state["account_id"] == "ACC-0987"
    assert session_mfa_email.state["contact_email"] == "jl.dubois@example.fr"
    assert res_mfa_email["data"]["masked_backup_email"] == "j***@example.fr"
    assert res_mfa_email["data"]["email_domain"] == "example.fr"


def test_manage_mfa_settings_backup_email_mirrors_account_caller_david() -> None:
    from lib.services import lookup_account_impl, manage_mfa_settings_impl, verify_login_impl

    # Caller David Miller calls with on-file phone 2025550143
    state: dict = {}
    r_lookup1 = lookup_account_impl(
        identifier="2025550143",
        full_name="David Miller",
        state=state,
    )
    assert r_lookup1["status"] == "ok"

    # Authenticate with PIN
    r_verify = verify_login_impl(code="1234", method="pin", state=state)
    assert r_verify["status"] == "ok"

    # Second lookup (as happened in VE-13 r2) with account_id
    r_lookup2 = lookup_account_impl(identifier="A1001", state=state)
    assert r_lookup2["status"] == "ok"

    # Manage MFA settings with lost authenticator
    r_mfa = manage_mfa_settings_impl(lost_authenticator=True, state=state)
    assert r_mfa["status"] == "ok"
    assert r_mfa["data"]["masked_backup_email"] == "d***@example.com"
    assert "starting with 'd'" in r_mfa["data"]["spoken_message"]
    assert "starting with d" in r_mfa["data"]["agent_action"]


def test_manage_mfa_settings_backup_email_derives_from_active_account() -> None:
    from lib.services import manage_mfa_settings_impl

    # State with active account ACC-1002 but no contact_email initially set
    state_taylor: dict = {"account_id": "ACC-1002", "auth_status": "pass"}
    r_mfa = manage_mfa_settings_impl(lost_authenticator=True, state=state_taylor)
    assert r_mfa["status"] == "ok"
    assert r_mfa["data"]["masked_backup_email"] == "t***@example.com"
    assert "starting with 't'" in r_mfa["data"]["spoken_message"]
    assert state_taylor["contact_email"] == "taylor@example.com"

    # Caller passes first_name in kwargs when requesting MFA disable
    state_david: dict = {"account_id": "A1001", "auth_status": "pass"}
    r_mfa_david = manage_mfa_settings_impl(lost_authenticator=True, state=state_david, first_name="David")
    assert r_mfa_david["status"] == "ok"
    assert r_mfa_david["data"]["masked_backup_email"] == "d***@example.com"
    assert "starting with 'd'" in r_mfa_david["data"]["spoken_message"]
    assert state_david["contact_email"] == "david@example.com"


def test_manage_mfa_settings_enable_authenticator_app_en_fr_es() -> None:
    from lib.services import manage_mfa_settings_impl

    # en-US
    state_en = {"auth_status": "pass", "account_id": "A1001"}
    r_en = manage_mfa_settings_impl(action="enable", preferred_mfa_channel="authenticator", language="en-US", state=state_en)
    assert r_en["status"] == "ok"
    assert r_en["data"]["setup_complete"] is True
    assert r_en["data"]["preferred_mfa_channel"] == "authenticator_app"
    assert "authenticator app" in r_en["data"]["spoken_message"]
    assert "portal" in r_en["data"]["agent_action"]
    assert state_en["preferred_mfa_channel"] == "authenticator_app"

    # fr-CA
    state_fr = {"auth_status": "pass", "account_id": "A1001"}
    r_fr = manage_mfa_settings_impl(action="enable", channel="app", language="fr-CA", state=state_fr)
    assert r_fr["status"] == "ok"
    assert r_fr["data"]["setup_complete"] is True
    assert r_fr["data"]["preferred_mfa_channel"] == "authenticator_app"
    assert "application d'authentification" in r_fr["data"]["spoken_message"]
    assert state_fr["preferred_mfa_channel"] == "authenticator_app"

    # es-US
    state_es = {"auth_status": "pass", "account_id": "A1001"}
    r_es = manage_mfa_settings_impl(action="enable", method="totp", language="es-US", state=state_es)
    assert r_es["status"] == "ok"
    assert r_es["data"]["setup_complete"] is True
    assert r_es["data"]["preferred_mfa_channel"] == "authenticator_app"
    assert "aplicación de autenticación" in r_es["data"]["spoken_message"]
    assert state_es["preferred_mfa_channel"] == "authenticator_app"


def test_manage_mfa_settings_enable_email_and_sms_channels() -> None:
    from lib.services import manage_mfa_settings_impl

    # email
    state_email = {"auth_status": "pass", "account_id": "A1001"}
    r_email = manage_mfa_settings_impl(action="enable", channel="courriel", language="fr-CA", state=state_email)
    assert r_email["status"] == "ok"
    assert r_email["data"]["setup_complete"] is True
    assert r_email["data"]["preferred_mfa_channel"] == "email"
    assert "courriel au dossier" in r_email["data"]["spoken_message"]
    assert state_email["preferred_mfa_channel"] == "email"

    # sms default
    state_sms = {"auth_status": "pass", "account_id": "A1001"}
    r_sms = manage_mfa_settings_impl(action="enable", language="en-US", state=state_sms)
    assert r_sms["status"] == "ok"
    assert r_sms["data"]["setup_complete"] is True
    assert r_sms["data"]["preferred_mfa_channel"] == "sms"
    assert "text message" in r_sms["data"]["spoken_message"]
    assert state_sms["preferred_mfa_channel"] == "sms"


def test_manage_mfa_settings_backup_email_resend_confirmation(monkeypatch) -> None:
    session = SimpleNamespace(
        state={
            "auth_status": "pass",
            "mfa_enabled": True,
            "contact_email": "arthur.sterling@example.com",
            "account_id": "ACC100",
        }
    )
    monkeypatch.setattr(tool, "context", session, raising=False)

    # Initial lost-authenticator step-up request
    first_call = tool.manage_mfa_settings(lost_authenticator=True, language="en-US")
    assert first_call["status"] == "ok"
    assert first_call["data"]["requires_email_step_up"] is True
    assert "code_resent" not in first_call["data"]
    assert "just sent a 6-digit verification code" in first_call["data"]["spoken_message"]
    assert session.state["mfa_email_code_sent"] is True

    # Resend request (second call when code already sent but not verified)
    resend_call = tool.manage_mfa_settings(lost_authenticator=True, language="en-US")
    assert resend_call["status"] == "ok"
    assert resend_call["data"]["requires_email_step_up"] is True
    assert resend_call["data"]["code_resent"] is True
    assert resend_call.get("code_resent") is True
    assert "I have resent the 6-digit verification code" in resend_call["data"]["spoken_message"]
    assert "Confirm that the 6-digit verification code was resent" in resend_call["data"]["agent_action"]
    assert "starting with 'a'" in resend_call["data"]["spoken_message"]


def test_manage_mfa_settings_backup_email_resend_locales() -> None:
    from lib.services import manage_mfa_settings_impl

    # en-US
    state_en = {
        "auth_status": "pass",
        "mfa_enabled": True,
        "contact_email": "beatrice@example.com",
        "account_id": "ACC101",
        "mfa_email_code_sent": True,
    }
    r_en = manage_mfa_settings_impl(lost_authenticator=True, language="en-US", state=state_en)
    assert r_en["status"] == "ok"
    assert r_en["data"]["code_resent"] is True
    assert "I have resent the 6-digit verification code to the email address on file starting with 'b'" in r_en["data"]["spoken_message"]
    assert "Confirm that the 6-digit verification code was resent" in r_en["data"]["agent_action"]

    # fr-CA
    state_fr = {
        "auth_status": "pass",
        "mfa_enabled": True,
        "contact_email": "claire@example.com",
        "account_id": "ACC102",
        "mfa_email_code_sent": True,
    }
    r_fr = manage_mfa_settings_impl(lost_authenticator=True, language="fr-CA", state=state_fr)
    assert r_fr["status"] == "ok"
    assert r_fr["data"]["code_resent"] is True
    assert "J'ai renvoyé le code de vérification à 6 chiffres à l'adresse courriel au dossier commençant par « c »" in r_fr["data"]["spoken_message"]
    assert "Confirmez que le code de vérification à 6 chiffres a été renvoyé" in r_fr["data"]["agent_action"]

    # es-US
    state_es = {
        "auth_status": "pass",
        "mfa_enabled": True,
        "contact_email": "diego@example.com",
        "account_id": "ACC103",
        "mfa_email_code_sent": True,
    }
    r_es = manage_mfa_settings_impl(lost_authenticator=True, language="es-US", state=state_es)
    assert r_es["status"] == "ok"
    assert r_es["data"]["code_resent"] is True
    assert "He reenviado el código de verificación de 6 dígitos al correo electrónico registrado que comienza con 'd'" in r_es["data"]["spoken_message"]
    assert "Confirme que el código de verificación de 6 dígitos se reenvió" in r_es["data"]["agent_action"]


def test_manage_mfa_settings_enable_backup_codes_confirmation() -> None:
    from lib.services import manage_mfa_settings_impl

    # SMS enable
    state_sms = {"auth_status": "pass", "account_id": "A1001"}
    r_sms = manage_mfa_settings_impl(action="enable", preferred_mfa_channel="sms", language="en-US", state=state_sms)
    assert r_sms["status"] == "ok"
    assert r_sms["data"]["backup_codes_generated"] is True
    assert r_sms["data"]["backup_recovery_active"] is True
    assert r_sms["data"]["task_completed"] is True
    assert "backup verification codes" in r_sms["data"]["spoken_message"]
    assert "backup recovery codes" in r_sms["data"]["agent_action"]

    # Authenticator app enable in French
    state_fr = {"auth_status": "pass", "account_id": "A1001"}
    r_fr = manage_mfa_settings_impl(action="enable", preferred_mfa_channel="authenticator", language="fr-CA", state=state_fr)
    assert r_fr["status"] == "ok"
    assert r_fr["data"]["backup_codes_generated"] is True
    assert "codes de secours" in r_fr["data"]["spoken_message"]

    # Email enable in Spanish
    state_es = {"auth_status": "pass", "account_id": "A1001"}
    r_es = manage_mfa_settings_impl(action="enable", preferred_mfa_channel="email", language="es-US", state=state_es)
    assert r_es["status"] == "ok"
    assert r_es["data"]["backup_codes_generated"] is True
    assert "códigos de verificación de respaldo" in r_es["data"]["spoken_message"]

