# Defect Log

Group failing evaluations by shared root cause (not one entry per evaluation). Fix one root-cause cluster per commit after verifying with `make impact` and `make smoke-impact`.

### DEF-01: VE-08 simulator never produces silent turns and slot 3 platform judge error
- **Found by**: `VE-08` (`sim__check_ticket_status_retry_strikes`) (`full-32498c1`, `1/3`)
- **Evidence**: `bench/runs/failing_runs_data/full-32498c1/VE-08__44f08f2f__r2.md`, `bench/runs/failing_runs_data/full-32498c1/VE-08__44f08f2f__r3.md`
- **Label**: `judge`
- **Status**: `open`
- **Root cause layer**: `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Slot 2 FAIL (`bench/runs/failing_runs_data/full-32498c1/VE-08__44f08f2f__r2.md`): simulator never produces silent turns ("In the provided conversation, there are no instances of silent turns from the user."). Slot 3 OUTCOME_UNSPECIFIED (`bench/runs/failing_runs_data/full-32498c1/VE-08__44f08f2f__r3.md`): platform judge error (`OUTCOME_UNSPECIFIED`, metric value -1, diagnostic_info: "The conversation does not contain any instances of silent turns.").
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Simulator and platform judge noise; evaluation expectation requires recovery from silent turns that the simulator never injects. No agent code change.
- **Alternatives considered**: None (eval definition and platform judge behavior).
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as simulator/judge noise on `full-32498c1` (1/3 pass).

### DEF-02: VE-04 judge faults user requesting SMS guide before agent offered it
- **Found by**: `VE-04` (`sim__check_outage_none_found_sms_troubleshoot`) (`full-32498c1`, `2/3`)
- **Evidence**: `bench/runs/failing_runs_data/full-32498c1/VE-04__44f08f2f__r3.md`
- **Label**: `judge`
- **Status**: `open`
- **Root cause layer**: `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Slot 3 FAIL (`bench/runs/failing_runs_data/full-32498c1/VE-04__44f08f2f__r3.md`): "Since the agent did not initiate the offer, the expectation is not fully met." (Judge faults user requesting SMS guide proactively before agent offered it).
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Judge noise; user proactively requested SMS troubleshooting guide before agent offered it. No agent code change.
- **Alternatives considered**: Prompt change rejected; agent correctly handled caller-initiated request.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as judge noise on `full-32498c1` (2/3 pass).

### DEF-03: Holdout VE-07 declined card scenario cannot trigger card decline
- **Found by**: Holdout `VE-07` (`holdout-32498c1`, `0/3`)
- **Evidence**: `bench-holdout/runs/failing_runs_data/holdout-32498c1/` VE-07 r1, r2, r3
- **Label**: `judge`
- **Status**: `open`
- **Root cause layer**: `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: All 3 runs FAIL: Scenario expects a card decline flow, but caller simulation guide provides no declining card number. The agent offers the card on file (`4242`), which succeeds because the fake database only declines cards ending in `0000` or `9999` (`lib/fakes.py:38`, `lib/services.py:1188`). Hence, card decline cannot occur.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Platform/scenario noise: guide names no declining card, and `lib/fakes.py:38` / `lib/services.py:1188` correctly enforces `DECLINED_CARD_LAST4`. Modifying card numbers would violate fake-world invariants.
- **Alternatives considered**: None (modifying valid/declined card invariants is strictly prohibited).
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as holdout scenario design noise on `holdout-32498c1` (0/3 pass).

### DEF-04: VE-20 mid-call fraud transfer timing misjudged as not immediate from turn 1
- **Found by**: `VE-20` (`sim__report_fraud_mid_call_switch`) (`full-32498c1`, `2/3`)
- **Evidence**: `bench/runs/failing_runs_data/full-32498c1/VE-20__44f08f2f__r1.md`
- **Label**: `judge`
- **Status**: `open`
- **Root cause layer**: `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Slot 1 FAIL (`bench/runs/failing_runs_data/full-32498c1/VE-20__44f08f2f__r1.md`): "The user was not immediately transferred to the fraud team. The conversation started with the user asking about their bill balance... The transfer to the fraud team only occurred after the user expressed concerns about unauthorized charges, which was several turns into the conversation." In the turn caller first said "hacked", the agent spoke the empathy + handoff line and called `handover_to_person(reason="fraud_escalation", target_queue="fraud_and_security_24x7")` + `end_session` in that same turn. Judge misread "immediately" as "from turn 1".
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Judge timing artifact; caller switched topic mid-call and agent immediately escalated in that turn. No agent code change needed.
- **Alternatives considered**: Prompt change rejected; transfer is already immediate upon the first fraud mention.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as judge timing artifact on `full-32498c1` (2/3 pass).

