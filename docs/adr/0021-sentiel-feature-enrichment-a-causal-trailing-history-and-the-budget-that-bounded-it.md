# ADR 0021 — Sentiel feature enrichment: a causal trailing history, the budget that bounded it, and what it was worth

- **Status:** Accepted
- **Date:** 2026-08-19
- **PART:** 6A
- **Supersedes:** nothing
- **Depends on:** [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0005](0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md),
  [ADR 0020](0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md)

## Context

PART 6·D read CERT r3.1 into the ontology and logged Sentiel's first real number: precision
0.004061 on 1,686,512 test observations, about 16× better than a detector that alerts on every
user-window. That number came from eight raw daily counts, and its weakness was understood before
it was measured. A raw count says what someone *did*. It does not say whether that is normal **for
them**, whether it is a *change*, or **who** they were doing it with. CERT's own scenario
descriptions are written almost entirely in those three registers — a user who "begins logging in
after hours", who uses a thumb drive "at markedly higher rates than their previous activity", whose
file searches occur "more and more frequently over a 3 month period", who "logs into another user's
machine". Eight levels cannot express any of that.

This PART adds features that can, strictly inside the featurisation layer, and re-measures. It does
**not** add peer-group baselining — that is 6B — so the class of insider who is unremarkable
against their own past and remarkable against their team's is still out of reach, by construction.

---

## Decision 1 — A causal, rolling, per-entity trailing history, with the ordering as the guarantee

`phos.sentiel.history.TrailingHistory` maintains, per `(user, feature)`, a bounded window of that
user's own recent values, and per `(user, counterparty-kind)`, a bounded rolling set of the names
they have been seen with. Every enriched feature is computed from it.

**Causality is enforced by structure, not by discipline.** The reading methods (`deviation`,
`difference`, `trend`, `new_counterparties`) are pure with respect to the object. `observe` is the
only mutator. `Featuriser._flush` reads a window, emits it, and *then* folds it in — and windows are
flushed strictly in time order, so the history a window is judged against holds every earlier window
of that user and no later one.

The alternative — computing a trailing mean over a pandas rolling window after the fact — was
rejected because the off-by-one that includes the current row in its own baseline is invisible in
the output. It does not crash and it does not produce absurd numbers; it quietly drags the mean
toward the value being judged and flattens exactly the spikes the feature exists to find. So the
test that would fail is written explicitly: eight windows of 10 give a trailing standard deviation
of 0, so a value of 100 is reported at the cap; had it leaked in first, the mean would be 20, the
standard deviation 30, and the answer a comfortable 2.67.

Rejected alternative: an **all-time** mean per user. It is cheaper and it is wrong for the same
reason a fixed training window is wrong — a user who changes role is then permanently anomalous
against a self they no longer are. A bounded window is what makes "normal for them" track a
drifting-but-normal person.

## Decision 2 — One documented neutral for cold start, one documented cap for zero variance

Two boundaries put an unusable number into an `Observation` if they are not decided explicitly.

**Cold start.** Before a user has `min_history_windows` populated windows there is no baseline, so
every baseline-relative, trend and new-counterparty read returns `NEUTRAL_VALUE`, which is `0.0` and
is a named constant rather than a bare literal. Zero because zero is the value that *claims
nothing*: no departure, no change, nobody new. Any other sentinel — `-1`, a large magic number, a
`NaN` — is read by a downstream model as evidence of something, and the model has no way to know it
was a placeholder.

The cost is stated rather than hidden: **a model cannot distinguish "no history" from "perfectly
ordinary"**, so a user in their first eight active windows is invisible to every baseline-relative
feature. Encoding cold start as a separate feature was considered and rejected as scope this PART
does not have; it is noted for 6B.

**Zero variance.** A user who has never varied has a trailing standard deviation of zero, and
dividing by it is the obvious way to put an infinity into a feature. The policy: identical value →
`0.0`; any other value → `deviation_cap`, **signed**. The departure is real and unmeasurable in
standard deviations, so it is reported at the ceiling rather than as an infinity that would not even
serialise. Every finite deviation is clamped to the same cap, so one pathological window cannot
dominate the second-stage baseline `phos.models` later learns over these features.

Deviations are **signed**. A collapse in activity and a spike are different behaviours and the
feature keeps them apart; the Gaussian model takes an absolute z-score of the feature afterwards, so
nothing is lost by carrying the sign and something is gained.

## Decision 3 — The window lengths, and why each is that number

| Knob | Value | Why |
|---|---|---|
| `trailing_windows` | 30 | About six working weeks: long enough to average over a month's rhythm, short enough that a change of role stops being judged against the old one within a quarter. |
| `min_history_windows` | 8 | Matches `BehaviouralModel.min_samples`. PHOS gives **one** answer to "how many points before you may claim a baseline", not two. |
| `trend_windows` | 7 | One working week, so a weekly rhythm contributes a full cycle rather than a fraction of one. |
| `deviation_cap` | 10.0 | Past ten trailing standard deviations the number has stopped being informative. |

