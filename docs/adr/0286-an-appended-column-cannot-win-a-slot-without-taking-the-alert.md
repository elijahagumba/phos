# ADR 0286 — An appended column cannot win a budget slot without taking its group's alert

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Atlas, stronger-engine programme, a constraint found by lane 3
- **Supersedes:** nothing
- **Depends on:** [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0274](0274-the-icssim-corpus-exists-and-its-held-out-half-is-sealed.md),
  [ADR 0285](0285-the-corpus-gains-a-coordinated-low-amplitude-class.md)

## Context

The stronger-engine programme gives every lane the same shape: build a new statistic, append it to
the score matrix as extra columns, and send the augmented matrix through the **unchanged**
`phos.atlas.consistency.events` and `budget_alerts`, so the new columns compete with the per-signal
columns for the same eight alerts a shift. `phos.atlas.command_consistency` (lane 1, kept) and
`phos.atlas.breadth_consistency` (lane 2, undeclared) are both built that way, and
`docs/build-brief-2026-10-e.md` requires lane 3 and lane 4 to be built that way too.

Lane 3 measured a consequence of that shape which no earlier lane could have seen, because lane 3
is the first lane whose bar mentions **detection delay**. The measurement is
`eval_runs/build/lane-e/lane3-development.md`: on `phos-icssim-dev2`, the accumulator detector
`phos.atlas.drift_consistency` catches **53 of 70 attacks against the frozen engine's 32**, loses
nothing, and takes `liar_freeze` from 1 of 10 to 10 of 10 — and its median detection delay is
**worse at every setting of its one free parameter**, under both the paired and the own-set reading.
It therefore failed its bar and was not declared.

The reason is not the statistic. It is the alert-placement rule.

## Decision

**Record this as a property of the engine's event machinery, binding on every lane that appends
columns.**

`events` groups episodes whose onsets chain within `event_window`, then for each group:

```python
best = max(group, key=lambda episode: episode[2])
level = min(best[2], max(ONSET_LEVEL, ONSET_FRACTION * best[2]))
onset, column = best[3], best[4]
for s, e, peak, _at, j in group:
    if peak < level or s >= onset:
        continue
```

Three facts follow, and together they are the constraint:

1. The alert starts at `best`'s **peak row**, and moves earlier only to a member that reaches
   `level`.
2. A member whose own peak is below `level` is **skipped** — it cannot place the alert at all.
3. Alone, every episode qualifies against itself, because `level` is clamped by `min(best[2], ...)`.

So a weak episode — peak between `THRESHOLD` and `ONSET_LEVEL` — places its own early alert when it
is the strongest thing in its group, and loses that right the moment a stronger column joins the
group. On a **saturated** budget the two properties cannot be separated: a column must score high
to win a slot at all, and scoring high is exactly what makes it its group's `best` and takes the
placement. `budget_alerts` ranks events by score, so a column that ranks below the per-signal
columns never alerts, and a column that ranks above them re-places their alerts.

Lane 3's dial is the evidence that this is structural rather than a tuning miss. Its cap is the
only quantity trading the two halves, and every value was measured:

| Cap | Attacks caught (frozen 32) | Attacks both catch | Paired median delay |
| ---: | ---: | ---: | --- |
| 1.05 | 39 | 31 | 1 s → 2 s |
| 1.25 | 42 | 30 | 1 s → 3 s |
| 1.50 | 42 | 30 | 1 s → 4 s |
| 2.00, 5.00, 20.00 | 53 | 32 | 1 s → 5 s |

Caps at or above `ONSET_LEVEL` are identical, because `level` is already at its floor. Below it,
delay comes back only by surrendering catches — and the paired set *shrinks*, 32 to 30, so the low
end gives up attacks the frozen engine catches. No setting passes both halves.

**What this does not license.** `atlas-v1-consistency` is on the frozen list in
`docs/rules/data-tiers.md` and `events` is part of it. This record does not authorise editing it,
and lane 3 did not. A delay-aware placement rule is a **new function beside** the frozen one, under
a new name, declared and measured on its own — not a patch to the frozen engine, and not something
this record decides.

## Consequences

**Lane 4 inherits this.** The brief's lane 4 bar is "strictly more attacks caught within budget and
no more false alarms per day", which does not mention delay, so lane 4 is not blocked. But lane 4
appends columns to the same machinery, and if its result is ever read for timeliness, or its bar is
ever amended to include delay, it meets this wall for the same reason. A lane whose bar includes
delay cannot be satisfied by appending a column alone.

> **Correction, same day, before lane 4 was built.** The paragraph above is wrong about lane 4 and
> is left standing rather than edited away. Lane 4 **appends no column**: the brief specifies
> "replace ridge regression with a predictor that can represent saturation, deadbands and phase
> changes. Same inputs, same outputs, same interpretation", so it is a drop-in replacement for the
> loop predictor returning the same one score per signal. `phos.atlas.bending_consistency` is built
> that way and a test pins it. So this record's constraint does **not** reach lane 4 at all, under
> any bar: with no extra column there is no extra episode to join a group, become its `best` and
> re-place its alert. The claim that lane 4 "appends columns to the same machinery" was an
> assumption about lane 4's shape, made while writing up lane 3 and not checked against the brief.
> Everything else in this record stands: it is about appended columns, which lanes 1, 2 and 3 all
> are, and about step 0283, where several appended families combine.

**Step 0283 inherits it twice over.** The combined candidate assembles every kept lane's columns
into one matrix. Two or more appended column families in one group compete for placement against
each other as well as against the per-signal columns, so the combined detector's alert times are
not predictable from any lane's alert times measured alone. Delay must be re-measured on the
combination, not inferred.

**It explains a number already on the record.** Lane 1's benign alerts *fell* 5 of 20 to 3 of 20 on
`phos-icssim-dev2` while its catches rose, which `eval_runs/build/lane-e/dev2-with-creep-many.md`
attributes to the fixed budget letting strong evidence displace weak noise. This record is the same
mechanism seen from the other side: displacement is what the budget does, and it moves alert times
as well as alert counts. Lane 1 was lucky in which direction that cut; lane 3 was not.

This is a finding on a simulated plant. R4 and ADR 0143 make it diagnosis and not proof, and no
claim here says anything about Atlas's timeliness on a real plant. It is a statement about the
engine's own machinery, which is where it is safe: the arithmetic quoted above is the committed
source, not a measurement.

## What would reverse this

A reading of `events` showing the placement rule does something other than the three facts above;
or a measurement where an appended column wins budget slots on a saturated shift without changing
any per-signal alert's row. Lane 3 looked for the second and did not find it over the whole range
of its parameter.
