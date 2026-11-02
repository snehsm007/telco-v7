#!/usr/bin/env python3
"""Change-to-Eval Impact Analyzer and the cloud gates: push -> smoke -> record.

Computes which evaluations are impacted by a code/prompt diff between a base
commit (default: last full benchmark run) and a target state (default: working
tree), and keeps the order of the cloud steps honest:

  1. `make push` refuses uncommitted changes in cxas_app/, lib/ and evals/, pushes,
     and records what it pushed in history/last_push.json (--require-clean,
     --record-push).
  2. `make smoke-impact` only runs when the app runs this checkout (the source
     fingerprint of history/last_push.json matches), smokes every impacted eval
     3 times, and records the verdict for that fingerprint (--smoke-plan,
     --record-smoke).
  3. `make bench-full` only runs on the pushed checkout and after a passing smoke,
     unless there is no baseline full run yet, the verdict is FULL, nothing changed,
     or SKIP_SMOKE_GATE=1 REASON="..." is given (--check-bench-full).

The source fingerprint hashes the committed git trees of cxas_app/, lib/ and evals/,
so a docs-only or history-only commit does not change it. Uncommitted edits in those
folders add a "+dirty" suffix that never matches a push.

Verdicts: FULL (a change every eval depends on: global instruction, app.json, shared
lib code, login or fake-account code; a tool folder the impact map has never seen, i.e.
a new or renamed tool; or every eval is impacted), SMOKE (the listed evals: an edit under
cxas_app/tools/<name>/ smokes the evals that use <name>, plus canaries), NONE (nothing to
smoke; only the generated after_model callback files are ignored).

Usage:
  python3 scripts/impact.py [--base <commit>] [--target <commit>]
  python3 scripts/impact.py --build-map
  python3 scripts/impact.py --print-evals
  python3 scripts/impact.py --record-smoke bench/runs/smoke-<sha7>.json
  python3 scripts/impact.py --require-clean
  python3 scripts/impact.py --record-push --app <app resource> --version git-<sha7>
  python3 scripts/impact.py --smoke-plan --app <app resource>
  python3 scripts/impact.py --check-bench-full --app <app resource> [--skip-smoke-gate --reason "..."]
  python3 scripts/impact.py --source-fingerprint
  python3 scripts/impact.py --self-test

`--check-smoke` and `--check-push` are kept as aliases of `--check-bench-full`.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
IMPACT_MAP_PATH = ROOT / "history" / "eval_impact_map.json"
IMPACT_LAST_PATH = ROOT / "history" / "last_impact.json"
IMPACT_LOG_PATH = ROOT / "history" / "impact_gate.log"
LAST_PUSH_PATH = ROOT / "history" / "last_push.json"

# Folders whose committed trees make up the source fingerprint (what `make push` deploys).
SOURCE_DIRS: tuple[str, ...] = ("cxas_app", "lib", "evals")

# Shared login and fake-account code: every conversation goes through it, so a change
# to any of these needs a full run (verdict FULL), not a smoke of a few evals.
CORE_SHARED_FAKES = frozenset(
    {
        "ACCOUNTS",
        "VALID_PINS",
        "VALID_OTPS",
        "VALID_LOGIN_CODES",
        "ALWAYS_WRONG_LOGIN_CODES",
        "find_account",
        "login_code_accepted",
        "secret_pin_accepted",
        "normalize_code",
        "only_digits",
    }
)
CORE_LOGIN_TOOLS = frozenset(
    {
        "lookup_account",
        "send_login_code",
        "check_login_code",
        "check_secret_pin",
        "fetch_customer_profile",
        "send_authentication_otp",
        "validate_authentication_otp",
        "validate_authentication_pin",
    }
)

STARTER_DEFAULT_TOOLS = [
    "lookup_account",
    "send_login_code",
    "check_login_code",
    "check_secret_pin",
    "submit_request",
    "handover_to_person",
]


def _candidate_lib_dirs(root: Path | None = None) -> list[Path]:
    base = root or ROOT
    return [
        base / "cxas_app" / "python_code" / "lib",
        base / "lib",
    ]


def _candidate_bench_dirs(root: Path | None = None) -> list[Path]:
    base = root or ROOT
    return [
        base / "history" / "bench",
        base / "bench" / "runs",
    ]


def derive_const_to_tools(root: Path | None = None) -> dict[str, list[str]]:
    """Derive mapping from fakes.py constants/functions to tool names via AST."""
    mapping: dict[str, set[str]] = {}
    lib_dir: Path | None = None
    for cand in _candidate_lib_dirs(root):
        if cand.is_dir():
            lib_dir = cand
            break

    fakes_symbols: set[str] = set()
    fakes_fn_deps: dict[str, set[str]] = {}
    if lib_dir and (lib_dir / "fakes.py").is_file():
        try:
            f_tree = ast.parse((lib_dir / "fakes.py").read_text(encoding="utf-8"))
            for node in f_tree.body:
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            fakes_symbols.add(t.id)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    fakes_symbols.add(node.target.id)
                elif isinstance(node, ast.FunctionDef):
                    fakes_symbols.add(node.name)
                    referenced = {
                        sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)
                    }
                    fakes_fn_deps[node.name] = referenced
        except (OSError, SyntaxError):
            pass

    if lib_dir and (lib_dir / "services.py").is_file():
        try:
            s_tree = ast.parse((lib_dir / "services.py").read_text(encoding="utf-8"))
            for node in s_tree.body:
                if isinstance(node, ast.FunctionDef) and node.name.endswith("_impl"):
                    tool_name = node.name[: -len("_impl")]
                    names_used = {
                        sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)
                    }
                    for sym in list(names_used):
                        if sym in fakes_fn_deps:
                            names_used |= fakes_fn_deps[sym]
                    for sym in names_used:
                        if not fakes_symbols or sym in fakes_symbols:
                            mapping.setdefault(sym, set()).add(tool_name)
        except (OSError, SyntaxError):
            pass

    # Fallback starter defaults for standard credential/account symbols
    defaults = {
        "ACCOUNTS": ["lookup_account"],
        "VALID_PINS": ["check_login_code", "check_secret_pin"],
        "VALID_OTPS": ["check_login_code", "send_login_code"],
        "ALWAYS_WRONG_LOGIN_CODES": ["check_login_code", "check_secret_pin"],
        "find_account": ["lookup_account"],
        "lookup_account_record": ["lookup_account"],
        "login_code_accepted": ["check_login_code", "check_secret_pin"],
    }
    for k, tools in defaults.items():
        mapping.setdefault(k, set()).update(tools)

    return {k: sorted(v) for k, v in mapping.items()}


def _is_valid_full_run_payload(
    data: dict[str, Any],
    expected_min_evals: int = 0,
) -> bool:
    """Return True if `data` represents a clean, single-commit, non-holdout full run."""
    if not isinstance(data, dict):
        return False
    if data.get("is_holdout") is True:
        return False

    commits = data.get("commits")
    if isinstance(commits, list) and len(commits) > 1:
        return False

    app_versions = data.get("app_versions_seen", data.get("app_versions"))
    if isinstance(app_versions, list) and len(app_versions) > 1:
        return False

    results = data.get("results", {})
    eval_count = int(
        data.get("eval_count")
        or data.get("total_evals")
        or (data.get("evals") if isinstance(data.get("evals"), int) else 0)
        or (len(results) if isinstance(results, (list, dict)) else 0)
    )
    if expected_min_evals > 0 and eval_count < expected_min_evals:
        return False

    if "is_full_run" in data:
        return bool(data["is_full_run"]) and eval_count > 0

    return eval_count >= max(1, expected_min_evals or 50)


def _extract_eval_map(raw_map: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_map, dict):
        return {}
    nested = raw_map.get("evals")
    if isinstance(nested, dict):
        return nested
    return {
        k: v
        for k, v in raw_map.items()
        if isinstance(v, dict) and ("tools" in v or "agents" in v or "language" in v)
    }


def find_latest_full_run(
    eval_map: dict[str, Any] | None = None,
    root: Path | None = None,
) -> tuple[Path | None, dict[str, Any] | None]:
    """Find the most recent valid full benchmark run JSON by inspecting payload content."""
    expected_min = len(eval_map) if eval_map else 0
    candidates: list[Path] = []
    for bench_dir in _candidate_bench_dirs(root):
        if bench_dir.is_dir():
            candidates.extend(bench_dir.glob("*.json"))

    candidates.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    for path in candidates:
        if path.name.startswith("smoke-") or "holdout" in path.name.lower():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _is_valid_full_run_payload(data, expected_min_evals=expected_min):
            return path, data
    return None, None


def get_last_full_run_commit(root: Path | None = None) -> str | None:
    """Return the commit SHA of the latest valid full benchmark run, or None."""
    eval_map: dict[str, Any] | None = None
    map_path = (root / "history" / "eval_impact_map.json") if root else IMPACT_MAP_PATH
    if map_path.is_file():
        try:
            eval_map = _extract_eval_map(json.loads(map_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            eval_map = None

    _, data = find_latest_full_run(eval_map=eval_map, root=root)
    if not data:
        return None
    commit = data.get("git_sha") or data.get("commit")
    if not commit:
        commits = data.get("commits")
        if isinstance(commits, list) and len(commits) == 1:
            commit = commits[0]
    if commit and str(commit) != "unknown":
        return str(commit)
    return None


find_latest_full_run_commit = get_last_full_run_commit


# ----------------------------------------------------------------------------- source fingerprint


def _git(args: list[str], cwd: Path, strip: bool = True) -> str | None:
    """stdout of `git <args>` run in `cwd`, or None when git fails or is missing."""
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return res.stdout.strip() if strip else res.stdout


def _norm_dirs(dirs: Any) -> tuple[str, ...]:
    """Accept "a,b c" or a list; return clean relative folder names (Postel's law)."""
    if dirs is None:
        return SOURCE_DIRS
    if isinstance(dirs, str):
        dirs = re.split(r"[,\s]+", dirs)
    out = tuple(str(d).strip().strip("/") for d in dirs if str(d).strip().strip("/"))
    return out or SOURCE_DIRS


def head_sha7(root: Path | None = None) -> str:
    """Short commit id of HEAD (the `git-<sha7>` version and `full-<sha7>` label)."""
    return _git(["rev-parse", "--short=7", "HEAD"], root or ROOT) or "nogit"


def source_dirty_files(root: Path | None = None, dirs: Any = None) -> list[str]:
    """`git status --porcelain` lines for uncommitted changes in the source folders."""
    base = root or ROOT
    out = _git(
        ["status", "--porcelain", "--untracked-files=all", "--", *_norm_dirs(dirs)],
        base,
        strip=False,
    )
    if out is None:
        return []
    return [line for line in out.splitlines() if line.strip()]


def source_fingerprint(
    root: Path | None = None,
    dirs: Any = None,
    ref: str = "HEAD",
    include_dirty: bool = True,
) -> str:
    """Hash of the committed git trees of the source folders at `ref`.

    `git rev-parse HEAD:cxas_app` names the exact content of a committed folder, so
    the hash changes only when cxas_app/, lib/ or evals/ change; a docs-only or
    history-only commit keeps it. Uncommitted edits in those folders (at HEAD) add
    a "+dirty.<hash>" suffix, which never matches a recorded push.
    """
    base = root or ROOT
    folders = _norm_dirs(dirs)
    listing = _git(["ls-tree", ref, "--", *folders], base)
    if listing is None:
        if _git(["rev-parse", "--git-dir"], base) is None:
            return "nogit"
        listing = ""  # a repository without commits yet
    trees: dict[str, str] = {}
    for line in listing.splitlines():
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if len(fields) == 3:
            trees[path.strip()] = fields[2]
    parts = [f"{folder}={trees.get(folder, '-')}" for folder in folders]
    fingerprint = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    if not include_dirty or ref != "HEAD":
        return fingerprint
    dirty = source_dirty_files(base, folders)
    if not dirty:
        return fingerprint
    digest = hashlib.sha256()
    digest.update((_git(["diff", "HEAD", "--", *folders], base, strip=False) or "").encode("utf-8"))
    for line in sorted(dirty):
        digest.update((line + "\n").encode("utf-8"))
        if line.startswith("??"):
            path = base / line[3:].strip().strip('"')
            if path.is_file():
                try:
                    digest.update(path.read_bytes())
                except OSError:
                    pass
    return f"{fingerprint}+dirty.{digest.hexdigest()[:8]}"


def fingerprint_at(commit: str | None, root: Path | None = None, dirs: Any = None) -> str | None:
    """Source fingerprint of an earlier commit, or None when that commit is not in this clone."""
    base = root or ROOT
    if not commit or _git(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], base) is None:
        return None
    return source_fingerprint(base, dirs, ref=commit, include_dirty=False)


