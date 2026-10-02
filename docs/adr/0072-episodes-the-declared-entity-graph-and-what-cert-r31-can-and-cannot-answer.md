# ADR 0072 — Episodes, the declared entity graph, and what CERT r3.1 can and cannot answer

- **Status:** Accepted
- **Date:** 2026-09-02
- **PART:** Sentiel episode cycle
- **Supersedes:** nothing
- **Depends on:** [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0020](0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md),
  [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0045](0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md),
  [ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md)

## Context

Sentiel scores one entity on one day and forgets. That is the right unit for the measurement PART
6B published and the wrong unit for an investigation: r3.1's second labelled insider is malicious
across sixty calendar days, and a queue of entity-days can only offer those days one at a time,
competing with each other for the same budget. Fifty-three malicious entity-days presented as
fifty-three items is one finding shattered into fifty-three, and the shattering is what makes it
invisible at a realistic budget.

Three modules had also been written and left unwired. `phos.sentiel.sequences` computes n-gram
surprise and is called only by a fixture diagnostic. `phos.sentiel.interaction`'s
`DeclaredCounterpartyDirectory` and `interaction_is_expected` are called by nothing but their own
test. `phos.ontology.EvidenceKind.SEQUENCE_ANOMALY` has existed since PART 1, is matched by two
templates in `phos.reasoning.templates`, and has never been emitted by any engine.

This cycle builds six things together, and measures what each is actually able to say on CERT r3.1.

## Decision 1 — A trace cache, proved equivalent, because the build loop was the real constraint

Reading r3.1 end to end through `phos.sentiel.cert.CertReader` measures **2,189 events/second**,
which puts one pass at about three and a half hours; `scripts/evaluate_sentiel_baseline.py` pays it
twice. That is not a build loop, and it is the reason nothing downstream of 6B had ever been tried.

`phos.sentiel.traces` stores each entity-day as the exact end state of
`phos.sentiel.featurise._Accumulator`, plus the two facts the featuriser discards: which
counterparties the day touched, and in what order it acted. `replay_observations` reconstructs a
real `_Accumulator` and calls the featuriser's own methods, so **no feature is re-derived anywhere**.
`phos.sentiel.fast_intake` reads the five logs about **50x faster** by never building the
intermediate `EnterpriseEvent`.

**Two guards, because a cache that is nearly the featuriser's input is worse than none.**

1. `scripts/build_sentiel_trace_cache.py --verify-days N` re-reads the first N days through
   `CertReader` — the authority — and compares the traces field by field. It refuses to write on
   disagreement. On the real release it **agreed on 5,162 entity-day traces over 7 days**.
2. `scripts/measure_sentiel_episodes.py` reproduces PART 6B's frozen 48-alert row from the cache
   **before it computes anything new**, and exits if it cannot. It reproduces it exactly:
   threshold `13.700640148454447`, precision `0.10416666666666667`, window recall `0.5`, sample
   recall `0.09433962264150944` (5/53), 210,814 entity-days, 43 false positives.

The whole release caches to **340,171 entity-day traces, 48 MB, in 251 seconds**.

## Decision 2 — Episode boundaries are inherited, not chosen

Two candidate days of one entity join one episode when the gap between them is at most
`EpisodePolicy.gap`. The default is **seven days**, and it is read from
`phos.reasoning.ReasoningConfig` rather than written as a literal, because `SentielConfig` already
sets the reasoning correlation window to seven days with a reason given at the time — a window
shorter than three days splits a working pattern across a weekend, and a week is the cadence an
organisation runs on. A different number here would mean PHOS held two answers to one question, and
`EPISODE_GAP_INHERITS_CORRELATION_WINDOW` plus its test stop the two drifting apart.

**Two thresholds, because they answer different questions.** A day *joins* an episode at the
extension floor — "was anything unusual happening?" — and an episode is *reportable* only if some
day in it reaches the anchor threshold — "was anything unusual enough?". The anchor is the operating
point from the score distribution, read with no label consulted, exactly as `thresholds_for_budgets`
reads one. The floor is a declared quantile of the same distribution.

**The whole sweep is reported.** `episode_sensitivity` computes the full grid over five gaps and
five floors, and the report prints all twenty-five rows with the declared default marked. A rule
that only works at one setting is a rule fitted to the answer; showing the settings that produce a
worse episode set is what makes the default readable as a choice rather than a search result.

## Decision 3 — The graph is declared, and r3.1 declares less than it appears to

