# ADR 0022 — Peer-group baselining, and the scoring shape that survives a wide feature set

- **Status:** Accepted
- **Date:** 2026-08-19
- **PART:** 6B
- **Supersedes:** nothing
- **Depends on:** [ADR 0005](0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md),
  [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0020](0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md),
  [ADR 0021](0021-sentiel-feature-enrichment-a-causal-trailing-history-and-the-budget-that-bounded-it.md)

## Context

PART 6A built features that can say "this is unlike *them*" and measured two things with them. The
first was encouraging: at a matched alert budget the 26-feature enriched set beat the 8-count
starter set, 25.35x the alert-on-everything floor against 16.15x. The second was not. The enriched
set had an **irreducible floor of 1,668 alerts containing no true positive**, which no threshold
below `1e6` could remove, so it could not be operated at any budget a SOC would recognise. The best
figure Sentiel had ever produced remained the *narrow* set: 110x the floor at 723 alerts.

That leaves PART 6B with two jobs that cannot be separated. The capability this PART exists to add —
peer-group baselining, the thing that catches the insider who is unremarkable against their own past
and remarkable against their team's — makes the feature set *wider*. Adding it on 6A's scoring shape
would walk straight back into 6A's wall and measure nothing. So this ADR covers both: the peer
baseline, and the change to how a window is scored that makes a wide feature set usable at all.

---

## Decision 1 — The peer group is a **role**, and it is declared rather than inferred

`phos.sentiel.peers.PeerGroups` is built from one attribute of the `EntityCatalogue`, which is read
from the release's own LDAP directory. Nothing in the module accepts an `Observation`. There is no
path from behaviour to group membership, and a test asserts it by generating wildly different
corpora and getting identical groups.

**Why declared.** A group inferred from behaviour defines "normal" using the very anomaly being
hunted: cluster users by what they do, and three people who exfiltrate data land in a group where
exfiltration is normal. Atlas refused exactly this circularity for topology (ADR 0010, declared
subsystems rather than correlation-derived ones) and Sentiel refuses it for people.

**Why role.** A peer group is meant to be *people who should behave alike*, and what determines how
somebody uses a computer is the job they do. A salesperson mails outside the organisation all day; an
electrical engineer does not. A night-shift technician logs on at 03:00; an accountant does not.
Neither fact is predicted by who signs their timesheet.

The r3.1 directory offers six candidates, and the arithmetic decided between them as much as the
argument did — 897 users in the final snapshot:

| Attribute | Distinct values | Populated | Groups ≥ 5 | Users covered |
|---|---|---|---|---|
| `business_unit` | **1** | 897 | 1 | 897 |
| `functional_unit` | 6 | 896 | 6 | 896 |
| `department` | 22 | 885 | 20 | 877 |
| **`role`** | **40** | **897** | **31** | **875** |
| `team` | 37 | **757** | 37 | 757 |
| `supervisor` | 66 | 896 | 58 | 867 |

`business_unit` is the degenerate case and there is a test for it: one value for the whole company
is a *population* baseline, not a peer baseline, and it would answer a question 6A's `_dev` family
already answers better. `team` is attractive — a median of 18 members — but is blank for 16% of the
population and mixes roles within a unit. `role` is populated for **every** user, gives 40 groups
with a median size of 8, and is the only candidate that is functional rather than organisational.

`PeerPolicy.group_attribute` is the seam. Changing it is one argument, `--group-attribute`, and a
test asserts a different attribute cuts different groups.

## Decision 2 — Five declared members minimum, and the two absences are different claims

**Five members**, so a leave-one-out baseline rests on at least four other people. This is
deliberately **not** PHOS's existing answer to "how many points before you may claim a baseline"
(eight — `BehaviouralModel.min_samples` and `HistoryPolicy.min_history_windows`), because that is a
question about *sample count* and this is a question about *distinct people*. The pool's sample count
is members times populated windows and passes eight almost immediately; what eight cannot tell you is
whether "the group's normal" is really one idiosyncratic colleague. So both gates exist and each
answers its own question: the sample count is gated at `min_history_windows` — PHOS's one answer,
reused — and the person count at `PeerPolicy.min_group_size`.

Five is a judgement and is written down as one rather than dressed up as a derivation. Below four
peers a single member is more than a quarter of the spread being divided by. It is configurable and
its boundary is tested from both sides.

**The two absences are kept apart because they are different claims**, and conflating them is how a
placeholder becomes a measurement:

