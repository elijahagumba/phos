# ADR 0102 — The clean HAI run, and Atlas loses both editions

- **Status:** Accepted
- **Date:** 2026-10-06
- **PART:** v1, the one score declared in ADR 0101
- **Depends on:** [ADR 0101](0101-the-clean-hai-run-is-declared.md)

## Context

ADR 0101 named the command, the denominators, and the row join, and was committed
before this run. `scripts/measure_clean_hai.py` then ran once. It refused nothing
it was built to refuse: the attack runs were 58 and 52, the published 9/38 line was
still there, and `g1-clean-hai.json` did not yet exist.

## Decision

These are the headline counts. Nothing was retuned after them.

| Corpus | Exposure | Ungrouped Atlas | Ungrouped MinMax | Grouped Atlas | Grouped MinMax | Beyond grouping |
|---|---|---:|---:|---:|---:|---:|
| hai-22.04 | | 5/58 | 6/58 | 5/58 | 10/58 | −5 |
| hai-23.05 | | 3/52 | 4/52 | 5/52 | 6/52 | −1 |

Ungrouped Steadytime and Histogram are 3/58 and 2/52. Grouped, they are 4/58 and 2/52.

Atlas is below MinMax on both editions, ungrouped and grouped. Grouping does not
reverse either loss. On HAI 22.04 it leaves Atlas at 5 and raises MinMax from 6 to
10. On HAI 23.05 it raises Atlas from 3 to 5 and MinMax from 4 to 6.

Attacks only grouped Atlas catches: HAI 22.04 `test2.csv#0`, `test3.csv#9`; HAI
23.05 `hai-test2.csv#0`, `hai-test2.csv#3`, `hai-test2.csv#37`.

Fit: HAI 22.04, 1004402 benign rows, 68 Atlas signals, 0 attack rows excluded.
HAI 23.05, 896400 benign rows, 66 Atlas signals, 0 attack rows excluded. Median
step 1 second on both, matching the declared period.

Reference eTaPR F1, ungrouped: HAI 22.04 Atlas 0.097671 and MinMax 0.212024; HAI
23.05 Atlas 0.091212 and MinMax 0.132292. HAICon eTaPR F1 follows the same order.
Point-adjusted F1, which is not the headline, goes the other way: Atlas 0.334485
against MinMax 0.192879 on HAI 22.04, and 0.544110 against 0.338163 on HAI 23.05.
Grouped reference and HAICon eTaPR F1 are 0.0 for every detector on both editions.
One sample per event does not meet the overlap prune. Grouped point-adjusted F1 is
not zero.

The published rows for HAI 20.07, HAI 21.03, BATADAL, distillation and Data4Cyber
are unchanged, including HAI 20.07 Atlas 9/38. The two `not_scored` objects in
`g1-baseline-table.json` were replaced. The frozen recall 0.23684210526315788 is
still in that file. The experiment log was not appended. These editions are not
labelled seen.

## Consequences

There is no remaining unscored HAI edition in the G1 table. haiend-23.05 stays
registered and not fetched. A second score of 22.04 or 23.05 needs a new command
and a reason written first.

## What would reverse this

Replacing one of these fractions, or changing a detector or a grouping constant
because of them.
