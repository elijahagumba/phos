# atlas-daily:joint-champions

ADR 0316, declared 23 October 2026 and scored once on 9 November 2026, seventeen days later. E-0003
on Q-0003 is the machine-readable declaration of the same thing, committed at `8448518` before the
run, because the gate reads HEAD and the October record is prose. Champion bytes matched the
declaration on the day of the score: `consistency.py`
`71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`, `command_consistency.py`
`87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`. `eval_runs/log.jsonl` was not
appended. `phos-icssim-heldout5` was not generated and was not opened. The walk score was not
rerun and no divisor was retuned.

Generation used `python3` because `python` is not on this machine's path. The generator uses only
the standard library and spawns the pinned ICSSim virtual environment for the simulation itself, so
the interpreter that reads the argument list is not part of the measurement. Nothing else in the
declared command changed.

The denominator was computed from committed code before any directory was opened, by drawing
`schedule("joint", seed)` for the eight declared seeds: 2, 3, 4, 3, 2, 2, 2, 2, which is twenty.
The corpus as generated holds exactly that, per run and in total, so bar b1 is met by a count that
was fixed in advance rather than read off the result.

Train: `normal-98001`, `normal-98002`, `normal-98003`, copied byte-identical from the main
checkout and verified with `diff -r` before use. Test: `joint-98011` through `joint-98018`.

    fitted on 3 normal run(s), 43203 rows, 13 signals, sample period 1.0s
    breadth divisor 4.0090
    command path: writers=['operator'] readers=['operator', 'plc1', 'plc2'] divisors=(1.0, 1.0)
    joint-98011: frozen 8 alerts, lane1 8 alerts
    joint-98012: frozen 3 alerts, lane1 3 alerts
    joint-98013: frozen 8 alerts, lane1 8 alerts
    joint-98014: frozen 7 alerts, lane1 7 alerts
    joint-98015: frozen 5 alerts, lane1 5 alerts
    joint-98016: frozen 6 alerts, lane1 6 alerts
    joint-98017: frozen 8 alerts, lane1 8 alerts
    joint-98018: frozen 8 alerts, lane1 8 alerts

    label    kind                  frozen  lane1  lane2   of  what caught it
    attack   joint_command             15     15     15   20  signal
    benign   maintenance                0      0      0   10  
    benign   setpoint                   1      1      1   18  signal

    attacks caught, frozen: 15 of 20
    attacks caught, lane 1: 15 of 20
    attacks caught, lane 2: 15 of 20
    benign drawing an alert, frozen: 1 of 28
    benign drawing an alert, lane 1: 1 of 28
    benign drawing an alert, lane 2: 1 of 28

    day1 joint_command events: 20
    day1 joint_command misses frozen: 5
    day1 joint_command misses lane1: 5
    day1 M_champion: 5 frozen
    day1 false alerts frozen: 38
    day1 false alerts lane1: 38
    day1 duration_s: 115200.000000
    day1 false alerts per hour frozen: 1.187500
    day1 false alerts per hour lane1: 1.187500
    day1 median delay s frozen: 0.500000
    day1 median delay s lane1: 0.500000

## What it says

`M_champion` is **5 of 20**, so the detector ADR 0316 specified **may be built**, under its own
record and as specified there. The gate that record set is open. Nothing is built here.

The two champions are identical on every number printed: 5 misses each, 38 false alerts each,
1.187500 per hour each, median delay 0.500000 s each. A tie on misses and a tie on false alerts
keeps the frozen detector by ADR 0316's own rule, so the champion is `frozen`. The identity is not
a coincidence and it is the mechanism E-0003 predicted: lane 1 adds `unknown_writer` and
`unknown_reader` to the frozen engine, this class writes from the operator console that already
writes in training, and it reads nothing out of the ordinary, so neither component has anything to
fire on and lane 1 reduces exactly to the engine it extends. The breadth column also matches and is
not a champion.

The false-alert rate, 1.187500 per hour, is the same number the walk column recorded in
`day1-sequential-walk.md`: 38 alerts over 32 hours here, 19 over 16 hours there. Both are the
budgeted alert load of this generator's runs rather than a property of either class, and neither
figure may be quoted as a detection result.

One benign `setpoint` event of eighteen drew an alert, and all ten `maintenance` events were quiet.

## What it does not say

This is a denominator, not a detection claim. 15 of 20 is not a recall figure for Atlas, on this
plant or any other: the corpus is synthetic, one plant, Modbus/TCP only, and ADR 0143 stands, so no
claim here may say the plant map improves detection on real plant data. The miss count is not
evidence for A2, A3 or A7. v1 stays 8 of 12. P1 stays the blocked human conversation.
