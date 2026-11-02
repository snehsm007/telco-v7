# Experiment Log

Every cloud evaluation run and hill-climb iteration is logged here in chronological order.
Always report **Strict `3/3`** first, then **Majority `>=2/3`**, then **Individual** pass rates, side-by-side (never composite slices across runs/SHAs).
Gate 3 (`make gate3`) requires **Strict `3/3` >= 90% AND 100% Majority (`>=2/3`, zero `0/3` or `1/3` evals)** with `0` tool runtime errors, from one complete, single-commit full run.
Add a holdout result only when it ran on the **same code** as the full run in that row (same source fingerprint of `cxas_app/`, `lib/` and `evals/`; a docs-only or history-only commit in between is fine); never add visible and holdout scores measured on different code.

| Iteration | Date (UTC) | Commit | Mechanism / Change | Impact Verdict (`make smoke-impact`) | Strict `3/3` | Majority `>=2/3` | Individual | Holdout strict `3/3` (same code only) | Decision / Keep? | Full Run ID & Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | YYYY-MM-DD | `<sha>` | Kickstart baseline (`make kickstart`) | — | `0/0 (0%)` | `0/0 (0%)` | `0/0 (0%)` | — | baseline | `full-<sha>` |
