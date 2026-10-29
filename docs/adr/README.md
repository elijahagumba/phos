# Architecture decision records

Every significant decision in PHOS is recorded here: what the situation was, what was chosen, what
the alternatives were, and what the choice costs. Several of these records exist to document a
measured **negative** result, or a limit a component cannot pass. Those are kept deliberately.

Records are immutable once accepted. A decision that changes gets a new record that supersedes the
old one, so the reasoning at the time stays readable.

## Missing numbers

The sequence has gaps, and every gap has exactly one of three reasons. Some numbers were reserved
for a programme or skipped, and no record was ever written for them — 0277–0284 is the largest
such block, reserved for build brief E and left unwritten when that brief closed (ADR 0297), and
the older gaps are the same thing smaller. Some numbers name records that exist on a branch that
has not merged — 0328, 0330–0332, 0337–0339, 0343, 0369–0371 and 0379–0380 at the time of
writing — and the index gains them when the branch lands, unless one turns out to be the third
kind of gap. And some numbers name records withheld from publication under ADR 0342, merged or
not: 0334 is the one today, its index row says so, and what the record says is not restated
anywhere. A missing number is not a missing record; it is one of these three.

## Format

Each record opens with a metadata block, then `## Context`, the decision or decisions, and the
consequences:

```markdown
# ADR NNNN — Title

- **Status:** Accepted
- **Date:** YYYY-MM-DD
- **PART:** the build stage that produced it
- **Supersedes:** nothing, or a link
- **Depends on:** links to the records this one builds on
```

`Supersedes` and `Depends on` appear where a record states them.

## Index

### Foundations

The shared vocabulary, the measurement rules, and how data enters the project.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0001](0001-ontology-value-objects-and-store-enforced-integrity.md) | Frozen value objects, reference by id, integrity enforced by the store | 1 | 2026-07-28 | Accepted |
| [0002](0002-pytest-imports-package-from-src.md) | pytest imports `phos` from `src/`, not from the editable install | 1 | 2026-07-28 | Accepted |
| [0003](0003-window-level-recall-and-false-positives-per-normal-hour.md) | Recall is window-level; false positives are per hour of normal operation | 2 | 2026-07-28 | Accepted |
| [0004](0004-first-real-dataset-and-the-operator-manifest.md) | HAI is the first real corpus, reached through an operator manifest | 2 | 2026-07-28 | Accepted, amended |
| [0005](0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md) | Fit/score separation, per-key baselines with a feature-level fallback, and attack-free splits | 3 | 2026-07-28 | Accepted |
| [0006](0006-dataset-registry-and-never-committing-data.md) | A committed dataset registry, a fetch script, and data that is never committed | none | 2026-07-29 | Accepted |
| [0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md) | Corpus intake: a confirmed licence, a version pin, and two label sources that disagree | C1 | 2026-08-21 | Accepted |
| [0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md) | Joining batch-distillation without poisoning the false-positive ruler | C2 | 2026-08-21 | Accepted |
| [0082](0082-batch-distillation-label-classes-are-phases-and-only-the-anomalous-phase-is-scored.md) | Batch-distillation label classes are phases (0 normal, 1 blind, 2 anomalous, 3 recovery); only class 2 is scored, 1 and 3 are unscored (outside the FP denominator and recall); labels block-pooled across the stride; v1.1.3 recorded, not pinned | C1 | 2026-09-23 | Accepted |
| [0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md) | Encyclopedia, easy to reads, and README must move with every `main` advancement | process | 2026-08-22 | Accepted |
| [0049](0049-split-scorecard-public-files-vs-partner.md) | Split scorecard: public files vs partner site; activate category Clock A at C1 | C0 | 2026-08-23 | Accepted |
| [0051](0051-saturated-fp-load-is-a-refused-claim.md) | Saturated FP load is a refused claim; `evaluate()` does not auto-apply | C2 | 2026-08-23 | Accepted |
| [0052](0052-scale-invariant-shrinkage-is-a-named-option.md) | Scale-invariant shrinkage is a named option; public default stays average-variance | C3 | 2026-08-23 | Accepted |
| [0053](0053-joint-vs-univariate-is-a-table.md) | Joint vs univariate is a table, not a 10× stamp | C4 | 2026-08-23 | Accepted |
| [0061](0061-clock-a-published-partner-unearned.md) | Clock A public core published; partner and product surface unearned | Ω1–Ω2 | 2026-08-23 | Accepted |

### Evidence and reasoning

What counts as evidence, and how competing explanations are held and weighed.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md) | The evidence boundary, and a confidence that means what it says | 4A | 2026-07-30 | Accepted |
| [0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md) | Written-down explanations, belief in log-odds, and never knowing for certain | 4B | 2026-07-31 | Accepted |
| [0045](0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md) | Shared narrative ranker; `overall_confidence` unset until calibrated | cycle | 2026-08-23 | Accepted |
| [0083](0083-calibrator-without-labelled-positives.md) | Calibrator without labelled positives: normal-score CDF; HAI 3.55 FP/hr logged beside frozen 53.26; distillation parity; incomplete dual win | usefulness follow-on | 2026-09-24 | Accepted |

### Atlas: the OT engine

Modelling a plant as one machine, mapping it, and turning departures into narratives.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md) | Modelling the plant as one machine, attributing what breaks, and the model that lost | 5A | 2026-08-03 | Accepted |
| [0050](0050-snapshot-joint-assumptions-are-executable.md) | Snapshot assumptions named and pinned; PCA OOS is a test, not a retune | C1 | 2026-08-23 | Accepted |
| [0054](0054-var-residual-is-a-named-experiment.md) | VAR residual is a named experiment beside snapshot Mahalanobis | C5–C6 | 2026-08-23 | Accepted |
| [0064](0064-var1-on-hai-is-louder-than-snapshot-mahalanobis.md) | VAR(1) on HAI is louder than snapshot Mahalanobis; refused as the public detector | engine week | 2026-08-24 | Accepted |
| [0066](0066-correlation-target-cannot-invert-on-hai.md) | Correlation-target Mahalanobis cannot invert on HAI three-way at frozen shrinkage | engine week | 2026-08-24 | Accepted |
| [0068](0068-the-atlas-operator-queue-cannot-be-ranked.md) | The Atlas operator queue cannot be ranked; magnitude buries the incidents, weight is constant | Build 1 | 2026-08-26 | Accepted |
| [0075](0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md) | The HAI false-alert load is modelling error, not missing evidence; 418 of 418 explained, fit is 15% of one duty cycle | U1 | 2026-09-11 | Accepted |
| [0083](0083-calibrator-without-labelled-positives.md) | Normal-score CDF; HAI `hai[designed-normal-score][after]` logged at 3.55 FP/hr beside frozen 53.26; distillation detection parity; incomplete dual win | usefulness follow-on | 2026-09-24 | Accepted |
| [0076](0076-sentiel-fails-on-an-aggregation-ceiling-not-a-missing-corpus.md) | Sentiel's CERT failure is an aggregation ceiling, not a missing corpus; 14 of 34 features must speak at once, and the episode unit is reproduced by chance | U2 | 2026-09-12 | Accepted |
| [0084](0084-non-saturating-aggregation-for-sentiel.md) | Opens the non-saturating aggregation session ADR 0076 deferred at Gate 2; success is window recall 1.0 at the frozen 48 (CCH0959 surfaced, CSF0929 kept), three candidates declared in ADR 0093, not scored | usefulness follow-on | 2026-09-27 | Accepted |
| [0085](0085-phos-demo-runs-one-incident-end-to-end-and-names-its-misses.md) | `phos demo` runs one simulated incident end to end, chooses the incident without ground truth, and names a miss or a false alarm as one | public pre-release | 2026-10-02 | Accepted |
| [0086](0086-empirical-command-baseline.md) | Empirical quantile band for command behaviour at the inherited three-sigma tail; operator false alarms 0.75 to 0.20; unauthorised write in the brief 19/20 Gaussian and 20/20 empirical; Gaussian frozen rows untouched | public pre-release | 2026-10-02 | Accepted |
| [0077](0077-realism-reaches-the-instruments-and-the-manifest-becomes-reproducible.md) | Realism reaches `_sense` and the capture; 22 of 22 corpus files byte-identical, and a `frozenset` that made four of six manifests irreproducible is fixed | U3 | 2026-09-12 | Accepted |
| [0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md) | Twelve scenarios constructible; four diagnostic questions answered as SYNTHETIC-DERIVED; real plants forward realism; quiet corpora stay byte-identical | U3 | 2026-09-15 | Accepted |
| [0079](0079-u4-renders-an-existing-narrative-in-plain-english.md) | U4 renders an existing narrative in plain English; unresolved is first-class; Sentiel ceiling appears in the output | U4 | 2026-09-16 | Accepted |
| [0080](0080-u5-three-arm-instrument-is-not-operational-usefulness.md) | U5 is an executable three-arm instrument; the crude non-operator run is not operational usefulness | U5 | 2026-09-16 | Accepted |
| [0081](0081-the-refusal-register-is-confirmed-four-entries-had-drifted.md) | The refusal register is confirmed against HEAD; four entries had drifted and were corrected | U6 | 2026-09-20 | Accepted |
| [0069](0069-cmms-exports-reach-the-work-order-inlet.md) | SAP PM / Maximo exports reach the E3 work-order inlet; no public corpus carries one, so coverage stays refused | Build 2 | 2026-08-26 | Accepted |
| [0070](0070-the-evidence-facet-replaces-summary-string-parsing.md) | The evidence facet replaces summary-string parsing; typed `facet_kind`/`facet`, no reasoning outcome moves | refactor | 2026-08-31 | Accepted |
| [0055](0055-starved-modes-fall-back-forgery-unhandled.md) | Starved declared modes fall back; matching-physics forgery is unhandled | C7–C8 | 2026-08-23 | Accepted |
| [0056](0056-three-w-is-faults-not-attacks.md) | 3W is a fault process type, not an attack row | C9 | 2026-08-23 | Accepted |
| [0057](0057-command-behaviour-is-a-stamp.md) | Command-behaviour is a stamp; narratives reconstruct to a frame or absence | D1–D2 | 2026-08-23 | Accepted |
| [0058](0058-public-command-corpus-still-absent.md) | Public command corpus still absent (Clock A restatement of 0040) | D3 | 2026-08-23 | Accepted |
| [0059](0059-explanation-geometry-and-work-order-inlet.md) | Explanation geometry is fixture-first; prior-only is silence; work orders are an inlet | E1–E3 | 2026-08-23 | Accepted |
| [0010](0010-declared-topology-and-the-granularity-hai-supports.md) | Topology is declared, never inferred, and HAI supports it only this finely | 5B | 2026-08-06 | Accepted |
| [0011](0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md) | Group before reason, the OT template priors, and two honesty guards | 5C | 2026-08-10 | Accepted |

