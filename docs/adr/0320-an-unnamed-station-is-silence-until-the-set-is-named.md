# ADR 0320 — An unnamed station is silence until the set is named

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the allowed writer
- **Supersedes:** nothing
- **Depends on:** [ADR 0319](0319-only-a-broken-law-takes-a-slot.md)

## Context

ADR 0319 says a declared law is held, broken, or unstated, and that only a
broken law takes a slot. The four predicates it names stay as they are: a
joint in-band move, a walk of the frozen length, a handoff, and a program
transfer. None of them answers a different question a plant can already state
in words: which stations are allowed to write.

A plant may declare that set. A write from a station outside it is a fact a
person can check. A write from a station inside it is not a break of this law.
An empty set is not a declaration. Treating it as "everyone is an intruder"
would fill the page from a directory the plant never stated.

This law is only membership. It does not invent a known-station
unexpected-function law. It does not read a learned graph. It does not score a
probability. A station the plant named stays silence for this law even when
some other declared law is broken. Known-station and unknown-master stay apart
because this law does not speak about a station the plant named, and it does
not emit a rate.

The frozen residual files were not edited: `consistency.py`,
`command_consistency.py`, `walk_consistency.py`, `drift_consistency.py`,
`bending_consistency.py`, `breadth_consistency.py`, `queue.py`, `grouping.py`,
`joint_setpoint.py`, `subfloor_walk.py`, `band_handoff.py`,
`handoff_booking.py`, `program_transfer.py`, `shift_brief.py`,
`handoff_page.py`, and `leap_stack.py`. The four predicates already written
are unchanged. No corpus was generated or scored. `eval_runs/log.jsonl` was
not appended. Held-out data was not opened. v1 stays 8 of 12. This page is
not a field result.

## Decision

**A write from a station outside the declared set is one break. A station
inside the set is silence for this law. An empty allowed set means the law
was not stated, so the standing is unstated and the page stays quiet.**

`allowed_writer` is a declared law. Its statement is that a write from a
station outside the declared set is a break, a station inside the set is
silence, and an empty set means the law was not stated. `WriterWrite` is a
frozen record with a station name and a timezone-aware time. An empty station
raises. A function code is not a station. The caller supplies the name. This
module does not infer it.

The law is evaluated only when the register names it. If the name is absent,
it appears in none of held, broken, or unstated, including when an outside
write and a non-empty set were both supplied.

When the law is declared, `assess_plant` uses the same one-list rule as the
other laws:

- **Unstated** when `writes` is empty or `allowed_stations` is empty. An empty
  set wins over the presence of writes: the standing is still unstated, and
  it is never broken. The sentence names the empty set when the set is empty,
  and the missing writes when the set was stated and no write was supplied.
- **Broken** when the set is non-empty, at least one write exists, and at
  least one station is outside the set. One `LawBreak` per such write, at
  that write's time. The statement names the station. The law is not also
  held.
- **Held** when the set is non-empty, at least one write exists, and every
  station is inside the set. Held carries no time and takes no slot.

`assess_plant` and `breaks_from_plant` take `writes` and `allowed_stations`
as keyword-only arguments, both defaulting to empty. Callers that omit them
keep today's behaviour for the four laws already written. `law_page` and
`page_from_report` are unchanged: time, then name, ceiling 8, only the broken
list, and the register is required. Nine outside writes keep the earliest
eight. The later write is the one left off.

There is no score, confidence, probability, weight, or magnitude on
`WriterWrite` or on the outcome.

### Options

1. An empty allowed set means every write is outside, so every write breaks.
   That treats a missing directory as an accusation. Refused.
2. A station inside the set can still break this law when a learned graph, or
   an unexpected function, says so. That invents a second law and reads a
   graph this page does not have. Refused. A station the plant named is
   silence here.
3. Membership only, through the three standings ADR 0319 already fixed.
   Chosen. Outside the non-empty set is one break per write. Inside is held.
   Empty set or empty writes is unstated. An undeclared law is on no list.

## Consequences

**Gained.** A plant can name who may write, and the page can show a station
outside that set without a score. A blank directory stays quiet. A station
the plant named does not break this law, so the page does not spend a slot
on the directory for a write the plant allowed.

**Cost.** A station inside the set can still be a break of a different
declared law. This record does not add that law. v1 stays 8 of 12. No corpus
was scored. The frozen residual files were not edited.

**Ten years.** The directory stays a boolean the plant states. A missing
config cannot accuse every station. A later law about an unexpected function
on a station the plant named has to be its own law, scored apart from
unknown-master work, and it cannot be smuggled in by widening this one.
This decision should be revisited if the plant needs that other law, or if an
empty directory should alarm. Either change is a new record.

## What would reverse this

Calling an empty allowed set a break. Breaking this law for a station the
plant named. Inferring a station from a function code. Reading a learned
graph. Adding a score, a confidence, a weight, a magnitude, or a probability.
Editing the frozen residual files so the report can call them. Quoting this
fixture as a detection rate, as 8 of 12 moving, as 10×, as 2–3 a day, or as
at least 70%. Pooling a known station with an unknown master.
