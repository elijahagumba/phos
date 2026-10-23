# ADR 0317 — A slot exists only when a declared law is false

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the declared-law page
- **Supersedes:** nothing
- **Depends on:** [ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md),
  [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0302](0302-a-program-transfer-is-not-a-register-write.md),
  [ADR 0305](0305-two-setpoints-inside-the-band-are-one-move.md),
  [ADR 0307](0307-a-720-step-walk-is-invisible-to-the-joint-check.md),
  [ADR 0310](0310-the-same-value-after-the-window-is-one-handoff.md),
  [ADR 0312](0312-the-unbooked-transfer-keeps-its-place-on-the-process-page.md)

## Context

Atlas version 1 ranks operator slots by residual magnitude and then cuts to 8.
ADR 0068 measured that ranking on HAI: magnitude points away from the incidents,
weight is a constant, and breadth does not rank either. That measurement stays
where it is. It is the reason this page does not ask a residual how loud a slot
is.

ADR 0300 keeps the shift ceiling at 8 alerts. `docs/v1-roadmap.md` section 2.0
already fixed that integer: 8 alerts per 8-hour shift, and it is not searched.
The predicates this page calls are already object-or-nothing. A joint move is
two or more in-band tags inside the frozen window (ADR 0305). A walk is the
frozen length, and a shorter chain is nothing (ADR 0307). A handoff is the same
ordinary value on a second tag after that window (ADR 0310), and a booking that
names both tags clears it (ADR 0312). An unbooked download, upload, or online
edit is an act the caller supplies, and a covering booking clears it (ADR 0302).
`refuse_function_code` stays the refusal for a Modbus function code.

`shift_brief.py` already places some of those hits on a page of eight. It was
not rewritten. The frozen residual files were not edited: `consistency.py`,
`command_consistency.py`, `walk_consistency.py`, `drift_consistency.py`,
`bending_consistency.py`, `breadth_consistency.py`, `queue.py`, and `grouping.py`.
No corpus was generated or scored. `eval_runs/log.jsonl` was not appended.
Held-out data was not opened.

## Decision

**A slot exists only when a declared law is false. A law the facts satisfy is
silence. Residual magnitude does not create a slot and does not order one.
Fewer than 8 broken laws is a complete page.**

The page is `src/phos/atlas/declared_law.py`. `law_page` sorts by time, then law
name, and keeps at most the module constant `OPERATOR_PAGE_CEILING`. That
constant is the integer 8 from `docs/v1-roadmap.md` section 2.0. It is written
in this module. It is not imported from the residual detector, and it is not
searched. There is no limit parameter.

`breaks_from_plant` calls the predicates above and returns a `LawBreak` only
when the predicate returns an object that is still an alert:

- Two or more in-band tags inside the frozen window: one break at the earliest
  step. One tag returns nothing.
- A walk of the frozen length: one break at the first step. Fewer steps return
  nothing.
- A handoff: one break only while `alert` is true. A booking that names both
  tags clears it.
- An unbooked download, upload, or online edit: one break. A covering booking
  or a work order that names the act clears it.

A `LawBreak` has a law name, a timezone-aware time, and a sentence naming the
tags or the act. It has no confidence, probability, weight, magnitude, or
score. A count an existing predicate already computes, including a joint-move
tag count, is not copied onto the break and is not the sort key. A naive time
raises. An empty inlet is an empty page. Nine breaks keep the earliest eight,
including when a later break is the one residual magnitude would have ranked
first.

### Options

1. Keep creating slots from residuals and ordering them by magnitude, then cut
   to 8. ADR 0068 is the measurement that this order does not surface the
   incidents. The frozen queue stays that record. It is not this page.
2. Rewrite `shift_brief` so the process page becomes the law page. That module
   still sits beside `shift_page`, which drops other alerts from the lowest
   score. Folding the rule into it would route a score-ordered page and a law
   page through one function. It was left alone.
3. A separate page whose inlet is a false declared law and whose order is time.
   Chosen. The ceiling is the integer already fixed. Adding a slot later means
   declaring a law, not adding a score column.

## Consequences

**Gained.** The operator page can be short. Silence is a law the facts satisfy.
A later residual cannot jump the queue, because the slot has no residual on it.
The frozen detector files still reproduce the measurements they already hold.

**Cost.** A broken law after the eighth in time is absent even when a person
would have called it severe. Severity is not recovered by a hidden field. v1
stays 8 of 12. This page is not that result, and it is not a detection claim.
No corpus was scored.

**Ten years.** Every place on this page stays a fact a person can check against
a law the plant or the operator declared. A new score column cannot buy a slot
here. The ceiling moves only when a partner names a different budget, and that
move is a new record, not a search. A new law is a new predicate with its own
record. This decision should be revisited if a law this page needs cannot be
stated by the predicates already written.

## What would reverse this

Sorting the page by a magnitude, a weight, a count, or a confidence. Emitting a
slot for a law the facts satisfy. Padding an empty place so the page reaches 8.
Editing the frozen residual files so this page can call them. Importing the
ceiling from the residual detector, or searching it. Turning a Modbus function
code into a slot. Quoting this fixture as a detection rate, as 8 of 12, as 10×,
as 2–3 a day, or as at least 70%.
