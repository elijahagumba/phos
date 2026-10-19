# ADR 0166 — Kelmarsh operating modes are declared states

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane B, operating-mode awareness
- **Depends on:** [ADR 0165](0165-kelmarsh-round-2-trains-on-2018.md)

## Context

One pooled baseline treats idle, pitched-out, and generating rows as one
normal. The aim is fewer unexplained alerts, and a higher share explained by
the turbine's own status log, without editing `atlas-v1-consistency`.

The five signals do not carry a mode column. Modes are read off the same
signals, with cuts declared here, not fitted on 2019–2022.

## Decision

`phos.eval.kelmarsh_modes` labels each kept row, in this order:

1. **Idle** when power is at most 0 kW and rotor speed is below 1 RPM.
2. **Curtailment** when the row is not idle, pitch is at least 5 degrees,
   wind is at least 6 m/s, and power is below 1800 kW.
3. **Startup** on the first three non-idle rows after an idle row.
4. **Shutdown** on the last three non-idle rows before an idle row, unless
   that row is already startup.
5. **Running** otherwise.

A mode is scored by calling the frozen `detect` on contiguous runs of that
mode, one fit per turbine per mode. Runs of one row are skipped, because lag
1 needs a neighbour. A mode with no trainable run is silent on that mode. The
pooled 2018 fit stays the comparison, under its own name.

A change is kept only when unexplained alerts per shift fall and the explained
share does not fall. Losing either is a revert. The synthetic closure harness
is not part of this score and is not edited.

## Consequences

Startup and shutdown are three samples by declaration. A different length
would be a different configuration. The counts are not a detection claim.
