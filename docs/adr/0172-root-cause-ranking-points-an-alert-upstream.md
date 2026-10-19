# ADR 0172 — Root-cause ranking points an alert at the signal its deviation started from

- **Status:** Accepted (written before the module was built; development numbers below)
- **Date:** 2026-10-18
- **PART:** Build lane E, capability "root-cause ranking"
- **Depends on:** [ADR 0170](0170-every-control-coupling-is-a-loop-and-bars-only-its-outputs.md),
  [ADR 0161](0161-the-plant-map-names-the-champions-alerts.md)

## Context

`atlas-v1-consistency` raises an alert on the signal whose consistency broke. On a run where one
sensor is held false, most alerts land on other signals: the falsified value feeds models
downstream, and those models break too. Lane D's and lane E's explainers name a lying instrument
only at alerts on the falsified column. Every other alert's explanation names its own column.

On development seeds 97001–97020, every declared sensor held at 90% of its span (the naming guard
survey), the champion raised 1,961 alerts inside the hold window. 575 were on the falsified
column. An explanation that names the alerting signal points at the falsified sensor 29.3% of the
time.

## Decision

1. `phos.atlas.root_cause.rank_root_causes` ranks the alerting signal and every signal upstream
   of it in the fitted plant map (every ancestor through the map's learned links, with its graph
   distance). It does not change which cells are alerts, the naming verdict, or any score.
2. Each candidate gets one of three tiers at the alert row:
   - **origin:** its own model is out of band and every modelled driver of it is in band, so the
     departure starts at it;
   - **inherited:** its own model is out of band but a driver is too;
   - **in band:** its own model is in band.
   Candidates are ordered by tier, then by their own out-of-band score (larger first), then by
   graph distance, then by column order. The first is the root cause the explanation quotes; the
   whole list is kept, so the ranking can be reconstructed.
3. Depth is not a knob. Every ancestor is a candidate (development loops at depth 1, 2 and 3
   scored 821, 1,067 and 1,120 of 1,961; every ancestor scored 1,226).
4. The plant map is the lane E explainer's (ADR 0170), fitted on the champion's training seed.
   Nothing here edits the champion, the map defaults, priors, `EVIDENCE_STRENGTH` or templates.

## Development result

Root cause first on the falsified sensor: 1,226 of 1,961 window alerts (62.5%), against 575
(29.3%) when the explanation names the alerting signal. Within the first two: 1,415 (72.2%).
On the 1,386 alerts that sit on another signal, 726 now point at the falsified sensor, against 0.
The cost: 75 of the 575 alerts on the falsified column now rank an ancestor first.

## Consequences

An explanation carries a ranked upstream list beside the naming verdict. It is synthetic
diagnosis on the three PHOS plants. It is not a claim that the ranking finds the cause on a real
plant (ADR 0143), and the rank is not a probability.

## What would reverse this

Choosing tiers or depth on held-back seeds. Letting the ranking add, drop or reorder an alert.
