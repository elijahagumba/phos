# ADR 0104 — The frozen candidate on clean HAI

- **Status:** Accepted
- **Date:** 2026-10-10
- **PART:** v1, the one score declared in ADR 0103
- **Depends on:** [ADR 0103](0103-the-frozen-candidate-is-declared-on-clean-hai.md)

## Context

ADR 0103 named the file, the command, both editions, and the comparison rows, and
was committed before the run. `scripts/measure_candidate_look.py` then ran once.
`eval_runs/v1/g1-candidate-look.json` is that run. The sha256 of
`experiments/2026-10-04-sandbox/candidate.py` is still
`7d485b7298282b6b369d55675804d3017e9f952d1353b5e673c84734720433d4`. The MinMax
replay, used only to name attacks, returned 10 of 58 and 6 of 52.

## Decision

Recall within budget is the headline. It is the caught/attacks column.
Point-adjusted F1 is reported and is not the headline. Grouped MinMax and
grouped Atlas are the published ADR 0102 counts, quoted, not recomputed.
Their point-adjusted F1 figures are the grouped figures from that same record.
Beyond grouped MinMax is catches minus the published grouped MinMax catches.

| Edition | Row | Caught/attacks | Beyond grouped MinMax | Point-adjusted F1 |
|---|---|---:|---:|---:|
| hai-22.04 | sandbox-candidate:own-grouping | 53/58 | 43 | 0.9593944845394529 |
| hai-22.04 | sandbox-candidate:shared-wrapper | 53/58 | 43 | 0.9593944845394529 |
| hai-22.04 | grouped MinMax (published, ADR 0102) | 10/58 | 0 | 0.19287938914889316 |
| hai-22.04 | grouped Atlas (published, ADR 0102) | 5/58 | −5 | 0.21093050043327796 |
| hai-23.05 | sandbox-candidate:own-grouping | 36/52 | 30 | 0.8494745699247331 |
| hai-23.05 | sandbox-candidate:shared-wrapper | 36/52 | 30 | 0.8494745699247331 |
| hai-23.05 | grouped MinMax (published, ADR 0102) | 6/52 | 0 | 0.34577455732863505 |
| hai-23.05 | grouped Atlas (published, ADR 0102) | 5/52 | −1 | 0.33258641641437736 |

The margin is 43 attacks on HAI 22.04 and 30 attacks on HAI 23.05, for both
candidate rows. Own grouping and the shared wrapper name the same attacks.

Attacks only the candidate catches. HAI 22.04, both rows: `test1.csv#0`,
`test1.csv#1`, `test1.csv#2`, `test1.csv#3`, `test1.csv#4`, `test1.csv#5`,
`test1.csv#6`, `test2.csv#0`, `test2.csv#2`, `test2.csv#3`, `test2.csv#4`,
`test2.csv#5`, `test2.csv#6`, `test2.csv#7`, `test2.csv#8`, `test2.csv#9`,
`test2.csv#10`, `test2.csv#13`, `test2.csv#14`, `test2.csv#15`, `test2.csv#16`,
`test3.csv#0`, `test3.csv#2`, `test3.csv#3`, `test3.csv#4`, `test3.csv#7`,
`test3.csv#8`, `test3.csv#9`, `test4.csv#1`, `test4.csv#3`, `test4.csv#5`,
`test4.csv#6`, `test4.csv#7`, `test4.csv#8`, `test4.csv#11`, `test4.csv#15`,
`test4.csv#16`, `test4.csv#17`, `test4.csv#18`, `test4.csv#19`, `test4.csv#20`,
`test4.csv#22`, `test4.csv#23`. HAI 23.05, both rows: `hai-test1.csv#0`,
`hai-test1.csv#1`, `hai-test1.csv#2`, `hai-test1.csv#3`, `hai-test1.csv#4`,
`hai-test1.csv#5`, `hai-test1.csv#6`, `hai-test1.csv#7`, `hai-test1.csv#8`,
`hai-test1.csv#10`, `hai-test1.csv#12`, `hai-test1.csv#13`, `hai-test2.csv#0`,
`hai-test2.csv#2`, `hai-test2.csv#3`, `hai-test2.csv#4`, `hai-test2.csv#5`,
`hai-test2.csv#6`, `hai-test2.csv#7`, `hai-test2.csv#13`, `hai-test2.csv#15`,
`hai-test2.csv#16`, `hai-test2.csv#17`, `hai-test2.csv#25`, `hai-test2.csv#26`,
`hai-test2.csv#27`, `hai-test2.csv#29`, `hai-test2.csv#30`, `hai-test2.csv#34`,
`hai-test2.csv#37`.

HAI 22.04 and HAI 23.05 are now seen by this candidate. This is not Atlas, and
it does not judge A2 by itself. No constant, detector, or published row changed.
The experiment log was not appended.

## Consequences

A second score of this file on these editions needs a new command and a reason
written first. The command refuses to start while
`eval_runs/v1/g1-candidate-look.json` exists.

## What would reverse this

Replacing one of these fractions, or changing a detector or a grouping constant
because of them.
