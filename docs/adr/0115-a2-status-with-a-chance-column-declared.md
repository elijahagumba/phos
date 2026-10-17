# ADR 0115 — A2's status for the consistency detector, with a chance column, declared before it runs

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1 A2, handover step 3
- **Depends on:** [ADR 0100](0100-grouped-g1-rows-and-where-atlas-loses.md),
  [ADR 0102](0102-the-clean-hai-run-and-where-atlas-loses.md),
  [ADR 0104](0104-the-frozen-candidate-on-clean-hai.md),
  [ADR 0106](0106-four-checks-on-the-frozen-candidate.md),
  [ADR 0113](0113-consistency-on-batadal-five-of-five-and-a-saturated-budget.md)

## Context

A2 (roadmap §2.1): recall within budget against the best checked opponent on each of the five
judging corpora, strictly higher on at least three. A grouped detector is compared only with
grouped opponents (ADR 0096). `atlas-v1-consistency` has lab-scored rows on HAI 22.04, 23.05 and
BATADAL. On HAI 20.07 and 21.03 its only figures are the sandbox harness's (37/38 and 42/50),
which used the G1 loader and the lab's `_keep_top` but not `_score_detector`.

ADR 0113 showed that on BATADAL random alerts catch every attack. Elijah delegated the response to
Claude on 12 October. Claude chose not to add a new metric after seeing a score, and instead to
put ADR 0106's existing chance null beside every corpus in the A2 status, so a win that chance
also achieves is visible as such.

## Decision

One command, after this record is committed, and not before:

`uv run python scripts/measure_a2_status.py`

It refuses to start if `eval_runs/v1/a2-status.json` exists. It:

1. Fits `atlas-v1-consistency` (frozen windows; both editions are declared at 1 s) on HAI 20.07's
   two training files and on HAI 21.03's three, read by the G1 loader, and scores their test files
   once with its own events and budget through `_score_detector`. Whether the result equals the
   sandbox's 37/38 and 42/50 is reported. It is not enforced: a difference is a finding about the
   sandbox harness, and the lab-scored figure is the one that counts.
2. Draws ADR 0106's chance null on HAI 20.07, HAI 21.03 and BATADAL: 8 distinct rows per 8-hour
   shift, 500 draws, a fresh `PCG64(20261010)` generator per corpus, reporting the mean, the
   linear 95th percentile and the maximum. HAI 22.04 and 23.05 keep ADR 0106's rows.
3. Writes one table: for each corpus, its exposure, the detector's catch, the best grouped checked
   opponent's published catch (grouped MinMax on all five: 32/38, 36/50, 10/58, 6/52, 3/5), whether
   the detector is strictly higher, the chance row, and whether the detector is above every chance
   draw. It counts corpora strictly higher, and corpora strictly higher and above every draw.

Grouped MinMax, Steadytime and Histogram are the three checked opponents (ADR 0095), so A2's
two-opponent condition holds. Nothing here edits roadmap §2 or the G1 table, and no log row is
appended.

## Consequences

The table is A2's status, not A2's verdict. A2 is judged at the v1 freeze, under A6's one
configuration; this detector with ADR 0112's rule is one configuration. Every corpus in the table
is seen by this detector, and HAI 20.07 is the corpus it was developed on. The table says so on
every row.

## What would reverse this

Running the command twice, or enforcing the sandbox figures instead of reporting the lab's.
