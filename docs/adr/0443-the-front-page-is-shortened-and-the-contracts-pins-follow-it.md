# ADR 0443 — The front page is shortened, and the contract's pins follow it

- **Status:** Accepted
- **Date:** 2026-11-15
- **PART:** Public record
- **Supersedes:** nothing
- **Depends on:** [0381](0381-the-front-door-is-corrected-and-the-freeze-opens-for-figures.md), [0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md), [0116](0116-a2-status-four-of-five-beyond-chance.md), [0064](0064-var1-on-hai-is-louder-than-snapshot-mahalanobis.md), [0439](0439-the-public-surfaces-carry-the-custody-argument-and-the-test-programme.md)

## Context

The public front page had grown to 3,955 words of prose and eight embedded SVGs, and it opened
with a hundred-word definition of held, broken and unstated before a reader knew what Atlas was.
Four LaTeX display equations sat above the fold. The founder's judgement, and the reason for this
record, is that the page read as a specification rather than as a position, and that the material
most likely to earn a reader's attention — the three detectors that were built and refused — sat
below two screens of mechanism.

Nothing was wrong with the page's facts. This is a presentation decision and not a measurement.
No number moved, no bar moved, and no claim was strengthened.

Two things on the old page were weak in a way a reader would find out for themselves, and both
are fixed here rather than left:

1. The page said the HAI comparison was against "the best baseline checked". It was grouped
   min-max normalisation, which is an elementary opponent, and ADR 0116 names it plainly while
   the front page did not. A reader who clicked discovered the gap unaided.
2. The page carried no placement in the literature at all. Checking declared rules against
   process data is invariant and specification-based detection, a populated family, and a front
   page that cites nobody invites the conclusion that the family is unknown to the project.

ADR 0439 already settled the register this change writes in: from Theranos, the restraint and the filed-document feel but **not the tense**, because a present-tense sentence must be checkable today; and *sovereign* as custody rather than size. Nothing here reopens that. The page is shorter in the same voice, and every bold sentence on it is a statement about architecture or custody, not about a measurement.

## Decision

**The front page is 1,225 words and three images.** The order is position, what it does, what it
will not do, the refused detectors, how it gets proven, the rules it checks, where it stands, how
to run it. The refusals and the sealed sixth family are reached before the caveats, because they
are what the page has that another project's does not.

**The four display equations move to `docs/whitepaper/eight-alert-non-admission.md`**, the paper
about what the page refuses, verbatim and with their prose. The front page links them.

**ADR 0381's pins follow the equations and do not loosen.**
`tests/public/test_overlay_readme.py` now checks the ceiling phrase on the front page, as before,
and checks the formula, the refused word set and the refused count against the contract page.
Two tests are added: that the contract file exists, so a move cannot leave four assertions
reading an empty string, and that the front page still links it. The ceiling regexes are
unchanged; narrowing one was tried and reverted in the same session, because the front page
satisfies the original.

**The min-max baseline is named on the front page**, with the sentence that an elementary
opponent is what it is. ADR 0064's VAR(1) result is named beside it, and reconstruction
baselines and HAI's own published results are stated as the next measurement and as not done.

**One sentence places the work in its family**, and claims the novelty is the custody rather than
the check.

## Consequences

The page no longer states the contract formally, so a reader who wants it takes one click. That
is the cost, and it is accepted: the formal statement was serving the project's discipline rather
than the reader's first thirty seconds.

Naming the baseline weakens how the strongest number reads. That is the intended direction. A
comparison a reader can value is worth more than one they discover is thin.

The two added sentences are claims about the world, not about a measurement, so no harness run
backs them and none is required. If the literature placement is wrong, it is wrong as prose and a
later record corrects it.

ADR 0044 is satisfied in this change rather than deferred, because the public claim moved and the
three surfaces move with it: `encyclopedia/12-adr-catalogue.md` gains this record's entry,
`easy to reads/188` is the plain-English note and is listed in that index, and the lab `README.md`
names grouped min-max in the release paragraph that previously said only "the best baseline
checked". The front page's own text is the fourth surface and is the subject of the change.

**This record does not** lift a tier, move v1 off 8 of 12, open a closed rung, fill 0277-0284,
score anything, define sovereign grade, or unblock P1.

## Verified

`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run pytest -q` were
run on this worktree after the change. The result is recorded in the commit that carries this
file; a reader who wants it should read that message rather than this paragraph, because this
paragraph was written before the run finished.