def compute_working_tree_fingerprint(root: Path | None = None) -> str:
    """Legacy name: the source fingerprint of the working tree (see source_fingerprint)."""
    return source_fingerprint(root)


def build_impact_map(root: Path | None = None) -> dict[str, Any]:
    """Build or update history/eval_impact_map.json from benchmark run JSONs and eval configs."""
    base = root or ROOT
    map_path = base / "history" / "eval_impact_map.json"
    evals_dir = base / "bench" / "dev" / "evaluations"

    eval_map: dict[str, dict[str, Any]] = {}

    if evals_dir.is_dir():
        for ef in sorted(evals_dir.rglob("*.json")):
            try:
                edata = json.loads(ef.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(edata, dict):
                continue
            eid = str(edata.get("displayName") or edata.get("name") or ef.stem)
            entry = eval_map.setdefault(
                eid,
                {"agents": set(), "tools": set(), "language": "en", "last_pass_rate": "3/3"},
            )
            task_str = json.dumps(edata).lower()
            if "french" in eid.lower() or "français" in task_str or "je veux" in task_str:
                entry["language"] = "fr"
            elif "spanish" in eid.lower() or "español" in task_str:
                entry["language"] = "es"

    for bench_dir in _candidate_bench_dirs(base):
        if not bench_dir.is_dir():
            continue
        for rpath in sorted(bench_dir.glob("*.json")):
            if "holdout" in rpath.name.lower():
                continue
            try:
                rdata = json.loads(rpath.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(rdata, dict):
                continue
            results = rdata.get("results", [])
            items: list[tuple[str, dict[str, Any]]] = []
            if isinstance(results, dict):
                items = [(str(k), v) for k, v in results.items() if isinstance(v, dict)]
            elif isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        eid = str(
                            item.get("display_name")
                            or item.get("eval_id")
                            or item.get("name")
                            or ""
                        )
                        if eid:
                            items.append((eid, item))

            for eid, res in items:
                entry = eval_map.setdefault(
                    eid,
                    {"agents": set(), "tools": set(), "language": "en", "last_pass_rate": "3/3"},
                )
                entry["agents"].add("router")
                pass_runs = res.get("pass_runs")
                total_runs = res.get("total_runs", 3)
                if isinstance(pass_runs, int):
                    entry["last_pass_rate"] = f"{pass_runs}/{total_runs}"
                for tool_item in res.get("tool_vector") or res.get("tool_Vector") or []:
                    tname = str(tool_item).split(":")[0].strip()
                    if tname:
                        entry["tools"].add(tname)
                for conv in res.get("conversations") or []:
                    if not isinstance(conv, dict):
                        continue
                    for tool_call in conv.get("tools") or []:
                        tname = str(tool_call).split("(")[0].strip()
                        if tname:
                            entry["tools"].add(tname)
                for raw_run in res.get("raw_runs") or []:
                    if not isinstance(raw_run, dict):
                        continue
                    scen = raw_run.get("scenario_result")
                    if not isinstance(scen, dict):
                        continue
                    for span in scen.get("span_latencies") or []:
                        if not isinstance(span, dict):
                            continue
                        disp = str(span.get("display_name") or "").strip()
                        res_name = str(span.get("resource") or "").strip()
                        if span.get("callback") and "(" in disp:
                            ag = disp.split("(", 1)[0].strip()
                            if ag:
                                entry["agents"].add(ag)
                        elif "/tools/" in res_name or span.get("type_") == 1:
                            tname = disp or res_name.rsplit("/tools/", 1)[-1].strip()
                            if tname:
                                entry["tools"].add(tname)

    serializable_evals: dict[str, dict[str, Any]] = {}
    for eid, info in sorted(eval_map.items()):
        serializable_evals[eid] = {
            "agents": sorted(info["agents"]) if info["agents"] else ["router"],
            "tools": sorted(info["tools"]),
            "language": info["language"],
            "last_pass_rate": info["last_pass_rate"],
        }

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_count": len(serializable_evals),
        "evals": serializable_evals,
    }
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return output


def get_git_diff_files(
    base_commit: str,
    target_commit: str | None = None,
    root: Path | None = None,
) -> list[str]:
    """Return list of changed file paths between `base_commit` and `target_commit` (or working tree)."""
    cwd = root or ROOT
    cmd = ["git", "diff", "--name-only", base_commit]
    if target_commit:
        cmd.append(target_commit)
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
        files = set(res.stdout.strip().splitlines())
        if not target_commit:
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            files.update(untracked.stdout.strip().splitlines())
        return sorted(f for f in files if f)
    except subprocess.CalledProcessError:
        return []


def get_changed_python_symbols(
    file_path: str,
    base_commit: str,
    target_commit: str | None = None,
    root: Path | None = None,
) -> set[str]:
    """Identify which top-level Python functions or constants changed in `file_path`."""
    cwd = root or ROOT
    cmd = ["git", "diff", "-U0", base_commit]
    if target_commit:
        cmd.append(target_commit)
    cmd.extend(["--", file_path])
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
        diff_text = res.stdout
    except subprocess.CalledProcessError:
        return {"ALL"}

    full_path = cwd / file_path
    if not full_path.exists():
        return {"ALL"}

    content = full_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"ALL"}

    changed_lines: set[int] = set()
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                for ln in range(start, start + max(1, count)):
                    changed_lines.add(ln)

    changed_symbols: set[str] = set()
    for node in tree.body:
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start)
        if any(start <= ln <= end for ln in changed_lines):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                changed_symbols.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        changed_symbols.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                changed_symbols.add(node.target.id)

    return changed_symbols if changed_symbols else {"ALL"}


