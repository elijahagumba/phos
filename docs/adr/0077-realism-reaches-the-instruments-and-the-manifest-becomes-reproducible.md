# ADR 0077 — Realism reaches the instruments, and the manifest becomes reproducible

- **Status:** Accepted
- **Date:** 2026-09-12
- **PART:** Usefulness Phase, item U3 (the synthetic diagnostic environment) — **first increment**
- **Supersedes:** nothing
- **Depends on:** [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0075](0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md)

## Context

`phos.synth.realism` has existed since ADR 0073 with seven phenomenon kinds — grade change, ambient
drift, equipment ageing, operator intervention, sensor fault, comms dropout, startup transition —
a profile, a planner, and effect objects carrying `apply`, `at` and `drops` methods. **None of it
was connected to anything.** ADR 0073 deferred the wiring deliberately, because it changes how
every corpus is produced, and required that the work carry its own ADR and a proof that every
pre-existing corpus is either byte-identical or explicitly re-versioned.

U3 is that work. Gate 1 (2026-09-11) passed U3's scenario list unchanged and added one binding
safeguard: the environment must give Atlas enough declared-normal history to fit against, because
U1 measured fit length as the dominant driver of alert volume.

The seven kinds are not an arbitrary list. They are, nearly one for one, the categories U1's error
taxonomy could **not** exercise on HAI:

| Realism kind | U1 category | Why HAI could not show it |
| --- | --- | --- |
| `COMMS_DROPOUT` | `communication_artefacts` | The prepared corpus is a 1-in-10 downsample; finer irregularity is unobservable **by construction** (R11) |
| `STARTUP_TRANSITION` | `startup_shutdown_transition` | All 15 declared run-state signals constant across the whole slice |
| `GRADE_CHANGE` | `grade_or_recipe_change` | No declared mode or setpoint change anywhere in the slice (R10) |
| `EQUIPMENT_AGEING` | `equipment_ageing` | 2.5 days cannot separate a duty-cycle phase from a degradation (R9) |
| `SENSOR_FAULT` | `sensor_noise` | Measurable, and refuted there; a *fault* is a different object from noise |
| `OPERATOR_INTERVENTION` | `maintenance` | HAI carries no operator-identity column: 0 of 79 (R8) |

This increment does the wiring and the proof. **It does not build the scenarios and does not answer
U3's four diagnostic questions** — see *Unfinished* under Consequences.

## Decision

**1. The profile is a `Plant` argument, not a `RunSpec` field.** `RunSpec` is serialised into every
`manifest.json` verbatim, so a field added there would have changed every existing manifest and
destroyed the identity proof before it began. The profile follows the `commands` idiom instead:
`Plant(spec, realism=...)`, defaulting to `None`, and **a plant given nothing is byte-identical to
one given `RealismProfile()`**.

**2. Realism draws from a third spawned seed.** `Plant.__init__` moved from
`SeedSequence(spec.seed).spawn(2)` to `spawn(3)`. `spawn` is deterministic by child index, so the
noise and setup streams are bit-identical to what `spawn(2)` produced — asserted by test across
four seeds rather than assumed. A quiet profile additionally returns from `plan_realism` before it
draws anything, so it consumes nothing from its own generator either. Byte-identity is therefore a
property of the construction, not of an ordering discipline someone must remember.

**3. `phos.synth.realism` no longer imports `phos.synth.plant`.** `plan_realism` took a `RunSpec`
and read exactly two fields from it; it now takes `start` and `duration`. That is the whole of its
real dependency, and removing the import is what lets the plant import the planner and apply its
effects where readings are made. The alternative — a local import inside `__init__` to dodge the
cycle — would have left the cycle in place and hidden it.

The anti-bias test that pins this signature is **strengthened, not weakened**: it still asserts the
exact parameter set, and it now also asserts the forbidden attack lexicon that only the maintenance
planner's twin was checking. The structural refusal is unchanged — the planner cannot see the
attack schedule, so a benign phenomenon cannot be placed to coincide with, or to avoid, an attack.

**4. The effects are applied in a declared order, and the order is the claim.** In `Plant._sense`:
ambient influence and ageing are added to the quantity **before** the instrument's span clamp,
because they move the true thing being measured; a sensor fault is applied **as the instrument's own
reading**, because a frozen transmitter or a walked calibration is not a fact about the process.
The first two are the plant; the third is the instrument. A detector that cannot tell them apart is
failing at something real rather than at an artefact of how this harness stacks its arithmetic.

**5. Comms dropouts reach the capture.** `modbus_frames` takes a `dropouts` sequence, empty by
default. A covered exchange is **lost**; if its dropout retransmits, it is re-sent once
service returns, which puts a gap and then a burst in the capture. Those are the two shapes a real
transport failure leaves. The jitter draws happen **before** the dropout is consulted, so the timing
stream is a function of the exchanges the plant made and not of where the network failed.