### DEF-05: VE-12 simulator invented login codes indistinguishable from fact-less auth evaluations
- **Found by**: `VE-12` (`sim__manage_mfa_auth_failure`) (`full-32498c1` 0/3, `full-532d45d` 0/3)
- **Evidence**: `bench/runs/failing_runs_data/full-532d45d/VE-12__af11e5a7__r1.md`, `bench/runs/failing_runs_data/full-532d45d/VE-12__af11e5a7__r2.md`, `bench/runs/failing_runs_data/full-532d45d/VE-12__af11e5a7__r3.md`
- **Label**: `scenario`
- **Status**: `open`
- **Root cause layer**: `platform / scenario`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: All runs FAIL: Guide says provide incorrect codes ×3; the simulator's invented codes (`998877`/`842957`/`482910`…) are indistinguishable from the invented codes 12 fact-less auth evals need accepted on attempt 1 (Rule 21). Fails whenever identification succeeds because invented codes either get accepted or bypass expected lockout.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Recorded noise. Simulator-generated random codes conflict with the need to accept fact-less authentication codes across other evaluations. No agent code change.
- **Alternatives considered**: Rejecting random codes breaks fact-less login in 12 other evaluations.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as simulator/eval design noise (0/3 on full-532d45d).

### DEF-06: VE-24 judge expects literal key string instead of localized verbatim transfer_to_specialist line
- **Found by**: `VE-24` (`sim__request_refund_exceeding_threshold_escalation`) (`full-532d45d`, `2/3`)
- **Evidence**: `bench/runs/failing_runs_data/full-532d45d/VE-24__af11e5a7__r3.md`
- **Label**: `judge`
- **Status**: `open`
- **Root cause layer**: `platform`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Slot 3 FAIL: Agent speaks `transfer_to_specialist` verbatim in every slot, but some judge slots demand the literal key string `transfer_to_specialist` rather than the spoken localized line.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Recorded noise / judge artifact; tool surfaces `verbatim_key: "transfer_to_specialist"` next to spoken/handoff messages.
- **Alternatives considered**: Emitting literal key in agent utterance rejected as unnatural for callers.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as judge artifact (2/3 on full-532d45d).

### DEF-07: VE-41 out-of-service caller cannot authenticate and correctly hands over to human
- **Found by**: `VE-41` (`sim__troubleshoot_mobile_service_french`) (`smoke-db3068f`, `1/3`)
- **Evidence**: `bench/runs/failing_runs_data/smoke-db3068f/` VE-41 r1/r2
- **Label**: `scenario`
- **Status**: `open`
- **Root cause layer**: `scenario`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: "Aucun service" caller cannot receive SMS, has no PIN, and does not recognise the e-mail on file. PRD M4 requires auth before account troubleshooting, so handover to a human representative is PRD-correct.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Scenario conflict: unauthenticated caller cannot proceed with self-serve troubleshooting under PRD M4 security requirements. Handover is PRD-correct behavior. No agent code change.
- **Alternatives considered**: Bypassing authentication would violate PRD M4 security policies.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as scenario design conflict (1/3 on smoke-db3068f, 3/3 on full-532d45d when caller authenticates).

