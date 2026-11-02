# Makefile: the ONE way to run tasks, for humans, coding agents and CI alike.
# `make` (no target) lists everything. Pick the target app with ENV=<name>,
# which loads environments/<name>.mk (PROJECT_ID, LOCATION, APP_ID, AGENT_NAME).
#
#   make install                                  deps into .venv (uv sync)
#   make kickstart NAME=my-agent PRD=prd.md        scaffold a complete agent
#   make ci                                       Gate 0: offline, free
#   make preflight ENV=staging                    login (ADC) + permissions check; every cloud target runs it
#   make push ENV=staging                         commit first; bundle + push + version git-<sha7>
#   make smoke-impact ENV=staging                 Gate 1: impacted evals x 3 on the pushed commit
#   make bench-unstable ENV=staging               Gate 2 (unstable set x 5)
#   make bench-full ENV=staging                   Gate 3 (everything x 3, then the Gate 3 verdict)
#   make eval ENV=staging LAYERS=probe PRIORITY=P0 RUNS=1 && make gate   CI-style gate
#
# The 4-Gate Confidence Ladder: Gate 0 offline -> Gate 1 smoke -> Gate 2 unstable
# -> Gate 3 full (70 public evals in bench/dev/ x 3 + make gate3; references/05-evals.md).
# Order of the cloud steps: commit -> make push -> make smoke-impact -> make bench-full.
# history/last_push.json records which commit each app runs (by source fingerprint:
# the committed trees of cxas_app/, lib/ and evals/), so the smoke and full runs
# always measure the pushed commit.

.DEFAULT_GOAL := help
.PHONY: help install kickstart bootstrap bootstrap-dry bundle bundle-check overfit-check format lint llm-lint test selftest ci voice-audit \
        preflight auth-check impact smoke-impact eval-contract setup-dlp skill-assets skill-assets-check \
        push push-evals pull preview-up preview-down eval gate gate3 smoke chat inspect versions-compare \
        bench bench-dry bench-smoke bench-unstable bench-full bench-record bench-compare bench-fetch \
        trace-triage trace-replay dashboard publish-dashboard need-app need-cxas need-deps

ENV ?= staging
-include environments/$(ENV).mk

# --- tools: project .venv first, then PATH -----------------------------------------------
# No `uv run` fallback on purpose: `uv run --no-sync` creates an empty .venv and then
# fails with "Failed to spawn: cxas", which also breaks every later `make` call.
# First run: `make install` (uv sync, or pip into .venv when uv is missing).
VENV   ?= .venv
PYTHON ?= $(shell if [ -x $(VENV)/bin/python ]; then echo $(VENV)/bin/python; else command -v python3; fi)
CXAS   ?= $(shell if [ -x $(VENV)/bin/cxas ]; then echo $(VENV)/bin/cxas; else command -v cxas; fi)
PYTEST ?= $(PYTHON) -m pytest
# The two cloud runners (override only to stub them out in a dry check of the gates).
RUN_EVALS ?= $(PYTHON) scripts/run_evals.py
RUN_BENCH ?= $(PYTHON) scripts/run_bench.py

