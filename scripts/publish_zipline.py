"""Publish the dashboard/ folder as a new version of a Zipline asset (go/zipline).

Zipline hosts static files for Googlers. This script does not talk to the Zipline
API itself: it runs the official Zipline CLI (go/zipline-cli, repo
sso://uxe-internal/zipline-cli) in its prompt-free mode, which is what the
Zipline team supports. The CLI needs Node; when `node` is not on PATH the
`nodejs-wheel-binaries` Python package (a user-space Node, no sudo) is used.

Usage:
  python scripts/publish_zipline.py --project <project id> --asset <asset id> \
      [--dir dashboard] [--cli-dir .zipline-cli]

One-time setup per repo: create a Zipline project and an asset once with the same
CLI (`zipline add project`, then `zipline upload` for the first version), note the
two ids it prints, and set ZIPLINE_PROJECT / ZIPLINE_ASSET for `make
publish-dashboard` (for example in environments/<env>.mk). With --asset_id and
--config the CLI asks no questions, so this is safe to run from `make`/CI.

Exit codes: 0 published (URL printed), 1 bad input, 2 the CLI failed (its output
is shown; the usual cause is an expired corp session -> open go/zipline in the
browser, or `uplink-helper login` on a gMac, and retry).
"""

from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import shutil
from pathlib import Path
from re import compile as _regex_compile

CLI_REPO = "sso://uxe-internal/zipline-cli"
URL_RE = _regex_compile(r"https://serve-dot-zipline\.googleplex\.com/hosting/[0-9a-f-]+")


def ensure_cli(cli_dir: Path, run=subprocess.run) -> Path:
    """Clone the official CLI once (git-ignored folder); return the path of its entry file."""
    main = cli_dir / "main"
    if main.exists():
        return main
    print(f"cloning {CLI_REPO} into {cli_dir} ...", file=sys.stderr)
    run(["git", "clone", "-q", CLI_REPO, str(cli_dir)], check=True)
    if not main.exists():
        raise FileNotFoundError(f"{main} missing after clone")
    return main


def node_command() -> list[str]:
    """Argv prefix that runs Node: `node` from PATH, else the nodejs-wheel-binaries package."""
    path_node = shutil.which("node")
    if path_node:
        return [path_node]
    try:
        import nodejs_wheel  # type: ignore
    except ImportError:
        print(
            "ERROR: no `node` on PATH and nodejs-wheel-binaries is not installed; "
            "run with `uv run --with nodejs-wheel-binaries ...` (the Makefile does)",
            file=sys.stderr,
        )
        raise
    bin_dir = Path(nodejs_wheel.__file__).parent / "bin"
    exe = bin_dir / ("node.exe" if os.name == "nt" else "node")
    return [str(exe)]


def upload_args(
    main: Path, folder: Path, project_id: str, asset_id: str, config: Path
) -> list[str]:
    return [
        str(main),
        "upload",
        "--source",
        str(folder),
        "--project_id",
        project_id,
        "--asset_id",
        asset_id,
        "--index_entry",
        "index.html",
        "--config",
        str(config),
    ]


def parse_url(output: str) -> str | None:
    m = URL_RE.search(output)
    return m.group(0) if m else None


def run_in_pty(cmd: list[str], cwd: str, timeout_s: int = 900) -> tuple[int, str]:
    """Run cmd with a pseudo-terminal as stdout (the CLI's progress bar needs one).

    With a plain pipe the CLI dies on `process.stdout.clearLine is not a function`
    half-way through the upload. Nothing is ever typed: stdin gets no data.
    """
    import pty
    import select
    import time

    pid, fd = pty.fork()
    if pid == 0:  # child
        os.chdir(cwd)
        os.execv(cmd[0], cmd)
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout_s
    status = None
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 1.0)
        if ready:
            try:
                data = os.read(fd, 65536)
            except OSError:
                data = b""
            if not data:
                break
            chunks.append(data)
        else:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
    if status is None:
        _, status = os.waitpid(pid, 0)
    os.close(fd)
    return os.waitstatus_to_exitcode(status), b"".join(chunks).decode(
        "utf-8", "replace"
    )


def publish(
    folder: Path,
    project_id: str,
    asset_id: str,
    cli_dir: Path,
    run=subprocess.run,
    node: list[str] | None = None,
    run_cli=run_in_pty,
) -> dict:
    cli_dir = cli_dir.resolve()
    folder = folder.resolve()
    main = ensure_cli(cli_dir, run=run)
    config = cli_dir / "zipline-config.json"
    # The CLI reads this file (its own format) and rewrites it after the upload;
    # with --config present it asks no "save config?" question.
    config.write_text(
        json.dumps(
            {
                "source": str(folder),
                "projectId": project_id,
                "assetId": asset_id,
                "name": "hill-climb dashboard",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    cmd = (node or node_command()) + upload_args(
        main, folder, project_id, asset_id, config
    )
    returncode, output = run_cli(cmd, str(cli_dir))
    clean = "\n".join(
        line
        for line in output.splitlines()
        if "DeprecationWarning" not in line and "trace-deprecation" not in line
    )
    url = parse_url(output)
    if returncode != 0 or not url:
        raise RuntimeError(f"zipline upload failed (exit {returncode}):\n{clean}")
    return {
        "project_id": project_id,
        "asset_id": asset_id,
        "version_url": url + "/index.html",
        "asset_url": f"https://zipline.googleplex.com/projects/{project_id}",
    }


def _self_test() -> int:
    url = parse_url(
        "Uploaded: https://serve-dot-zipline.googleplex.com/hosting/1234-5678-abcd"
    )
    assert (
        url == "https://serve-dot-zipline.googleplex.com/hosting/1234-5678-abcd"
    ), url
    args = upload_args(
        Path("/tmp/main"), Path("/tmp/dash"), "proj-1", "asset-1", Path("/tmp/cfg.json")
    )
    assert "--project_id" in args and "--asset_id" in args, args
    print("OK: 2/2 publish_zipline self-test cases passed")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project", help="Zipline project id (uuid)")
    p.add_argument("--asset", help="Zipline asset id (uuid)")
    p.add_argument(
        "--dir", default="dashboard", help="Folder to publish (needs index.html)"
    )
    p.add_argument(
        "--cli-dir",
        default=".zipline-cli",
        help="Where the official CLI is (or gets) cloned; git-ignored",
    )
    p.add_argument("--self-test", action="store_true", help="Run built-in self-tests")
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.project or not args.asset:
        p.error("--project and --asset are required")
    folder = Path(args.dir)
    if not (folder / "index.html").exists():
        print(
            f"ERROR: {folder}/index.html not found; run `make dashboard` first",
            file=sys.stderr,
        )
        return 1
    try:
        result = publish(folder, args.project, args.asset, Path(args.cli_dir))
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        FileNotFoundError,
        ImportError,
    ) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

