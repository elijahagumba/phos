# ADR 0303 — The shift page holds eight

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas, the floor question, day 2
- **Supersedes:** nothing
- **Depends on:** [ADR 0302](0302-a-program-transfer-is-not-a-register-write.md)

## Context

ADR 0302 names a program transfer and says `Go and look.` when nothing booked it. That
report did not yet share a shift with any other alert. The frozen allocator
`budget_alerts` already keeps 8 alerts a shift. It is not edited here. ADR 0301 has not
been run, so the sub-floor walk stays ungenerated.

## Decision

**`shift_page` keeps at most 8 alerts for one shift. An unbooked transfer stays. A booked
transfer is omitted. Other alerts leave from the lowest score.**

The function is in `src/phos/atlas/program_transfer.py`. It reads `ALERTS_PER_SHIFT` and
`SHIFT_SECONDS`. It does not call `budget_alerts`.

- An unbooked report stays, with the instruction `Go and look.`, both stories tied, and
  `lead` is `None`.
- A booked report takes no slot.
- When unbooked transfers and other alerts together exceed 8, other alerts leave from the
  lowest score. An unbooked transfer is not removed to save one.
- When unbooked transfers themselves exceed 8, eight stay: earliest time first, then act
  name.
- Times that span a second shift are refused. An empty inlet is still empty. A function
  code still raises. A tag-only work order still leaves the transfer on the page.
- No confidence field is added.

No corpus was generated. `eval_runs/log.jsonl` was not appended. v1 stays 8 of 12.
`templates.py` and `consistency.py` were not edited.

## Consequences

A caller who already has a shift's other alerts can place the named transfers on the same
page without a ninth slot. This is a fixture. It is not a detection claim.

## What would reverse this

Editing `budget_alerts` or `consistency.py` to make room. Dropping an unbooked transfer so
a lower sensor score can stay. Calling a booked transfer an alert. Inferring an act from a
function code.
