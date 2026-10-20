# S2 — identity features, not scored

Lane A, 2026-10-17. ADR 0146.

## What was built

`phos.sentiel.named_counterparties` emits six features beside the existing 34.
`phos.sentiel.identity` is the Clock B layer scorer and was not edited:

- declared hosts, and which of those hosts are new for that user
- declared email destinations, and which of those are new
- declared machines, and which of those are new

The register is supplied by the caller and ships empty. Matched names are stored on
the observation. A new-name count stays silent until the user's own history meets the
same eight-window bar the 34 already use.

The 34 were not edited. `AggregationPolicy()` still has empty weights. Bet 001's three
formulas were not edited. No register was filled from a labelled insider.

## What the tests check

Renaming every host, machine and recipient leaves the 34-vector unchanged. The same
rename changes an identity count when the register is not renamed with it. Swapping
two declared names keeps the count and changes the recorded name. Equal magnitudes on
the 34 score equally under `linear-excess` and `gaussian-tail`. `family-max`'s total
does not depend on input order. Computing the identity stream does not move a paired
peer featurisation of the same events.

## What was not scored

CERT r3.1 is not on disk (ADR 0145). r4.2 is not on disk. No identity feature was
scored on either release.

## Scorecard

| Field | This run |
| --- | --- |
| catches_within_budget | not measured |
| margin_over_best_simple_rival | not measured |
| margin_over_chance | not measured |
| falsified_sensor_passes | not applicable |
| naming_right | not applicable |
| naming_wrong | not applicable |
| reconstruction_error | not applicable |
| maintenance_closures | not applicable |
| calibration | not measured |
| false_alerts_per_shift | not measured |
| runtime | not measured |

## Bar

Implemented and tested. Not scored. The S2 pass bar, which requires a score on CERT
r3.1 and on a larger release, is not met.
