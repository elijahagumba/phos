# ADR 0319 — Only a broken law takes a slot

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the three standings
- **Supersedes:** nothing
- **Depends on:** [ADR 0318](0318-a-slot-requires-a-declared-law.md)

## Context

ADR 0317 says a slot exists only when a declared law is false, and it orders
that page by time. ADR 0318 says only a law the plant named is evaluated. A
law the facts satisfy, and a law with nothing to check, were the same silence.
An operator could not tell a missing inlet from a law that had been checked
and held. Neither of those should take a slot. The page still has eight
places.

The four predicates stay the ones already written. This record does not add a
fifth. It does not retune their constants. The frozen residual files were not
edited: `consistency.py`, `command_consistency.py`, `walk_consistency.py`,
`drift_consistency.py`, `bending_consistency.py`, `breadth_consistency.py`,
`queue.py`, `grouping.py`, `joint_setpoint.py`, `subfloor_walk.py`,
`band_handoff.py`, `handoff_booking.py`, `program_transfer.py`,
`shift_brief.py`, `handoff_page.py`, and `leap_stack.py`. No corpus was
generated or scored. `eval_runs/log.jsonl` was not appended. Held-out data was
not opened. v1 stays 8 of 12. This page is not a field result.

## Decision

**A declared law is held, broken, or unstated. Only a broken law takes a
slot. Held and unstated are listed and take none. A law that is not in the
register appears in none of the three lists.**

The three words apply only to laws the register names:

- **Unstated.** The law is declared, and the inlet has no facts that law can
  be checked against. Joint, walk, and handoff are unstated when `steps` is
  empty. Program transfer is unstated when `transfers` is empty. A missing
  inlet is unstated.
- **Held.** The inlet has facts, the predicate was able to run, and it
  returned silence. One in-band write is held for `joint_move`. A chain
  shorter than the frozen walk length is held for `subfloor_walk`. Steps that
  do not form an open handoff, including a handoff cleared by a booking that
  names both tags, are held for `band_handoff`. A transfer whose booking or
  work order covers the act is held for `program_transfer`.
- **Broken.** The predicate returns an alert, exactly as ADR 0317 and ADR
  0318 already define. Two in-band tags, a walk of the frozen length, an open
  handoff, an unbooked download, upload, or online edit.

There is no score, confidence, probability, weight, or magnitude on any
outcome. The standing is a word. It is not a number, and the page does not
sort by it.

`LawOutcome` carries a name, a standing, and a statement. Its time is present
only when the standing is broken, and it is `None` otherwise. A held or
unstated outcome has no timestamp that could rank it. The report's broken
list stays `LawBreak`, which already has a timezone-aware time. Held and
unstated are not breaks, so they cannot be passed to `law_page`.

`assess_plant` takes the same inlet as `breaks_from_plant`, and the register
is still required. It returns one frozen report with three tuples: held,
broken, and unstated. Held and unstated are ordered by law name. Broken is
ordered by time, then law name. One law occupies one list. `breaks_from_plant`
returns that broken tuple, so the predicates run once.

`law_page` stays the only slot function. It still takes breaks plus the
register, still sorts by time then name, and still caps at
`OPERATOR_PAGE_CEILING`, the integer 8. `page_from_report` calls `law_page`
on `report.broken` only. Held and unstated do not compete for those eight
places. An empty register still evaluates nothing. A break whose name is
absent from the register still raises in `law_page`.

### Options

1. Keep one word, silence, for a satisfied law and for a missing inlet, and
   leave both off every list. The page stays short, and the operator cannot
   see which declared laws were checked.
2. Put held and unstated on the page, so every declared law takes a slot.
   That spends the eight places on laws that are not broken.
3. Three lists. Only the broken list is a `LawBreak`, and only that list
   enters `law_page`. Chosen. A missing inlet stays visible as unstated, and
   it takes no slot.

## Consequences

**Gained.** A plant can see a law that was checked and held, a law that was
false, and a law that had nothing to check, as three different lists. Only
the false law reaches the operator page. A later held law cannot jump the
queue, because it has no time and it is not a break.

**Cost.** Every caller that wants the three lists uses `assess_plant`. A
broken law after the eighth in time is still absent. Severity is not
recovered by a hidden field. v1 stays 8 of 12. No corpus was scored.

**Ten years.** The page stays a list of broken declared laws. Held and
unstated stay visible and stay off that page. A new score column cannot buy
a slot, and a clock on a held law cannot either. This decision should be
revisited if a law the page needs cannot be stated by the four predicates
already written.

## What would reverse this

Sorting the page by standing, by a magnitude, by a weight, or by a
confidence. Giving a held or unstated outcome a time so it can rank. Letting
held or unstated take a slot. Calling a missing inlet a break. Dropping an
undeclared break instead of raising. Adding a fifth law in this module.
Editing the frozen residual files so the report can call them. Quoting this
fixture as a detection rate, as 8 of 12, as 10×, as 2–3 a day, or as at
least 70%.
