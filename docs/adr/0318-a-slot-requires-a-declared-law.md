# ADR 0318 — A slot requires a declared law

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the law register
- **Supersedes:** nothing
- **Depends on:** [ADR 0317](0317-a-slot-exists-only-when-a-declared-law-is-false.md)

## Context

ADR 0317 says a slot exists only when a declared law is false, and it orders
that page by time. The module that landed with it still evaluates four
predicates on every call: a joint in-band move, a walk of the frozen length, a
handoff, and a program transfer. A plant that never named those laws still
inherits them. An empty plant is not silence. That is the hole.

The four predicates stay the ones already written. This record does not add a
fifth. It does not retune their constants. The frozen residual files were not
edited: `consistency.py`, `command_consistency.py`, `walk_consistency.py`,
`drift_consistency.py`, `bending_consistency.py`, `breadth_consistency.py`,
`queue.py`, `grouping.py`, `joint_setpoint.py`, `subfloor_walk.py`,
`band_handoff.py`, `handoff_booking.py`, `program_transfer.py`,
`shift_brief.py`, `handoff_page.py`, and `leap_stack.py`. No corpus was
generated or scored. `eval_runs/log.jsonl` was not appended. Held-out data was
not opened. v1 stays 8 of 12. This register is not a field result.

## Decision

**A plant names the laws in force. Only a declared law may be evaluated. An
undeclared law is silence. A slot for an undeclared name is a refusal.**

`LawRegister` is a frozen record whose only field is the tuple of laws the
plant named. The same name twice raises. There is no default register, and
there is no field for a score, a confidence, a probability, a weight, or a
magnitude. Admission is a boolean.

`breaks_from_plant` takes that register as a required keyword. It calls a
predicate only when that predicate's name is in the register. The four
predicates above are still the only ones. An empty register returns nothing,
including when the supplied steps are a joint move and a walk of the frozen
length and the supplied transfers hold an unbooked act. A register that names
only the joint move returns that joint and does not return the walk on the
same steps.

`law_page` takes the same register, still required. Order stays time, then law
name. The ceiling stays the integer 8 already fixed for a shift. A break whose
name is not in the register raises. It is not dropped, and it is not sorted by
anything else. The page of an empty break list is empty.

### Options

1. Keep evaluating all four predicates for every plant. A plant that never
   declared a walk would still inherit one. That is the hole this record
   closes.
2. Default the register to all four laws, so a caller that omits it keeps
   today's page. The default would turn the laws on without the plant naming
   them. The hole would remain, one argument away from silence.
3. Require the register. Evaluate only a named law. Refuse a slot whose name
   was not named. Chosen. An empty register is silence. A new law is still a
   new predicate with its own record, not a fifth name invented here.

## Consequences

**Gained.** A plant starts quiet. A law reaches the page only because someone
named it, and only the predicates already written can answer that name. A
manufactured break for an undeclared name cannot sit on the page.

**Cost.** Every caller must pass the register. A later break whose name was
declared still leaves after the eighth in time. Severity is not recovered by a
hidden field. v1 stays 8 of 12. No corpus was scored.

**Ten years.** The register is the list of laws a plant has accepted, not a
weight vector and not a detector. Adding a law means writing a predicate and a
record, then naming it. A plant that names nothing stays silent. This decision
should be revisited if a law the page needs cannot be stated by the four
predicates already written.

## What would reverse this

A default that turns all four laws on. Evaluating a predicate the register did
not name. Dropping an undeclared break instead of raising. Sorting the page by
a magnitude, a weight, a count, or a confidence. Adding a fifth law in this
module. Editing the frozen residual files so the register can call them.
Quoting this fixture as a detection rate, as 8 of 12, as 10×, as 2–3 a day, or
as at least 70%.
