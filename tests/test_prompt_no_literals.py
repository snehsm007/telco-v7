from pathlib import Path
import re

from lib.fakes import ACCOUNTS

APP_DIR = Path(__file__).resolve().parent.parent / "cxas_app"
FORBIDDEN_NAMES = (
    *(acc.get("first_name", "") for acc in ACCOUNTS if acc.get("first_name")),
    "Jordan",
    "Alex",
    "Marie",
    "Carlos",
    "Smith",
    "Rivera",
)
FORBIDDEN_IDS = (
    *(acc.get("account_id", "") for acc in ACCOUNTS if acc.get("account_id")),
    "A1001",
    "A1002",
    "ACC-1001",
    "ACC-1002",
)
_ALLOWED_PROMPT_PATTERNS = (
    re.compile(r"<[^>]+>"),
    re.compile(r"\{[^}]+\}"),
    re.compile(r"\b\d+-digit\b", re.IGNORECASE),
    re.compile(r"\b(?:\w+_)?last[ -]?4(?:\s+digits)?\b", re.IGNORECASE),
    re.compile(r"\b2FA\b", re.IGNORECASE),
    re.compile(r"\b[a-z]{2}-[A-Z]{2}(?:-[A-Za-z0-9]+)?\b"),
    re.compile(r"\b[a-z]{2}-419\b", re.IGNORECASE),
    re.compile(r"\bstep[_\s-]*\d+\b", re.IGNORECASE),
    re.compile(r"\bM\d+\b"),
    re.compile(r"\b1-800-[0-9-]+\b"),
    re.compile(r"\b24/7\b"),
    re.compile(r"\b24\b"),
    re.compile(r"\b[1234]\b"),
    re.compile(r"(?m)^\s*\d+\.\s"),
)


def _strip_allowed(text: str, prd_digits: set[str] | None = None) -> str:
    cleaned = text
    for pat in _ALLOWED_PROMPT_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    for num in prd_digits or ():
        cleaned = re.sub(rf"\b{re.escape(str(num))}\b", " ", cleaned)
    return cleaned


def test_prompts_contain_no_literals_or_defect_ids() -> None:
    prompt_files = [
        APP_DIR / "global_instruction.txt",
        *sorted((APP_DIR / "agents").rglob("instruction.txt")),
    ]
    assert len(prompt_files) >= 5
    for path in prompt_files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b\d{4,}\b", text), f"{path} contains a 4+ digit number"
        assert not re.findall(r"\b\d+\b", _strip_allowed(text)), f"{path} contains unallowed digits"
        assert not re.search(r"\b(?:DEF|VE|HE|BUG)-\d+\b", text), f"{path} contains a tracker ID"
        for name in FORBIDDEN_NAMES:
            assert not re.search(rf"\b{re.escape(name)}\b", text), f"{path} contains fake name {name}"
        for acc_id in FORBIDDEN_IDS:
            assert acc_id not in text, f"{path} contains fake account ID {acc_id}"


def test_five_agent_tree_subtask_structure_and_handover_pairing() -> None:
    agent_names = ("router", "billing", "tech_support", "sales_equipment", "account")
    global_txt = (APP_DIR / "global_instruction.txt").read_text(encoding="utf-8")
    assert "{@TOOL: handover_to_person}" in global_txt
    assert "handoff_message" in global_txt

    for name in agent_names:
        agent_txt = (APP_DIR / "agents" / name / "instruction.txt").read_text(encoding="utf-8")
        assert "{@TOOL: handover_to_person}" in agent_txt
        assert "handoff_message" in agent_txt
        subtasks = re.findall(r'<subtask name="([^"]+)">', agent_txt)
        assert len(subtasks) >= 2, f"{name} should define at least 2 subtasks"

        if name == "router":
            assert all(s.startswith("M1 ") for s in subtasks)
            assert "first_name" not in agent_txt
        else:
            assert "{@TOOL: verify_login}" in agent_txt
            assert any("M2 " in s for s in subtasks)


def test_paretoloop_cherry_picked_instruction_invariants() -> None:
    for name in ("account", "billing", "sales_equipment", "tech_support"):
        agent_txt = (APP_DIR / "agents" / name / "instruction.txt").read_text(encoding="utf-8")
        assert "never call {@TOOL: verify_login} until the caller provides their PIN" in agent_txt, (
            f"{name} missing gated verify_login PIN instruction"
        )

    account_txt = (APP_DIR / "agents" / "account" / "instruction.txt").read_text(encoding="utf-8")
    assert '<step name="Post-Cancellation Inquiries">' in account_txt
    assert "contract_cancellation_fee_disclosure" in account_txt

    tech_txt = (APP_DIR / "agents" / "tech_support" / "instruction.txt").read_text(encoding="utf-8")
    assert "The caller explicitly asks about a network outage or requests a regional outage check" in tech_txt
    assert '<step name="No Service Verbal Device Troubleshooting">' in tech_txt
    assert "provide verbal device troubleshooting steps before escalating" in tech_txt


def test_billing_autopay_instruction_invariants() -> None:
    billing_txt = (APP_DIR / "agents" / "billing" / "instruction.txt").read_text(encoding="utf-8")
    assert '<step name="Configure Autopay">' in billing_txt
    assert "- payment_method: card_on_file, bank_on_file, or new_card" in billing_txt
    assert 'use payment_method="card_on_file" or "bank_on_file" when the caller selects credit card or bank account without providing a specific 4-digit card ending' in billing_txt
    assert 'use payment_method="new_card" only when the caller specifies a 4-digit card ending not on file or explicitly asks to add a new card' in billing_txt


def test_router_lookup_by_name_instruction_invariants() -> None:
    router_txt = (APP_DIR / "agents" / "router" / "instruction.txt").read_text(encoding="utf-8")
    assert '<step name="Lookup Account Record">' in router_txt
    assert "- full_name: the caller's full name when provided" in router_txt
    assert "When the caller gives their name (or does not have their phone or account number), call {@TOOL: lookup_account} immediately with full_name" in router_txt


