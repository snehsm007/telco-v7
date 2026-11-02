# Requirements

Source: `prd.md` (version/date: …). Every requirement below quotes or points to
the PRD line it comes from. Nothing here is invented; guesses go under
Assumptions.

## Requirements
| ID | Requirement (one testable sentence) | PRD ref | Priority | Channel | Notes |
|---|---|---|---|---|---|
| REQ-1 | | §… | P0 | text+voice | |
| REQ-2 | | | P1 | | |

Priority: **P0** = launch blocker, must pass every CI run. **P1** = important,
gated by floor. **P2** = nice to have, nightly only.

## Out of scope (from the PRD)
- …

## Data contract (from the PRD)
Every field, allowed value (enum) and timeline the PRD fixes. Each row gets a
contract test. Money is a number plus a 2-decimal display string and a
currency (`amount: 85.5`, `amount_display: "85.50"`, `currency: "CAD"`).
| Field / value / timeline | Allowed values or format | Returned by tool | PRD ref | Contract test |
|---|---|---|---|---|
| | | | §… | |

## Open questions for the human
| # | Question | Why it matters | Answer |
|---|---|---|---|
| Q1 | | | |

## Assumptions (until answered)
- A1: …