- **No group at all** — absent from the directory, no value for the attribute, or a group below the
  minimum: **no observation is emitted**. The feature does not exist for this person and will not
  while the directory says what it says. Unknown is not anomalous.
- **A real group whose pool cannot speak yet** — too few samples, or too few distinct peers
  contributing: `NEUTRAL_VALUE`, which is 6A's cold-start policy applied unchanged one level out.
  The feature exists; it has nothing to say *yet*.

The first is why `PeerHistory.deviation` returns `float | None` rather than a float. A featuriser
whose emitted feature list varies per user is the price, and it is paid in one place: the emission
loop skips a `None` while keeping each feature's **index** tied to its position in the full set, so
an `Observation.id` still names a feature and a report stays traceable.

`PeerGroups` also refuses an attribute **no** catalogued user carries, at construction. That
configuration emits no peer feature for anybody, forever, and says nothing about it — the same
silent-and-permanent failure mode `HistoryPolicy` already rejects.

## Decision 3 — Causality is the signature of `observe`, and the pool is leave-one-out

`PeerHistory.observe` takes a **whole completed window at once**. That is not an ergonomic choice;
it is the causality guarantee expressed in a type. A per-user `observe` would let the first user of a
window into the pool that judges the second user of the same window, and that leak raises no error
and produces no absurd number — it quietly drags each peer mean toward the very cohort being judged.
`Featuriser._flush` was restructured to group by window start for this reason: every user in a window
is emitted, and only then is the window pooled.

The test written to break the leak makes the two answers far apart. Four peers sit at 10 for eight
windows and all jump to 100 on the ninth while the subject stays at 10. Causally the subject's pool
for the ninth window is nothing but tens, so 10 is exactly the peer mean and the answer is `0.0`; had
the ninth window been folded in first, the subject would sit far below a mean of 100 and the answer
would be strongly negative. The test asserts `0.0` **then** negative, in that order.

**The pool excludes the entity's own past.** Left in, a peer feature would be part self-baseline and
collinear with the `_dev` family sitting beside it — eight more features buying a question 6A already
answers, which is precisely the multiplicity cost ADR 0021 measured. Leave-one-out is what makes the
two families orthogonal, and it is what makes "unlike the *others* like me" a claim the feature can
actually support.

Implementation: per group, a bounded deque of windows plus incrementally maintained totals — per
member and for the group — so a leave-one-out mean and spread is a subtraction rather than a scan.
The pooled features are integer counts, so the running sums and sums of squares are exact in float64
and a perfectly constant group yields a variance of exactly zero rather than a small positive number
that would read as an enormous z-score. There is a `max(0.0, ...)` guard anyway.

## Decision 4 — Eight peer companions, one per starter count, and none for the enrichments

`PEER_RELATIVE_FEATURES` is derived from `STARTER_FEATURES`, exactly as
`BASELINE_RELATIVE_FEATURES` is, giving 34 features in `FeatureSet.PEER`. The rule is "every level
gets a peer level", which is a rule rather than a selection, and it means no feature had to be
argued for or against individually.

The enrichments get **no** peer companion. A `_dev` is already a difference, and comparing one
person's difference to their peers' differences is a second-order question that would cost the
multiplicity ADR 0021 measured without answering anything this PART asked. The full cross-product
would be over 50 features again.

## Decision 5 — The score is a sum of bounded per-feature contributions

This is the centre of the PART, so it is stated as a formula and then defended property by property:

    score(entity, window) = sum over candidate deviations of  1 - exp(-magnitude / score_scale)

**One alert per entity-window, not per feature per window.** An analyst triages a person on a day.
A feature set three times as wide should add *evidence* to a fixed number of alerts, not multiply the
alerts — which is what 6A measured happening: 3.25x the features gave 3.58x the alerts for 2.78x the
true positives.

**No single feature can dominate, structurally.** Each term lies in `[0, 1]` — open in arithmetic,
closed in float64, where a clamped magnitude rounds to exactly 1.0. One clamped feature therefore
adds at most 1.0 out of a possible `len(features)`, for *every* input including an infinite
magnitude. This is not a threshold that happened to work; it is a bound that cannot be exceeded.

**Monotone** in every magnitude and in the number of features that fired, so more evidence is never
less score. **Order-independent**, because addition commutes — which matters because the
contributions are stored as a set, not a sequence.