# --- layout --------------------------------------------------------------------------
APP_DIR      ?= cxas_app
AGENT_DIR    ?= $(APP_DIR)
LIB_DIR      ?= lib
TESTS_DIR    ?= tests
EVALS_DIR    ?= evals
COVERAGE_MIN ?= 80
BENCH_DIR    ?= bench
UNSTABLE_SET ?= $(EVALS_DIR)/unstable_set.txt
HISTORY      ?= history/runs.jsonl
THRESHOLDS   ?= gate_thresholds.json
WAIVERS      ?= lint_waivers.json
SKILL_ASSETS ?= .agents/skills/gecx-agent-playbook/assets
SKILL_ASSET_FILES = $(sort $(wildcard scripts/*.py suite/*.py)) Makefile gate_thresholds.json environments/example.mk lint_waivers.json
LOCAL_VOICE_AUDIT := .agents/skills/cxas-composite-voice-agent-optimizer/scripts/audit_agent.py
VOICE_AUDIT  ?= $(if $(wildcard $(LOCAL_VOICE_AUDIT)),$(LOCAL_VOICE_AUDIT),$(HOME)/.gemini/config/skills/cxas-composite-voice-agent-optimizer/scripts/audit_agent.py)

# --- kickstart -----------------------------------------------------------------------
TARGET_DIR  ?= .
NAME        ?=
AGENT_NAME  ?= $(if $(NAME),$(NAME),starter-voice-agent)
PRD         ?=
PROJECT_ID  ?= my-gcp-project
LOCATION    ?= us
LANGUAGES   ?= en-US,fr-CA,es-US
TEMPERATURE ?= 1.0

# --- cloud target --------------------------------------------------------------------
APP_ID ?=
APP    ?= projects/$(PROJECT_ID)/locations/$(LOCATION)/apps/$(APP_ID)
SHA7   := $(shell git rev-parse --short=7 HEAD 2>/dev/null || echo nogit)
GIT_SHA7 := $(SHA7)

# --- evals ---------------------------------------------------------------------------
TARGETS  ?=
LAYERS   ?=
PRIORITY ?=
RUNS     ?=
MODALITY ?= text
TRIGGER  ?= local
RUN_ID   ?= eval-$(shell date -u +%Y%m%d%H%M)-$(SHA7)
REPORT   ?=
RUN_IDS  ?=
FROM     ?=
TO       ?=
BEFORE   ?= $(FROM)
AFTER    ?= $(TO)
KIND     ?= targeted
CONV_ID  ?=
CONV     ?= $(CONV_ID)
Q        ?=
VERSION  ?=
PR       ?=
ZIPLINE_PROJECT  ?=
ZIPLINE_ASSET    ?=
PARALLEL_BATCHES ?= 1
PARALLEL_FLAG     = $(if $(filter 1 true yes,$(PARALLEL_BATCHES)),--parallel-batches,)
SKIP_PREFLIGHT   ?=
SKIP_SMOKE_GATE  ?=
SKIP_IMPACT      ?=
REASON           ?=
BASE             ?=
DRY_RUN          ?=

# The gates of scripts/impact.py: push -> smoke -> record (source fingerprint = committed
# trees of APP_DIR, LIB_DIR and EVALS_DIR; history/last_push.json = what each app runs).
IMPACT = $(PYTHON) scripts/impact.py --env "$(ENV)" --source-dirs "$(APP_DIR),$(LIB_DIR),$(EVALS_DIR)"

# run_evals.py flags shared by eval / smoke / bench-* (records go to $(HISTORY) for `make gate`)
EVAL_COMMON = --app $(APP) --bench-dir $(BENCH_DIR) --eval-dir $(EVALS_DIR) --app-dir $(APP_DIR) \
              --records $(HISTORY) --thresholds $(THRESHOLDS) --trigger $(TRIGGER) --modality $(MODALITY) \
              $(if $(RUNS),--repeats $(RUNS))

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

install: ## Install dependencies into .venv (uv sync; pip fallback when uv is missing)
	@if command -v uv >/dev/null 2>&1; then uv sync; \
	else python3 -m venv $(VENV) && $(VENV)/bin/python -m pip install -q -U pip && \
	  $(VENV)/bin/python -m pip install -q $$(python3 -c 'import tomllib;print(" ".join(tomllib.load(open("pyproject.toml","rb"))["project"]["dependencies"]))'); fi

need-app:
	@case "$(APP)" in \
	  *"/apps/"|*"/apps") echo "ERROR: no app for ENV=$(ENV). Create environments/$(ENV).mk from environments/example.mk (PROJECT_ID, LOCATION, APP_ID) or pass APP=projects/<p>/locations/<l>/apps/<id>." >&2; exit 1;; \
	  *"<"*|*">"*) echo "ERROR: environments/$(ENV).mk still has a placeholder (APP=$(APP)). Fill in PROJECT_ID, LOCATION and APP_ID with real values." >&2; exit 1;; \
	esac

need-cxas:
	@test -n "$(CXAS)" || (echo "ERROR: cxas CLI not found. Run 'make install' (uv sync) or pip install cxas-scrapi." >&2; exit 1)

need-deps:
	@$(PYTHON) -c "import pytest, yaml" 2>/dev/null || (echo "ERROR: Python dependencies missing for $(PYTHON). Run 'make install' first." >&2; exit 1)

# --- offline (no cloud) ----------------------------------------------------------------
kickstart: ## Scaffold a complete agent: NAME=<agent> PRD=<prd.md> [PROJECT_ID= LOCATION= LANGUAGES= TEMPERATURE= TARGET_DIR=]
	$(PYTHON) scripts/kickstart.py --target-dir $(TARGET_DIR) --agent-name $(AGENT_NAME) \
		$(if $(PRD),--prd $(PRD),) \
		--project-id $(PROJECT_ID) --location $(LOCATION) --languages $(LANGUAGES) \
		--temperature $(TEMPERATURE)

bootstrap: ## Interactive Zero-to-CI/CD wizard (provisions GCP WIF + Service Account, GitHub Secrets/Vars, and .github/workflows/)
	$(PYTHON) bootstrap/bootstrap.py --target-dir $(TARGET_DIR)

bootstrap-dry: ## Dry-run preview of all gcloud, gh, and workflow files that bootstrap.py will create
	$(PYTHON) bootstrap/bootstrap.py --target-dir $(TARGET_DIR) --non-interactive --dry-run --gcp-project $(PROJECT_ID) --gcp-location $(LOCATION) --create-wif-pool

bundle: ## Inline lib/ into every tool and callback (never edit the generated block)
	$(PYTHON) suite/bundle.py --app $(APP_DIR) --lib $(LIB_DIR)

bundle-check: ## Fail if a generated bundle is stale
	$(PYTHON) suite/bundle.py --check --app $(APP_DIR) --lib $(LIB_DIR)

overfit-check: ## Scan prompts, lib/ and tool wrappers for test values, fake data, test IDs, non-PRD numbers/dates, bloat, one-sided rules
	$(PYTHON) suite/overfit_check.py --app $(APP_DIR) --lib $(LIB_DIR) --prd prd.md --eval-dir $(EVALS_DIR) --bench-dir $(BENCH_DIR)/dev

format: ## Format Python with ruff (skips if ruff is not installed)
	@if $(PYTHON) -m ruff --version >/dev/null 2>&1; then $(PYTHON) -m ruff format $(APP_DIR) $(LIB_DIR) suite scripts $(TESTS_DIR); \
	else echo "ruff not installed (uv add --dev ruff); skipping format"; fi

lint: bundle-check need-cxas ## cxas structural lint: fails on errors and on warnings not waived in lint_waivers.json (+ stale-bundle check)
	$(PYTHON) scripts/lint_check.py --app-dir $(APP_DIR) --waivers $(WAIVERS) --cxas "$(CXAS)"

llm-lint: need-cxas ## AI instruction lint, advisory (AGENT=<agent dir name>, default: every agent)
	@for d in $(if $(AGENT),$(APP_DIR)/agents/$(AGENT),$(APP_DIR)/agents/*/); do \
	  echo "== llm-lint $$d"; $(CXAS) llm-lint --agent-dir "$$d" || exit 1; done

test: need-deps ## pytest + per-file coverage >= COVERAGE_MIN + one test file per code file
	$(PYTEST) $(TESTS_DIR) --cov=$(APP_DIR) --cov=$(LIB_DIR) --cov-report=json:coverage.json -q
	$(PYTHON) suite/coverage_check.py --report coverage.json --min $(COVERAGE_MIN) --tests-dir $(TESTS_DIR)

selftest: ## --self-test of every suite/, scripts/, and bootstrap/ utility, plus skill-assets-check
	@for s in suite/bundle.py suite/overfit_check.py suite/grader.py suite/gate.py suite/coverage_check.py suite/preview_app.py \
	          suite/cloud_log.py suite/regression.py suite/tool_tests.py scripts/kickstart.py scripts/eval_contract.py \
	          scripts/impact.py scripts/run_evals.py scripts/run_bench.py scripts/bench_summary.py \
	          scripts/build_dashboard.py scripts/verify_mutations.py scripts/inspect_evals.py \
	          scripts/publish_zipline.py scripts/preflight.py scripts/setup_dlp.py scripts/lint_check.py \
	          scripts/triage_failures.py \
	          bootstrap/bootstrap.py; do \
	  $(PYTHON) $$s --self-test || exit 1; done
	@$(MAKE) --no-print-directory skill-assets-check

ci: need-deps need-cxas bundle-check overfit-check eval-contract lint ## Gate 0: everything that runs offline (bundle-check, overfit-check, eval-contract, cxas lint + waivers, pytest+coverage, self-tests, mutation check, eval validation)
	$(MAKE) test
	$(PYTHON) suite/overfit_check.py --self-test
	$(PYTHON) scripts/eval_contract.py --self-test
	$(PYTHON) scripts/impact.py --self-test
	$(PYTHON) suite/grader.py --self-test
	$(PYTHON) suite/gate.py --self-test
	$(PYTHON) scripts/verify_mutations.py --app $(APP_DIR) --tests $(TESTS_DIR)
	$(PYTHON) scripts/run_evals.py --mode local --eval-dir $(EVALS_DIR)

voice-audit: ## Gemini Composite V1/V2 voice readiness: app.json checks + optimizer audit when the skill is installed
	@$(PYTHON) -c 'import json, pathlib; app = json.loads(pathlib.Path("$(APP_DIR)/app.json").read_text()); m = app.get("modelSettings", {}).get("model"); assert m in ("gemini-composite-v1", "gemini-composite-v2"), "Expected gemini-composite-v1 or gemini-composite-v2"; assert app.get("audioProcessingConfig", {}).get("bargeInConfig", {}).get("bargeInAwareness") is True, "Expected bargeInAwareness=True"; assert app.get("defaultChannelProfile", {}).get("noiseSuppressionLevel") == "HIGH", "Expected noiseSuppressionLevel=HIGH"; print(f"OK: voice-audit passed ({m}, bargeInAwareness=True, noiseSuppressionLevel=HIGH)")'
	@if [ -f "$(VOICE_AUDIT)" ]; then $(PYTHON) "$(VOICE_AUDIT)" --workspace $(APP_DIR) --report --json; \
	else echo "cxas-composite-voice-agent-optimizer skill not installed; skipped the P0/P1 audit"; fi

eval-contract: need-deps ## Check lib/fakes.py against the visible evals in $(BENCH_DIR)/dev/evaluations (first-try and wrong codes, caller ids); part of make ci
	@if [ ! -d "$(BENCH_DIR)/dev/evaluations" ] || [ ! -f "$(LIB_DIR)/fakes.py" ]; then \
	  echo "eval-contract: skipped ($(BENCH_DIR)/dev/evaluations or $(LIB_DIR)/fakes.py does not exist yet)"; \
	else \
	  $(PYTHON) scripts/eval_contract.py --evals-dir $(BENCH_DIR)/dev/evaluations --fakes $(LIB_DIR)/fakes.py; \
	fi

skill-assets: ## Copy scripts/*.py, suite/*.py, Makefile, gate_thresholds.json, environments/example.mk and lint_waivers.json into the playbook skill's assets/
	@test -d "$(SKILL_ASSETS)" || { echo "skill-assets: $(SKILL_ASSETS) does not exist in this repo; nothing to refresh."; exit 0; }; \
	for f in $(SKILL_ASSET_FILES); do \
	  mkdir -p "$(SKILL_ASSETS)/$$(dirname $$f)"; cp "$$f" "$(SKILL_ASSETS)/$$f"; \
	done; \
	for f in $(SKILL_ASSETS)/scripts/*.py $(SKILL_ASSETS)/suite/*.py; do \
	  [ -e "$$f" ] || continue; rel="$${f#$(SKILL_ASSETS)/}"; \
	  [ -f "$$rel" ] || { rm -f "$$f"; echo "skill-assets: removed $$f ($$rel no longer exists)"; }; \
	done; \
	echo "skill-assets: refreshed $(words $(SKILL_ASSET_FILES)) files in $(SKILL_ASSETS)/"

skill-assets-check: ## Fail when the playbook skill's assets/ copies differ from the root scripts, suite, Makefile and configs (fix: make skill-assets)
	@test -d "$(SKILL_ASSETS)" || { echo "skill-assets-check: no $(SKILL_ASSETS) in this repo; skipped."; exit 0; }; \
	drift=""; \
	for f in $(SKILL_ASSET_FILES); do cmp -s "$$f" "$(SKILL_ASSETS)/$$f" || drift="$$drift $$f"; done; \
	for f in $(SKILL_ASSETS)/scripts/*.py $(SKILL_ASSETS)/suite/*.py; do \
	  [ -e "$$f" ] || continue; rel="$${f#$(SKILL_ASSETS)/}"; [ -f "$$rel" ] || drift="$$drift $$rel(deleted-at-root)"; \
	done; \
	if [ -n "$$drift" ]; then \
	  echo "ERROR: the copies in $(SKILL_ASSETS)/ differ from the root files:$$drift" >&2; \
	  echo "Run: make skill-assets (then commit both)" >&2; exit 1; \
	fi; \
	echo "OK: skill assets match the root files ($(words $(SKILL_ASSET_FILES)) files)"

# --- cloud: preflight, impact & app lifecycle ---------------------------------------------
preflight: ## Check the Google Cloud login (ADC), its quota project and the CES permissions on the project before a cloud run (SKIP_PREFLIGHT=1 skips)
	@if [ "$(SKIP_PREFLIGHT)" = "1" ]; then echo "preflight: skipped (SKIP_PREFLIGHT=1)"; \
	else $(PYTHON) scripts/preflight.py --project-id "$(PROJECT_ID)" --app "$(APP)"; fi

auth-check: preflight ## Alias for preflight credential check

impact: ## Map git diff since the last clean full run to impacted evaluation IDs and a verdict: SMOKE, FULL or NONE (BASE=<sha> to override)
	$(IMPACT) $(if $(BASE),--base $(BASE),)

smoke-impact: need-app preflight ## Gate 1 on the pushed commit: impacted evals x 3, verdict recorded for its source fingerprint (FULL verdict: stops, run bench-full)
	@targets=$$($(IMPACT) --app "$(APP)" --smoke-plan $(if $(BASE),--base $(BASE),)) || exit $$?; \
	if [ -z "$$targets" ]; then exit 0; fi; \
	$(RUN_EVALS) --smoke $(EVAL_COMMON) --targets "$$targets" --label smoke-$(SHA7) && \
	$(IMPACT) --record-smoke $(BENCH_DIR)/runs/smoke-$(SHA7).json

push: need-app need-cxas bundle-check preflight ## Push $(APP_DIR) to ENV's app as version git-<sha7> (commit cxas_app/, lib/, evals/ first) and record it in history/last_push.json
	@$(IMPACT) --require-clean
	$(PYTHON) suite/cloud_log.py exec --op WRITE --target "$(APP)" --notes "push commit $(SHA7)" -- \
		$(CXAS) push --app-dir $(APP_DIR) --to $(APP) --create-version --version-name git-$(SHA7)
	@$(IMPACT) --record-push --app "$(APP)" --version-name git-$(SHA7)
	@echo "Re-apply any app-level settings an overwriting push resets (see references/13-commands.md)."
	@echo "Next: make smoke-impact ENV=$(ENV)"

push-evals: need-app preflight ## Create/update the local goldens, simulations and probes in ENV's app (TARGETS= to limit)
	$(PYTHON) scripts/run_evals.py --push --app $(APP) --eval-dir $(EVALS_DIR) $(if $(TARGETS),--targets "$(TARGETS)")

setup-dlp: need-app preflight ## Cloud DLP: create/update <AGENT_NAME>-pii-inspect/-deidentify in LOCATION and turn on log redaction in app.json (then commit + make push; DRY_RUN=1 previews)
	$(PYTHON) scripts/setup_dlp.py --project-id "$(PROJECT_ID)" --location "$(LOCATION)" --agent-name "$(AGENT_NAME)" \
		--app-dir $(APP_DIR) --apply-app-json $(if $(filter 1 true yes,$(DRY_RUN)),--dry-run,)

pull: need-app need-cxas ## Pull the app (VERSION=<id> for a version) into ./pulled/ to compare
	$(CXAS) pull $(APP) --target-dir pulled $(if $(VERSION),--version-id $(VERSION)) --overwrite

preview-up: bundle need-cxas ## Create or update the throwaway app for PR=<n>; writes its name to .preview_app and records the push
	@test -n "$(PR)" || (echo "PR=<number> required" >&2; exit 1)
	@name="$(AGENT_NAME)-pr-$(PR)"; \
	app=$$($(PYTHON) suite/preview_app.py resolve --project $(PROJECT_ID) --location $(LOCATION) --name "$$name"); \
	version="git-$(SHA7)"; \
	if [ -z "$$app" ]; then \
	  $(CXAS) push --app-dir $(APP_DIR) --display-name "$$name" --project-id $(PROJECT_ID) --location $(LOCATION); \
	  app=$$($(PYTHON) suite/preview_app.py resolve --project $(PROJECT_ID) --location $(LOCATION) --name "$$name"); \
	  version="draft"; \
	else \
	  $(CXAS) push --app-dir $(APP_DIR) --to "$$app" --create-version --version-name git-$(SHA7); \
	fi; \
	test -n "$$app" || (echo "preview app not found after push" >&2; exit 1); \
	echo "$$app" > .preview_app; echo "preview app: $$app"; \
	$(IMPACT) --record-push --app "$$app" --version-name "$$version"

preview-down: need-cxas ## Delete the throwaway app for PR=<n>
	@test -n "$(PR)" || (echo "PR=<number> required" >&2; exit 1)
	$(CXAS) delete --display-name "$(AGENT_NAME)-pr-$(PR)" --project-id $(PROJECT_ID) --location $(LOCATION) --force

# --- cloud: CI-style eval + gate (history/runs.jsonl) --------------------------------------
eval: need-app ## Run evals on APP (TARGETS= or LAYERS=golden,sim,probe PRIORITY=P0; RUNS= RUN_ID= TRIGGER=) and append records to history/runs.jsonl
	$(PYTHON) scripts/run_evals.py --mode staging $(EVAL_COMMON) --label $(RUN_ID) \
		$(if $(TARGETS),--targets "$(TARGETS)") $(if $(LAYERS),--layers $(LAYERS)) $(if $(PRIORITY),--priority $(PRIORITY))

gate: ## PASS / FAIL / INCONCLUSIVE for RUN_ID from history/runs.jsonl, incl. strict 3/3 >= strict_pass_rate (exit 0 / 1 / 3)
	@mkdir -p artifacts/$(RUN_ID)
	$(PYTHON) suite/gate.py --records $(HISTORY) --thresholds $(THRESHOLDS) --run-id $(RUN_ID) \
		$(if $(GITHUB_STEP_SUMMARY),--summary-md $(GITHUB_STEP_SUMMARY)) --json artifacts/$(RUN_ID)/gate.json

gate3: ## Gate 3 verdict of a full run: strict 3/3 >= 90%, 100% majority, 0 tool errors, one complete commit (REPORT= defaults to the full run of HEAD's source)
	@report="$(REPORT)"; [ -n "$$report" ] || report=$$($(IMPACT) --full-record) || report="history/bench/full-$(SHA7).json"; \
	$(PYTHON) scripts/bench_summary.py --gate3 "$$report" --thresholds $(THRESHOLDS) --bench-dir $(BENCH_DIR)

smoke: ## Post-deploy check: P0 probes x 1 repeat on APP (then `make gate RUN_ID=...`)
	$(MAKE) eval LAYERS=probe PRIORITY=P0 RUNS=1 RUN_ID=$(RUN_ID)

# --- cloud: the Confidence Ladder (bench/runs/<label>.json reports + history/runs.jsonl) ----
bench-dry: need-app ## Print the plan for TARGETS (or all) without cloud calls
	$(PYTHON) scripts/run_bench.py --app $(APP) --bench-dir $(BENCH_DIR) --modality $(MODALITY) \
		$(if $(TARGETS),--evals "$(TARGETS)") --dry-run

bench-smoke: need-app preflight ## Gate 1: TARGETS=VE-01,VE-02 x 3 repeats, go/no-go verdict (measured median about 6 min)
	@test -n "$(TARGETS)" || (echo "Usage: make bench-smoke ENV=staging TARGETS=VE-01,VE-02" >&2; exit 1)
	$(RUN_EVALS) --smoke $(EVAL_COMMON) --targets "$(TARGETS)" --label smoke-$(SHA7)

bench-unstable: need-app preflight ## Gate 2: $(UNSTABLE_SET) x 5 repeats (~15-25 min)
	@test -s "$(UNSTABLE_SET)" && grep -v '^[[:space:]]*\(#\|$$\)' "$(UNSTABLE_SET)" | grep -q . || (echo "ERROR: $(UNSTABLE_SET) is missing or has no uncommented eval IDs (one eval id or display name per line)" >&2; exit 1)
	$(RUN_EVALS) --unstable $(EVAL_COMMON) --unstable-set $(UNSTABLE_SET) --label unstable-$(SHA7)

bench-full: need-app preflight ## Gate 3: every eval x 3 on the pushed commit after a passing smoke-impact (SKIP_SMOKE_GATE=1 REASON="..." overrides); writes history/bench/full-<sha7>.json, rebuilds the impact map, prints Gate 3 (measured 11-29 min, median about 16)
	@$(IMPACT) --app "$(APP)" --check-bench-full --bench-dir "$(BENCH_DIR)" \
		$(if $(filter 1 true yes,$(SKIP_SMOKE_GATE) $(SKIP_IMPACT)),--skip-smoke-gate --reason "$(REASON)",)
	PARALLEL_BATCHES=$(PARALLEL_BATCHES) $(RUN_EVALS) --full $(EVAL_COMMON) --label full-$(SHA7)
	@mkdir -p history/bench
	$(PYTHON) scripts/bench_summary.py "$(BENCH_DIR)/runs/full-$(SHA7).json" --bench-dir $(BENCH_DIR) --out-dir history/bench
	@$(IMPACT) --build-map
	@$(PYTHON) scripts/bench_summary.py --gate3 history/bench/full-$(SHA7).json --thresholds $(THRESHOLDS) --bench-dir $(BENCH_DIR) || \
	  echo "bench-full finished, but this run does not pass Gate 3 (see above). Fix the failures one mechanism at a time: commit, make push, make smoke-impact, make bench-full."

bench: bench-full ## Alias for bench-full (Gate 3)

bench-record: ## Summarise a report into history/bench/: REPORT=$(BENCH_DIR)/runs/full-<sha7>.json
	@test -n "$(REPORT)" || (echo "Usage: make bench-record REPORT=$(BENCH_DIR)/runs/<label>.json" >&2; exit 1)
	$(PYTHON) scripts/bench_summary.py "$(REPORT)" --bench-dir $(BENCH_DIR) --out-dir history/bench

bench-compare: ## Keep/Undo + Failure-Shape verdict: FROM=<before.json> TO=<after.json> [KIND=targeted|hygiene TARGETS=]
	@test -n "$(BEFORE)" && test -n "$(AFTER)" || (echo "ERROR: set FROM=<before.json> TO=<after.json>" >&2; exit 1)
	$(PYTHON) scripts/bench_summary.py --compare "$(BEFORE)" "$(AFTER)" --kind $(KIND) --targets "$(TARGETS)" --bench-dir $(BENCH_DIR)

bench-fetch: need-app ## READ-only: re-fetch finished evaluation runs RUN_IDS=<id,id> into $(BENCH_DIR)/runs/
	@test -n "$(RUN_IDS)" || (echo "Usage: make bench-fetch ENV=staging RUN_IDS=<evaluationRun id,...>" >&2; exit 1)
	$(PYTHON) scripts/run_bench.py --app $(APP) --bench-dir $(BENCH_DIR) --fetch-runs "$(RUN_IDS)"

# --- cloud: telemetry -------------------------------------------------------------------------
chat: need-app need-cxas ## Talk to the agent in the terminal (text)
	$(CXAS) run-session text $(APP)

inspect: need-app need-cxas ## Find conversations containing Q="text"
	$(CXAS) trace search "$(Q)" --app-name $(APP) --match all

trace-triage: need-app need-cxas ## Categorise one conversation: CONV=<conversation id>
	@test -n "$(CONV)" || (echo "Usage: make trace-triage ENV=staging CONV=<conversation-id>" >&2; exit 1)
	$(CXAS) trace triage $(CONV) --app-name $(APP) --app-dir $(APP_DIR)

trace-replay: need-app need-cxas ## Replay one conversation against local code and diff tool/callback outputs: CONV=<id>
	@test -n "$(CONV)" || (echo "Usage: make trace-replay ENV=staging CONV=<conversation-id>" >&2; exit 1)
	$(CXAS) trace replay $(CONV) --app-name $(APP) --app-dir $(APP_DIR)

versions-compare: need-app need-cxas ## Diff two app versions: FROM=<version id> TO=<version id>
	@test -n "$(FROM)" && test -n "$(TO)" || (echo "Usage: make versions-compare ENV=staging FROM=<v> TO=<v>" >&2; exit 1)
	$(CXAS) versions compare --app-name $(APP) --source $(FROM) --target $(TO)

# --- reporting ---------------------------------------------------------------------------------
dashboard: ## Render the static HTML hill-climb dashboard into dashboard/ (title/links from ENV)
	$(PYTHON) scripts/build_dashboard.py --bench-dir $(BENCH_DIR) --app-dir $(APP_DIR) --app "$(APP)" --title "$(AGENT_NAME)"

publish-dashboard: dashboard ## Publish dashboard/ to Zipline: ZIPLINE_PROJECT= ZIPLINE_ASSET=
	@test -n "$(ZIPLINE_PROJECT)" && test -n "$(ZIPLINE_ASSET)" || (echo "ERROR: set ZIPLINE_PROJECT and ZIPLINE_ASSET" >&2; exit 1)
	$(PYTHON) scripts/publish_zipline.py --project "$(ZIPLINE_PROJECT)" --asset "$(ZIPLINE_ASSET)" --dir dashboard
