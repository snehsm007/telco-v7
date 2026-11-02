"""Discover and validate regression eval files: evals/regression/<layer>/<topic>.yaml.

Regression cases guard one behaviour change each (team rule: every behaviour change adds or
updates a regression test in our own suite, in our own words). They are ordinary cases of the
four base layers, appended to the base lists, so the offline checks and the staging runner treat
them exactly like base cases. Nothing is relaxed compared with the base files.

Discovery rule (the only place cases come from; evals/holdout/ and evals/calibration/ are never read):
  1. `<eval_dir>/regression/` missing or empty -> no regression cases (fine).
  2. Its sub-directories must be layer names: tool_tests, goldens, simulations, probes. Anything
     else in it (another directory, a loose file) raises.
  3. Per layer, every `*.yaml` file in sorted path order (so the order is fixed). Any other file in a
     layer directory (for example `*.yml`) raises: a bad file is never skipped silently.

File schema (every rule raises RegressionError naming the file):
  suite: regression             # fixed value
  layer: <directory name>       # must equal the parent directory
  description: <one or two sentences, our own words>
  <layer key>: [cases]          # tests | goldens | simulations | probes; a non-empty list

Case rules, all layers: `id` starts with `reg_<layer>_<topic>_` (topic = the file name without
.yaml, snake_case) and is unique across the whole suite (base and regression); `regression_of` is
a non-empty sentence; `priority` is P0 or P1; `requirements` is a non-empty list of REQ ids that
exist in docs/requirements.md. Per layer:
  goldens:     cuj, language (en/fr/es), customer_id (a fake-world customer), expected_copy_keys
               (copy keys in lib/copy.py), turns (alternating user/agent, user first); agent
               tool_calls name deployed tools only.
  simulations: cuj, language, customer_id, task, user_facts (mapping), max_turns (int >= 5, i.e. a
               journey of at least one turn + 4), expected_tools (deployed tools), rubric (non-empty
               list of strings).
  probes:      language, assert.must_call_tools (deployed tools), and either the routing shape
               (routing_row, >= 3 phrasings, expected_intent, expected_route) or the safety shape
               (turns: non-empty list of caller lines).
  tool_tests:  the same rules as the base tool tests (suite/tool_tests.validate_case).
Each loaded case gets `source: evals/regression/<layer>/<topic>.yaml`.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_MD = REPO_ROOT / "docs" / "requirements.md"

# directory name -> the case-list key the base file of that layer uses
LAYER_KEYS = {
    "tool_tests": "tests",
    "goldens": "goldens",
    "simulations": "simulations",
    "probes": "probes",
}
COMMON_REQUIRED = ("id", "priority", "requirements", "regression_of")
LAYER_REQUIRED = {
    "goldens": ("cuj", "language", "customer_id", "expected_copy_keys", "turns"),
    "simulations": (
        "cuj",
        "language",
        "customer_id",
        "task",
        "user_facts",
        "max_turns",
        "expected_tools",
        "rubric",
    ),
    "probes": ("language", "assert"),
    "tool_tests": (),
}
ROUTING_PROBE_REQUIRED = (
    "routing_row",
    "phrasings",
    "expected_intent",
    "expected_route",
)
# Built-in platform tools an agent may call besides our own deployed tools.
PLATFORM_TOOLS = ("end_session",)
LANGUAGES = ("en", "fr", "es")
PRIORITIES = ("P0", "P1")
MIN_SIM_MAX_TURNS = 5
TOPIC_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
REQ_ROW_RE = re.compile(r"^\|\s*(REQ-\d+)\s*\|", re.MULTILINE)
# Keys only this loader knows about; strip them before handing a case to a layer runner.
LOADER_ONLY_KEYS = ("regression_of",)


class RegressionError(ValueError):
    """A regression file or case that breaks the schema or discovery rules."""


def known_requirement_ids(requirements_md: Path = REQUIREMENTS_MD) -> set[str]:
    """Every REQ id defined in the requirements table (P0 and P1)."""
    return set(REQ_ROW_RE.findall(Path(requirements_md).read_text(encoding="utf-8")))


def default_known_tools() -> set[str]:
    from lib import services

    return set(services.ALL_33_TOOLS) | set(PLATFORM_TOOLS)


def strip_loader_keys(case: dict) -> dict:
    """A copy of `case` without loader-only metadata, for runners that refuse unknown keys."""
    return {k: v for k, v in case.items() if k not in LOADER_ONLY_KEYS}


def discover(eval_dir: Path) -> list[tuple[str, Path]]:
    """(layer, path) for every regression file, in layer order then sorted path order."""
    root = Path(eval_dir) / "regression"
    if not root.exists():
        return []
    if not root.is_dir():
        raise RegressionError(f"{root}: expected a directory")
    found: list[tuple[str, Path]] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if not entry.is_dir() or entry.name not in LAYER_KEYS:
            raise RegressionError(
                f"{entry}: only the layer directories {sorted(LAYER_KEYS)} may live in {root}"
            )
    for layer in LAYER_KEYS:
        layer_dir = root / layer
        if not layer_dir.is_dir():
            continue
        for path in sorted(layer_dir.iterdir()):
            if path.name.startswith("."):
                continue
            if not path.is_file() or path.suffix != ".yaml":
                raise RegressionError(
                    f"{path}: regression files must be <topic>.yaml files (nothing is skipped silently)"
                )
            found.append((layer, path))
    return found


def _fail(path, msg: str):
    raise RegressionError(f"{path}: {msg}")


def _require_str(case, key, path, cid):
    value = case.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(path, f"{cid}: {key} must be a non-empty string")
    return value


def _require_list(case, key, path, cid, min_len=1):
    value = case.get(key)
    if not isinstance(value, list) or len(value) < min_len:
        _fail(path, f"{cid}: {key} must be a list with at least {min_len} item(s)")
    return value


def _check_tools(names, known_tools, path, cid, where):
    for name in names:
        if name not in known_tools:
            _fail(
                path,
                f"{cid}: {where} names {name!r}, which is not a deployed tool",
            )


def _check_customer(case, path, cid):
    from lib import fakes

    if case["customer_id"] not in fakes.NAMED_CUSTOMERS:
        _fail(
            path,
            f"{cid}: customer_id {case['customer_id']!r} is not a fake-world customer",
        )


def _validate_golden(case, path, cid, known_tools):
    _check_customer(case, path, cid)
    keys = case["expected_copy_keys"]
    if not isinstance(keys, list):
        _fail(path, f"{cid}: expected_copy_keys must be a list")
    from lib import copy as copy_lib

    for key in keys:
        try:
            copy_lib.get_copy(key, "en")
        except KeyError:
            _fail(path, f"{cid}: expected_copy_keys names unknown copy key {key!r}")
    turns = _require_list(case, "turns", path, cid, min_len=2)
    for pos, turn in enumerate(turns):
        want = "user" if pos % 2 == 0 else "agent"
        if not isinstance(turn, dict) or turn.get("role") != want:
            _fail(
                path,
                f"{cid}: turn {pos + 1} must be a {want} turn (user first, alternating)",
            )
        if not isinstance(turn.get("text"), str) or not turn["text"].strip():
            _fail(path, f"{cid}: turn {pos + 1} needs a non-empty text")
        calls = turn.get("tool_calls") or []
        if want == "user" and calls:
            _fail(
                path, f"{cid}: turn {pos + 1} is a user turn and cannot hold tool_calls"
            )
        names = [c.get("name") if isinstance(c, dict) else None for c in calls]
        _check_tools(names, known_tools, path, cid, f"turn {pos + 1} tool_calls")


def _validate_simulation(case, path, cid, known_tools):
    _check_customer(case, path, cid)
    _require_str(case, "task", path, cid)
    if not isinstance(case["user_facts"], dict) or not case["user_facts"]:
        _fail(path, f"{cid}: user_facts must be a non-empty mapping")
    max_turns = case["max_turns"]
    if (
        not isinstance(max_turns, int)
        or isinstance(max_turns, bool)
        or max_turns < MIN_SIM_MAX_TURNS
    ):
        _fail(path, f"{cid}: max_turns must be an integer >= {MIN_SIM_MAX_TURNS}")
    tools = _require_list(case, "expected_tools", path, cid)
    _check_tools(tools, known_tools, path, cid, "expected_tools")
    rubric = _require_list(case, "rubric", path, cid)
    if not all(isinstance(r, str) and r.strip() for r in rubric):
        _fail(path, f"{cid}: every rubric item must be a non-empty string")


def _validate_probe(case, path, cid, known_tools):
    assertion = case["assert"]
    if not isinstance(assertion, dict) or not isinstance(
        assertion.get("must_call_tools"), list
    ):
        _fail(path, f"{cid}: assert.must_call_tools must be a list")
    _check_tools(
        assertion["must_call_tools"], known_tools, path, cid, "assert.must_call_tools"
    )
    if "phrasings" in case or "routing_row" in case:
        missing = [k for k in ROUTING_PROBE_REQUIRED if k not in case]
        if missing:
            _fail(path, f"{cid}: a routing probe needs {missing}")
        phrasings = _require_list(case, "phrasings", path, cid, min_len=3)
        if not all(isinstance(p, str) and p.strip() for p in phrasings):
            _fail(path, f"{cid}: every phrasing must be a non-empty string")
        if not isinstance(case["routing_row"], int) or isinstance(
            case["routing_row"], bool
        ):
            _fail(path, f"{cid}: routing_row must be an integer")
        _require_str(case, "expected_intent", path, cid)
        _require_str(case, "expected_route", path, cid)
        return
    turns = _require_list(case, "turns", path, cid)
    if not all(isinstance(t, str) and t.strip() for t in turns):
        _fail(path, f"{cid}: a safety probe's turns must be non-empty caller lines")


def validate_case(case, layer, topic, path, known_reqs, known_tools):
    """Raise RegressionError if `case` breaks a rule; return the case otherwise."""
    if not isinstance(case, dict):
        _fail(path, f"every case must be a mapping, got {type(case).__name__}")
    cid = case.get("id", "<no id>")
    missing = [k for k in COMMON_REQUIRED + LAYER_REQUIRED[layer] if k not in case]
    if missing:
        _fail(path, f"{cid}: missing required fields {missing}")
    prefix = f"reg_{layer}_{topic}_"
    if (
        not isinstance(cid, str)
        or not cid.startswith(prefix)
        or len(cid) == len(prefix)
    ):
        _fail(path, f"{cid}: id must start with {prefix!r} and add a suffix")
    _require_str(case, "regression_of", path, cid)
    if case["priority"] not in PRIORITIES:
        _fail(path, f"{cid}: priority must be one of {PRIORITIES}")
    reqs = _require_list(case, "requirements", path, cid)
    unknown = sorted(r for r in reqs if r not in known_reqs)
    if unknown:
        _fail(path, f"{cid}: unknown requirement ids {unknown}")
    if "language" in case and case["language"] not in LANGUAGES:
        _fail(path, f"{cid}: language must be one of {LANGUAGES}")
    if layer == "goldens":
        _validate_golden(case, path, cid, known_tools)
    elif layer == "simulations":
        _validate_simulation(case, path, cid, known_tools)
    elif layer == "probes":
        _validate_probe(case, path, cid, known_tools)
    else:
        from suite import tool_tests

        try:
            tool_tests.validate_case(strip_loader_keys(case), known_tools)
        except tool_tests.CaseError as exc:
            _fail(path, f"tool-test rule: {exc}")
    return case


def load_file(layer, path, known_reqs, known_tools, rel_root=REPO_ROOT) -> list[dict]:
    """Load one regression file; every case validated and tagged with its `source`."""
    path = Path(path)
    topic = path.stem
    if not TOPIC_RE.match(topic):
        _fail(path, "the file name must be a snake_case topic in our own words")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        _fail(path, f"not valid YAML ({exc})")
    if not isinstance(doc, dict):
        _fail(path, "the file must be a mapping")
    if doc.get("suite") != "regression":
        _fail(path, "suite must be 'regression'")
    if doc.get("layer") != layer:
        _fail(path, f"layer must equal the directory name {layer!r}")
    if not isinstance(doc.get("description"), str) or not doc["description"].strip():
        _fail(path, "description must be a non-empty string")
    key = LAYER_KEYS[layer]
    cases = doc.get(key)
    if not isinstance(cases, list) or not cases:
        _fail(path, f"the layer key {key!r} must be a non-empty list")
    try:
        source = str(path.resolve().relative_to(Path(rel_root).resolve()))
    except ValueError:
        source = str(path)
    out = []
    for case in cases:
        validate_case(case, layer, topic, path, known_reqs, known_tools)
        tagged = dict(case)
        tagged["source"] = source
        out.append(tagged)
    return out


def merge_into(
    suite: dict, eval_dir: Path, *, known_reqs=None, known_tools=None, rel_root=None
) -> dict:
    """Append every regression case to its layer list in `suite` (in place); return `suite`.

    `suite` maps layer names (tool_tests, goldens, simulations, probes) to base case lists.
    Raises RegressionError on any bad file, bad case or duplicate id (base or regression).
    """
    files = discover(eval_dir)
    if not files:
        return suite
    reqs = known_requirement_ids() if known_reqs is None else known_reqs
    tools = default_known_tools() if known_tools is None else known_tools
    root = Path(rel_root) if rel_root else Path(eval_dir).resolve().parent
    seen = {
        c.get("id")
        for layer in LAYER_KEYS
        for c in suite.get(layer, [])
        if isinstance(c, dict)
    }
    for layer, path in files:
        for case in load_file(layer, path, reqs, tools, rel_root=root):
            if case["id"] in seen:
                _fail(
                    path,
                    f"duplicate id {case['id']} (ids are unique across the whole suite)",
                )
            seen.add(case["id"])
            suite.setdefault(layer, []).append(case)
    return suite


def _self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        eval_dir = Path(tmp) / "evals"
        eval_dir.mkdir(parents=True)
        suite = {"tool_tests": [], "goldens": [], "simulations": [], "probes": []}
        merged = merge_into(suite, eval_dir, known_reqs={"REQ-01"}, known_tools={"lookup_account"})
        assert merged["goldens"] == []
    print("OK (regression self-test)")
    return 0


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        sys.exit(_self_test())

