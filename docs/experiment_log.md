# Experiment Log

Every cloud evaluation run and hill-climb iteration is logged here in chronological order.
Always report **Strict `3/3`**, **Majority `>=2/3`**, and **Individual** pass rates side-by-side (never composite slices across runs/SHAs).
Gate 3 requires **Strict `3/3` >= 90% AND 100% Majority (`>=2/3`, zero `0/3` or `1/3` evals)** with `0` tool runtime errors.

| Iteration | Date (UTC) | Commit | Mechanism / Change | Impact Verdict (`make smoke-impact`) | Strict `3/3` | Majority `>=2/3` | Individual | Decision / Keep? | Full Run ID & Notes |
|---|---|---|---|---|---|---|---|---|---|
| ADR-36 | 2026-11-04 | `0d3243e` (`fix/unsupported-language-policy`) | PRD-strict unsupported-language policy (`language_not_supported` trilingual notice on strike 1, `secondary_language_live_agent` handover on strike 2, switch-to-supported recovery) | `FULL` (`smoke-0d3243e` on `759c10d4...`: `GATE 1: go`, 0 tool errors, 0 hallucinations) | `20/21` (95.2%) | `21/21` (100.0%) | `62/63` (98.4%) | Keep (candidate verified; `VE-71` 3/3, `VE-72` 3/3) | `evaluationRuns/5f26ab12-03b9-4feb-98eb-f7936087628f` |