def _is_only_generated_tool_bundle_diff(
    file_path: str,
    base_commit: str,
    target_commit: str | None = None,
    root: Path | None = None,
) -> bool:
    """Return True if `file_path` is a tool python_code.py whose diff is strictly below `# DO NOT MODIFY CODE BELOW THIS LINE`."""
    if not (file_path.startswith("cxas_app/tools/") and file_path.endswith("/python_function/python_code.py")):
        return False
    cwd = root or ROOT
    full_path = cwd / file_path
    if not full_path.exists():
        return False
    content = full_path.read_text(encoding="utf-8")
    marker_line = None
    for idx, line in enumerate(content.splitlines(), 1):
        if "# DO NOT MODIFY CODE BELOW THIS LINE" in line:
            marker_line = idx
            break
    if marker_line is None:
        return False
    cmd = ["git", "diff", "-U0", base_commit]
    if target_commit:
        cmd.append(target_commit)
    cmd.extend(["--", file_path])
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        return False
    if "new file mode" in res.stdout or "deleted file mode" in res.stdout:
        return False
    hunks = [ln for ln in res.stdout.splitlines() if ln.startswith("@@")]
    if not hunks:
        return False
    for line in hunks:
        m = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if not m or int(m.group(1)) <= marker_line:
            return False
    return True


