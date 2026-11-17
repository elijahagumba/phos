# Example corpora selected for publication

This document lists the synthetic corpora PHOS intends to publish under ADR 0457 Decision 3. Selection is
deliberate, not exhaustive. Fixed datasets establish reproducibility of those particular experiments, not the
fidelity of the entire simulation engine.

## Selected corpora

| Corpus | Location | Samples | Attack windows | Purpose |
|---|---|---|---|---|
| `synth-water-treatment-holdout` | `data/synth/synth-water-treatment-holdout/` | 51,840 | 0 | Quiet plant; false-positive baseline. No attacks. Used to measure FP/normal-hour on normal operation. |
| `synth-attack-water-treatment-graded` | `data/synth/attacks/synth-attack-water-treatment-graded/` | 14,400 | 28 | Labelled attacks across four difficulty levels (obvious, moderate, subtle, near-invisible) and seven attack types. The main graded corpus. |
| `synth-attack-water-unknown-master` | `data/synth/attacks/synth-attack-water-unknown-master/` | 2,880 | 4 | Command/re-routing scenario. Unknown-master engineering workstation writes. Tests Atlas's ADR 0027 path. |
| `synth-hostile-malformed-records` | `data/synth/attacks/synth-hostile-malformed-records/` | 2,880 | 0 | Software robustness. Malformed CSV records; not a detection corpus. Tests whether the parser survives hostile input. |
| `synth-power-generation-train` | `data/synth/synth-power-generation-train/` | 165,888 | 0 | Second plant family, quiet. Power generation set with islanded grid dynamics. |
| `synth-batch-reactor-holdout` | `data/synth/synth-batch-reactor-holdout/` | 33,696 | 0 | Batch process, quiet. Reactor trains stepping through recipes. |

## Files published per corpus

Each corpus directory ships:

| File | Format | Purpose |
|---|---|---|
| `telemetry.csv` | Prepared-corpus CSV | `phos.eval.LabelledCsvAdapter` reads unchanged. Timestamp, label column, value columns. |
| `topology.toml` | TOML | Declared subsystem map. `phos.atlas.topology.load_topology` reads. |
| `manifest.json` | JSON | Generation recipe, plant declaration, seeds, traffic seed, digests of each file. |
| `capture.pcap` | PCAP/PCAPNG | Modbus/TCP control traffic. `phos.atlas.packet.dissect_capture` reads. Absent for plants with no control network. |
| `SHA256SUMS` | Text | SHA-256 digest of every file above, for integrity verification. |

## What is NOT published

- The generator source code (`src/phos/synth/`).
- The attack configs (`configs/attacks/*.toml`) — these describe the attack plans but are not required to score
  against the published corpora.
- The training/calibration split policy used internally by D3 — researchers bring their own split.
- Any HAI, BATADAL, SWaT, or other real-plant corpus.

## Publication caveats

Every published corpus carries the four standing caveats in its manifest:

1. `MODEL_NOT_REALITY_CAVEAT` — this is a model of a plant, not reality.
2. `ATTACKS_ARE_OURS_CAVEAT` — these are attacks PHOS designed; upper bound on this library, never lower bound
   on reality.
3. `SYNTHETIC_TOPOLOGY_CAVEAT` — topology declared by PHOS, not derived from plant documentation.
4. `INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT` — input-hostile survival is software robustness, not detection.

Plus `SYNTHETIC-DERIVED` marking on any evaluation report produced against these corpora.

## How researchers use these

1. Download a corpus. Verify SHA-256 digests.
2. Load `telemetry.csv` through `phos.eval.LabelledCsvAdapter` (or their own equivalent).
3. Run their detector against the labelled attack windows.
4. Publish recall, FP/normal-hour, precision — with `SYNTHETIC-DERIVED` and the four caveats attached.
5. Do not compare against frozen public rows (HAI 646.58, grouped 53.26, etc.). Do not claim field detection rates.