**Not tuned to the answer, and here is the argument that it is not.** Three things could have been
fitted and none was. The squash is `phos.models.uncalibrated_confidence`, an existing, documented,
tested function, at its existing default scale of 3.0 — the number PART 3 already put a three-sigma
departure at. The emission bar is the model's own `emit_k`, which is already PHOS's definition of
what counts as a candidate deviation, so the aggregate counts evidence PHOS already recognised
rather than evidence this PART defined. And the *shape* is the one the system already uses: PART 4B's
`update_confidence` accumulates `EVIDENCE_STRENGTH x weight` per piece of evidence in log-odds,
bounded per item, additive and order-independent (ADR 0008). This score is that same sum one layer
down, in units of "features' worth of evidence"; multiplying it by `EVIDENCE_STRENGTH` gives the
log-odds 6C's reasoning layer will accumulate. Nothing here imports `phos.reasoning` — that wiring is
6C — but the shape was chosen to be the one already in the system, and it can be checked against a
document written four PARTs earlier.

Rejected alternatives, each for a stated reason. **Max** is the current shape and fails outright.
**Mean or sum of raw magnitudes** does not help: one `MAX_MAGNITUDE` among 34 features still gives a
mean of 29,412 and still dominates. **Median** is robust to the point of blindness — a real insider
spikes on a handful of features and the median of 34 stays near zero. **A count of features past a
threshold** is the discrete version of what was built and throws away magnitude below saturation;
the squashed sum is its graded form.

## Decision 6 — A degenerate baseline means *unquantified*, not *infinitely surprising*

The second half of 6A's floor is a per-key Gaussian with nothing to divide by. A `(user, feature)`
training slice that never varied gives `stddev == 0`, `ExpectedRange.zscore` returns infinity, and
`clamp_magnitude` makes it a permanent maximum. The trap is what that reads as. Infinity here does
not mean *infinitely anomalous*; it means the model knows the value is outside everything training
saw and **has no units in which to say by how much**. A user who never touched a thumb drive and
connects one, and a user who never touched one and connects forty, become the same alert — the most
and least interesting days in the corpus, made identical.

Three treatments were considered.

**Drop it.** Defensible on PHOS's own rule — `resolve_range` returns `None` for a feature training
never saw, because "unknown is not the same as anomalous" — and rejected, because "never used a
thumb drive, now uses one" is the single most informative signal CERT's scenarios contain. Throwing
it away to avoid over-claiming would be a different dishonesty.

**Score it at the ceiling and move on.** This is what the aggregation alone does, and it is a real
improvement — a lone clamped feature contributes 1.0 and a threshold above 1.0 removes it, which no
threshold could do before. But a user with several permanently-dormant features gets a constant
per-user offset every single day, and the floor returns in aggregate form.

**Borrow the scale, which is what was built.** When the entity's own baseline has no spread, keep
that entity's own centre — the model *did* learn their normal level — and take the spread from
`FittedModel.feature_ranges`, the feature-level baseline learned across every entity. This is not a
new mechanism: it is the fallback the model already applies to a missing *key*, applied to a missing
*scale*. The thumb-drive user who connects one device now scores under a standard deviation and
falls below the emission bar entirely; the one who connects forty saturates. The distinction the
clamp destroyed is back.

Where the population has no spread either — a feature constant across every entity in training —
there is genuinely no scale anywhere. The contribution stays at its 1.0 ceiling and is **counted** in
`ScoringSummary.unquantified`, whose `note()` says the word UNMEASURED and is stamped into every
report's `source_note`. Nothing is dropped silently; the share of a score that came from departures
that could not be measured is on the record.

`--no-borrowed-scale` restores 6A's behaviour, and a test uses it to show the mechanism is the
borrow and not something else.

## Decision 7 — The corpus is scored as it streams, and the evaluation gets a window-level dataset

At 34 features the r3.1 test half is about 7.2 million `Observation` objects — roughly 11 GB of
process memory on a machine with 16 GB. PART 6A already read the corpus twice to avoid holding it
once; that is no longer enough.

So pass two never holds the corpus. `WindowScorer` consumes the stream, scores each observation, and
drops it; what survives is one `Detection` per user-window and **one representative observation per
user-window** for the evaluation's `Dataset`. Peak resident memory for the run is bounded by pass
one's training prefix rather than by the test half.

The consequence is declared rather than buried, because it changes a number a reader will see:
`EvaluationReport.n_observations` counts **user-windows** for an aggregated run, not feature
observations, and the source note says so along with the true feature-stream size. Everything else is
identical, and this is asserted rather than argued — a test evaluates the same alert set against both
a full and a window-level dataset and requires equal precision, recall, false positives and
false-positive rate. That holds because the normal-hours denominator comes from each user's first and
last window, `base_rate` already de-duplicates to user-windows, and every matching decision is about
detections and intervals.

