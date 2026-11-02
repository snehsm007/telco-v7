#!/usr/bin/env python3
"""Two-Bucket Failure Triage CLI for GECX / CXAS evaluations.

Wraps `scripts/inspect_evals.py --triage` and classifies non-3/3 evaluations into:
  - Bucket A (Additive Leaf Fixes): Zero-coupling single specialist/leaf tool
    metadata, response schema additions, leaf tool docstrings/descriptions, or
    atomic sequential wrapping. Safe to batch in a single commit.
  - Bucket B (Shared Decision Boundaries): Shared control flow, routing, global
    rules, auth/OTP gating, or eligibility thresholds. Must be isolated one at a
    time and smoke-tested alongside negative twins from the same topic.

Usage:
  python3 scripts/triage_failures.py --run <run.json> [--evals-dir bench] [--json]
  python3 scripts/triage_failures.py --self-test
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts import inspect_evals
except ImportError:
    inspect_evals = None  # type: ignore[assignment]


# Boundary markers indicating Bucket B (shared decision boundary / router / auth / global)
BUCKET_B_INDICATORS = {
    "router",
    "routing",
    "transfer",
    "agent_transfer",
    "global",
    "auth",
    "otp",
    "pin",
    "secret_pin",
    "login_code",
    "auth_status",
    "gate",
    "gating",
    "threshold",
    "cap",
    "deflection",
    "business_deflection",
    "eligibility",
    "multilingual",
    "language_switch",
    "speak_immediate",
    "speak_mid_call",
}

# Leaf tool indicators favoring Bucket A when no boundary indicators are triggered
LEAF_TOOL_INDICATORS = {
    "tool_expectation",
    "missing_key",
    "schema",
    "metadata",
    "response_key",
    "docstring",
    "formatting",
    "pacing",
    "leaf",
}


def normalize_eval_id(raw_id: str) -> str:
    """Normalize eval ID by stripping sim__ or golden__ prefixes and extensions."""
    s = raw_id.strip()
    s = re.sub(r"\.(?:json|yaml|yml)$", "", s)
    s = re.sub(r"^(?:sim__|golden__)", "", s)
    return s


def extract_topic(eval_id: str) -> str:
    """Extract topic group from an eval ID (e.g. 'check_outage', 'dispute_charge')."""
    clean = normalize_eval_id(eval_id)
    # Common multi-word action prefixes in telco / service domains
    common_prefixes = [
        "check_outage",
        "check_tech_status",
        "check_ticket_status",
        "dispute_charge",
        "dispute_unrecognized",
        "report_fraud",
        "reset_password",
        "restore_service",
        "request_refund",
        "manage_mfa",
        "pay_bill",
        "pay_mobility",
        "pay_past_due",
        "cancel_service",
        "cancel_home",
        "upgrade_mobile",
        "upgrade_internet",
        "troubleshoot_mobile",
        "troubleshoot_satellite",
        "troubleshoot_tv",
        "warranty_replacement",
        "transfer_number",
        "transfer_landline",
        "speak_immediate",
        "speak_mid_call",
        "setup_autopay",
        "port_out",
    ]
    for p in common_prefixes:
        if clean.startswith(p):
            return p
    parts = clean.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return parts[0] if parts else clean


def scan_bench_evals(evals_dir: Path) -> dict[str, list[str]]:
    """Index all evaluations by topic from evals_dir."""
    topics: dict[str, list[str]] = {}
    if not evals_dir.exists():
        return topics

    # Look for evaluation folders/files
    found_names: set[str] = set()
    for p in evals_dir.rglob("*.json"):
        if "evaluationExpectations" in p.parts or "runs" in p.parts:
            continue
        if p.name in ("index.json", "coverage.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                name = str(data.get("displayName") or data.get("name") or p.parent.name)
                found_names.add(name)
        except (OSError, ValueError):
            continue

    for p in evals_dir.rglob("*.yaml"):
        if "runs" in p.parts:
            continue
        found_names.add(p.stem)

    for name in found_names:
        topic = extract_topic(name)
        topics.setdefault(topic, []).append(name)

    return topics


def find_negative_twins(eval_id: str, topic: str, topic_index: dict[str, list[str]]) -> list[str]:
    """Find other evaluations under the same topic that represent contrasting branches."""
    siblings = topic_index.get(topic, [])
    norm = normalize_eval_id(eval_id)
    twins: list[str] = []
    for s in siblings:
        if normalize_eval_id(s) != norm and s not in twins:
            twins.append(s)
    return sorted(twins)


def classify_failure(
    failure: dict[str, Any],
    topic_index: dict[str, list[str]],
) -> dict[str, Any]:
    """Classify a non-3/3 failure into Bucket A vs Bucket B."""
    eval_id = str(
        failure.get("eval_id")
        or failure.get("display_name")
        or failure.get("displayName")
        or failure.get("name")
        or failure.get("id")
        or "unknown"
    )
    topic = extract_topic(eval_id)
    twins = find_negative_twins(eval_id, topic, topic_index)

    blob = json.dumps(failure, ensure_ascii=False).lower()
    
    # Check for strong Bucket B indicators
    has_b_indicator = any(
        re.search(rf"\b{re.escape(term)}\b", blob) for term in BUCKET_B_INDICATORS
    )
    # Check if there are twins representing different branches
    has_contrasting_twins = len(twins) > 0

    # Bucket B criteria:
    # 1. Direct indicator of routing, auth, global instruction, threshold, or
    # 2. Topic has multiple contrasting branches and failure mentions decision/branching/transfer/tool selection
    if has_b_indicator or (has_contrasting_twins and ("transfer" in blob or "route" in blob or "auth" in blob or "status" in blob)):
        bucket = "Bucket B"
        rationale = "Shared Decision Boundary: involves routing, auth, global rules, or shared eligibility threshold."
    elif any(re.search(rf"\b{re.escape(term)}\b", blob) for term in LEAF_TOOL_INDICATORS):
        bucket = "Bucket A"
        rationale = "Additive Leaf Fix: single specialist/leaf tool metadata or response schema addition."
    elif not has_contrasting_twins:
        bucket = "Bucket A"
        rationale = "Additive Leaf Fix: isolated CUJ with no shared branch collisions detected."
    else:
        # If ambiguous and contrasting twins exist, classify as Bucket B for safety
        bucket = "Bucket B"
        rationale = "Shared Decision Boundary: topic has sibling branches with coupling risk."

    return {
        "eval_id": eval_id,
        "topic": topic,
        "bucket": bucket,
        "rationale": rationale,
        "negative_twins": twins if bucket == "Bucket B" else [],
        "raw_failure": failure,
    }


def triage_failures(
    run_path: Path,
    evals_dir: Path,
) -> dict[str, Any]:
    """Triage failures from run_path using inspect_evals triage and classify into buckets."""
    if inspect_evals is not None and hasattr(inspect_evals, "triage_run_file"):
        base_triage = inspect_evals.triage_run_file(run_path)
    else:
        # Fallback if inspect_evals is not importable
        data = json.loads(run_path.read_text(encoding="utf-8"))
        records = data.get("results") or data.get("evaluations") or data.get("details") or []
        failures = [
            r for r in records
            if isinstance(r, dict)
            and not (
                r.get("passed") is True
                or str(r.get("status", "")).upper() == "PASS"
                or (r.get("passes") == 3 and r.get("repeats", 3) == 3)
            )
        ]
        base_triage = {
            "file": str(run_path),
            "total": len(records),
            "failed": len(failures),
            "failures": failures,
        }

    raw_failures = base_triage.get("failures") or []
    topic_index = scan_bench_evals(evals_dir)

    classified: list[dict[str, Any]] = []
    bucket_a: list[dict[str, Any]] = []
    bucket_b: list[dict[str, Any]] = []

    for f in raw_failures:
        res = classify_failure(f, topic_index)
        classified.append(res)
        if res["bucket"] == "Bucket A":
            bucket_a.append(res)
        else:
            bucket_b.append(res)

    return {
        "run_file": str(run_path),
        "total_evals": base_triage.get("total", len(raw_failures)),
        "total_non_3_3": len(raw_failures),
        "bucket_a_count": len(bucket_a),
        "bucket_b_count": len(bucket_b),
        "bucket_a": bucket_a,
        "bucket_b": bucket_b,
    }


def render_markdown(triage_result: dict[str, Any]) -> str:
    lines = [
        "# Non-3/3 Evaluation Triage Report",
        "",
        f"- **Run file**: `{triage_result['run_file']}`",
        f"- **Total evaluations**: {triage_result['total_evals']}",
        f"- **Non-3/3 failures**: {triage_result['total_non_3_3']} "
        f"({triage_result['bucket_a_count']} in Bucket A, {triage_result['bucket_b_count']} in Bucket B)",
        "",
        "## Bucket A: Additive Leaf Fixes (Safe to batch)",
        "Zero-coupling single specialist/leaf tool metadata, schema additions, or docstrings.",
    ]
    if not triage_result["bucket_a"]:
        lines.append("- None")
    else:
        for item in triage_result["bucket_a"]:
            lines.append(f"- **`{item['eval_id']}`** (topic: `{item['topic']}`)")
            lines.append(f"  - Rationale: {item['rationale']}")

    lines.extend([
        "",
        "## Bucket B: Shared Decision Boundaries (Isolate 1-at-a-time)",
        "Shared control flow, routing, global rules, auth/OTP gating, or shared thresholds.",
        "Always smoke-test alongside the listed negative twin(s) before running bench-full.",
    ])
    if not triage_result["bucket_b"]:
        lines.append("- None")
    else:
        for item in triage_result["bucket_b"]:
            lines.append(f"- **`{item['eval_id']}`** (topic: `{item['topic']}`)")
            lines.append(f"  - Rationale: {item['rationale']}")
            if item["negative_twins"]:
                twins_str = ", ".join(f"`{t}`" for t in item["negative_twins"])
                lines.append(f"  - **Negative Twins**: {twins_str}")
            else:
                lines.append("  - **Negative Twins**: None identified in evals directory")

    return "\n".join(lines) + "\n"


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        evals_dir = tmp_dir / "bench" / "evaluations"
        evals_dir.mkdir(parents=True)

        # Create topic twin evals
        (evals_dir / "sim__check_outage_active.json").write_text(
            json.dumps({"displayName": "sim__check_outage_active"}), encoding="utf-8"
        )
        (evals_dir / "sim__check_outage_none_found.json").write_text(
            json.dumps({"displayName": "sim__check_outage_none_found"}), encoding="utf-8"
        )
        (evals_dir / "sim__lookup_spec_sheet.json").write_text(
            json.dumps({"displayName": "sim__lookup_spec_sheet"}), encoding="utf-8"
        )

        # Create a mock run JSON
        run_file = tmp_dir / "run.json"
        run_file.write_text(
            json.dumps({
                "results": [
                    {
                        "displayName": "sim__lookup_spec_sheet",
                        "passed": False,
                        "error": "missing response_key remaining_services_policy in tool_expectation",
                    },
                    {
                        "displayName": "sim__check_outage_active",
                        "passed": False,
                        "error": "router transferred to tech_support instead of billing; auth threshold failed",
                    },
                    {
                        "displayName": "sim__passing_eval",
                        "passed": True,
                    },
                ]
            }),
            encoding="utf-8",
        )

        res = triage_failures(run_file, evals_dir)
        assert res["total_evals"] == 3, res
        assert res["total_non_3_3"] == 2, res
        assert res["bucket_a_count"] == 1, res
        assert res["bucket_b_count"] == 1, res

        a_item = res["bucket_a"][0]
        assert a_item["eval_id"] == "sim__lookup_spec_sheet", a_item

        b_item = res["bucket_b"][0]
        assert b_item["eval_id"] == "sim__check_outage_active", b_item
        assert "sim__check_outage_none_found" in b_item["negative_twins"], b_item

        md = render_markdown(res)
        assert "Bucket A: Additive Leaf Fixes" in md
        assert "Bucket B: Shared Decision Boundaries" in md
        assert "Negative Twins" in md

    print("OK: triage_failures self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", dest="run_path", help="Path to evaluation/benchmark run JSON file")
    parser.add_argument(
        "--evals-dir",
        default="bench",
        help="Evaluations directory to discover twins (default: bench)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Markdown")
    parser.add_argument("--self-test", action="store_true", help="Run self-test suite")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.run_path:
        parser.error("--run <path> is required unless --self-test is set")

    run_path = Path(args.run_path)
    if not run_path.exists():
        sys.stderr.write(f"ERROR: Run file not found: {run_path}\n")
        return 1

    evals_dir = Path(args.evals_dir)
    res = triage_failures(run_path, evals_dir)

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(res))

    return 0


if __name__ == "__main__":
    sys.exit(main())
