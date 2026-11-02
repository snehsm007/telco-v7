#!/usr/bin/env python3
"""Gate 0 offline mutation and tool-breakage verifier.

Copies the repo's `lib/`, `cxas_app/`, `suite/`, `tests/`, and `evals/` into a
`tempfile.TemporaryDirectory()` so the working tree is never modified, then:
  1. Applies each policy/guardrail mutation in `MUTATIONS` and verifies `pytest`
     fails (exit code != 0).
  2. Injects a synthetic `SYSTEM_DOWN` error return into every `<tool>_impl` in
     `lib/services.py` (`ALL_TOOLS`) and verifies the unit/tool test suite fails.

Usage:
  python3 scripts/verify_mutations.py [--root .] [--mutations-only]
  python3 scripts/verify_mutations.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each mutation breaks one rule the agent must keep; the unit tests must notice.
# These match the kickstart scaffold. Add one for every PRD rule you implement
# (a cap, a disclosure, a refusal), and remove ones whose code you deleted:
# a mutation whose file or target is missing is skipped.
MUTATIONS = [
    {
        "id": "mutation_1_speak_long_numbers_in_full",
        "description": "Stop cutting long numbers to their last 4 digits in lib/speech.py",
        "file": "lib/speech.py",
        "target": "return digits[-4:]",
        "replacement": "return match.group(0)",
    },
    {
        "id": "mutation_2_task_without_login",
        "description": "Let submit_request run before the caller passed login in lib/services.py",
        "file": "lib/services.py",
        "target": 'if state.get("auth_status") != "pass":',
        "replacement": "if False:",
    },
    {
        "id": "mutation_3_forget_wrong_codes",
        "description": "Stop counting wrong login codes, so login is never refused, in lib/services.py",
        "file": "lib/services.py",
        "target": 'state["auth_failure_count"] = failures',
        "replacement": 'state["auth_failure_count"] = 0',
    },
    {
        "id": "mutation_4_login_survives_account_switch",
        "description": "Keep a login when the caller switches to another account in lib/services.py",
        "file": "lib/services.py",
        "target": 'state["auth_status"] = "none"',
        "replacement": "pass",
    },
    {
        "id": "mutation_5_accept_any_login_code",
        "description": "Accept every login code in lib/services.py",
        "file": "lib/services.py",
        "target": "if not login_code_accepted(digits, attempts=failures, max_attempts=MAX_LOGIN_ATTEMPTS):",
        "alt_targets": ["if not login_code_accepted(digits):"],
        "replacement": "if False:",
    },
]


def _find_python(repo_root: Path) -> str:
    """Interpreter for the mutated copies: $PYTHON, the repo's .venv, else this interpreter."""
    env_python = os.environ.get("PYTHON", "").strip()
    if env_python:
        # The Makefile may pass a command like "uv run --no-sync python"; only a
        # plain executable path can be used here.
        candidate = Path(env_python)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _copy_workspace(src_root: Path, dst_root: Path) -> None:
    for item in ("lib", "cxas_app", "suite", "tests", "evals", "docs"):
        src_dir = src_root / item
        if src_dir.exists():
            shutil.copytree(
                src_dir,
                dst_root / item,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
    for fname in (
        "pyproject.toml",
        "Makefile",
        "gate_thresholds.json",
        "run_record.schema.json",
    ):
        src_file = src_root / fname
        if src_file.exists():
            shutil.copy2(src_file, dst_root / fname)


def patch_function_to_return_error(source_text: str, tool_name: str) -> str:
    """Insert an immediate `SYSTEM_DOWN` error return at the start of `<tool_name>_impl`."""
    func_name = f"{tool_name}_impl"
    pattern = re.compile(
        rf"(^def {re.escape(func_name)}\b[\s\S]*?\)\s*(?:->\s*[^:]+)?:\n(?:\s*\"\"\"[\s\S]*?\"\"\"\n)?)",
        re.MULTILINE,
    )
    match = pattern.search(source_text)
    if not match:
        raise ValueError(f"Could not locate function header for {func_name}")
    injection = (
        '    return {"status": "error", "error": "SYSTEM_DOWN", '
        '"message": "injected breakage", "agent_action": "ESCALATE_SYSTEM_UNAVAILABLE"}\n'
    )
    return source_text[: match.end()] + injection + source_text[match.end() :]


def _resolve_target_str(mut: dict, content: str) -> str | None:
    candidates = [mut["target"]]
    if mut.get("alt_target"):
        candidates.append(mut["alt_target"])
    candidates.extend(mut.get("alt_targets", []))
    for cand in candidates:
        if cand and cand in content:
            return cand
    return None


def run_mutations(
    repo_root: Path,
    mutations: list[dict] | None = None,
    include_tool_breakages: bool = True,
) -> dict:
    python_bin = _find_python(repo_root)
    explicit_mutations = mutations is not None
    active_mutations = mutations if explicit_mutations else MUTATIONS
    results: list[dict] = []
    tool_results: list[dict] = []
    all_caught = True

    with tempfile.TemporaryDirectory(prefix="gecx_mutations_") as tmp:
        tmp_root = Path(tmp)
        _copy_workspace(repo_root, tmp_root)

        for mut in active_mutations:
            target_path = tmp_root / mut["file"]
            if not target_path.exists():
                if not explicit_mutations:
                    continue
                results.append(
                    {
                        "id": mut["id"],
                        "caught": False,
                        "error": f"File not found: {mut['file']}",
                    }
                )
                all_caught = False
                continue

            original_content = target_path.read_text(encoding="utf-8")
            target_str = _resolve_target_str(mut, original_content)
            if target_str is None:
                if not explicit_mutations:
                    continue
                results.append(
                    {
                        "id": mut["id"],
                        "caught": False,
                        "error": f"Target string not found in {mut['file']}",
                    }
                )
                all_caught = False
                continue

            mutated_content = original_content.replace(
                target_str, mut["replacement"], 1
            )
            target_path.write_text(mutated_content, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [python_bin, "-B", "-m", "pytest", "-q", "-o", "addopts="],
                    cwd=tmp_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                caught = proc.returncode != 0
            finally:
                target_path.write_text(original_content, encoding="utf-8")

            if not caught:
                all_caught = False
            results.append(
                {
                    "id": mut["id"],
                    "description": mut.get("description", ""),
                    "exit_code": proc.returncode,
                    "caught": caught,
                }
            )

        if include_tool_breakages and (tmp_root / "lib" / "services.py").exists():
            services_path = tmp_root / "lib" / "services.py"
            orig_services = services_path.read_text(encoding="utf-8")
            impl_names = re.findall(
                r"^def ([a-z0-9_]+)_impl\b", orig_services, flags=re.MULTILINE
            )
            for tool_name in impl_names:
                unit_test = tmp_root / "tests" / f"test_{tool_name}.py"
                services_test = tmp_root / "tests" / "test_services.py"
                test_targets = [
                    str(p.relative_to(tmp_root))
                    for p in (unit_test, services_test)
                    if p.exists()
                ]
                if not test_targets:
                    continue
                try:
                    patched = patch_function_to_return_error(orig_services, tool_name)
                except ValueError:
                    continue
                services_path.write_text(patched, encoding="utf-8")
                bundled_path = (
                    tmp_root
                    / "cxas_app"
                    / "tools"
                    / tool_name
                    / "python_function"
                    / "python_code.py"
                )
                orig_bundled = (
                    bundled_path.read_text(encoding="utf-8")
                    if bundled_path.exists()
                    else None
                )
                if orig_bundled is not None:
                    try:
                        bundled_path.write_text(
                            patch_function_to_return_error(orig_bundled, tool_name),
                            encoding="utf-8",
                        )
                    except ValueError:
                        pass
                try:
                    proc = subprocess.run(
                        [
                            python_bin,
                            "-B",
                            "-m",
                            "pytest",
                            "-q",
                            "-o",
                            "addopts=",
                            *test_targets,
                        ],
                        cwd=tmp_root,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                    caught = proc.returncode != 0
                finally:
                    services_path.write_text(orig_services, encoding="utf-8")
                    if orig_bundled is not None:
                        bundled_path.write_text(orig_bundled, encoding="utf-8")
                if not caught:
                    all_caught = False
                tool_results.append(
                    {
                        "tool": tool_name,
                        "caught": caught,
                        "exit_code": proc.returncode,
                    }
                )

    if not results and not tool_results:
        all_caught = False

    return {
        "total_mutations": len(results),
        "caught_mutations": sum(1 for r in results if r["caught"]),
        "total_tool_breakages": len(tool_results),
        "caught_tool_breakages": sum(1 for r in tool_results if r["caught"]),
        "all_caught": all_caught,
        "results": results,
        "tool_breakages": tool_results,
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "lib").mkdir()
        (root / "tests").mkdir()
        (root / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (root / "lib" / "wording.py").write_text(
            'GREETING = "Hello, thanks for calling."\n'
            'UNUSED = "unused"\n',
            encoding="utf-8",
        )
        (root / "lib" / "services.py").write_text(
            "def demo_tool_impl(x: str = '') -> dict:\n"
            '    return {"status": "ok", "agent_action": "DONE", "data": {"x": x}}\n',
            encoding="utf-8",
        )
        (root / "tests" / "test_wording.py").write_text(
            "from lib.wording import GREETING\n"
            "def test_greeting():\n"
            '    assert GREETING == "Hello, thanks for calling."\n',
            encoding="utf-8",
        )
        (root / "tests" / "test_services.py").write_text(
            "from lib.services import demo_tool_impl\n"
            "def test_demo():\n"
            '    assert demo_tool_impl("a")["status"] == "ok"\n',
            encoding="utf-8",
        )
        good_muts = [
            {
                "id": "m_caught",
                "file": "lib/wording.py",
                "target": '"Hello, thanks for calling."',
                "replacement": '"Hi, thanks for calling."',
            }
        ]
        summary = run_mutations(root, mutations=good_muts, include_tool_breakages=True)
        assert summary["all_caught"] is True, f"Expected all_caught=True, got {summary}"
        assert summary["caught_mutations"] == 1
        assert summary["caught_tool_breakages"] == 1

        uncaught_muts = [
            {
                "id": "m_missed",
                "file": "lib/wording.py",
                "target": '"unused"',
                "replacement": '"changed"',
            }
        ]
        summary_miss = run_mutations(
            root, mutations=uncaught_muts, include_tool_breakages=False
        )
        assert summary_miss["all_caught"] is False, "Expected uncaught mutation to fail"

    print("OK (verify_mutations self-test)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", default=None)
    p.add_argument("--app", default=None, help="Optional path to cxas_app directory")
    p.add_argument("--tests", default=None, help="Optional path to tests directory")
    p.add_argument("--mutations-only", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.root:
        root_dir = Path(args.root).resolve()
    elif args.app:
        root_dir = Path(args.app).resolve().parent
    elif args.tests:
        root_dir = Path(args.tests).resolve().parent
    else:
        root_dir = REPO_ROOT
    summary = run_mutations(
        root_dir,
        include_tool_breakages=not args.mutations_only,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_caught"] else 1


if __name__ == "__main__":
    sys.exit(main())
