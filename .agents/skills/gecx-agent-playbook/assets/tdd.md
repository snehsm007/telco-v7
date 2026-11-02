# Technical design: <agent name>

Status: draft | approved (date, by) · PRD: `prd.md` · Requirements:
`docs/requirements.md` · Scenarios: `docs/scenarios.md`

## 1. Architecture
Default (what `make kickstart` writes): a `router` that greets, finds the
account and routes, plus one `specialist` per PRD module that logs the caller
in itself when its task needs it. One agent is fine for a PRD with one job.
For each additional agent, name the failing scenario that proves it's needed.

```
router ──> specialist (rename after the PRD module)
```

## 2. Tools
All tools return one shape (`lib/replies.py`): `{status, data, error_message,
tracking_id}`; errors add `error` (a code from `ERROR_CODES`) and
`agent_action`. Money is a number plus a 2-decimal display string and a
currency (`amount: 85.5`, `amount_display: "85.50"`, `currency: "CAD"`).

The scaffold starts with six tools (plus the built-in `end_session`):
`lookup_account`, `send_login_code`, `check_login_code`, `check_secret_pin`,
`submit_request` (rename it after the PRD's task) and `handover_to_person`.

### `<tool_name>`
- Purpose:
- Inputs:
  | Name | Type | Required | Allowed values |
  |---|---|---|---|
- Returns (`data`): every field the PRD requires, with allowed values and
  timelines; money as number + `*_display` string + `currency`.
- Errors: `error` codes and what the agent should do for each (`agent_action`).
- Data source: live API / snapshot; freshness; `source` field.
- Contract tests: one per required field, allowed value and timeline.

## 3. Routing and handoffs
| From | To | When | What is passed |
|---|---|---|---|
Sub-agent transfers are silent; the receiving agent answers in the same turn.
A handover to a person speaks the transfer line, calls `handover_to_person`
and calls `end_session` in the same turn.

## 4. State
Flat, typed variables, one fact each, each declared in `app.json` with a
default.
| Variable | Default | Written by | Read by | Survives handoff? | Never override in evals? |
|---|---|---|---|---|---|
| `language` | `""` (never `"en-US"`) | | | yes | |
| `account_id` | `""` | `lookup_account` | | yes | |
| `logged_in` | `false` | `check_login_code`, `check_secret_pin` | money-moving tools | yes | |
| `handover_complete` / `handoff_message` | `false` / `""` | `handover_to_person` | `speech_hygiene` | yes | |

## 5. Callbacks
| Callback | Agent(s) | Trigger | What it changes |
|---|---|---|---|
| `speech_hygiene` | every agent | after model | Cleans reply text (markdown, long numbers); injects `handoff_message` only when a handover reply has no text, never rewriting spoken text |

No `before_tool` or `before_model` callbacks (`docs/DESIGN_RULES.md` rule 16).

## 6. Voice and channel rules
- Plain text; no markdown, emoji, URLs.
- IDs and numbers read in groups; amounts read from the 2-decimal display string.
- Max spoken reply: … characters.
- Greet once. Silence and interruption handling: …
- Model + voice per channel: … (temperature 1.0)

## 7. Policies
| Policy | REQ | Behavior |
|---|---|---|
| Escalation / human request | | |
| Refusals | | |
| Sensitive data | | |

## 8. Coverage map
| REQ | Scenarios | Eval type | Eval name | Gated? |
|---|---|---|---|---|

## 9. Test data
Fixtures per tool (valid / invalid / edge). Oracle for time-dependent facts:
`<path>`.

## 10. Acceptance bars
Strict 3/3 first, then majority, then individual.
| Layer | Bar | Repeats | Measured on model | Judge model |
|---|---|---|---|---|
| Tool / callback / contract | 100% | 1 | | |
| Goldens | >90% | 5 | | |
| Sims (Gate 3, `make gate3`) | strict 3/3 ≥ 90% AND 100% majority, 0 tool errors | 3 | | |
| Holdout (same code as a full visible run that passed Gate 3) | | 3 | | |
| Audio | | | | |
| Latency p50 (voice) | | | | |

## 11. Known issues
| ID | Symptom | Status |
|---|---|---|

## 12. Changelog
| Date | Change | Reason | Score before → after (strict 3/3 \| majority \| individual) |
|---|---|---|---|