### Atlas: the packet adapter

Reading the control network itself, and containing input that may be hostile.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md) | dpkt, the dissector seam, and containing hostile packet input | P1 | 2026-08-14 | Accepted |
| [0013](0013-command-behaviour-features-device-identity-and-the-command-graph.md) | Command behaviour: what a device *is*, what a feature may claim, and the command graph | P2 | 2026-08-14 | Accepted |
| [0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md) | Command evidence: the second boundary door, what commands discriminate, and the measurement PHOS cannot yet run | P3 | 2026-08-14 | Accepted |
| [0027](0027-unknown-master-writes-are-not-maintenance.md) | Unknown-master writes are not maintenance; known-link findings still support both | cycle | 2026-08-22 | Accepted |
| [0034](0034-command-lead-rate-zero-on-known-link-writes.md) | Lead rate still 0/16 after 0027: the battery writes from known stations | cycle | 2026-08-22 | Accepted |
| [0035](0035-unknown-master-writes-still-do-not-lead.md) | Unknown-master D2 writes: moved 4/4, led 0/4; scored apart from known stations | cycle | 2026-08-22 | Accepted |
| [0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md) | A lead tie is a refusal, not an alphabetical unique winner | cycle | 2026-08-22 | Accepted |
| [0037](0037-silence-is-judged-against-a-comparable-learned-stretch.md) | Silence is judged against a comparable learned stretch, not a rate over the whole train | cycle | 2026-08-22 | Accepted |
| [0038](0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md) | A window's story attaches graph findings by entity-reachability, not by co-occurrence | cycle | 2026-08-22 | Accepted |
| [0039](0039-ranking-contract-lock-undoing-0036-0038-must-turn-existing-tests-red.md) | Mutants that undo 0036–0038 must turn existing tests red | cycle | 2026-08-22 | Accepted |
| [0040](0040-no-labelled-public-command-corpus.md) | No labelled public command corpus; Data4Cyber pcapng is readable, labels are process phases | cycle | 2026-08-22 | Accepted |

### The simulator and the adversary

Plants we control, attacks we grade, and a harness built to find blind spots.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md) | Simulated plants, the injection hook, and the true-state record | D1 | 2026-08-15 | Accepted |
| [0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md) | The graded attack library: flavour separation, measured ground truth, and the anti-fingerprint discipline | D2 | 2026-08-17 | Accepted |
| [0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md) | The breaking harness: where it sits, how it fits a baseline, which results are clean, and what judges a miss | D3 | 2026-08-17 | Accepted |
| [0041](0041-input-hostile-report-must-not-overwrite-detection.md) | Input-hostile 04–07 must write `input-hostile-robustness`; never overwrite detection | cycle | 2026-08-22 | Accepted |

### Atlas: measured fixes

Changes commissioned by a measurement, and scored the same way.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0018](0018-phase-conditional-modelling-for-a-batch-process.md) | Seeing a phased process: why Atlas was blind on the batch reactor, and the one fix that does not cost another plant | A-FIX-1 | 2026-08-17 | Accepted |
| [0019](0019-the-settling-allowance-and-the-blind-window-it-is-bounded-by.md) | Settling after a phase change: forgiving only what the phase being left explains, and the blind window that buys | A-FIX-2 | 2026-08-19 | Accepted |
| [0026](0026-joint-distance-gating-and-the-actionable-alert-unit.md) | Joint-distance gating, and the alert unit that is a plant-moment | cycle | 2026-08-22 | Accepted |
| [0030](0030-moment-dwell-and-chronic-volume-decay.md) | Moment dwell on the joint detector; chronic volume decay on Sentiel scoring | cycle | 2026-08-22 | Accepted |
| [0031](0031-distillation-budget-refused-without-declared-phase.md) | 2–3/day refused on distillation until a declared phase exists | cycle | 2026-08-22 | Accepted; missing-column clause superseded by 0048 |
| [0048](0048-distillation-declared-phase-is-louder.md) | Distillation logs declare Executing step; phase-conditional is louder, not quieter; 2–3/day still refused | cycle | 2026-08-23 | Accepted |
| [0046](0046-data4cyber-track-a-is-process-phase-telemetry-not-a-control-room-ruler.md) | Data4Cyber Track A process-phase row; FP/hour refused; 6.6× is not 10× | cycle | 2026-08-23 | Accepted |
| [0047](0047-s7-process-parquet-is-unlabelled-track-a-refused.md) | S7 process parquet has no label column; labelled Track A refused | cycle | 2026-08-23 | Accepted |


### Sentiel: the enterprise engine

Reading an organisation rather than a plant, and scoring a claim about a *person*.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0020](0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md) | Enterprise data intake: entity-scoped truth, a reused ruler, and what CERT actually ships | 6·D | 2026-08-19 | Accepted |
| [0021](0021-sentiel-feature-enrichment-a-causal-trailing-history-and-the-budget-that-bounded-it.md) | Feature enrichment: a causal trailing history, the budget that bounded it, and what it was worth | 6A | 2026-08-19 | Accepted |
| [0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md) | Peer-group baselining, and the scoring shape that survives a wide feature set | 6B | 2026-08-19 | Accepted |
| [0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md) | Per-entity reasoning, the completed competing set, and what CERT r4.2 can unblock | 6C | 2026-08-21 | Accepted |
| [0028](0028-precision-policy-volume-peer-match-and-the-family-gate.md) | Precision policy: volume weights, peer-match discount, family gate; 6B default unchanged | cycle | 2026-08-22 | Accepted |
| [0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md) | A synthetic dataset library is not a public corpus; catalogues committed, payloads regenerated | cycle | 2026-08-22 | Accepted |
| [0032](0032-precision-policy-lost-on-cert-at-48.md) | Precision policy lost on CERT r3.1 at 48 alerts; 6B remains the headline | cycle | 2026-08-22 | Accepted |
| [0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md) | Three campaign licences confirmed; confirmation is not a detection claim | cycle | 2026-08-22 | Accepted |
| [0040](0040-no-labelled-public-command-corpus.md) | Session 5: files inspected; still no labelled command corpus | cycle | 2026-08-22 | Accepted |
| [0045](0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md) | Sentiel ranking shares ADR 0036; `Narrative.overall_confidence` stays unset | cycle | 2026-08-23 | Accepted |
| [0060](0060-sentiel-clock-a-routing-and-cert-curve.md) | Sentiel Clock A: peer routing, declared interaction, CERT curve, HR fixture | S1–S5 | 2026-08-23 | Accepted |
| [0062](0062-clock-b-freeze-before-optimise.md) | Clock B: freeze PHOS Benchmark v1 before model work; P1 stays human | Clock B | 2026-08-23 | Accepted |
| [0063](0063-declared-physical-roles-unblock-cross-plant-measurement.md) | Declared flow/pressure/pump roles; BATADAL→HAI zero-shot is a new log name; SWaT form-gated | Clock B | 2026-08-24 | Accepted |
| [0065](0065-cert-6b-queue-autopsy-no-exclusive-stem.md) | CERT 6B top-48 autopsy: no stem led every hit and none of the misses; no named subset scored | engine week | 2026-08-24 | Accepted |
| [0067](0067-follow-up-corpora-and-partner-icd-stay-closed.md) | r4.2 events, SWaT, ICSSim and the partner ICD stay closed by absence; cite new names in Benchmark v2 | engine week | 2026-08-24 | Accepted |
| [0071](0071-command-behaviour-evidence-reaches-a-template.md) | Command-behaviour evidence reaches a template; the maintenance-vs-attacker tie stays tied | session | 2026-08-31 | Accepted |
| [0072](0072-episodes-the-declared-entity-graph-and-what-cert-r31-can-and-cannot-answer.md) | Sentiel episodes: a measured coverage gain, a declared graph and a sequence signal that carry nothing | cycle | 2026-09-02 | Accepted |
| [0084](0084-non-saturating-aggregation-for-sentiel.md) | Opens the non-saturating aggregation session ADR 0076 deferred at Gate 2; success is window recall 1.0 at the frozen 48 (CCH0959 surfaced, CSF0929 kept), three candidates declared in ADR 0093, not scored | usefulness follow-on | 2026-09-27 | Accepted |

