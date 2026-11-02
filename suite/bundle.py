#!/usr/bin/env python3
"""Inline shared code from lib/ into each CX Agent Studio tool and callback.

Why: every tool and callback runs as ONE file (`python_code.py`) in a sandbox.
`from lib.x import y` works in local tests but fails on the platform. So shared
code lives in `lib/`, and this script copies what each file uses into a
generated block at the end of that file.

Hardened against:
  - DEF-14 (alias stripping): `from lib.mod import name as alias` preserves the
    alias by emitting `alias = name` inside the generated block.
  - DEF-15 (duplicate top-level symbols across lib/*.py): fails fast if two
    modules in `lib/` define the same top-level function, class, or constant.
  - Tool wrapper signature drift: verifies that each tool wrapper function (the
    code above the generated block, or above `# DO NOT MODIFY CODE BELOW THIS
    LINE` if a file has that marker) has the exact same parameters as its
    `*_impl` function in `lib/` (ignoring the injected `state`, `session_state`,
    `context` and `callback_context` parameters).
  - `--check` mode runs an isolated-namespace `compile()` + `exec()` smoke check
    on every bundled `python_code.py`.

Usage:
  python suite/bundle.py [--root .] [--app-dir cxas_app] [--lib-dir lib]
  python suite/bundle.py --check      # exit 1 if any bundle is stale or invalid (CI)
  python suite/bundle.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import os
import re
import sys
import tempfile

BEGIN = "# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---"
END = "# --- END GENERATED SHARED BUNDLE ---"
DO_NOT_MODIFY = "# DO NOT MODIFY CODE BELOW THIS LINE"
USES = re.compile(r"^#\s*uses:\s*from\s+lib\.(\w+)\s+import\s+(.+)$")
LIB_IMPORT = re.compile(r"^from\s+lib\.(\w+)\s+import\s+(.+)$")

# Platform types injected by the CES Python runtime at callback execution time.
CES_SANDBOX_GLOBALS = {
    "CallbackContext": object,
    "LlmRequest": object,
    "LlmResponse": object,
    "Tool": object,
    "ToolContext": object,
    "Part": object,
    "Content": object,
}


class BundleError(ValueError):
    """Raised on duplicate lib symbols, missing symbols, or signature mismatches.

    Deliberately NOT a SystemExit: an uncaught SystemExit without an exit code
    ends the process silently with status 0, which hid every bundle failure from
    `make bundle-check`. main() prints it and returns 1.
    """


def parse_import_specs(spec_str: str) -> list[tuple[str, str | None]]:
    """Parse 'foo, bar as _bar' into [('foo', None), ('bar', '_bar')]."""
    out: list[tuple[str, str | None]] = []
    for part in spec_str.strip("() ").split(","):
        item = part.strip()
        if not item:
            continue
        if " as " in item:
            orig, alias = item.split(" as ", 1)
            orig, alias = orig.strip(), alias.strip()
            out.append((orig, alias if alias and alias != orig else None))
        else:
            out.append((item, None))
    return out


def format_import_spec(orig: str, alias: str | None) -> str:
    return f"{orig} as {alias}" if alias and alias != orig else orig


def split_names(s: str) -> list[str]:
    """Return original symbol names from an import clause."""
    return [orig for orig, _ in parse_import_specs(s)]


def load_lib(lib_dir: str):
    """Return {symbol: (source, module, names_it_references)} and {module: [import lines]}.

    Raises BundleError (DEF-15) if two files in `lib/` define the same top-level symbol.
    """
    symbols: dict[str, tuple[str, str, set[str]]] = {}
    imports: dict[str, list[str]] = {}
    if not os.path.isdir(lib_dir):
        return symbols, imports

    for fn in sorted(os.listdir(lib_dir)):
        if not fn.endswith(".py") or fn == "__init__.py":
            continue
        mod = fn[:-3]
        full_path = os.path.join(lib_dir, fn)
        with open(full_path, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, filename=full_path)
        imports[mod] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    continue
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "lib"
                ):
                    # Preserve intra-lib import aliases (`from lib.x import Y as Z`)
                    for alias_node in node.names:
                        if alias_node.asname and alias_node.asname != alias_node.name:
                            alias_name = alias_node.asname
                            target_name = alias_node.name
                            alias_src = f"{alias_name} = {target_name}"
                            if alias_name in symbols:
                                prev_src, prev_mod, _ = symbols[alias_name]
                                if prev_mod != mod and prev_src != alias_src:
                                    raise BundleError(
                                        f"bundle: duplicate symbol '{alias_name}' in "
                                        f"lib/{prev_mod}.py and lib/{mod}.py (DEF-15)"
                                    )
                            symbols[alias_name] = (alias_src, mod, {target_name})
                    continue
                imports[mod].append(ast.unparse(node))
                continue
            names: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            refs = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            segment = ast.get_source_segment(src, node) or ast.unparse(node)
            for name in names:
                if name in symbols:
                    _, prev_mod, _ = symbols[name]
                    if prev_mod != mod:
                        raise BundleError(
                            f"bundle: duplicate symbol '{name}' in "
                            f"lib/{prev_mod}.py and lib/{mod}.py (DEF-15)"
                        )
                symbols[name] = (segment, mod, refs)
    return symbols, imports


def resolve(wanted: set[str], symbols: dict[str, tuple[str, str, set[str]]]) -> list[str]:
    """Wanted symbols plus their lib dependencies, dependencies first."""
    out: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen or name not in symbols:
            return
        seen.add(name)
        for ref in sorted(symbols[name][2]):
            if ref != name:
                visit(ref)
        out.append(name)

    for name in sorted(wanted):
        if name not in symbols:
            raise BundleError(f"bundle: '{name}' not found in lib/")
        visit(name)
    return out


def _extract_func_params(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    params = [a.arg for a in fn_node.args.posonlyargs]
    params.extend(a.arg for a in fn_node.args.args)
    params.extend(a.arg for a in fn_node.args.kwonlyargs)
    return [
        p
        for p in params
        if p not in ("self", "state", "session_state", "context", "callback_context")
    ]


def check_wrapper_signature(
    path: str, body: str, symbols: dict[str, tuple[str, str, set[str]]]
) -> None:
    """Verify tool wrapper signature above DO_NOT_MODIFY matches `<tool>_impl` in `lib/`."""
    header_part = body.split(DO_NOT_MODIFY)[0] if DO_NOT_MODIFY in body else body
    try:
        tree = ast.parse(header_part, filename=path)
    except SyntaxError as exc:
        raise BundleError(f"bundle: syntax error in {path}: {exc}") from exc

    if "tools" in path.replace("\\", "/").split("/"):
        for n in tree.body:
            if isinstance(n, ast.ImportFrom) and n.module == "__future__":
                raise BundleError(
                    f"bundle: 'from __future__ import annotations' in {path} breaks CES ImportApp server-side reflection (KF-70)"
                )

    fn_defs = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for fn_node in fn_defs:
        impl_name = f"{fn_node.name}_impl"
        # Also detect if the wrapper delegates to an `*_impl` call inside its body
        called_impls = [
            n.func.id
            for n in ast.walk(fn_node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id.endswith("_impl")
            and n.func.id in symbols
        ]
        target_impl = (
            impl_name
            if impl_name in symbols
            else (called_impls[0] if len(called_impls) == 1 else None)
        )
        if not target_impl:
            continue

        impl_src = symbols[target_impl][0]
        impl_tree = ast.parse(impl_src, filename=f"lib/{symbols[target_impl][1]}.py")
        impl_nodes = [
            n
            for n in impl_tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if not impl_nodes:
            continue
        impl_node = impl_nodes[0]
        wrapper_params = _extract_func_params(fn_node)
        impl_params = _extract_func_params(impl_node)
        if wrapper_params != impl_params:
            raise BundleError(
                f"bundle: wrapper signature mismatch in {path}: "
                f"{fn_node.name}({', '.join(wrapper_params)}) != "
                f"{target_impl}({', '.join(impl_params)})"
            )


def smoke_exec(path: str, content: str) -> dict:
    """Compile and execute `content` in an isolated sandbox namespace (no `lib` import)."""
    code_obj = compile(content, path, "exec")
    ns = dict(CES_SANDBOX_GLOBALS)
    ns["__name__"] = "__bundle_smoke__"
    ns["__file__"] = path
    exec(code_obj, ns)
    for line in content.splitlines():
        m = USES.match(line.strip())
        if m:
            for orig, alias in parse_import_specs(m.group(2)):
                if orig not in ns:
                    raise BundleError(
                        f"bundle: expected symbol '{orig}' missing from namespace in {path}"
                    )
                if alias and alias not in ns:
                    raise BundleError(
                        f"bundle: expected alias '{alias}' (for '{orig}') missing from namespace in {path}"
                    )
    return ns


def render(
    path: str,
    symbols: dict[str, tuple[str, str, set[str]]],
    imports: dict[str, list[str]],
) -> str:
    """Return the new file content for one python_code.py."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    body, _, rest = text.partition(BEGIN)
    old_block = rest.partition(END)[0] if rest else ""
    tail = rest.partition(END)[2] if rest else ""

    # uses: mod -> set of (orig, alias)
    uses: dict[str, set[tuple[str, str | None]]] = {}
    for line in old_block.splitlines():
        m = USES.match(line.strip())
        if m:
            uses.setdefault(m.group(1), set()).update(parse_import_specs(m.group(2)))
    kept: list[str] = []
    for line in body.splitlines():
        m = LIB_IMPORT.match(line.strip())
        if m:
            uses.setdefault(m.group(1), set()).update(parse_import_specs(m.group(2)))
        else:
            kept.append(line)
    body = "\n".join(kept).rstrip() + "\n"

    check_wrapper_signature(path, body, symbols)

    if not uses:
        return body + tail.lstrip("\n") if rest else text

    # Consolidate (orig, None) and (orig, alias) so if an alias is used, we don't duplicate
    cleaned_uses: dict[str, list[tuple[str, str | None]]] = {}
    aliases: list[tuple[str, str]] = []
    wanted: set[str] = set()
    for mod, pairs in sorted(uses.items()):
        by_orig: dict[str, set[str | None]] = {}
        for orig, alias in pairs:
            wanted.add(orig)
            by_orig.setdefault(orig, set()).add(alias)
        mod_specs: list[tuple[str, str | None]] = []
        for orig in sorted(by_orig):
            non_none = sorted(a for a in by_orig[orig] if a)
            if non_none:
                for a in non_none:
                    mod_specs.append((orig, a))
                    aliases.append((orig, a))
                if None in by_orig[orig]:
                    mod_specs.append((orig, None))
            else:
                mod_specs.append((orig, None))
        cleaned_uses[mod] = mod_specs

    order = resolve(wanted, symbols)
    mods = sorted({symbols[n][1] for n in order})
    std_imports = sorted({i for m in mods for i in imports.get(m, [])})

    lines = ["", "", BEGIN]
    for mod in sorted(cleaned_uses):
        spec_list = [format_import_spec(o, a) for o, a in cleaned_uses[mod]]
        lines.append(f"# uses: from lib.{mod} import {', '.join(spec_list)}")
    lines += std_imports
    for name in order:
        src = symbols[name][0]
        first, *more = src.split("\n")
        lines += ["", first + "  # pragma: no cover", *more]
    for orig, alias in sorted(set(aliases)):
        if alias not in order:
            lines += ["", f"{alias} = {orig}  # pragma: no cover"]
    lines.append(END)
    return body + "\n".join(lines) + "\n" + tail.lstrip("\n")


