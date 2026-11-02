# environments/<name>.mk — one file per target app, loaded by `make <target> ENV=<name>`.
# Copy to environments/staging.mk (and environments/live.mk) and fill in.
# `make kickstart` writes a staging.mk from --project-id / --location / --agent-name.
PROJECT_ID := <gcp-project>
LOCATION   := <location, e.g. us>
# App id from the console URL (…/apps/<id>) or the resource name `cxas push` prints.
# The display name also works: run_bench resolves it, but prefer the real id.
APP_ID     := <app id>
# Used for per-PR preview apps (<AGENT_NAME>-pr-<n>) and the dashboard title.
AGENT_NAME := <agent-name>
# Model sampling temperature: 1.0 is final (voice-audit rule A010). 0.2 made no measurable
# difference on text evals (run #9: 41/48/138 at 0.2 vs 40/47/137 at 1.0, strict/majority/individual).
TEMPERATURE ?= 1.0
# Set to 1 to run evaluation batches with 2x concurrency (ThreadPoolExecutor(max_workers=2)).
PARALLEL_BATCHES ?= 1
# Optional Zipline publishing targets for `make publish-dashboard`.
# ZIPLINE_PROJECT := <zipline-project>
# ZIPLINE_ASSET   := <zipline-asset>