### v1 week 1

Pass criteria frozen at `93156a5`. These records do not edit roadmap §2.

| ADR | Decision | PART | Date | Status |
|---|---|---|---|---|
| [0087](0087-every-hai-version-is-registered.md) | Every HAI version is registered; the new files are not fetched | v1 week 1 | 2026-10-04 | Accepted |
| [0088](0088-etapr-and-shift-budget-recall.md) | eTaPR and shift-budget recall are metrics, not a pass mark | v1 week 1 | 2026-10-04 | Accepted |
| [0089](0089-three-published-hai-detectors.md) | Three published HAI detectors, checked against their own table; point scores not reproduced | v1 week 1 | 2026-10-04 | Accepted |
| [0090](0090-authors-hai-pipeline-matches-our-detectors-not-the-paper.md) | The authors' HAI pipeline matches our detectors, not the paper; the three are checked, the table is not | v1 week 1 | 2026-10-04 | Accepted |
| [0091](0091-haicon-2020-etapr-parameters.md) | HAICon 2020's four eTaPR parameters, recorded beside the reference defaults; 180 samples is not a fractional delta | v1 week 1 | 2026-10-04 | Accepted |
| [0092](0092-real-corpus-tests-are-marked-slow.md) | Real-corpus tests of at least five seconds are marked slow; the default suite omits them | v1 week 1 | 2026-10-04 | Accepted |
| [0093](0093-bet-001-three-candidates-declared.md) | Bet 001's three formulas are declared and pinned; none is scored on CERT | v1 S1 | 2026-10-04 | Accepted |
| [0094](0094-liar-measurement-seeds-and-pass-share.md) | Liar measurement seeds 94001-94020 and a pass share strictly above one half; no run scored | v1 T1 | 2026-10-04 | Accepted |
| [0095](0095-g1-baseline-table.md) | G1 baseline table: one ungated Atlas configuration; Atlas is below MinMax on both scored HAI editions | v1 G1 | 2026-10-04 | Accepted |
| [0096](0096-sandbox-event-grouping-explains-the-budget-gap.md) | Sandbox experiment: grouping alerts into events takes Atlas from 7/50 to 42/50 held out, but MinMax grouped the same way gets 41/50. Corrected in part by 0106: on clean HAI the loop model, not grouping, carries the gain | v1, after G1 | 2026-10-04 | Accepted, corrected in part |
| [0097](0097-hai-21-03-payloads-are-on-disk.md) | HAI 21.03's eight files are on disk, each with a sha256; they are not in git and are not fetched by --all | v1 registry | 2026-10-05 | Accepted |
| [0098](0098-hai-22-and-23-are-on-disk-and-not-scored.md) | HAI 22.04 and 23.05 are on disk, each sha256 equals the Git LFS oid, and neither is scored | v1 registry | 2026-10-05 | Accepted |
| [0099](0099-event-grouping-is-a-shared-wrapper.md) | Event grouping is a shared wrapper with the sandbox's constants; nothing is scored | v1 grouping | 2026-10-05 | Accepted |
| [0100](0100-grouped-g1-rows-and-where-atlas-loses.md) | Grouped G1 rows beside the published ones; Atlas still loses on both seen HAI editions | v1 grouped rows | 2026-10-06 | Accepted |
| [0101](0101-the-clean-hai-run-is-declared.md) | The one HAI 22.04 and 23.05 run, grouped and ungrouped, declared before it is scored | v1 clean HAI | 2026-10-06 | Accepted |
| [0102](0102-the-clean-hai-run-and-where-atlas-loses.md) | That run, scored once: Atlas is below MinMax on both editions, grouped and ungrouped | v1 clean HAI | 2026-10-06 | Accepted |
| [0103](0103-the-frozen-candidate-is-declared-on-clean-hai.md) | The frozen sandbox candidate on HAI 22.04 and 23.05, declared before it is scored | v1 candidate look | 2026-10-08 | Accepted |
| [0104](0104-the-frozen-candidate-on-clean-hai.md) | The frozen candidate on clean HAI, scored once: 53/58 and 36/52, margins 43 and 30 | v1 candidate look | 2026-10-10 | Accepted |
| [0105](0105-four-checks-on-the-frozen-candidate.md) | Four checks on that score, declared before they run | v1 candidate checks | 2026-10-10 | Accepted |
| [0106](0106-four-checks-on-the-frozen-candidate.md) | Those checks, run once: chance, one flagged valve command, the controls, and two different alert lists | v1 candidate checks | 2026-10-10 | Accepted |
| [0107](0107-the-consistency-detector-enters-the-engine.md) | The clean-HAI winner is ported into the engine as `phos.atlas.consistency`, unchanged; identity with the frozen file is a lab test | v1, after G1 | 2026-10-11 | Accepted |
| [0108](0108-consistency-evidence-routes-to-the-explanations.md) | A reading that disagrees with the rest of the plant becomes `CONSISTENCY` evidence: supports an instrument fault, contradicts a real upset, silent on intent; a third optional engine inlet | v1, after G1 | 2026-10-11 | Accepted |
| [0109](0109-liar-subtlety-zero-is-the-obvious-end.md) | Liar subtlety 0.0 is the most obvious liar, not "no attack"; ADR 0094 stands unchanged | v1 T1 | 2026-10-11 | Accepted |
| [0110](0110-the-ports-identity-on-real-hai-declared.md) | Whether the port reproduces ADR 0104's scored alert list on real HAI (float32 against float64 grouping), declared before it runs | v1 rebuild | 2026-10-12 | Accepted |
| [0111](0111-the-port-reproduces-the-scored-list-on-real-hai.md) | That check, once: on all six clean HAI files the port's scores and alert list equal ADR 0104's scored list, float32 or float64 grouping | v1 rebuild | 2026-10-12 | Accepted |
| [0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md) | One rule scales the consistency detector's windows by sample period (identity at 1 s); one BATADAL score against grouped MinMax 3/5, declared before it runs | v1 BATADAL | 2026-10-12 | Accepted |
| [0113](0113-consistency-on-batadal-five-of-five-and-a-saturated-budget.md) | BATADAL once: 5/5 against grouped MinMax 3/5, but 8 alerts per 8 hourly rows means chance also catches 5/5; lowest of five on eTaPR and point-adjusted F1 | v1 BATADAL | 2026-10-12 | Accepted |
| [0114](0114-the-liar-measurement-is-assembled-and-held.md) | T1 assembled (`phos.breaking.liar`, inlet calibrated on development seeds); 4/18 on a development seed, water never fires; the held-out run is held | v1 T1 | 2026-10-12 | Accepted |
| [0115](0115-a2-status-with-a-chance-column-declared.md) | A2's status for the consistency detector on the five judging corpora, with ADR 0106's chance null beside each, declared before it runs | v1 A2 | 2026-10-12 | Accepted |
| [0116](0116-a2-status-four-of-five-beyond-chance.md) | A2 status: strictly higher than grouped MinMax on 5 of 5, beyond every chance draw on 4 (not BATADAL); all seen; sandbox 37/38 and 42/50 reproduced | v1 A2 | 2026-10-12 | Accepted |
| [0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md) | Two loops: iterate freely on development data, claim only through a declared single score; the registry records each corpus's role and who has seen it; no Atlas corpus is held out, and the bank is refilled in a stated order | after v1 A2 | 2026-10-12 | Accepted |
| [0118](0118-decisions-and-outcomes-in-a-chained-ledger.md) | Learning engine S1: frozen decision and outcome records in an append-only, hash-chained ledger; unknown is a kind, an operator alone cannot confirm; the experiment log's first 185 lines are pinned | learning engine S1 | 2026-10-12 | Accepted |
| [0119](0119-why-a-liar-run-fails-by-a-declared-precedence.md) | Learning engine S2: a declared eight-clause precedence says why each liar run fails; on development seed 4242, 10 of 14 failures are the inlet staying below threshold; every run recorded in a ledger, eligibility joined | learning engine S2 | 2026-10-12 | Accepted |
| [0120](0120-the-arena-tasks-an-enforced-budget-and-a-fence.md) | Learning engine S3: research tasks (at most three hypotheses), a chained attempt log that enforces a run budget of at most 25 in code, a fence on candidate diffs; a candidate is a window set under ADR 0112's rule; liar slice on declared development seeds, red-team seeds kept back; champion 24/90 and HAI 20.07 37/38 | learning engine S3 | 2026-10-12 | Accepted |
| [0121](0121-the-first-learning-lifecycle-and-its-control-arm.md) | Learning engine S4 and S5: the first full lifecycle on the water liar; diagnosis-led search found 7 qualifying candidates in 12 runs against 2 in 18 for an untargeted control; both chosen candidates fail the red team (each loses two champion passes); nothing promoted, T1 held-out runs still held | learning engine S4–S5 | 2026-10-12 | Accepted |
| [0122](0122-a-phos-generated-icssim-corpus.md) | A PHOS-generated ICSSim corpus: process, true state and Modbus from the same runs, falsified readings with the truth known; development and held-out seeds declared before use | after v1 A2 | 2026-10-13 | Accepted |
| [0123](0123-the-plant-map-proposed.md) | The plant map: per-target lagged regression with per-link lag selection in level or increment form, a drop-one band per link, a reconstruction that cannot learn the lie back from its controller; extends the frozen detector as challenger `atlas-plant-map-v1`; development slices and ten falsifiers (one a 30-minute fit budget) declared; HAI roles from the official point list; nothing built or scored | after v1 A2 | 2026-10-13 | Accepted |
| [0124](0124-the-plant-map-is-built-and-fits-in-seconds.md) | ADR 0123 steps 1–2: HAI 20.07 roles from the official point list (52 of 59), the plant map built as written (setpoints get no model); §9.10 passes, 6.7 s on an M4 laptop, 32 signals and 85 links; the §5.2 naming rule fails the controlled tank, pinned as a strict xfail; nothing scored | ADR 0123 steps 1–2 | 2026-10-13 | Accepted |
| [0125](0125-a-drop-one-check-is-decisive-or-inconclusive.md) | A drop-one check is decisive or inconclusive (amends ADR 0123 §5.2). Alone it fails the tank (lying level named 3 of 19; level wrongly blamed 5 of 20), because §3’s cycle exclusion strips real links; amended by ADR 0126; nothing scored | ADR 0123 §5.2 | 2026-10-15 | Accepted, amended |
| [0126](0126-declared-loops-narrow-the-level-form-bar.md) | Control loops are declared in role files (HAI 20.07's six, from the manual); the level-form bar applies only to a loop's reading; three testimony rules (vacuous drop-ones inconclusive, drivers judged without the candidate, single-liar explanations). Fixture: lying level named 109 of 110, never wrongly blamed; HAI refit 31 signals, 73 links; nothing scored | ADR 0123 §3, §5.2; ADR 0125 §2 | 2026-10-15 | Accepted |
| [0127](0127-the-arena-scores-the-plant-map-challenger.md) | The arena scores a detector configuration: `atlas-plant-map-v1` with overrides on its caps, stopping rule and horizons only; task `plant-map`, six runs, selection rule fixed before attempt 1; synthetic plants read their CONTROL couplings as loops; the development measures script; nothing scored | ADR 0123 step 3 | 2026-10-15 | Accepted |
| [0128](0128-icssim-roles-loops-and-the-development-slice.md) | ICSSim's roles and six loops from its own source (tag table, PLC programs; a mode tag is a setpoint); a run reader that refuses the held-out corpus; the plant map's ICSSim development slice defined before it is scored | ADR 0123 step 3 | 2026-10-15 | Accepted |
| [0129](0129-the-plant-map-detects-but-is-not-yet-a-map.md) | Step 3's report: attempt 1 passes 55 of 90 liar runs (water 22, champion 0) with no champion pass lost and HAI 20.07 37 of 38; chance 15 against the champion's 9. By ADR 0123 §9 it fails 9.5, 9.6 (not a map), 9.7 and 9.9 (no naming or reconstruction). Red team held for Elijah | ADR 0123 step 3 | 2026-10-15 | Accepted |
| [0130](0130-the-graded-plant-model.md) | Proposed: the graded plant model. Every link carries its evidence: A declared, B intervened, C network-observed, D statistical and stable; naming and reconstruction on A–C only; "I don't know" is an output; five falsifiers set before anything is built | ADR 0123, ADR 0129 | 2026-10-15 | Proposed |
| [0131](0131-stricter-links-do-not-stabilise-the-map.md) | Attempts 2–4 (stricter stopping rule and caps): HAI links shared across halves stay at 37–38%, water passes fall to 0 (its one inflow link has share 0.022), wrong names rise past 10%. Attempt 1 stays chosen; two runs left unspent | ADR 0127, ADR 0129 | 2026-10-15 | Accepted |
| [0132](0132-grade-b-links-from-logged-changes.md) | Grade B declared before it is scored: mean-shift responses to logged writes within 120 s, beyond the 99th percentile of ordinary shifts, in at least 3 changes and two thirds of them, never first; ICSSim's true graph (20 edges) from its source, for judging only; chance precision reported beside the measured one | ADR 0130 | 2026-10-15 | Accepted |
| [0133](0133-grades-a-and-d-and-naming-on-trusted-links.md) | Grades A and D and naming on the trusted map (A to C drivers only), declared before scoring; the synthetic plants' couplings read as their drawing; ADR 0130 falsifiers 3, 4 and 5 unmoved | ADR 0130 | 2026-10-15 | Accepted |
| [0134](0134-red-team-and-the-trusted-map-first-results.md) | Red team: attempt 1 passes 116 of 180 against the champion's 53 (water 47 against 0) but loses 2 power runs, so fails §9.3; power corpora differ across machines. Trusted map: falsifier 3 fails on water, 4 fails (0 of 105 right, 21 wrong), 5 passes; causes diagnosed | ADR 0123 §9.3, ADR 0130 | 2026-10-15 | Accepted |
| [0135](0135-decisive-witnesses-and-upstream-first.md) | Two naming rules, selectable: a downstream witness testifies only if decisive; a candidate is named only if everything upstream outside its loop is in band. Attempt 5 declared; CONFIRM_SEEDS 95201–95210 declared for one confirmation of detection and naming | ADR 0123 §5.2–5.3, ADR 0127, ADR 0130 | 2026-10-15 | Accepted |
| [0136](0136-the-confirmation-water-works-the-bars-are-not-met.md) | Confirmation, once: 113 of 180 against 50 (water 49 against 0) but 2 champion passes lost; naming 50% right with the full map, 43% with the trusted map; water alone 47 of 54 named right, none wrong, band 99.9%. Pooled bars not met; nothing promoted | ADR 0135, ADR 0130 | 2026-10-15 | Accepted |
| [0137](0137-smooth-weights-and-a-third-confirmation.md) | The power losses are calibrator ties (isotonic steps give equal weights); a Platt option for the challenger's facts only; attempt 6, the arena's last run, and CONFIRM_SEEDS_2 95301–95310 declared before scoring | ADR 0123 §9.3, ADR 0127 | 2026-10-15 | Accepted |
| [0138](0138-three-confirmations-the-same-answer.md) | Third confirmation fails like the others: 103 of 174 against 43, 2 lost. Across three held-back sets 332 against 146 passes (water 137 against 0), 6 lost; water named right in 91 of 107, none wrong. Arena task closed; the zero-loss rule and scope are Elijah's questions | ADR 0137 | 2026-10-15 | Accepted |
| [0139](0139-a-forward-rule-for-losses-within-the-champions-own-churn.md) | Written after three failures and saying so: for future sets only, a challenger may lose at most the champion's own measured churn (3 of 52) and must gain more than that; earlier verdicts stand; CONFIRM_SEEDS_3 95401–95410 for attempt 6 unchanged, once | ADR 0123 §9.3, ADR 0134 | 2026-10-15 | Accepted |
| [0140](0140-the-plant-map-survives-the-fourth-set.md) | Fourth held-back set, once, under ADR 0139: 111 against the champion's 46 (water 49 against 0), none lost; survives. Across four sets 443 against 192. Candidate for ADR 0117's gate as a detector; role files for the validation corpora come first | ADR 0139, ADR 0117 | 2026-10-15 | Accepted |
| [0141](0141-role-files-for-the-later-hai-editions.md) | Role files for HAI 21.03, 22.04 and 23.05, generated from 20.07's file and 31 quoted manual points; no matching by name shape (23.05's `x…` columns unroled); BATADAL gets none, so the challenger is the champion there | ADR 0123 §3, ADR 0140 | 2026-10-15 | Accepted |
| [0142](0142-the-plant-map-gate-is-declared.md) | ADR 0117's gate for attempt 6, declared and not run: `scripts/gate.py` pinned by sha256 with the detector, candidate and role files; committed tree only; reproduces the champion's published rows before fitting the challenger; one look, result to Elijah | ADR 0117 §3, ADR 0141 | 2026-10-15 | Accepted |
| [0143](0143-the-plant-map-fails-the-gate.md) | ADR 0117's gate, run once: challenger 40/50, 53/58, 35/52, 5/5 against the champion's 42, 53, 36, 5; fewer on two HAI editions, more on none; fails. Champion unchanged; no claim of real-plant improvement | ADR 0142 | 2026-10-16 | Accepted |
| [0144](0144-the-october-build-is-declared.md) | October build declared before any new file is opened: seeds 97001–97020 and 97101–97120; Kelmarsh year split; Penmanshiel WT01–10 / WT11–15; 4SICS days; GRFICS runs outside the repo; scorecard names only. No score | ADR 0117, ADR 0122 | 2026-10-17 | Accepted |
| [0145](0145-bet-001-not-run.md) | Bet 001 is not run: the CERT payload and the trace cache are absent | ADR 0144 | 2026-10-19 | Accepted |
| [0146](0146-identity-features-keep-the-thirty-four-symmetric.md) | Identity features name declared hosts, destinations and machines | ADR 0144 | 2026-10-19 | Accepted |
| [0147](0147-cert-r42-held-out-and-not-fetched.md) | CERT r4.2 is declared held out, and it is not fetched | ADR 0144 | 2026-10-19 | Accepted |
| [0148](0148-bet-001-is-scored-once.md) | Bet 001 is scored once, with the ranking fixed first | ADR 0144 | 2026-10-19 | Accepted |
| [0149](0149-lane-a-dev-loop-does-not-touch-6b.md) | Lane A's development loop does not touch 6B | ADR 0144 | 2026-10-19 | Accepted |
| [0150](0150-maintenance-alerts-close-only-with-a-citation.md) | A maintenance alert closes only when a work order is cited | ADR 0144 | 2026-10-19 | Accepted |
| [0151](0151-the-maintenance-closure-harness-is-declared.md) | The maintenance-closure harness is declared before it is scored | ADR 0144 | 2026-10-19 | Accepted |
| [0152](0152-kelmarsh-log-rule.md) | The Kelmarsh log rule is declared before it is scored | ADR 0144 | 2026-10-19 | Accepted |
| [0153](0153-maintenance-closure-on-the-development-seeds.md) | Maintenance closure on seeds 97001–97020 | ADR 0144 | 2026-10-19 | Accepted |
| [0154](0154-the-kelmarsh-score-did-not-run.md) | The Kelmarsh score did not run | ADR 0144 | 2026-10-19 | Accepted |
| [0155](0155-incident-types-are-template-ids.md) | An incident type in a notification report is the template id already stored, not a new taxonomy | ADR 0144 | 2026-10-17 | Accepted |
| [0156](0156-the-report-checker-fails-closed.md) | The report checker fails closed: a sentence without an evidence id rejects the report; confidence is left off the page | ADR 0155 | 2026-10-17 | Accepted |
| [0157](0157-notification-stages-quote-the-store.md) | NIS2 (24 h, 72 h) and UK (initial, full) notification stages quote the store and add nothing it does not hold | ADR 0156 | 2026-10-17 | Accepted |
| [0160](0160-a-command-the-actuator-ignored.md) | A command the actuator ignored is consistency evidence: fault against maintenance separated on 20 of 20 development and 20 of 20 held-back synthetic seeds, no false command alert on follow runs | ADR 0144 | 2026-10-17 | Accepted |
| [0161](0161-the-plant-map-names-the-champions-alerts.md) | The plant map as an explainer on the champion's alerts: three sensors (chosen on development) named 59/60 and 60/60 held back; across all nine surveyed, 96 of 156 right (62%), 1 wrong. Corrected at merge: W2 not met | ADR 0135, ADR 0143 | 2026-10-17 | Accepted |
| [0162](0162-explanation-confidence-is-not-a-probability.md) | Explanation confidence is not shown as a probability: right and wrong leads share one raw figure; nothing reaches 80%; W5 not met | ADR 0144 | 2026-10-17 | Accepted |
| [0163](0163-the-tu-wien-pilot-factory-is-registered.md) | TU Wien pilot factory registered (CC BY 4.0, 147 GB): development tf_a.zip, held back tf_s.zip; benign behaviour only, never a catch count | ADR 0144 | 2026-10-17 | Accepted |
| [0164](0164-the-held-back-maintenance-check-is-declared.md) | The held-back maintenance check is declared before it runs | ADR 0144 | 2026-10-19 | Accepted |
| [0165](0165-kelmarsh-round-2-trains-on-2018.md) | This Kelmarsh run trains on 2018 and scores 2019–2022 | ADR 0144 | 2026-10-19 | Accepted |
| [0166](0166-kelmarsh-modes-are-declared-states.md) | Kelmarsh operating modes are declared states | ADR 0144 | 2026-10-19 | Accepted |
| [0170](0170-every-control-coupling-is-a-loop-and-bars-only-its-outputs.md) | The lane E explainer reads every control coupling as a loop, and a loop bars only its outputs | ADR 0144 | 2026-10-19 | Accepted |
| [0171](0171-explanation-confidence-is-calibrated-by-evidence-shape.md) | Explanation confidence is calibrated by the shape of its evidence | ADR 0144 | 2026-10-19 | Accepted |
| [0172](0172-root-cause-ranking-points-an-alert-upstream.md) | Root-cause ranking points an alert at the signal its deviation started from | ADR 0144 | 2026-10-19 | Accepted |
| [0173](0173-four-atlas-capabilities-were-not-scored.md) | Four Atlas capabilities were not scored this round | ADR 0144 | 2026-10-19 | Accepted |
| [0174](0174-kelmarsh-held-back-score-is-declared.md) | Kelmarsh held-back score is declared before it runs: unchanged consistency scorer, ADR 0165 status-log rule, 2023–2024 only after sha256 | ADR 0144, ADR 0165 | 2026-10-19 | Accepted |
| [0175](0175-w5-seeds-and-scenarios-are-declared.md) | W5 seeds 97401–97420 and 97501–97520, and five scenario kinds, declared before any plant is built | ADR 0144, ADR 0171 | 2026-10-19 | Accepted |
| [0176](0176-w5-held-back-confidence-is-declared.md) | W5 held-back confidence score is declared after development: 28 of 46 right, 18 wrong, no high band, bar not met | ADR 0171, ADR 0175 | 2026-10-19 | Accepted |
| [0177](0177-4sics-development-days-are-declared.md) | 4SICS development days: learn the command graph on 151020, compare 151021, no catches, 151022 stays closed | ADR 0144, ADR 0040 | 2026-10-19 | Accepted |
| [0178](0178-kelmarsh-held-back-years-were-scored-once.md) | Kelmarsh 2023–2024 scored once: 29 alerts, 23 explained by the turbine log; meters not scored | ADR 0174 | 2026-10-19 | Accepted |
| [0190](0190-depth-counting-one-loud-signal.md) | Depth counting: one loud signal can match many quiet ones | ADR 0144 | 2026-10-19 | Accepted |
| [0191](0191-behaviour-chains-are-declared-shapes.md) | Behaviour chains are declared shapes, not host names | ADR 0144 | 2026-10-19 | Accepted |
| [0192](0192-peer-groups-by-role-and-time.md) | Peer groups are role and time of day, not a new 6B peer feature | ADR 0144 | 2026-10-19 | Accepted |
| [0193](0193-rare-links-among-declared-peers.md) | Rare user–machine–site links are scored, not drawn on the org graph | ADR 0144 | 2026-10-19 | Accepted |
| [0194](0194-kept-scorer-is-still-6b-r42-unscored.md) | The kept scorer is still 6B; r4.2 stays unscored | ADR 0144 | 2026-10-19 | Accepted |
| [0200](0200-the-public-repository-takes-the-house-style.md) | The public front page takes the house style of `brand/phos_pdf.py` before week 13, by Elijah's decision: monochrome, white logo once on a black cover, black callouts, grey stat panels; a results card; Bet 001's loss recorded | ADR 0044, ADR 0170 | 2026-10-19 | Accepted |
| [0201](0201-the-front-page-leads-with-real-data-and-a-contact.md) | The front page leads with real data (131 of 160 HAI attacks at 8 alerts a shift, against 52 for the best baseline checked); the record page opens with current numbers and "start here"; one public contact address, with the guard still refusing every other Proton address | ADR 0116, ADR 0200 | 2026-10-19 | Accepted |
| [0195](0195-a-return-to-a-host-nobody-else-has-used.md) | A return to a host nobody else has used is the one Sentiel challenger | Sentiel investigation | 2026-10-19 | Accepted |
| [0196](0196-exclusive-host-return-is-the-r42-one-shot.md) | exclusive-host-return is the r4.2 one-shot, and it is not run | Sentiel investigation | 2026-10-19 | Accepted |
| [0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md) | S3 is scored at 48 tickets a day, positive scores only, beside frozen 6B and a label-free chance null; declared before the r4.2 holdout lift | ADR 0196 | 2026-10-19 | Accepted |
| [0203](0203-r42-email-columns-are-read-when-present.md) | r4.2's extra email columns (user, pc, cc, bcc) are read when present; nothing else changes | ADR 0202 | 2026-10-19 | Accepted |
| [0204](0204-the-identity-register-stays-empty.md) | The identity register stays empty for the S2 score, so the six features score zero | ADR 0146 | 2026-10-19 | Accepted |
| [0210](0210-the-g1-table-reprints-its-validation-rows.md) | The G1 table's one command checks development rows and reprints validation rows | ADR 0095 | 2026-10-19 | Accepted |
| [0211](0211-a6-is-one-configuration.md) | A6 holds: the per-corpus differences are the declared sample-period rule | ADR 0112 | 2026-10-19 | Accepted |
| [0212](0212-a3-queue-rank-is-declared.md) | A3's queue rank is declared before the one look; the look finds 57 of 203 | ADR 0112 | 2026-10-19 | Accepted |
| [0220](0220-tag-suggestions-are-not-declarations.md) | The onboarding tool's tag suggestions are not declarations | ADR 0123 | 2026-10-19 | Accepted |
| [0221](0221-the-v1-command-checks-the-record.md) | The v1 command checks the committed record without rescoring | ADR 0116 | 2026-10-19 | Accepted |
| [0230](0230-v1-stands-at-six-of-twelve.md) | v1 stands at 6 of 12 after the sprint; S2 is not met, by Elijah's decision, because an empty register names nothing | ADR 0204, ADR 0212 | 2026-10-19 | Accepted |
| [0231](0231-queue-rankers-and-mixed-shifts-are-declared.md) | Six queue reorderings and mixed-shift seeds 97651–97670 and 97601–97620 are declared before any ranker runs | ADR 0212 | 2026-10-19 | Accepted |
| [0232](0232-familiarity-is-frozen-before-the-held-back-queue.md) | Familiarity is the only reorder that did not lower recall; it is frozen before seeds 97601–97620 | ADR 0231 | 2026-10-19 | Accepted |
| [0233](0233-familiarity-held-back-queue-did-not-beat-the-champion.md) | Familiarity on seeds 97601–97620 is 20 of 20, the same as the champion; the bar is not met | ADR 0232 | 2026-10-19 | Accepted |
| [0234](0234-the-familiarity-queue-gate-is-not-run.md) | The five-corpus gate for familiarity is named and not run; v1 A3 stays 57 of 203 | ADR 0212, ADR 0233 | 2026-10-19 | Accepted |
| [0240](0240-lane-r-held-back-confidence-is-declared.md) | Lane R held-back seeds 97701-97720 are declared before the one score | ADR 0175, ADR 0176 | 2026-10-19 | Accepted |
| [0250](0250-a-command-effect-is-not-a-known-link-change.md) | A command effect is a new facet; known-link function changes still support both explanations; lane T seeds 97801–97820 and 97901–97920 | ADR 0034, ADR 0073 | 2026-10-19 | Accepted |
| [0251](0251-h1-attaches-and-does-not-lead.md) | H1 attaches on 20 of 20 hostile development writes and uniquely leads on 0 of 20; authorised false alarms 0.00 | ADR 0250 | 2026-10-19 | Accepted |
| [0252](0252-h2-is-rejected-for-false-alarms.md) | H2 is rejected: setpoint jumps false-alarm on 20 of 20 authorised development runs | ADR 0250, ADR 0086 | 2026-10-19 | Accepted |
| [0253](0253-h3-is-kept-and-does-not-lead.md) | H3 is kept; H1+H3 uniquely leads on 0 of 20 development seeds and false-alarms at 0.00 | ADR 0251, ADR 0252 | 2026-10-19 | Accepted |
| [0254](0254-trusted-station-held-back-is-declared.md) | Held-back seeds 97901-97920 are declared for one score of H1+H3; the score is not run in this record | ADR 0253 | 2026-10-19 | Accepted |
| [0255](0255-trusted-station-held-back-lead-bar-is-not-met.md) | Held-back unique leads 0 of 20, not met; false alarms 0.00, met; known-link tests green, met | ADR 0254 | 2026-10-19 | Accepted |
| [0260](0260-build-d-is-merged-and-its-bars-stand.md) | Build D is merged; no ranker beat the champion, W5's high flag cannot reach 0.8 by construction, and the trusted-station facts do not lead | ADR 0234, ADR 0240, ADR 0255 | 2026-10-19 | Accepted |
| [0261](0261-the-s2-register-is-the-directorys-email.md) | The S2 register is each release's LDAP email addresses, declared before the score | ADR 0146, ADR 0230 | 2026-10-20 | Accepted |
| [0262](0262-s2-is-met-on-directory-email.md) | S2 is met on directory email; host and machine features stay zero; v1 stands at 7 of 12 | ADR 0261 | 2026-10-20 | Accepted |
| [0263](0263-the-g1-table-is-regenerated-once.md) | The G1 table is regenerated once from the files; the run is not this record | ADR 0210, ADR 0221 | 2026-10-20 | Accepted |
| [0264](0264-the-g1-regeneration-matched.md) | The G1 regeneration matched; A1 is met; the grouped block was not recomputed | ADR 0263 | 2026-10-20 | Accepted |
| [0265](0265-the-always-apply-rules-load-themselves.md) | The always-apply rules load themselves: the bodies stay in `.cursor/rules/`, `docs/rules/*.md` symlinks to them, a committed root `CLAUDE.md` imports them, and the skills restate no figure | ADR 0044, ADR 0049 | 2026-10-20 | Accepted, amended |
| [0266](0266-the-programme-counter-is-written-from-evidence-not-by-hand.md) | The programme counter is written from the repository's evidence by `scripts/roadmap_state.py`; the roadmap freeze narrows to the contract and stops pinning `current_session` | ADR 0049, ADR 0061, ADR 0265 | 2026-10-20 | Accepted |
| [0267](0267-role-files-reach-the-public-tree.md) | Role files reach the public tree; absent experiment pins skip; the log prefix carries the lab digest and the exported digest | ADR 0118, ADR 0123 | 2026-10-20 | Accepted |
| [0268](0268-the-a7-regeneration-is-declared.md) | The A7 regeneration is declared: four producers recompute and compare, a mismatch is the result, the benchmark's three frozen constants are not regenerated, and A7 is therefore not met as frozen | ADR 0221, ADR 0263, ADR 0264 | 2026-10-20 | Accepted |
| [0269](0269-the-a7-regeneration-matched.md) | The A7 regeneration matched all four rebuilt records, the grouped block included, so A1's copied-block caveat closes; A7 stays not met on the frozen benchmark constants and the outside run | ADR 0264, ADR 0268 | 2026-10-20 | Accepted |
| [0270](0270-declared-new-destination-is-frozen.md) | Declared-new-destination is the second S3 challenger, frozen before any r4.2 look | ADR 0261, ADR 0202 | 2026-10-20 | Accepted |
| [0271](0271-declared-new-destination-r42-is-declared.md) | The declared-new-destination shot on r4.2 is declared and not run | ADR 0270 | 2026-10-20 | Accepted |
| [0272](0272-declared-new-destination-lost-the-r42-shot.md) | Declared-new-destination surfaced 21 distinct insiders against frozen 6B's 59, below its own chance null of 35.29 and a subset of 6B's set; S3 stays not met | ADR 0202, ADR 0270, ADR 0271 | 2026-10-20 | Accepted |
| [0273](0273-the-stronger-engine-programme-is-declared.md) | The stronger-engine programme is declared: four lanes, the corpus first, ADR numbers 0273-0284 reserved so progress is read from the record, and v1 untouched | ADR 0106, ADR 0108, ADR 0122, ADR 0269 | 2026-10-20 | Accepted |
| [0274](0274-the-icssim-corpus-exists-and-its-held-out-half-is-sealed.md) | The ICSSim corpus exists in two halves, 13 development and 20 held-out runs from one pinned generator, with both the readings and the control traffic for the same plant; written late, and carrying the macOS loopback failure that cost a whole generation run | ADR 0047, ADR 0112, ADR 0122, ADR 0143, ADR 0273 | 2026-10-21 | Accepted |
| [0275](0275-lane-1-is-frozen-and-its-held-out-score-declared.md) | Lane 1 is frozen at two attribution components and its one held-out score declared; the response component was removed because mimic_maintenance and genuine maintenance are physically indistinguishable, making it a provenance attack for A5's CMMS inlet | ADR 0034, ADR 0069, ADR 0122, ADR 0273 | 2026-10-21 | Accepted |
| [0276](0276-lane-1-met-its-bar-on-held-out-runs.md) | Lane 1 met its bar on the twenty held-out runs: 87 of 120 attacks against the frozen engine's 49, recon 0 to 20 of 20, benign alerts unchanged; the gain is attribution on a simulated plant, not the physics claim | ADR 0273, ADR 0275 | 2026-10-21 | Accepted |
| [0285](0285-the-corpus-gains-a-coordinated-low-amplitude-class.md) | The ICSSim corpus gains `creep_many`, several instruments biased 3-8% of their own range at once, on new seeds in new directories; the existing corpus is frozen as the record lane 1's score rests on | ADR 0122, ADR 0273, ADR 0276 | 2026-10-21 | Accepted |

