# The detectors that beat the frozen engine at catching, and were still refused.

*Two detectors caught more attacks than the engine PHOS ships, and neither was adopted. This paper is the measurement and the reason: one arrived later, and the other was quieter and blinder, because part of the shipped engine's detection turns out to be a side effect of its own misfit.*

[The record](../README.md) · [Front page](../../README.md)

Build brief E asked for a stronger engine and closed without one (ADR 0297). Two of the lanes are in the tree as separate modules. They do not edit `src/phos/atlas/consistency.py`. They import its constants and its episode machinery. Both lost the bar they were given. The code remains so the loss can be re-read. It is not a champion, and it is not a queue of work waiting to be turned back on. Reserved ADR numbers 0277–0284 stay unwritten.

The scores below are on `phos-icssim-dev2`, a plant this repository generated. ADR 0073 and ADR 0143: a simulated score is a diagnosis. It is not a field rate and it is not a result about a real plant. v1 stays 8 of 12. Held-out for these lanes was not opened.

## Lane 3: a leaky sum that wins the slot and arrives late

`src/phos/atlas/drift_consistency.py`, result name `atlas-drift-consistency`. The frozen detector opens an episode only where a score crosses `THRESHOLD` (1.0) at a single sample. A reading that is mildly wrong for an hour never crosses. The detrender makes that worse on purpose. Scores are detrended against their own median over `DETREND_WINDOW` (3600 samples), which is there so a slow drift stops alerting. For a ramp, the trailing median follows the ramp, and what remains is a small offset.

The accumulator, one column per signal, on that signal's own frozen score:

```text
A[i, j] = max(0, retention * A[i - 1, j] + score[i, j] - slack[j])
```

`slack[j]` is the `SLACK_QUANTILE = 0.99` quantile of that signal's attack-free scores. Below it, nothing accumulates. `retention_for` sets the leak so the memory matches `detrend_window`. The clamp at zero is Page's: being quieter than normal does not earn credit. Each column is then divided by the third-largest attack-free episode peak (`CALIBRATION_RANK = 3`), the same rule `fit` already uses, so `THRESHOLD` means the same thing on the new columns.

The augmented matrix goes through the unchanged `events` and `budget_alerts`. The new columns compete for the same eight alerts. They are not added on top.

On that corpus the accumulator caught 53 of 70 attacks against the frozen engine's 32, lost nothing the frozen engine caught at the caps that matter, and took `liar_freeze` from 1 of 10 to 10 of 10. Median detection delay was worse at every setting of its one free parameter, `CONTRIBUTION_CAP`. ADR 0286 prints the dial:

| Cap | Attacks caught (frozen 32) | Attacks both catch | Paired median delay |
| ---: | ---: | ---: | --- |
| 1.05 | 39 | 31 | 1 s → 2 s |
| 1.25 | 42 | 30 | 1 s → 3 s |
| 1.50 | 42 | 30 | 1 s → 4 s |
| 2.00, 5.00, 20.00 | 53 | 32 | 1 s → 5 s |

The mechanism is in `events`, not in the sum. An event's alert starts at the strongest member's peak and moves earlier only to a member that reaches `level = min(best_peak, max(ONSET_LEVEL, ONSET_FRACTION * best_peak))`. `ONSET_LEVEL` is 2.0. `ONSET_FRACTION` is 0.1. A member whose own peak is below `level` cannot place the alert. Alone, a weak episode qualifies against itself. The moment a louder column joins the group, the weak episode loses the right to place anything.

On a full budget those two facts cannot be separated. A column must score high to win one of the eight slots. Scoring high is what makes it the group's `best`, which disqualifies the modest per-second evidence that would have fired earlier. Caps at or above `ONSET_LEVEL` are identical, because `level` is already floored. Below that, delay comes back only by giving up attacks, including attacks the frozen engine caught (the paired set shrinks from 32 to 30). No setting passes both halves. Lane 3 is not declared.

`CONTRIBUTION_CAP` exists because an uncapped tally peaks in the hundreds while a per-sample score sits near one. The tally then becomes every group's best, drives `level` into the tens, and moves the alert onto its own later crossing. Measured once that way, paired median delay went from 1 s to 8 s. The cap is `ONSET_LEVEL / ONSET_FRACTION`, which is 20. It is there to keep the column from stealing placement. It is not a sensitivity knob, and turning it after the table above would be fitting the bar you already failed.

A delay-aware placement rule would be a new function beside `events`. ADR 0286 does not authorise editing the frozen detector. ADR 0294 records that the placement rule was not built.

## Lane 4: a predictor that understood the attack

`src/phos/atlas/bending_consistency.py`, result name `atlas-bending-consistency`. The question stays the frozen one: predict each signal from every other signal, now and at lags `(0, 5, 15, 30, 60)`, one ridge (`RIDGE = 1.0`) per signal from one shared Gram matrix. The target's own history is still excluded. The residual is still an absolute error in units of the attack-free 99.99th percentile (`RESID_QUANTILE = 0.9999`).

