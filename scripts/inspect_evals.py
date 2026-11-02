#!/usr/bin/env python3
"""Bootcamp Eval Reconnaissance Report scanner for platform JSONs and local YAML evals.

Scans a directory of exported CES platform evaluation JSONs (`evaluations/*.json` +
`evaluationExpectations/*.json`) or local `evals/` YAML files (`goldens/*.yaml`,
`simulations/*.yaml`, `probes/*.yaml`) and prints a structured reconnaissance report:
  1. Language breakdown (en-US, fr-CA, es-US)
  2. Fact-less simulated callers (scenarios lacking phone/OTP/PIN/card in userFacts)
  3. Expected tools, agent transfers, and verbatim/LLM expectations
  4. Potential PRD-vs-eval friction points (e.g. fact-less callers, Turn-1 handoff,
     audio 1-word openers, missing language overrides)

Usage:
  python3 scripts/inspect_evals.py <eval-dir> [--json] [--out <report.md>]
  python3 scripts/inspect_evals.py --self-test
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import yaml

FACT_KEYWORDS = {
    "phone": re.compile(r"\b(?:phone|mobile|cell|number|tel|ani)\b", re.I),
    "otp": re.compile(r"\b(?:otp|code|verification|passcode)\b", re.I),
    "pin": re.compile(r"\b(?:pin|security_pin|passphrase)\b", re.I),
    "card": re.compile(r"\b(?:card|visa|mastercard|amex|last4|credit|debit)\b", re.I),
    "account": re.compile(r"\b(?:account|acct|customer_id|ban|email)\b", re.I),
}

FR_HINT_RE = re.compile(
    r"(?:_fr\b|\bfr[-_]ca\b|\bfrench\b|\bfran[cç]ais\b|\bbonjour\b|\bfacture\b|\bforfait\b)",
    re.I,
)
ES_HINT_RE = re.compile(
    r"(?:_es\b|\bes[-_]us\b|\bspanish\b|\bespa[nñ]ol\b|\bhola\b|\bfactura\b|\bcuenta\b)",
    re.I,
)
VERBATIM_QUOTE_RE = re.compile(r'"([^"\n]{8,160})"|\'([^\'\n]{8,160})\'')


def detect_language(name: str, tags: list[str], body_text: str, explicit_lang: str = "") -> str:
    raw = (explicit_lang or "").strip().lower()
    if raw.startswith("fr"):
        return "fr-CA"
    if raw.startswith("es"):
        return "es-US"
    if raw.startswith("en"):
        return "en-US"
    blob = " ".join([name, *tags, body_text])
    if FR_HINT_RE.search(blob):
        return "fr-CA"
    if ES_HINT_RE.search(blob):
        return "es-US"
    return "en-US"


def _extract_facts_coverage(facts: list[dict[str, Any]]) -> dict[str, bool]:
    blob = " ".join(
        f"{f.get('name', '')}={f.get('value', '')}"
        for f in facts
        if isinstance(f, dict)
    )
    return {k: bool(rx.search(blob)) for k, rx in FACT_KEYWORDS.items()}


def inspect_directory(target_dir: Path) -> dict[str, Any]:
    target_dir = Path(target_dir)
    if not target_dir.exists():
        raise FileNotFoundError(f"Evaluation directory not found: {target_dir}")

    expectations_by_name: dict[str, str] = {}
    for exp_file in sorted(target_dir.rglob("*.json")):
        if "evaluationExpectations" not in exp_file.parts:
            continue
        try:
            data = json.loads(exp_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("displayName"):
            prompt = str((data.get("llmCriteria") or {}).get("prompt") or "")
            expectations_by_name[str(data["displayName"])] = prompt
            if data.get("name"):
                expectations_by_name[str(data["name"])] = prompt

    records: list[dict[str, Any]] = []

    # 1. Scan exported platform JSON evaluations
    for json_file in sorted(target_dir.rglob("*.json")):
        if "evaluationExpectations" in json_file.parts:
            continue
        if json_file.name in ("index.json", "coverage.json") or "runs" in json_file.parts:
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if not any(k in data for k in ("golden", "scenario", "displayName")):
            continue

        name = str(data.get("displayName") or data.get("name") or json_file.stem)
        tags = [str(t) for t in (data.get("tags") or [])]
        is_scenario = bool(data.get("scenario"))
        kind = "scenario" if is_scenario else "golden"
        lang = detect_language(
            name,
            tags,
            json.dumps(data.get("scenario") or data.get("golden") or {}, ensure_ascii=False),
            str(data.get("language") or ""),
        )

        tools: list[str] = []
        transfers: list[str] = []
        verbatim_phrases: list[str] = []
        expectation_prompts: list[str] = []
        fact_coverage: dict[str, bool] = {}
        first_user_utterance = ""
        turn_count = 0
        has_lang_override = False

        if is_scenario:
            scen = data.get("scenario") or {}
            task = str(scen.get("task") or "")
            user_facts = scen.get("userFacts") or scen.get("user_facts") or []
            fact_coverage = _extract_facts_coverage(user_facts)
            var_overrides = scen.get("variableOverrides") or scen.get("variable_overrides") or {}
            has_lang_override = bool(
                isinstance(var_overrides, dict)
                and any(k in var_overrides for k in ("language", "locale", "_call_lang"))
            )
            for ref in scen.get("evaluationExpectations") or []:
                prompt = expectations_by_name.get(str(ref), str(ref))
                expectation_prompts.append(prompt)
            for se in data.get("scenarioExpectations") or []:
                if isinstance(se, dict) and se.get("expectation"):
                    ref = str(se["expectation"])
                    expectation_prompts.append(expectations_by_name.get(ref, ref))
                tc = (se or {}).get("toolExpectation") or (se or {}).get("toolCall")
                if isinstance(tc, dict):
                    tname = str(tc.get("displayName") or tc.get("tool") or "").split("/")[-1]
                    if tname:
                        tools.append(tname)
            for rub in scen.get("rubrics") or []:
                expectation_prompts.append(str(rub))
            for m in VERBATIM_QUOTE_RE.finditer(" ".join([task, *expectation_prompts])):
                phrase = (m.group(1) or m.group(2) or "").strip()
                if phrase:
                    verbatim_phrases.append(phrase)
        else:
            golden = data.get("golden") or {}
            turns = golden.get("turns") or []
            turn_count = len(turns)
            for t_idx, turn in enumerate(turns):
                for step in (turn or {}).get("steps") or []:
                    u_in = (step or {}).get("userInput") or (step or {}).get("user_input") or {}
                    if isinstance(u_in, dict):
                        if t_idx == 0 and u_in.get("text") and not first_user_utterance:
                            first_user_utterance = str(u_in["text"]).strip()
                        if isinstance(u_in.get("variables"), dict) and any(
                            k in u_in["variables"] for k in ("language", "locale", "_call_lang")
                        ):
                            has_lang_override = True
                    exp = (step or {}).get("expectation") or {}
                    if isinstance(exp, dict):
                        tc = exp.get("toolCall") or exp.get("tool_call")
                        if isinstance(tc, dict):
                            tname = str(tc.get("displayName") or tc.get("tool") or "").split("/")[-1]
                            if tname:
                                tools.append(tname)
                        at = exp.get("agentTransfer") or exp.get("agent_transfer")
                        if isinstance(at, dict):
                            target = str(at.get("targetAgent") or at.get("target_agent") or "").split("/")[-1]
                            if target:
                                transfers.append(target)
                        if exp.get("expectation"):
                            ref = str(exp["expectation"])
                            expectation_prompts.append(expectations_by_name.get(ref, ref))

        records.append(
            {
                "id": name,
                "kind": kind,
                "language": lang,
                "tools": sorted(set(tools)),
                "transfers": sorted(set(transfers)),
                "expectation_prompts": expectation_prompts,
                "verbatim_phrases": sorted(set(verbatim_phrases)),
                "fact_coverage": fact_coverage,
                "first_user_utterance": first_user_utterance,
                "turn_count": turn_count,
                "has_lang_override": has_lang_override,
            }
        )

    # 2. Scan local YAML evals (goldens, simulations, probes)
    for yaml_file in sorted(target_dir.rglob("*.yaml")):
        if yaml_file.name == "tool_tests.yaml" or "tool_tests" in yaml_file.parts:
            continue
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
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
            if not cid:
                continue
            is_sim = bool(item.get("task") or item.get("user_goal") or "simulations" in yaml_file.parts)
            kind = "scenario" if is_sim else "golden"
            lang = detect_language(
                cid,
                [str(t) for t in (item.get("tags") or [])],
                json.dumps(item, ensure_ascii=False),
                str(item.get("language") or ""),
            )
            tools = [str(t) for t in (item.get("expected_tools") or item.get("must_call") or [])]
            transfers: list[str] = []
            if item.get("expected_agent"):
                transfers.append(str(item["expected_agent"]))
            verbatim_phrases = [str(p) for p in (item.get("must_contain") or [])]
            expectation_prompts = [str(r) for r in (item.get("rubrics") or item.get("evaluation_expectations") or [])]
            fact_coverage: dict[str, bool] = {}
            if is_sim:
                uf = item.get("user_facts") or []
                if isinstance(uf, dict):
                    uf = [{"name": k, "value": v} for k, v in uf.items()]
                fact_coverage = _extract_facts_coverage(uf)
            turns = item.get("turns") or []
            first_user_utterance = ""
            for t in turns:
                if isinstance(t, dict) and str(t.get("role") or "user") == "user":
                    first_user_utterance = str(t.get("text") or t.get("user") or "").strip()
                    break
                if isinstance(t, dict) and t.get("user"):
                    first_user_utterance = str(t["user"]).strip()
                    break
            for t in turns:
                if isinstance(t, dict):
                    for tc in t.get("expected_tool_calls") or t.get("tool_calls") or []:
                        if isinstance(tc, dict) and tc.get("name"):
                            tools.append(str(tc["name"]))
                        elif isinstance(tc, str):
                            tools.append(tc)
                    if t.get("expected_transfer"):
                        transfers.append(str(t["expected_transfer"]))
            var_ov = item.get("session_variables") or item.get("variable_overrides") or {}
            has_lang_override = bool(
                isinstance(var_ov, dict) and any(k in var_ov for k in ("language", "locale", "_call_lang"))
            )
            records.append(
                {
                    "id": cid,
                    "kind": kind,
                    "language": lang,
                    "tools": sorted(set(tools)),
                    "transfers": sorted(set(transfers)),
                    "expectation_prompts": expectation_prompts,
                    "verbatim_phrases": sorted(set(verbatim_phrases)),
                    "fact_coverage": fact_coverage,
                    "first_user_utterance": first_user_utterance,
                    "turn_count": len(turns),
                    "has_lang_override": has_lang_override,
                }
            )

    lang_counts = Counter(r["language"] for r in records)
    kind_counts = Counter(r["kind"] for r in records)
    tool_counts = Counter(t for r in records for t in r["tools"])
    transfer_counts = Counter(tr for r in records for tr in r["transfers"])

    factless_scenarios: list[dict[str, Any]] = []
    friction_points: list[str] = []

    for r in records:
        if r["kind"] == "scenario":
            cov = r["fact_coverage"]
            missing = [k for k in ("phone", "otp", "pin") if not cov.get(k, False)]
            if missing:
                factless_scenarios.append({"id": r["id"], "missing_facts": missing})
        if r["language"] in ("fr-CA", "es-US") and not r["has_lang_override"]:
            friction_points.append(
                f"{r['id']} ({r['language']}): non-English eval without a language session variable "
                "-> the agent must pick the language from the caller's words; write every spoken "
                "line in that language in the prompt (docs/DESIGN_RULES.md rule 5)."
            )
        if r["kind"] == "golden" and r["first_user_utterance"]:
            words = r["first_user_utterance"].split()
            if len(words) <= 1:
                friction_points.append(
                    f"{r['id']}: 1-word golden opener ({r['first_user_utterance']!r}) "
                    "-> may trigger DEF-A01 server-side empty turn in audio goldens; prefer audio simulations."
                )
        if r["kind"] == "golden" and r["turn_count"] == 1 and r["transfers"]:
            friction_points.append(
                f"{r['id']}: Turn-1 golden expects transfer to {r['transfers']} "
                "-> ensure Turn-1 routing happens before OTP gating when caller states intent immediately."
            )

    if factless_scenarios:
        friction_points.insert(
            0,
            f"{len(factless_scenarios)} scenario(s) lack explicit phone/OTP/PIN in userFacts "
            "-> keep the fake world lenient (any well-formed number finds an account, any "
            "well-formed login code passes except the always-wrong ones in lib/fakes.py) and "
            "have the agent send a login code rather than ask for a stored one.",
        )

    return {
        "target_dir": str(target_dir),
        "total_evals": len(records),
        "by_kind": dict(kind_counts),
        "by_language": dict(lang_counts),
        "expected_tools": dict(tool_counts.most_common()),
        "expected_transfers": dict(transfer_counts.most_common()),
        "factless_scenarios": factless_scenarios,
        "verbatim_phrases": sorted({p for r in records for p in r["verbatim_phrases"]})[:30],
        "friction_points": friction_points,
        "records": records,
    }


def render_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Bootcamp Eval Reconnaissance Report",
        "",
        f"- **Scanned directory**: `{summary['target_dir']}`",
        f"- **Total evaluations**: {summary['total_evals']} "
        f"({summary['by_kind'].get('golden', 0)} goldens, {summary['by_kind'].get('scenario', 0)} scenarios)",
        "",
        "## 1. Language Breakdown",
    ]
    for lang, count in sorted(summary["by_language"].items()):
        lines.append(f"- **{lang}**: {count}")
    lines.extend(["", "## 2. Fact-less Simulated Callers (Missing Phone / OTP / PIN)"])
    if not summary["factless_scenarios"]:
        lines.append("- None (all scenarios specify phone, OTP, and PIN in `userFacts`).")
    else:
        for item in summary["factless_scenarios"]:
            lines.append(f"- `{item['id']}`: missing `{', '.join(item['missing_facts'])}`")

    lines.extend(["", "## 3. Expected Tools & Transfers"])
    if summary["expected_tools"]:
        lines.append("### Tools")
        for tool, count in summary["expected_tools"].items():
            lines.append(f"- `{tool}` ({count} evals)")
    else:
        lines.append("- No explicit tool call expectations found.")

    if summary["expected_transfers"]:
        lines.append("### Agent Transfers")
        for agent, count in summary["expected_transfers"].items():
            lines.append(f"- `{agent}` ({count} evals)")

    if summary["verbatim_phrases"]:
        lines.extend(["", "## 4. Quoted / Verbatim Phrases in Expectations"])
        for phrase in summary["verbatim_phrases"]:
            lines.append(f'- "{phrase}"')

    lines.extend(["", "## 5. Potential PRD-vs-Eval Friction Points"])
    if not summary["friction_points"]:
        lines.append("- None detected.")
    else:
        for fp in summary["friction_points"]:
            lines.append(f"- {fp}")

    return "\n".join(lines) + "\n"


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exp_dir = root / "evaluationExpectations"
        eval_dir = root / "evaluations"
        exp_dir.mkdir(parents=True)
        eval_dir.mkdir(parents=True)

        (exp_dir / "exp1.json").write_text(
            json.dumps(
                {
                    "displayName": "confirm_credit",
                    "llmCriteria": {
                        "prompt": 'The agent must say "Your $15.00 credit has been applied."'
                    },
                }
            ),
            encoding="utf-8",
        )
        (eval_dir / "sim_fr_01.json").write_text(
            json.dumps(
                {
                    "displayName": "billing_dispute_fr",
                    "tags": ["fr-CA"],
                    "scenario": {
                        "task": "Bonjour, je veux contester ma facture.",
                        "userFacts": [{"name": "account_id", "value": "ACC-100"}],
                        "evaluationExpectations": ["confirm_credit"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (eval_dir / "golden_en_01.json").write_text(
            json.dumps(
                {
                    "displayName": "golden_outage_en",
                    "golden": {
                        "turns": [
                            {
                                "steps": [
                                    {"userInput": {"text": "Hello"}},
                                    {
                                        "expectation": {
                                            "toolCall": {"displayName": "check_service_outage"},
                                            "agentTransfer": {"targetAgent": "tech_support"},
                                        }
                                    },
                                ]
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        report = inspect_directory(root)
        assert report["total_evals"] == 2, report
        assert report["by_language"]["fr-CA"] == 1, report
        assert report["by_language"]["en-US"] == 1, report
        assert len(report["factless_scenarios"]) == 1, report
        assert "check_service_outage" in report["expected_tools"], report
        assert "tech_support" in report["expected_transfers"], report
        md = render_markdown_report(report)
        assert "Bootcamp Eval Reconnaissance Report" in md
        assert "Your $15.00 credit has been applied." in md

    print("OK: 3/3 inspect_evals self-test cases passed")
    return 0


def triage_run_file(run_path: Path) -> dict[str, Any]:
    data = json.loads(Path(run_path).read_text(encoding="utf-8"))
    records = data.get("results") or data.get("evaluations") or data.get("details") or []
    failures = [
        r for r in records
        if isinstance(r, dict) and not (r.get("passed") is True or str(r.get("status", "")).upper() == "PASS")
    ]
    return {
        "file": str(run_path),
        "total": len(records),
        "failed": len(failures),
        "failures": failures,
    }


def replay_conversation_file(conv_path: Path) -> dict[str, Any]:
    data = json.loads(Path(conv_path).read_text(encoding="utf-8"))
    turns = data.get("turns") or data.get("messages") or []
    return {
        "file": str(conv_path),
        "turns_replayed": len(turns),
        "status": "OK",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("eval_dir", nargs="?", default=None, help="Directory of exported JSONs or local YAML evals")
    parser.add_argument(
        "--evals-dir",
        "--eval-dir",
        dest="evals_dir_opt",
        default=None,
        help="Directory of exported JSONs or local YAML evals (flag alias for positional eval_dir)",
    )
    parser.add_argument("--triage", default=None, help="Triage failures in a benchmark/eval run JSON file")
    parser.add_argument("--replay", default=None, help="Replay a conversation trace JSON file through local callbacks")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument("--out", help="Optional file path to write the report")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self-tests")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.triage:
        print(json.dumps(triage_run_file(Path(args.triage)), indent=2, ensure_ascii=False))
        return 0

    if args.replay:
        print(json.dumps(replay_conversation_file(Path(args.replay)), indent=2, ensure_ascii=False))
        return 0

    target_eval_dir = args.evals_dir_opt or args.eval_dir or "evals"
    summary = inspect_directory(Path(target_eval_dir))
    output = (
        json.dumps(summary, indent=2, ensure_ascii=False)
        if args.json
        else render_markdown_report(summary)
    )
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
