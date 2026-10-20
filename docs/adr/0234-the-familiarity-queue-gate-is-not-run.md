# ADR 0234 — The familiarity queue gate is declared and not run

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane Q
- **Depends on:** [ADR 0212](0212-a3-queue-rank-is-declared.md),
  [ADR 0232](0232-familiarity-is-frozen-before-the-held-back-queue.md),
  [ADR 0233](0233-familiarity-held-back-queue-did-not-beat-the-champion.md)

## Context

Held-back seeds did not show that `familiarity` ranks attacks ahead of the champion
(ADR 0233). A verdict on the five judging corpora would be a new look at validation
data. This record names that look. It does not take it. `data-tiers.mdc` has no
one-look exception for this ranker.

## Decision

**Ranker.** The frozen `familiarity` reorder, sha256
`b5e0eed03bf0799f5f5db5d0898cda63a07ce2d27234e7c155ee45df97c0188b`
of `src/phos/eval/queue_reorder.py`. It reorders the frozen champion's alerts and
does not add or remove one. The champion is not edited.

**Corpora.** HAI 20.07, HAI 21.03, HAI 22.04, HAI 23.05, BATADAL. The same five as
ADR 0212. A corpus that cannot be scored counts as not won. The denominator does
not shrink.

**Metric.** ADR 0212's A3, with the ranker's order in place of the champion's score.
Recall within 8 is `recall_within_budget` at 8 alerts a shift, per file, summed
inside each corpus. Chance is one shuffle inside each shift from
`numpy.random.default_rng(97651)`, the draw already declared for the HAI 20.07
diagnosis, reported beside the ranker and not used to choose a threshold.

**Bar.** A3 strictly higher than 57 of 203 in total, and strictly higher on at least
three of the five corpora. Recall within 8 not lower on any corpus. The chance
draws are reported.

**Command.** `PYTHONPATH=src:. .venv/bin/python scripts/measure_d_queue_gate.py`

**Result name.** `atlas-queue-v2:familiarity-gate`

**Output.** `eval_runs/build/d/queue/gate.json`, which does not exist: as this
<!-- evidence-ack: eval_runs/build/d/queue/gate.json — the gate is not run, as this record's title says, so the output does not exist -->
record's title says, the gate is not run. The command refuses to start. It
does not open a corpus. Running it needs Elijah to add a one-look exception to
`data-tiers.mdc`, as he did for the champion's A3.

Whatever that look finds, v1's A3 stays not met. The recorded 57 of 203 under
`atlas-v1-consistency:a3-queue-rank` is not rewritten. A pass would be a v2
measurement under `atlas-queue-v2:familiarity-gate`.

## Consequences

The command exists so the look has a name. It is not run in this lane.

## What would reverse this

Opening a validation corpus from this branch, or calling a pass on this gate a
change to v1's 57 of 203.