### DEF-08: VE-15 r3: same-turn router lookup_account(fr-CA) → account send_login_code(language=en-US) returned en-US copy
- **Found by**: `VE-15` (`sim__manage_mfa_french_disable`) (`full-c8d6339`, `1/3`)
- **Evidence**: `bench/runs/full-c8d6339.json` VE-15 r3
- **Label**: `platform`
- **Status**: `fixed @e3aa022`
- **Root cause layer**: `agent_transfer`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Slot 3 FAIL: Same-turn router `lookup_account(fr-CA)` → account `send_login_code(language=en-US)` returned en-US copy; the asymmetric lock is not yet visible across the agent transfer inside one turn.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Asymmetric session language lock not yet visible across agent transfer inside one turn. Fixed in `lib/dynamic_prompt.py` (skipping relayed agent context and honouring non-English lock) and `lib/services.py:handover_to_person_impl` (`_session_language`).
- **Alternatives considered**: Recorded as noise / follow-up investigation.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Fixed in `cand/language-sheet-ignores-relay` (`c76bff6` / `e3aa022`): 14/16 strict (87.5%), 16/16 majority (100%), 46/48 individual (95.8%) on `smoke-c76bff6` (VE-02, VE-15, VE-41 all cured to 3/3 PPP).

### DEF-09: VE-12/VE-13: account agent toggles manage_mfa_settings disable→enable→disable in consecutive turns
- **Found by**: `VE-12` (`sim__manage_mfa_auth_failure`) & `VE-13` (`sim__manage_mfa_disable`) (`full-c8d6339`)
- **Evidence**: `bench/runs/full-c8d6339.json` VE-12 r2
- **Label**: `agent`
- **Status**: `open`
- **Root cause layer**: `instruction`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Account agent toggles `manage_mfa_settings` disable→enable→disable in consecutive turns (seen 4× in `full-c8d6339` VE-12 r2).
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: Account agent instruction refinement for MFA toggle stability.
- **Alternatives considered**: Service-side idempotency check vs prompt instruction.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as agent instruction oscillation noise (seen 4× in full-c8d6339 VE-12 r2).

### DEF-10: VE-04 simulator-invented active postal code triggers outage rather than negative check
- **Found by**: `VE-04` (`sim__check_outage_none_found_sms_troubleshoot`) (`smoke-c55b43d`, `smoke-f0863fa`)
- **Evidence**: `bench/runs/failing_runs_data/smoke-c55b43d/VE-04__c50b72f8__r1.md`, `bench/runs/failing_runs_data/smoke-f0863fa/VE-04__e2bddd89__r2.md`
- **Label**: `eval-design`
- **Status**: `open`
- **Root cause layer**: `platform / scenario`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: VE-04 evaluation expectation requires offering an SMS troubleshooting guide after a negative outage check ("The user is offered and accepts an SMS troubleshooting guide after the outage check returns negative"). However, the VE-04 user guide specifies no postal code ("The user provides their postal code..."), and the simulator invents the canonical sample Montréal postal code `H*Z *Y*` (`H3Z 2Y7`), which is the exact code required by VE-03 to simulate an active regional outage.
    - Quoted caller lines (digits masked):
      - `smoke-c55b43d` (`c50b72f8…`, slot 1): `"Internet is down. Check for an outage in H*Z *Y*."`
      - `smoke-f0863fa` (`e2bddd89…`, slot 2): `"Hello. I'm currently working from my home office and my internet has gone down. I would like to check if there is a known outage in my area. My postal code is H*Z *Y*. Could you please verify this for me?"`
    When `check_regional_outage` returns `outage_active: true`, the agent correctly offers restoration updates rather than a troubleshooting guide, failing the negative-check prerequisite.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: None on agent side. The collision is an eval-design limitation since both evaluations share the same phone/account profile and simulator-invented postal code `H3Z 2Y7` cannot be distinguished from intentional VE-03 active outage queries. The exact-match change in `cand/outage-region-exact` (`lib/fakes.py:53`, `lib/services.py:613,1151`) restricts active outage reporting to exact `H3Z2Y7`, removing prefix false positives for any other invented `H3Z xxx` codes (e.g., `H3Z 1A1`).