`PrecomputedDetector` is what lets a stream-scored alert set enter the unchanged
`evaluate_entity_aware`, and a test asserts it returns exactly what `AggregatedDetector` would have
produced from the same stream. There is one scoring implementation, not two.

`static_range_model` refuses an order-dependent model. `PerKeyBehaviouralModel.fit` is declared to
return a `FittedModel`, which is right for the model layer and too wide for this one: scoring a
window at a time requires each observation to be judged independently, which `StaticRangeFittedModel`
guarantees and EWMA does not. A scorer that silently restarted an EWMA's state at every window would
produce entirely ordinary-looking numbers that mean nothing, so it raises instead.

## Decision 8 — One corpus read, two feature sets, one fitted model

A peer run scores **two** subsets of the same emitted stream: all 34 features, and the 26 per-entity
features of PART 6A. This is not decoration. Without it, a change between 6A and 6B could be the peer
features or could be the scoring shape and there would be no way to tell which. Because
`PerKeyBehaviouralModel` fits every `(entity, feature)` key independently, the baselines for those 26
features are identical whether or not the peer features were also fitted, so the control is exactly
what a 26-feature run would have produced — from the same read, the same split and the same model.

Operating points are chosen by **alert budget** rather than by threshold (`--alert-budgets`), because
a threshold means a different thing for every feature-set width and the budget is the constraint an
analyst actually has. `thresholds_for_budgets` reads the score distribution and **no label**, which
is what keeps it a choice of operating point rather than a fit to the answer.

## Decision 9 — Two caveats are declined, and a marker makes the substitution loud

Following ADR 0021 Decision 8: a peer run's source note drops PART 6·D's starter-set caveat
(`SUPERSEDED_CAVEAT_MARKER`) and **two** of PART 6A's (`SUPERSEDED_ENRICHED_MARKERS`) — the one
describing a 26-feature set and the one asserting there is no peer context at all, which is the
sentence this PART exists to delete. The other two enriched caveats, short baseline-relative
histories being noisy and two labelled insiders making recall unquotable, are as true here and are
carried forward. A test asserts each marker still matches exactly one entry, so a later PART
rewriting them fails loudly rather than stamping a stale claim onto every report.

`PEER_CAVEATS` adds four, of which one is easy to under-state and is therefore first among the new
ones: **the alert unit changed**. A threshold on an aggregate score is not comparable to a threshold
on a per-feature magnitude, so every comparison in this PART is made at a matched alert budget and
the caveat says so.

---

## Decision 10 — The shape worked, the peer features did not, and the corpus cannot test them

One run on CERT r3.1 at commit `b71c40f`, seed 7, `model:gaussian`, `train_fraction=0.5`. The peer
set emitted **34 features over 7,167,676 observations**, aggregated to **210,814 entity-windows**.
Peer grouping by `role`: **31 of 41 groups reached the five-member minimum (sizes 5–180), covering
977 of 1,000 users; 23 were ungrouped** and received the 26 per-entity features alone. Of 1,001,992
feature contributions, **244 were judged against a borrowed population spread and 0 remained
unquantified** — every degenerate baseline in the corpus had a population scale to fall back on.
The alert-on-everything floor is 53/210,814 = 2.514e-4.

Both the peer set and the 26-feature **enriched control** were scored from the *same* fitted model
and the *same* corpus read (Decision 8), so the difference between them is the peer features and
nothing else.

| Alerts | 6·D starter (8f, old shape) | 6A enriched (26f, old shape) | 6B enriched control (26f) | 6B peer set (34f) |
|---|---|---|---|---|
| 48 | **0.00x** (0 TP — its whole floor) | unreachable | 331.47x (4 TP) | **414.34x** (5 TP) |
| ~200 | 366.60x at 217 (20 TP) | unreachable | 119.33x (6 TP) | 99.44x (5 TP) |
| 500 | 154.17x at 516 (20 TP) | unreachable | 47.73x (6 TP) | 47.73x (6 TP) |
| 723 | **110.03x** (20 TP) | unreachable | 38.51x (7 TP) | 33.01x (6 TP) |
| 1,668 | — | **unreachable: this *is* its floor**, 0 TP | 16.69x (7 TP) | 19.08x (8 TP) |
| ~5,000 | 48.34x at 2,386 | 35.53x at 5,262 | 11.14x | 11.14x |

