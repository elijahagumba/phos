# atlas-walk-consistency

ADR 0314. Scored after commit `5fd281d`. Challenger bytes matched the declaration:
`src/phos/atlas/walk_consistency.py`
`396b1fa08414ef5bd279dd0ec60e9d1e6b22637cec62ba91003f020edba9f991`,
`scripts/lane_daily_walk.py`
`5cbd7d50bd5791aa472296db15e96e06f9405b8ddbb147b518fa60c91470b595`.
The path is not mixed in. Champion bytes were unchanged:
`consistency.py`
`71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`,
`command_consistency.py`
`87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`.
`eval_runs/log.jsonl` was not appended. Held-out was not opened. The corpus was
not regenerated. `eval_runs/build/lane-daily/day1-walk.md` was not replaced.

The command's log line was `walk column divisor 2.0000 from 3 peaks`.

```
result: atlas-walk-consistency
budget alerts per shift: 8
walk divisor: 2.000000
walk events: 9
walk misses frozen: 1
walk misses new: 1
walk false alerts frozen: 19
walk false alerts new: 19
walk duration_s: 57600.000000
walk false alerts per hour frozen: 1.187500
walk false alerts per hour new: 1.187500
walk median delay s frozen: 0.950000
walk median delay s new: 0.950000
walk later than champion: 0
```

The first bar is not met. The column is not a kept detector. This score is not run again.
