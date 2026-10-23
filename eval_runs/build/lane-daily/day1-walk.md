# atlas-daily:day1-walk

ADR 0301. Scored after generation of `data/phos-icssim-dev4-walk`, once ADR 0309 and `eval_runs/build/lane-daily/day1-champions.md` were in HEAD. Champion bytes matched the declaration: `consistency.py` `71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`, `command_consistency.py` `87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`. `eval_runs/log.jsonl` was not appended. Held-out was not generated.

`python` is not on PATH. Generation was `python3 -u scripts/icssim/generate_corpus.py development4-walk`. The shell then failed assigning `status`, which zsh keeps read-only, after that process had returned. All 11 manifests exist. The scorer in HEAD before commit `61d03ec` opened `mixed*` and `in_range-*` only. The walk runs are `subfloor-*`. That selection was extended in `61d03ec` before this score. No alerts were computed before it. The champion files were not edited. The score command was then run once and exited 0.

Train: `normal-96801`, `normal-96802`, `normal-96803`. Test: `subfloor-96811` through `subfloor-96818`.

```
label    kind                  frozen  lane1  lane2   of  what caught it
attack   subfloor_walk              8      8      8    9  signal
benign   maintenance                3      3      3   14  signal
benign   setpoint                   3      3      3    9  signal

attacks caught, frozen: 8 of 9
attacks caught, lane 1: 8 of 9
attacks caught, lane 2: 8 of 9
benign drawing an alert, frozen: 6 of 23
benign drawing an alert, lane 1: 6 of 23
benign drawing an alert, lane 2: 6 of 23

day1 subfloor_walk events: 9
day1 subfloor_walk misses frozen: 1
day1 subfloor_walk misses lane1: 1
day1 M_champion: 1 frozen
day1 false alerts frozen: 19
day1 false alerts lane1: 19
day1 duration_s: 57600.000000
day1 false alerts per hour frozen: 1.187500
day1 false alerts per hour lane1: 1.187500
day1 median delay s frozen: 0.950000
day1 median delay s lane1: 0.950000
```

`M_v1` is 1. `M_cmd` is 1. `M_champion` is 1, and the tie on misses and on the false-alert rate keeps the frozen detector. Breadth is printed and is not a champion. What caught the walks that were caught is `signal`.

This score has no pass bar. It is the denominator. `M_champion` is 1, so the walk detector specified in ADR 0301 may be built. It is not built here. This score is not run again.
