# Lane 4 on ICSSim development — a faithful predictor is a quieter and blinder detector

**Date:** 2026-10-21 · **Development data only** (`phos-icssim-dev2`, ADR 0285).
`phos-icssim-heldout` and `phos-icssim-heldout2` were **not** read; heldout2 was never generated.
**Not declared, not frozen.** Simulated, so diagnosis and not proof (R4, ADR 0143).
`eval_runs/log.jsonl` was not appended and no v1 number moved.

Command: `uv run python scripts/lane_e_bending.py --corpus .../phos-icssim-dev2 --knots <set>`
Detector: `phos.atlas.bending_consistency` — the frozen engine with its ridge regression replaced
by the same ridge over a **hinge basis**, `[x, max(0, x - t_1), ..., max(0, x - t_k)]`, knots at
quantiles of each signal's attack-free training distribution, inputs clamped to the training range
so the predictor saturates instead of extrapolating.

Unlike lanes 1 to 3 this lane appends **no** column. The brief specifies "same inputs, same
outputs, same interpretation", so it returns the same one score per signal and goes straight into
the unchanged `events` and `budget_alerts`. ADR 0286's constraint on appended columns therefore does
not reach it, and that record has been corrected where it assumed otherwise.

## The bar, and the answer

From `docs/build-brief-2026-10-e.md`, not reworded: **strictly more attacks caught within the same
eight-alerts-a-shift budget, and no more false alarms per day on attack-free data than the frozen
engine.** A catch gain bought with more false alarms is not a pass.

**Second half met, comfortably. First half failed, at every setting tried — and failed in the
opposite direction to the lane's own hypothesis.** Lane 4 is **not declared**: ADRs 0281 and 0282
stay unwritten, no held-out score was taken, and `phos-icssim-heldout2` was not generated.

## The measurement

Every row is `phos-icssim-dev2`: fitted on the three `normal` runs, scored on the ten `mixed2` runs,
nothing tuned. The zero-knot row is the frozen engine by construction, and a test pins that the two
agree there bit-for-bit — so this is one detector with one dial, not two detectors.

| Knots | Attacks caught of 70 | Benign alerting of 20 | FP/day in sample | FP/day leave-one-out |
| --- | ---: | ---: | ---: | ---: |
| 0 — **is** the frozen engine | **32** | 5 | 18.00 | 28.00 |
| 1, at the median | 24 | 1 | 0.00 | 20.00 |
| 3, at the quartiles (default) | 25 | 1 | 2.00 | 24.00 |
| 5, at 0.1/0.25/0.5/0.75/0.9 | 23 | 1 | 2.00 | 22.00 |

Per class at the default, frozen against lane 4: `liar_offset` 10 → 10, `rogue_command` 4 → **6**,
`creep_many` 10 → 7, `replay` 5 → 1, `mimic_maintenance` 2 → 1, `liar_freeze` 1 → **0**,
`recon` 0 → 0.

**The dial does not have a good setting.** Catches fall to 23–25 from 32 for *any* amount of bend and
do not recover as the bend changes; the effect is "bend at all", not "how much". False alarms fall
hard and stay down. One class improves (`rogue_command`, 4 to 6) and the rest hold or fall.

**On the two false-alarm figures.** Both engines are fitted on the only attack-free data the corpus
has, so counting alerts on those same runs is in sample and flatters both — the frozen engine's own
number moves 18.00 to 28.00 per day when it is measured honestly, which is worth noting on its own.
The leave-one-out column holds one `normal` run out, fits both engines on the other two, counts
alerts on the held-out run and rotates. The bar is judged on that column. Lane 4 passes it at every
setting.

## Why it fails, and why the reason matters more than the lane

The brief's hypothesis was that a linear model "leaves structured errors during ordinary non-linear
operation, which costs false alarms, and an attacker moving inside what a linear model cannot
represent is invisible". **The first half of that is confirmed and the second half is refuted.**

Making the predictor faithful did remove the structured error: false alarms on honest out-of-sample
attack-free data fall from 28.00 to 20.00–24.00 per day, and benign events drawing an alert fall from
5 of 20 to 1 of 20. That is a real improvement and it is exactly what the brief predicted.

But detection fell with it, because **some of the frozen engine's sensitivity comes from its
misfit.** The loop score is the error between a reading and what the rest of the plant implies. A
crude predictor is surprised easily — including by an attack. A faithful predictor explains more of
what it sees, and an attack is part of what it sees: a frozen reading, a replayed trace, a slow creep
that stays inside the plant's own non-linear envelope are all *better explained* by a model that can
bend, so the residual they produce is smaller. `liar_freeze` going 1 of 10 to **0 of 10** is the
clearest case, and `replay` 5 to 1 the largest.

So the linear predictor is not only a limitation to be removed. Its crudeness is load-bearing, and
removing it costs more detection than the quiet it buys — on this corpus, under this bar.

## What this is not

It is not a refutation of non-linear prediction. A faithful predictor that was **also** sensitive
would need the two things separated: let the model bend where the plant genuinely bends during
ordinary operation, and not where an attacker is operating. Nothing here does that, and nothing here
shows it cannot be done. What is measured is that a straight swap of the predictor trades the one for
the other.

It is also not a result about real plants. ICSSim is generated by PHOS; R4 and ADR 0143 make it
diagnosis, not proof.

## What would test it properly

Each of these is a declaration of its own, and none is done here:

1. **A quieter engine judged as a quieter engine.** Lane 4 is a clear win on the half of the bar it
   passes — 28 to 20 false alarms a day out of sample, benign alerts 5 of 20 to 1 of 20 — and the
   programme has no bar that rewards that alone. Whether a plant would take 24 fewer false alarms a
   day for 8 fewer catches is the design-partner conversation in `docs/design-partner-brief.md`, not
   a number a build session may set.
2. **Bending constrained to ordinary operation**, for example fitting the bend only on stretches the
   frozen engine already calls quiet, so the flexible model never learns to explain an attack. That
   is a different detector, not a setting of this one.
3. **The two combined rather than swapped.** The frozen linear score and the bent score are
   available at once, and they fail differently: the bent one is quiet, the linear one is sensitive.
   Whether both as separate columns beats either alone is a real question — and it runs straight into
   ADR 0286, because that is an appended column on a saturated budget.

The detector and its harness are kept on disk, tested, and left undeclared, as lanes 2 and 3 are.
