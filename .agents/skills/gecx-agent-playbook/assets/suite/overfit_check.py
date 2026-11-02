#!/usr/bin/env python3
"""Offline anti-overfitting and prompt-diet checker (Gate 0).

Why this exists (from Kestrel + ParetoLoop Appendix B, and docs/DESIGN_RULES.md
rules 8 and 16):
Coding agents hill-climbing on visible evaluations frequently "cheat" by:
  1. Leaking test-only literals into prompts (``instruction.txt``,
     ``global_instruction.txt``) or code (every ``lib/*.py`` except
     ``fakes.py``, and the tool and callback wrappers in ``cxas_app/``):
     scenario IDs like ``cust-vz-0008``, customer names like
     ``Harriet Rivera``, account IDs like ``ACC-9921``, codes and PINs a test
     caller says (``the code is 482913``), or runs of 8+ words copied from an
     evaluation's user turns (LEAKED_EVAL_LITERAL).
  2. Copying the fake world into prompts: ids, phone numbers (or their last 4
     digits), names and codes from ``lib/fakes.py`` (FAKE_DATA_IN_PROMPT).
  3. Naming tests: eval IDs (``VE-07``, ``HE-12``) in prompts or code, and
     defect or decision IDs (``DEF-15``, ``DD-30``) in prompts
     (TEST_ID_IN_SOURCE).
  4. Copying the exported evaluations' expected agent lines or judge
     expectations into prompts (EVAL_EXPECTATION_IN_PROMPT, a warning).
  5. Baking specific non-zero dollar amounts (``$210.00``) or calendar dates
     (``August 15th``) into ``instruction.txt`` instead of reading dynamic tool
     output fields—causing the agent to recite training numbers on hidden tests.
  6. Writing one-sided conditional rules (``ONLY when is_past_due is true ...
     NEVER say ...``) without stating the opposite branch (``when false``).
  7. Bloating ``instruction.txt`` past a safe character ceiling or +50% growth.

Any literal or phrase that legitimately appears in ``prd.md`` is allowlisted
automatically so PRD business rules (e.g. a ``$25`` dispute cap) never trigger
false positives. ``lib/fakes.py`` is the one file whose values may match the
tests (it is only checked for test IDs); other code refers to them by name.

Usage:
  python3 suite/overfit_check.py --app cxas_app --lib lib --prd prd.md \\
      [--eval-dir evals] [--bench-dir bench/dev] [--max-chars 12000] [--json]
  python3 suite/overfit_check.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - stdlib fallback when PyYAML is absent
    yaml = None  # type: ignore[assignment]

DEFAULT_MAX_CHARS = 12000
DEFAULT_MAX_GROWTH = 0.50

GENERIC_VALUES = frozenset(
    {
        "true",
        "false",
        "none",
        "null",
        "ok",
        "error",
        "pass",
        "fail",
        "yes",
        "no",
        "high",
        "medium",
        "low",
        "active",
        "inactive",
        "suspended",
        "cancelled",
        "canceled",
        "pending",
        "completed",
        "open",
        "closed",
        "current",
        "past_due",
        "overdue",
        "authenticated",
        "unauthenticated",
        "verified",
        "unverified",
        "identified",
        "anonymous",
        "en",
        "fr",
        "es",
        "en-us",
        "fr-ca",
        "es-us",
        "english",
        "french",
        "spanish",
        "billing",
        "sales",
        "tech_support",
        "appointments",
        "account",
        "router",
    }
)

# Matches non-zero dollar amounts in prompts, e.g. "$210.00", "$35", "140.50 dollars"
PROMPT_DOLLAR_RE = re.compile(
    r"(?:\$\s*[1-9]\d*(?:\.\d{1,2})?\b|\b[1-9]\d*(?:\.\d{1,2})\s*(?:dollars|usd|cad)\b)",
    re.IGNORECASE,
)

# Matches explicit calendar dates in prompts, e.g. "August 15th", "October 24"
PROMPT_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

# Matches one-sided conditional rules that forbid phrasing without an opposite branch
ONE_SIDED_TRIGGER_RE = re.compile(
    r"\b(?:ONLY\s+when|If)\s+([^\n:.;]{3,60}?)\s+(?:is\s+true|is\s+past\s+due|==\s*True)\b"
    r"[^\n]*?\bNEVER\s+(?:say|claim|state|use)\b",
    re.IGNORECASE,
)

OPPOSITE_BRANCH_RE = re.compile(
    r"\b(?:when\s+[^\n]{1,40}\s+is\s+false|is\s+not\s+past\s+due|otherwise|if\s+false|"
    r"==\s*False|when\s+current|in\s+present\s+tense)\b",
    re.IGNORECASE,
)

# Public (VE-07) and holdout (HE-12) evaluation IDs: never in prompts or code.
TEST_ID_RE = re.compile(r"\b(?:VE|HE)-\d{1,4}\b")
# Defect, decision and review IDs (DEF-15, DEF-A01, DD-30): fine in docs and
# code comments, but a prompt that names them can make the agent say them.
TRACKER_ID_RE = re.compile(r"\b(?:DEF|DD|PD|RV)-[A-Z]?\d{1,4}\b")
# Codes, PINs and card digits a test caller says ("the code is 482913"): 4 to 8
# digits on their own, not part of a longer number, an amount or a decimal.
CALLER_DIGITS_RE = re.compile(r"(?<![\d.,$])\d{4,8}(?!\d)(?![.,]\d)")
# A run of this many words copied from an eval counts as a leak (a shorter
# phrase counts when all of it is copied).
NGRAM_WORDS = 8
# A person or product name in lib/fakes.py ("Pat", "Jordan Lee", "O'Brien"),
# as opposed to an identifier like "billing_agent" stored under "tool_name".
PROPER_NOUN_RE = re.compile(r"[A-Z][A-Za-z'’-]*(?: [A-Z][A-Za-z'’-]*){0,3}")
# Everything below these lines in a cxas_app python_code.py is copied from lib/
# by suite/bundle.py, so only the wrapper above them is scanned.
GENERATED_MARKERS = (
    "# --- BEGIN GENERATED SHARED BUNDLE",
    "# DO NOT MODIFY CODE BELOW THIS LINE",
)


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _word_list(text: str) -> list[str]:
    """Lowercase words without punctuation, so "Hi, I'd like" -> ["hi", "i'd", "like"]."""
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", (text or "").lower())


def _grams(words: list[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def find_copied_runs(
    content: str,
    phrases: set[str],
    allowed_lower: str = "",
    n: int = NGRAM_WORDS,
) -> list[tuple[str, str]]:
    """Return (phrase, copied words) for each phrase that shares a run of `n` words with `content`.

    A phrase shorter than `n` words counts only when all of it is copied. Runs
    that also appear in the allowed text (the PRD) are ignored.
    """
    content_words = _word_list(content)
    allowed_words = _word_list(allowed_lower)
    by_size: dict[int, tuple[set[tuple[str, ...]], set[tuple[str, ...]]]] = {}
    hits: list[tuple[str, str]] = []
    for phrase in sorted(phrases):
        words = _word_list(phrase)
        size = min(n, len(words))
        if size == 0:
            continue
        if size not in by_size:
            by_size[size] = (_grams(content_words, size), _grams(allowed_words, size))
        content_grams, allowed_grams = by_size[size]
        for gram in (tuple(words[i : i + size]) for i in range(len(words) - size + 1)):
            if gram in content_grams and gram not in allowed_grams:
                hits.append((phrase, " ".join(gram)))
                break
    return hits


def _run_line(content: str, run: str) -> int:
    """Line of the first place `run` (lowercase words) occurs in `content`, ignoring punctuation."""
    pattern = r"[\W_]+".join(re.escape(w) for w in run.split())
    m = re.search(pattern, content, re.IGNORECASE)
    return _line_number(content, m.start()) if m else 1


def fake_data_values(fakes_path: Path) -> set[str]:
    """Values from lib/fakes.py that no prompt may contain.

    Short string and number constants that look test-specific (ids, phone
    numbers, codes), proper nouns stored under a key with "name" in it, and the
    last 4 digits of every number with 7 or more digits, since prompts tend to
    say "the number ending in 0143".
    """
    try:
        tree = ast.parse(fakes_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and "name" in key.value.lower()
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and len(value.value.strip()) >= 3
                    and PROPER_NOUN_RE.fullmatch(value.value.strip())
                ):
                    values.add(value.value.strip())
        # Strings only: integers in fakes.py are mostly limits and counts (300, 1000).
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value.strip()
        if len(text) > 40:
            continue  # docstrings and sentences, not data
        if is_discriminative_literal(text):
            values.add(text)
        if re.fullmatch(r"[\d\s()+.-]{7,20}", text) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 7:
                values.add(digits[-4:])
    return values


def _caller_digits(text: str, out: set[str], allowed_lower: str) -> None:
    """Add the 4-8 digit numbers a test caller says (codes, PINs, card digits) to `out`."""
    for m in CALLER_DIGITS_RE.finditer(text or ""):
        digits = m.group(0)
        if len(digits) == 4 and digits[:2] in ("19", "20"):
            continue  # most likely a year
        if not allowed_lower or digits not in allowed_lower:
            out.add(digits)


def extract_expected_text(eval_dirs: list[Path]) -> set[str]:
    """Expected agent lines and judge expectations from exported CES evaluations (JSON).

    Only for evaluations someone else wrote (bench/dev): the local evals/
    repeat the prompt's own lines on purpose.
    """
    texts: set[str] = set()
    for root in eval_dirs:
        if not root or not root.is_dir():
            continue
        for jf in sorted(root.rglob("*.json")):
            if jf.name in ("index.json", "coverage.json") or "runs" in jf.parts:
                continue
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            prompt = (data.get("llmCriteria") or {}).get("prompt")
            if isinstance(prompt, str):
                texts.add(prompt)
            scen = data.get("scenario") or {}
            if isinstance(scen, dict):
                texts.update(str(r) for r in scen.get("rubrics") or [] if isinstance(r, str))
            golden = data.get("golden") or {}
            for turn in (golden.get("turns") or []) if isinstance(golden, dict) else []:
                for step in (turn or {}).get("steps") or []:
                    exp = (step or {}).get("expectation") or {}
                    if not isinstance(exp, dict):
                        continue
                    resp = exp.get("agentResponse") or exp.get("agent_response") or {}
                    for chunk in resp.get("chunks") or [] if isinstance(resp, dict) else []:
                        if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                            texts.add(chunk["text"])
    return {t for t in (_norm_space(x) for x in texts) if len(t.split()) >= 7}


def load_allowed_text(prd_path: Path | None, extra_files: list[Path] | None = None) -> str:
    """Read PRD and any explicit allowlist files into a single lowercased blob."""
    chunks: list[str] = []
    for p in [prd_path, *(extra_files or [])]:
        if p and p.is_file():
            try:
                chunks.append(p.read_text(encoding="utf-8"))
            except OSError:
                continue
    return "\n".join(chunks).lower()


def is_discriminative_literal(val: str, key_hint: str = "", allowed_lower: str = "") -> bool:
    """Return True if `val` looks like a test-specific entity/number rather than a generic enum."""
    cleaned = _norm_space(str(val or ""))
    if len(cleaned) < 4 or cleaned.lower() in GENERIC_VALUES:
        return False
    key_low = (key_hint or "").lower()
    if any(k in key_low for k in ("status", "error", "action", "language", "locale", "intent", "type")):
        return False
    # Ignore pure lowercase words or snake_case tokens without digits
    if re.fullmatch(r"[a-z]+(?:_[a-z]+)*", cleaned):
        return False
    # Ignore SCREAMING_SNAKE_CASE enums (PAST_DUE, NOT_FOUND) unless they end with
    # a 3+ digit ID (CUST_1001). Plain numbers and ids like A1001 are not enums.
    if re.fullmatch(r"[A-Z]+(?:_[A-Z0-9]+)*", cleaned) and not re.search(r"_[0-9]{3,}$", cleaned):
        return False
    # Ignore $0.00 / 0.00
    if re.fullmatch(r"\$?\s*0+(?:\.0+)?", cleaned):
        return False
    if allowed_lower and cleaned.lower() in allowed_lower:
        return False
    # 1. Non-zero currency amounts ($210.00) or 4+ digit numbers/codes (9921, 2025550143)
    if re.fullmatch(r"\$?\s*\d+\.\d{2}", cleaned) or re.fullmatch(r"\d{4,}", cleaned):
        return True
    # 2. Alphanumeric IDs with hyphens/digits (ACC-9921, cust-vz-0008, H3Z 2Y7)
    if re.search(r"[A-Za-z]", cleaned) and re.search(r"\d", cleaned) and len(cleaned) <= 32:
        return True
    # 3. Multi-word capitalized proper names / dates (e.g. "Harriet Rivera", "August 15th")
    words = cleaned.split()
    if 2 <= len(words) <= 4 and len(cleaned) <= 40:
        if all(w[0].isupper() for w in words if w and w[0].isalpha()):
            return True
    return False


def _collect_dict_literals(obj: Any, out: set[str], allowed_lower: str, key_hint: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) in ("name", "value") and isinstance(v, str):
                # Handle userFacts list of {"name": "...", "value": "..."}
                _collect_dict_literals(v, out, allowed_lower, str(obj.get("name") or key_hint))
            else:
                _collect_dict_literals(v, out, allowed_lower, str(k))
    elif isinstance(obj, list):
        for item in obj:
            _collect_dict_literals(item, out, allowed_lower, key_hint)
    elif obj is not None and not isinstance(obj, bool):
        s = str(obj).strip()
        if is_discriminative_literal(s, key_hint=key_hint, allowed_lower=allowed_lower):
            out.add(s)


def _maybe_add_phrase(text: str, out: set[str], allowed_lower: str, min_words: int = 7) -> None:
    clean = _norm_space(text).strip(" .?!\"'")
    words = clean.split()
    if len(words) >= min_words and len(clean) >= 32:
        if not allowed_lower or clean.lower() not in allowed_lower:
            out.add(clean)


def extract_eval_literals(
    eval_dirs: list[Path],
    allowed_lower: str = "",
) -> tuple[set[str], set[str]]:
    """Extract (test_literals, distinctive_user_phrases) from local YAML and exported JSON evals."""
    literals: set[str] = set()
    phrases: set[str] = set()

    for root in eval_dirs:
        if not root or not root.is_dir():
            continue
        # 1. Exported CES JSON evaluations
        for jf in sorted(root.rglob("*.json")):
            if jf.name in ("index.json", "coverage.json", "SHA256SUMS") or "runs" in jf.parts:
                continue
            if "evaluationExpectations" in jf.parts:
                continue
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            dname = str(data.get("displayName") or "").strip()
            if (
                len(dname) >= 6
                and re.search(r"[-_]\d+", dname)
                and dname.lower() not in allowed_lower
            ):
                literals.add(dname)
            scen = data.get("scenario") or {}
            if isinstance(scen, dict):
                _collect_dict_literals(
                    scen.get("variableOverrides") or scen.get("variable_overrides") or {},
                    literals,
                    allowed_lower,
                )
                _collect_dict_literals(
                    scen.get("userFacts") or scen.get("user_facts") or [],
                    literals,
                    allowed_lower,
                )
                task = str(scen.get("task") or "")
                for m in re.finditer(r'"([^"\n]{20,160})"', task):
                    _maybe_add_phrase(m.group(1), phrases, allowed_lower)
                _caller_digits(task, literals, allowed_lower)
            golden = data.get("golden") or {}
            if isinstance(golden, dict):
                for turn in golden.get("turns") or []:
                    for step in (turn or {}).get("steps") or []:
                        u_in = (step or {}).get("userInput") or (step or {}).get("user_input") or {}
                        if isinstance(u_in, dict):
                            if u_in.get("text"):
                                _maybe_add_phrase(str(u_in["text"]), phrases, allowed_lower)
                                _caller_digits(str(u_in["text"]), literals, allowed_lower)
                            _collect_dict_literals(u_in.get("variables") or {}, literals, allowed_lower)

        # 2. Local YAML evaluations
        if yaml is None:
            continue
        for yf in sorted(root.rglob("*.yaml")):
            if "tool_tests" in yf.parts or yf.name == "tool_tests.yaml":
                continue
            try:
                raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, Exception):
                continue
            items: list[dict[str, Any]] = []
            if isinstance(raw, list):
                items = [x for x in raw if isinstance(x, dict)]
            elif isinstance(raw, dict):
                for k in ("goldens", "simulations", "probes", "routing_probes", "safety_probes", "cases"):
                    if isinstance(raw.get(k), list):
                        items.extend(x for x in raw[k] if isinstance(x, dict))
            for item in items:
                cid = str(item.get("id") or "").strip()
                if len(cid) >= 6 and re.search(r"[-_]\d+", cid) and cid.lower() not in allowed_lower:
                    literals.add(cid)
                _collect_dict_literals(
                    item.get("variable_overrides") or item.get("variables") or {},
                    literals,
                    allowed_lower,
                )
                _collect_dict_literals(item.get("user_facts") or [], literals, allowed_lower)
                _caller_digits(str(item.get("task") or ""), literals, allowed_lower)
                for turn in item.get("turns") or []:
                    if isinstance(turn, dict):
                        u_txt = turn.get("user") or (
                            turn.get("text") if turn.get("role") == "user" else ""
                        )
                        if u_txt:
                            _maybe_add_phrase(str(u_txt), phrases, allowed_lower)
                            _caller_digits(str(u_txt), literals, allowed_lower)

    return literals, phrases


def _line_number(content: str, char_pos: int) -> int:
    return content.count("\n", 0, max(0, char_pos)) + 1


def scan_instruction_file(
    path: Path,
    rel_path: str,
    eval_literals: set[str],
    eval_phrases: set[str],
    allowed_lower: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    baseline_chars: int | None = None,
    max_growth: float = DEFAULT_MAX_GROWTH,
    fake_values: set[str] | None = None,
    expected_phrases: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan a single instruction.txt file for leaks, hardcoded numbers/dates, bloat, and one-sided rules."""
    findings: list[dict[str, Any]] = []
    content = path.read_text(encoding="utf-8")

    # 1. Prompt bloat check
    char_count = len(content)
    if char_count > max_chars:
        findings.append(
            {
                "code": "PROMPT_BLOAT",
                "severity": "ERROR",
                "file": rel_path,
                "line": 1,
                "message": (
                    f"Instruction length is {char_count} chars, exceeding ceiling of {max_chars} chars "
                    f"(+{char_count - max_chars} chars). Move static copy/facts into tool responses."
                ),
            }
        )
    if baseline_chars and baseline_chars > 0:
        growth = (char_count - baseline_chars) / baseline_chars
        if growth > max_growth + 1e-9:
            findings.append(
                {
                    "code": "PROMPT_BLOAT",
                    "severity": "ERROR",
                    "file": rel_path,
                    "line": 1,
                    "message": (
                        f"Instruction grew from {baseline_chars} to {char_count} chars "
                        f"(+{growth * 100:.1f}%), exceeding max growth of +{max_growth * 100:.0f}%."
                    ),
                }
            )

    # 2. Leaked evaluation literals and phrases
    for lit in sorted(eval_literals):
        pat = rf"(?<![A-Za-z0-9_.]){re.escape(lit)}(?![A-Za-z0-9_])"
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            findings.append(
                {
                    "code": "LEAKED_EVAL_LITERAL",
                    "severity": "ERROR",
                    "file": rel_path,
                    "line": _line_number(content, m.start()),
                    "message": (
                        f"Hardcoded evaluation literal '{lit}' found in prompt. "
                        f"Use dynamic session variables or tool return fields instead."
                    ),
                }
            )
    for phrase, run in find_copied_runs(content, eval_phrases, allowed_lower):
        findings.append(
            {
                "code": "LEAKED_EVAL_LITERAL",
                "severity": "ERROR",
                "file": rel_path,
                "line": _run_line(content, run),
                "message": (
                    f"Prompt copies '{run}' from the evaluation user utterance '{phrase[:60]}...'. "
                    f"Describe the kind of request instead of quoting a test."
                ),
            }
        )
    for phrase, run in find_copied_runs(content, expected_phrases or set(), allowed_lower):
        findings.append(
            {
                "code": "EVAL_EXPECTATION_IN_PROMPT",
                "severity": "WARNING",
                "file": rel_path,
                "line": _run_line(content, run),
                "message": (
                    f"Prompt copies '{run}' from an exported evaluation's expected line or "
                    f"expectation ('{phrase[:60]}...'). Keep it only if the PRD requires that wording."
                ),
            }
        )

    # 3. Fake-data values and test or defect IDs
    for value in sorted(fake_values or set()):
        # Whole-token check, so the PRD word "pattern" does not excuse the name "Pat".
        token_re = rf"(?<![A-Za-z0-9_.]){re.escape(value)}(?![A-Za-z0-9_])"
        if allowed_lower and re.search(token_re, allowed_lower, re.IGNORECASE):
            continue
        # Case-sensitive, so a fake first name like "Will" does not match "will".
        m = re.search(token_re, content)
        if m:
            findings.append(
                {
                    "code": "FAKE_DATA_IN_PROMPT",
                    "severity": "ERROR",
                    "file": rel_path,
                    "line": _line_number(content, m.start()),
                    "message": (
                        f"Value '{value}' from lib/fakes.py found in prompt. The agent may say it "
                        f"without a tool returning it; read it from a tool result instead."
                    ),
                }
            )
    for m in [*TEST_ID_RE.finditer(content), *TRACKER_ID_RE.finditer(content)]:
        if allowed_lower and m.group(0).lower() in allowed_lower:
            continue
        findings.append(
            {
                "code": "TEST_ID_IN_SOURCE",
                "severity": "ERROR",
                "file": rel_path,
                "line": _line_number(content, m.start()),
                "message": (
                    f"Prompt names '{m.group(0)}'. Describe the behaviour; never name a test "
                    f"or defect in a prompt."
                ),
            }
        )

    # 4. Hardcoded non-zero dollar amounts or calendar dates not in PRD
    for m in PROMPT_DOLLAR_RE.finditer(content):
        token = _norm_space(m.group(0))
        # Allow if the token or its numeric core appears in the PRD
        num_core = re.sub(r"[^0-9.]", "", token)
        if allowed_lower and (
            token.lower() in allowed_lower
            or f"${num_core}" in allowed_lower
            or f"${num_core.rstrip('0').rstrip('.')}" in allowed_lower
        ):
            continue
        findings.append(
            {
                "code": "HARDCODED_PROMPT_NUMBER",
                "severity": "ERROR",
                "file": rel_path,
                "line": _line_number(content, m.start()),
                "message": (
                    f"Hardcoded currency amount '{token}' in instruction (not in PRD). "
                    f"Return currency amounts from tools and reference dynamic fields."
                ),
            }
        )

    for m in PROMPT_DATE_RE.finditer(content):
        date_str = _norm_space(m.group(0))
        if allowed_lower and date_str.lower() in allowed_lower:
            continue
        findings.append(
            {
                "code": "HARDCODED_PROMPT_NUMBER",
                "severity": "ERROR",
                "file": rel_path,
                "line": _line_number(content, m.start()),
                "message": (
                    f"Hardcoded calendar date '{date_str}' in instruction (not in PRD). "
                    f"Use dynamic tool output fields instead of training-set dates."
                ),
            }
        )

    # 5. Any remaining numeric literal not in PRD and not a structural pattern
    allowed_prd_numbers = set(re.findall(r"\d+", allowed_lower))
    masked = _mask_allowed_prompt_numbers(content, allowed_lower)
    for m in re.finditer(r"\b\d+\b", masked):
        num_tok = m.group(0)
        if num_tok in allowed_prd_numbers:
            continue
        msg = (
            f"Numeric literal '{num_tok}' in instruction (not in PRD and not an allowed "
            f"structural pattern). Move business numbers to prd.md or return them from tools."
        )
        findings.append(
            {
                "code": "NUMBER_IN_PROMPT",
                "rule": "NUMBER_IN_PROMPT",
                "severity": "ERROR",
                "file": rel_path,
                "line": _line_number(content, m.start()),
                "message": msg,
                "detail": msg,
            }
        )

    # 6. One-sided conditional rule check (Appendix B GR-BILL-03 pattern)
    # Split by <step ...> blocks or paragraphs so we check local context.
    blocks = re.split(r"(?=<step\b)|\n\s*\n", content)
    offset = 0
    for block in blocks:
        pos = content.find(block, offset)
        if pos >= 0:
            offset = pos + len(block)
        for m in ONE_SIDED_TRIGGER_RE.finditer(block):
            if not OPPOSITE_BRANCH_RE.search(block):
                cond_name = _norm_space(m.group(1))
                findings.append(
                    {
                        "code": "ONE_SIDED_CONDITION",
                        "severity": "WARNING",
                        "file": rel_path,
                        "line": _line_number(content, (pos if pos >= 0 else 0) + m.start()),
                        "message": (
                            f"One-sided rule for '{cond_name}' states what to do/avoid when true, "
                            f"but omits the opposite branch (when false / not past due)."
                        ),
                    }
                )

    return findings


