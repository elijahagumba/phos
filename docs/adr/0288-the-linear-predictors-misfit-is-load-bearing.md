# ADR 0288 — The linear predictor's misfit is load-bearing

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Atlas, stronger-engine programme, a finding from lane 4
- **Supersedes:** nothing
- **Depends on:** [ADR 0106](0106-four-checks-on-the-frozen-candidate.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0274](0274-the-icssim-corpus-exists-and-its-held-out-half-is-sealed.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md)

## Context

Lane 4 of the stronger-engine programme asks for the frozen engine's question to be kept exactly —
predict each signal from every other signal, now and at four lags — and its answer to be replaced:
a predictor that can represent saturation, deadbands and phase changes in place of the ridge
regression. "Same inputs, same outputs, same interpretation."

The brief states a two-part hypothesis for why that should help: a linear model "leaves structured
errors during ordinary non-linear operation, which costs false alarms, and an attacker moving
inside what a linear model cannot represent is invisible."

`phos.atlas.bending_consistency` implements it as the same ridge over a hinge basis,
`[x, max(0, x - t_1), ..., max(0, x - t_k)]`, with knots at quantiles of each signal's attack-free
training distribution and inputs clamped to the training range so the predictor saturates rather
than extrapolating. The model stays linear in its parameters, so it is still one ridge solve per
signal from one shared Gram matrix, still excludes the target's own history, and still returns an
absolute residual in units of a training quantile. **With zero knots it is the frozen detector, and
a test pins that the scores agree bit-for-bit** — so the bend is the only difference between the two
things compared, and the result below is one detector with one dial rather than two detectors.

It also appends **no** column, unlike lanes 1 to 3, which is why ADR 0286's constraint does not
reach it. That record has been corrected where it assumed otherwise.

## Decision

**Record that the first half of the hypothesis is confirmed, the second half is refuted, and lane 4
is not declared.**

`eval_runs/build/lane-e/lane4-development.md` carries the measurement. On `phos-icssim-dev2`, fitted
on the three `normal` runs and scored on the ten `mixed2` runs with nothing tuned:

| Knots | Attacks caught of 70 | Benign alerting of 20 | FP/day in sample | FP/day leave-one-out |
| --- | ---: | ---: | ---: | ---: |
| 0 — **is** the frozen engine | **32** | 5 | 18.00 | 28.00 |
| 1, at the median | 24 | 1 | 0.00 | 20.00 |
| 3, at the quartiles | 25 | 1 | 2.00 | 24.00 |
| 5, at 0.1/0.25/0.5/0.75/0.9 | 23 | 1 | 2.00 | 22.00 |

**The quiet is real.** On honest out-of-sample attack-free data — one `normal` run held out, both
engines fitted on the other two, rotated — false alarms fall from 28.00 to 20.00–24.00 per day, and
benign events drawing an alert fall from 5 of 20 to 1 of 20. Exactly what the brief predicted, and a
clear win on that half of the bar.

**The blindness is also real, and was not predicted.** Catches fall from 32 to 23–25 for *any*
amount of bend, and do not recover as the bend changes: the effect is "bend at all", not "how much".
`liar_freeze` goes 1 of 10 to **0 of 10** and `replay` 5 of 10 to 1 of 10. Only `rogue_command`
improves, 4 to 6.

**The mechanism, which is the finding worth keeping.** The loop score is the error between a reading
and what the rest of the plant implies. A crude predictor is surprised easily, and an attack is one
of the things it is surprised by. A faithful predictor explains more of what it sees — and an attack
is part of what it sees. A frozen reading, a replayed trace or a slow creep that stays inside the
plant's own non-linear envelope are all *better explained* by a model that can bend, so the residual
they leave is smaller. **Some of the frozen engine's detection power is a side effect of its
misfit**, and removing the misfit costs more detection than the quiet it buys.

So the linear predictor is not only a limitation waiting to be removed. On this corpus, under this
bar, its crudeness is load-bearing.

**Lane 4 is therefore not declared.** ADRs 0281 and 0282 stay unwritten, no held-out score was
taken, and `phos-icssim-heldout2` was not generated — the brief says to freeze and declare only if
the lane wins on development, and it loses the half it was built to win.

## Consequences

**Three of the four lanes are now closed without a kept result, and only lane 1 passed.** Lane 2 is
untestable on any corpus that exists (it needs an attack invisible per-signal, which is its own
declaration). Lane 3 caught 21 more attacks and failed on delay (ADR 0286). Lane 4 is quieter and
blinder. Step 0283 therefore assembles a candidate from **one** lane, whose own ADR 0275 records its
gain as attribution and as shallow by construction: an attacker working from the operator's station
defeats both its components. Whether that supports "significantly stronger than the engine we
shipped" is a question to settle **before** step 0284 spends a one-look exception, not after.

**A bar the programme does not have.** Lane 4 is a substantial improvement on a dimension the brief
only ever wrote as a constraint. Nothing in the programme rewards a quieter engine on its own, so a
real gain has nowhere to be recorded as a gain. Whether a plant would take roughly a quarter fewer
false alarms a day for eight fewer catches is the design-partner conversation
(`docs/design-partner-brief.md`), and it is not a number a build session may set.

**A caveat this lane found in the existing numbers.** The frozen engine's own false-alarm rate moves
from 18.00 to 28.00 per day between the in-sample and leave-one-out measurements on the same runs.
Any false-alarm figure for this engine measured on the runs it was fitted on is optimistic by about
that much. No committed claim rests on the in-sample figure, and none should.

This is a finding on a simulated plant. R4 and ADR 0143 make it diagnosis and not proof, and nothing
here says anything about Atlas on a real plant.

## What would reverse this

A predictor that bends where the plant bends during ordinary operation and not where an attacker is
operating — for example one fitted only on stretches already judged quiet — which is a different
detector and not a setting of this one. Or a measurement on a corpus whose attacks fall outside the
plant's learned non-linear envelope, where a faithful model would stay surprised. Neither is done
here, and neither is refuted by this record.