| [0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md) | On a saturated budget an appended score column cannot win an alert slot without also becoming its group's `best` and re-placing that group's alert; found by lane 3, which caught 53 of 70 against 32 and still failed its delay bar at every setting | ADR 0122, ADR 0143, ADR 0273, ADR 0274, ADR 0285 | 2026-10-21 | Accepted |

| [0287](0287-the-live-brief-is-discoverable-from-the-rules.md) | A seventh always-apply rule points at the live brief, because every other rule and the tracker still name P1 and none mentions build brief E, so a session in any tool concluded the project was parked; it lifts nothing | ADR 0044, ADR 0265, ADR 0273, ADR 0286 | 2026-10-21 | Accepted |

| [0288](0288-the-linear-predictors-misfit-is-load-bearing.md) | Lane 4 swapped the ridge for a hinge basis: false alarms fell 28 to 20-24 a day out of sample and benign alerts 5 of 20 to 1 of 20, and catches fell 32 to 23-25 at every setting, because a faithful predictor also explains the attack; lane 4 not declared | ADR 0106, ADR 0143, ADR 0273, ADR 0274, ADR 0286 | 2026-10-21 | Accepted |

| [0289](0289-the-build-record-reaches-the-public-tree.md) | The build record reaches the public tree, so the cited scorecard resolves; the failing pin is not made to skip. Written as 0268 and renumbered on merge (ADR 0291) | ADR 0044, ADR 0144, ADR 0267 | 2026-10-20 | Accepted |

