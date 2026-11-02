#!/usr/bin/env python3
"""Locked, append-only writer for docs/cloud-log.md: one row per cloud call, with its outcome.

Every cloud command or API call (reads too) gets exactly one row, in the table format used since row 0:

  | <n> | <UTC start time> | `READ` | `<exact command or API method>` | `<target resource>` | <notes> — outcome: <outcome> |

Rules this module enforces:
- The row number is computed from the file while an exclusive ``fcntl.flock`` is held on docs/cloud-log.md
  itself (the same inode every writer appends to); the row is appended, flushed and fsynced before the lock
  is released. Other writers must lock the same file (scripts/run_bench.py does).
- A missing log, or a file without the cloud-activity table header, is an error: a cloud call must never go
  unrecorded silently.
- Rows are only appended; existing rows are never rewritten.
- The timestamp is the call's start time. The outcome is known only after the call, so the row is written
  then; with parallel calls, row numbers follow completion order.
- DD-17: a row that contains a visible eval's name is refused (names are read at run time from the bench
  index outside the repo, when that file exists). Use resource IDs instead.

Library use:
    from suite import cloud_log
    with cloud_log.logged_call("READ", "Evaluations.get_evaluation_run", run_name, "poll probe run") as call:
        run = client.get_evaluation_run(run_name)
        call.outcome = f"OK (state={run.state.name})"
    idx = cloud_log.append_row("READ", "Apps.list_apps", "projects/p/locations/us", "notes", "OK (3 apps)")

CLI:
    python suite/cloud_log.py append --op READ --method Apps.list_apps \\
        --target projects/<project>/locations/<location> --notes "after snapshot" --outcome "OK (3 apps)"
    python suite/cloud_log.py exec --op WRITE --target <app resource> --notes "push commit abc1234" -- cxas push ...
"""

import argparse
import contextlib
import errno
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = REPO_ROOT / "docs" / "cloud-log.md"
DEFAULT_EVAL_INDEX = Path(
    os.environ.get("CLOUD_LOG_EVAL_INDEX")
    or Path(os.environ.get("BENCH_DIR") or (REPO_ROOT / "bench")) / "dev" / "index.json"
)
TABLE_HEADER = re.compile(
    r"^\|\s*#\s*\|\s*UTC Timestamp\s*\|\s*Operation Type\s*\|\s*Command or API Method\s*\|"
    r"\s*Target Resource\s*\|\s*Notes\s*\|\s*$",
    re.MULTILINE,
)
ROW_INDEX = re.compile(r"^\|\s*(\d+)\s*\|")
OPERATIONS = ("READ", "WRITE")
MAX_OUTCOME_CHARS = 300


class CloudLogError(Exception):
    """The log cannot take the row (wrong file, bad input, or a forbidden term)."""


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cell(text: object) -> str:
    """Keep a cell on one line and inside its table column."""
    return " ".join(str(text).replace("`", "'").replace("|", "/").split())


def load_forbidden_terms(index_path: Path | None = DEFAULT_EVAL_INDEX) -> set[str]:
    """Visible-eval names (and their slugs without the `sim__` prefix), lower-cased; empty if no index."""
    if index_path is None or not Path(index_path).is_file():
        return set()
    entries = json.loads(Path(index_path).read_text(encoding="utf-8"))
    terms = set()
    for entry in entries:
        name = str(entry.get("name", "")).strip().lower()
        if not name:
            continue
        terms.add(name)
        slug = name.split("__", 1)[1] if "__" in name else name
        terms.add(slug)
    return terms


def next_index(text: str) -> int:
    """1 + the highest row number in the table (0 for an empty table)."""
    best = -1
    for line in text.splitlines():
        m = ROW_INDEX.match(line)
        if m:
            best = max(best, int(m.group(1)))
    return best + 1


def format_row(
    idx: int, ts: str, op: str, method: str, target: str, notes: str, outcome: str
) -> str:
    cell_notes = _cell(notes)
    cell_outcome = _cell(outcome)[:MAX_OUTCOME_CHARS]
    joined = (
        f"{cell_notes} — outcome: {cell_outcome}"
        if cell_notes
        else f"outcome: {cell_outcome}"
    )
    return f"| {idx} | {ts} | `{op}` | `{_cell(method)}` | `{_cell(target)}` | {joined} |\n"


def _validate(op: str, method: str, target: str, outcome: str) -> None:
    if op not in OPERATIONS:
        raise CloudLogError(f"operation must be one of {OPERATIONS}, got {op!r}")
    for label, value in (("method", method), ("target", target), ("outcome", outcome)):
        if not _cell(value or ""):
            raise CloudLogError(f"{label} must not be empty")


def _check_forbidden(row: str, forbidden: set[str]) -> None:
    lowered = row.lower()
    hits = sorted(t for t in forbidden if t and t in lowered)
    if hits:
        raise CloudLogError(
            f"row would contain {len(hits)} visible-eval name(s); log resource IDs instead (DD-17)"
        )


def _lock(fileobj, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fcntl.flock(fileobj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EACCES):
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"could not lock {fileobj.name} within {timeout_s}s"
                ) from exc
            time.sleep(0.05)


