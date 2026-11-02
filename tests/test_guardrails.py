import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_default_prompt_guardrail_language_aware() -> None:
    path = REPO_ROOT / "cxas_app" / "guardrails" / "Default_Prompt_Guardrail" / "Default_Prompt_Guardrail.json"
    assert path.is_file(), f"Missing {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("enabled") is True
    assert "generativeAnswer" in data.get("action", {})
    prompt = data["action"]["generativeAnswer"].get("prompt", "")
    assert len(prompt) > 0
    # Must instruct the model to respond in the caller's language
    prompt_lower = prompt.lower()
    assert any(
        term in prompt_lower
        for term in ("same language", "caller is using", "exact language", "caller's language")
    ), f"Prompt guardrail answer prompt must be language-aware: {prompt!r}"
    assert "cannot fulfill that request" not in prompt_lower


def test_default_safety_guardrail_language_aware() -> None:
    path = REPO_ROOT / "cxas_app" / "guardrails" / "Default_Safety_Guardrail" / "Default_Safety_Guardrail.json"
    assert path.is_file(), f"Missing {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("enabled") is True
    assert "generativeAnswer" in data.get("action", {})
    prompt = data["action"]["generativeAnswer"].get("prompt", "")
    assert len(prompt) > 0
    # Must instruct the model to respond in the caller's language
    prompt_lower = prompt.lower()
    assert any(
        term in prompt_lower
        for term in ("same language", "caller is using", "exact language", "caller's language")
    ), f"Safety guardrail answer prompt must be language-aware: {prompt!r}"
