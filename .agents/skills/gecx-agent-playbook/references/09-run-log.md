# 09 Run log: one history of every eval run

Goal: answer "which tests failed, what's the pass rate, and is the agent getting
better?" for any date, from one file.

## Store
`history/runs.jsonl`: append-only, one JSON object per **test × repeat**,
written by the eval scripts (locally and in CI). Schema:
`assets/run_record.schema.json`. CI appends its rows and commits them to a
`history` branch (or loads them into BigQuery). Don't keep a second,
local-only history: it drifts from CI.

Required fields:
| Field | Why |
|---|---|
| `run_id`, `timestamp` | Group rows into a run |
| `git_sha`, `dirty` | Which code produced it |
| `app_version` | The CXAS version the eval hit (restorable) |
| `agent_model`, `judge_model` | Scores aren't comparable across models |
| `eval_file_sha` | Which version of the test file ran |
| `trigger` | `local`, `pr`, `main`, `nightly`, `release` |
| `test_id`, `layer`, `requirement_ids`, `priority`, `modality` | Report per requirement, per layer |
| `repeat` | 1..N |
| `status` | `pass`, `fail`, `infra_error` |
| `label` | `real`, `judge`, `infra`, or empty for passes |
| `reason` | Grader finding or judge reason (short) |
| `latency_ms_p50`, `reply_chars_max` | Voice health |
| `conversation_id` | Jump to the transcript |
| `change_note` | Why this run happened ("fix REQ-4 dead air") |

## Integrity Rules for `history/runs.jsonl` and `docs/experiment_log.md`
1. **Report all 3 metrics side-by-side, strict first:** Always run with `--repeats 3` (or `--repeats 5` on the unstable set) and record **`strict 3/3 | majority >=2/3 | individual`** side-by-side in `docs/experiment_log.md` and `docs/defects.md` (e.g., `47/50 (94%) | 50/50 (100%) | 147/150 (98.0%)`).
2. **Never write synthetic composite `full-*` records:** Every `full-*` run in `history/runs.jsonl` and `history/bench/` must come from a single unsplit `make bench-full` invocation against one `git_sha` and `app_version`. Never stitch partial or targeted reruns into a synthetic `full-*-composite` record.
3. **Combine visible and holdout only on the same code.** A visible + holdout total is valid only when both runs measured the same code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`; a docs-only or history-only commit in between is fine). After any holdout-driven change, run a full visible `make bench-full` on that code before reporting or re-running the holdout.
4. **Preflight runs automatically before every cloud target** (`push`, `smoke-impact`, `bench-*` and others): it checks the ADC identity, the quota project and the CES permissions before a run starts, so an expired login fails fast instead of stalling a run or writing incomplete records. `SKIP_PREFLIGHT=1` skips it.
5. **No unmeasured durations.** Quote run times and totals only from timestamps you actually have.

## The measured record (`telco-rebuild`, same-commit pairs only; `docs/DESIGN_RULES.md` rule 28)
Strict `3/3` means all 3 tries pass. These are the only visible + holdout combinations to quote:

| Commit | Visible strict 3/3 | Holdout strict 3/3 | Same-commit total | Note |
|---|---|---|---|---|
| `ecf0288` | 16/50 | — | — | first full run (baseline) |
| `0bf79fe` | 46/50 (146/150 runs, 50/50 majority) | 14/20 (18/20 majority) | **60/70** | best visible run |
| `894efde` | not re-run | 18/20 | — | after 3 holdout-driven fix commits (`fe22348`, `1e79e0f`, `894efde`, 29 files) |
| `60f0727` (= `6c704c4` code = `894efde` + DLP) | 38/50 | 16/20 | 54/70 | the same holdout-fixed code, measured later on visible |
| `df6029c` (raw merge of 3 ParetoLoop winners) | 42/50 (only 46/50 majority) | 17/20 | 59/70 | |
| `44cd839` | 41/50 | 15/20 | 56/70 | |
| `1a959d0` (one candidate with 7 fixes merged) | 42/50 | 17/20 | 59/70 | 3 visible tests fell to 1/3 |
| `aa2bed4` (final) | 42/50 (141/150 runs) | 17/20 (57/60) | **59/70** | 69/70 majority, 198/210 runs |

- An older headline added the visible score of `0bf79fe` to the holdout score of `894efde`. That mixes two different versions of the code (the holdout run came after three holdout-driven fix commits) and is wrong; never quote it or any other sum across different code.
- "Holdout fixes preserved 46/50" is wrong: visible was not re-run after them, and the same code later measured 38/50.
- Temperature 0.2 vs 1.0 made no measurable difference (`full-b5f6c72` at 0.2: 41/50 strict, 48/50 majority, 138/150 individual; `full-14ad14c` at 1.0: 40/50, 47/50, 137/150; the set of failing tests kept rotating). The kit keeps 1.0; that decision is final.
- Time: the V2 hill-climb took about 25 hours of wall clock for 16 full runs; about 7 hours went to 5 preventable regressions and about 13 hours to expired Google Cloud logins (ADC).

## Commit messages with deltas
Generate them from the log, e.g.
`agent: answer in the same turn after handoff (REQ-4) — strict 41/50 → 47/50, maj 48/50 → 50/50, ind 138/150 → 147/150`.

## Charts (nightly, from the log)
- Pass rate (`strict 3/3`, `majority >=2/3`, `individual`) per requirement and per layer over time, with a marker on every model or judge change.
- Count of `judge` and `infra` labels (rising `judge` = rubric drift).
- Flaky tests (mixed `2/3` repeats) count.
- Latency p50/p90 and reply length (voice).

## Docs from data
The TDD's "pass-rate history" and "known issues" sections, and any README
badges, are generated from the log. Hand-typed numbers go stale.
