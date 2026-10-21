# Lane 3 on ICSSim development — twenty-one more attacks, and it still fails the bar

**Date:** 2026-10-21 · **Development data only** (`phos-icssim-dev2`, ADR 0285).
`phos-icssim-heldout` and `phos-icssim-heldout2` were **not** read; heldout2 was never generated.
**Not declared, not frozen.** Simulated, so diagnosis and not proof (R4, ADR 0143).
`eval_runs/log.jsonl` was not appended and no v1 number moved.

Command: `uv run python scripts/lane_e_drift.py --corpus .../phos-icssim-dev2 --cap <cap>`
Detector: `phos.atlas.drift_consistency` — one leaky accumulator column per signal, over that
signal's own frozen score, appended to the score matrix and sent through the unchanged `events`
and `budget_alerts` so the columns compete for the same eight alerts a shift.

## The bar, and the answer

From `docs/build-brief-2026-10-e.md`, not reworded: **strictly more attacks caught within the same
eight-alerts-a-shift budget, and median detection delay no worse.** Both reported; a recall gain
bought by alerting later is not a pass.

**First half met, decisively. Second half failed, at every setting tried.** Lane 3 is therefore
**not declared**: ADRs 0279 and 0280 stay unwritten, no held-out score was taken, and
`phos-icssim-heldout2` was not generated. The brief's instruction is to freeze and declare only
*if it wins on development*, and it does not.

## The result at the module's own default

`SLACK_QUANTILE = 0.99`, `CONTRIBUTION_CAP = ONSET_LEVEL / ONSET_FRACTION = 20.0`, retention
`1 - 1/3600 = 0.999722` from the engine's own detrend window.

| Label | Class | Frozen | Lane 3 | Of | Placed by |
| --- | --- | ---: | ---: | ---: | --- |
| attack | `liar_freeze` | 1 | **10** | 10 | accumulator |
| attack | `rogue_command` | 4 | **10** | 10 | accumulator, signal |
| attack | `replay` | 5 | **7** | 10 | accumulator, signal |
| attack | `mimic_maintenance` | 2 | **6** | 10 | accumulator |
| attack | `creep_many` | 10 | 10 | 10 | accumulator, signal |
| attack | `liar_offset` | 10 | 10 | 10 | signal |
| attack | `recon` | 0 | 0 | 10 | — |
| benign | `maintenance` | 4 | 8 | 10 | accumulator |
| benign | `setpoint` | 1 | 0 | 10 | signal |

**Attacks: frozen 32 of 70, lane 3 53 of 70. Benign drawing an alert: frozen 5 of 20, lane 3 8 of
20.** Lane 3 loses nothing: there is no attack the frozen engine catches and lane 3 misses.

`liar_freeze` 1 of 10 to **10 of 10** is the lane's own hypothesis landing. That class is a reading
held while the plant moves away underneath it — a departure that is never large at any one sample
and that the detrender actively flattens — and it is the shape the brief predicted a peak threshold
would miss and an accumulator would catch. `recon` stays at 0 because it never moves the plant, so
no telemetry-only statistic can see it however it is accumulated; that is lane 1's territory and
the baseline already says so.

## Why it fails anyway

Delay, on the 32 attacks **both** engines catch, so the two numbers describe the same events:

| Class | n | Frozen | Lane 3 | |
| --- | ---: | ---: | ---: | --- |
| `creep_many` | 10 | 93 s | **71 s** | lane 3 22 s earlier |
| `liar_offset` | 10 | 1 s | 1 s | identical on all ten |
| `rogue_command` | 4 | 2 s | 2 s | three identical, one earlier |
| `replay` | 5 | 0 s | 8 s | four of five later |
| `mimic_maintenance` | 2 | 1 s | 80 s | both much later |
| `liar_freeze` | 1 | 134 s | 137 s | 3 s later |

**Median over the paired set: frozen 1 s, lane 3 5 s.** Over each engine's own caught set:
frozen 1 s, lane 3 13 s. The second half of the bar fails under **both** readings, so the verdict
does not depend on which definition of "median delay" is used — worth stating, because the brief
does not pin that choice.

