# Unbooked valve commands on the development plant

Written by `scripts/lane_unbooked_command.py`.

A break is a valve-mode write whose value is not release and whose tag and time no work order covers. The work order asset `tank_output_valve` covers `tank_output_valve_mode`. Release writes are not breaks.

The digest of `src/phos/atlas/declared_law.py` is `f6b2c3c435103b5e789deac0a78c0e97c8642631badd38f89f7a9b18d5755271`.

## Per run

| run | mimic | maintenance | setpoint | release | replay | rogue | unlabelled |
|---|---|---|---|---|---|---|---|
| `mixed-96011` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96012` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96013` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96014` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96015` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96016` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96017` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96018` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96019` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `mixed-96020` | 1/1 | 0 | 0 | 0 | 1/1 | 1/1 | 0 |
| `normal-96001` | 0/0 | 0 | 0 | 0 | 0/0 | 0/0 | 0 |
| `normal-96002` | 0/0 | 0 | 0 | 0 | 0/0 | 0/0 | 0 |
| `normal-96003` | 0/0 | 0 | 0 | 0 | 0/0 | 0/0 | 0 |

## The metrics

| metric | value |
|---|---|
| `mimic_catch_rate` | 1 (10/10) |
| `maintenance_breaks` | 0 |
| `setpoint_breaks` | 0 |
| `release_breaks` | 0 |

Replay and rogue command are reported beside the bars. Both force a valve with no work order, so a break there is the law doing what it says. They are not part of the question, which is whether mimic maintenance and genuine maintenance come apart.

Breaks in total: 30. Breaks outside every labelled window: 0.
