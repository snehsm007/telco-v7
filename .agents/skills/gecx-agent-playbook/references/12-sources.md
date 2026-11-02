# 12 Sources

## Public (works anywhere)
- **cxas-scrapi** (`GoogleCloudPlatform/cxas-scrapi` on GitHub): the `cxas`
  CLI and Python library.
  - `docs/guides/evaluation/`: eval types, simulations, audio sims, shadow
    evals; `docs/getting-started/quotas.md`.
  - `cxas init` installs its `cxas-agent-foundry` skill into `.agents/skills/`:
    `references/tdd-guide.md` (TDD sections, coverage map),
    `references/eval-templates.md` (YAML specs), `agents/triage-failure.md`
    (fix types), `agents/eval-writer.md`, `scripts/run-and-report.py`,
    `scripts/generate_interactive_report.py`.
  - Other skills in the same repo: CUJ report generator, loss analysis
    (production conversations → new scenarios), sim-eval, composite voice
    optimizer.
- Python/CLI help is the final word on flags: `uv run cxas <command> --help`.
- **gecx-agent-blueprint** (`github.com/cloud-ai-fde/bryankelly-gecx-agent-blueprint`,
  needs access to the `cloud-ai-fde` org): a full reference repo for a larger
  multi-agent voice agent. The source of this kit's Makefile-first, `lib/` +
  bundling, fakes-behind-interfaces, per-file coverage and per-PR preview app
  ideas. Worth reading: `docs/shared_code_and_bundling.md`, `docs/ci-cd.md`,
  `docs/coding_standards_and_tdd.md`, `.github/workflows/pr-validation.yml`,
  and its simulation dashboard (`make dashboard`).

## Google-internal (optional; needs corp access)
If you can't open one of these, say so; don't guess its contents.
- go/cxas-docs: official CX Agent Studio docs (evaluation, best practices).
- google3 `cloud/ai/fde/skills/`: FDE skills, notably
  `cxas_best_practices/issues/*.yaml` (known failure modes with fix prompts),
  `cxas_auto_eval_generator`, `cxas_eval_coverage`, `cxas_scheduled_eval`,
  `cxas_composite_testing` (audio model A/B), `agent_report`.
- google3 `cloud/ai/fde/templates/agents/`: reference agents with goldens.
- `depot.code.corp.goog/experimental/danyals-cxas-best-practices`: eval, prompt,
  tool, callback and mock anti-pattern guides; platform-injected text catalog;
  prompt and tool linters (`linter/cxas_prompt_linter.py`,
  `linter/cxas_tool_linter.py`). Needs a browser sign-in; from a cloud
  workstation, clone on a laptop and copy it over.

## More public references
- **GECX Agent Design Guide** (Google Doc `1ncyyYL6w-VLuj3xLzFGF5T_37b4wUzsFOfiBzxdBvpA`):
  the architecture rules this kit's `AGENTS.md` Rules 1-13 condense (multiple
  agents instead of one long prompt, state passing, latency budget).
- **Slot-filling pattern** (`cxas-scrapi/docs/patterns/slot-filling.md`): the
  reference way to collect required fields across turns without re-asking; use
  it before inventing a collection flow in instructions.
- **cxas-graph skills** (Drive folder `1LWElNzYA4_JMnNm_NUccq04PbcMH9yhy`): graph
  visualisation of agent / tool / callback topology for design reviews.
- **kohinoorc-fde-hub** (`github.com/cloud-ai-fde/kohinoorc-fde-hub`, `cloud-ai-fde`
  org access): FDE hub of CXAS examples, scripts and runbooks beyond the blueprint.
- **"Build and Deploy Customer Experience Agent Studio" course**: the Skills Boost
  path (`partner.skills.google/paths/523/course_templates/1446`) redirects to a
  sign-in, but the same HTML5 course is served unauthenticated from
  `https://storage.googleapis.com/cloud-training/cls-html5-courses/P-BNXGCD-I/content/index.html`
  (lesson JSON is base64-encoded inside `.../content/runtime-data.js`). Lesson 23,
  "Configure the quality hill climbing process", is the official version of the
  Confidence Ladder.

## Bootcamp-specific (Google FDE bootcamp participants)
- **Agent Bootcamp Notes** (Google Doc `1JYaj_GQvtR3UBOEHvoonjH-5oh3XB49Le5vUavbD36A`):
  format, the hidden rubric ("pass context, state pass, latency"), and the tips
  behind `docs/experiment_log.md` and the Keep / Undo rule.
- **Prerequisite Checklist** (Google Doc `1uCrhkPM3w9lDtkOvnwiRKw_AR_8nI_NWwz_nJcljDWw`):
  accounts, tooling and course work to finish before day 1.
- **AAI FDE Learning Series** (`go/aai-fde-training-topics`, Google Doc
  `1Wz9ZkENbza2Edi0Ld43IciP4Phxy_AGh-qQc5IFiAzQ`): topic list and recording archive.
- **Sandbox project**: `fde-bootcamp` (`go/fde-bootcamp-project`), location `us`,
  app naming `<ldap>-[FDE-bootcamp]-<agent>`. From a cloud workstation,
  corp credentials are blocked by Context-Aware Access: run `gcloud auth login`
  and `gcloud auth application-default login` interactively. The automatic
  preflight (`make preflight`, run before every push and evaluation target)
  then shows the ADC identity and quota project and checks the CES
  permissions; run both logins again whenever it fails.
- **Internal reference agent and harness**: google3
  `experimental/users/avanigarg/fdebootcampworkfolder/{totto_agent,GreenfieldAgentBuilding}`
  (the Totto PRD is also public at `cxas-scrapi/examples/mercedes-f1-fan-agent/prd.md`).
- **Rules of the room**: never download or copy another participant's agent
  (several bootcamp repos such as other participants' telco agents are visible in
  the `cloud-ai-fde` org; read for ideas, build your own); commit every score
  improvement and revert any change that lowers the score.
