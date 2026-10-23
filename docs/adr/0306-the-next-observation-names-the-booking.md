# ADR 0306 — The next observation names the booking

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas, the floor question, the check
- **Supersedes:** nothing
- **Depends on:** [ADR 0302](0302-a-program-transfer-is-not-a-register-write.md)

## Context

An unbooked transfer says `Go and look.` and keeps both stories (ADR 0302). The page did
not say which missing fact would withdraw the alert. A confidence is not that fact, and
none is shown.

## Decision

**When the alert is up, the next observation is exactly `A booking that names this act
and covers this hour.` Supplying that booking withdraws the alert and does not pick a
lead.**

The sentence is `NEXT_OBSERVATION` on `TransferReport`. It is present only while
`alert` is true. A covering check-in clears `alert`, clears the instruction, and clears
the next observation. `tied_lead_ids` still holds both stories. `lead` stays `None`.

No corpus was generated. `templates.py` was not edited. v1 stays 8 of 12.

## Consequences

A reader can see the one fact that would take the alert down. The fact does not choose
between the job and an intruder.

## What would reverse this

Using the booking to make one story the unique lead. Replacing the sentence with a
probability. Editing `templates.py` to force that lead.