def analyze_impact(
    base_commit: str,
    target_commit: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Analyze git diff from `base_commit` and compute `must_smoke` evaluation list."""
    base = root or ROOT
    map_path = base / "history" / "eval_impact_map.json"
    last_path = base / "history" / "last_impact.json"

    if not map_path.exists():
        build_impact_map(root=base)

    impact_data = json.loads(map_path.read_text(encoding="utf-8"))
    eval_map: dict[str, dict[str, Any]] = _extract_eval_map(impact_data)
    const_to_tools = derive_const_to_tools(root=base)

    changed_files = get_git_diff_files(base_commit, target_commit, root=base)
    has_lib_diff = any(
        f.endswith(("lib/services.py", "lib/fakes.py", "lib/replies.py")) for f in changed_files
    )

    code_changed_files = [
        f
        for f in changed_files
        if not (
            f.startswith("docs/")
            or f.startswith("bench/")
            or f.startswith("history/")
            or f.startswith("tests/")
            or f.startswith("dashboard/")
            or f.endswith(".md")
            or f in (".gitignore", "scripts/impact.py", "scripts/eval_contract.py")
            # Generated from lib/ by suite/bundle.py; lib/ changes are mapped below.
            or (f.startswith("cxas_app/agents/") and "after_model_callbacks" in f)
            or (has_lib_diff and _is_only_generated_tool_bundle_diff(f, base_commit, target_commit, root=base))
        )
    ]

    impacted_agents: set[str] = set()
    impacted_tools: set[str] = set()
    global_impact = False
    reasons: dict[str, set[str]] = {}
    # Why a smoke run cannot clear this change (verdict FULL); empty -> SMOKE or NONE.
    full_reasons: list[str] = []

    for f in code_changed_files:
        m_agent = re.match(r"cxas_app/agents/([^/]+)/", f)
        if m_agent:
            agent_name = m_agent.group(1)
            impacted_agents.add(agent_name)
            for ve, data in eval_map.items():
                if agent_name in data.get("agents", []):
                    reasons.setdefault(ve, set()).add(f"agent:{agent_name} ({f})")
            continue

        # A tool's description and parameter schema are prompts too: smoke the evals that
        # use the tool. A tool the impact map has never seen (new or renamed) needs a full run.
        m_tool = re.match(r"cxas_app/tools/([^/]+)/", f)
        if m_tool:
            tool_name = m_tool.group(1)
            impacted_tools.add(tool_name)
            users = [ve for ve, data in eval_map.items() if tool_name in data.get("tools", [])]
            if not users:
                full_reasons.append(f"tool {tool_name} is not in the impact map (new or renamed tool) ({f})")
            for ve in users:
                reasons.setdefault(ve, set()).add(f"tool:{tool_name} ({f})")
            continue

        if f in ("cxas_app/global_instruction.txt", "cxas_app/app.json"):
            global_impact = True
            full_reasons.append(f"{f} changed (every evaluation reads it)")
            for ve in eval_map:
                reasons.setdefault(ve, set()).add(f"global ({f})")
            continue

        if f.endswith("lib/speech.py") or f.endswith("lib/replies.py"):
            global_impact = True
            full_reasons.append(f"shared {f} changed (every tool or callback uses it)")
            for ve in eval_map:
                reasons.setdefault(ve, set()).add(f"global_lib ({f})")
            continue

        if f.endswith("lib/services.py"):
            syms = get_changed_python_symbols(f, base_commit, target_commit, root=base)
            if "ALL" in syms:
                global_impact = True
                full_reasons.append(f"{f} changed outside a single tool function")
                for ve in eval_map:
                    reasons.setdefault(ve, set()).add("services:ALL")
            else:
                for sym in syms:
                    if sym.endswith("_impl"):
                        tool_name = sym[: -len("_impl")]
                        impacted_tools.add(tool_name)
                        if tool_name in CORE_LOGIN_TOOLS:
                            full_reasons.append(f"login tool {tool_name} changed ({f}:{sym})")
                        for ve, data in eval_map.items():
                            if tool_name in data.get("tools", []):
                                reasons.setdefault(ve, set()).add(
                                    f"tool:{tool_name} (services.py:{sym})"
                                )
                    else:
                        global_impact = True
                        full_reasons.append(f"shared helper {sym} in {f} changed")
                        for ve in eval_map:
                            reasons.setdefault(ve, set()).add(f"services_helper:{sym}")
            continue

        if f.endswith("lib/fakes.py"):
            syms = get_changed_python_symbols(f, base_commit, target_commit, root=base)
            if "ALL" in syms:
                global_impact = True
                full_reasons.append(f"{f} changed outside a single constant or function")
                for ve in eval_map:
                    reasons.setdefault(ve, set()).add("fakes:ALL")
            else:
                for sym in syms:
                    if sym in CORE_SHARED_FAKES:
                        full_reasons.append(f"shared login or account data {sym} in {f} changed")
                    mapped_tools = const_to_tools.get(sym, STARTER_DEFAULT_TOOLS)
                    for tool_name in mapped_tools:
                        impacted_tools.add(tool_name)
                        for ve, data in eval_map.items():
                            if tool_name in data.get("tools", []):
                                reasons.setdefault(ve, set()).add(
                                    f"fakes:{sym}->tool:{tool_name}"
                                )
            continue

    directly_impacted = sorted(reasons.keys())

    # Canary selection: up to 1 per agent + 1 non-English eval
    canaries: set[str] = set()
    if code_changed_files and eval_map:
        agents_covered: set[str] = set()
        for ve in directly_impacted:
            for ag in eval_map.get(ve, {}).get("agents", []):
                agents_covered.add(ag)

        all_agents = {
            ag
            for info in eval_map.values()
            for ag in info.get("agents", [])
            if ag != "router"
        }
        if not all_agents:
            all_agents = {"router"}

        for ag in sorted(all_agents):
            if ag not in agents_covered:
                for ve, data in sorted(eval_map.items()):
                    if ag in data.get("agents", []) and data.get("last_pass_rate") == "3/3":
                        canaries.add(ve)
                        reasons.setdefault(ve, set()).add(f"canary:agent_{ag}")
                        break

        non_en_covered = any(
            eval_map.get(ve, {}).get("language", "en") != "en"
            for ve in (set(directly_impacted) | canaries)
        )
        if not non_en_covered:
            for ve, data in sorted(eval_map.items()):
                if data.get("language", "en") != "en" and data.get("last_pass_rate") == "3/3":
                    canaries.add(ve)
                    reasons.setdefault(ve, set()).add("canary:non_en")
                    break

    must_smoke = sorted(set(directly_impacted) | canaries)
    if code_changed_files and eval_map and set(eval_map) <= set(directly_impacted):
        full_reasons.append(f"all {len(eval_map)} evaluations are directly impacted")
    full_reasons = list(dict.fromkeys(full_reasons))
    verdict = "FULL" if full_reasons else ("SMOKE" if must_smoke else "NONE")
    fingerprint = source_fingerprint(root=base)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_commit": base_commit,
        "target_commit": target_commit or "WORKING_TREE",
        "source_fingerprint": fingerprint,
        "working_tree_fingerprint": fingerprint,
        "verdict": verdict,
        "verdict_reasons": full_reasons,
        "changed_files": changed_files,
        "code_changed_files": code_changed_files,
        "global_impact": global_impact,
        "impacted_agents": sorted(impacted_agents),
        "impacted_tools": sorted(impacted_tools),
        "directly_impacted_count": len(directly_impacted),
        "directly_impacted": directly_impacted,
        "canaries": sorted(canaries),
        "must_smoke_count": len(must_smoke),
        "must_smoke": must_smoke,
        "reasons": {k: sorted(v) for k, v in sorted(reasons.items())},
        "smoke_verified": len(must_smoke) == 0,
        "smoke_results": {},
    }

    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _eval_strict_passed_and_errors(
    ve: str,
    res: dict[str, Any],
    top_smoke_gate: dict[str, Any] | None = None,
) -> tuple[bool, int, int, list[str]]:
    """Determine (strict_3_of_3_passed, pass_runs, total_runs, tool_errors) for one eval."""
    tool_errors: list[str] = []

    if isinstance(top_smoke_gate, dict):
        for err in top_smoke_gate.get("unexpected_tool_errors") or []:
            if isinstance(err, dict) and err.get("eval") in (ve, None):
                tool_errors.append(str(err))
            elif isinstance(err, str) and ve in err:
                tool_errors.append(err)
        per_eval = (top_smoke_gate.get("per_eval") or {}).get(ve)
        if isinstance(per_eval, dict):
            pr = int(per_eval.get("pass_runs", 0))
            tr = int(per_eval.get("total_runs", 3))
            for err in per_eval.get("unexpected_tool_errors") or []:
                tool_errors.append(str(err))
            return (pr == tr and tr > 0 and not tool_errors), pr, tr, tool_errors

    for err in res.get("unexpected_tool_errors") or res.get("unexpected_errors") or []:
        tool_errors.append(str(err))
    try:
        if int(res.get("tool_errors") or 0) > 0:
            tool_errors.append(f"tool_errors={res['tool_errors']}")
    except (TypeError, ValueError):
        pass

    for tv in res.get("tool_vector") or res.get("tool_Vector") or []:
        tv_str = str(tv)
        if any(
            tok in tv_str
            for tok in ("ERROR", "SYSTEM_DOWN", "INTERNAL_ERROR", "AUTH_SERVICE_UNAVAILABLE")
        ):
            tool_errors.append(tv_str)

    for conv in res.get("conversations") or []:
        if not isinstance(conv, dict):
            continue
        for t in conv.get("tools") or []:
            t_str = str(t)
            if any(
                tok in t_str
                for tok in ("ERROR", "SYSTEM_DOWN", "INTERNAL_ERROR", "AUTH_SERVICE_UNAVAILABLE")
            ):
                tool_errors.append(t_str)

    total_runs = int(res.get("total_runs", res.get("runs", 3)) or 3)
    if "pass_runs" in res and res["pass_runs"] is not None:
        pass_runs = int(res["pass_runs"])
    elif isinstance(res.get("passed"), int) and not isinstance(res.get("passed"), bool):
        pass_runs = int(res["passed"])
    elif res.get("smoke_gate") == "PASS" or res.get("strict_pass") is True:
        pass_runs = total_runs
    else:
        pass_runs = 0

    if res.get("smoke_gate") == "FAIL" or res.get("strict_pass") is False:
        strict_ok = False
    elif res.get("smoke_gate") == "PASS":
        strict_ok = (pass_runs == total_runs and total_runs > 0)
    else:
        strict_ok = (pass_runs == total_runs and total_runs > 0)

    return (strict_ok and not tool_errors), pass_runs, total_runs, tool_errors


def record_smoke_results(
    smoke_json_path: str | Path,
    root: Path | None = None,
    dirs: Any = None,
    env: str = "staging",
) -> bool:
    """Record smoke run results into history/last_impact.json and append to history/impact_gate.log."""
    base = root or ROOT
    last_path = base / "history" / "last_impact.json"
    log_path = base / "history" / "impact_gate.log"

    if not last_path.exists():
        base_commit = get_last_full_run_commit(root=base) or "HEAD"
        analyze_impact(base_commit, root=base)

    impact = json.loads(last_path.read_text(encoding="utf-8"))
    spath = Path(smoke_json_path)
    if not spath.exists():
        print(f"ERROR: Smoke results file not found: {spath}", file=sys.stderr)
        return False

    smoke_data = json.loads(spath.read_text(encoding="utf-8"))
    top_smoke_gate = smoke_data.get("smoke_gate") if isinstance(smoke_data, dict) else None

    results_by_eval: dict[str, dict[str, Any]] = {}
    raw_results = smoke_data.get("results", {})
    if isinstance(raw_results, dict):
        for k, v in raw_results.items():
            if isinstance(v, dict):
                results_by_eval[str(k)] = v
    elif isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, dict):
                eid = str(
                    item.get("display_name")
                    or item.get("eval_id")
                    or item.get("name")
                    or ""
                )
                if eid:
                    results_by_eval[eid] = item

    smoke_results: dict[str, dict[str, Any]] = impact.get("smoke_results", {})
    for ve, res in results_by_eval.items():
        strict_ok, pass_runs, total_runs, tool_errors = _eval_strict_passed_and_errors(
            ve, res, top_smoke_gate=top_smoke_gate
        )
        smoke_results[ve] = {
            "passed": pass_runs,
            "pass_runs": pass_runs,
            "total": total_runs,
            "total_runs": total_runs,
            "strict_pass": strict_ok,
            "rate": res.get("pass_rate", f"{pass_runs}/{total_runs}"),
            "tool_errors": tool_errors,
            "source_file": str(spath),
        }

    impact["smoke_results"] = smoke_results

    must_smoke = impact.get("must_smoke", [])
    all_verified = True
    failed_evals: list[str] = []

    if isinstance(top_smoke_gate, dict) and top_smoke_gate.get("gate_verdict") in ("no-go", "FAIL"):
        all_verified = False

    for ve in must_smoke:
        sr = smoke_results.get(ve)
        if not sr:
            all_verified = False
            failed_evals.append(f"{ve} (NOT RUN)")
        elif not sr.get("strict_pass"):
            all_verified = False
            if sr.get("tool_errors"):
                failed_evals.append(f"{ve} (TOOL ERROR: {sr['tool_errors']})")
            else:
                failed_evals.append(f"{ve} ({sr.get('passed', 0)}/{sr.get('total', 3)} < 3/3)")

    impact["smoke_verified"] = all_verified
    impact["verified_at"] = datetime.now(timezone.utc).isoformat()
    impact["verified_fingerprint"] = source_fingerprint(root=base, dirs=dirs)
    impact["verified_commit"] = head_sha7(base)
    last_path.write_text(json.dumps(impact, indent=2) + "\n", encoding="utf-8")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    status_str = "PASS (3/3 on all impacted + canaries)" if all_verified else f"FAIL ({', '.join(failed_evals)})"
    log_entry = (
        f"[{impact['verified_at']}] base={impact['base_commit']} "
        f"commit={impact['verified_commit']} fingerprint={impact['verified_fingerprint']} "
        f"files={len(impact.get('code_changed_files', []))} "
        f"must_smoke={len(must_smoke)} source={spath.name} status={status_str}\n"
    )
    with log_path.open("a", encoding="utf-8") as f:
        f.write(log_entry)

    if all_verified:
        print(
            f"SMOKE GATE PASSED: All {len(must_smoke)} impacted/canary evals passed 3/3 "
            f"(recorded for source fingerprint {impact['verified_fingerprint']}). "
            f"Next: make bench-full ENV={env}"
        )
    else:
        print(f"SMOKE GATE FAILED: {failed_evals}", file=sys.stderr)
        print(
            f"Read the failing conversations under {spath.parent}/failing_runs_data/{spath.stem}/, "
            f"fix the cause, commit, then run: make push ENV={env} && make smoke-impact ENV={env}",
            file=sys.stderr,
        )
    return all_verified


def check_smoke_gate(root: Path | None = None, dirs: Any = None, env: str = "staging") -> bool:
    """The smoke part of the `make bench-full` gate (see check_bench_full_gate).

    Allowed when one of these holds:
      - no baseline full run or no history/eval_impact_map.json yet (first full run,
        fresh clone, CI runner);
      - cxas_app/, lib/ and evals/ are unchanged since the last full run;
      - a passing smoke is recorded for the current source fingerprint;
      - the impact verdict is FULL (a smoke run cannot clear the change);
      - 0 evaluations are impacted (nothing to smoke).
    """
    base = root or ROOT
    folders = _norm_dirs(dirs)
    map_path = base / "history" / "eval_impact_map.json"
    last_path = base / "history" / "last_impact.json"

    base_commit = get_last_full_run_commit(root=base)
    if not map_path.exists() or base_commit is None:
        print(
            "Impact Gate: No baseline full run or history/eval_impact_map.json found "
            "(first full run, fresh clone or CI runner); allowed."
        )
        return True

    curr_fp = source_fingerprint(root=base, dirs=folders)
    base_fp = fingerprint_at(base_commit, base, folders)
    if base_fp is None:
        print(
            f"Impact Gate: the last full run's commit {base_commit} is not in this clone (shallow "
            "checkout?), so changes since then cannot be mapped; allowed (treated like a first full run)."
        )
        return True
    if base_fp == curr_fp:
        print(
            f"Impact Gate: {_dirs_text(folders, 'and')} are unchanged since the last full run "
            f"({base_commit}); allowed."
        )
        return True

    last = _read_json(last_path) if last_path.exists() else None
    if (
        isinstance(last, dict)
        and last.get("base_commit") == base_commit
        and last.get("verified_fingerprint") == curr_fp
        and last.get("smoke_verified") is True
    ):
        print(
            f"Impact Gate: VERIFIED (base={base_commit}, "
            f"must_smoke={last.get('must_smoke_count', 0)} evals passed 3/3)."
        )
        return True

    impact = analyze_impact(base_commit, root=base)
    if impact.get("verdict") == "FULL":
        print(
            f"Impact Gate: verdict FULL ({'; '.join(impact['verdict_reasons'][:3])}); a smoke run "
            "cannot clear this change, so the full run is the next step; allowed."
        )
        return True
    if impact["must_smoke_count"] == 0:
        print(f"Impact Gate: 0 code changes since last full run ({base_commit}); nothing to smoke; allowed.")
        return True

    rule = "=================================================================="
    _eprint(
        rule,
        "STOP: run `make smoke-impact` before `make bench-full`",
        rule,
        f"Changes since the last full run ({base_commit}):",
        *[f"  - {f}" for f in impact["code_changed_files"]],
        "",
        f"Evaluations that must pass 3/3 in a smoke run first ({impact['must_smoke_count']}):",
        *[f"  * {ve}  [{', '.join(impact['reasons'].get(ve, []))}]" for ve in impact["must_smoke"]],
        "",
        "Next:",
        f"  make smoke-impact ENV={env}",
        "Skip the smoke run only with a reason (it is written to history/impact_gate.log):",
        f'  make bench-full ENV={env} SKIP_SMOKE_GATE=1 REASON="why"',
        rule,
    )
    return False


# Old name: before push -> smoke -> record, this gate ran in front of `make push`.
check_push_gate = check_smoke_gate


# ----------------------------------------------------------------------------- push / deployed / bench-full / holdout gates


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _eprint(*lines: str) -> None:
    for line in lines:
        print(line, file=sys.stderr)


def _dirs_text(folders: tuple[str, ...], conj: str = "or") -> str:
    """("cxas_app", "lib", "evals") -> "cxas_app/, lib/ or evals/"."""
    names = [f"{d}/" for d in folders]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" {conj} " + names[-1]


def _log_gate(root: Path, text: str) -> None:
    path = root / "history" / "impact_gate.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{_utc_now()}] {text}\n")


def require_clean_source(
    root: Path | None = None,
    dirs: Any = None,
    env: str = "staging",
    action: str = "make push",
) -> bool:
    """`make push` refuses uncommitted changes in the source folders ("commit first")."""
    base = root or ROOT
    folders = _norm_dirs(dirs)
    if source_fingerprint(base, folders) == "nogit":
        _eprint(
            f"{action}: this folder is not a git repository, so there is no commit to push. "
            'Run: git init && git add -A && git commit -m "first version", '
            f"then run: make push ENV={env}"
        )
        return False
    dirty = source_dirty_files(base, folders)
    if not dirty:
        return True
    _eprint(
        f"{action}: refusing to push: {_dirs_text(folders, 'and')} have uncommitted changes:",
        *[f"  {line}" for line in dirty[:20]],
        *([f"  ... and {len(dirty) - 20} more"] if len(dirty) > 20 else []),
        "The app version is named after the commit (git-<sha7>) and every result is recorded",
        "per commit, so commit first:",
        f'  git add {" ".join(folders)} && git commit -m "<what changed>"',
        f"then run: make push ENV={env}",
    )
    return False


def record_push(app: str, version: str, root: Path | None = None, dirs: Any = None) -> dict[str, Any]:
    """Write history/last_push.json after a successful push: which commit the app now runs."""
    base = root or ROOT
    path = base / "history" / "last_push.json"
    app = str(app or "").rstrip("/")
    entry = {
        "commit": head_sha7(base),
        "source_fingerprint": source_fingerprint(base, dirs),
        "app": app,
        "version": version,
        "pushed_at": _utc_now(),
    }
    old = _read_json(path)
    by_app: dict[str, Any] = {}
    if isinstance(old, dict) and isinstance(old.get("by_app"), dict):
        by_app = dict(old["by_app"])
    by_app[app] = {k: v for k, v in entry.items() if k != "app"}
    data = {**entry, "by_app": by_app}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"Recorded the push in history/last_push.json: {app or 'the app'} runs commit "
        f"{entry['commit']} as {version} (source fingerprint {entry['source_fingerprint']})."
    )
    return data


def last_push_for(app: str | None, root: Path | None = None) -> dict[str, Any] | None:
    """The recorded push for `app` (or the most recent push when `app` is empty)."""
    base = root or ROOT
    data = _read_json(base / "history" / "last_push.json")
    if not isinstance(data, dict):
        return None
    app = str(app or "").rstrip("/")
    if not app:
        return data
    by_app = data.get("by_app")
    if isinstance(by_app, dict) and isinstance(by_app.get(app), dict):
        return {**by_app[app], "app": app}
    if str(data.get("app") or "").rstrip("/") == app:
        return data
    return None


def check_deployed(
    app: str | None,
    root: Path | None = None,
    dirs: Any = None,
    env: str = "staging",
    action: str = "this command",
) -> tuple[bool, str]:
    """(ok, message): `app` runs exactly this checkout's committed source folders."""
    base = root or ROOT
    folders = _norm_dirs(dirs)
    current = source_fingerprint(base, folders)
    if current == "nogit":
        return False, (
            f"{action}: this folder is not a git repository; the gates compare commits. "
            'Run: git init && git add -A && git commit -m "first version", '
            f"then make push ENV={env}"
        )
    dirty = source_dirty_files(base, folders)
    if dirty:
        listing = "\n".join(f"  {line}" for line in dirty[:10])
        return False, (
            f"{action}: {_dirs_text(folders, 'and')} have uncommitted changes, so the app cannot "
            f"be running this checkout:\n{listing}\n"
            f'Commit and push first: git add {" ".join(folders)} && git commit -m "<what changed>" '
            f"&& make push ENV={env}"
        )
    pushed = last_push_for(app, base)
    where = str(app or "").rstrip("/") or "the app"
    if not pushed:
        return False, (
            f"{action}: no push to {where} is recorded in history/last_push.json, so nothing shows "
            f"the app runs this commit ({head_sha7(base)}). Push this commit first: make push ENV={env}"
        )
    if pushed.get("source_fingerprint") != current:
        return False, (
            f"{action}: {where} runs commit {pushed.get('commit')} ({pushed.get('version')}, pushed "
            f"{pushed.get('pushed_at')}), but {_dirs_text(folders)} changed since then (source "
            f"fingerprint {pushed.get('source_fingerprint')} -> {current}). "
            f"Push this commit first: make push ENV={env}"
        )
    return True, (
        f"Deployed check: {where} runs this checkout (pushed as {pushed.get('version')} from commit "
        f"{pushed.get('commit')}; source fingerprint {current})."
    )


def record_nothing_to_smoke(impact: dict[str, Any], root: Path | None = None, dirs: Any = None) -> None:
    """Record a passing smoke for a change that impacts 0 evaluations."""
    base = root or ROOT
    data = dict(impact)
    data.update(
        {
            "smoke_verified": True,
            "smoke_results": {},
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "verified_fingerprint": source_fingerprint(base, dirs),
            "verified_commit": head_sha7(base),
        }
    )
    last_path = base / "history" / "last_impact.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    log_path = base / "history" / "impact_gate.log"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"[{data['verified_at']}] base={data.get('base_commit')} commit={data['verified_commit']} "
            f"fingerprint={data['verified_fingerprint']} files={len(data.get('code_changed_files', []))} "
            "must_smoke=0 source=none status=PASS (0 impacted evaluations; nothing to smoke)\n"
        )


