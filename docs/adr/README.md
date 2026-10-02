# Architecture decision records

Every significant decision in PHOS is recorded here: what the situation was, what was chosen, what
the alternatives were, and what the choice costs. Several of these records exist to document a
measured **negative** result, or a limit a component cannot pass. Those are kept deliberately.

Records are immutable once accepted. A decision that changes gets a new record that supersedes the
old one, so the reasoning at the time stays readable.

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
| [0084](0084-non-saturating-aggregation-for-sentiel.md) | Opens the non-saturating aggregation session ADR 0076 deferred at Gate 2; success is window recall 1.0 at the frozen 48 (CCH0959 surfaced, CSF0929 kept), candidates pre-registered by commit; not implemented | usefulness follow-on | 2026-09-27 | Accepted |
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
| [0084](0084-non-saturating-aggregation-for-sentiel.md) | Opens the non-saturating aggregation session ADR 0076 deferred at Gate 2; success is window recall 1.0 at the frozen 48 (CCH0959 surfaced, CSF0929 kept), candidates pre-registered by commit; not implemented | usefulness follow-on | 2026-09-27 | Accepted |

## Related reading

- [../atlas-report.md](../atlas-report.md) is the status report for the Atlas engine: what was
  built, what was measured, and what is honest about those numbers.
- [../../PROGRESS.md](../../PROGRESS.md) is the chronological build log, one section per PART.
- [../../encyclopedia/](../../encyclopedia/README.md) is the complete repository reference, including a one-paragraph catalogue of these records.
