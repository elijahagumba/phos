# ADR 0136 — The confirmation: the water liar is caught and named, but the pooled bars are not met

- **Status:** Accepted (a report)
- **Date:** 2026-10-15
- **PART:** ADR 0135's confirmation; the end of ADR 0130's build order
- **Depends on:** [ADR 0130](0130-the-graded-plant-model.md),
  [ADR 0134](0134-red-team-and-the-trusted-map-first-results.md),
  [ADR 0135](0135-decisive-witnesses-and-upstream-first.md)

## Context

ADR 0135 declared two naming rules, attempt 5, and `CONFIRM_SEEDS` (95201–95210, 180 runs), to
be scored once after attempt 5's development measures. This records that score, and where ADR
0130's graded model stands with every grade built.

## Attempt 5 on development data (arena seeds)

Detection as attempt 1: 55 of 90 (water 22), none lost, HAI 20.07 37 of 38. Naming with the full
map 41 of 85 right, 2 wrong; with the trusted map 40 of 105 right, 7 wrong (ADR 0134: 0 and 21).
ICSSim: 20 of 20 liar events alerted; a liar named on 4 of 50 events where the readings are true.

## The confirmation (once)

| | Champion | Attempt 5 | Bar | Verdict |
| --- | ---: | ---: | --- | --- |
| Liar passes | 50 | **113** | More than the champion | Met |
| Water passes | 0 | **49** | — | — |
| Champion passes lost | — | 2 (batch 95205 at 0.8, power 95207 at 0.4) | None | **Fails** |
| Full map: right / wrong names, caught runs | — | 86 / 11 of 173 (50% / 6%) | ≥ 70% / ≤ 10% | **Fails** on right |
| Trusted map: right / wrong names | — | 83 / 22 of 193 (43% / 11%) | ≥ 70% / ≤ 10% | **Fails** on both |
| Band covers the truth | — | Water 99.9%, batch 95.5%, power 0.4% | ≥ 90% | **Fails** on power |

By plant, the pattern of every earlier slice repeats on seeds no rule has seen:

| Plant | Passes (champion) | Named right / wrong, full map | Trusted map | Band coverage |
| --- | --- | --- | --- | ---: |
| **Water** | **49 (0)** | **47 / 0 of 54** | **47 / 0 of 54** | **99.9%** |
| Power | 29 (26) | 0 / 0 of 60 | 10 / 0 of 60 | 0.4% |
| Batch | 35 (24) | 39 / 11 of 59 | 26 / 22 of 59 | 95.5% |

## Findings

- **The case the plant map was built for works, on unseen runs.** The water liar, where the
  controller follows the lie and the champion passes none, is caught in 49 of 60 runs, the right
  instrument named in 47 of 54 caught runs with no wrong name, and its true value inside the band
  on 99.9% of falsified samples.
- **The power plant is a different problem.** Its liar target, the feeder voltage, is held by a
  tap changer that follows the reading, and the map reconstructs it no better than chance (0.4%
  coverage). No naming rule fixes a reconstruction that is wrong.
- **Batch names consequences.** Upstream-first halves the full map's wrong names on development
  data, but on the confirmation seeds the trusted map still names a responding signal 22 times.
- **Both red teams fail by two runs.** Each time the challenger more than doubles the champion's
  passes and loses exactly two of about fifty. ADR 0123 §9.3 allows none, and the rule stands. Whether
  a two-run loss beside a sixty-run gain should be judged differently is a policy question, not a
  measurement, and only Elijah can open it, in its own record, before any further red team.

## Where ADR 0130 stands

| Falsifier | Verdict |
| --- | --- |
| 1. Grade C | Passes (ICSSim: 4 of 4) |
| 2. Grade B | Passes (ICSSim: 5 of 5, chance 58%) |
| 3. Grade D | Fails on water's recall (21%); precision far better than the full map's |
| 4. Naming on A–C | Fails pooled (43% right, 11% wrong); water alone 87% right, 0 wrong |
| 5. The water target placed | Passes |

## Decision

Nothing is promoted, gated or emitted. ADR 0129's restriction stands: detection only, no naming
or reconstruction shown to an operator. The remaining arena run (6) is left unspent. The next
steps need what this lab cannot produce alone: the power plant's failure is a reconstruction
problem to study on its own, the batch plant's a cause-versus-consequence problem, and grades A,
B and C on a real plant need a design partner's drawings, historian and traffic.