def smoke_plan(
    app: str | None,
    base_commit: str | None = None,
    root: Path | None = None,
    dirs: Any = None,
    env: str = "staging",
) -> tuple[int, str]:
    """What `make smoke-impact` runs: (exit code, comma-separated eval ids to smoke).

    1: refused (the app does not run this checkout). 2: verdict FULL, run make bench-full.
    0 with ids: smoke them 3 times, then --record-smoke. 0 without ids: nothing to run
    (no baseline full run yet, or 0 impacted evals, recorded as a pass).
    """
    base = root or ROOT
    ok, msg = check_deployed(app, base, dirs, env, action="make smoke-impact")
    _eprint(msg)  # stdout carries only the eval ids
    if not ok:
        return 1, ""
    full_commit = base_commit or get_last_full_run_commit(root=base)
    if full_commit is None:
        _eprint(
            "make smoke-impact: no full run is recorded yet (history/bench/full-*.json), so there is "
            "nothing to compare this change against. The first full run is allowed without a smoke "
            f"run. Next: make bench-full ENV={env}"
        )
        return 0, ""
    if fingerprint_at(full_commit, base, dirs) is None:
        reason = f"the base commit {full_commit} is not in this clone"
        last_path = base / "history" / "last_impact.json"
        last_path.parent.mkdir(parents=True, exist_ok=True)
        last_path.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "base_commit": full_commit,
                    "verdict": "FULL",
                    "verdict_reasons": [reason],
                    "must_smoke": [],
                    "must_smoke_count": 0,
                    "smoke_verified": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _eprint(
            f"make smoke-impact: {reason} (a shallow checkout needs `git fetch --unshallow`), so the "
            f"change cannot be mapped to evaluations. Run: make bench-full ENV={env}"
        )
        return 2, ""
    impact = analyze_impact(full_commit, root=base)
    if impact["verdict"] == "FULL":
        _eprint(
            f"make smoke-impact: verdict FULL: {'; '.join(impact['verdict_reasons'][:3])}. A smoke run "
            "of a few evaluations cannot clear a change that every evaluation depends on. "
            f"Run: make bench-full ENV={env}"
        )
        return 2, ""
    if not impact["must_smoke"]:
        record_nothing_to_smoke(impact, base, dirs)
        _eprint(
            f"make smoke-impact: 0 evaluations are impacted since the last full run ({full_commit}); "
            f"recorded a pass for this source fingerprint. Next: make bench-full ENV={env}"
        )
        return 0, ""
    n = impact["must_smoke_count"]
    _eprint(
        f"make smoke-impact: smoking {n} evaluation{'s' if n != 1 else ''} x 3 (impacted since the "
        f"full run on {full_commit}, plus canaries):",
        *[f"  * {ve}  [{', '.join(impact['reasons'].get(ve, []))}]" for ve in impact["must_smoke"]],
    )
    return 0, ",".join(impact["must_smoke"])


