# ADR 0078 — The synthetic diagnostic environment is constructible and answers its four questions

- **Status:** Accepted
- **Date:** 2026-09-15
- **PART:** Usefulness Phase, item U3 (the synthetic diagnostic environment) — continuation
- **Supersedes:** nothing
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0069](0069-cmms-exports-reach-the-work-order-inlet.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0075](0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md),
  [ADR 0077](0077-realism-reaches-the-instruments-and-the-manifest-becomes-reproducible.md)

## Context

ADR 0077 wired `phos.synth.realism` into `Plant._sense` and `modbus_frames`, and proved the six
standard quiet corpora byte-identical. It did not build the twelve scenarios, did not answer U3's
four diagnostic questions, did not write a `realism.json` sidecar, did not hand planned dropouts to
`generate.py`, did not test the non-empty dropout path, and did not enforce Gate 1's fit-history
safeguard. A 2026-09-15 audit also found that no *real* plant constructor forwarded `realism`, so
ADR 0077's claim that the phenomena "can now actually happen to a plant" was true of the base class
and of `TinyTank` only. That overstatement is annotated on ADR 0077 rather than rewritten.

U3 stays authorised through `.phos_usefulness_state.json` (Gate 1 passed 2026-09-11). This record
is diagnostic output on a plant we simulated. It is not a detection claim, not a row in
`eval_runs/log.jsonl`, and not evidence about a real plant.

## Decision

**1. Real plants forward `realism`.** `WaterTreatmentPlant`, `PowerGenerationPlant`,
`BatchReactorPlant`, `_PlantFactory`, `build_plant` and `run_plant` accept `realism=` and pass it
to `Plant.__init__`. `realism=None` remains byte-identical to `RealismProfile()`. A non-quiet
profile changes the readings. The identity proof for quiet corpora is therefore still a property of
`spawn(3)` plus a planner that draws nothing under a quiet profile.

**2. Dropouts reach the capture, including the non-empty path.** `generate.py` and
`attacks/generate.py` pass `run.realism.dropouts` to `modbus_frames`. Tests pin:

- a covered exchange with `retransmits=False` sends no request/response PDU inside the window;
- `retransmits=True` produces a gap and then a burst, with the same request count as no dropout;
- a named node leaves other connections byte-identical;
- TCP sequence numbers never go backwards;
- `dropouts=()` matches passing nothing; a plant with no control network yields no frames.

**Two transport-model decisions, from the implemented order, not from a preference:**

1. A dropped exchange still consumes its conversation's Modbus transaction id. The id is allocated
   before dropouts are consulted. Empty dropout sets stay byte-identical either way.
2. A whole-segment dropout does not suppress the TCP handshake of a connection first opened during
   it. `_conversation_for` emits the handshake before dropouts are consulted. The dropout covers
   Modbus PDUs, not TCP setup.

**3. `realism.json` is a sidecar, not a `RunSpec` field.** Written for non-quiet runs only, labelled
SYNTHETIC-DERIVED, serialised with `sort_keys=True`, listed in the manifest's `files`. Quiet
manifests stay byte-identical. Atlas never reads it (`src/phos/atlas/` contains no `realism.json`).

**4. Gate 1's fit-history safeguard is a property.** Every plant draws instrument calibration drift
from `DRIFT_PERIOD_HOURS = (48, 120)`. That range's upper bound is therefore a declared cycle of
every signal on every plant, slower than water's 72 h turbidity wander, power's 24 h demand, and
the batch reactor's declared timers (~3.21 h). Required history is **120 h on every plant**, named
as the instrument calibration-drift period. The committed power-generation train is 48 h and is
refused as a U3 fit; U3 generates its own stretch. `assert_fit_history` raises `FitHistoryTooShortError`
naming the cycle. The 120 h figure was not chosen because it separates scenarios.

**5. The twelve scenarios are seeded configurations.** Ground truth lives on `DiagnosticScenario`
and in the sidecar, never as an Atlas input. The batch reactor refuses the kinds that need a
control network rather than inventing a bus. Attacker-during-maintenance gives the *adversary* an
independently planned calendar; the calendar is never moved to cover the attack. A first
construction floored the chosen step to before `order.start`, so a write the adversary "picked a
window" for missed `covered_windows`. Fixed by taking the first sample at or after the order's
start. Seed 11 remains a no-overlap control; natural overlap is a reported seed search.

