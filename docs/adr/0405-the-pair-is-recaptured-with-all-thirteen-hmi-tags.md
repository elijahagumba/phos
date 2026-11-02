# ADR 0405 — The pair is recaptured with all thirteen HMI tags, so the block claim is in the files

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS capture, second pass. Runs `97201` and `97206` again, wider HMI stream
- **Supersedes:** nothing. ADRs 0402–0404 stand. The first captures are **kept**, not overwritten
- **Depends on:** [ADR 0404](0404-the-cyber-relay-freezes-all-thirteen-registers-and-the-pair-is-more-symmetric.md),
  [ADR 0403](0403-both-grfics-runs-were-captured-and-the-pair-disagrees-as-predicted.md),
  [ADR 0402](0402-the-grfics-capture-harness-is-declared-and-the-cyber-half-runs-on-the-bridge.md),
  [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md)

## Context

ADR 0404 retracted ADR 0402's co-tag claim. The corrected statement is that the cyber relay freezes
**all thirteen** registers of the block the HMI polls, not only the target. That was established on
the live stack — reading the relay twice for an identical block, and sampling four HMI points three
times for four constant values.

**It is not in the captured files.** `hmi_values.csv` records one tag, `Level`. So the correction is
true and the captures cannot show it, which ADR 0404 recorded as a gap rather than hiding. This
record closes the gap.

The first captures stay on disk under `data/grfics-dev/v1-<run>/` so ADR 0403's numbers remain
checkable against the files that produced them.

## What changes

**The HMI stream widens from one tag to thirteen.** ScadaLTS's seeded project has exactly thirteen
data points bound to the PLC's block, and they map one-to-one onto `%IW100`–`%IW112`:

| Point | Register | Tag | Scaling (`remote_io/modbus/*.py`) |
| --- | --- | --- | --- |
| `AValve` | 100 | `f1_valve_pos` | `/100`, valve percent |
| `AFlow` | 101 | `f1_flow` | `/1000` |
| `BValve` | 102 | `f2_valve_pos` | `/100`, valve percent |
| `BFlow` | 103 | `f2_flow` | `/500` |
| `PurgeValve` | 104 | `purge_valve_pos` | `/100`, valve percent |
| `PurgeFlow` | 105 | `purge_flow` | `/2000` |
| `ProductValve` | 106 | `product_valve_pos` | `/100`, valve percent |
| `ProductFlow` | 107 | `product_flow` | `/500` |
| `Pressure` | 108 | `pressure` | `/3200`, kPa |
| `Level` | 109 | `level` | `/100`, percent |
| `AComp` | 110 | `a_in_purge` | `*1`, mole fraction |
| `BComp` | 111 | `b_in_purge` | `*1`, mole fraction |
| `CComp` | 112 | `c_in_purge` | `*1`, mole fraction |

`hmi_values.csv` therefore gains a column per point, and every column has a matching `raw_<addr>`
column in the ICS-side register stream, so a reader can compare the operator's view against the
register **tag by tag** rather than only for the target.

`modbus.csv` gains every raw register of the block, not just level and pressure.

## Decision

1. **Both runs are captured again, once each, with the wider stream.** Same seeds, same event, same
   length, same clock discipline as ADR 0402. Nothing else about the harness changes.

2. **The first captures are kept, not deleted.** `data/grfics-dev/v1-<run>/` holds them, so ADR
   0403's table can still be reproduced from the exact files it was computed from. A recapture that
   overwrote them would make those numbers unverifiable, which is the failure mode this project
   exists to avoid.

3. **The new captures go to the same run directories as before**, `<cause>-frozen-tank_level-<seed>`,
   because they are the declared run and a reader looking for `97201` should find the current one.
   The v1 copy is the archive.

4. **The block-wide claim becomes checkable from the files.** Specifically, ADR 0404's statement that
   the cyber relay freezes all thirteen registers must be **visible in `hmi_values.csv` for `97206`**
   and **not** in `97201`, where eleven of the thirteen should keep moving. If the recapture does not
   show that, the correction is wrong and the files will say so.

5. **No new claim follows from the wider stream.** It makes an existing correction checkable; it does
   not license a detection statement, a rate, or a cross-zone claim. A capture is not a measurement
   (ADR 0402 Decision 7), the corpus is still one bridge with no router (ADR 0401), and v1 stays
   **8 of 12**.

## Consequences

- **A retraction becomes evidence.** ADR 0404 corrected a claim on live-stack measurement alone; this
  puts the same fact in the recorded files, where a reader can check it without a container.
- **The pair gets a second reason to exist.** With all thirteen tags recorded on both sides, the
  agreement tell is checkable per tag rather than for a single column, which is what the design doc's
  "PLC and HMI agree / disagree" actually means.
- **The archive grows to four run directories**, two current and two v1. That is deliberate and named
  in `data/grfics-dev/` rather than inferred.
- **Nothing is measured.** No rate, no recall, no confidence. v1 stays 8 of 12.

## What would reverse this

Overwriting `v1-*`; reporting the v1 numbers as if the v2 stream produced them or the reverse;
treating the wider stream as a new corpus or pooling it with anything; claiming detection,
cross-zone evidence, or a rate from either pass; or asserting the block-freeze fact after a recapture
that does not show it.
