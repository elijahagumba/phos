# ADR 0321 — The controller comparison is true or false

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the controller comparison
- **Supersedes:** nothing
- **Depends on:** [ADR 0320](0320-an-unnamed-station-is-silence-until-the-set-is-named.md)

## Context

ADR 0320 names who may write. It does not say what the controller itself
writes. PLC1, at ICSSim `bcfd1844d3f063850c69f2643f6a052bac03d8ec` — that commit is
not in this repository — already does. The same lines are quoted in
`data/phos-icssim-dev/roles.toml`. The input valve closes when the tank level
is strictly above its maximum and opens when the level is strictly below its
minimum. Inside that band, including either end, the quoted logic does not
move the valve. The output valve closes when the bottle is strictly above its
maximum or the belt is strictly past the filler, and opens otherwise. The
close value is 0. The open value is 1. The belt comparison is 1.0. The
automatic law runs only when the mode is 3, the release value the generator
already uses. Those four numbers are the plant's. They are not tuned here.

A mode that is not 3 is manual. The automatic comparison was not in force.
Treating a valve held by hand as this law's break would fill the page from a
rule the plant had switched off. ADR 0316 already says a held valve is not
the controller column. This page has no column. It has no divisor, no onset
score, no third-peak calibration, and no residual.

The frozen residual files were not edited: `consistency.py`,
`command_consistency.py`, `walk_consistency.py`, `drift_consistency.py`,
`bending_consistency.py`, `breadth_consistency.py`, `queue.py`, `grouping.py`,
`joint_setpoint.py`, `subfloor_walk.py`, `band_handoff.py`,
`handoff_booking.py`, `program_transfer.py`, `shift_brief.py`,
`handoff_page.py`, and `leap_stack.py`. `joint_move`, `subfloor_walk`,
`band_handoff`, `program_transfer`, and `allowed_writer` are unchanged. No
corpus was generated or scored. `eval_runs/log.jsonl` was not appended.
Held-out data was not opened. v1 stays 8 of 12. This page is not a field
result.

## Decision

**The controller comparison is true or false. Agreement is silence.
Disagreement is one break per side. Manual mode is unstated.**

`controller_valve` is a declared law. Its statement is the two comparisons,
and that manual mode means the law was not stated. `ControllerSample` is a
frozen record with a timezone-aware time and the nine floats the comparison
reads: level, level minimum, level maximum, input valve, input mode, bottle
level, bottle maximum, belt, output valve, and output mode. A naive time
raises. There is no score, confidence, probability, weight, or magnitude.

The constants live in this module as literals. This module does not import
the residual detector or the walk column. Those files own the divisor.

The law is evaluated only when the register names it. If the name is absent,
it appears in none of held, broken, or unstated, including when the sample
disagrees.

When the law is declared, `assess_plant` uses the same one-list rule as the
other laws:

- **Unstated** when no sample was supplied.
- **Unstated** when either mode is not 3. Manual mode means this automatic
  law was not in force. That is silence, not a break. A valve that would have
  disagreed under release does not break this law while a mode is manual.
- **Broken** when a sample was supplied, both modes are 3, and a side's valve
  is not the value the rule writes. One `LawBreak` per disagreeing side, at
  the sample time. The statement names the valve and the value the rule
  required. The law is not also held.
- **Held** when a sample was supplied, both modes are 3, and neither side
  disagrees. Held carries no time and takes no slot.

The input side writes 0 when `tank_level_value` is strictly above
`tank_level_max`, and 1 when `tank_level_value` is strictly below
`tank_level_min`. The maximum comparison is first, the quoted `if` / `elif`
order. Inside the band, including either end, that side does not break, whatever
the valve reads. The output side, only when its mode is 3, writes 0 when
`bottle_level_value` is strictly above `bottle_level_max` or
`bottle_distance_to_filler_value` is strictly above 1.0, and 1 otherwise.
Equality on the bottle maximum, and equality on 1.0, do not by themselves
require 0.

`assess_plant` and `breaks_from_plant` take `controller` as a keyword-only
argument, defaulting to omitted. Callers that omit it keep today's behaviour
for the four older laws and for `allowed_writer`. `law_page` and
`page_from_report` are unchanged: time, then name, ceiling 8, only the broken
list, and the register is required. Two breaks from the two sides both stay
when the page is under that ceiling.

### Options

1. A manual mode is a break, because the valve is not where the automatic
   rule would have put it. That treats a switched-off law as an accusation.
   Refused. Manual mode is unstated.
2. Inside the band, compare the input valve with a residual, an onset score,
   or a divisor taken from the walk column. That imports the calibration this
   page does not have, and the quoted line does not move the valve there.
   Refused.
3. The comparison is true or false, through the three standings already
   fixed. Chosen. Both modes at release and both sides in agreement is held.
   Each disagreeing side is one break. No sample, or either mode not release,
   is unstated. An undeclared law is on no list.

## Consequences

**Gained.** A plant can name the controller comparison, and the page can show
a valve that is not the value the plant's own line writes, without a score.
Agreement is silence. A mode the plant did not leave on automatic stays quiet.

**Cost.** This record does not say whether a disagreeing valve is an attack.
It does not score a corpus. v1 stays 8 of 12. The frozen residual files were
not edited. The four older laws and `allowed_writer` are unchanged.

**Ten years.** The comparison stays a boolean the plant already wrote down.
The constants stay the plant's literals. A later calibration, a divisor, or a
residual has to be its own record, and it cannot be smuggled in by widening
this one. This decision should be revisited if the quoted PLC1 line changes,
or if a plant wants a manual valve on this page. Either change is a new record.

## What would reverse this

Tuning 0, 1, 1.0, or mode 3. Treating the band ends as outside. Treating
manual mode as a break. Importing the residual detector or the walk column
so this law can grow a divisor. Adding a score, a confidence, a weight, a
magnitude, or a probability. Editing the frozen residual files so the report
can call them. Quoting this fixture as a detection rate, as 8 of 12 moving,
as 10×, as 2–3 a day, or as at least 70%.