def targets(app_dir: str):
    if not os.path.isdir(app_dir):
        return
    for dirpath, _, files in os.walk(app_dir):
        for fn in files:
            if fn == "python_code.py":
                yield os.path.join(dirpath, fn)


def run(root: str, app_dir: str, lib_dir: str, check: bool) -> int:
    symbols, imports = load_lib(os.path.join(root, lib_dir))
    stale: list[str] = []
    for path in sorted(targets(os.path.join(root, app_dir))):
        new = render(path, symbols, imports)
        with open(path, encoding="utf-8") as f:
            current = f.read()
        if new == current:
            if check:
                smoke_exec(path, current)
            continue
        if check and BEGIN in current:
            smoke_exec(path, current)
        smoke_exec(path, new)
        stale.append(os.path.relpath(path, root))
        if not check:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
    verb = "stale" if check else "updated"
    for p in stale:
        print(f"{verb}: {p}")
    if check and stale:
        print("run `make bundle` and commit the result")
        return 1
    return 0


def self_test() -> int:
    # 1. Standard bundling, tree-shaking, idempotency, and isolated compile+exec
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(f"{d}/lib")
        os.makedirs(f"{d}/cxas_app/tools/greet/python_function")
        open(f"{d}/lib/__init__.py", "w").close()
        open(f"{d}/lib/responses.py", "w").write(
            "import json\n\nSTATUS_OK = 'ok'\n\n"
            "def _wrap(status, data):\n    return {'status': status, 'data': data}\n\n"
            "def ok(data):\n    return _wrap(STATUS_OK, data)\n\n"
            "def greet_impl(name: str = 'world', state: dict | None = None):\n"
            "    return ok({'hello': name})\n\n"
            "def unused():\n    return json.dumps({})\n"
        )
        tool = f"{d}/cxas_app/tools/greet/python_function/python_code.py"
        open(tool, "w").write(
            '"""Greets."""\nfrom lib.responses import greet_impl, ok as _ok_alias\n\n\n'
            "def greet(name: str = 'world'):\n"
            "    res = greet_impl(name=name)\n"
            "    return _ok_alias(res['data'])\n\n\n"
            "# DO NOT MODIFY CODE BELOW THIS LINE\n"
        )
        assert run(d, "cxas_app", "lib", check=True) == 1, "fresh file should be stale"
        assert run(d, "cxas_app", "lib", check=False) == 0
        out = open(tool).read()
        assert "from lib.responses import" not in out.split(BEGIN)[0], (
            "import not moved"
        )
        assert "# uses: from lib.responses import greet_impl, ok as _ok_alias" in out
        assert "_ok_alias = ok" in out, "DEF-14 alias assignment not emitted"
        assert "def unused" not in out, "tree-shaking failed"
        assert (
            out.index("STATUS_OK =") < out.index("def _wrap") < out.index("def ok")
        ), "dependency order"
        ns = smoke_exec(tool, out)
        assert ns["greet"]("Ada") == {"status": "ok", "data": {"hello": "Ada"}}
        assert run(d, "cxas_app", "lib", check=True) == 0, "not idempotent"

        # 2. DEF-15: Duplicate symbol across lib/*.py must fail fast
        open(f"{d}/lib/second.py", "w").write("def ok(data):\n    return data\n")
        try:
            run(d, "cxas_app", "lib", check=False)
            raise AssertionError("Expected BundleError for duplicate symbol across lib/*.py")
        except BundleError as exc:
            assert "duplicate symbol 'ok'" in str(exc)
        os.remove(f"{d}/lib/second.py")

        # 3. Tool wrapper signature mismatch against *_impl must fail fast
        open(tool, "w").write(
            '"""Greets."""\nfrom lib.responses import greet_impl\n\n\n'
            "def greet(wrong_param: str = 'world'):\n"
            "    return greet_impl(name=wrong_param)\n\n\n"
            "# DO NOT MODIFY CODE BELOW THIS LINE\n"
        )
        try:
            run(d, "cxas_app", "lib", check=False)
            raise AssertionError("Expected BundleError for wrapper signature mismatch")
        except BundleError as exc:
            assert "wrapper signature mismatch" in str(exc)

        # 4. From the command line, a bundle failure must exit 1 and say why
        #    (an uncaught SystemExit subclass used to end it silently with 0).
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--root", d, "--check"])
        assert code == 1, "bundle failure must exit 1"
        assert "wrapper signature mismatch" in err.getvalue(), err.getvalue()

    print("OK (bundle self-test)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Inline lib/ code into single-file tools and callbacks"
    )
    p.add_argument(
        "app_dir_pos",
        nargs="?",
        default=None,
        help="Optional positional app directory (e.g. cxas_app)",
    )
    p.add_argument("--root", default=".")
    p.add_argument("--app-dir", default="cxas_app")
    p.add_argument("--lib-dir", default="lib")
    p.add_argument("--check", action="store_true")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)
    if a.self_test:
        return self_test()
    app_dir = a.app_dir_pos if a.app_dir_pos else a.app_dir
    try:
        return run(a.root, app_dir, a.lib_dir, a.check)
    except BundleError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