| [0290](0290-bet-003-the-first-shift.md) | Bet 003 `atlas-first-shift`, bars frozen: A3's top-10% fraction is retired as an instrument because the shift queue is shorter than the budget; coverage, position, story and load replace it. Written as 0269 and renumbered on merge (ADR 0291) | ADR 0068, ADR 0164, ADR 0212, ADR 0230, ADR 0234 | 2026-10-20 | Accepted |

| [0291](0291-the-colliding-adr-and-note-numbers-are-resolved.md) | Two branches each took ADRs 0268/0269 and notes 78/79 for different decisions; the pair committed first keeps them on three grounds, the other becomes 0289/0290 and notes 85/86, and the cause is recorded as unfixed | ADR 0044, ADR 0268, ADR 0269, ADR 0287, ADR 0289, ADR 0290 | 2026-10-21 | Accepted |
| [0292](0292-a-number-another-branch-already-used-is-refused.md) | A change that adds an ADR or note number another branch already gave to a different file is refused. The settled collision is not reopened | ADR 0273, ADR 0291 | 2026-10-21 | Accepted |
| [0293](0293-step-0284-would-reproduce-the-frozen-alerts-on-a-process-table.md) | As lane 1 is built, a process table with no command messages reproduces the frozen alerts. Shown on a hand-built matrix and the registry. The seen corpora were not opened. 0284 stays unspent | ADR 0040, ADR 0058, ADR 0276, ADR 0286 | 2026-10-21 | Accepted |
| [0294](0294-three-rescues-are-refused-and-lane-2-stays-a-question.md) | The combined candidate is not assembled, the seen-corpora look is not taken, the delay-aware placement rule is not built, and lane 4's two scores are not both kept. Lane 2's plant-ratio attacker stays a future declaration | ADR 0273, ADR 0276, ADR 0285, ADR 0286, ADR 0288, ADR 0293 | 2026-10-21 | Accepted |
| [0295](0295-legal-flow-biases-the-level-and-keeps-the-plants-own-flow.md) | `legal_flow` scales tank level by the fixed 3–8% band and sets outflow to the value ICSSim's physics would emit. Declared before any detector run. Held-out3 unopened | ADR 0122, ADR 0285, ADR 0294 | 2026-10-21 | Accepted |
| [0296](0296-legal-flow-does-not-give-breadth-the-catches.md) | On dev3, breadth caught 15 of 32 attacks and the frozen engine 16 of 32. The first bar fails. `legal_flow` was 2 of 4 for each. The band was not changed | ADR 0295 | 2026-10-21 | Accepted |
| [0297](0297-build-brief-e-is-closed-without-a-stronger-engine.md) | Build brief E is closed. The stronger engine was not reached. 0277–0284 stay unwritten and are not a queue. This record is not a new roadmap | ADR 0273, ADR 0276, ADR 0286, ADR 0288, ADR 0293, ADR 0294, ADR 0296 | 2026-10-21 | Accepted |
| [0298](0298-five-questions-succeed-the-closed-stronger-engine-programme.md) | Five questions and one evaluation. None is assumed to work. First step is an evaluation set for in-range commands, then a score of the frozen detector. Flagship bar is more catches inside 8 alerts a shift and false alerts no higher | ADR 0297 | 2026-10-21 | Accepted |
| [0299](0299-the-public-release-note-restates-the-record.md) | The public release note restates the record. The cards and the PolyForm Noncommercial licence stay. Three unsent drafts are corrected to the recorded bands. No measurement | ADR 0044, ADR 0116, ADR 0200, ADR 0201, ADR 0276, ADR 0286, ADR 0288, ADR 0297 | 2026-10-22 | Accepted |
| [0300](0300-a-kept-day-halves-the-remaining-misses.md) | A kept day halves the remaining misses of one declared class, inside 8 alerts a shift, with false alerts no higher. Five kept days would be a 32-fold cut. Not a result | ADR 0297, ADR 0298 | 2026-10-22 | Accepted |
| [0301](0301-the-in-range-command-is-declared-before-either-champion-is-scored.md) | `in_range_command` writes the ordinary setpoint band and holds the input valve off. Champions are named and not scored. The walk corpus waits on a zero-miss gate | ADR 0300, ADR 0122, ADR 0128, ADR 0276, ADR 0073 | 2026-10-22 | Accepted |
| [0302](0302-a-program-transfer-is-not-a-register-write.md) | Download, upload, and online edit are three acts. An unbooked one says go and look. A register write is not an act. A missing booking is not an attack verdict | ADR 0014, ADR 0036, ADR 0069, ADR 0071 | 2026-10-22 | Accepted |
| [0303](0303-the-shift-page-holds-eight.md) | A shift page holds 8. An unbooked transfer stays. A booked one is omitted. Other alerts leave from the lowest score. budget_alerts is not edited | ADR 0302 | 2026-10-22 | Accepted |
| [0304](0304-packing-puts-more-incidents-inside-eight.md) | Same-id alerts pack into one chain on the frozen 300s/600s windows. A five-incident fixture goes from 2 misses to 0 inside 8 slots. Two ids never merge | ADR 0300, ADR 0303 | 2026-10-22 | Accepted |
| [0305](0305-two-setpoints-inside-the-band-are-one-move.md) | One in-band setpoint raises nothing. Two tags within the frozen 300s window are one move. Twelve pairs on a page of 8 miss 4, at most half of the single-tag misses | ADR 0300, ADR 0304 | 2026-10-22 | Accepted |
| [0306](0306-the-next-observation-names-the-booking.md) | An unbooked transfer names the booking that would withdraw the alert. Supplying it clears the alert and does not pick a lead | ADR 0302 | 2026-10-22 | Accepted |
| [0307](0307-a-720-step-walk-is-invisible-to-the-joint-check.md) | One tag walked 720 in-band steps alerts at the first step. The joint check is silent. 719 steps are not a walk. Twelve walks on a page of 8 miss 4 | ADR 0300, ADR 0305 | 2026-10-22 | Accepted |
| [0308](0308-the-stack-catches-both-classes-inside-eight.md) | Four joint moves and four walks. Each checker misses 4. The stack misses 0 inside 8. A lone in-band write adds nothing | ADR 0305, ADR 0307 | 2026-10-22 | Accepted |
| [0309](0309-the-champions-missed-none-of-the-in-range-commands.md) | On dev4, both champions caught 13 of 13 in-range commands. `M_champion` is 0, so no new detector. The walk corpus stays ungenerated until this report is committed | ADR 0301, ADR 0073 | 2026-10-22 | Accepted |
| [0310](0310-the-same-value-after-the-window-is-one-handoff.md) | The same in-band value on a second tag after the frozen 300s window. The stack misses all 12. A page of 8 misses 4. A pair inside the window stays with the joint check | ADR 0300, ADR 0305, ADR 0308 | 2026-10-22 | Accepted |
| [0311](0311-handoffs-share-the-page-and-the-misses-fall-by-half.md) | Two joints, two walks, eight handoffs. The stack misses all 8 handoffs. The shared page misses 4 inside 8. A lone in-band write adds nothing | ADR 0308, ADR 0310 | 2026-10-22 | Accepted |
| [0312](0312-the-unbooked-transfer-keeps-its-place-on-the-process-page.md) | Four unbooked transfers stay on a page of eight handoffs, so those misses go from 4 to 0. A booking that names both tags clears the handoff and does not pick a lead | ADR 0303, ADR 0310, ADR 0311 | 2026-10-22 | Accepted |
| [0313](0313-the-champions-missed-one-of-the-slow-walks.md) | On dev4-walk, both champions caught 8 of 9 slow walks. `M_champion` is 1, so the walk detector may be built. It is not built here. Do not rerun the score | ADR 0301, ADR 0309, ADR 0073 | 2026-10-23 | Accepted |
| [0314](0314-the-walk-column-is-declared-before-it-is-scored.md) | The walk column is declared before it is scored. Hashes and five bars are fixed. No number from the column exists in this record | ADR 0301, ADR 0313, ADR 0073 | 2026-10-23 | Accepted |
| [0315](0315-the-walk-column-does-not-halve-the-remaining-miss.md) | The walk column missed the same 1 of 9. The first bar is not met. The column is not kept. Do not rerun or retune it | ADR 0314, ADR 0073 | 2026-10-23 | Accepted |
| [0316](0316-the-joint-command-is-declared-before-either-champion-is-scored.md) | `joint_command` writes the tank setpoint inside 6.5–7.5 and the bottle setpoint inside 1.3–2.0. Champions are named and not scored. The column is specified and not built. Held-out5 unopened | ADR 0300, ADR 0301, ADR 0315, ADR 0122, ADR 0128, ADR 0073 | 2026-10-23 | Accepted |
| [0317](0317-a-slot-exists-only-when-a-declared-law-is-false.md) | A slot exists only when a declared law is false. Time orders the page. The ceiling stays 8 and is not searched. Residual magnitude does not create or sort a slot. No corpus was scored. v1 stays 8 of 12 | ADR 0068, ADR 0300 | 2026-10-23 | Accepted |
| [0318](0318-a-slot-requires-a-declared-law.md) | A plant names the laws in force. An undeclared law is silence. A slot for an undeclared name is refused. An empty register stays empty. No corpus was scored. v1 stays 8 of 12 | ADR 0317 | 2026-10-23 | Accepted |
| [0319](0319-only-a-broken-law-takes-a-slot.md) | A declared law is held, broken, or unstated. Only broken takes a slot. A missing inlet is unstated. No corpus was scored. v1 stays 8 of 12 | ADR 0318 | 2026-10-23 | Accepted |
| [0320](0320-an-unnamed-station-is-silence-until-the-set-is-named.md) | A station outside the declared set is one break. An empty set is unstated. A station the plant named does not break this law. No corpus was scored. v1 stays 8 of 12 | ADR 0319 | 2026-10-23 | Accepted |
| [0321](0321-the-controller-comparison-is-true-or-false.md) | The controller comparison is true or false. Agreement is silence. Disagreement is one break per side. Manual mode is unstated. There is no divisor. No corpus was scored. v1 stays 8 of 12 | ADR 0320 | 2026-10-23 | Accepted |
| [0322](0322-a-slot-enters-only-as-a-law-break.md) | A slot enters only as a law break. The exact type is required. A subclass with a magnitude is refused. No corpus was scored. v1 stays 8 of 12 | ADR 0321 | 2026-10-23 | Accepted |
| [0323](0323-every-sentence-names-the-law-it-came-from.md) | Every sentence names the law it came from. A score-word is refused. An uncited break is not placed. No corpus was scored. v1 stays 8 of 12 | ADR 0322 | 2026-10-23 | Accepted |
| [0324](0324-the-operating-plan-loads-in-both-tools.md) | The operating plan loads in both tools. The plan is the sequence. The rule lifts nothing. No corpus was scored. v1 stays 8 of 12 | ADR 0265, ADR 0287, ADR 0323 | 2026-10-23 | Accepted |
| [0325](0325-the-law-page-inlet-is-a-named-map.md) | The law-page inlet is a named map. A function code is not a station and not a program act. The corpus stays unopened. v1 stays 8 of 12 | ADR 0323, ADR 0324 | 2026-10-23 | Accepted |
| [0326](0326-a-score-word-is-not-placed-and-an-unchecked-law-stays-listed.md) | A score-word is not placed, and an unchecked law stays listed. The call places nothing. No new law and no new threshold. No corpus was scored. v1 stays 8 of 12 | ADR 0319, ADR 0323 | 2026-10-24 | Accepted |
| [0327](0327-the-front-door-shows-the-path-and-labels-the-older-engine.md) | The front door shows the path and labels the older engine. A price for the company has no date. No corpus was scored. v1 stays 8 of 12 | ADR 0324, ADR 0044 | 2026-10-24 | Accepted |
| [0329](0329-the-score-word-refusal-covers-the-fact-not-the-law-name.md) | The score-word refusal covers the fact, not the law's name. A register name that carries one of the words no longer withholds the page. No corpus was scored. v1 stays 8 of 12 | ADR 0323, ADR 0326 | 2026-10-26 | Accepted |
| [0333](0333-the-law-page-invariant-bar-is-declared-before-it-is-run.md) | The law-page invariant bar is declared before it is run. Eight structural counts on phos-icssim-dev, each 0. The harness does not exist yet. No corpus was scored. v1 stays 8 of 12 | ADR 0325, ADR 0326, ADR 0122, ADR 0073 | 2026-10-26 | Accepted |
| 0334 | **Not published.** A commercial decision record, held in the private lab and not exported (`public/manifest.toml`). Its decisions stand there, unchanged; only its publication is withdrawn. [ADR 0342](0342-commercial-records-are-not-published.md) records why, and states the policy: this repository publishes its measurement record and withholds commercial and personal financial material. |
| [0335](0335-the-invariant-bar-is-redeclared-over-the-fixed-score-word-refusal.md) | The invariant bar is redeclared over the fixed score-word refusal. ADR 0333's eight bars are carried byte for byte; only the digests and the tree move. No corpus was scored. v1 stays 8 of 12 | ADR 0333, ADR 0329, ADR 0325, ADR 0326 | 2026-10-27 | Accepted |
| [0336](0336-the-law-page-invariants-hold-and-the-corpus-was-silent.md) | The law-page invariants hold, and the corpus was silent. All eight bars met at 0 on phos-icssim-dev; the plant broke no declared law, so all 104 placed sentences were the probe's and bars 1 and 2 got no corpus exercise. Kept. Not a detection claim. v1 stays 8 of 12 | ADR 0335, ADR 0333, ADR 0329, ADR 0325, ADR 0073 | 2026-10-27 | Accepted |
| [0340](0340-the-dataset-library-directory-loses-its-space.md) | The dataset library directory loses its space. `dataset library` becomes `dataset-library`, superseding ADR 0029 Decision 1's path and nothing else. `LIBRARY_DIRNAME` already held the name, so only a docstring was wrong. ADRs 0029, 0073 and 0084 keep the old path; an accepted record is immutable. No measurement moved. |
| [0341](0341-the-onboarding-brief-runs-on-a-historian-alone.md) | The onboarding brief runs on a historian alone, and `phos` carries it. `--capture` becomes optional, `phos onboard` is added beside the `python -m` form, and the public README carries the invitation: it runs on your own machine, nothing leaves your site. Supersedes ADR 0220's command surface only; no role rule or evidence text moved. C2 is still not met and v1 stays 8 of 12. |
| [0342](0342-commercial-records-are-not-published.md) | Commercial records are not published, and the export enforces it. `docs/adr/*` is a wholesale include, so a record reasoning about funding or ownership published by default. ADR 0334's path is forbidden and `[forbidden].content` gains the vocabulary of a funding discussion; one hit stops the export. Supersedes ADR 0334's publication only — its decisions stand in the lab. Withdrawing a publication is not withdrawing a decision, and removing a file does not remove it from a published history. |
| [0344](0344-industrial-protocol-coverage-is-declared.md) | Industrial protocol coverage is declared, and ADR 0345–0367 are reserved. For build brief G only, protocols may be named ahead of a partner's capture. Each still needs its own declaration. Modbus/TCP remains the only dissector. No corpus was scored. v1 stays 8 of 12. |
| [0345](0345-the-packet-foundation-is-declared.md) | The packet foundation is declared before it is built. Caps: 131072 bytes a flow, 256 flows, 16 out-of-order segments, 256 pairs, 60 seconds. Modbus is not edited. No code in this record. v1 stays 8 of 12. |
| 0346–0367 | **Reserved** by ADR 0344. Not decisions and not verdicts. The filenames stay when a lane fills them. |
| [0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md) | Triangulation and a self-search are named as the next Atlas programme, after brief G. Code laws, physics laws and the signed register; a detectability prediction tested once; then a search for departures that break none. Each rung has its own declaration. Brief H is written only after ADR 0363. Recipes stay in the lab. Nothing was built or scored. v1 stays 8 of 12. |
| [0381](0381-the-front-door-is-corrected-and-the-freeze-opens-for-figures.md) | The front door is corrected, and the freeze opens for explanatory figures. The untrue first sentence is corrected under the freeze's own exception; diagrams, mathematics and charts cross it by decision, ADR 0200 as precedent, no identity work admitted. Every plotted value is read from a committed record, and a chart the record does not hold is refused. The plain-English notes publish; note 132 is held back as ADR 0334's companion, and the index's gaps are explained. No corpus was scored. v1 stays 8 of 12. |

## Related reading

- [../atlas-report.md](../atlas-report.md) is the status report for the Atlas engine: what was
  built, what was measured, and what is honest about those numbers.
- PROGRESS.md (lab record, not published) is the chronological build log, one section per PART.
- encyclopedia/ (lab record, not published) is the complete repository reference, including a one-paragraph catalogue of these records.
