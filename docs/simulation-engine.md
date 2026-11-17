# PHOS Simulation Engine

The PHOS simulation engine generates clean, richly labelled, attack-dense industrial control
system data with perfect ground truth. It has three parts:

| Part | What it builds | Where it lives |
|---|---|---|
| **D1** | Simulated plants with true-state records, Modbus captures, declared topologies | `src/phos/synth/` (plants, injection, topology) |
| **D2** | Graded attack library — 28 attacks per plant at four difficulty levels, plus input-hostile cases | `src/phos/synth/attacks/` |
| **D3** | Evaluation harness that runs Atlas against synthetic corpora and maps where it goes blind | `scripts/evaluate_atlas_synthetic.py` |

Real-world labelled OT data barely exists in public, and the public corpora PHOS inspected are all
refused as detection rulers (ADR 0040, ADR 0046, ADR 0047). The simulation engine is PHOS's answer
to that gap: an environment we build ourselves, understand completely, and can generate ground
truth for.

## What this is

- **Three simulated plants:** a water treatment works, a power generation set, and a batch chemistry
  reactor. Each runs on physics (tanks fill because something flowed into them, temperatures lag
  behind heat applied, controllers act on what instruments report) and records what the plant was
  *actually* doing, separately from what its instruments say it was doing.
- **Declared topologies:** which signals sit on which physical unit, written down and sourced to the
  plant declaration — never clustered from co-movement (ADR 0010).
- **Modbus/TCP captures:** real packet captures that the Atlas packet path already dissects, with
  attacker writes included where attacks act on the wire.
- **Graded attacks:** 28 attacks per plant at four points on the difficulty dial (obvious, moderate,
  subtle, near-invisible), spanning seven attack types (blatant, stealth drift, correlation break,
  liar, mimic, rogue command, mimic command), plus input-hostile cases (malformed records,
  out-of-range values, truncated files, poisoned baselines).
- **Perfect ground truth:** every corpus is two simulations of one seed — one clean, one attacked.
  Ground truth is the measured difference between them, not an intention. An attack that changed
  nothing is refused rather than labelled.

## What this is not

- **It is not real plant data.** Every plant is a model of reality, written from public descriptions
  of how such processes behave. The physics is deliberately modest: tanks are volumes with flows in
  and out, temperatures are first-order lags, valves are flow coefficients. There is no CFD, no
  detailed chemistry, no mechanical wear model. A million generated plants are a million models.
- **It is not a detection claim.** Results measured on this data describe what Atlas handles in *our
  model of a plant* — an upper bound on this library, never a lower bound on reality. If Atlas ever
  scores suspiciously well, the first hypothesis is a leaked fingerprint, not brilliance.
- **It is not a public corpus.** ADR 0029: the synthetic library is not a public corpus. ADR 0073:
  the synthetic harness measures nothing that may be believed as a real-world detection rate.
- **It is not deployable.** The engine generates data; it does not detect, alert, or act on a live
  plant.

## The standing caveats

Every corpus the engine writes carries these four caveats, and every downstream user must read them
before drawing conclusions:

1. **MODEL_NOT_REALITY_CAVEAT** — This is a model of a plant, not reality. Good scores here mean
   Atlas handles our model of a plant, not evidence of handling a real one.
2. **ATTACKS_ARE_OURS_CAVEAT** — These are attacks we designed. A detection rate measured here is
   an upper bound on this library, never a lower bound on reality. A suspiciously good score is a
   leaked fingerprint until proven otherwise.
3. **SYNTHETIC_TOPOLOGY_CAVEAT** — The topology is declared by us, not derived from plant
   documentation. A real corpus's topology is a reading of process documentation and can be wrong.
4. **INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT** — Input-hostile cases test software survival, not
   security. Passing them is not evidence that PHOS is secure against a real-world attacker.

## The anti-bias construction

The central risk is circularity: if one author writes both "an attack looks like this" and "the
detector looks for that", a good score measures the agreement of two beliefs. The engine enforces
five mechanisms, each failing the build if violated:

1. **The generator may not reference the detector.** No module under `src/phos/synth/` may import
   from or name any Atlas or Sentiel feature, score, threshold, model, or detection concept. The one
   declared exception: `phos.synth.topology` imports `SCHEMA_VERSION`, `Subsystem` and `SubsystemMap`
   from `phos.atlas.topology` so a generated corpus ships its declared subsystem map in the same
   format a real corpus does — a declaration format, carrying no feature, score, threshold or
   finding.
2. **Attacks are specified by intent, never by signature.** A scenario states a goal in the plant's
   own terms (e.g., "drive the clearwell above the level the works is operated to"). It is forbidden
   to specify an attack as "make signal X deviate by Y" or in terms of any quantity the detector
   computes. Difficulty is carried by patience (how long the adversary is willing to take), not by a
   magnitude field — the `Scenario` model has no `magnitude`, `deviation`, `strength`, `subtlety` or
   `z_score` field.
