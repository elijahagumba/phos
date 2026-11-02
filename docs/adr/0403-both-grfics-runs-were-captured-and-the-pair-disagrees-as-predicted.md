# ADR 0403 — Both GRFICS runs were captured, and the pair disagrees in the direction the tell predicts

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS capture, the result. Runs `97201` and `97206` on `grfics-v3-bridge`
- **Supersedes:** nothing. ADR 0402's declaration is unchanged and this record judges it against the
  bar it set before the first run
- **Depends on:** [ADR 0402](0402-the-grfics-capture-harness-is-declared-and-the-cyber-half-runs-on-the-bridge.md),
  [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md),
  [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

ADR 0402 declared `scripts/grfics/capture.py` before it was written and named four facts it had
established by hand. This record reports **both declared runs**, each taken once, with nothing
re-run and nothing tuned after seeing the data.

The bar ADR 0402 set was not a detection number. It was this: the two runs must record **both sides
of the comparison at the same instant**, and the cyber run must be a real read-path capture or an
explicit refusal — never a passthrough presented as an attack.

**Credit:** GRFICSv3 is Fortiphyd's. Research use permitted by email; Fortiphyd asks for credit. No
GRFICS source is in this repository; the checkout stays at `data/grfics-source/`, git-ignored.

## The captures

| Run | Directory | Samples | Event |
| --- | --- | --- | --- |
| `97201` physical/frozen/tank_level | `data/grfics-dev/physical-frozen-tank_level-97201/` | 1776 | 600 s quiet, then 1200 s |
| `97206` cyber/frozen/tank_level | `data/grfics-dev/cyber-frozen-tank_level-97206/` | 1776 | 594 s quiet, then 1200 s |

Both carry the six declared streams. Every stream is stamped from the host wall clock, sampled on
each observation. Measured container offsets were **+33 to +77 ms**, well inside the one-second
sample interval, and `manifest.json` states the figure rather than assuming it away.

## What the pair shows

The tell is a comparison, so the result is stated as one.

| | `97201` physical | `97206` cyber |
| --- | --- | --- |
| `measured` spread over the event | **0.0000** (frozen at 43.9880) | **8.2942** (43.87 to 52.17) |
| `true` spread over the event | **15.1862** (43.99 to 59.18) | 8.2942 (43.87 to 52.17) |
| HMI minus engine-true, first event sample | **−0.0016** | **+6.6094** |
| HMI minus engine-true, last event sample | **+15.1874** | **+14.7884** |

The two runs are structurally opposite, which is what the experiment needs.

**`97201` is a fault at the source.** The engine's `measured` and the PLC register both froze at
43.9880 while `true` climbed to 59.18 — the sensor lied to everything downstream, exactly as
`apply_sensor_fault`'s `SENSOR_FAULT_FROZEN` case is written to (`TE_process.cc:65-68`). The HMI
followed the frozen value to within 0.0153 and its archive stopped advancing on **1185 of 1186**
event samples.

**`97206` is a fault in flight.** `measured` and `true` track each other the whole way, because the
PLC's own control loop was never touched: the attacker sat between the PLC and the HMI, not between
the engine and the PLC. The HMI held 58.7747 while the engine moved underneath it, and the gap
**widened monotonically** from +6.61 to +14.90 as the freeze receded from reality.

That monotonic widening is the strongest single observation in the pair. A stale screen would drift
by chance; a screen held at a fixed value while the plant moves can only diverge, and it did so on
every sample.

## Two honest limits, stated rather than smoothed

1. **`modbus.csv` is a sampled register view, not a frame log.** It records the 13-register block as
   read from the ICS side once per sample, with the replay observation per row, and names its own
   source in a `source` column. It is not a per-packet transcript. A full `tcpdump` capture was
   demonstrated working during the probe (a sidecar container sharing the HMI's network namespace)
   but is not what this column contains, and calling it one would be false. Measured during the
   capture: **0 of 1777** rows flagged as an exact block repeat on the ICS side, which is correct —
   the relay froze the HMI's view, and the ICS-side read is upstream of it.

2. **The cyber run's quiet phase is 594 s, not 600 s.** Arming the relay costs about six seconds
   before the first sample, so the elapsed-based event boundary landed at t=594.348 rather than
   600.0. The event still ran its full 1200 s and `events.json` records the actual boundaries. The
   sample count matches the physical run (1776 each).

**One asymmetry, restated.** ADR 0402 finding 6 said the physical run freezes **one tag** and the
cyber run freezes the **whole 13-register block**, because a narrower relay zeroes its co-tags. The
second half is true and the conclusion drawn from it was not: a 13-register relay freezes all
thirteen of those registers, not one. **[ADR 0404](0404-the-cyber-relay-freezes-all-thirteen-registers-and-the-pair-is-more-symmetric.md)
corrects it.** Both runs freeze the value the HMI sees for the target; they differ in **where the
freeze enters**. In the physical run it enters at the engine's `measured`, so `measured`, the PLC
register and the HMI all hold one value and agree — both wrong, together. In the cyber run the engine
and the PLC register keep moving and only the HMI's view is frozen, so they disagree. That difference
is the tell, and it is exactly what the table above shows: `measured` spread **0.0000** against
**8.2942**. **The numbers in this record never depended on the wrong claim, and are unchanged.** One
collateral is stated in ADR 0404: `hmi_values.csv` records only `Level`, so the block-wide behaviour
of the HMI in the cyber run is not evidenced by the captured files, only by the live stack.

## Decision

1. **Both runs are kept as captures.** Neither is a refusal, and both are reproducible from the
   command and pin recorded in their `manifest.json`.

2. **The cyber half is real, and the bridge is why it was possible.** ADR 0402's reversal of the
   work order's premise is now backed by a full-length capture rather than a probe: the HMI's ARP
   entry for the PLC pointed at the attacker, the connection terminated at the relay
   (`192.168.95.6:502` established to `192.168.95.107`), and the HMI followed the relay's value
   across a 20-minute event.

3. **Nothing is measured, and no claim is made about detection.** A capture is not a score. No
   recall, rate, accuracy or confidence is computed here or derivable from these files alone.
   `eval_runs/log.jsonl` is not appended, no frozen row is read, and **v1 stays 8 of 12**.

4. **No cross-zone claim.** This corpus is one Docker bridge. There is no router, so no firewall,
   Suricata or arpmon evidence exists and none is claimed. The design doc's exercise leans on those
   sensors; this corpus can pose the PLC-vs-HMI tell and nothing else (ADR 0401).

5. **The stack was returned to quiet.** The relay, the ARP spoof and the redirect are torn down and
   the HMI's ARP entry healed back to the PLC's real MAC (`aa:a5:63:18:3d:55`), verified after both
   runs.

6. **It is an emulated plant.** Any later result from these files is a diagnosis, not proof (R4,
   ADR 0143), and it does not advance P1, which remains a blocked human conversation.

## Consequences

- **The tank-level pair can now be posed**, which is what the corpus was registered for a fortnight
  ago. Before this session `data/grfics-dev/` was empty and the cyber half looked impossible on this
  host.
- **The pair is usable only with its asymmetry attached.** A reader who treats the two runs as the
  same intervention measured twice will draw the wrong conclusion, because one freezes a tag at the
  source and the other freezes a block in flight.
- **The remaining eight development runs are still undriven**, deliberately. They would widen the
  corpus; they would not make the pair distinguishable, which is the question.
- **`grfics-v3` remains ungenerated** and still needs a Linux host with macvlan. Nothing here
  narrows that gap or may be reported as its result.

## What would reverse this

Reporting either run as `grfics-v3`; pooling the two corpora; calling a capture a measurement or
quoting a rate from it; presenting the physical and cyber runs as the same mechanism; claiming
cross-zone, firewall or IDS evidence from this corpus; describing `modbus.csv` as a packet capture
when it is a sampled register view; driving a `973xx` seed or any of the other eight development
runs without a new declaration; or committing GRFICS source, a payload, or any file under
`data/grfics-dev/`.
