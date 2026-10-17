# ADR 0096 — A sandbox experiment: alert grouping explains most of the budget gap

- **Status:** Accepted (exploratory finding; changes no engine path and no frozen result)
- **Corrected in part, 2026-10-11, by:** [ADR 0106](0106-four-checks-on-the-frozen-candidate.md).
  Decision 2 below ("the cause is grouping, not detection") held on HAI 21.03, which this record
  measured. It does not hold on the clean editions. There, the same controls show grouping adding
  11 and 9 attacks over grouped MinMax, and the candidate's loop model adding 32 more on HAI 22.04
  (21/58 to 53/58) and 21 more on HAI 23.05 (15/52 to 36/52). Decision 3, comparing grouped Atlas
  only with opponents grouped the same way, stands. The text below is unchanged.
- **Date:** 2026-10-04
- **PART:** v1 roadmap, after gate G1
- **Depends on:** [ADR 0088](0088-etapr-and-shift-budget-recall.md),
  [ADR 0095](0095-g1-baseline-table.md)

## Context

ADR 0095's G1 table put Atlas below MinMax on both scored HAI editions at the headline metric,
recall within 8 alerts per 8-hour shift: 9/38 against 15/38 on HAI 20.07, 7/50 against 14/50
on HAI 21.03. Elijah asked for an unconstrained attempt to improve Atlas and to see what
happened. One agent was given a sandbox, a scorer it could not edit and HAI 20.07 to develop
on, with HAI 21.03 held back and scored once at the end. The set-up, every file and every run
are in [`experiments/2026-10-04-sandbox/`](../../experiments/2026-10-04-sandbox/README.md).

## Decision

**1. The finding is recorded as found.** Held out on HAI 21.03, scored once each:

| Detector | HAI 21.03 |
| --- | ---: |
| G1 Atlas | 7 / 50 |
| G1 MinMax | 14 / 50 |
| Sandbox candidate | 42 / 50 |
| Control A: MinMax's range rule with the same event grouping | 41 / 50 |
| Control B: candidate without its loop model | 41 / 50 |
| Random alerts at 8 per shift, 500 draws | mean 2.8, max 9 |

**2. The cause is grouping, not detection.** G1 counts each (row, feature) alert against the
budget. Both G1 detectors spend a shift's 8 slots on consecutive seconds of one departure, so a
shift catches about one attack. Grouping departures into events and giving each event one alert
lets 8 slots reach 8 moments. MinMax's own rule, grouped that way, gets 41 of the candidate's
42. The loop model (each signal predicted from every other at lags of 0 to 60 s, one ridge
regression per signal) adds one held-out attack.

**3. This does not make A2 pass, and must not be presented as if it did.** The checked opponents
are scored as published, ungrouped. Comparing a grouped Atlas with ungrouped opponents would win
A2 on grouping alone, which any opponent could adopt: the rebuild-opponents-badly failure that
Bet 002 names as the thing that would make the bet meaningless. Any Atlas configuration that
groups alerts must be reported beside the opponents grouped the same way.

**4. Nothing enters the engine from this record.** No module in `src/` changes. Frozen rows,
§2 and `eval_runs/log.jsonl` are untouched. HAI 20.07's development score (37/38) was shaped by
the agent's feedback and is not a result.

## Consequences

- The metric's outcome is dominated by alert de-duplication. That is a finding about how
  detectors are scored at an operator's budget, and plausibly the most useful thing an operator
  could be given first.
- Atlas's distinctive contribution must be measured as what it adds **beyond** grouping. Here
  that is one attack of 50, held out.
- HAI 21.03 has now been seen by this experiment's controls as well as by G1. HAI 22.04 and 23.05,
  once fetched, are the clean test for any grouped configuration.

## What would reverse this

A grouped Atlas configuration that beats grouped checked opponents by a clear margin on HAI 22.04
and 23.05, scored once, would make Atlas's own detection the story rather than grouping.