def append_row(
    op: str,
    method: str,
    target: str,
    notes: str,
    outcome: str,
    *,
    ts: str | None = None,
    log_path: Path | str | None = None,
    forbidden: set[str] | None = None,
    lock_timeout_s: float = 60.0,
) -> int:
    """Append one row for one cloud call; return its row number.

    Raises FileNotFoundError if the log is missing and CloudLogError if the file has no cloud-activity table,
    the input is invalid, or the row would name a visible eval.
    """
    path = Path(log_path or os.environ.get("CLOUD_LOG_PATH") or DEFAULT_LOG)
    terms = load_forbidden_terms() if forbidden is None else forbidden
    _validate(op, method, target, outcome)
    if not path.is_file():
        raise FileNotFoundError(
            f"cloud log missing: {path} (a cloud call must never go unrecorded)"
        )
    with open(path, "a+", encoding="utf-8") as f:
        _lock(f, lock_timeout_s)
        try:
            f.seek(0)
            text = f.read()
            if not TABLE_HEADER.search(text):
                raise CloudLogError(f"{path} has no cloud-activity table header")
            idx = next_index(text)
            row = format_row(idx, ts or now_iso(), op, method, target, notes, outcome)
            _check_forbidden(row, terms)
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write(row)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return idx


class CallRecord:
    """Handed to the body of `logged_call`; set `outcome` (e.g. "OK (run=<name>)") before leaving."""

    def __init__(self) -> None:
        self.outcome = "OK"
        self.idx: int | None = None


@contextlib.contextmanager
def logged_call(op: str, method: str, target: str, notes: str = "", **kwargs):
    """Log one cloud call with its start time and real outcome; errors are logged and re-raised.

    Everything known before the call (operation, method, target, notes, log file) is checked
    first, so a refusal happens before the cloud call, never after it.
    """
    if kwargs.get("forbidden") is None:
        kwargs["forbidden"] = load_forbidden_terms()
    _validate(op, method, target, "pending")
    _check_forbidden(f"{op} {method} {target} {notes}", kwargs["forbidden"])
    path = Path(
        kwargs.get("log_path") or os.environ.get("CLOUD_LOG_PATH") or DEFAULT_LOG
    )
    if not path.is_file():
        raise FileNotFoundError(
            f"cloud log missing: {path} (a cloud call must never go unrecorded)"
        )
    record = CallRecord()
    ts = now_iso()
    try:
        yield record
    except BaseException as exc:
        record.idx = _append_after_call(
            op, method, target, notes, f"ERROR {type(exc).__name__}: {exc}", ts, kwargs
        )
        raise
    record.idx = _append_after_call(
        op, method, target, notes, record.outcome, ts, kwargs
    )


def _append_after_call(op, method, target, notes, outcome, ts, kwargs) -> int:
    """The call already ran, so its row must land: if the outcome text is refused, log a placeholder."""
    try:
        return append_row(op, method, target, notes, outcome, ts=ts, **kwargs)
    except CloudLogError as exc:
        placeholder = f"outcome withheld by the log guard ({exc})"
        return append_row(op, method, target, notes, placeholder, ts=ts, **kwargs)


def _cmd_append(args) -> int:
    idx = append_row(
        args.op, args.method, args.target, args.notes, args.outcome, log_path=args.log
    )
    print(idx)
    return 0


def _cmd_exec(args) -> int:
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise CloudLogError("exec needs a command after --")
    target_log = Path(args.log or os.environ.get("CLOUD_LOG_PATH") or DEFAULT_LOG)
    if not target_log.is_file():
        raise FileNotFoundError(f"cloud log missing: {target_log}")
    ts = now_iso()
    outcome = "ERROR interrupted before the command exited"
    code = 2
    try:
        code = subprocess.run(cmd, check=False).returncode
        outcome = "OK exit=0" if code == 0 else f"FAILED exit={code}"
    except OSError as exc:
        outcome = f"ERROR {type(exc).__name__}: {exc}"
        code = 127
    finally:
        idx = append_row(
            args.op,
            shlex.join(cmd),
            args.target,
            args.notes,
            outcome,
            ts=ts,
            log_path=args.log,
        )
        print(f"cloud-log row {idx}: {outcome}", file=sys.stderr)
    return code


def _self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "cloud-log.md"
        log_file.write_text(
            "| # | UTC Timestamp | Operation Type | Command or API Method | Target Resource | Notes |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        idx = append_row(
            "READ",
            "Apps.list_apps",
            "projects/p/locations/us",
            "self-test",
            "OK (1 app)",
            log_path=log_file,
        )
        assert idx == 0, idx
        with logged_call(
            "WRITE",
            "Apps.push",
            "projects/p/locations/us/apps/a1",
            "push test",
            log_path=log_file,
        ) as call:
            call.outcome = "OK"
        assert call.idx == 1, call.idx
    print("OK (cloud_log self-test)")
    return 0


def main(argv=None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv_list:
        return _self_test()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--log", default=None, help=f"default: {DEFAULT_LOG}")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append", help="append one row for a call made elsewhere")
    a.add_argument("--op", required=True, choices=OPERATIONS)
    a.add_argument("--method", required=True, help="exact command or API method")
    a.add_argument("--target", required=True, help="target resource")
    a.add_argument("--notes", default="")
    a.add_argument("--outcome", required=True, help='e.g. "OK (3 apps)" or "ERROR ..."')
    e = sub.add_parser(
        "exec", help="run a command and log it (exact command line + exit code)"
    )
    e.add_argument("--op", required=True, choices=OPERATIONS)
    e.add_argument("--target", required=True)
    e.add_argument("--notes", default="")
    e.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv_list)
    try:
        return _cmd_append(args) if args.cmd == "append" else _cmd_exec(args)
    except (FileNotFoundError, CloudLogError, TimeoutError) as exc:
        print(f"cloud_log: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

