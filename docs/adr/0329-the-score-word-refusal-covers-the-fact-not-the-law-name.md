# ADR 0329 — The score-word refusal covers the fact, not the law's name

- **Status:** Accepted
- **Date:** 2026-10-26
- **PART:** Atlas, the operator page
- **Supersedes:** nothing
- **Depends on:** [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0326](0326-a-score-word-is-not-placed-and-an-unchecked-law-stays-listed.md)

## Context

ADR 0323 requires a placed sentence to start with its law's name, a period,
and a space. ADR 0326 then refused a placed sentence that contains
confidence, probability, weight, magnitude, or score, anywhere in it, as a
substring. Both run in `law_page`, before the page is ordered.

For a register name that carries one of those five words, the two cannot
both hold. The citation rule requires the name at the front of the
sentence. The refusal then reads that same name and raises. Checked on a
plant register naming one law `tank_weight_limit`:

```
law_page RAISED: a placed sentence does not carry weight
assess_plant unstated: [('tank_weight_limit', 'tank_weight_limit. This page
has no check for this law, so it was not stated.')]
```

No break of that law could be placed by any caller. Because ADR 0326 places
nothing from a call that carries one of the words, that single name also
withheld every other break in the same call. The two halves of ADR 0326
disagreed: `assess_plant` listed the same name without complaint.

Weight and magnitude are ordinary process words. A plant may hold a weight,
and `docs/zero-to-one-master-plan.md` has the plant writing the laws. The
register is the plant's vocabulary, not a sentence this page composed.

No code outside `law_page` is reached by this. The six law names Atlas
evaluates carry none of the five words, so no recorded page moves. No
corpus was generated or scored. `eval_runs/log.jsonl` was not appended.
Held-out data was not opened. `law-inlet:invariants` stays unrun. v1 stays
8 of 12. This page is not a field result. P1 stays blocked.

ADR 0328 and `easy to reads/125` are in the main checkout's working tree and
are not committed, so this record takes 0329 and note 126 (ADR 0292).

## Decision

**The refusal reads the fact. The law's name is the plant's word and is not
read for a score.**

`law_page` checks the sentence with its `"<name>. "` prefix removed. That
remainder is the fact, which is the text the page composed through
`cited_statement`. A fact containing confidence, probability, weight,
magnitude, or score, in any case, as a substring, still raises, and that
call still places nothing — including a later break that would otherwise
have been clean. The ceiling stays 8. The sort stays time, then law name.
No new law and no new threshold.

`cited_statement` already tested the fact alone. The two now run the same
test on the same text, which is what the module already claimed and did
not do.

### Options

1. Refuse the law name where the register is built. A plant may genuinely
   hold a weight, and dropping a declared law was already refused by ADR
   0326's second option. Refused.
2. Place the other breaks and drop only the sentence that carries the word.
   A break that disappears quietly is worse than a call that raises.
   Refused.
3. Read the fact and leave the name alone. Chosen. No number moves.

## Consequences

**Gained.** A plant whose law name happens to carry one of the five words
still gets a page. One such name no longer withholds the other breaks in
that call. The refusal covers exactly the text the page writes, and the
builder and the page agree.

**Cost.** A law name the plant wrote can put one of the five words on the
page, as the plant's own word. This page still does not say whether a break
is an attack. No corpus was scored. The frozen residual files and the
predicate modules were not edited. v1 stays 8 of 12.

**Ten years.** The page refuses its own claims of certainty and does not
police the plant's vocabulary. A register the plant writes is admitted or
it is not; it is not silently narrowed by a word list.

## What would reverse this

Placing a fact that contains confidence, probability, weight, magnitude, or
score. Adding a field for a score. Checking a plant's law name against a
word list, or dropping a named law, without a record. Placing part of a
call that carried one of the words. Changing the ceiling of 8 or the sort
key. Quoting this record as a detection rate, as 8 of 12 moving, as 10×, as
2–3 a day, or as at least 70%.
