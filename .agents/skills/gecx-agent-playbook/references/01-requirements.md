# 01: PRD → numbered requirements

Goal: a list every later artifact can point to. If a test can't name the
requirement it protects, it's either missing a requirement or testing nothing.

## Steps
1. Read the whole PRD. List every "must", "should", acceptance criterion,
   policy, persona rule and non-functional target (latency, languages,
   channels).
2. Give each one an ID `REQ-n` and one line in `docs/requirements.md`:
   - **Priority:**
     - P0 = launch-blocking; the business fails without it.
     - P1 = important.
     - P2 = nice to have.
   - **Type:** journey / policy (must not) / persona / non-functional / data.
   - **Acceptance:** the observable behavior that proves it, in one sentence.
     "Agent gives the store's opening hours from the hours tool", not
     "Agent is helpful".
   - **PRD source:** section or line.
3. Separate out **open questions** (ambiguity, missing data, conflicting
   statements) and **assumptions** (what you'll do if nobody answers). Never
   silently fill a gap.
4. Also capture what the PRD **forbids**: out-of-scope topics, actions the
   agent must never take, sensitive data, required disclosures, the escalation
   policy. Each one is a requirement with its own ID. These are the
   most-failed areas in practice.
5. Fill the **data contract** table in `docs/requirements.md`: every field,
   allowed value (enum) and timeline the PRD fixes, the tool that must return
   it, and the contract test that checks it. Earlier builds lost tests to
   exactly these gaps: a missing required field, a timeline that contradicted
   the PRD, and an enum value spelled differently from the PRD (`"bank"` where
   the contract said `"bank_account"`).
6. 🧑 Ask for approval. Changes to requirements after approval go in the
   changelog at the bottom of `docs/requirements.md`.

## Checks
- Every P0 requirement has an acceptance sentence a test could check.
- Every "must not" in the PRD has a requirement.
- Every PRD field, allowed value and timeline is in the data contract table
  with a contract test.
- Every amount the agent says is returned as a number plus a 2-decimal display
  string and a currency (`amount: 85.5`, `amount_display: "85.50"`,
  `currency: "CAD"`): an agent once read `85.5` aloud as "85.5 $".
- Channel and language requirements exist, even if they're implicit (e.g.
  "phone line" means voice rules).
