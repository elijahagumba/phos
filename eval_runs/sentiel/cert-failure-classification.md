# CERT r3.1 — why Sentiel fails (Usefulness Phase U2)

Threshold **13.700640148454** (PART 6B's 48-alert operating point, reproduced as a gate before anything here was computed). The frozen row — 0.104 at 48, window recall 0.5 — is **untouched**; nothing below is logged under its name.

## The ceiling

`AggregationPolicy` sums `1 - exp(-magnitude / 3.0)` over the features that spoke. Every term is below 1, so a window in which *k* features spoke scores at most *k*.

**At this threshold, at least 14 of the 34 features must speak at once for any entity-day to alert — whatever the magnitudes.**

The bound is `<=` rather than `<` for a floating-point reason, not a mathematical one: in exact arithmetic the term is strictly below 1, and in IEEE754 it reaches exactly 1.0 once `magnitude / scale` passes 37.4299 — a magnitude of 112.29 at scale 3, against a largest observed magnitude of **18.768** anywhere in this run. The conservative reading is the one asserted, so the finding cannot be overstated by a rounding error.

```
A malicious day is read in this order, and the first clause that fits decides it:

1. ``n_speaking == 0``           -> EVIDENCE_ABSENT. No feature cleared the emission bar at all.
2. ``n_speaking < threshold``    -> STRUCTURALLY_UNALERTABLE. Features spoke, but too few: the
                                   score is bounded above by the count of speaking features, so
                                   the largest magnitude representable on every one of them still
                                   misses the cut.
3. ``score < threshold``         -> REACHABLE_BUT_SUBTHRESHOLD. Enough features spoke that the day
                                   *could* have alerted; their magnitudes were too small.
4. otherwise                     -> ALERTED.

Clause 2 is the one that matters and is the one no accuracy number would reveal. It separates "this
person was not unusual enough" from "this detector could not have said so however unusual they
were", and those point in opposite directions: the first is answered by evidence, the second only
by changing the aggregation.

```

## The two insiders

| Insider | Scenario | Malicious days | Alerted | Reachable, sub-threshold | Structurally unalertable | Evidence absent | Best rank | Malicious median | Own ordinary median |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `CSF0929` | 1 | 11 | 5 | 1 | 5 | 0 | 1 of 210,814 | 10.995 | 2.764 |
| `CCH0959` | 2 | 42 | 0 | 11 | 31 | 0 | 957 of 210,814 | 4.500 | 4.586 |

## The episode unit, against the only null that can falsify it

Each entity's own scores reshuffled across their own days — activity calendar and score distribution held, order destroyed. 200 iterations, seed 11.

| Statistic | Observed | Permuted mean | 95% interval | P(permuted ≥ observed) | Inside null |
| --- | ---: | ---: | :---: | ---: | :---: |
| reportable episodes | 40 | 41.3 | [39, 44] | 0.915 | yes |
| entity-days inside episodes | 506 | 471.7 | [360, 605] | 0.240 | yes |
| longest single episode (days) | 75 | 65.5 | [35, 113] | 0.280 | yes |
| episodes of 40+ days | 4 | 2.4 | [0, 5] | 0.140 | yes |
| malicious entity-days covered | 9 | 6.6 | [5, 9] | 0.055 | yes |
| mean leading-feature agreement | 0.339 | 0.312 | [0.274, 0.353] | 0.100 | yes |

## What the ground truth contains

Counted from the corpus's own answer files, not from the engine's output: an engine that discards a channel reports nothing about it either way.

| Insider | Labelled events | Kinds | Active days | Span | Distinct hosts/recipients |
| --- | ---: | --- | ---: | ---: | ---: |
| `CSF0929` | 35 | device 20, http 3, logon 12 | 7 | 16 d | 1 |
| `CCH0959` | 310 | device 181, email 8, http 121 | 43 | 60 d | 12 |

`CSF0929` most-named targets: `wikileaks.org` (3).

`CCH0959` most-named targets: `lockheedmartinjobs.com` (46), `aol.com` (11), `yahoo.com` (10), `lockheedmartin.com` (10), `linkedin.com` (9), `indeed.com` (9).

## How fast the aggregation saturates

| Magnitude | Contribution |
| ---: | ---: |
| 1.000 | 0.2835 |
| 2.000 | 0.4866 |
| 3.000 | 0.6321 |
| 4.000 | 0.7364 |
| 6.000 | 0.8647 |
| 6.333 | 0.8789 |
| 10.000 | 0.9643 |
| 18.768 | 0.9981 |

The out-of-band cut, recovered from the fitted model rather than assumed, is **3.0000**.

## The long false episodes

| Entity | Days in episode | Span | Distinct leading features | Above-floor rate, all their days |
| --- | ---: | ---: | ---: | ---: |
| `LUP0038` | 75 | 185 d | 22 | 115/218 = 52.8% |
| `BSB0995` | 71 | 113 d | 11 | 101/274 = 36.9% |
| `JZA0447` | 49 | 116 d | 16 | 116/255 = 45.5% |
| `CSG0640` | 41 | 107 d | 16 | 109/219 = 49.8% |

Against a population rate of 10% above the floor by construction.

## What the malicious days did to each feature

Measured against each person's **own pre-attack days** — every day of theirs before the corpus's first labelled attack, which is the data the model was fitted on. A fixed baseline, not the trailing window the `_dev` family uses: a trailing baseline chases a slow escalation, so a fixed one is the generous choice. The five largest shifts per insider, by |z| against their own pre-attack spread.

**`CSF0929` — scenario 1**

| Feature | Pre-attack mean | Malicious mean | Ratio | Shift (z) |
| --- | ---: | ---: | ---: | ---: |
| `off_hours_logon_count` | 0.008 | 0.455 | 57.73× | 5.05 |
| `removable_device_connects` | 0.016 | 0.727 | 46.18× | 4.03 |
| `file_access_count` | 0.016 | 0.727 | 46.18× | 4.03 |
| `distinct_files` | 0.016 | 0.727 | 46.18× | 4.03 |
| `logon_count` | 1.008 | 1.364 | 1.35× | 4.03 |

**`CCH0959` — scenario 2**

| Feature | Pre-attack mean | Malicious mean | Ratio | Shift (z) |
| --- | ---: | ---: | ---: | ---: |
| `distinct_pcs_peer` | -0.233 | -0.189 | 0.81× | 1.27 |
| `removable_device_connects_peer` | 0.253 | 0.598 | 2.36× | 1.12 |
| `removable_device_connects` | 2.213 | 3.262 | 1.47× | 1.07 |
| `file_access_count` | 2.087 | 3.381 | 1.62× | 0.66 |
| `distinct_files` | 2.087 | 3.381 | 1.62× | 0.66 |

## Coherence

Across 39 multi-day episodes, the mean share of an episode's days that agree on a single leading feature is **0.339**.

