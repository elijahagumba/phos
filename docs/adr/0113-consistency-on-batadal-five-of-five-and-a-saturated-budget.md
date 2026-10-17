# ADR 0113 — The consistency detector on BATADAL: 5/5, and a budget that does not bind on hourly rows

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1, the score declared in ADR 0112
- **Depends on:** [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md)

## Context

ADR 0112 declared the window rule and one command, `scripts/measure_consistency_batadal.py`,
committed and pushed in `2406180` before it ran. It then ran once. The measured period was
3600 s, grouped MinMax replayed to its published 3/5, and the denominator was 5. Windows on
BATADAL: lags 0 and 1, every other window one sample. No constant, rule, or published row changed.
The experiment log was not appended.

## Decision

Headline, recall within budget at 8 alerts per 8-hour shift. Grouped rows are ADR 0100's
published counts, not scored again.

| Detector | Caught | Recall within budget | eTaPR F1 (reference) | eTaPR F1 (HAICon) | Point-adjusted F1 | Alerts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **atlas-v1-consistency** | **5/5** | 1.000 | 0.112 | 0.260 | 0.265 | 1335 |
| g1-grouped:atlas-mahalanobis | 5/5 | 1.000 | 0.491 | 0.652 | 0.833 | 182 |
| g1-grouped:simple-minmax (best checked) | 3/5 | 0.600 | 0.220 | 0.401 | 0.757 | 34 |
| g1-grouped:simple-steadytime | 2/5 | 0.400 | 0.452 | 0.690 | 0.593 | 144 |
| g1-grouped:simple-histogram | 2/5 | 0.400 | 0.000 | 0.487 | 0.346 | 442 |

By roadmap §2.0's headline, `atlas-v1-consistency` is strictly higher than the best grouped
checked opponent on BATADAL: 5/5 against 3/5. That is the frozen criterion's answer, and it is
recorded as such.

**What the headline cannot show here.** An 8-hour shift on hourly BATADAL holds 8 rows, and the
budget keeps 8 alerts per shift. A detector that puts one alert on every row keeps every row and
catches every attack. ADR 0106's chance null, 8 distinct rows per shift, therefore catches 5/5 on
every draw on this corpus. That is arithmetic about the declared budget, not a new measurement.
On BATADAL, recall within budget does not separate a detector from chance.

**What the reported measures show.** The detector formed 1,206 events and kept 1,335 alerts on
1,302 distinct hours, 31% of the 4,177 test hours. Grouped MinMax kept 34. On both eTaPR scores
and on point-adjusted F1 the consistency detector is the lowest of the five rows. Those measures
are reported and never headlined (§2.0), and they are not re-weighted here. They say the 5/5 comes
from alerting on a third of all hours.

## Consequences

- For A2's count, BATADAL is won by the frozen headline. Any report of A2 that counts it states,
  beside it, that random alerts also catch 5/5 on BATADAL and that this detector is lowest of five
  on eTaPR and point-adjusted F1. A2's status across the five corpora is a later record.
- BATADAL is now seen by this detector.
- The saturation is a property of §2.0's budget on hourly data, not of this detector. §2 is frozen
  and is not edited. Whether a budget-sensitive figure should be reported beside the headline for
  coarse corpora is Elijah's decision. Any such figure is a new name, declared before it is
  computed.

## What would reverse this

Running the command again, or changing the window rule, a constant, or the reader in the light of
this score.
