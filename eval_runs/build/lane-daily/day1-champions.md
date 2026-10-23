# atlas-daily:day1-champions

ADR 0301. Scored after generation of `data/phos-icssim-dev4`. Champion bytes matched the declaration: `consistency.py` `71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`, `command_consistency.py` `87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`. `eval_runs/log.jsonl` was not appended. Held-out and the walk corpus were not generated.

The first invocation of the score command exited 1. The script opened only `mixed*` directories, and these attack runs are `in_range-*`. No alerts were computed. The glob was extended to `in_range-*` and the same command was run again. The champion files were not edited.

Train: `normal-96601`, `normal-96602`, `normal-96603`. Test: `in_range-96611` through `in_range-96618`.

```
label    kind                  frozen  lane1  lane2   of  what caught it
attack   in_range_command          13     13     13   13  signal
benign   maintenance                4      4      4   17  signal
benign   setpoint                   0      0      0   18

attacks caught, frozen: 13 of 13
attacks caught, lane 1: 13 of 13
attacks caught, lane 2: 13 of 13
benign drawing an alert, frozen: 4 of 35
benign drawing an alert, lane 1: 4 of 35
benign drawing an alert, lane 2: 4 of 35

day1 in_range_command events: 13
day1 in_range_command misses frozen: 0
day1 in_range_command misses lane1: 0
day1 M_champion: 0 frozen
day1 false alerts frozen: 11
day1 false alerts lane1: 11
day1 duration_s: 115200.000000
day1 false alerts per hour frozen: 0.343750
day1 false alerts per hour lane1: 0.343750
day1 median delay s frozen: 0.500000
day1 median delay s lane1: 0.500000
```

`M_v1` is 0. `M_cmd` is 0. `M_champion` is 0, and the tie on misses and on the false-alert rate keeps the frozen detector. Breadth is printed and is not a champion. What caught the attacks is `signal`.

This score has no pass bar. It is the denominator. `M_champion` is 0, so `atlas-inrange-consistency` is not built. The walk corpus is the next legal command and was not generated here.
