# ADR 0326 — A score-word is not placed, and an unchecked law stays listed

- **Status:** Accepted
- **Date:** 2026-10-24
- **PART:** Atlas, the operator page
- **Supersedes:** nothing
- **Depends on:** [ADR 0319](0319-only-a-broken-law-takes-a-slot.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md)

## Context

ADR 0323 refuses a score-word inside `cited_statement`. `law_page` checked
the type, the law-name prefix, the time, and register membership. It did not
read the words. A `LawBreak` built by hand, whose statement already started
with its law name, could carry confidence, probability, weight, magnitude,
or score onto the page.

`assess_plant` evaluated the six names it knows. A register that named some
other law returned three empty lists for that name. The law was not held,
not broken, and not unstated. Section 4 of
`docs/zero-to-one-master-plan.md` says the register is partitioned across
those three lists, one law in one list. An empty register is a separate
case, and it stays three empty lists.

This record adds no new law and no new threshold. The ceiling stays 8. The
sort stays time, then law name. `law-inlet:invariants` is not run. No corpus
was generated or scored. `eval_runs/log.jsonl` was not appended. Held-out
data was not opened. v1 stays 8 of 12. This page is not a field result.

## Decision

**A placed sentence cannot carry a score-word. A name no predicate placed
is unstated, once.**

`law_page` refuses a statement that contains confidence, probability,
weight, magnitude, or score, in any case, as a substring. The check runs
with the exact-type check and the citation check, before the page is
ordered. The call raises and places nothing, including a later break in the
same call that would otherwise have been clean. A decimal the plant already
uses stays when none of those words appear. The refusal is the word. It is
not a search for a number.

After the six predicates have each placed a named law into one list, any
register name still absent is unstated. The sentence says this page has no
check for that law. It takes no slot. It is not a break. An empty register
still returns three empty lists.

### Options

1. Leave both holes until the replay in Q2. A hand-built sentence could
   carry a score onto the page in the meantime, and a named law could
   vanish. Refused.
2. Raise when the register names a law this page cannot check, and return
   no report. Refused. The partition is three lists. A name the plant wrote
   that this page cannot check is unstated. An empty register stays empty.
3. Refuse the score-word at placement, and list the unchecked name as
   unstated. Chosen. No new law. No new threshold.

## Consequences

**Gained.** A sentence containing a score-word cannot take a slot, and it
cannot be the reason a clean sentence in the same call is shown. Every name
in the register appears in held, broken, or unstated. An empty register is
still silence.

**Cost.** This record does not say whether a break is an attack. It does
not score a corpus. v1 stays 8 of 12. The frozen residual files and the
predicate modules were not edited. No field for a score was added.
`law-inlet:invariants` stays unrun.

**Ten years.** The page refuses the five words itself, not only the
builder. A plant can name a law this page cannot check, and that name stays
visible as unstated. Dropping it, or placing a score-word, is a new record.

## What would reverse this

Placing a sentence that contains confidence, probability, weight, magnitude,
or score. Omitting a named law from all three lists. Treating an unchecked
name as a break, or as a reason to refuse the whole register. Treating an
empty register as a break. Searching a number and calling that the refusal.
Changing the ceiling of 8 or the sort key. Quoting this fixture as a
detection rate, as 8 of 12 moving, as 10×, as 2–3 a day, or as at least 70%.