The cause is a structural interaction with the frozen engine's event machinery, not a tuning miss.
`phos.atlas.consistency.events` puts an event's alert at the earliest member episode reaching
`level = max(ONSET_LEVEL, ONSET_FRACTION * best_peak)` and **skips any member whose own peak is
below that level**. When a weak per-signal episode — peak between `THRESHOLD` and `ONSET_LEVEL`,
which is what an instantly-detected `replay` looks like — is grouped with a saturated accumulator
episode, the accumulator becomes the group's `best`, `level` is pinned at its `ONSET_LEVEL` floor,
and the weak episode is disqualified from placing the alert. The alert moves to the accumulator's
own later crossing. Alone, that weak episode would have placed its own alert, because `level` is
clamped by `min(best_peak, ...)` and an episode always qualifies against itself.

## The whole dial, so nobody repeats the sweep

The cap is the only quantity that trades the two halves against each other. Every row is
`phos-icssim-dev2`, slack quantile 0.99.

| Cap | Attacks caught | Attacks both catch | Paired delay | Own-set delay | Both halves |
| ---: | ---: | ---: | --- | --- | --- |
| 1.05 | 39 | 31 | 1 s → 2 s | 1 s → 4 s | no |
| 1.25 | 42 | 30 | 1 s → 3 s | 1 s → 7 s | no |
| 1.50 | 42 | 30 | 1 s → 4 s | 1 s → 8 s | no |
| 2.00 | 53 | 32 | 1 s → 5 s | 1 s → 13 s | no |
| 5.00 | 53 | 32 | 1 s → 5 s | 1 s → 13 s | no |
| 20.00 | 53 | 32 | 1 s → 5 s | 1 s → 13 s | no |

Three things this says. Caps at and above `ONSET_LEVEL` are **identical**, because the accumulator
saturates past any of them and `level` is already at its floor — so the earlier worry that the
result was a cap artifact is answered: it is not. Below `ONSET_LEVEL` the cap buys delay back only
by giving up catches, and it never reaches "no worse". And the paired set **shrinks** as the cap
falls, 32 to 31 to 30, meaning a weak accumulator starts losing attacks the frozen engine catches —
so the low end is worse on both halves at once, not a trade.

The bar is met on recall at every setting on the dial and failed on delay at every setting on the
dial. There is no setting of this detector, as specified, that passes.

## What this is not

It is not a refutation of accumulation. The idea does what it was built to do — `liar_freeze` 1 of
10 to 10 of 10, nothing lost, and `creep_many` detected 22 s **earlier** — and the thing that
sinks it is the alert-placement rule of the engine it is bolted to, which the brief requires be
left unchanged ("the unchanged `events()` and `budget_alerts()` handle it"). That constraint is
what makes "more catches" and "no later" mutually exclusive here: a column strong enough to win a
slot on a saturated budget is, by the same number, strong enough to capture its group's alert
placement. Recorded as its own finding in **ADR 0286**, because it constrains lane 4 in the same
way — lane 4 also appends columns and will meet the same wall if its bar mentions delay.

It is also not a result about real plants. ICSSim is generated by PHOS; R4 and ADR 0143 make this
diagnosis, not proof, and nothing here says Atlas is any particular strength on a real plant.

## What would test it properly

Either of two things, each a declaration of its own and neither done here:

1. **A delay-aware placement rule**, which means a new event-grouping function beside the frozen
   one rather than an edit to it — `atlas-v1-consistency` is never edited — so an accumulator
   column can win a budget slot while a weak per-sample episode keeps the right to place the alert.
   That is a change to the engine's machinery, not to this lane, and it is the honest next question.
2. **A bar that prices the trade**, if a partner says 21 more attacks at four seconds' median cost
   is worth having. That is a conversation for `docs/design-partner-brief.md` and P1, not a number
   this session may move: the bar as written refuses it, and the bar as written stands.

The detector and its harness are kept on disk, tested, and left undeclared, exactly as lane 2's
breadth column is. They cost nothing while they sit there.