All four are configurable on `HistoryPolicy`, and a policy under which a feature could never leave
its cold start — `min_history_windows` past `trailing_windows`, or a trend longer than the memory
can supply — is **rejected at construction**. That failure mode is worse than a crash because it is
silent and permanent: the feature is emitted forever, always neutral, and nothing says so.

Windows are counted in **populated** windows, not calendar days. The featuriser emits nothing for a
day a user was idle, so the history indexes activity. A first difference therefore steps from what a
user last did rather than from an implied zero, and a fortnight's leave closes rather than reading
as a collapse and a recovery.

## Decision 4 — Twenty-six features, and the two budgets that bounded the set

The exhaustive design — every enrichment operator applied to every base feature — is over fifty
features. It was rejected on two grounds, one physical and one statistical.

**Memory.** A Pydantic-v2 `Observation` costs **1,539 bytes** of process memory, measured on this
machine rather than estimated. r3.1 produces 340,171 user-windows, so **each emitted feature costs
about 0.49 GiB across the corpus** and about 0.30 GiB for the test half alone. Fifty features is
24 GiB; the machine has 16. The feature count is not a free parameter.

**Multiplicity.** The baselines in `phos.models` judge every feature independently and
`ModelDetector` emits one candidate per feature per window, so **each added feature is another
opportunity to raise a false alarm on every user-day**. Adding features that are strongly collinear
with ones already present — and a trailing slope is a close cousin of a deviation from a trailing
mean — costs precision without adding information. Leanness here is not a concession to the
hardware; it is also the better experiment.

So the set is 26, a **strict superset** of the eight starter counts so any change in the numbers is
attributable to what was added:

| Family | Count | What |
|---|---|---|
| Starter | 8 | Unchanged, so the level is still available beside every enrichment. |
| Baseline-relative | 8 | `*_dev` for **every** starter count, as PART 6A §5.2 requires. |
| Temporal | 6 | `*_diff` and `*_trend` for three signals. |
| Relationship | 4 | `distinct_email_recipients`, `external_email_ratio`, `new_pcs`, `new_counterparties`. |

The temporal subset is **not** a guess. `ONSET_SIGNALS` is off-hours logons, removable-device
connects and file accesses, because those are the three behaviours r3.1's own
`answers/scenarios.txt` describes as beginning or escalating. `external_email_count` — escalating in
scenario 4 alongside the file searches — was the next candidate and was left out on the budget
above; its level and its `_dev` companion are still emitted.

New counterparties are counted in **two** memories, not one. A machine is somewhere a user acts
*from*; a recipient or a web host is somewhere data can *go*. Pooling them lets a steady trickle of
new web hosts bury the single new workstation that is scenario 4's whole tell.

## Decision 5 — The relationship features are per-entity, and a test says so

Every feature in this PART is computed from one user's own events and one user's own history.
Nothing reads another user. "New" means **new for this user** — a machine all their colleagues use
is still new to someone who has never logged into it, which is the reading scenario 4 needs.

This is asserted as behaviour, not as a comment: adding a second user who generates four hundred
logons a day on a different machine, visits the same hosts and mails strangers leaves the first
user's twenty-six features **byte-identical**, and so does removing everyone else. That is the
boundary 6B is on the far side of, and it is now a regression test rather than an intention.

## Decision 6 — The starter set stays the default, and one script measures both

`Featuriser.feature_set` defaults to `FeatureSet.STARTER`. Every caller written against 6·D keeps
its behaviour, and — more importantly — **the 6·D baseline stays reproducible from this same code**.
`scripts/evaluate_sentiel_baseline.py --feature-set starter` reruns it through the identical split,
model, metrics and code path that the enriched run uses, so a difference between the two numbers is
a difference in the features and nothing else. Without that, "did enrichment help?" would be
answered by comparing two code paths.

## Decision 7 — The corpus is read twice, and a check keeps the split PART 3's

At 26 features the corpus does not fit in memory (Decision 4), so the script reads it twice: pass
one takes the attack-free prefix, fits, and drops it; pass two takes the remainder. Pass one stops
at the first labelled attack instead of running to the end, so the cost is about 1.3 reads.

The risk is that a hand-rolled streaming split silently stops agreeing with PART 3's
`train_test_split`. Two things close it. First, `check_the_attack_bound_the_split` verifies after
pass two that the `train_fraction` ceiling falls *after* the first attack — that the attack, which
is the only rule the stream can apply, is the one that binds — and raises with the fraction to use
otherwise. Second, a test asserts the streamed halves reproduce `train_test_split`'s partition
**and its values** exactly, for both feature sets, on a fixture whose attack starts 41% of the way
through, as r3.1's does.

## Decision 8 — One PART 6·D caveat is declined, not edited

`SENTIEL_CAVEATS` is defined in `phos.sentiel.evaluation`, and PART 6A must not modify the
entity-aware evaluation. Its second entry asserts the featurisation is the eight-count starter set
with no relationship context. Half of that is still true — there is still no peer context — and half
of it stops being true the moment an enriched run is logged.

