# ADR 0302 — A program transfer is not a register write

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas, the floor question
- **Supersedes:** nothing
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0069](0069-cmms-exports-reach-the-work-order-inlet.md),
  [ADR 0071](0071-command-behaviour-evidence-reaches-a-template.md)

## Context

The floor question is a program put on a PLC, and whether anything booked that hour. The
notes of that question are in `docs/plc-reddit-2026-10-22.md`. They are not a measurement
and they are not quoted here.

Atlas already keeps both `engineering_maintenance` and `unauthorised_control_activity` when
a known station does something new, and a tie is not a lead (ADR 0014, ADR 0036, ADR 0071).
A work order, when one is supplied, can separate them (ADR 0069). What Atlas did not have
is a name for the three program-transfer acts, or an alert whose instruction is to go and
look when nothing covers the act. A Modbus function code is a register or coil operation.
It is not one of those acts.

ADR 0301 is a declaration that has not been run. This record does not run it.

## Decision

**Download, upload, and online edit are three acts. An unbooked one raises a security
alert whose instruction is `Go and look.` Neither story is the lead.**

`src/phos/atlas/program_transfer.py` is the module. `templates.py` is not edited.
`atlas-v1-consistency` is not edited.

- The caller supplies `download`, `upload`, or `online_edit`. There is no function from a
  Modbus function code to an act. Codes 1, 2, 3, 4, 5, 6, 15, and 16 raise.
- An empty booking inlet and an empty work-order inlet stay empty. Nothing is invented
  from a clock or from a register write.
- With no covering record, `alert` is true and the instruction is exactly `Go and look.`
- Both stories stay visible. `tied_lead_ids` holds both, so the tie is a refusal.
  `insufficient_evidence` stays in the competing set. `lead` is `None`.
  `unauthorised_control_activity` is not a verdict.
- A booking of kind `downtime`, `commissioning`, or `check_in` withdraws the alert only
  when it names the same act and its interval contains the transfer time. A work order
  does the same only when it names that act. A tag-only work order does not. Withdrawing
  the alert does not pick a lead.
- The report has no confidence field. The equal confidence used to compute the tie is not
  shown.

No corpus was generated. `eval_runs/log.jsonl` was not appended. v1 stays 8 of 12. This is
a fixture and a report. It is not a detection claim.

## Consequences

A later session can pass a named act and the bookings it actually holds. It cannot turn a
register write into a download. A missing booking stays a reason to go and look, not a
reason to call the transfer an attack.

## What would reverse this

Inferring an act from a function code. Editing `templates.py` so one story wins this tie.
Filling an empty inlet from a clock. Treating a tag-only work order as cover. Surfacing
the tie's confidence. Starting Intelligence, an API, or a UI from this record.
