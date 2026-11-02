# Scenarios (CUJs)

One row per scenario. Buckets and near-twins: see the playbook's
`references/02-scenarios.md`. A P0 requirement without a gated scenario is a
bug (a test enforces this).

| ID | REQ | Bucket | Lang / channel | User says (gist) | Correct behavior | Near-twin of | Eval type | Eval name | Priority | Gated? |
|---|---|---|---|---|---|---|---|---|---|---|
| S-1 | REQ-1 | happy | en / text | | | | golden | | P0 | yes |
| S-2 | REQ-1 | ambiguous | en / voice | | | S-1 | sim | | P0 | yes |

## Coverage summary
| REQ | # scenarios | Buckets covered | Gated? |
|---|---|---|---|
| REQ-1 | | | |