3. **Every scenario carries real-world provenance.** Each scenario cites a documented incident, a
   published ICS attack taxonomy, a process-engineering failure mode, or a vendor advisory. The
   provenance validator rejects citations naming `atlas`, `sentiel`, `interesting`, `tbd`, `todo` or
   `n/a`.
4. **A mandatory band of cases the detector should miss.** A generator that only produces catchable
   attacks is a mirror. The catalogue requires scenarios whose adversary walks a setpoint over 720+
   samples — a per-step change far under the plant's ordinary variation — and requires benign cases
   deliberately shaped like attacks.
5. **The method is published, including its failures.** This document and the limitations section
   below are required deliverables; a test fails if they are shorter than 400 words.

## Limitations

Everything below is a way this engine is likely to mislead, written down while it is still
uncomfortable to write:

- **The physics is a model of a process, not a process.** None of it was fitted to, or validated
  against, any particular works or station. The dynamics are almost certainly too clean: real plants
  have unmodelled interactions, hysteresis, stiction, dead bands, and operators who do things the
  model has no representation for.
- **The noise model is too kind.** Instrument error here is Gaussian noise plus bounded calibration
  drift. Real instrument error is heavy-tailed, correlated across instruments, and punctuated by
  spikes, freezes and rail-outs with no distribution behind them.
- **The control network is impoverished.** One protocol, one unit id, a fixed poll cycle, a handful
  of devices. Real plants carry several protocols, redundant masters, serial gateways, historians,
  vendor remote-access sessions.
- **The write authority is a fiction of convenience.** Granting exactly one station produces a clean
  three-case structure (authorized HMI, unauthorized SCADA, unknown-master engineering). Real plants
  have messy, partially documented, frequently violated access policies.
- **The maintenance practice is invented.** The intervals, callout rate and share of non-sanctioning
  orders are plausible numbers, not measured ones.
- **The adversary is more consistent than a real one.** No lateral movement, credential theft, dwell
  time, or track-covering.
- **The benign class is still too easy.** Real plants produce most false positives from things
  nobody thought to simulate.
- **The whole thing shares an author with the detector.** The five mechanisms reduce circularity;
  they do not eliminate it.

## How to use it

Generate plants:

```bash
# List available plant families
uv run python scripts/generate_plants.py list-families

# Draw one plant and write a day of it
uv run python scripts/generate_plants.py generate level_flow 2026001

# Verify a generated plant against its manifest
uv run python scripts/generate_plants.py verify data/plants/level-flow-2026001
```

Generate attack corpora:

```bash
# Generate every configured attack dataset
uv run python scripts/generate_attacks.py --all

# Generate one dataset by name
uv run python scripts/generate_attacks.py --dataset synth-attack-water-treatment-graded
```

Run Atlas against synthetic corpora (D3):

```bash
# Score Atlas on every synthetic corpus found
uv run python scripts/evaluate_atlas_synthetic.py

# Score one corpus only
uv run python scripts/evaluate_atlas_synthetic.py synth-attack-water-treatment-graded

# Print tables without writing to the experiment log
uv run python scripts/evaluate_atlas_synthetic.py --no-log
```

Every D3 report is written to `eval_runs/synth/` — never to `eval_runs/log.jsonl` — and carries
`SYNTHETIC-DERIVED` plus the four standing caveats.

## Licence

Released under the [PolyForm Noncommercial License 1.0.0](public/overlay/LICENSE). Noncommercial
use, research, education, and personal experimentation are permitted purposes. Commercial use
requires a separate licence. Copyright (c) 2026 Elijah A. Edoigiawerie.

## Related decisions

- [ADR 0015](docs/adr/0015-simulated-plants-the-injection-hook-and-the-true-state-record.md) — Simulated plants, the injection hook, and the true-state record
- [ADR 0016](docs/adr/0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md) — The graded attack library: flavour separation and the anti-fingerprint discipline
- [ADR 0029](docs/adr/0029-synthetic-dataset-library-is-not-a-public-corpus.md) — A synthetic dataset library is not a public corpus
- [ADR 0073](docs/adr/0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md) — A synthetic command-and-maintenance harness, built so that its results cannot be believed
- [ADR 0078](docs/adr/0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md) — The synthetic diagnostic environment is constructible and answers its four questions
- [ADR 0454](docs/adr/0454-d3-synthetic-evaluation-harness-for-atlas.md) — D3: synthetic evaluation harness for Atlas, SYNTHETIC-DERIVED only
- [ADR 0455](docs/adr/0455-simulation-engine-is-a-releasable-open-source-component.md) — The simulation engine is a releasable open-source component
