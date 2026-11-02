# Defect Log

Group failing evaluations by shared root cause (not one entry per evaluation). Fix one mechanism per candidate: commit, `make push ENV=staging`, then verify with `make smoke-impact ENV=staging` (strict `3/3` on every impacted evaluation) before `make bench-full` and `make gate3`.

### DEF-01: <one-line symptom>
- **Found by**: `<eval_ids>` (`<run_id>`, `<pass_rate>`) / `verify_mutations.py` / `pytest`
- **Label**: `real` | `judge` | `infra`
- **Status**: `open` | `fixed in <commit>` | `reverted in <commit>`
- **Root cause layer**: `prompt` | `tool` | `callback` | `fake data` | `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: <pass/fail + verbatim judge reasoning>
  - *User Goal*: <pass/fail + verbatim judge reasoning>
  - *Hallucination*: <pass/fail + verbatim judge reasoning>
- **Fix & `file:line`**: <one mechanism changed and exact `file:line`>
- **Alternatives considered**: <what else was tried or ruled out>
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: <before -> after on `smoke-impact` and `bench-full`>

