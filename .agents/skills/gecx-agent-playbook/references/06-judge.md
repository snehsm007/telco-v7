# 06 Keeping the LLM judge honest (and understanding the 3 platform judge metrics)

The **judge** is the Large Language Model (**LLM**) that reads a simulation transcript and grades whether the conversation succeeded. A weak judge or a misunderstood judge metric makes every evaluation score misleading.

---

## The 3 Platform Judge Metrics (The Composite Verdict)

On **Google Customer Experience Agent Studio** (**CXAS** / **CES**), a simulation conversation passes **only when all three independent judge dimensions pass** (the **Composite Verdict**):

| # | Judge Dimension | What It Checks | Common Failure Trap & How to Fix It |
|---|---|---|---|
| **1** | **Custom Behavioral Expectations** | Deterministic rubric assertions defined per scenario (e.g., *"The conversation remains strictly in French Canadian"*, *"Agent states the verbatim transfer line and confirmation ID"*). | **Trap:** The LLM paraphrases a mandatory sentence or leaks English metadata from a tool output.<br>**Fix:** Put spoken lines in the prompt in every language the PRD needs (`docs/DESIGN_RULES.md` rule 5); tools return structured data (codes, numbers, masked digits), never sentences (except `handover_to_person` returning `spoken_message = SPOKEN_LINES[lang]["handover"]`, backed by `speech_hygiene` when `end_session` fires on the same turn); let `speech_hygiene` sanitize output without brittle text guards (`DEF-25`, `DEF-28`). |
| **2** | **User Goal Satisfaction** | Grades dialogue termination as:<br>• `Task Completed (1.0)`<br>• `Graceful Handoff (1.0)`<br>• `Task Not Completed (0.0)` (*"Partial Completion is Failure"*). | **Trap (The Turn-1 Router Handover Trap, `DEF-05`, `DEF-26`, `DEF-37`):** When an agent escalates a caller on Turn 1 or after a lockout without closing the session cleanly, the User Goal judge often scores `Task Not Completed (0.0)`.<br>**Fix:** Both halves are required (`docs/DESIGN_RULES.md` rule 7): (a) `handover_to_person` returns `status: "ok"`, `tracking_id`, `spoken_message`, `handoff_message`, `handoff_status: "completed_via_specialist_queue"`, `action_fulfilled: True`, `task_completed: True`, `user_goal_fulfilled: True`, and a structured `handoff_summary` (carrying reference number, caller goal, and auth progress per rules 4 and 10), **and** (b) the agent speaks the verbatim transfer sentence, calls `handover_to_person`, and calls `end_session` in that **same turn** (with `speech_hygiene` injecting `handoff_message` only if the reply has no text). |
| **3** | **Hallucination & Grounding** | Compares every factual statement spoken by the agent against the structured tool outputs in that turn (`Justified (1.0)` vs. `Not Justified (0.0)`). | **Trap 1 (Ungrounded Policy/Detail or Helpful Embellishment, `DEF-30`, `DEF-35`, `DEF-41`):** The agent states a true fact (`"before applicable taxes"`, `"$0.00 setup fee"`, `"14-day return window"`) or adds ungrounded conversational embellishments (delivery timelines, follow-up promises, refund arrival dates, credit bureaus) not present as an explicit key in the tool response dictionary.<br>**Trap 2 (Two-Step Pre-Action Disclosure Before Confirmation):** On Turn 1 of a two-step flow, the agent states the fee, proration rule, or warning before calling the action tool (`caller_confirmed=True` runs on Turn 2). Fix: embed the pre-action disclosure fields (`early_termination_fee`, `cancellation_effective`, `proration_policy`, `auto_pay_warning`) directly in the lookup/login tool responses (`lookup_account`, `check_login_code`, `check_secret_pin`) so Turn 1's disclosure is 100% grounded.<br>**Trap 3 (Account ID With Letters Turned Into a Phone Number, learned in an earlier build):** a lookup that strips the letters from an account ID that mixes letters and digits can invent a phone number ending, which the agent then reads aloud as the number on file. Fix: synthesize a phone only from a 9–10 digit identifier with no letters (`not any(c.isalpha() for c in raw)`, `docs/DESIGN_RULES.md` rule 22).<br>**Trap 4 (Declined Card Ending Reused or Mentioned on Retry, learned in an earlier build):** After a card decline, `card_last4` stays in session state or the agent repeats the declined card's digits. Fix: clear `state["card_last4"] = ""` on decline and set `last_payment_method` (`docs/DESIGN_RULES.md` rule 24).<br>**Trap 5 (Same-Turn Passcode Send + Sub-Agent Transfer, `DEF-33`, or Ticket ID Mismatch, `DEF-32`):** Have each specialist run its own login (rule 2) and align IDs deterministically across tools (rule 10). |

