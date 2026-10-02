# Fixture ablation ladder -- not a public row

FIXTURE_NOT_A_PUBLIC_ROW. Seed 11 on this split remains a freeze, not a search knob.
Public HAI Gaussian stays **8389.81** FP/normal hour (CITED).
Public HAI Mahalanobis stays **646.58** FP/normal hour (CITED).
Do not copy the false-positive column below onto those names.

| Profile | Fixture FP | Fixture TP | Public log name | Overwrites public log |
|---|---|---|---|---|
| gaussian | 0 | 1 | - | false |
| ewma | 0 | 1 | - | false |
| mahalanobis | 2 | 173 | - | false |
| mahalanobis+topology | 2 | 173 | - | false |
| mahalanobis+topology+declared_phase | 2 | 173 | - | false |
| mahalanobis+topology+declared_phase+grouping | 1 | 173 | - | false |
| mahalanobis+topology+declared_phase+grouping+command_evidence | 1 | 173 | - | false |
| mahalanobis+topology+declared_phase+grouping+command_evidence+reachability | 1 | 173 | - | false |

Later rungs (topology, declared phase, grouping, command evidence, reachability) are names on this fixture. They are not new HAI measurements.