_STRUCTURAL_PROMPT_PATTERNS = (
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
    re.compile(r"\b(?:199\d|20[0-2]\d|203[0-5])\b"),
    re.compile(r"\$\s*0+(?:\.0+)?\b"),
)

STARTER_ALLOWED_FAKES_LITERALS = frozenset(
    {
        "0000",
        "000000",
        "1111",
        "111111",
        "9999",
        "999999",
        "1234",
        "5678",
        "123456",
        "246810",
        "384920",
        "482913",
        "654321",
        "A1001",
        "A1002",
        "AC1001",
        "ACC-1001",
        "ACC-1002",
        "2025550143",
        "2025550198",
        "6175550111",
        "0143",
        "0198",
        "0111",
        "Jordan",
        "Taylor",
        "Alex",
        "Pat",
        "jordan@example.com",
        "taylor@example.com",
        "Standard Monthly",
        "Plus Annual",
    }
)


def _blank_span(m: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def _mask_allowed_prompt_numbers(content: str, allowed_lower: str) -> str:
    masked = content
    # Blank allowed currency expressions first so "$25.00" when "$25" is in PRD does not flag "00"
    for m in PROMPT_DOLLAR_RE.finditer(content):
        token = _norm_space(m.group(0))
        num_core = re.sub(r"[^0-9.]", "", token)
        if allowed_lower and (
            token.lower() in allowed_lower
            or f"${num_core}" in allowed_lower
            or f"${num_core.rstrip('0').rstrip('.')}" in allowed_lower
        ):
            span = re.sub(r"[^\n]", " ", m.group(0))
            masked = masked[: m.start()] + span + masked[m.end() :]
    for pat in _STRUCTURAL_PROMPT_PATTERNS:
        masked = pat.sub(_blank_span, masked)
    return masked


def scan_fakes_ast(
    path: Path,
    rel_path: str,
    eval_literals: set[str],
    allowed_lower: str = "",
) -> list[dict[str, Any]]:
    """Inspect AST of lib/fakes.py for credential-set stuffing or leaked eval values."""
    findings: list[dict[str, Any]] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return findings

    eval_lit_lower = {lit.lower() for lit in eval_literals}
    eval_lit_digits = {
        re.sub(r"\D", "", lit)
        for lit in eval_literals
        if len(re.sub(r"\D", "", lit)) >= 4
    }

    for node in tree.body:
        targets: list[str] = []
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    targets.append(t.id)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets.append(node.target.id)
            value_node = node.value

        if not targets or value_node is None:
            continue

        for var_name in targets:
            is_cred_set = var_name in (
                "VALID_PINS",
                "VALID_OTPS",
                "ALWAYS_WRONG_LOGIN_CODES",
                "DECLINED_CARD_LAST4",
            ) or var_name.endswith(("_PINS", "_OTPS", "_CODES", "_LAST4"))
            is_accounts = var_name == "ACCOUNTS" or var_name.endswith("_ACCOUNTS")

            if is_cred_set:
                items: list[tuple[str, int]] = []
                for sub in ast.walk(value_node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, (str, int)):
                        items.append((str(sub.value).strip(), getattr(sub, "lineno", node.lineno)))
                if len(items) > 8:
                    msg = (
                        f"{var_name} in {rel_path} contains {len(items)} entries (> 8 max); "
                        f"do not stuff evaluation credentials into fakes.py."
                    )
                    findings.append(
                        {
                            "code": "EVAL_VALUE_IN_FAKES",
                            "rule": "EVAL_VALUE_IN_FAKES",
                            "severity": "ERROR",
                            "file": rel_path,
                            "line": node.lineno,
                            "message": msg,
                            "detail": msg,
                        }
                    )
                for val_str, lineno in items:
                    if not val_str or val_str in STARTER_ALLOWED_FAKES_LITERALS:
                        continue
                    if allowed_lower and val_str.lower() in allowed_lower:
                        continue
                    msg = (
                        f"Credential literal '{val_str}' in {var_name} ({rel_path}) is not in "
                        f"prd.md or starter defaults; do not hardcode eval-specific codes in fakes.py."
                    )
                    findings.append(
                        {
                            "code": "EVAL_VALUE_IN_FAKES",
                            "rule": "EVAL_VALUE_IN_FAKES",
                            "severity": "ERROR",
                            "file": rel_path,
                            "line": lineno,
                            "message": msg,
                            "detail": msg,
                        }
                    )

            elif is_accounts:
                for sub in ast.walk(value_node):
                    if not isinstance(sub, ast.Constant) or not isinstance(sub.value, str):
                        continue
                    s = sub.value.strip()
                    if (
                        len(s) < 3
                        or s.lower() in GENERIC_VALUES
                        or s in STARTER_ALLOWED_FAKES_LITERALS
                    ):
                        continue
                    if allowed_lower and s.lower() in allowed_lower:
                        continue
                    s_digits = re.sub(r"\D", "", s)
                    if s.lower() in eval_lit_lower or (
                        len(s_digits) >= 4 and s_digits in eval_lit_digits
                    ):
                        lineno = getattr(sub, "lineno", node.lineno)
                        msg = (
                            f"Evaluation literal '{s}' found in {var_name} ({rel_path}) "
                            f"but not in prd.md."
                        )
                        findings.append(
                            {
                                "code": "EVAL_VALUE_IN_FAKES",
                                "rule": "EVAL_VALUE_IN_FAKES",
                                "severity": "ERROR",
                                "file": rel_path,
                                "line": lineno,
                                "message": msg,
                                "detail": msg,
                            }
                        )

    return findings


def scan_code_file(
    path: Path,
    rel_path: str,
    eval_literals: set[str],
    eval_phrases: set[str],
    allowed_lower: str = "",
    content: str | None = None,
    ids_only: bool = False,
) -> list[dict[str, Any]]:
    """Scan agent code (lib/*.py, tool and callback wrappers) for eval literals and test IDs.

    `content` overrides the file text (used to scan only the hand-written part
    of a bundled python_code.py). `ids_only` checks test IDs and nothing else
    (used for lib/fakes.py, whose values are allowed to match the tests).
    """
    findings: list[dict[str, Any]] = []
    if content is None:
        content = path.read_text(encoding="utf-8")

    for m in TEST_ID_RE.finditer(content):
        findings.append(
            {
                "code": "TEST_ID_IN_SOURCE",
                "severity": "ERROR",
                "file": rel_path,
                "line": _line_number(content, m.start()),
                "message": (
                    f"{rel_path} names the test '{m.group(0)}'. Code that names a test only "
                    f"passes that test; describe the behaviour instead."
                ),
            }
        )
    if ids_only:
        return findings

    for lit in sorted(eval_literals):
        pat = rf"(?<![A-Za-z0-9_.]){re.escape(lit)}(?![A-Za-z0-9_])"
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            findings.append(
                {
                    "code": "LEAKED_EVAL_LITERAL",
                    "severity": "ERROR",
                    "file": rel_path,
                    "line": _line_number(content, m.start()),
                    "message": (
                        f"Hardcoded evaluation literal '{lit}' found in {rel_path}. "
                        f"Keep mock records in lib/fakes.py and keep the rest of lib/ general."
                    ),
                }
            )
    for phrase, run in find_copied_runs(content, eval_phrases, allowed_lower):
        findings.append(
            {
                "code": "LEAKED_EVAL_LITERAL",
                "severity": "ERROR",
                "file": rel_path,
                "line": _run_line(content, run),
                "message": (
                    f"{rel_path} copies '{run}' from the evaluation user utterance '{phrase[:60]}...'."
                ),
            }
        )
    return findings


def _hand_written_part(text: str) -> str:
    """The part of a cxas_app python_code.py above the code suite/bundle.py generates."""
    for marker in GENERATED_MARKERS:
        text = text.split(marker, 1)[0]
    return text


def check_app(
    app_dir: Path,
    lib_dir: Path | None = None,
    prd_path: Path | None = None,
    eval_dirs: list[Path] | None = None,
    baseline_app_dir: Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_growth: float = DEFAULT_MAX_GROWTH,
    expected_text_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Run all anti-overfitting and prompt-diet checks on an agent workspace.

    `eval_dirs` are all evaluations (local evals/ and exported bench/dev);
    `expected_text_dirs` are only the exported ones, whose expected agent lines
    and expectations someone else wrote.
    """
    app_dir = Path(app_dir)
    lib_path = Path(lib_dir) if lib_dir else None
    if prd_path is None:
        cand_prd = app_dir.parent / "prd.md"
        if cand_prd.is_file():
            prd_path = cand_prd
    if eval_dirs is None:
        auto_evals: list[Path] = []
        for cand_eval in (app_dir.parent / "evals", app_dir.parent / "bench" / "dev"):
            if cand_eval.is_dir():
                auto_evals.append(cand_eval)
        eval_dirs = auto_evals

    has_lib = bool(lib_path and lib_path.is_dir())
    extra_allow: list[Path] = []
    fake_values: set[str] = set()
    if has_lib:
        # Older agents keep spoken wording in lib/copy.py; it counts as allowed text.
        if (lib_path / "copy.py").is_file():
            extra_allow.append(lib_path / "copy.py")
        # lib/fakes.py may hold values that match the tests, but nothing else may
        # (other code refers to them by name), so it is not allowed text.
        if (lib_path / "fakes.py").is_file():
            fake_values = fake_data_values(lib_path / "fakes.py")

    allowed_lower = load_allowed_text(prd_path, extra_allow)
    eval_lits, eval_phrases = extract_eval_literals(eval_dirs or [], allowed_lower=allowed_lower)
    expected_phrases = extract_expected_text(expected_text_dirs or [])

    findings: list[dict[str, Any]] = []
    instruction_files: list[Path] = []
    if (app_dir / "global_instruction.txt").is_file():
        instruction_files.append(app_dir / "global_instruction.txt")
    if (app_dir / "agents").is_dir():
        instruction_files.extend(sorted((app_dir / "agents").rglob("instruction.txt")))

    for inst_path in instruction_files:
        rel = str(inst_path.relative_to(app_dir.parent if app_dir.parent.exists() else app_dir))
        base_chars: int | None = None
        if baseline_app_dir:
            try:
                sub = inst_path.relative_to(app_dir)
                cand_base = Path(baseline_app_dir) / sub
                if cand_base.is_file():
                    base_chars = len(cand_base.read_text(encoding="utf-8"))
            except ValueError:
                pass
        findings.extend(
            scan_instruction_file(
                inst_path,
                rel_path=rel,
                eval_literals=eval_lits,
                eval_phrases=eval_phrases,
                allowed_lower=allowed_lower,
                max_chars=max_chars,
                baseline_chars=base_chars,
                max_growth=max_growth,
                fake_values=fake_values,
                expected_phrases=expected_phrases,
            )
        )

    if has_lib:
        for py_path in sorted(lib_path.glob("*.py")):
            if py_path.name == "copy.py":
                continue  # wording allowlist, scanned as allowed text
            rel_py = f"{lib_path.name}/{py_path.name}"
            findings.extend(
                scan_code_file(
                    py_path,
                    rel_path=rel_py,
                    eval_literals=eval_lits,
                    eval_phrases=eval_phrases,
                    allowed_lower=allowed_lower,
                    ids_only=py_path.name == "fakes.py",
                )
            )
            if py_path.name == "fakes.py":
                findings.extend(
                    scan_fakes_ast(
                        py_path,
                        rel_path=rel_py,
                        eval_literals=eval_lits,
                        allowed_lower=allowed_lower,
                    )
                )

    # Tool and callback wrappers: only the hand-written part above the bundle.
    for py_path in sorted(app_dir.rglob("python_code.py")) if app_dir.is_dir() else []:
        try:
            wrapper = _hand_written_part(py_path.read_text(encoding="utf-8"))
        except OSError:
            continue
        findings.extend(
            scan_code_file(
                py_path,
                rel_path=str(py_path.relative_to(app_dir.parent)),
                eval_literals=eval_lits,
                eval_phrases=eval_phrases,
                allowed_lower=allowed_lower,
                content=wrapper,
            )
        )

    errors = [f for f in findings if f["severity"] == "ERROR"]
    warnings = [f for f in findings if f["severity"] == "WARNING"]
    return {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "eval_literals_checked": len(eval_lits),
        "eval_phrases_checked": len(eval_phrases),
        "fake_values_checked": len(fake_values),
        "expected_phrases_checked": len(expected_phrases),
        "findings": findings,
    }


def _run_self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prd = root / "prd.md"
        prd.write_text(
            "# Sample PRD\n"
            "Disputes under $25.00 are auto-approved. Standard fee is $0.00.\n"
            'Greeting: "Thanks for calling, I can help with billing and account questions today."\n',
            encoding="utf-8",
        )
        # A local evaluation (ours) and an exported benchmark evaluation (someone else's).
        evals_dir = root / "evals"
        evals_dir.mkdir()
        (evals_dir / "cust_vz_0008.json").write_text(
            json.dumps(
                {
                    "displayName": "cust-vz-0008",
                    "scenario": {
                        "task": (
                            'Caller says "I mailed my trade in phone back in late October of last '
                            'year" and reads the code 739204 when asked.'
                        ),
                        "variableOverrides": {
                            "customer_name": "Harriet Rivera",
                            "account_id": "ACC-9921",
                            "status": "past_due",
                        },
                        "userFacts": [
                            {"name": "card_last4", "value": "9012"},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        bench_dir = root / "bench" / "dev"
        bench_dir.mkdir(parents=True)
        expected_lines = [
            "Thanks for calling, I can help with billing and account questions today.",
            "I can see your bill, and the amount due is listed on your latest statement.",
        ]
        (bench_dir / "balance_question.json").write_text(
            json.dumps(
                {
                    "displayName": "balance_question",
                    "golden": {
                        "turns": [
                            {
                                "steps": [
                                    {"userInput": {"text": "How much do I owe?"}},
                                    {
                                        "expectation": {
                                            "agentResponse": {
                                                "chunks": [{"text": line} for line in expected_lines],
                                            },
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        app_dir = root / "cxas_app"
        agent_dir = app_dir / "agents" / "billing"
        agent_dir.mkdir(parents=True)
        wrapper_dir = app_dir / "tools" / "lookup" / "python_function"
        wrapper_dir.mkdir(parents=True)
        lib_dir = root / "lib"
        lib_dir.mkdir()
        (lib_dir / "fakes.py").write_text(
            "ACCOUNTS = [\n"
            '    {"account_id": "AC1001", "phone": "6175550111", "first_name": "Pat", "status": "ACTIVE"},\n'
            "]\n"
            "MAX_TRIES = 3000\n",
            encoding="utf-8",
        )
        fakes = fake_data_values(lib_dir / "fakes.py")
        assert fakes == {"AC1001", "6175550111", "0111", "Pat"}, f"Unexpected fake-data values: {fakes}"
        (lib_dir / "speech.py").write_text(
            'def say_digits(value):\n    return " ".join(str(value))\n',
            encoding="utf-8",
        )
        (lib_dir / "services.py").write_text(
            "def code_matches(code, expected):\n    return code == expected\n",
            encoding="utf-8",
        )
        # A bundled lib/ can repeat test values below the generated marker; only
        # the hand-written wrapper above it is checked.
        wrapper_head = (
            "def lookup(account_id: str) -> dict:\n"
            '    """Looks up the caller\'s account."""\n'
            "    return find(account_id)\n"
        )
        wrapper_tail = f'\n{GENERATED_MARKERS[0]} (edit lib/, then run `make bundle`) ---\nKNOWN_CODE = "739204"\n'
        (wrapper_dir / "python_code.py").write_text(wrapper_head + wrapper_tail, encoding="utf-8")

        def run(**kwargs: Any) -> dict[str, Any]:
            return check_app(
                app_dir=app_dir,
                lib_dir=lib_dir,
                prd_path=prd,
                eval_dirs=[evals_dir, bench_dir],
                expected_text_dirs=[bench_dir],
                **kwargs,
            )

        # 1. Clean agent: two-sided rule, PRD amount and PRD greeting quoted, dynamic fields.
        (agent_dir / "instruction.txt").write_text(
            "<step name=\"check_balance\">\n"
            "  <trigger>Caller asks about their balance or a dispute under $25.00</trigger>\n"
            "  <action>Say \"Thanks for calling, I can help with billing and account questions today.\" "
            "ONLY when is_past_due is true, state the balance WAS due on {due_date} "
            "and NEVER say 'Everything looks good'. When is_past_due is false, state in present "
            "tense that the balance IS due on {due_date}.</action>\n"
            "</step>\n",
            encoding="utf-8",
        )
        res_clean = run()
        assert res_clean["ok"], f"Expected clean app to pass, got: {res_clean}"
        assert res_clean["warning_count"] == 0, f"Expected 0 warnings, got: {res_clean}"
        assert res_clean["fake_values_checked"] and res_clean["expected_phrases_checked"], res_clean

        # 2. Overfitted and bloated agent.
        (agent_dir / "instruction.txt").write_text(
            "<step name=\"check_balance\">\n"
            "  <trigger>Caller Harriet Rivera asks about $210.00 due August 15th (VE-12, DEF-15)</trigger>\n"
            "  <action>If the caller says \"I mailed my trade in phone back in late October\", look up "
            "the return. Confirm the number ending in 0111 for Pat. Tell them the amount due is "
            "listed on your latest statement. ONLY when is_past_due is true, state $210.00 WAS due "
            "August 15th and NEVER say 'Everything looks good'.</action>\n"
            "</step>\n"
            + ("<!-- bloat -->\n" * 900),
            encoding="utf-8",
        )
        (lib_dir / "fakes.py").write_text(
            "ACCOUNTS = [\n"
            '    {"account_id": "AC1001", "phone": "6175550111", "first_name": "Pat", "status": "ACTIVE"},\n'
            '    {"account_id": "ACC-9921", "phone": "6175550199", "first_name": "Harriet Rivera", "status": "ACTIVE"},\n'
            "]\n"
            'VALID_PINS = frozenset({"739204"})\n'
            "MAX_TRIES = 3000\n",
            encoding="utf-8",
        )
        (lib_dir / "services.py").write_text(
            "def code_matches(code, expected):\n"
            '    if code == "739204":\n'
            "        return True\n"
            "    return code == expected\n",
            encoding="utf-8",
        )
        (lib_dir / "other.py").write_text("# Added for HE-04.\nRETRIES = 2\n", encoding="utf-8")
        (wrapper_dir / "python_code.py").write_text(
            "# VE-12: keep this path\n" + wrapper_head + wrapper_tail, encoding="utf-8"
        )

        res_bad = run(max_chars=5000)
        assert not res_bad["ok"], "Expected overfitted app to fail"
        prompt = "cxas_app/agents/billing/instruction.txt"
        wrapper = "cxas_app/tools/lookup/python_function/python_code.py"
        found = {(f["code"], f["file"]) for f in res_bad["findings"]}
        for expected in (
            ("LEAKED_EVAL_LITERAL", prompt),  # "Harriet Rivera" and a partly copied caller line
            ("FAKE_DATA_IN_PROMPT", prompt),  # "0111" and "Pat" from lib/fakes.py
            ("TEST_ID_IN_SOURCE", prompt),  # VE-12 and DEF-15
            ("EVAL_EXPECTATION_IN_PROMPT", prompt),
            ("HARDCODED_PROMPT_NUMBER", prompt),
            ("NUMBER_IN_PROMPT", prompt),
            ("PROMPT_BLOAT", prompt),
            ("ONE_SIDED_CONDITION", prompt),
            ("EVAL_VALUE_IN_FAKES", "lib/fakes.py"),
            ("LEAKED_EVAL_LITERAL", "lib/services.py"),  # the code the test caller reads out
            ("TEST_ID_IN_SOURCE", "lib/other.py"),
            ("TEST_ID_IN_SOURCE", wrapper),
        ):
            assert expected in found, f"Missing expected finding {expected} in {sorted(found)}"
        assert ("LEAKED_EVAL_LITERAL", wrapper) not in found, "Generated bundle code must not be scanned"
        messages = " ".join(f["message"] for f in res_bad["findings"])
        for needle in ("'0111'", "'Pat'", "'VE-12'", "'DEF-15'", "'i mailed my trade in phone back in'"):
            assert needle in messages, f"Missing {needle} in findings: {messages}"

    print("OK: suite/overfit_check.py --self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline anti-overfitting and prompt-diet checker.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in unit self-tests.")
    parser.add_argument("--app", default="cxas_app", help="Path to CXAS app directory.")
    parser.add_argument("--lib", default="lib", help="Path to shared lib/ directory.")
    parser.add_argument("--prd", default="prd.md", help="Path to PRD markdown file.")
    parser.add_argument("--eval-dir", default="evals", help="Path to local evals/ directory.")
    parser.add_argument("--bench-dir", default="bench/dev", help="Path to exported benchmark evals directory.")
    parser.add_argument("--baseline-app", default="", help="Optional baseline app directory for growth cap.")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="Max chars per instruction.txt.")
    parser.add_argument("--max-growth", type=float, default=DEFAULT_MAX_GROWTH, help="Max fractional growth vs baseline.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON report.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    eval_dirs = [Path(p) for p in (args.eval_dir, args.bench_dir) if p and Path(p).is_dir()]
    # Expected agent lines are only checked in exported evaluations: the local
    # evals/ were written from the prompt, so they repeat it on purpose.
    expected_dirs = [Path(args.bench_dir)] if args.bench_dir and Path(args.bench_dir).is_dir() else []
    result = check_app(
        app_dir=Path(args.app),
        lib_dir=Path(args.lib) if args.lib else None,
        prd_path=Path(args.prd) if args.prd else None,
        eval_dirs=eval_dirs,
        baseline_app_dir=Path(args.baseline_app) if args.baseline_app else None,
        max_chars=args.max_chars,
        max_growth=args.max_growth,
        expected_text_dirs=expected_dirs,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for f in result["findings"]:
            print(f"[{f['severity']}] {f['code']} {f['file']}:{f['line']} — {f['message']}")
        status = "OK" if result["ok"] else "FAILED"
        print(
            f"{status}: overfit_check ({result['error_count']} errors, {result['warning_count']} warnings, "
            f"{result['eval_literals_checked']} eval literals & {result['eval_phrases_checked']} phrases, "
            f"{result['fake_values_checked']} fake-data values, "
            f"{result['expected_phrases_checked']} expected lines scanned)"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
