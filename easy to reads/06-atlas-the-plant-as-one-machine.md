# Atlas: the plant as one machine

**What this is:** the industrial engine — from plant telemetry in, to competing-hypothesis
narratives out.

**Why it exists:** a factory is not fifty independent thermometers. When one pump’s flow, pressure,
and valve position move together, that is often **one event**. Counting fifty alarms is how control
rooms learn to ignore the board.

## Orchestra, not fifty soloists

A **per-signal** Gaussian asks each instrument: “are you loud compared with your own past?” A
flute can be “loud” while the orchestra is still in key.

Atlas’s **joint model** asks: “given everything else we hear, is this chord still the piece we
learned?” The method that won the measurement is **Mahalanobis** distance — a way of saying “this
combination of readings is rare together,” not merely “this one pipe is high.”

**PCA** (a related compression trick) was tried on the same data and **lost**: more false alarms,
not fewer. That negative result is kept in the decision record on purpose.

On the HAI water-treatment corpus, at unchanged recall:

| What we counted | False alarms per normal hour |
| --- | --- |
| Per-signal Gaussian | 8,390 |
| Atlas joint (Mahalanobis) | 647 |
| Same alerts, grouped by declared plant unit | **53** |

Joint modelling cut false positives about **13×**. Grouping cut the operator’s queue another
**12×** (5,123 per-signal alerts → 424 subsystem events) without dropping an attack window.

**53 alerts per quiet hour is still far past a control room.** Precision sits near 0.009. The
grouping factor is also inflated because HAI’s published documentation could not be partitioned
finer than process level. The 12× figure proves grouping is **implemented**, not that the map is
**correctly resolved**.

## Explainability survives the joint score

A joint anomaly could have been a single opaque “weirdness number.” Atlas still answers, per
signal: *given the rest of the plant, this should have read about X ± Y; it read Z.* That becomes
an ordinary deviation in the shared language. Missing readings are carried forward only briefly
and **never raise a deviation** — inventing a measurement is forbidden.

A signal that never moved during training is **dropped**, and Atlas says nothing about it. You
cannot learn “normal” from a constant.

## Topology is declared, never guessed

Which sensors share a pump is read from a **hand-authored map** grounded in published process
docs (`topology.toml`). PHOS does not infer the plumbing from correlations. Analogy: you copy the
building’s pipe diagram; you do not invent pipes from water-pressure wiggles. Guessing would
confuse “these two numbers move together because physics” with “these two numbers move together
because an attacker.”

Only HAI has such a map today. Features that need a subsystem layout are HAI-only until another
corpus earns one.

## What this is not

- Not deployable. The atlas status report says so in those words.
- Not a proof that joint modelling always wins 10× on every plant. [The first distillation
  baseline](12-batch-distillation-todays-work.md) measured about **8.6×** vs Gaussian, with a large
  recall cost, and still hundreds of alerts per day-equivalent. [Gating the moment](13-quieter-queues-and-honest-ranking.md)
  then cut that to about **49/day** at the cost of **halving perturbation recall**. The 2–3/day
  contract is **refused** on that corpus until a declared phase exists
  ([ADR 0031](../docs/adr/0031-distillation-budget-refused-without-declared-phase.md)). Asking the
  unusual chord to **hold** (dwell) was measured on plants we packed ourselves, not substituted
  for that distillation row
  ([dataset library](14-the-dataset-library-is-not-a-public-corpus.md)).
- Not command-level detection on real packet captures. That measurement was deliberately **not
  run** until a labelled corpus exists ([next file](07-atlas-listening-to-commands.md)).

## Where to read more

- Status report: `docs/atlas-report.md`
- Decisions: [ADR 0009](../docs/adr/0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
  [ADR 0010](../docs/adr/0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0011](../docs/adr/0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md),
  [ADR 0026](../docs/adr/0026-joint-distance-gating-and-the-actionable-alert-unit.md),
  [ADR 0031](../docs/adr/0031-distillation-budget-refused-without-declared-phase.md),
  [ADR 0030](../docs/adr/0030-moment-dwell-and-chronic-volume-decay.md)