**The scoring change did what it was built to do.** PART 6A's 26 features could not be operated
below 1,668 alerts, and those 1,668 contained no true positive. The same features under aggregated
scoring reach **48 alerts at 331x the floor, still catching an insider**. A wide feature set is
usable at a SOC-sized budget for the first time, and the mechanism is the one Decision 6 predicted:
244 borrowed scales, 0 left unquantified, and the floor gone rather than merely pushed down.

**The peer features did not earn their place.** Against the enriched control they are better at 48
and 1,668 alerts, worse at 200 and 723, and identical at 500 and 5,000. Every one of those
differences is **one true positive** — five versus six, seven versus eight — out of 53 malicious
user-windows generated by two people. That is not a signal, and reporting it as one would be the
dishonesty this comparison exists to prevent. Eight more features bought nothing measurable.

**And it does not beat the narrow set.** In the 200–723 band the eight-count starter set under the
*old* shape is far ahead — 366x at 217 alerts against 99x at 200. Two things qualify that, and both
must be read with it. First, **the two shapes do not count the same thing**: under the old shape one
malicious day can yield up to eight true positives, one per feature, so its precision counts
feature-firings while the aggregated shape's counts *days*, and the aggregated shape is structurally
capped at 53 possible true positives where the old shape could reach 424. ADR 0021 already measured
that concentration and warned that "precision counts alerts; an investigator counts days". Second,
the starter set's advantage **ends abruptly**: at 48 alerts it scores 0.00x, because its own
quietest reachable point is 48 clamped alerts of which none is true. Below about 200 alerts the old
shape stops working entirely and the aggregated shape is the only thing still carrying signal.

**Why peer baselining found nothing here, and it is a fact about the corpus rather than a hedge.**
r3.1's two labelled insiders are scenarios 1 and 2, and CERT's own `answers/scenarios.txt` writes
both of them in the self-relative register: scenario 1 is a user "who did not previously use
removable drives or work after hours" who *begins* doing so, and scenario 2 uses a thumb drive "at
markedly higher rates than **their previous activity**". Both tells are departures from the
person's own past — exactly what PART 6A's `_dev` family already measures. The insider this PART
targets, the one unremarkable against their own history and remarkable against their team's, **is
not among r3.1's labelled examples**. So 6B built the capability and the corpus contains no
positive case to detect with it. That is PART 6B §5's second outcome, and the leading hypothesis is
not "peer baselining does not work" but "this corpus cannot test whether it does".

Two further contributors are named without being separable at this sample size: `role` on r3.1
yields one group of 180 members, which is a department rather than a peer group and whose spread is
correspondingly wide; and 53 malicious windows out of 210,814 cannot move a metric far enough to
clear the noise of a single alert either way.

**Nothing here is deployable.** The best figure in the table is 414x the floor at 48 alerts, which
is 10.4% precision: 43 innocent people accused for 5 true alerts, catching one of two insiders. A
multiple over random says the machinery finds signal. It does not say the machinery works.

---

## Consequences

**What this buys.** Sentiel can ask the question 6A structurally could not — whether a person is
unlike the people who should behave like them — and a wide feature set can now be operated at a
budget a SOC would recognise, which before this PART it could not be at all. `WindowScorer` is
general: nothing in it is Sentiel-specific, and a later PART may promote it if Atlas wants the same
shape.

**What it costs.**

- **Peer coverage is partial and always will be.** Users the directory does not list, or who carry
  no value for the grouping attribute, or whose group is too small, get 26 features rather than 34.
  Every report states how many that was.
- **A cold start on top of a cold start.** A group's pool needs history before it can speak, so a
  user's peer features are neutral for their group's first windows as well as their own.
- **A second-order blind spot the grouping chooses.** Judging by role means a user who changes role
  mid-corpus is judged against their new peers from the moment the merged directory says so — the
  catalogue is a last-wins merge of monthly snapshots (ADR 0020), not a timeline.
- **The aggregate hides which feature fired.** `Detection.feature` carries the largest contributor
  so an alert names something to open, but the score is the sum, and the reason for an alert is the
  whole `ScoredWindow.contributions` list rather than the one feature named.
- **`n_observations` means user-windows on an aggregated run**, which any reader comparing a 6B row
  in the experiment log against a 6A row must know. It is in the source note on every such row.

**What it does not buy.** Calibration. The aggregate is a monotone score, squashed for the confidence
field by the same function PART 3 used, and the reported calibration error is a measurement of that
fact rather than a claim about it. Nothing here may be shown to a user as a probability
(Constitution §3.3), and the reasoning layer that would give it meaning is 6C.
