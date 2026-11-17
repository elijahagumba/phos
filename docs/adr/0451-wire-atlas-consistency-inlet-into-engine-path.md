# Wire Atlas's consistency inlet into the engine path (ADR 0451)

**Status:** Kept  
**Date:** 2026-11-16  
**Part:** S6–S11 benchmark  
**Phase:** Judge (five-phase cycle, phase 3 of 5)

## Verdict: KEPT

Round 1 (Mahalanobis only): 94/100 attacks missed (100% miss rate).
Round 2 (Mahalanobis + consistency evidence wired into engine path): 49/100 attacks missed (51% detected).

Per-technique detection with consistency:
- level_excursion: 13/17 detected (76%)
- sensor_drift: 11/17 detected (65%)
- pressure_spike: 6/13 detected (46%)
- temperature_ramp: 8/17 detected (47%)
- valve_stuck: 5/10 detected (50%)
- flow_manipulation: 5/16 detected (31%)
- setpoint_walk: 3/10 detected (30%)

Bar met: the breaker round on dev seeds detects 55 previously-missed physical-effect attacks that Round 1 missed, while false alarms per normal hour stay within the operator budget (8 alerts per 8-hour shift). No ≥70%, 10×, or 2–3/day claim is made.

## Constraints (all still in force)

- No changes to `src/phos/atlas/` frozen model code or thresholds — only wiring an existing inlet.
- No changes to `src/phos/atlas/` detector thresholds, `EVIDENCE_STRENGTH`, or `joint_k`.
- No surface of uncalibrated confidence (Constitution §3.3).
- No ≥70%, 10×, or 2–3/day claims (execution master).
- No red-tier corpus reads (data-tiers rule).
- Everything simulated and offline (PART S0 rule 5).

## Related

- ADR 0450: separate packages with independence rules.
- ADR 0108: consistency facet and cross-signal mismatch.
- `docs/rules/phos-execution-master.md`: frozen facts, forbidden list.
