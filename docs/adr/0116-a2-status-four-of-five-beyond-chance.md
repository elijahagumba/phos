# ADR 0116 — A2's status: strictly higher on five of five, and beyond chance on four

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1 A2, the status declared in ADR 0115
- **Depends on:** [ADR 0115](0115-a2-status-with-a-chance-column-declared.md)

## Context

ADR 0115 declared one command, `scripts/measure_a2_status.py`, committed and pushed in `d995594`
before it ran. It then ran once. No constant, detector, or published row changed. The experiment
log was not appended.

## Decision

Recall within budget, 8 alerts per 8-hour shift, against the best grouped checked opponent
(grouped MinMax on every corpus). Chance is ADR 0106's null: 8 random rows per shift, 500 draws.

| Corpus | Exposure | atlas-v1-consistency | Grouped MinMax | Strictly higher | Chance mean / 95th / max | Above every draw |
| --- | --- | ---: | ---: | --- | ---: | --- |
| HAI 20.07 | development: tuned against | 37/38 | 32/38 | yes | 4.478 / 8 / 11 | yes |
| HAI 21.03 | held out once by the sandbox, now seen | 42/50 | 36/50 | yes | 2.728 / 5.05 / 8 | yes |
| HAI 22.04 | scored once (ADR 0104), now seen | 53/58 | 10/58 | yes | 3.808 / 7 / 9 | yes |
| HAI 23.05 | scored once (ADR 0104), now seen | 36/52 | 6/52 | yes | 3.060 / 6 / 8 | yes |
| BATADAL | scored once (ADR 0113), now seen | 5/5 | 3/5 | yes | 5 / 5 / 5 | **no** |

**Strictly higher on 5 of 5. Strictly higher and above every chance draw on 4 of 5.** The lab
scorer reproduced the sandbox harness's 37/38 and 42/50 exactly.

## Consequences

- By the frozen headline, A2's bar (strictly higher on three of five, with at least two checked
  opponents) is met five times over. Without BATADAL, whose budget chance saturates, it is met on
  all four HAI editions, each beyond every chance draw.
- This is A2's status, not its verdict. Every corpus is seen by this detector, HAI 20.07 is its
  development corpus, and the margins on HAI 20.07 (5) and 21.03 (6) are much smaller than on
  22.04 (43) and 23.05 (30). ADR 0106's flag on `P1_PCV01D` stands beside the 22.04 row.
- What A2 cannot show is held-out performance on a corpus released after this detector was frozen.
  That is W1 in `docs/phos-2027.md`, and it needs a corpus this detector has never seen.

## What would reverse this

Running the command again, or reading this table as a held-out result.
