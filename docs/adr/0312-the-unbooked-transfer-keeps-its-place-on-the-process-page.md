# ADR 0312 — The unbooked transfer keeps its place on the process page

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the shift brief
- **Supersedes:** nothing
- **Depends on:** [ADR 0303](0303-the-shift-page-holds-eight.md),
  [ADR 0310](0310-the-same-value-after-the-window-is-one-handoff.md),
  [ADR 0311](0311-handoffs-share-the-page-and-the-misses-fall-by-half.md)

## Context

The process page holds eight handoffs and has no place for a program transfer.
An unbooked transfer is the alert whose instruction is go and look. Dropping it to
keep a setpoint hit would hide that alert. A booking that names both tags of a
handoff is the fact that would withdraw the handoff. It must not pick a story, and
a missing booking must not become a verdict of attack.

## Decision

**Four unbooked transfers stay on a page that already holds eight handoffs. The
transfer misses go from 4 to 0, which is at most half. A booking that names both
tags clears that handoff and leaves the tie in place.**

`src/phos/atlas/shift_brief.py` keeps unbooked transfers first, then the earliest
joint moves, walks, and open handoffs, at most 8. A booked transfer is omitted.
Nine unbooked transfers keep the earliest eight.

`src/phos/atlas/handoff_booking.py` says `Go and look.` while the handoff is open,
and the next observation is `A booking that names both tags and covers this hour.`
Both stories stay tied. `lead` stays `None`. A covering booking clears the alert,
the instruction, and that sentence. One tag, or the wrong hour, does not. A joint
inside the window is not this notice.

No corpus was generated. `budget_alerts` is not called. `consistency.py` and
`templates.py` were not edited. v1 stays 8 of 12. This is a fixture. It is not a
detection claim, and it does not open the walk corpus.

## Consequences

One shift can show the program transfer and the process hits together. The screen
still does not pick maintenance or attack. A later session still cannot open the
walk corpus from this record.

## What would reverse this

Dropping an unbooked transfer to keep a process hit when both fit in 8. A missing
booking yielding an attack verdict. A covering booking choosing a lead. Quoting
the fixture as a plant result.