**Rule:** Before writing any code for a failing evaluation, record **all three judge metrics** for every failing repeat in `docs/defects.md`. A fix that flips Custom Expectations from `0/3` to `3/3` will still score `0/3` overall if User Goal or Hallucination is still failing!

---

## Rules for Keeping Grading Honest
1. **Strong judge.** Use a judge model at least as capable as the agent model (`--eval-model` on `cxas evals report` or `eval_model` in `scripts/run_evals.py`). Record the judge model in `gate_thresholds.json` and every run record.
2. **Deterministic code checks (`suite/grader.py`) override the LLM judge.** Run `suite/grader.py` on every transcript (simulations, goldens, probes, audio transcripts). A code-check `FAIL` always overrides a judge `PASS`. Code checks catch failures that LLM judges routinely miss:
   - Python or tool-call code printed or spoken (`default_api.foo(...)`);
   - specific facts stated before the tool that provides them was called (`fact_before_tool`);
   - `"Let me check..."` followed by silence or a raw transfer (`dead_air_handoff`);
   - reply language different from the locked call language;
   - internal agent or tool identifiers (`router`, `specialist`, `evaluate_routing_rules`) leaked in spoken replies;
   - markdown (`**bold**`, bullet lists), URLs, or emoji in voice replies, or replies exceeding voice length limits;
   - platform fallback text (`"Hmm, I'm having trouble with that..."`) counted as a normal agent turn.
3. **Arithmetic invariant.** A simulation repeat passes only if **all** expectations pass **AND** User Goal passes **AND** Hallucination passes **AND** `suite/grader.py` reports 0 errors. Use SCRAPI's `triage-results.py` (in the `cxas-agent-foundry` skill) to flag `SCORES_PASS_BUT_FAIL` discrepancies across a run, and `make trace-triage CONV=<id>` (`cxas trace triage`) to categorize one conversation.
4. **Calibration set (`evals/calibration/`):** Maintain 20–40 saved transcripts hand-labelled pass/fail per expectation, including tricky edge cases (spoken code, invented facts, fact-less simulated callers volunteering numbers, Turn-1 handovers). Re-grade `evals/calibration/` whenever the judge model, expectation wording, or `suite/grader.py` changes. Target ≥90% agreement.
5. **Label every failure** as `real`, `judge`, or `infra` (see [07-failure-loop](07-failure-loop.md)). Track the `judge` count over time; a rising `judge` count indicates rubric drift.
6. **Read passing transcripts too.** Sample 2–3 passing transcripts per run to verify the agent isn't passing via a loophole.
7. **Gate 0 Offline Mutation, Eval-Contract & Tool-Breakage Testing (`scripts/verify_mutations.py`, `make eval-contract`):** Before trusting your local test suite or pushing to staging, run `make ci` (which runs `python3 scripts/verify_mutations.py` and, when `bench/dev/evaluations` exists, the eval contract that `make eval-contract` also runs). It deliberately injects bugs into your tools and callbacks and verifies that your tests fail on 100% of injected mutations, and checks that no `ALWAYS_WRONG_*` value collides with positive eval fixtures (`docs/DESIGN_RULES.md` rule 23).
8. **Watch for overfitting:** Visible evaluations going up while the holdout, measured on the same code, goes down means fixes were overfitted to specific test strings instead of fixing the underlying root-cause cluster. Compare visible and holdout only on the same code (same source fingerprint of `cxas_app/`, `lib/` and `evals/`).

---

## Writing Expectations the Judge Can Grade Reliably
- **One observable behavior per expectation.**
- **Specify order and observable content:** *"Calls `check_regional_outage` and states whether an outage is active before offering troubleshooting steps."*
- **Avoid subjective adjectives** (*"appropriately"*, *"politely"*, *"helpful"*) unless paired with an observable criterion.
- **Avoid conflicting currency or terminology traps (`DEF-27`, `DEF-40`):** If a caller may say `"PIN"` while a tool says `"verification code"`, ground both terms in the tool data dictionary so both terms are justified. If an evaluation rubric checks for specific localized amounts or formats, ensure the tool data dictionary provides the expected values (`docs/DESIGN_RULES.md` rule 10).
