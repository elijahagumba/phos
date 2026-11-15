# atlas-sequential-consistency

GENESIS E-0001, serving Q-0001. Scored after commit `96b0553`, which is the commit that put
`docs/genesis/experiments/E-0001.json` in history. The command was the one the declaration names,
run once:

```
uv run python scripts/lane_sequential_walk.py --corpus data/phos-icssim-dev4-walk
```

Challenger `src/phos/atlas/sequential_consistency.py`
`495a5bd5933d4b2d78d3fdf3ef0cdd1e7f695754547c01d5aee9689bb3a3b971`. The corpus was not regenerated;
it is the directory ADR 0313 generated and scored. `eval_runs/log.jsonl` was not appended. Held-out
was not opened. The champion command (`lane_e_icssim_baseline.py`) was **not** re-run on this
corpus: ADR 0313's `atlas-daily:day1-walk` is spent, and its 1.187500 per hour is read from the
committed record rather than recomputed.

Log:

```
sequential column longest attack-free run 1 samples
tank_level_max: longest attack-free run 1 samples
attack-free range of tank_level_max: [6.600000, 7.240000]
```

Output:

```
result: atlas-sequential-consistency
walk events: 9
walk misses sequential: 0
walk samples outside range: 2331
walk min outside range: 258
walk duration_s: 57600.000000
walk false alerts sequential: 0
walk false alerts per hour sequential: 0.000000
walk false alerts per hour champion committed: 1.187500
walk alerts per shift max: 4
walk budget per shift: 8
walk denominator committed: 9

run                    start       end  longest  outside  caught
subfloor-96811     1767228522.8 1767229242.8      302      259  yes
subfloor-96812     1767228286.1 1767229006.1       55      259  yes
subfloor-96813     1767229385.0 1767230105.0       19      260  yes
subfloor-96814     1767228251.4 1767228971.4      720      259  yes
subfloor-96815     1767227801.2 1767228521.2      720      259  yes
subfloor-96815     1767231384.3 1767232104.3      720      259  yes
subfloor-96816     1767227152.0 1767227872.0       13      258  yes
subfloor-96817     1767228752.2 1767229472.2      720      259  yes
subfloor-96818     1767230641.7 1767231361.7      720      259  yes
```

## The denominator

ADR 0313 reports nine `subfloor_walk` events and ADR 0315 reports missing "the same 1 of 9", but no
committed file names the nine per walk. They were reconstructed here from committed code rather than
from a report, because `schedule()` in `scripts/icssim/phos_icssim.py` is a pure function of the
seed and the `subfloor` scenario is unchanged since the generation commit `1c448d7`:

```
subfloor-96811: maintenance, subfloor_walk(2922.8-3642.8), setpoint, maintenance
subfloor-96812: setpoint, subfloor_walk(2686.1-3406.1), maintenance, maintenance
subfloor-96813: maintenance, setpoint, subfloor_walk(3785.0-4505.0), maintenance
subfloor-96814: maintenance, setpoint, subfloor_walk(2651.4-3371.4), maintenance
subfloor-96815: setpoint, subfloor_walk(2201.2-2921.2), maintenance, subfloor_walk(5784.3-6504.3)
subfloor-96816: subfloor_walk(1552.0-2272.0), maintenance, setpoint, maintenance
subfloor-96817: subfloor_walk(3152.2-3872.2), setpoint, maintenance, setpoint
subfloor-96818: setpoint, maintenance, subfloor_walk(5041.7-5761.7), maintenance
```

**Nine walks over eight runs**: `subfloor-96815` holds two. The scenario draws four events from three
kinds, so a run can hold more than one walk — which is why the corpus holds eight episode directories
and nine events. The reconstruction matches the `events.json` written by generation, and it matches
the nine the report counted.

What the record still cannot say is **which** of the nine the champion missed. No committed file names
it, `day1-walk.md` and `day1-walk-detector.md` print only aggregate counts, and the champion score may
not be re-run. That gap is not closed here and is not closed by this report.

## What the numbers say

The sequential column missed **0 of 9** and raised **0 false alerts** in 57600 s, against the
champion's committed 1 of 9 and 1.187500 per hour. Its learned threshold was **1 sample**: the
longest run on `tank_level_max` that three attack-free runs produced was a single legitimate setpoint
write.

The order-blind half found **2331** samples outside the range training recorded, and **no walk had
fewer than 258**. The attack-free range was `[6.600000, 7.240000]`; the walk writes from 6.5 to
7.498611.

## Two caveats that belong beside those numbers

**The zero false-alert count is structural, not earned.** In this generator a `setpoint` event is one
write (`DURATIONS["setpoint"] = (1, 1)`, one `send`), so the register changes once and holds — a run of
1, which the strict `>` at the learned threshold of 1 does not admit. On `tank_level_max` the only
event kind that moves the value continuously is `subfloor_walk`. So zero false alerts is close to a
property of the generator, and it is not evidence that the column is quiet on a real plant.

**The order-blind count is nearly guaranteed, and was predictable before the run.** The walk spans the
whole declared band `SETPOINT_BAND = (6.5, 7.5)` by construction, and three normal runs contain six
setpoint draws, so the empirical range is narrower than the walk's own endpoints. A walk therefore
leaves the training range whether or not any detector could see it. This report states the count
because the declaration asked for it; the count is weak evidence and is not offered as more.

## What this is not

A simulated diagnosis (ADR 0073). Not a detection claim, not a daily-leap claim, not a field rate.
`M_champion` stays 1 and the champion walk score is not replaced. Held-out stays unopened. v1 stays
8 of 12. No confidence is calibrated or surfaced.
