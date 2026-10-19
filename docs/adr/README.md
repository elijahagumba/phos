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
| [0190](0190-depth-counting-one-loud-signal.md) | Depth counting: one loud signal can match many quiet ones | ADR 0144 | 2026-10-19 | Accepted |
| [0191](0191-behaviour-chains-are-declared-shapes.md) | Behaviour chains are declared shapes, not host names | ADR 0144 | 2026-10-19 | Accepted |
| [0192](0192-peer-groups-by-role-and-time.md) | Peer groups are role and time of day, not a new 6B peer feature | ADR 0144 | 2026-10-19 | Accepted |
| [0193](0193-rare-links-among-declared-peers.md) | Rare user–machine–site links are scored, not drawn on the org graph | ADR 0144 | 2026-10-19 | Accepted |
| [0194](0194-kept-scorer-is-still-6b-r42-unscored.md) | The kept scorer is still 6B; r4.2 stays unscored | ADR 0144 | 2026-10-19 | Accepted |
| [0200](0200-the-public-repository-takes-the-house-style.md) | The public front page takes the house style of `brand/phos_pdf.py` before week 13, by Elijah's decision: monochrome, white logo once on a black cover, black callouts, grey stat panels; a results card; Bet 001's loss recorded | ADR 0044, ADR 0170 | 2026-10-19 | Accepted |
| [0201](0201-the-front-page-leads-with-real-data-and-a-contact.md) | The front page leads with real data (131 of 160 HAI attacks at 8 alerts a shift, against 52 for the best baseline checked); the record page opens with current numbers and "start here"; one public contact address, with the guard still refusing every other Proton address | ADR 0116, ADR 0200 | 2026-10-19 | Accepted |

## Related reading

- [../atlas-report.md](../atlas-report.md) is the status report for the Atlas engine: what was
  built, what was measured, and what is honest about those numbers.
- [../../PROGRESS.md](../../PROGRESS.md) is the chronological build log, one section per PART.
- [../../encyclopedia/](../../encyclopedia/README.md) is the complete repository reference, including a one-paragraph catalogue of these records.