`phos.sentiel.graph.DeclaredGraph` is built only from `LDAP/*.csv`. The refusal is enforced by
construction on `phos.sentiel.PeerGroups`' pattern: **no method on the class accepts an
`Observation`, an `EnterpriseEvent` or an `EntityDayTrace`**, and a test asserts it by inspecting
the annotations. A graph inferred from behaviour would define normal using the anomaly being hunted
— the circularity ADR 0010 refused for topology and ADR 0022 refused for peer groups.

Measured against the real directory (1,000 users):

| | |
| --- | --- |
| Accounts (email addresses) | **1,000** |
| Reporting lines resolved by name | **999** (0 unresolvable, 1 rootless) |
| Distinct `business_unit` values | **1** |
| Distinct `functional_unit` values | **6** |
| Distinct `department` values | **22** |
| Distinct `team` values | **37** (159 rows leave it blank) |
| Role cohorts | **41**, modal size **180** |

**Two findings that bound everything built on top.**

**No device and no resource ownership is declared anywhere.** The directory carries role, unit,
supervisor and email; `psychometric.csv` carries five personality scores. Every user-machine pair in
r3.1 exists only in the activity logs. So no user-device or user-resource edge is built, and no path
finding rests on one (`UNDECLARED_DEVICE_OWNERSHIP`, `UNDECLARED_RESOURCE_OWNERSHIP`).

**The outermost containment level is vacuous.** All 1,000 employees are in business unit `1`, so
`DeclaredRelation.ORG_UNRELATED` — the directory knows both people and places them nowhere near each
other — **never occurs**. A path finding cut at that relation would have read zero on every
entity-day for a structural reason and would have been mistaken for a measured negative. The cut is
therefore `DISTANT_HOPS`, one level in: "no closer than a shared functional unit", which is to say
*outside your department*. The choice is made from the directory's own shape — department separates
22 ways, business unit separates nobody, `team` is blank for a sixth of the organisation — and from
nothing else. `VACUOUS_TOP_LEVEL_FINDING` records it.

## Decision 4 — The route is observed; the judgement is declared

Every hop `phos.sentiel.paths` considers is a field of a *single* activity row: this message went to
that address, this day's events named that machine. Nothing is aggregated into a profile first. The
anomaly is then decided exclusively by the directory. At no point does "unusual" mean "unlike what
you have done before" — that question is already asked and answered by 6A's `_dev` family and 6B's
peer family, and conflating the two would make this a second, worse self-baseline wearing a graph
costume.

`undeclared_recipients` (mail to an address the directory does not own) is computed, reported, and
then **excluded from the path feature set**, because `external_email_count` already measures it and
a feature set carrying both would let one act raise a score twice — the multiplicity PART 6B removed.

**The declared interaction policy is wired and, on CERT, refuses.** `interaction_is_expected` is
called on every internal counterparty pair. CERT ships no policy about which roles may talk to
which, so every verdict is `InteractionVerdict.INSUFFICIENT`. That is
`UNDECLARED_INTERACTION_CAVEAT` working end to end for the first time, not a failure.

## Decision 5 — Two new evidence kinds, each supporting exactly one explanation

ADR 0023 made the case plainly: a template supported by everything is separated from its rivals only
by its prior. So each new fact attaches to one explanation, argued from shape:

- A **rare ordered path** (`EvidenceKind.SEQUENCE_ANOMALY`) supports `compromised_account`. The
  account holder knows their own workflow; somebody else driving the account performs the same
  ordinary actions in an unfamiliar order. It is *not* evidence for `insider_misuse`, because a
  misusing holder still works the way they always have.
- A **declared-path finding** (`EvidenceKind.RELATIONSHIP_CHANGE`) supports `insider_misuse`. It is
  the holder using access they legitimately have to reach across the declared structure. It is *not*
  evidence for `compromised_account`, because an intruder's first problem is establishing access,
  and where an account's mail goes says nothing about who is typing.

Neither is listed as contradictory anywhere: manufacturing a contradiction to tidy a ranking would
corrupt the belief arithmetic, which is `phos.sentiel.templates`' own rule about role changes.

`episode_library()` copies the 6C templates with their ids, labels and priors untouched and grows
exactly two `supported_by` tuples, so an episode story and a 6C day story rank the same explanations
against the same base rates. Every reasoning invariant is re-asserted by test: the competing set is
completed with the untouched explanations at their priors (ADR 0023 D2), `insufficient_evidence` is
always present, `rank_hypotheses` refuses an alphabetical winner on a tie (ADR 0036),
`overall_confidence` stays unset (ADR 0045), evidence about another entity is refused (ADR 0023 D1),
and every evidence id resolves back through the store.

**The belief arithmetic gets worse, not better, and says so.** `EPISODE_BELIEF_CAVEAT`: the update
is additive in log-odds over facts it treats as independent, and an episode is by construction a run
of days that are not. A long episode accumulates a higher confidence than a short one for the same
behaviour, and the difference measures duration, not certainty. This *sharpens* clause (3) of
`UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT` rather than answering it.

