# ADR 0076 — Sentiel's CERT failure is an aggregation ceiling, not a missing corpus

- **Status:** Accepted
- **Date:** 2026-09-12
- **PART:** Usefulness Phase, item U2 (Sentiel failure classification)
- **Supersedes:** nothing
- **Depends on:** [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0032](0032-precision-policy-lost-on-cert-at-48.md),
  [ADR 0065](0065-cert-6b-queue-autopsy-no-exclusive-stem.md),
  [ADR 0072](0072-episodes-the-declared-entity-graph-and-what-cert-r31-can-and-cannot-answer.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0075](0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md)

## Context

`aggregate:gaussian:peer set (34 features)` at 48 alerts is the frozen public Sentiel ruler:
precision **0.104** (5 TP / 43 FP), window recall **0.5** — one of the two labelled insiders — and
sample recall 5/53. ADR 0074 forbids optimising it and requires understanding it first, and names
four questions U2 must answer: why the second insider is invisible to both queues, what
distinguishes the one that is found, why entirely false episodes run 49, 41, 71 and 75 days, and
what the episode model actually understands about coherence. It also requires an explicit verdict
on whether **the unit of analysis is wrong** and on whether **r3.1 contains the evidence at all**.

ADR 0075 answered the same shape of question for Atlas and found modelling error rather than
missing evidence. Whether Sentiel is in the same position or the opposite one was open.

## Decision

**1. The classification is new analysis in `phos.sentiel`, and it decides nothing by assumption.**

`src/phos/sentiel/failure.py` classifies why an insider's days do not alert;
`src/phos/sentiel/episode_null.py` asks whether the episode unit carries any temporal information;
`scripts/classify_sentiel_failures.py` runs both. `featurise.py`, `scoring.py`, `peers.py`,
`episodes.py`, `templates.py` and every threshold are **untouched**. Nothing appends to
`eval_runs/log.jsonl`; the report lands in `eval_runs/sentiel/cert-failure-classification.md`,
following ADR 0065 and ADR 0075.

The two modules are **not** re-exported through `phos/sentiel/__init__.py`. ADR 0075 records what
editing a package `__init__` cost when U1 did it; callers import from the submodules. `phos.eval`,
`phos.models` and `phos/sentiel/evaluation.py` are pinned by contract tests and are not opened here.

**2. Three gates, and each later one exists because the earlier ones are not enough.**

PART 6B's 48-alert point is reproduced through `measure_sentiel_episodes.check_frozen_row` — the
same gate the episode cycle already used — and the run stops on any disagreement past 1e-12. It
reproduces exactly: threshold `13.700640148454447`, precision `0.10416666666666667`, window recall
`0.5`, sample recall `0.09433962264150944`, 210,814 entity-days, 43 false positives.

The **second** gate reproduces ADR 0072's published episode set — **40 reportable episodes over 506
entity-days** — because the permutation null reassembles episodes from `(day, score)` pairs rather
than from `Episode` objects, for speed. A fast reimplementation that disagreed with the published
rule would make every null that follows a null about the wrong thing. It agrees exactly.

The **third** gate reproduces ADR 0072's published **coverage** figure — the **9** malicious
entity-days the episode queue shows at budget 48 — before the null that reads it against chance is
allowed to mean anything. It is the figure ADR 0072 took a ratio from, so a null computed beside a
different count would be a null about a different claim. It agrees exactly.

**3. The deciding instrument is a counterfactual settled by arithmetic, not by search.**

`AggregationPolicy` sums one squashed term per speaking feature,
`1 - exp(-magnitude / score_scale)`. Every term is below 1, so a window in which *k* features spoke
scores **at most *k***. Setting every speaking feature to the largest magnitude representable is the
strongest intervention available; a day that still does not alert under it is **structurally
unalertable**, and its failure is a property of the aggregation rather than of how unusual the
person was.

This is the Sentiel analogue of ADR 0075's instrument. There, the model's behaviour on
declared-normal data it never saw showed the alert load was the model's own. Here, the ceiling shows
whether a missed day was ever missable.

**The bound is `<=` and not `<`, and the difference is floating point rather than mathematics.** In
exact arithmetic the term is strictly below 1. In IEEE754 it reaches exactly `1.0` once
`magnitude / scale` passes **37.4299** — magnitude 112.29 at the policy's scale of 3, against a
largest magnitude of **18.768** anywhere in this run. A first draft of the module asserted the
strict bound; its own test failed it, and `features_required` was off by one at an integer
threshold as a result. Both are recorded here rather than quietly fixed, and the module now asserts
the conservative version, which can only ever *under*state how unalertable a day is.

