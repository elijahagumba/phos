# The first-crossing placement rule — refused, and the cause is the rule, not the statistic

**Date:** 2026-11-01 · **Development data only** (`phos-icssim-dev2`, ADR 0285) · Half A of ADR 0397,
declared in ADR 0398, judged here. **Not declared, not frozen.** Simulated, so diagnosis and not
proof (R4, ADR 0143). `eval_runs/log.jsonl` was not appended and no v1 number moved.

Command: `uv run python scripts/lane_e_placement.py --corpus data/phos-icssim-dev2`
Result name: `atlas-placement:dev2`
Detector under test: `phos.atlas.placement_consistency` — lane 3's accumulator columns, at
`SLACK_QUANTILE = 0.99` and `CONTRIBUTION_CAP = 20.0`, with each event's alert placed at the first
sample any member is at or above `THRESHOLD` instead of at the first sample a member reaches
`level = min(best_peak, max(ONSET_LEVEL, ONSET_FRACTION * best_peak))`.

**The question ADR 0397 asked was whether the delay failure ADR 0286 recorded belongs to the
statistic or to the placement rule.** The answer this run gives is: **the placement rule is
responsible for part of it and the statistic for the rest, and removing the rule's share is not
enough to pass.** The rule was replaced and the lane still fails, on three of four bars. The
refusal below says which three and why, and which of them the rule can reach at all.

## The result

One fit on the three `normal` runs, three engines scored on the ten `mixed2` runs. The frozen column
and the lane 3 column are the same engines `lane3-development.md` measured, and they reproduce its
numbers exactly — 32 of 70 with 5 of 20 benign, and 53 of 70 with a paired median of 5 s and an
own-set median of 13 s. So the only difference in the "placed" column is where the alert goes.

| Label | Class | Frozen | Lane 3 | **Placed** | Of |
| --- | --- | ---: | ---: | ---: | ---: |
| attack | `liar_freeze` | 1 | 10 | **9** | 10 |
| attack | `rogue_command` | 4 | 10 | **9** | 10 |
| attack | `replay` | 5 | 7 | **6** | 10 |
| attack | `mimic_maintenance` | 2 | 6 | **5** | 10 |
| attack | `creep_many` | 10 | 10 | **10** | 10 |
| attack | `liar_offset` | 10 | 10 | **10** | 10 |
| attack | `recon` | 0 | 0 | **0** | 10 |
| benign | `maintenance` | 4 | 8 | **7** | 10 |
| benign | `setpoint` | 1 | 0 | **1** | 10 |

**Attacks: frozen 32 of 70, lane 3 53 of 70, placed 49 of 70.**
**Benign drawing an alert: frozen 5 of 20, lane 3 8 of 20, placed 8 of 20.**

| Reading | Frozen | Lane 3 | Placed |
| --- | ---: | ---: | ---: |
| Attacks caught | 32 / 70 | 53 / 70 | **49 / 70** |
| Paired set with the frozen engine | — | 32 | **30** |
| Median delay, paired set | 0.85 s | 5 s | **0.80 s** |
| Median delay, own caught set | 0.85 s | 13 s | **6.10 s** |
| Benign drawing an alert | 5 / 20 | 8 / 20 | **8 / 20** |

## The four bars, each reported

From ADR 0397, repeated verbatim in ADR 0398, and judged as declared.

1. **Strictly more than 32 of 70 attacks caught — MET.** 49 is strictly more than 32.
2. **No attack the frozen engine catches is lost, paired set ≥ 32 — FAILED.** The paired set is
   **30**, short by two. `mixed2-96213`'s `rogue_command` (frozen at +91.6 s) and `mixed2-96217`'s
   `replay` (frozen at +0.2 s) each lose the alert they had.
3. **Median delay no worse than 1 s under both readings — HALF MET, and the half that failed is
   structural.** The paired median is 0.80 s against the frozen 0.85 s: the rule wins that reading,
   and it wins it on the same 30 attacks where 8 alerts moved earlier and none moved later. The
   own-set median is **6.10 s** against the frozen 0.85 s. Bar three requires both, so bar three is
   **not met**.
4. **Benign no higher than 5 of 20 — FAILED.** 8 of 20, exactly lane 3's figure. The rule did not
   buy a single benign alert back.

**A partial win is a refusal.** Three of the four halves fail, so the lane is refused again, and the
module stays on disk undeclared beside lanes 2 and 3.

## Why it fails, and what that says about the statistic

### Bar 2: the rule reaches backwards, and a group can start long before its attack does

This is the rule's own defect, and it is the mirror image of the one ADR 0286 recorded. The frozen
rule can place an alert **too late**, by skipping a weak member. This rule can place one **too
early**, by crediting a member that crossed `THRESHOLD` long before the attack began — and because
`budget_alerts` spends one alert per event and there are only eight slots, an early alert can consume
a slot that would otherwise have carried an in-window alert.

Both losses have the same shape, and it is not a tuning miss:

