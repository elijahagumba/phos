# ADR 0274 — The ICSSim corpus exists, and its held-out half is sealed

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Atlas, stronger-engine programme, step 0274
- **Supersedes:** nothing
- **Depends on:** [ADR 0047](0047-s7-process-parquet-is-unlabelled-track-a-refused.md),
  [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0273](0273-the-stronger-engine-programme-is-declared.md)

## Context

This record is written late. `docs/build-brief-2026-10-e.md` reserves 0274 for "the corpus
exists", and the corpus was generated and used — lanes 1 and 2 are both measured on it, and
ADR 0276 took its held-out score — but the step itself was never recorded. The number stayed
missing while the work it names was finished, so `ls docs/adr/ | grep -E '^02(7[3-9]|8[0-4])'`
under-reported the programme by one step. Nothing here is a new result; it records facts already on
disk and already relied on.

**Why the corpus had to exist at all.** ADR 0273 established that for labelled *physical* attacks
under a licence PHOS may use commercially there is no headroom left: the seen HAI editions and
BATADAL are barred from iteration by `docs/rules/data-tiers.md`, `hai-20.07` is already caught 37
of 38, `s7-data-modification` has no attack labels in its process file (ADR 0047),
`tu-wien-pilot-factory` contains no attack that moves the plant, and the remaining corpora are
faults, phases, or licence-barred. A stronger engine could therefore only be developed against a
plant PHOS generates, and only proved on data PHOS has never opened.

## Decision

**The corpus is what the programme measures on, in the two halves recorded below.**

| Item | Value |
| --- | --- |
| Generator | `scripts/icssim/phos_icssim.py`, sha256 `029e262591793d07f3d387b6eaadc2d91e07792cb454536d299db3b20845c0d0`, identical across every run's `manifest.json` in both halves |
| Driver | `scripts/icssim/generate_corpus.py`, subcommands `setup`, `development`, `held-out`. Standard library only; `setup` clones ICSSim at a pinned commit under `data/`, so git never sees it |
| Development | `data/phos-icssim-dev/` — 13 runs: `normal-96001`–`96003` and `mixed-96011`–`96020` |
| Held out | `data/phos-icssim-heldout/` — 20 runs, `mixed-96101`–`96120` |
| Signals | 13, one second a sample. A `normal` run is 14,401 rows; a `mixed` run is 7,201 |
| Per run | `process.csv` (the readings), `truth.csv` (the real values, so a falsified reading is recoverable), `modbus.csv` (every message with the station that sent it), `events.json`, `work_orders.csv`, `manifest.json`, `logs/`, `storage/` |
| Pinning | Each `manifest.json` carries the generator's sha256 and a sha256 per data file, plus seed, declared duration 7,200 s, time scale 20.0 and wall seconds |
| Events | A `mixed` run carries eight labelled events: six attacks — `recon`, `replay`, `liar_freeze`, `rogue_command`, `mimic_maintenance`, `liar_offset` — and two benign, `maintenance` and `setpoint`. Each has a start, an end and its parameters |
| Split rule | `phos-icssim-dev` is iterated on freely. `phos-icssim-heldout` is generated and then **not opened** until a committed declaration names it (`data-tiers.md`). Generating is not opening |
| Payloads | Never committed. `roles.toml` is the one tracked file under a corpus directory |

**Both halves for the same plant, which no public corpus gives.** `process.csv` and `modbus.csv`
cover the same minutes, and the `role` column attributes each message to `operator`, `plc1`,
`plc2` or `attacker`. That is the only reason lane 1 could be posed at all: "a write arrived, and
it came from somewhere that does not normally write" is not recoverable from any corpus in
`data/registry.json`.

**The baseline this corpus was built to provide.** `eval_runs/build/lane-e/baseline-icssim-dev.md`,
21 October: the frozen `atlas-v1-consistency`, fitted on the three `normal` runs and scored on the
ten `mixed` runs with nothing tuned, catches **24 of 60 attacks** within the frozen budget of 8
alerts per 8-hour shift, with 4 of 20 benign events also drawing an alert. Two classes sit at zero
(`recon`, `mimic_maintenance`). That spread is the point: on the synthetic plants every shape was
caught 6 of 6 by both the champion and the lane 2 variant, so no variant could be distinguished
from the champion at all (lane Q hit the same wall at 20 of 20, ADR 0233). This corpus
discriminates and the synthetic harness did not.

## Consequences

**The macOS loopback failure is part of this record, because it cost a full generation run and
will recur.** The harness gives each simulated station its own loopback address — `127.0.0.11`
PLC1, `127.0.0.12` PLC2, `127.0.0.21` operator, `127.0.0.66` attacker
(`scripts/icssim/phos_icssim.py:46`) — so the Modbus server can tell which station spoke. Linux
binds all of `127.0.0.0/8`; macOS binds only `127.0.0.1`, so every `sock.bind((source, 0))` fails
with errno 49 **and the run still exits 0**.

On 20 October all 13 development runs completed, 85 MB, and every one was unusable:
`modbus.csv` was 46 bytes, header only; `process.csv` had its 7,201 rows per mixed run with
**every value in every row 0.0**, verified across four runs; `snapshots_PLC1.csv` and
`snapshots_PLC2.csv` were empty, so neither controller completed a single scan; and
`logs-Factory.log` ran to 71,264 lines ending in repeated `tank water overflowed`, the signature
of a plant nobody is controlling. One cause, both symptoms: with no controller reading sensors or
driving actuators, the recorded state never leaves its initial zero.

So the aliases are a precondition, they need a password, and they do not survive a reboot:

```
sudo ifconfig lo0 alias 127.0.0.11 up
sudo ifconfig lo0 alias 127.0.0.12 up
sudo ifconfig lo0 alias 127.0.0.21 up
sudo ifconfig lo0 alias 127.0.0.66 up
```

Two further operational facts, both learned the hard way: the generator **skips** any run directory
that already exists and is non-empty, so a rerun over a spoiled batch produces nothing and the
directories must be removed first; and a generated run is only trustworthy once it is checked for
non-zero rows and a `modbus.csv` over 100 KB, because this corpus has twice produced plausible
files containing nothing.

**What this corpus is not.** A simulated plant. R4 and ADR 0143 make every result on it diagnosis
and not proof, and no claim from it says Atlas is any particular strength on real plant data. It
does not say the six classes are representative of anything. The frozen `atlas-v1-consistency` is
not edited by anything measured here, and no v1 number moves; v1 stays 8 of 12.

## What would reverse this

Regenerating either half over the existing directories, which would destroy the record lane 1's
ADR 0276 score rests on. `phos-icssim-dev` and `phos-icssim-heldout` are frozen as the corpus the
programme's first two lanes were measured against; a generator change takes a new corpus under a
new name and its own declaration, which is how `phos-icssim-dev2` came to exist (ADR 0285).
