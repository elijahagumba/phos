# ADR 0108 — A reading that disagrees with the rest of the plant becomes evidence, and routes

- **Status:** Accepted
- **Date:** 2026-10-11
- **PART:** v1, rebuilding the detector after G1; groundwork for the liar measurement (T1) and for
  `docs/phos-2027.md` W2
- **Depends on:** [ADR 0070](0070-the-evidence-facet-replaces-summary-string-parsing.md) (typed facets),
  [ADR 0071](0071-command-behaviour-evidence-reaches-a-template.md),
  [ADR 0094](0094-liar-measurement-seeds-and-pass-share.md),
  [ADR 0107](0107-the-consistency-detector-enters-the-engine.md)

## Context

ADR 0107 put the clean-HAI detector into the engine. Its strongest signal is the loop score: how
far a reading departs from what every other signal, now and over the last minute, implies. ADR 0106
showed that score carries most of the detector's margin over grouped MinMax on clean data. Nothing
in the reasoning layer could cite it. ADR 0094's liar declaration names two `Evidence.facet`
strings, `cross_signal_mismatch` and `command_to_response_mismatch`, and records that nothing
emitted them.

## Decision

**1. A new facet kind, `FacetKind.CONSISTENCY`.** Two features are declared:
`cross_signal_mismatch` (emitted) and `command_to_response_mismatch` (declared, not emitted:
telling a command from its response needs a declared pairing no topology carries yet, and
inferring one from co-movement is the circularity `phos.atlas.topology` refuses).

**2. `phos.atlas.consistency_evidence.promote_consistency`.** For each event the detector forms,
the alert cell becomes evidence only when its calibrated loop score is above the detector's
threshold and at least its range score. The fact is built through `phos.reasoning.boundary`, the
only door into reasoning, as an `Observation`, a `Deviation` and `Evidence` of kind `DEVIATION`.
The `Deviation`'s expected range is centred on the regression's prediction (what the rest of the
plant implies the reading is) with the half-width at which the calibrated loop score reaches the
threshold, including the detrending baseline (`phos.atlas.consistency.loop_expectation`). The
predicted value also travels in the observation's context and in the summary. For a falsified
instrument, that prediction is a reconstruction of the real value. Weights come from a supplied
calibrator, as for every other inlet.

**3. `ConsistencyPattern`, and two template relations. No prior moves.**

- It **supports `sensor_or_device_fault`**. One reading that stops agreeing with everything coupled
  to it is the instrument, or the equipment it measures.
- It **contradicts `process_disturbance`**. A real process upset propagates through physically
  coupled signals, so the learned relationships between them keep holding while the readings move.
  An unmodelled physical event such as a leak also breaks a mass balance, and is read as equipment
  failing, which is the label that fits it.
- It bears on **neither `engineering_maintenance` nor `unauthorised_control_activity`**. A
  falsified reading and a failed transmitter leave the same fact, and an attacker who moves
  actuators leaves the plant consistent. Separating those needs other evidence, such as who
  commanded what.

The pattern refuses grouped subsystem events and is disjoint from `CommandBehaviourPattern` by facet
kind; `SubsystemBreadthPattern.overlaps` and `CommandBehaviourPattern.overlaps` say so explicitly,
so every template stays single-valued.

**4. A third optional inlet on `AtlasEngine.run`: `consistency`.** Stored with its whole chain and
interleaved by time, exactly like commands and work orders. Omitted or empty, a run is
byte-identical to the run without it.

**5. The tripwire 5C left fired, as designed.** `test_the_malicious_and_the_benign_upset_differ_only_where_commands_reach`
asserted that process telemetry weighs the malicious and the benign upset identically, and said a
later PART that separated them would make it fail. This record is that PART: a consistency fact
contradicts the benign upset and is silent on the malicious one. The test now excludes
`ConsistencyPattern` from its telemetry comparison, for the reason it already excluded
`CommandBehaviourPattern`, and says so; the asymmetry is asserted on its own.

## Consequences

- The liar measurement can now be run: Atlas emits the facet ADR 0094's predicate reads. It has
  not been run. Nothing here is a liar result.
- On a synthetic plant with a frozen instrument, the reconstructed value is closer to the true
  value than the reading is (a unit test, not a measurement). W2 in `docs/phos-2027.md` is the
  measurement, declared before it is run.
- No frozen row, no prior, no `EVIDENCE_STRENGTH` and no published result changed. Nothing was
  appended to `eval_runs/log.jsonl`.

## What would reverse this

Evidence that real process upsets routinely break the learned cross-signal relationships, which
would remove the contradiction of `process_disturbance`; or a consistency fact reaching a template
by any route other than `ConsistencyPattern`.
