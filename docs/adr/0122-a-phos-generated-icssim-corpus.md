# ADR 0122 — A PHOS-generated ICSSim corpus: process, true state and Modbus, declared before use

- **Status:** Accepted
- **Date:** 2026-10-13
- **PART:** after v1 A2; data for T1, A4 and `docs/phos-2027.md` W2–W4
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md)

## Context

ADR 0117 records that every public corpus PHOS holds is now seen by `atlas-v1-consistency`, and
that no public corpus pairs network traffic with process state under a commercial licence: ICS-Flow,
the one lead, is CC BY-NC-SA 4.0 (registry `ics-flow`). It was produced with ICSSim, whose code is
MIT-licensed. A dataset PHOS generates itself with ICSSim belongs to PHOS, can be regenerated, and
can have fresh held-out runs whenever a clean test is needed. Elijah asked for one on 13 October.

## Decision

**1. The generator.** `scripts/icssim/phos_icssim.py` runs ICSSim's own physics and PLC logic,
unchanged, at `AlirezaDehlaghi/ICSSIM` commit `bcfd1844d3f063850c69f2643f6a052bac03d8ec` — that
commit is not in this repository — and patches at run time instead of editing ICSSim's files: a
scaled clock shared by every component (default 20×), an in-process store in place of ICSSim's
sqlite file, loopback identities for every Modbus client (PLC-1 `127.0.0.11`, PLC-2 `127.0.0.12`,
operator console `127.0.0.21`, attacker `127.0.0.66`), a log of every networked read and write each
PLC serves, and sensor tampering for falsified readings.
`scripts/icssim/generate_corpus.py setup` clones ICSSim at that commit under `data/` (so git never
sees it), checks its LICENSE file's sha256 and installs `pyModbusTCP==0.3.1` and
`python-memcached==1.62` in a virtual environment there. ICSSim's code is not copied into the lab.

**2. What a run contains.** One directory per run:

| File | What it is |
| --- | --- |
| `process.csv` | What the control system reports: every tag, read from the PLCs' registers once per simulated second |
| `truth.csv` | The plant's real state from the physics, same grid. **For judging only** (ADR 0017) |
| `modbus.csv` | Every networked read and write: time, client address, role, PLC, function, tag, decoded value |
| `events.json` | The declared events: kind, start, end, `attack` or `benign`, parameters |
| `work_orders.csv` | One row per genuine maintenance event |
| `manifest.json` | Scenario, seed, time scale, generator sha256, each file's sha256 |

**3. Events.** Seeded by `schedule(scenario, seed)`; never in the first ten minutes, at least five
minutes apart, never overlapping.

| Kind | Label | What happens |
| --- | --- | --- |
| `setpoint` | benign | The operator changes the tank's high level |
| `maintenance` | benign | The operator holds the output valve closed; a work order is written |
| `liar_freeze` | attack | PLC-1's tank-level sensor reports a frozen value while the real level moves |
| `liar_offset` | attack | It reports the real level minus 1–3 units |
| `rogue_command` | attack | The attacker forces a valve open over Modbus |
| `recon` | attack | The attacker reads every register on both PLCs repeatedly |
| `replay` | attack | The attacker sends the operator's maintenance command at the wrong time |
| `mimic_maintenance` | attack | The maintenance action from the operator's own console, with no work order |

`normal` runs (4 h) carry operator activity and maintenance only. `mixed` runs (2 h) carry eight
events and every kind at least once.

**4. The split, declared before any run is scored.**

| Role | Runs | Seeds |
| --- | --- | --- |
| `development` (`phos-icssim-dev`) | 3 `normal` + 10 `mixed` | 96001–96003; 96011–96020 |
| `held-out` (`phos-icssim-heldout`) | 20 `mixed`: 40 h, 160 events, 120 attacks | 96101–96120 |

The development set may be read and scored any number of times. The held-out set may be
generated at any time and is not opened until a declaration names the configuration and the
command; it is then scored once and moves to `validation` (ADR 0117). Training normal behaviour for
a held-out score comes from the development `normal` runs.

**5. What the generator was checked against (development seeds only).** A 2-hour `mixed` run
(seed 96001, 361 s of wall time) and two shorter runs. Every event had its stated effect: while
`liar_offset` ran, the reported tank level stayed between 2.7 and 7.0 while the real level rose to
9.5; during `liar_freeze` the report stayed at 3.34 while the tank ran dry; `rogue_command` overflowed
the tank; `replay`, maintenance and its mimic closed the output valve; `recon` had no physical effect.
The traffic log recorded about 220,000 transactions, attributed by role. Two limits seen: reported
and true values of fast-moving tags differ slightly outside any attack, because the PLCs sample on a
200 ms cycle; and one brief burst of failed PLC-to-PLC reads occurred mid-run. Both are properties
of the emulation and are left in the data rather than filtered.

**6. Licence.** The data is PHOS's own. ICSSim's LICENSE at the pinned commit is the MIT License,
read once; its copyright line names "CodeRefinery", which looks like template text. GitHub's licence
metadata, the second surface, was not reachable from the build container and is still to be read.

## Consequences

- PHOS has, for the first time, network traffic and plant state from the same runs, falsified
  readings with the true value known, and a genuine maintenance action beside the same action
  disguised. It is emulated, so every result on it is diagnosis, not proof (R4), and the registry
  says so on both entries.
- Nothing has been scored. No frozen row, prior, detector constant or published result changed.
  Nothing was appended to `eval_runs/log.jsonl`.
- Atlas does not read these files yet. An adapter from `process.csv` and `modbus.csv` to Atlas's
  telemetry and command inlets is the next step, built and checked on development runs only.

## What would reverse this

Reading the held-out runs' labels before a declaration; editing ICSSim's files rather than patching
at run time; or a change to `schedule` that alters a declared seed's events without a new record.