**6. `WriteAuthority.grants` serialises in sorted order.** Found while establishing the identity
proof, and **it predates this work**: `grants` is a `Mapping[str, frozenset[str]]`, and a
`frozenset` serialises in hash order, which varies between processes. Three generations of
`synth-water-treatment-train` from the same code and the same seed produced **two different
orderings** in `manifest.json` — runs one and three agreed, run two did not — while every payload
byte stayed identical. The defect touched the four manifests of the two plants that declare a
write authority; the batch reactor declares none, and its manifests always matched. A manifest
that cannot be reproduced makes "this corpus is unchanged" unfalsifiable, which is the one claim a
manifest exists to support. A `field_serializer` sorts both levels. The set genuinely has no
intrinsic order, so sorting is the only reproducible choice available.

## The corpus-identity proof

Not asserted — run. A detached worktree at `HEAD` (9549ebf, pre-U3) received **only** the
`grants` serialiser, so the single remaining variable between the two trees is the realism wiring.
Both trees regenerated all six standard datasets with `scripts/generate_synth.py --all`, and every
output file was compared by SHA-256:

| | |
| --- | --- |
| Files compared | **22** — telemetry, topology, capture and manifest, across six datasets |
| Byte-identical | **22** |
| Differing | **0** |

Before the `grants` fix the same comparison read 18 identical and 4 differing, and all four
differences were the grants ordering in manifests whose payload digests agreed — which is how the
nondeterminism was found rather than shipped.

**The attack corpora under `data/synth/attacks/` were not regenerated** and are named here rather
than quietly omitted: they are produced by `scripts/generate_attacks.py`, which this increment did
not run. Their payloads flow through the same `_sense` and `modbus_frames` paths under a quiet
profile, so the same argument covers them, but the *argument* is not the *measurement* and this
record does not pretend otherwise.

## Consequences

**Gained.** The seven benign phenomena PHOS has been able to describe since ADR 0073 can now
actually happen to a plant, and they are exactly the categories HAI could not exercise. The
confusability U3 needs — Atlas being unable to tell situations apart a priori — has a mechanism for
the first time.

> **Corrected 2026-09-15 by [ADR 0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md)
> (Usefulness Phase U3 continuation).** The sentence above overstated the reach of the wiring.
> `Plant.__init__` accepts `realism` and `_sense` applies the plan, but `WaterTreatmentPlant`,
> `PowerGenerationPlant` and `BatchReactorPlant` each override `__init__` and forward only
> `commands`. `_PlantFactory`, `build_plant` and `run_plant` have no `realism` argument, and
> nothing under `src/` or `scripts/` constructs a plant with `realism=`. The phenomena can happen
> to the base class and to the `TinyTank` test fixture; they cannot happen to a real plant until
> those constructors forward the argument. The paragraph is left as written, because what was
> claimed is part of the record.

**Gained, second.** A defect that made four of the six standard manifests irreproducible is fixed,
and it was found because the identity proof was run rather than asserted. That is the proof
earning its cost on its first use.

**Cost, and it must not be papered over.** This changes no number anywhere. No corpus moved, no
detector was touched, no scenario was built, and nothing here is a detection claim. `ADR 0029`
stands in full: synthetic data is our model, our adversary and our maintenance practice, and it
cannot validate anything against its own assumptions.

**Unfinished, and named rather than left to be discovered.** The scenarios, the four diagnostic
questions, the `realism.json` sidecar that will carry each run's benign phenomena as
SYNTHETIC-DERIVED ground truth, the plumbing that hands a plant's planned dropouts to its own
capture in `generate.py`, a test of the non-empty dropout path in `modbus_frames` — only the empty
path is exercised, by the identity proof — and Gate 1's fit-history safeguard as an enforced
property rather than a recorded intention. U3 stays `in_progress`.

> **Discharged 2026-09-15 by [ADR 0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md).**
> The named unfinished work is done: real plants forward `realism`; dropouts including the
> non-empty path are tested; `generate.py` hands planned dropouts to the capture; the sidecar
> exists; Gate 1's 120 h safeguard is a property; twelve scenarios are constructible; the four
> questions are answered as SYNTHETIC-DERIVED. This paragraph is left as written because what was
> unfinished is part of the increment's record.

## Alternatives considered

- **Add `realism` to `RunSpec`.** Rejected. `RunSpec` is serialised into every manifest, so this
  would have changed all six manifests on day one and made the identity proof impossible to state.
- **Import `phos.synth.realism` lazily inside `Plant.__init__`.** Rejected. It dodges the cycle
  instead of removing it, and leaves the next reader to rediscover why the import is in a function.
- **Normalise the grants ordering in the comparison rather than in the serialiser.** Rejected, and
  it is the tempting shortcut: it would have made this proof pass while leaving every future
  identity claim resting on a manifest that still could not be reproduced.
- **Regenerate the committed corpora on disk.** Rejected as out of scope and unnecessary — they are
  gitignored payloads, and the on-disk manifests are already stale against `HEAD` for an unrelated
  reason (`write_authority`, added by ADR 0073 after they were last written). The proof compares
  *code to code*, which is the claim that matters.
- **Apply sensor faults before the ambient and ageing terms.** Rejected. It would make an
  instrument fault indistinguishable from a process excursion by construction, which is precisely
  the discrimination U1 had to make on HAI and precisely what U3 exists to exercise.
