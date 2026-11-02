# The GRFICS agreement tell on the captured pair (ADR 0407)

**This is a diagnosis on an emulated plant.** It is not a detection result: no recall,
rate, accuracy, confidence or budget appears here, and none may be quoted from it
(ADR 0407 Decision 3, R4, ADR 0143).

Reproduce with: `python scripts/grfics/agreement.py`

Corpus: `grfics-v3-bridge`. Not `grfics-v3`, never pooled with it (ADR 0401).

## Verdict

**Kept.** The tell is visible on this pair: under the physical fault the operator's view tracked the PLC, and under the read-path attack it did not.

Analysis window: the event phase past the 10-sample transition,
matched sample by sample between `hmi_values.csv` and `modbus.csv` on their shared
clock.

A tag is **live on the ICS side** when its register held more than one distinct value.
Tags that were not live carry no evidence either way and are excluded from the bars, with
the reason shown.

## 97201 physical/frozen/tank_level

`data/grfics-dev/physical-frozen-tank_level-97201/`

| tag | reg | samples | distinct regs | HMI changes | live | tracked |
| --- | --- | --- | --- | --- | --- | --- |
| `AValve` | 100 | 1180 | 1 | 0 | no | no |
| `AFlow` | 101 | 1180 | 1 | 0 | no | no |
| `BValve` | 102 | 1180 | 1 | 0 | no | no |
| `BFlow` | 103 | 1180 | 1 | 0 | no | no |
| `PurgeValve` | 104 | 1180 | 204 | 479 | yes | yes |
| `PurgeFlow` | 105 | 1180 | 380 | 479 | yes | yes |
| `ProductValve` | 106 | 1180 | 142 | 72 | yes | yes |
| `ProductFlow` | 107 | 1180 | 196 | 584 | yes | yes |
| `Pressure` | 108 | 1180 | 197 | 593 | yes | yes |
| `Level` | 109 | 1180 | 1 | 0 | no | no |
| `AComp` | 110 | 1180 | 101 | 100 | yes | yes |
| `BComp` | 111 | 1180 | 1165 | 594 | yes | yes |
| `CComp` | 112 | 1180 | 1158 | 594 | yes | yes |

## 97206 cyber/frozen/tank_level

`data/grfics-dev/cyber-frozen-tank_level-97206/`

| tag | reg | samples | distinct regs | HMI changes | live | tracked |
| --- | --- | --- | --- | --- | --- | --- |
| `AValve` | 100 | 1174 | 1 | 0 | no | no |
| `AFlow` | 101 | 1174 | 1 | 0 | no | no |
| `BValve` | 102 | 1174 | 1 | 0 | no | no |
| `BFlow` | 103 | 1174 | 1 | 0 | no | no |
| `PurgeValve` | 104 | 1174 | 214 | 0 | yes | no |
| `PurgeFlow` | 105 | 1174 | 401 | 0 | yes | no |
| `ProductValve` | 106 | 1174 | 1070 | 0 | yes | no |
| `ProductFlow` | 107 | 1174 | 1106 | 0 | yes | no |
| `Pressure` | 108 | 1174 | 204 | 0 | yes | no |
| `Level` | 109 | 1174 | 181 | 0 | yes | no |
| `AComp` | 110 | 1174 | 1 | 0 | no | no |
| `BComp` | 111 | 1174 | 1 | 0 | no | no |
| `CComp` | 112 | 1174 | 1 | 0 | no | no |

## What this does not say

- It does not say Atlas detects anything. Nothing here is scored.
- It does not describe a real plant. The pair is an emulated process in a simulator.
- It does not report cross-zone evidence. The corpus is one Docker bridge with no
  router, so there is no firewall, Suricata or arpmon evidence (ADR 0401).
- It does not generalise to other faults, other tags or other seeds. Two runs were
  captured and two were analysed.

## The one row worth reading twice

`Level` is **not live on the ICS side in the physical run** (1 distinct register
value) but **is live in the cyber run** (181 distinct values), and its HMI froze in
both. That is not an inconsistency: it is the physical case doing exactly what the
design doc describes. The physical fault froze the sensor at the source, so the
register itself stopped moving and everyone downstream was fooled together, including
this analysis, which can therefore say nothing about it from the register alone. Under
the cyber attack the register kept moving (181 distinct values) while the operator's
view held one value for 1174 samples, which is the disagreement, recorded.

The sharpest single instance of agreement is therefore not `Level` in the physical run
but `Pressure` in it: 197 distinct register values, and an HMI that tracked them.