**6. The four questions are answered as SYNTHETIC-DERIVED diagnostic output.** Runner:
`scripts/diagnose_u3_environment.py --seed 11`. Report: `eval_runs/synth/u3-diagnostic.md`.
Nothing is appended to `eval_runs/log.jsonl`. Hypothesis confidence is never printed. Question 4
is structural: unique leader, tied leaders, competing template ids, whether `insufficient_evidence`
leads, whether the set shrinks when the capture is withheld.

The numbers below are the runner's. They are not a lead rate and are not set beside frozen 0/16 or
1/4.

| Question | Control that can come out no | What the runner printed |
| --- | --- | --- |
| 1. Command attribution when command evidence exists | ordinary operation: 0 unauthorised writes, 0 graph findings | treatment: 1 unauthorised scada write, 1 graph finding; issuer `scada` classified `known_station`; answer: the path sees the writes |
| 2. Maintenance evidence and direction | export withheld: 0 promoted facts; unique leader `insufficient_evidence` | SAP PM: 4 orders, 2 sanctioning, 2 promoted; unique leader `engineering_maintenance`; direction is ADR 0069's, not a retune |
| 3. Attacker inside a sanctioned window | seed 11 overlap `False` among searched `{7: True, 11: False, 13: True, 17: False, 19: True, 23: True}` | seed 7: 1 write issued, 1 falling inside a sanctioned clearwell window; calendar not moved |
| 4. More uncertain when evidence is removed | ordinary graph findings `0` | with capture: unique leader `insufficient_evidence`, 4 hypotheses, 1 graph finding, 3 command evidence; withheld: residual only, 0 command evidence; more uncertain `True`; more confident with less `False` |

Question 4's unique leader is already `insufficient_evidence` *with* the capture. That is ADR 0014
on a known-station write: the competing set contains both `engineering_maintenance` and
`unauthorised_control_activity`, so the residual is raised rather than an alphabetical winner.
Removing the capture does not mint a contentful unique leader. It shrinks the set from four
hypotheses to the residual. The sharp test is therefore passed in the only sense U3 is allowed to
read: Atlas did not grow more confident with less evidence. Changing templates to make
`unauthorised_control_activity` uniquely lead is outside U3.

**7. Quiet corpora stay byte-identical.** Attack corpora, pre-wiring `9549ebf` plus the grants
serialiser against `dd80523`: `scripts/compare_corpus_identity.py` printed `compared=39
identical=39 differing=0`. Repeat generation of the same tree: `39/39`. Standard quiet datasets at
`dd80523`: `compared=22 identical=22 differing=0`. After this continuation's wiring, dropouts,
sidecar, scenarios and runner, regeneration against those same `dd80523` baselines printed
`compared=22 identical=22 differing=0` (standard) and `compared=39 identical=39 differing=0`
(attacks). Quiet byte-identity is therefore a measured property of the finished tree, not an
argument from `spawn(3)`.

## Consequences

**Gained.** The categories U1 could not exercise on HAI are constructible. Atlas can be thrown into
situations it cannot tell apart a priori, and the four questions have controls that can come out
no. Realism reaches real plants. Dropouts reach the capture. Gate 1's 120 h safeguard is enforced
rather than intended.

**Cost, and it must not be papered over.** Everything here is our model, our adversary and our
maintenance practice (ADR 0029, ADR 0073, register R4). Question 1 is not a lead rate. Question 2
is a wiring result. Question 3 is inspectable on seed 7 and absent on seed 11. Question 4 confirms
ADR 0014 rather than lifting it: a known-station unauthorised write still cannot uniquely lead.
U4 is not started.

**Unfinished, and named.** U4's analyst interface, U5's human-decision machinery, U7's two-week
ask. The Atlas calibrator without labelled positives and Sentiel's non-saturating aggregation stay
`tracked_not_authorised`. Frozen public rows are untouched.

## Alternatives considered

- **Fit Atlas on the committed 48 h power-generation train.** Rejected. Gate 1 forbids a fit
  shorter than the slowest declared cycle; 48 h is below 120 h.
- **Move the maintenance calendar onto the attack.** Rejected. Anti-bias: coverage is a collision
  of two independent schedules, or an adversary given a calendar it did not write.
- **Print hypothesis confidence for question 4.** Rejected. Uncalibrated (constitution §3.3,
  ADR 0045). Structural terms only.
- **Score the 120 h baseline against itself as "evidence removed".** Rejected after the first
  draft. In-sample command behaviour on a long capture minted dozens of hypotheses and was not the
  incomplete-observations lever. Withholding the live pcap (no command facts ingested) is.
- **Invent a control network for the batch reactor.** Rejected. ADR 0015; recorded as a refusal.