def check_bench_full_gate(
    app: str | None,
    bench_dir: str = "bench",
    skip: bool = False,
    reason: str = "",
    root: Path | None = None,
    dirs: Any = None,
    env: str = "staging",
) -> bool:
    """`make bench-full`: refuse unless the app runs this checkout, then require
    check_smoke_gate unless SKIP_SMOKE_GATE=1 comes with a logged REASON."""
    _ = bench_dir
    base = root or ROOT
    ok, msg = check_deployed(app, base, dirs, env, action="make bench-full")
    if not ok:
        _eprint(msg)
        return False
    print(msg)
    if skip:
        why = " ".join(str(reason or "").split())
        if not why:
            _eprint(
                "make bench-full: SKIP_SMOKE_GATE=1 needs a reason, which is written to "
                f'history/impact_gate.log. Run: make bench-full ENV={env} SKIP_SMOKE_GATE=1 REASON="why the smoke run is skipped"'
            )
            return False
        _log_gate(
            base,
            f"OVERRIDE bench-full commit={head_sha7(base)} fingerprint={source_fingerprint(base, dirs)} "
            f"app={str(app or '').rstrip('/')} reason={why}",
        )
        print("Smoke gate skipped with SKIP_SMOKE_GATE=1; the reason is logged in history/impact_gate.log.")
        return True
    return check_smoke_gate(base, dirs, env)