## Decision 6 — The sequence baseline is trained on the attack-free prefix and cut without labels

`n = 3`: a bigram is a single transition — already implicit in the token alphabet — and a trigram is
the shortest window that can express a path. The alert cut is the **99th percentile of the
training-prefix day-surprise distribution**, computed with no label in sight. `SEQUENCE_SWEEP`
carries `n ∈ {2,3,4}` and cuts at `{95, 99, 99.9}` so a report can show the grid.

The token alphabet is nine symbols: an `EventKind` refined only by the declared working-hours policy
and whether a recipient domain is the organisation's own — the same two refinements the count
features already make. **Consecutive identical tokens collapse**, because volume is already measured
four ways and the sequence is for order; without the collapse an n-gram model would rediscover
`distinct_http_hosts` more expensively.

`TrainedSequences` counts grams once instead of rebuilding a `Counter` per call, which is a
performance change and must not become a semantic one — a test asserts it agrees exactly with
`sequences.sequence_surprise` on shared inputs.

**The claim being tested is narrow and the report forces the comparison.** Every count feature is
invariant to order, so a sequence score can only earn its place by firing where the counts do not.
`SequenceScores` carries `count_baseline_surprise` on the same day, and the report gives the rank
correlation between the two across the test half.

## Decision 7 — The frozen row is a gate, and nothing is scored under its name

PART 6B's row is never rewritten or re-derived. It is *reproduced* as a precondition, checked
against `eval_runs/log.jsonl` and against a constant restated in the script so the two cannot drift.
Every episode number is logged under `sentiel-episode:` — the pattern `phos.atlas.queue` set with
`atlas-queue:` — and the experiment log is append-only, so no episode row can reach the frozen one.

Peer baselining stays retired: `PEER_REGISTER_UNTESTED_CAVEAT` is unchanged and nothing here revives
the peer-relative claim.

## Consequences

### What was measured

Full tables in `eval_runs/sentiel/episode-measurement.md`. The corpus: **210,814** scored
entity-days in the test half, **53** of them labelled malicious across **2** insiders.

**Episodes compress, and the compression is real.** The 48 entity-days above the anchor threshold
assemble into **40 episodes** containing **506 entity-days** — **12.7 entity-days per item read**.
Compression is reported that way, as days-inside-episodes over episodes, rather than as corpus over
episodes: the latter would have read 5,270 and described the anchor threshold rather than any
grouping the rule did.

**At a fixed budget the episode queue shows more malicious activity, and the same insiders.**

| Budget | Queue | Items read | Entity-days contained | Malicious entity-days shown | Insiders |
| ---: | --- | ---: | ---: | ---: | ---: |
| 48 | per-day (6B) | 48 | 48 | **5** of 53 (9.4%) | 1 of 2 |
| 48 | episodes | 40 | 506 | **9** of 53 (17.0%) | 1 of 2 |
| 20 | per-day (6B) | 20 | 20 | **4** of 53 (7.5%) | 1 of 2 |
| 20 | episodes | 20 | 289 | **9** of 53 (17.0%) | 1 of 2 |

> **Corrected 2026-09-12 by [ADR 0076](0076-sentiel-fails-on-an-aggregation-ceiling-not-a-missing-corpus.md)
> (Usefulness Phase U2), refusal register R18.** The "1.8x" and "2.2x" ratios below are
> **withdrawn**. This cycle reported them with no null beside them. U2 ran that null — each entity's
> own scores reshuffled across their own days — and the 9 malicious entity-days sit at the **top
> edge** of a permuted 95% interval of **[5, 9]**, with a permuted mean of **6.63** and
> `P(permuted >= 9) = 0.055`. **The counts stand and are reproduced as a gate; the ratios read off
> them do not.** The coverage difference is not separable from chance at conventional levels on this
> corpus, and r3.1's two labelled insiders are too few to carry a ratio. The logged
> `sentiel-episode:peak` row is unchanged. The paragraph below is left as written, because what was
> claimed is part of the record.

**The insider survives as one coherent episode rather than as fragments, and it ranks first.**
`CSF0929`'s episode runs 2010-07-02 to 2010-07-23, holds 12 entity-days of which **9 are labelled
malicious**, and sits at **rank 1** of the queue. The per-day queue spends five of its forty-eight
slots on five of those same days and cannot say they are one thing. This is the capability working:
1.8x the malicious activity in front of an analyst at the same budget, and 2.2x at a budget of
twenty, because the item is first in the queue rather than spread through it.