* `mixed2-96213`, `rogue_command`, window 1335.4–1461.4 s. The placed alert is at **957.0 s**,
  378.4 s before the window opens. Its group's first member is an accumulator column that crossed
  `THRESHOLD` at 957.0 s with a peak of only 1.81, and the grouping rule chains that member to the
  attack's real departure at 1342.0 s because the onsets fall inside `event_window`.
* `mixed2-96217`, `replay`, window 1412.8–1579.8 s. The placed alert is at **1372.0 s**, 40.8 s
  early, on a group whose first member is a per-signal column with a peak of 1.07 — a crossing
  40 s ahead of the window.

That is the rule doing exactly what it was declared to do: the earliest member that clears the
threshold places the alert, with no level to hold it back. The cost is that "earliest" is unbounded
and the grouping boundary is generous — `event_window` is 300 s and `event_span` 600 s — so the
first crossing of a chain can be several minutes before the event an operator cares about. **A rule
that only ever moves earlier must eventually move earlier than the event.** I did not add a
look-back limit, because that would be a new constant and a new dial, and ADR 0398 declared no dial.

### Bar 3b: the own-set median is measuring the extra catches, not the rule's speed

The own-set reading compares 6.10 s over the 49 the rule catches against 0.85 s over the 32 the
frozen engine catches — **two different sets of attacks**, and the 17 the frozen engine misses are
precisely the slow, accumulated departures. Their median delay, measured alone, is **11.0 s**
(`liar_freeze` up to 183.8 s, `mimic_maintenance` 58.6 s). So the own-set figure rises because the
rule catches hard attacks, which is what it was built to do, and the bar as frozen treats that as a
cost. On the paired set — the same 30 events for both engines — the rule is **faster than the frozen
engine**, 0.80 s to 0.85 s.

This is the honest reading and it is also the one that does not pass. ADR 0397 foresaw exactly this
ambiguity and required both definitions to hold; bar 3b does not hold, so bar 3 does not hold. I am
not arguing the definition away. I am recording that **bar 3b is the one bar a recall gain cannot
satisfy**, because on this corpus every engine that catches more of the accumulated classes
necessarily has a higher own-set median. No placement rule can move that number without dropping
the catches that raised it — the ADR 0286 trade seen from the other side.

### Bar 4: the rule changes where benign alerts land, not how many

8 of 20 before and after. Four of the eight are placed on a per-signal column with a member peak of
1.04–1.11, i.e. a bare threshold crossing, and four on an accumulator column. They are the same
benign events lane 3 alerts on; the rule moved several of them earlier (one `maintenance` from 0.3 s
to out of the window entirely, another `setpoint` in) and the count did not move. **The benign cost
belongs to the statistic and the budget, not to the placement.** That is the clearest single answer
this session produces: placement can re-time an alert, and it cannot make a saturated column quieter.

### The separation, stated plainly

| Half | Owed to the placement rule | Owed to the statistic |
| --- | --- | --- |
| Paired delay (bar 3a) | **Yes.** 5 s → 0.80 s, and lane 3's own defect is gone. | No. |
| Two lost catches (bar 2) | **Yes.** Both are the rule reaching before the window. | No. |
| Own-set delay (bar 3b) | No. | **Yes.** Driven by the 17 slow catches the statistic adds. |
| Benign 8 of 20 (bar 4) | No. Identical before and after. | **Yes.** Saturated accumulator columns. |

So ADR 0286's diagnosis was **right and incomplete**. The placement rule really did account for the
paired-set delay, and replacing it recovers that reading outright — 5 s to 0.80 s, better than the
frozen engine. It was not the whole story: two of lane 3's four failures are the statistic's own,
and one of the remaining two is a fresh defect the replacement rule introduced.

## What this does not license

It is not a refutation of the rule's *idea* — that a weak episode should keep the right to place its
own alert — because the paired-set delay did come back without weakening the budget. It is a
refutation of the specific formula, which lets a group's earliest crossing sit arbitrarily far before
the group's own strongest departure. A version with a bounded look-back would be a different rule
with a new constant, and it would need its own declaration. **That is not done here**, and doing it
now — after seeing these two losses — would be tuning on the result.

Nor is it a win on any reading: 49 of 70 against the frozen 32 is a larger number and it is not a
pass, because the bar is four halves together.

It says nothing about real plants. ICSSim is generated by PHOS; R4 and ADR 0143 make this diagnosis,
not proof, and no sentence here says Atlas is any particular strength or speed on a real plant.

## What would test it properly, and what stays refused

1. **A bounded rule.** Same earliest-crossing placement, with the search refused where the group's
   first crossing is more than a declared span before the group's strongest peak. It needs a new
   constant and therefore its own declaration, written before it runs.
2. **A bar that prices the own-set reading differently.** If a partner says 17 more attacks at an
   11 s median is worth having, that is a conversation for `docs/design-partner-brief.md` and P1, not
   a number this session may move. The bar as written refuses it, and the bar as written stands.

Neither is authorised by ADR 0397, and neither is started here. The frozen engine, the lane 3
statistic, the cap, the slack quantile and every prior are untouched: `consistency.py` still hashes
to `71aeebfe…ff5911` and `drift_consistency.py` to `c5c16397…16e345`, the digests they carried
before this session opened.
