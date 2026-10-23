# ADR 0322 — A slot enters only as a law break

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the admission boundary
- **Supersedes:** nothing
- **Depends on:** [ADR 0321](0321-the-controller-comparison-is-true-or-false.md)

## Context

ADR 0321 admits a controller disagreement as a `LawBreak`. The page still
took any object that `isinstance` would call a break. A subclass can add a
magnitude, a score, a confidence, a weight, or a probability and still pass
that check. The object would then sort by time and law name and take a slot,
carrying a number the page is not allowed to have. `isinstance` is not an
admission boundary.

This record adds no new law and no new threshold. The three standings, the
register, the ceiling of 8, and the sort key — time, then law name — stay.
`page_from_report` remains the only bridge from a report to the page, and it
still passes only `report.broken`.

The frozen residual files and the other page builders were not edited:
`consistency.py`, `command_consistency.py`, `walk_consistency.py`,
`drift_consistency.py`, `bending_consistency.py`, `breadth_consistency.py`,
`queue.py`, `grouping.py`, `shift_brief.py`, `handoff_page.py`, and
`leap_stack.py`. The predicate modules were not edited either:
`joint_setpoint.py`, `subfloor_walk.py`, `band_handoff.py`,
`handoff_booking.py`, and `program_transfer.py`. The law module still imports
those five boolean predicates. It does not import the residual detector or
the other page builders. No corpus was generated or scored.
`eval_runs/log.jsonl` was not appended. Held-out data was not opened. v1
stays 8 of 12. This page is not a field result.

## Decision

**Only the exact `LawBreak` type is admitted. A subclass that carries a
magnitude is refused and is not placed.**

Inside `law_page`, before the page is ordered, each value must satisfy
`type(item) is LawBreak`. A different type, including a subclass, raises
`ValueError`. It is not dropped onto the page and it is not sorted. The
check runs before the name and the time are read, so a foreign object is
refused as a type. A genuine `LawBreak` whose name is in the register still
passes, and the page still orders those breaks by time, then law name, and
still keeps at most 8.

`page_from_report` does not grow a second entrance. It still calls
`law_page` on `report.broken` only. A subclass sitting in that tuple is
refused there, because that is the same check.

There is no score field on `LawBreak` or on `LawOutcome`. The field names of
a break stay name, time, and statement.

### Options

1. Keep `isinstance`. A subclass with a magnitude would enter and could be
   the earliest slot. Refused. That is how a number gets onto a page that
   has no number.
2. Strip the extra fields and admit the parent. The caller attached a
   magnitude, and deleting it would hide that the object was not a break.
   Refused.
3. Require the exact type. A different type raises and is not placed.
   Chosen. A magnitude subclass is refused even when its name is declared
   and its time is the earliest. A real `LawBreak` still enters.

## Consequences

**Gained.** The operator page cannot be entered by a scored subclass. The
admission rule is the type itself, checked before the sort. The laws, the
ceiling, and the order are the ones already written.

**Cost.** This record does not say whether a break is an attack. It does not
score a corpus. v1 stays 8 of 12. The frozen residual files and the other
page builders were not edited. No new law was added. No threshold was added.

**Ten years.** A later score has to be its own type and its own record. It
cannot ride in by subclassing `LawBreak`. The page stays a list of exact
breaks, ordered by time then name, capped at the ceiling already fixed.
This decision should be revisited only if the page is allowed to carry a
number, and that permission is a new record. Widening `isinstance` is not
that permission.

## What would reverse this

Using `isinstance` so a subclass can enter. Admitting a magnitude, a score,
a confidence, a weight, or a probability by adding a field or a subclass.
Giving `page_from_report` a second list to place. Importing the residual
detector or the other page builders. Editing those files, or the predicate
modules, so the page can call them. Changing the standings, the register,
the ceiling of 8, or the sort key. Quoting this fixture as a detection rate,
as 8 of 12 moving, as 10×, as 2–3 a day, or as at least 70%.
