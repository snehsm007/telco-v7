<!-- =====================================================================
  GECX AGENT PULL REQUEST TEMPLATE
  Please review AGENTS.md, docs/git-workflow.md, and docs/ci-cd.md.
  All sections below are required. For non-conversational PRs (e.g. docs-only,
  pure unit tests), mark interactive sections as N/A with rationale.

  CONTINUOUS SYNCHRONIZATION:
  Whenever new commits are pushed, amended, or rebased, update both the PR title
  and description to reflect the latest changes, test results, and links.
====================================================================== -->

### Description
<!-- Explain the business problem, caller impact, and 5-Part Engineering Rationale:
     (1) Prior Failure Diagnosis (conversation IDs + failing judge metrics),
     (2) What Changed, (3) Why This Fix Works, (4) Exact file:line References,
     (5) Alternatives Considered & Why Rejected. -->
{Provide background context, caller impact, or problem statement.}

Previously, {explain what the agent did before this change}. This change adds:
1. **{Core Feature / Turn}**: {What it does / what the agent says or does}
2. **{Happy Path / Opt-In}**: {e.g. Successful confirmation or downstream transfer}
3. **{Edge Case / Recovery}**: {e.g. Disambiguation, cancellation, or fallbacks}

**References**:
- PRD Requirement: `REQ-{N}`
- Defect Cluster: `DEF-{NN}` (in `docs/defects.md`)
- Architecture / TDD: `docs/tdd.md`

---

### Tests & Cloud Evaluation Gate

**Offline Gate 0 (`make ci`)**: {PASS_COUNT}/{TOTAL_COUNT} unit tests passing, >=80% per-file coverage, `bundle-check` + `overfit-check` + `cxas lint` clean.
<details>
<summary>Click to view Unit Test Coverage Breakdown</summary>

| File | Test File | Coverage | Status |
| :--- | :--- | :--- | :--- |
| `cxas_app/tools/{tool}/.../python_code.py` | `tests/test_tools.py` | 100% | PASS |
| `lib/{module}.py` | `tests/test_{module}.py` | 100% | PASS |
| **Full Repo Suite** | `make ci` | **>=80%** | **PASS** |

</details>

**Cloud CES Evaluation Runs (`evaluationRuns`)**:
<details>
<summary>Click to view Cloud Evaluation Results (3 Judge Metrics)</summary>

| Eval ID / Scenario | Custom Expectations | User Goal | Hallucination / Grounding | Cloud Run ID |
| :--- | :--- | :--- | :--- | :--- |
| `{EVAL_ID_1}` | PASS | PASS | PASS (`Justified`) | `evaluationRuns/{UUID}` |

</details>

---

### Try It Out

- **Interactive Preview App**: Provisioned automatically by `pr-validation.yml` (`<agent>-pr-<PR_NUM>`) when GCP WIF secrets are configured.
- **Sample Conversation**:
  <details>
  <summary>Click to view Turn-by-Turn Walkthrough</summary>

  1. **Caller**: *"{User utterance}"*
  2. **Agent**: *"{Agent response}"*
  3. **Caller**: *"{Follow-up utterance}"*
  4. **Agent**: *"{Verified response or action}"*

  </details>

---

### Quality & Compliance Checklist

- [ ] Branch follows convention (`fix/<n>-<slug>`, `feat/<scope>-<desc>`, `sync/...`, `epic/...`) and targets the correct base branch.
- [ ] Shared code was edited in `lib/` and inline bundles regenerated via `make bundle`.
- [ ] `make ci` passed locally (`bundle-check`, `overfit-check`, `cxas lint`, `pytest` >=80% per-file coverage, `verify_mutations.py`).
- [ ] Cloud evaluation pass rates are backed by real server-side `evaluationRuns` IDs (never offline unit tests).
- [ ] No failing test or evaluation expectation was relaxed without human approval.