The change is a hinge basis. Each standardised input `x` expands to

```text
[x, max(0, x - t_1), ..., max(0, x - t_k)]
```

Knots `t` come from `KNOT_QUANTILES = (0.25, 0.5, 0.75)` of that signal's attack-free training values. Inputs are clamped to the training range before expansion, so a wild reading does not produce a wild prediction and hide itself. With zero knots the basis is `[x]`, the Gram is the frozen Gram, and a test pins the scores identical. The bend is the only difference between the two detectors. This lane appends no column. ADR 0286's slot constraint does not apply to it. An earlier sentence in that ADR which said lane 4 appends columns is wrong; ADR 0288 corrects it.

`eval_runs/build/lane-e/lane4-development.md`, nothing tuned on a label:

| Knots | Attacks caught of 70 | Benign alerting of 20 | FP/day in sample | FP/day leave-one-out |
| --- | ---: | ---: | ---: | ---: |
| 0, which is the frozen engine | 32 | 5 | 18.00 | 28.00 |
| 1, at the median | 24 | 1 | 0.00 | 20.00 |
| 3, at the quartiles | 25 | 1 | 2.00 | 24.00 |
| 5, at 0.1 / 0.25 / 0.5 / 0.75 / 0.9 | 23 | 1 | 2.00 | 22.00 |

The quiet half of the hypothesis is confirmed. Leave-one-out false alarms fall from 28.00 to 20.00–24.00 a day. Benign events drawing an alert fall from 5 of 20 to 1 of 20. The detection half is refuted. Catches fall from 32 to 23–25 at every amount of bend. The effect is "bend at all", not "how many knots". `liar_freeze` goes from 1 of 10 to 0 of 10. `replay` goes from 5 of 10 to 1 of 10. Only `rogue_command` improves, 4 to 6.

The loop score is the error between a reading and what the rest of the plant implies. A crude predictor is surprised easily, and an attack is one of the things it is surprised by. A predictor that can represent saturation, a deadband, and a phase change explains more of what it sees, and the attack is part of what it sees. A frozen reading, a replayed trace, or a slow creep inside the plant's own non-linear envelope leaves a smaller residual. Some of the frozen engine's detection is a side effect of its misfit. Removing the misfit costs more catches than the quiet it buys. There is no bar in the programme that records "quieter" as a win by itself. Lane 4 is not declared. `phos-icssim-heldout2` was not generated.

The in-sample false-alarm rate of the frozen engine on these runs is 18.00 against 28.00 leave-one-out. Any in-sample figure for it is optimistic by about that much. Quote the leave-one-out column.

## The same shape, later, on a walk

`src/phos/atlas/walk_consistency.py` is not lane 3 or lane 4. It is the column ADR 0301 specified and ADR 0313 allowed, because the champions missed 1 of 9 `subfloor_walk` events on `phos-icssim-dev4-walk`. The column compares the inlet valve with the constant PLC1 writes: `VALVE_ABOVE_MAX = 0` when the level is strictly above `tank_level_max`, `VALVE_BELOW_MIN = 1` when the level is strictly below `tank_level_min`, and zero inside the band. `walk_divisor` is the third-largest attack-free peak, floored at 1. The frozen files were not edited.

ADR 0315: the column missed the same 1 of 9. False alerts per hour stayed 1.187500. The budget stayed 8. On events both catch, the new alert was not later. The first bar is `M_new <= floor(1 / 2)`, and that bound is 0. The printed divisor was 2.000000, from three training peaks, so a full valve error sits on `ONSET_LEVEL` and does not open an episode (`THRESHOLD` is a strict greater-than). The divisor was not lowered. The column is not a champion. Result name `atlas-walk-consistency` stays a name, not a promotion.

## What else was asked and did not land

Lane 1, command traffic, is the lane that was kept, under the name it already had: on twenty simulated runs it had not seen, attacks caught went from 49 of 120 to 87 of 120, reconnaissance from 0 of 20 to 20 of 20, benign alerts unchanged at 6 of 40 (ADR 0276). The gain is attribution. `mimic_maintenance` and genuine maintenance are physically indistinguishable in that corpus, so the lane cannot pose the physics question. Simulated.

`legal_flow` (ADR 0295, ADR 0296): the plant's outflow is a constant while the outlet valve is open and the tank holds water, so there is no continuous level-flow ratio to ride. The class scales the level by the already-fixed 3–8% band and sets the flow to that legal value. Breadth caught 15 of 32 attacks and the frozen engine 16 of 32. `legal_flow` itself was 2 of 4 for each. The band was not changed. The first bar fails.

The combined candidate was not assembled. The one look at the seen corpora was not taken. None of this moves 646.58, 18.72, or the 131 of 160 testbed figure. Those rows belong to other detectors and other files.

---

[The record](../README.md) · [Front page](../../README.md)