**4. `CEILING_PRECEDENCE` states the reading order in one place**, and the clause that matters is
the second: it separates "this person was not unusual enough" from "this detector could not have
said so however unusual they were". Those point in opposite directions and no accuracy number
distinguishes them.

**5. The episode unit is judged against the only null that can falsify it.** Each entity's own
scores are reshuffled across their own days: the activity calendar and the whole score distribution
are held, and only the order is destroyed. Everything the gap rule is entitled to use is preserved
except the one thing it claims to find. 200 iterations, seed 11, reported with the observed value
beside them.

**Six statistics, not four.** The four structural ones — episode count, entity-days contained,
longest episode, episodes of 40+ days — plus the **coverage** the claim in ADR 0072 rests on and the
**coherence** share that answers ADR 0074's fourth question. The coherence null carries each day's
leading feature along with its score, because the two are readings of the same scored day and
redealing one without the other would answer a question nobody asked; `_episodes` is generic over
the row shape so the gap rule is written once for both and a second copy of it cannot drift.

## Measured on CERT r3.1, seed 7, no threshold search

`eval_runs/sentiel/cert-failure-classification.md`.

**6. At this operating point at least 14 of the 34 features must speak at once for any entity-day
to alert, whatever the magnitudes.** That is the whole finding in one number. The score cannot be
reached by depth, only by breadth: a feature at magnitude 6.33 contributes 0.879, against 0.632 for
one sitting exactly at the out-of-band cut of 3.0. A 2.1× difference in magnitude buys a 1.39×
difference in contribution. The aggregation flattens *unusual* and *extraordinarily unusual* into
nearly the same number.

**7. Why `CCH0959` is invisible: neither absent nor outranked.**

| | `CSF0929` (scenario 1) | `CCH0959` (scenario 2) |
| --- | ---: | ---: |
| Labelled malicious entity-days | 11 | 42 |
| Alerted | **5** | **0** |
| Reachable, magnitudes too small | 1 | 11 |
| **Structurally unalertable** | 5 | **31** |
| Evidence absent | 0 | 0 |
| Best rank of any malicious day | **1** of 210,814 | **957** of 210,814 |
| Median score, malicious days | 10.995 | 4.500 |
| Median score, their own ordinary days | 2.764 | **4.586** |

**31 of `CCH0959`'s 42 malicious days could not have alerted at any magnitude**, because fewer than
14 features spoke on them at all. Eleven more could have and did not. None was **outranked**: the
best reached rank 957, and the question of what beat it never arises, because the day was never a
candidate. Nor is the evidence **absent**: every one of the 42 days had features speaking, and the
strongest reached magnitude 6.33 on `new_counterparties` — the feature ADR 0072 built for exactly
this ("recipients and web hosts new to this user").

The sharpest comparison needs no threshold at all: **`CCH0959`'s malicious days score *below* their
own ordinary days at the median**, 4.500 against 4.586. The detector cannot separate this person's
two-month theft from this person's ordinary fortnight.

**8. What distinguishes `CSF0929` is a near-zero baseline, not a larger crime.** `CCH0959` has
**310** labelled malicious events over 43 active days; `CSF0929` has **35** over 7. The insider with
nine times the malicious activity is the invisible one.

Measured against each person's own pre-attack days — a fixed baseline, which is the generous choice,
since the trailing window the `_dev` family uses would chase a slow escalation:

| Insider | Feature | Pre-attack mean | Malicious mean | Shift |
| --- | --- | ---: | ---: | ---: |
| `CSF0929` | `off_hours_logon_count` | 0.008 | 0.455 | **z = 5.05** (57.7×) |
| `CSF0929` | `removable_device_connects` | 0.016 | 0.727 | z = 4.03 |
| `CCH0959` | `removable_device_connects` | 2.213 | 3.262 | **z = 1.07** |
| `CCH0959` | `new_counterparties` | 2.654 | 3.452 | z = 0.41 |

**Scenario 1 is an onset from zero; scenario 2 is an escalation from an established base.** A
person who never logged on after hours and never touched a removable drive, starting to do both,
moves every count, every `_dev`, every `_peer`, every `_diff` and every `_trend` that touches those
two behaviours **at once**. `CSF0929` reaches **19** out-of-band features on a malicious day and a
**median of 10**; `CCH0959` peaks at **8** and has a **median of 0** — half their malicious days
carry no out-of-band feature at all. One behavioural change, multiplied by the feature set's own
redundancy into the breadth the aggregation requires.

