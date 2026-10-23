# ADR 0323 — Every sentence names the law it came from

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, citation
- **Supersedes:** nothing
- **Depends on:** [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md)

## Context

ADR 0322 admits only the exact `LawBreak` type. The sentence on that break,
and the sentences on held and unstated outcomes, still did not name the law
they came from. A reader could not point from the line back to the declared
law, and a line could carry a score, a confidence, a probability, a weight,
or a magnitude in words without the page refusing it. The type check stops
a subclass. It does not stop an uncited sentence.

This record adds no new law and no new threshold. The three standings, the
register, the ceiling of 8, and the sort key — time, then law name — stay.
Which facts are held, broken, or unstated stays. `page_from_report` remains
the only bridge from a report to the page, and it still passes only
`report.broken`.

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

**Every sentence names its law, then the fact. A score-word is refused. An
uncited break is not placed.**

`cited_statement` returns the law's name, a period, a space, and the fact.
The fact is the checkable sentence already written: the tags, the station,
the valve, or the act. Held, broken, and unstated all go through that
function, so each of them names its law. The fact must be non-empty after
stripping. If the fact contains the word confidence, probability, weight,
magnitude, or score, in any case, the function raises and returns no
sentence. A decimal the plant already uses is allowed when none of those
words appear. The refusal is the word. It is not a threshold, and it does
not search a number.

`law_page` refuses a break whose statement does not start with that law's
name, a period, and a space. The check runs with the exact-type check,
before the page is ordered. A bad citation raises and is not placed. The
ceiling stays 8. The sort stays time, then law name.

There is no score field on `LawBreak` or on `LawOutcome`. The field names of
a break stay name, time, and statement. `type(item) is LawBreak` stays.

### Options

1. Leave the sentences uncited. The fact would still be checkable, and the
   reader would have to guess which law produced it. Refused.
2. Replace the fact with a line that only names the law. The tags, the
   station, the valve, and the act would disappear. Refused.
3. Prefix the existing fact with the law name, refuse a score-word, and
   refuse an uncited break before the page is ordered. Chosen. No new law.
   No new threshold. A plant constant written as a decimal stays.

## Consequences

**Gained.** Every sentence the page can show names the declared law it came
from, then the fact that made it held, broken, or unstated. A score-word
does not become a sentence. An uncited break cannot take a slot.

**Cost.** This record does not say whether a break is an attack. It does not
score a corpus. v1 stays 8 of 12. The frozen residual files, the other page
builders, and the predicate modules were not edited. No new law was added.
No threshold was added. No field for a score, a confidence, a probability, a
weight, or a magnitude was added.

**Ten years.** A sentence without its law name cannot enter the page. A
later number cannot ride in as one of those five words. The page stays a
list of exact breaks, ordered by time then name, capped at the ceiling
already fixed. This decision should be revisited only if the page is allowed
to carry a number, and that permission is a new record. Dropping the prefix,
or admitting a score-word, is not that permission.

## What would reverse this

A sentence that does not name its law. Returning a sentence that carries
confidence, probability, weight, magnitude, or score. Searching a number and
calling that the refusal. Adding a field for any of those. Using
`isinstance` so a subclass can enter. Giving `page_from_report` a second
list to place. Importing the residual detector or the other page builders.
Editing those files, or the predicate modules, so the page can call them.
Changing which facts are held, broken, or unstated. Changing the standings,
the register, the ceiling of 8, or the sort key. Quoting this fixture as a
detection rate, as 8 of 12 moving, as 10×, as 2–3 a day, or as at least 70%.
