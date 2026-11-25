# A level that stays still while the tank drains

Written by `scripts/lane_still_drain.py`.

A break is a drain of two or more samples whose level never changes. The outlet is open, the inlet is shut, both modes are release, and the flow is the plant's own outlet rate. A drain whose level changes is silence.

The digest of `src/phos/atlas/declared_law.py` is `0e715c52dd8cbf286095a823fe4b5ee23a1aa76f6e60a825b3e304541f02b604`.

## Per run

| run | quiet breaks | freezes caught | maintenance | setpoint | no drain |
|---|---|---|---|---|---|
| `mixed-96011` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96012` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96013` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96014` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96015` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96016` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96017` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96018` | 0 | 0/0 | 0 | 0 | 1 |
| `mixed-96019` | 0 | 1/1 | 0 | 0 | 0 |
| `mixed-96020` | 0 | 1/1 | 0 | 0 | 0 |
| `normal-96001` | 0 | 0/0 | 0 | 0 | 0 |
| `normal-96002` | 0 | 0/0 | 0 | 0 | 0 |
| `normal-96003` | 0 | 0/0 | 0 | 0 | 0 |

## The metrics

| metric | value |
|---|---|
| `quiet_breaks` | 0 |
| `freeze_catch_rate` | 1 (9/9) |
| `maintenance_breaks` | 0 |
| `setpoint_breaks` | 0 |

A freeze that never opens the outlet has no drain, so the law is not stated there. Those freezes are counted beside the bars: 1.
