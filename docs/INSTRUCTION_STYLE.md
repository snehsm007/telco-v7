# Instruction style: how to write `instruction.txt`

Every agent instruction in this repo uses **one layout**. Why it matters:

- **The model follows it more reliably.** Short, named steps with one
  condition each beat paragraphs of "if… otherwise…".
- **Tools can read it.** Flow-map tools, stricter prompt checkers and
  humans can all find "the step that does X".
- **The official linter won't catch a bad layout.** `cxas lint` only checks
  that `<role>`, `<persona>` and `<taskflow>` exist and that the taskflow
  has *some* child (rules I001/I002). A `<step>` holding a bare sentence like
  `If the caller asks X, do Y.` gets 0 errors. A previous build shipped
  every step that way, and nobody noticed until a flow-map tool drew nothing.

Sources: the official SCRAPI instruction design guide
(`docs/design-guide/instruction-design.md` in the cxas-scrapi repo) and
Danyal's CXAS prompt best practices (`cxas_prompt_engineering_best_practices.md`,
section numbers below; see `references/12-sources.md` in the playbook).

## Layout

1. **Top-level tags, in this order:** `<role>`, `<persona>`,
   `<response_protocol>`, `<taxonomy>` (routing agent only), `<constraints>`,
   `<taskflow>`. *(SCRAPI guide; Danyal §1)*
2. **Every step sits inside a named subtask.** Every
   `<step name="…">` has exactly one `<trigger>` (when it starts) and one
   `<action>` (what to do). *(SCRAPI guide; Danyal §3, §19)*
3. **Names are Title Case and unique.** Start each subtask name with the
   PRD module or journey ID (e.g. `M3 Billing Inquiry`), so every box on a
   flow map points back to the PRD. *(Danyal §2, plus a traceability rule of our own)*
4. **Tools and agents are written `{@TOOL: exact_name}` and
   `{@AGENT: exact_name}`**, using the exact registered name with no
   invented suffixes. *(Danyal §5, §28)*

## Steps and triggers

5. **One tool call per step.** Tool inputs go in a short list under
   `Call {@TOOL: name} with:`, one `- input_name: value` per line. A tool
   result starts the next step, whose trigger names that result
   (`{@TOOL: name} returned error="NOT_FOUND"`). *(Danyal §5, §7, §41)*
6. **One condition per trigger.** No "if… otherwise if…" chains inside an
   action; split them into separate steps. Always include a dedicated
   `<step name="Code Not Received">` in the login subtask: if the caller says
   they did not receive the login code, offer to resend once (`send_login_code`),
   then offer the alternate channel (`sms` ↔ `email`), then offer secret PIN
   verification (`check_secret_pin`) — never volunteer a human transfer just
   because a code was not received (learned in an earlier build).
   *(Danyal §12; PAP-12)*
7. **Triggers describe what the user means**, not example phrases or
   keyword lists. *(Danyal §9, §33; PAP-7)*
8. **Move between subtasks; never write "go to step X".** *(Danyal §37)*
9. **Say what to do, not "Do NOT call X".** If a case must be excluded,
   give it its own earlier step. *(PAP-1; `cxas lint` I004)*
10. **Asking and doing are separate turns.** Ask for consent in one step;
    act on the "yes" in the next. *(Danyal §14; PAP-14)*

## Speaking

11. **`Say:` lines have no quote marks, and never embellish beyond tool output**
    (`Say: Thanks, I found your account.`). State ONLY facts, amounts, dates,
    confirmation codes, and policy rules explicitly returned by a tool in this
    session. Never invent or extrapolate security explanations, fee/tax
    breakdowns, billing-cycle timing, cancellation effective dates, or safety
    tips that were not returned in a tool payload (learned in an earlier
    build). *(Danyal §18; PAP-15)*
12. **Exact-wording lines** (legal notices, disclosures from the PRD) are
    copied character for character. Name the PRD key in the step name.
    - **12a. Pre-action disclosure for two-step confirmations:** When a workflow
      requires disclosing a policy (for example, an administrative fee or
      billing-cycle rule returned by the lookup/auth tool) and getting caller
      confirmation before calling the action tool, state that exact pre-grounded
      policy and ask for confirmation before invoking the action tool.
13. **Every turn that doesn't end the conversation finishes with a question
    or a clear next step** for the user. *(Danyal §46)*
14. **Silent sub-agent transfers vs. spoken one-turn human handovers.** In
    `<response_protocol>`, state: *"For normal tool calls, emit the tool call
    first and wait for its result before speaking. Sub-agent transfers are
    silent. EXCEPTION — Handover to a person (`handover_to_person`): in a
    SINGLE turn, speak the required closing/transfer sentence (using the
    step-specific transfer line if the current workflow step defines one,
    otherwise the generic transfer line), call `handover_to_person`, and call
    `end_session` together."* *(DESIGN_RULES.md Rules 5, 7, 20)*

## Rules vs. flow

15. **`<constraints>` holds only rules that apply on every turn**, written
    as `On [situation]: [do this]`. Anything step-by-step goes in
    `<taskflow>`. *(Danyal §17, §47; PAP-17)*