**It is a coverage gain, not a recall gain.** `CCH0959` — the second insider, sixty days of
escalation — is absent from the episode queue exactly as it is absent from the per-day queue.
Nothing here found a person 6B could not find. What changed is how much of the person it found is
visible in one place, which is worth having and is not the same claim.

**The cost is stated.** An episode is a larger unit of reading: 12.7 entity-days per item on
average, and the queue contains episodes of 49, 41, 71 and 75 days that are entirely false. A
compression ratio that ignored that would be a conjuring trick.

**Weak-signal accumulation happens, on the strict definition.** **18 of 40** episodes reach a
behaviour family that no single one of their days reached, or carry a family only their
sub-threshold days spoke for. `CSF0929`'s episode gains `RELATIONSHIP` that way. *A first run of
this measurement counted families over every emitted contribution and found the number degenerate
— four families on almost every day, because the scorer emits at ``emit_k`` = 1.0 — so the count is
taken over out-of-band contributions (magnitude > ``band_k`` = 3.0, recovered from the fitted
model rather than assumed), which is the same test `phos.reasoning.is_out_of_band` applies.*

**The declared-graph path findings carry nothing on this corpus.** Reported with the chance
baseline beside them, which is what turns a firing count into a result:

| Finding | Fired on | Labelled malicious | Chance would give | Beats chance |
| --- | ---: | ---: | ---: | :---: |
| `distant_internal_recipients` | 132,513 | 35 | 33.3 | marginally |
| `max_declared_hops` | 191,966 | 52 | 48.3 | marginally |
| `mean_declared_hops` | 191,966 | 52 | 48.3 | marginally |
| `shared_device_distant` | 35,842 | 3 | 9.0 | **no** |

Three fire on 63-91% of all entity-days and touch malicious days at very close to the rate chance
alone would give; the fourth lands **below** chance. On r3.1 the declared graph separates nothing.

**The sequence signal carries nothing either.** At the declared p99 cut of 6.9272 nats per gram,
**2,108** of 210,814 entity-days alert, of which **1** is malicious against a chance expectation of
**0.5**. One event above an expectation of half an event is noise, not a finding. Rank correlation
with the order-blind bag-of-tokens baseline is **0.642**, so a substantial part of what the ordered
score says, the counts were already saying.

**The declared interaction policy was asked 1,202,878 times and returned INSUFFICIENT every time**,
which is `phos.sentiel.interaction` refusing correctly on a corpus that ships no policy — wired end
to end for the first time since Session S2.

**`EvidenceKind.SEQUENCE_ANOMALY` was emitted 26 times** over the top 40 episodes — the first any
PHOS engine has produced — alongside 417 `RELATIONSHIP_CHANGE` path findings, assembling 51
narratives. Every reasoning invariant held.

Logged as `sentiel-episode:peak` on `cert-r3.1-entity-day-episodes`. The frozen 6B row is
untouched and was reproduced as the gate.

### What was built and could not be honestly measured

**Path findings have no labelled positive on r3.1.** Its two insiders are scenarios 1 and 2 — a user
who begins working after hours and using removable drives, and a user who escalates thumb-drive use
before leaving. Neither is a path scenario. The CERT scenarios that *are* path-shaped — 3 (a sysadmin
plants a keylogger on his supervisor's machine, then logs in as him) and 4 (a user works from another
user's machine) — appear in r4.2 and r5.2, whose event archives are not on disk (ADR 0023 D3 records
that r4.2's answers are, and its events are not). Firing rates are measured; detection is not
claimed. `PATH_NOT_VALIDATED_CAVEAT` travels with every path number.

**The declared interaction policy has no positive case anywhere**, because no corpus PHOS reads
ships a role-interaction policy. What is demonstrated is that the refusal path works.

**Cross-domain breadth has a low ceiling.** It is counted over four `BehaviourFamily` values, one of
which (`PEER`) rests on features with no labelled positive anywhere. An episode spanning three
families is near the maximum, not modestly broad; `WEAK_SIGNAL_CEILING_CAVEAT` carries the
denominator.

### Deferred, and named rather than left to be discovered

- `linked_episodes` is quadratic in the episode count. Fine at CERT's scale; a corpus-scale caller
  must bound it.
- The trace cache holds one release. A second corpus needs its own, and the format version exists so
  a stale one is refused rather than reinterpreted.
- ADR 0044's public surfaces moved with this record: `README.md`, `encyclopedia/09-sentiel.md`,
  `encyclopedia/04-history-parts-sessions.md`, `encyclopedia/12-adr-catalogue.md`,
  `docs/adr/README.md` and `easy to reads/37-a-person-is-not-a-day.md`. Each states the coverage
  gain as coverage, the cost in entity-days read, and both nulls with their chance baselines.