That redundancy is the multiplicity ADR 0021 bounded as a false-alarm cost. It is also the only
reason the one true positive is found. **The correlated feature families that inflate the false
alarms are what make scenario 1 detectable at all**, and nothing in the engine separates the two
effects.

**9. `CCH0959`'s job-hunting is in the corpus and cannot reach the feature space.** 121 of their 310
labelled events are HTTP requests led by `lockheedmartinjobs.com` (**46**), with `linkedin.com`,
`indeed.com`, `careerbuilder.com`, `monster.com`, `craigslist.org` and `simplyhired.com` behind it;
**7 of the 8 labelled emails are addressed to `Mario.Truman.Telsa@lockheed.com`** — a competitor —
and the eighth to a colleague. The corpus states the motive in plain text. The 34 features count
*how many* distinct hosts and *how many* external mails, never *which*: `distinct_http_hosts` moves
from 62.394 to 63.667 across the attack, a ratio of 1.02. Ten new hosts over 60 days sits below this
user's own ordinary novelty rate of **2.654 new counterparties a day**, and two of the ten are
webmail rather than job boards.

**10. The long false episodes are a gap-rule artefact. Every episode statistic is inside the null.**

| Statistic | Observed | Permuted mean | 95% interval | Inside null |
| --- | ---: | ---: | :---: | :---: |
| Reportable episodes | 40 | 41.3 | [39, 44] | yes |
| Entity-days inside episodes | 506 | 471.7 | [360, 605] | yes |
| Longest single episode (days) | 75 | 65.5 | [35, 113] | yes |
| Episodes of 40+ days | 4 | 2.4 | [0, 5] | yes |

Reshuffling each entity's scores across their own days — destroying all temporal structure —
reproduces the entire episode set. The four long false episodes belong to entities that sit above
the extension floor on **36.9% to 52.8% of all their days**, against a population rate of 10% by
construction. A 75-day episode is what the seven-day gap produces when an entity is above the floor
half the time: it is not a behavioural regime the model found, it is a base rate being chained.

**11. The episode model understands nothing a human would call one story.** The mean share of an
episode's days agreeing on a single leading feature, over the 39 multi-day episodes, is **0.339**
observed against **0.312** permuted (95% interval [0.274, 0.353], `P(permuted >= observed) =
0.100`) — inside the null, and so indistinguishable from what the same reshuffle produces with no
temporal structure to find. The 75-day episode is driven by **22 distinct leading features** across
its 75 days.

An earlier draft of this ADR asserted **0.317** and **[0.273, 0.367]** here from a scratch probe the
committed runner did not reproduce. The runner now computes this null — `coherence_permutation_null`
— and gates its observed value against the share the report prints, to 1e-12, so the two cannot
describe different statistics. The measured interval is **tighter** than the drafted one and the
reading is unchanged.

**12. ADR 0072's coverage gain is weaker than it was stated, and this must not be buried.** The 9
malicious entity-days the episode queue puts in front of an analyst is reproduced — as the run's
**third gate**, beside the 48-alert point and the episode set — but against the same null the
permuted mean is **6.63** with a 95% interval of **[5, 9]** and `P(permuted ≥ 9) = 0.055`. The
observed value sits **at the top edge of the interval, not outside it**. The gain is real in the
sense that it was measured, and it is **not separable from chance at conventional levels**. ADR
0072's "1.8× the malicious activity in front of an analyst" describes a ratio the measurement
cannot carry. The logged `sentiel-episode:peak` row is **not** rewritten — the number stands; what
changes is what may be claimed from it.

The null holds each entity's calendar fixed, so a malicious day keeps its date and only the score
standing on it is redealt from that entity's own distribution. It therefore asks the one question
the coverage claim needs: whether the queue's malicious coverage beats chance placement of the same
person's own unusual days. An earlier draft of this ADR asserted these three figures from a scratch
probe the committed runner did not reproduce; the runner now computes them and they come out
identical.

## Consequences

**Gained, and it redirects U4 and U5.** Sentiel's failure on r3.1 is an **aggregation ceiling**, not
an absent corpus. The evidence for scenario 2 is in the corpus, is representable, and reaches
magnitude 6.33 on the feature built for it; the scoring cannot hear it because it demands 14
simultaneous departures and caps what any one feature may contribute. That is the same class of
answer ADR 0075 gave for Atlas — **modelling error, not missing evidence** — reached by a different
instrument, and it means both engines' headline failures are now diagnosed as ours.

