# 03: The design doc (TDD)

Write `docs/tdd.md` from `assets/tdd.md` after the scenarios are approved.
**Update the TDD before changing evals or code**, and keep it true: tests
should check its key claims (tool names, argument values, agent list) against
the code.

## Required sections
1. **Architecture**: agents and why. `make kickstart` writes a `router` (greets,
   finds the account, routes) and one `specialist` per PRD module; one agent is
   fine for a PRD with one job. For each extra agent, say which failing scenario
   proves it's needed. Draw the routing.
2. **Tools**: for each tool:
   - name, purpose;
   - every input with type and **allowed values**;
   - the return shape;
   - the error cases;
   - the data source (live API or snapshot), and freshness.
   - Use one return shape for every tool (`lib/replies.py`): `status`, `data`,
     `error_message`, `tracking_id`; errors add `error` (a fixed code from
     `ERROR_CODES`) and `agent_action`.
   - Money is a number plus a 2-decimal display string and a currency
     (`amount: 85.5`, `amount_display: "85.50"`, `currency: "CAD"`; the
     generated `lib/replies.py` has `display_amount()` for the string).
   - Every field, allowed value and timeline the PRD fixes is listed here and
     has a contract test.
   - The scaffold starts with six tools: `lookup_account`, `send_login_code`,
     `check_login_code`, `check_secret_pin`, `submit_request` (rename it after
     the PRD's task) and `handover_to_person`.
3. **Routing / handoffs**: who hands to whom, and what is passed along.
   Sub-agent transfers are silent (emit only the transfer tool call; the
   receiving sub-agent answers in the same turn). Human handovers
   (`handover_to_person`) speak the required transfer line (step-specific
   override or generic line), call `handover_to_person`, and call `end_session`
   in the same turn (`docs/DESIGN_RULES.md` rules 5, 7, 20).
4. **State**: flat, typed session variables, who writes each one (which tool or
   callback), and which must survive handoffs (`language` with default `""`,
   `account_id`, `logged_in`, `card_last4`, `last_payment_method`,
   `handover_complete`, `handoff_message`).
5. **Callbacks**: keep only `speech_hygiene` (`after_model_callback`) attached to
   **every** agent (root-agent callbacks don't run for sub-agents). It cleans
   reply text and injects `handoff_message` only when a handover reply has no
   text. Never add `before_tool` `auth_gate` or `before_model` `turn_state`
   callbacks (`docs/DESIGN_RULES.md` rule 16).
6. **Voice and channel rules**:
   - plain text only
   - no markdown, emoji or URLs
   - IDs and numbers read in groups
   - maximum spoken reply length
   - greet once
   - how to handle silence and interruptions
   - the model and voice for each channel
7. **Policies**: refusals, sensitive data, disclosures, escalation. Each maps to
   a REQ.
8. **Coverage map**: REQ → scenarios → eval type → eval name → gated?
9. **Test data**: fixtures for every tool (valid, invalid, edge), plus the oracle
   for time-dependent facts.
10. **Acceptance bars**: pass rates stated strict `3/3` first, then majority,
    then individual (Gate 3: strict `3/3` ≥ 90% and 100% majority), latency
    targets, and the models they were measured on.
11. **Known issues**: open defects with IDs.
12. **Changelog**: date, change, reason, score before → after.

🧑 Get approval before building.
