# ADR 0137 — Smooth weights for the challenger's facts, the last arena run, and a third confirmation

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0123 §9.3, before anything below is scored
- **Amends:** [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md) §1 (one more override)
- **Depends on:** [ADR 0114](0114-the-liar-measurement-is-assembled-and-held.md),
  [ADR 0135](0135-decisive-witnesses-and-upstream-first.md),
  [ADR 0136](0136-the-confirmation-water-works-the-bars-are-not-met.md)

## Context

Both red teams failed by two champion passes out of about fifty (ADR 0134, ADR 0136). On the
three power-plant losses, diagnosed on seeds that are now spent, the challenger promoted the same
facts as the champion. But ADR 0114's isotonic calibrator, fitted on the challenger's stronger
facts, gave every one of them the same weight at the top of its step function. Two
`sensor_or_device_fault` hypotheses, one fact each, then reached exactly the same confidence.
ADR 0094's predicate refuses a tie, so the run failed. The champion's weaker facts fell on a
lower, uneven part of its step function, and one hypothesis led.

A tie made by a step function is an artefact of the calibrator, not evidence. A Platt
calibrator, the engine's other fitted calibrator (`phos.reasoning.PlattCalibrator`), is strictly
increasing in magnitude: facts of different strength never receive the same weight. On the three
spent power runs, the challenger with Platt weights passes all three. The batch loss (95205 at
0.8) is not explained by this and remains undiagnosed. These checks were made on spent seeds, so
they shaped the decision but cannot judge it.

## Decision

**1. A setting, `calibrator`**, `"isotonic"` (ADR 0114, the default) or `"platt"`, chooses how
the challenger's facts are weighted in the liar assembly. The champion's calibrator never
changes. ADR 0127's overridable settings gain it.

**2. Attempt 6, the arena's last run:**
`{"detector": "atlas-plant-map-v1", "map": {"naming_rules": "adr-0135", "calibrator": "platt"}}`.

**3. A third confirmation set, `CONFIRM_SEEDS_2`**, development seeds 95301–95310, disjoint from
every other set (a test checks). After attempt 6 is scored on the arena, and only then:
`scripts/arena_red_team.py plant-map --confirm 6 --confirm-set 2` once, judged by ADR 0123
§9.3's rule unchanged (more passes than the champion, none lost), and
`scripts/plant_map_dev.py --candidate …/candidate-6.json --confirm --confirm-set 2 liar` and
`… graded`, judged by §9.7's bars unchanged.

## Consequences

- If attempt 6 survives, `atlas-plant-map-v1` with these settings is the candidate for ADR
  0117's gate, as a detector. Naming stays behind its own bars.
- If it loses a champion pass again, that is the result. The arena's budget is then spent, and
  the next step is a new task with a stated hypothesis, or Elijah's own record on the rule.

## What would reverse this

Changing the champion's calibrator; scoring `CONFIRM_SEEDS_2` before attempt 6's arena score, or
more than once; or changing a bar after either score.

## Amendment before any confirmation score (15 October 2026)

Attempt 6 was scored on the arena (57 of 90, water 24, none lost, HAI 20.07 37 of 38: it
qualifies). The confirmation then stopped before writing anything: one generated corpus,
`t1-liar-water-treatment-s95310`, has every attack in one fold, so the harness cannot cross-fit
its sensor calibrator. That calibrator is the joint model's and never sees the inlet, so the
corpus is unmeasurable for the champion and the challenger alike. `score_windows` now reports
such a corpus as `unmeasurable` and scores the rest, for both detectors; no earlier scorecard had
one, so none changes. The confirmation is then run once, as declared.