**Gained, second: the unit of analysis is not the binding constraint.** ADR 0074 asked whether the
person-day is the wrong object and whether the episode is a better one. Both are wrong, and **for
the same reason**: the episode inherits its rank from `peak`, the maximum day score, so it inherits
the ceiling entire. Changing the time unit could not have helped and did not. Naming a better unit
is a valid U2 outcome and the measurement declines to name one, because no unit over this feature
space escapes a per-feature cap of 1.0. **The aggregation is the constraint.**

**Cost, and it must not be papered over.** This ADR does **not** make Sentiel find `CCH0959`. No
threshold moved, no policy was refitted, and 0.104 at 48 is still the number. Knowing that the
ceiling is 14 features is not permission to raise a cap, widen a band, or score a subset — ADR 0065
already refused the named-subset move on this corpus, and doing it here would be the "Atlas V47,
97.3%" outcome the phase exists to prevent.

**Cost, third, and it is a process cost rather than a measurement one.** Two of this record's
figures were asserted before the committed runner computed them: the coverage null (item 12) and the
coherence null (item 11). Both were caught by auditing this ADR's numbers against the runner's own
JSON rather than by a test, which is the weakest way to catch it. The coverage figures proved
**exactly right** and the coherence figures proved **wrong** — 0.317 against a measured 0.312, and an
upper interval bound of 0.367 against a measured 0.353. That asymmetry is the argument against ever
publishing a hand-measured number: the drafting process gave no signal which of the two was which.
Both are now computed by the runner, the coverage figure is gated against ADR 0072's published count
and the coherence null against the share the report prints, and this is the **second** session in a
row to record this same failure (ADR 0075 records it for U1). The lesson is not "check more
carefully" — it is that a figure in a PHOS record must come from the runner or not appear.

**Cost, second.** The `evidence_absent` count is 0 for both insiders, and a reader who takes that as
"the corpus holds everything needed" has misread it. It means only that *some* feature spoke on
every malicious day. Register entry R16 carries what the feature space cannot express at all.

**Unexplained, and named rather than papered.** Whether a non-saturating aggregation would actually
surface `CCH0959` is **not measured here**. The ceiling proves the current one cannot; it does not
prove an alternative can, and the eleven reachable-but-sub-threshold days say the magnitudes are
small even where breadth is sufficient. Testing that needs its own session and its own ADR, and it
is optimisation, which this phase defers.

**What this points at.** Three things, none started. An aggregation whose per-feature contribution
is not capped, measured against the ceiling this session quantified. A feature that reads *which*
host or *which* recipient rather than how many, which is the only thing that could express scenario
2's motive. And a peer-relative or content-aware channel that does not inherit the same cap.

## Alternatives considered

- **Report a quieter or wider operating point now that the ceiling is known.** Rejected. ADR 0074
  forbids optimising in this item, ADR 0065 already refused the subset move, and a diagnosis
  published beside its own remedy is the pattern this phase was written to avoid.
- **Conclude `CCH0959` is simply not detectable and close the question.** Rejected, and it is the
  tempting one. The evidence reaches magnitude 6.33 on the feature designed for it and the motive is
  spelled out in the URLs; "we did not find it" is not "it is not there", and U2's own
  `success_is_not` names that confusion.
- **Report the verdict as "present but unweighted", the framing U2 offered.** Rejected as imprecise.
  The features *are* weighted — they are 4 of the 34 and they contribute — and the failure is that
  no weight on fewer than 14 of them can reach the cut. `STRUCTURALLY_UNALERTABLE` is a fourth
  answer the three-way question did not contain, and inventing a fit to the offered three would have
  hidden the mechanism.
- **Retire the episode unit.** Rejected. U2's `success_is_not` forbids retiring it without
  evidence, and the evidence here is that the unit adds no temporal information *at this operating
  point on this corpus* — which is a statement about the gap rule meeting a 10% floor rate, not a
  proof that no episode rule could work. The refusal is recorded; the unit is not deleted.
- **Treat the permutation result as refuting ADR 0072's coverage gain.** Rejected in the other
  direction. `P = 0.055` is not a refutation and the 9 days were really counted. Reporting it as a
  null result would be as dishonest as reporting 1.8× was.
- **Use a trailing baseline for the shift table, matching what `_dev` does.** Rejected as the
  primary and named as the generous choice: a trailing window chases a 60-day escalation and would
  make scenario 2 look even flatter. Measuring against the fixed pre-attack history is the reading
  most favourable to the engine, and scenario 2 fails it anyway.