- **Alternatives considered**: None on agent side; altering fake database to report no outage for `H3Z 2Y7` breaks VE-03.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: 2/3 on `smoke-f0863fa` (`e2bddd89…`, slots 1 and 3 passed 3/3; slot 2 hit postal code collision).
- **Update**: exact match reverted on main: holdout VE-03 regressed 3/3→0/3 in `holdout-d661067`.

### DEF-12: Persona rejects on-file fixture data (e-mail starting with another initial, card not recognised)
- **Found by**: `VE-13` (`sim__manage_mfa_disable`) & `VE-17` (`sim__pay_mobility_bill_card_file`)
- **Evidence**: `VE-13` r2 smoke `f3ff955f-eb9b-4b88-9d87-fef3c08c6702`, `VE-17` r3 smoke `4723f21b-6231-4da4-adb6-c8b23c9ca4d5`, `VE-17` r2/r3 smoke `9b026cc9-7b05-45be-b8b8-e2176020c70e`
- **Label**: `eval-design`
- **Status**: `open`
- **Root cause layer**: `platform / scenario`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Simulator persona vs fixture: caller rejects legitimate on-file fixture records (e-mail starting with another initial, card not recognised) when agent recites on-file records.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: No agent fix (would be persona tuning / overfitting to simulator habits, prohibited by owner rule).
- **Alternatives considered**: Persona tuning prohibited by owner rule.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as simulator persona vs fixture conflict.

### DEF-13: Shared ledger fixture: callers on addendum phone share account with `is_suspended=false`
- **Found by**: `VE-31` (`sim__restore_service_standard`)
- **Evidence**: `VE-31` r2 `full-0f3b8a0` (`projects/google.com:nextgen-sandbox/locations/us/apps/25e84665-a03d-45b9-8212-23e314db5c14/evaluationRuns/a8b70e9d-8b02-4957-ad25-1ef557c1577a`, slot 2)
- **Label**: `fixture-limitation`
- **Status**: `open`
- **Root cause layer**: `fixtures / fakes`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Callers on the addendum phone share one account whose `is_suspended=false`, so a restore scenario cannot present a suspended line unless the session paid/reported a payment (#14); evidence VE-31 r2 `full-0f3b8a0`.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: No fix — deriving suspension from a caller's claim would be persona mirroring.
- **Alternatives considered**: None on agent side.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as fixture limitation.

### DEF-14: Simulator deviates from its own guide (skips required wrong-PIN retry)
- **Found by**: `VE-09` (`sim__dispute_charge_auth_retry`)
- **Evidence**: `VE-09` r3 `full-0f3b8a0` (`projects/google.com:nextgen-sandbox/locations/us/apps/25e84665-a03d-45b9-8212-23e314db5c14/evaluationRuns/c9b9740b-c03e-4616-bf11-3b95a63d8c8e`, slot 3)
- **Label**: `eval-design`
- **Status**: `open`
- **Root cause layer**: `platform / scenario`
- **Diagnosis (all 3 judge metrics)**:
  - *Expectations*: Simulator deviates from its own guide (skips the required wrong-PIN retry); evidence VE-09 r3 `full-0f3b8a0`.
  - *User Goal*: Skipped via config (score -1)
  - *Hallucination*: Skipped via config (score -1)
- **Fix & `file:line`**: No fix — simulator persona skipping its own guide steps cannot be cured on agent side.
- **Alternatives considered**: None on agent side.
- **Verification (`strict 3/3 | majority >=2/3 | individual`)**: Classified as simulator non-determinism / deviation.