16. **Each rule lives in exactly one place.** Rules shared by every agent
    go in `global_instruction.txt`. *(Danyal §4)*

## Data and state

17. **Never type facts from tools/data into instructions, and never greet or
    thank the caller by `first_name` from the fake profile.** Never put
    balances, dates, names, URLs, or IDs into instructions; use obvious
    placeholders like `[account number]`. Do NOT address the caller by the
    `first_name` returned by `lookup_account` or login tools: in cloud
    evaluations, fact-less simulated callers invent their own persona names
    while resolving against the default fake profile, so calling a
    simulated caller by the fake profile's `first_name` derails the
    conversation. Confirm verification using the action status and account
    details requested by the caller, never the profile's `first_name`.
    *(PAP-20; AGENTS.md rule 3; DESIGN_RULES.md Rule 21)*
18. **Variables:** `{var}` for values that change during the conversation,
    `{{var}}` for fixed values. Never `$session.params`. *(Danyal §6; PAP-4)*
19. **The model never writes state.** Only tools and callbacks do.
    *(AGENTS.md rule 15)*
20. **The routing agent's `<taxonomy>` lists the intent labels exactly as the
    routing code expects them**, and nothing else. *(Danyal §49)*

## Tool calls

21. **No filler line before a tool call.** Don't tell the model to say
    *"One moment while I check that"* before calling a tool. In an earlier
    build the model sometimes spoke the filler as a whole turn and skipped the
    tool call, which stranded the conversation (see "Pre-Tool Pacing Phrases"
    in [WHY_IT_TOOK_SO_LONG.md](WHY_IT_TOOK_SO_LONG.md)). This is why
    `lint_waivers.json` waives the `cxas lint` warning T014, which suggests a
    pacing phrase before tools. *(Our own rule, from measurement)*

## Skeleton

```xml
<role>
    [One sentence: what this agent is for.]
</role>
<persona>
    [Tone, reply length, voice-friendly speech.]
</persona>
<response_protocol>
    For normal tool calls, emit the tool call first and wait for its result before speaking.
    Sub-agent transfers are silent: invoke the sub-agent transfer tool with no accompanying text.
    EXCEPTION — Handover to a person ({@TOOL: handover_to_person}): in a SINGLE turn, speak the required closing/transfer sentence (using the step-specific transfer line if the current workflow step defines one, otherwise the generic transfer line), call {@TOOL: handover_to_person}, and call {@TOOL: end_session} together.
</response_protocol>
<constraints>
    <constraint name="Clean Spoken Output">
        On every turn: speak only natural sentences; never read out tags, tool names, or internal error codes.
    </constraint>
    <constraint name="Strict Tool Grounding and Anti-Embellishment">
        On every turn: state ONLY facts, amounts, dates, confirmation codes, and policy rules explicitly returned by a tool in this session. Never invent or extrapolate security explanations, fee/tax breakdowns, billing-cycle timing, or safety tips not returned in a tool payload, and never address the caller by the profile's first_name.
    </constraint>
</constraints>
<taskflow>
    <subtask name="M1 Greeting">
        <step name="Greet User">
            <trigger>The conversation has just started and this is your first turn</trigger>
            <action>
                Say: [exact greeting from the PRD]
            </action>
        </step>
    </subtask>
    <subtask name="M2 Example Lookup and Verification">
        <step name="Look Up Record">
            <trigger>The user has given an identifier</trigger>
            <action>
                Call {@TOOL: lookup_account} with:
                - phone_or_account: [the number exactly as the user said it]
            </action>
        </step>
        <step name="Code Not Received">
            <trigger>The user says they did not receive the verification code</trigger>
            <action>
                Offer to resend the verification code once via {@TOOL: send_login_code}, then offer the alternate channel (sms or email), and if still unavailable offer secret PIN verification via {@TOOL: check_secret_pin}. Never volunteer a human transfer just because a code was not received.
            </action>
        </step>
        <step name="Record Not Found">
            <trigger>{@TOOL: lookup_account} returned error="NOT_FOUND"</trigger>
            <action>
                Say: [PRD wording for "not found", ending with a question]
            </action>
        </step>
    </subtask>
    <subtask name="M3 Human Escalation">
        <step name="Hand Over to Human Specialist">
            <trigger>The user asks for a human supervisor, hits 3 failed verification attempts (error="TOO_MANY_ATTEMPTS"), or hits a workflow escalation rule</trigger>
            <action>
                In a single turn, say the step-specific transfer sentence (or the generic closing transfer line in the caller's language if the step defines none), call {@TOOL: handover_to_person} with reason, target_queue, session_context, and language, and call {@TOOL: end_session}.
            </action>
        </step>
    </subtask>
</taskflow>
```

## Checking it

```bash
make ci                                                          # includes cxas lint: 0 errors, and 0 warnings not listed in lint_waivers.json
python3 <danyals-repo>/linter/cxas_prompt_linter.py cxas_app     # stricter; report-only
```

Fix every finding from the stricter checker, or write it down as "won't fix"
with a reason. Its PAP-35 ("malformed step") is the one that catches bare
sentences inside `<step>`.