So `enriched_source_note` **drops that one entry** (matched by the exported
`SUPERSEDED_CAVEAT_MARKER`) and states both halves correctly in `ENRICHED_CAVEATS`. Editing the
constant was rejected: it would modify the evaluation module and break an existing 6·D test.
Appending the new caveats beside the old was also rejected — a source note that says both "8 count
features" and "26 features" is a note that contradicts itself, and a caveat block a reader cannot
trust is worse than none. A test asserts the marker still matches **exactly one** entry, so if 6B
rewrites that caveat the substitution fails loudly instead of stamping a stale claim on every run.

Every logged enriched run also carries a **side-by-side** with 6·D in its `source_note`: both
precisions, both multiples over the alert-on-everything floor, and a verdict. The verdict band
(±5%) is a **reporting convention, not a significance test** — with two labelled insiders no
significance test is available, and implying otherwise would be the dishonesty this comparison
exists to prevent.

---

## Decision 9 — The measured result, and what it says about the layer below

Six runs on CERT r3.1 at commit `9ce7298`, seed 7, `model:gaussian`, identical split and code path,
`--feature-set` the only difference. The alert-on-everything floor is 53/210,814 = 2.514e-4.

**The starter reproduction came back to every digit** — 1,686,512 observations, 9,850 alerts,
precision 0.004061, ECE 0.7288, median latency 138.0 h — which is what licenses reading the
difference below as a difference in features.

**At the default threshold the enrichment is worse:** 12.52× the floor against 6·D's 16.15×. 3.25×
the features gave 3.58× the alerts and only 2.78× the true positives. That is the multiplicity cost
this ADR predicted before the run, arriving exactly as predicted.

**At a matched alert budget it is better:** at ~10,000 alerts, 25.35× against 16.15× — 1.57× the
precision; at ~6,000 alerts, 35.53× against 25.73×. The features carry real signal and the headline
was an artefact of comparing at a fixed per-feature threshold. This is why
`--extra-thresholds` exists, and it is the reading that should be quoted.

**Two findings qualify the win, and they matter more than it does.**

*Coverage moves the other way.* At a matched budget the enriched set produces more true-positive
alerts (70 vs 40) across **fewer distinct malicious days** (13 vs 17 of 53). Twenty-six features can
all fire on one bad day, so its alerts concentrate. Precision counts alerts; an investigator counts
days.

*The enriched set cannot reach a deployable alert budget at all.* It has an irreducible floor of
**1,668 alerts containing zero true positives**, against the starter set's 48 — detections clamped
to `MAX_MAGNITUDE`, which no threshold below 1e6 can exclude. **This is a composition failure, not a
feature failure.** The enrichments are sparse by construction: a `*_dev` is a documented neutral
`0.0` throughout cold start (Decision 2), and `new_pcs`, `*_diff` and `*_trend` are `0.0` on most
days for most people. A great many `(user, feature)` training slices are therefore perfectly
constant; `GaussianBaseline` learns a standard deviation of zero; `ExpectedRange.zscore` returns
infinity for any departure; `clamp_magnitude` makes that a permanent maximum-magnitude alert.

The cost is concrete: the best figure Sentiel has produced is the **starter** set at threshold 6.0
— 110× the floor at 723 alerts, about 1.4 alerts a day across a thousand people, a budget a real SOC
could work — and the enriched set can never be quieter than 1,668 alerts, all false. **Below ~1,700
alerts the enrichment is not worse, it is unusable.**

**Nothing here is deployable.** Even 110× the floor is 2.8% precision: 703 false accusations of
innocent people for 20 true-positive alerts. A multiple over random says the machinery finds signal.
It does not say the machinery works.

**The conclusion drawn, and deliberately not acted on in this PART.** One alert per feature per
window is the wrong shape for a wide feature set, and a per-key Gaussian degenerates on a sparse
one. A per-user-window score — one alert per user-day, aggregated across features — would remove
both the multiplicity penalty and the concentration effect at once; a variance floor, or `IqrBaseline`,
would remove the clamped-alert floor. All of those are **modelling** changes, which PART 6A is
explicitly not permitted to make, so this PART records the failure rather than reaching across the
layer boundary to fix it. That is the finding 6B and 6C inherit.

---

## Consequences

**What this buys.** Sentiel's featurisation can now express "unlike this person", "changing", and
"someone new", which is the vocabulary CERT's scenarios are written in. `TrailingHistory` is a
general per-entity mechanism 6B can build peer baselines beside, and 6C can cite in a template.

**What it costs.**

- **A cold-start blind spot.** A user's first eight active windows have no baseline-relative signal
  at all, and the model cannot tell that from ordinariness.
- **Noise just past the boundary.** A trailing mean and spread from nine windows is a weak estimate;
  the deviations built on it swing. Stated in the caveats rather than discovered later.
- **Multiplicity.** Twenty-six features is 3.25× the alert opportunities per user-day of eight.
- **A weekly rhythm reads as movement.** With the default `WorkingHours`, all weekend activity is
  off-hours, so a user who logs on identically every day has a twice-weekly step in
  `off_hours_logon_count` and the temporal terms report it. Any real deployment must set the working
  pattern the organisation actually keeps. There is a test that documents this.
- **Two reads of a 13 GB corpus** instead of one, for the enriched set.

**What it does not buy, by construction.** Peer context. Every number here is still one person
judged against themselves.
