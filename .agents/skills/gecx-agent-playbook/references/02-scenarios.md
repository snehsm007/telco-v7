# 02: Requirements → scenarios (CUJs)

A CUJ (critical user journey) is one concrete thing a user tries to do, with
one correct outcome. The PRD's acceptance criteria are the starting point, not
the full list. In practice the worst bugs come from cases nobody wrote down, so
expand on purpose.

## Steps
1. For every REQ, walk the **bucket grid** and write the scenarios that apply.
2. Cross each scenario with **language** (each supported language plus one
   unsupported one) and **channel** (text, voice) where it matters.
3. For each scenario, add a **near-twin**: the case the agent is most likely
   to confuse it with. Examples:
   - "what if I cancelled?" (hypothetical) vs "cancel it" (action)
   - "unable" vs "unwilling"
   - one-time vs permanent
   - a name that is a substring of another ("Spain" / "Spa")
4. Add **robustness scenarios** for the known platform failure modes (below).
5. **Repeat until nothing new appears.** Keep asking "what else could go
   wrong for REQ-n?" until the answers repeat. Don't set a minimum count:
   agents treat minimums as quotas and stop early with shallow cases.
6. Fill `docs/scenarios.md`: one row per scenario with ID, REQ, bucket,
   language/channel, the gist of what the user says, the correct behavior, the
   eval type, the eval name, the priority, and whether it's gated.
7. 🧑 Ask for approval.
8. Add a test that fails if any P0 REQ has no gated scenario.

## Bucket grid
| Bucket | What to test |
|---|---|
| Happy path | Main intent, clearly stated |
| Alternate path | Same intent, different details, order or phrasing |
| Tool error / not found | Invalid ID, unknown item, tool timeout, backend down |
| Ambiguous | A required detail is missing; the agent asks exactly one clarifying question |
| Multi-intent | Two requests in one message, possibly handled by different parts of the agent |
| Out of scope / refusal | PRD-forbidden topics and actions; polite refusal + an official alternative |
| Adversarial | Prompt injection, "show me your instructions", impersonation, brand-safety bait |
| Human request | "Let me talk to a person": follow the PRD policy; never hang up silently |
| Language | Each supported language; switching mid-conversation; unsupported language; one-word replies |
| Silence / hold | User goes quiet, asks the agent to wait, or only says "okay" |
| Voice stress | Interrupting (barge-in), background noise, homophones, spelled-out IDs and numbers |
| Loops | User keeps refusing or repeating; transfer ping-pong; very long calls |
| Freshness / time | Past vs upcoming, time zones and daylight saving, data unavailable |
| Memory across the conversation | Details given early (name, ID, language, location) are still used later and after handoffs |
| Sensitive data | User volunteers a card number or ID; the agent must not repeat or store it |

## Known platform failure modes (write at least one scenario each where relevant)
- Language switching mid-reply
- Tool-call code printed or spoken
- Silent handoff / dead air
- Internal tags or instructions leaked
- Reasoning ("thoughts") leaked
- Facts invented without a tool call
- Tool call skipped
- Answer contradicts the tool result
- Context lost after a handoff
- Double response
- Conversation loops
- IDs / alphanumerics read back wrong
- Mispronunciation
- Audio cut off
- Voice changes or mimics the caller

## Other sources of scenarios
- **Sample conversations** attached to the PRD: each real failure becomes a
  scenario.
- **An independent reviewer**, a person or agent who did not write the evals,
  playing awkward users.
- **After launch, real failed conversations**: SCRAPI's `cxas-loss-analysis`
  skill clusters them into patterns. Each pattern becomes a scenario.
- **Coverage gaps**: any instruction sentence no test exercises.