def find_full_record(root: Path | None = None, dirs: Any = None) -> Path | None:
    """The full-run record that measured HEAD's source.

    history/bench/full-<HEAD sha7>.json when it exists; otherwise the newest
    history/bench/full-*.json whose commit has the same source fingerprint as HEAD
    (only docs or history were committed since, for example the record itself).
    """
    base = root or ROOT
    bench = base / "history" / "bench"
    exact = bench / f"full-{head_sha7(base)}.json"
    if exact.is_file():
        return exact
    current = source_fingerprint(base, dirs)
    if current == "nogit" or "+dirty" in current or not bench.is_dir():
        return None
    for path in sorted(bench.glob("full-*.json"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        commit = str(data.get("commit") or data.get("git_sha") or "")
        if commit and fingerprint_at(commit, base, dirs) == current:
            return path
    return None


def _run_self_test() -> int:
    import contextlib
    import io

    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        root = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)

        # Create minimal workspace
        lib_dir = root / "cxas_app" / "python_code" / "lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "fakes.py").write_text(
            'ACCOUNTS = {"ACC-1001": {"phone": "2025550143"}}\n'
            'VALID_PINS = frozenset({"1234", "5678"})\n',
            encoding="utf-8",
        )
        (lib_dir / "services.py").write_text(
            "from lib.fakes import ACCOUNTS, VALID_PINS\n"
            "def lookup_account_impl(x):\n"
            "    return ACCOUNTS.get(x)\n"
            "def check_login_code_impl(code):\n"
            "    return code in VALID_PINS\n",
            encoding="utf-8",
        )
        agent_dir = root / "cxas_app" / "agents" / "router"
        agent_dir.mkdir(parents=True)
        (agent_dir / "instruction.txt").write_text("Route the caller.\n", encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)
        base_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # First-push bootstrap check before any full run or impact map exists
        assert check_push_gate(root=root) is True

        # Create baseline full run and impact map
        bench_dir = root / "history" / "bench"
        bench_dir.mkdir(parents=True)
        (bench_dir / "full-20260101-000000Z.json").write_text(
            json.dumps(
                {
                    "git_sha": base_sha,
                    "commits": [base_sha],
                    "app_versions_seen": ["v1"],
                    "is_full_run": True,
                    "is_holdout": False,
                    "eval_count": 2,
                    "results": [
                        {
                            "display_name": "sim_account_lookup",
                            "pass_runs": 3,
                            "total_runs": 3,
                            "tool_vector": ["lookup_account:OK"],
                        },
                        {
                            "display_name": "sim_login_verification",
                            "pass_runs": 3,
                            "total_runs": 3,
                            "tool_vector": ["check_login_code:OK"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        build_impact_map(root=root)
        assert get_last_full_run_commit(root=root) == base_sha

        # Modify router instruction and verify impact detection
        (agent_dir / "instruction.txt").write_text("Updated router prompt.\n", encoding="utf-8")
        impact = analyze_impact(base_sha, root=root)
        assert "sim_account_lookup" in impact["must_smoke"]

        # Record passing 3/3 smoke run (with boolean passed=True and pass_runs=3)
        smoke_file = bench_dir / "smoke-20260101-010000Z.json"
        smoke_file.write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "display_name": "sim_account_lookup",
                            "passed": True,
                            "pass_runs": 3,
                            "total_runs": 3,
                            "smoke_gate": "PASS",
                        },
                        {
                            "display_name": "sim_login_verification",
                            "passed": True,
                            "pass_runs": 3,
                            "total_runs": 3,
                            "smoke_gate": "PASS",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert record_smoke_results(smoke_file, root=root) is True
        assert (root / "history" / "impact_gate.log").is_file()
        assert not (root / "docs" / "experiment_log.md").exists()

    _gates_self_test()
    print("impact.py self-test: PASSED")
    return 0


def _git_commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


def _gates_self_test() -> None:
    """push -> smoke -> record: fingerprint, deployed check, bench-full gate, find_full_record."""
    import contextlib
    import io

    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        root = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
        (root / "cxas_app").mkdir()
        (root / "cxas_app" / "app.json").write_text("{}\n", encoding="utf-8")
        (root / "lib").mkdir()
        (root / "lib" / "fakes.py").write_text("X = 1\n", encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs" / "notes.md").write_text("v1\n", encoding="utf-8")
        _git_commit_all(root, "base")
        app = "projects/p/locations/us/apps/a1"

        # A docs-only commit keeps the source fingerprint; an uncommitted source edit marks it dirty.
        fp = source_fingerprint(root)
        (root / "docs" / "notes.md").write_text("v2\n", encoding="utf-8")
        _git_commit_all(root, "docs only")
        assert source_fingerprint(root) == fp
        (root / "lib" / "fakes.py").write_text("X = 2\n", encoding="utf-8")
        assert "+dirty." in source_fingerprint(root)
        assert require_clean_source(root) is False
        _git_commit_all(root, "source change")
        assert require_clean_source(root) is True
        assert source_fingerprint(root) != fp

        # Deployed check: nothing pushed, pushed to another app, pushed here.
        assert check_deployed(app, root)[0] is False
        record_push("projects/p/locations/us/apps/other", "git-x", root)
        assert check_deployed(app, root)[0] is False
        record_push(app, "git-y", root)
        assert check_deployed(app, root)[0] is True
        assert smoke_plan(app, root=root) == (0, "")  # no baseline full run: first full run allowed

        # bench-full gate: bootstrap allowed, override needs a reason.
        assert check_bench_full_gate(app, "bench", root=root) is True
        assert check_bench_full_gate(app, "bench", skip=True, reason=" ", root=root) is False
        assert check_bench_full_gate(app, "bench", skip=True, reason="quota", root=root) is True
        assert "OVERRIDE bench-full" in (root / "history" / "impact_gate.log").read_text(encoding="utf-8")

        # find_full_record matches HEAD or a docs-only commit with the same source fingerprint.
        assert find_full_record(root) is None
        sha7 = head_sha7(root)
        record = {
            "label": f"full-{sha7}",
            "commit": sha7,
            "is_full_run": True,
            "runs_per_eval": 3,
            "tool_errors": 0,
            "per_eval": {f"VE-{n:02d}": {"pass": 3, "total": 3, "verdict": "PASS"} for n in range(1, 11)},
        }
        (root / "history" / "bench").mkdir(parents=True, exist_ok=True)
        full_file = root / "history" / "bench" / f"full-{sha7}.json"
        full_file.write_text(json.dumps(record), encoding="utf-8")
        assert find_full_record(root) == full_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Change-to-eval impact analyzer and the push -> smoke -> record gates"
    )
    parser.add_argument("--base", help="Base commit (defaults to commit of last full 70-eval run)")
    parser.add_argument("--target", help="Target commit (defaults to working tree)")
    parser.add_argument("--build-map", action="store_true", help="Rebuild history/eval_impact_map.json")
    parser.add_argument(
        "--targets-only",
        "--print-evals",
        dest="print_evals",
        action="store_true",
        help="Print only space-separated must_smoke eval IDs",
    )
    parser.add_argument("--record-smoke", help="Record smoke run results from JSON file")
    parser.add_argument(
        "--check-bench-full",
        "--check-smoke",
        "--check-push",
        dest="check_bench_full",
        action="store_true",
        help="make bench-full gate: the app runs this checkout and a smoke passed "
        "(--check-smoke and --check-push are the old names)",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="make push: refuse uncommitted changes in the source folders",
    )
    parser.add_argument(
        "--record-push",
        action="store_true",
        help="make push: write history/last_push.json (needs --app and --version-name)",
    )
    parser.add_argument("--version-name", default="", help="App version that was pushed, e.g. git-<sha7>")
    parser.add_argument(
        "--check-deployed",
        action="store_true",
        help="Exit 0 only when --app runs this checkout (source fingerprint of the last push)",
    )
    parser.add_argument(
        "--smoke-plan",
        action="store_true",
        help="make smoke-impact: print the eval ids to smoke (exit 1 refused, 2 verdict FULL)",
    )
    parser.add_argument("--source-fingerprint", action="store_true", help="Print the source fingerprint")
    parser.add_argument(
        "--full-record",
        action="store_true",
        help="Print the full-run record that measured HEAD's source (exit 1 when there is none)",
    )
    parser.add_argument("--app", default="", help="App resource: projects/<p>/locations/<l>/apps/<id>")
    parser.add_argument("--env", default="staging", help="ENV name used in the 'run this next' hints")
    parser.add_argument(
        "--source-dirs",
        default=",".join(SOURCE_DIRS),
        help="Folders of the source fingerprint (default: cxas_app,lib,evals)",
    )
    parser.add_argument("--bench-dir", default="bench", help="BENCH_DIR of the full run")
    parser.add_argument(
        "--skip-smoke-gate",
        action="store_true",
        help="SKIP_SMOKE_GATE=1: skip the smoke requirement of --check-bench-full (needs --reason)",
    )
    parser.add_argument("--reason", default="", help="Why a gate is overridden (written to a log)")
    parser.add_argument("--self-test", action="store_true", help="Run built-in unit self-tests")
    args = parser.parse_args(argv)
    dirs = _norm_dirs(args.source_dirs)
    try:  # keep stdout and stderr lines in order when both go to a log
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    if args.self_test:
        return _run_self_test()

    if args.build_map:
        m = build_impact_map()
        print(f"Built impact map with {m['eval_count']} evals at {IMPACT_MAP_PATH}")
        return 0

    if args.source_fingerprint:
        print(source_fingerprint(dirs=dirs))
        return 0

    if args.full_record:
        found = find_full_record(dirs=dirs)
        if found is None:
            return 1
        print(found.relative_to(ROOT) if found.is_relative_to(ROOT) else found)
        return 0

    if args.require_clean:
        return 0 if require_clean_source(dirs=dirs, env=args.env) else 1

    if args.record_push:
        record_push(args.app, args.version_name or f"git-{head_sha7()}", dirs=dirs)
        return 0

    if args.check_deployed:
        ok, msg = check_deployed(args.app, dirs=dirs, env=args.env)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.smoke_plan:
        code, targets = smoke_plan(args.app, base_commit=args.base, dirs=dirs, env=args.env)
        if targets:
            print(targets)
        return code

    if args.record_smoke:
        ok = record_smoke_results(args.record_smoke, dirs=dirs, env=args.env)
        return 0 if ok else 1

    if args.check_bench_full:
        ok = check_bench_full_gate(
            args.app,
            bench_dir=args.bench_dir,
            skip=args.skip_smoke_gate,
            reason=args.reason,
            dirs=dirs,
            env=args.env,
        )
        return 0 if ok else 1

    base = args.base or get_last_full_run_commit() or "HEAD"
    res = analyze_impact(base, args.target)
    if args.print_evals:
        print(" ".join(res["must_smoke"]))
    else:
        print(f"Impact Analysis (base={res['base_commit']} -> target={res['target_commit']}):")
        print(f"  Code files changed ({len(res['code_changed_files'])}): {res['code_changed_files']}")
        print(f"  Directly impacted evals ({res['directly_impacted_count']}): {res['directly_impacted']}")
        print(f"  Canaries selected ({len(res['canaries'])}): {res['canaries']}")
        print(f"  Total must_smoke ({res['must_smoke_count']}): {res['must_smoke']}")
        verdict_note = f" ({'; '.join(res['verdict_reasons'][:3])})" if res["verdict_reasons"] else ""
        print(f"  Verdict: {res['verdict']}{verdict_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
