# ADR 0114 — The liar measurement is assembled, and its held-out run is held

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1 T1, handover step 2
- **Depends on:** [ADR 0094](0094-liar-measurement-seeds-and-pass-share.md),
  [ADR 0108](0108-consistency-evidence-routes-to-the-explanations.md),
  [ADR 0109](0109-liar-subtlety-zero-is-the-obvious-end.md),
  [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md)

## Context

ADR 0094 fixed T1's seeds (94001–94020), plants, subtleties and pass share (strictly more than 180
of 360 runs). ADR 0108 gave Atlas the facet the predicate reads. The handover asked for the rest to
be declared (training runs, calibrator, engine assembly, comparison rows) and then for the 360 runs
to be scored once. Elijah delegated the choices in this record to Claude on 12 October.

## Decision

### 1. The assembly: `phos.breaking.liar`

- **Corpora.** One per plant and held-out seed: the plant's one library `LIAR` recipe
  (`phos.library.ot.liar_recipe`) at all six subtleties, laid out by the library's own
  process-pack layout (`lay_out`, prefix, 1.25 h gaps, tail, 30 s samples, traffic seed + 17).
  Sixty corpora, 360 runs. Six liars per corpus is what lets the harness split it into two folds.
- **Atlas.** As `phos.breaking.harness.run_breaking` assembles it, unchanged: the plant's joint
  model (`MahalanobisModel`, phase-conditional on batch) fitted on the library's attack-free
  corpus for that plant (train seeds 80001–80003, 48 h); the sensor calibrator cross-fitted on the
  other fold; the declared subsystem map; the OT templates; no prior moved.
- **The consistency inlet.** `phos.atlas.consistency` fitted on the same attack-free corpus, with
  ADR 0112's windows at 30 s (lags 0, 1, 2; events within 10 samples). Its calibrator is fitted
  once per plant on **development** liar corpora only, the library seeds 71001–71003, and applied
  unchanged to every held-out corpus. If those candidates hold one class, the plant runs without
  the inlet. Why not the harness's within-corpus cross-fit: see §2.
- **A run's competing set.** `phos.breaking.commands.rank_explanations`' rule: every hypothesis
  with supporting evidence timestamped inside the attack window. The predicate is ADR 0094's
  `liar_run_passes`, unchanged. An attack that straddles the fold boundary is unscored and does
  not pass.
- **Rows beside the pass share.** The same engine and calibrators without the inlet: the share
  whose unique contentful leader is `sensor_or_device_fault` (no citation can exist). And, for
  MinMax, Steadytime and Histogram fitted with the G1 defaults on the same attack-free corpus,
  whether any alert falls inside the window.

`tests/breaking/test_liar.py` covers the corpora, the leader rule, that the calibration seeds are
development seeds and not held out, and one development corpus end to end (`slow`).

### 2. What development seeds showed

Seeds 71001–71003 (calibration) and 4242 (test) are development seeds by ADR 0094's own list. No
held-out seed was generated, read or scored.

- **Within-corpus cross-fitting starves the inlet.** On power generation, seed 71001, every
  loop-carried candidate sits in the early fold (the obvious liars), so the late fold has none to
  calibrate on; the early fold's liars then run without the inlet. That is why the calibrator
  comes from development corpora. The choice was made after seeing this, on development data.
- **On seed 4242, 4 of 18 runs pass.**

  | Plant | Pass (inlet, cited) | Lead without the inlet | Inlet calibrator |
  | --- | --- | --- | --- |
  | water-treatment | 0/6 | 2/6 | none: no in-window candidate on 71001–71003 |
  | power-generation | 2/6 (subtlety 0.0, 0.2) | 0/6 | fitted |
  | batch-reactor | 2/6 (0.0, 0.4) | 4/6 | fitted |

  On power generation the inlet is the whole result: without it nothing leads.
- **Why water treatment fails.** On seed 71001 the falsified clearwell level's calibrated loop
  score peaks between 0.15 and 0.68 inside the six liars, against a threshold of 1.0, even at the
  obvious end; 152 cells outside the attacks cross it. Without detrending the peak reaches 2.0 at
  one subtlety. The liar holds a steady value a fixed deficit under setpoint, and a one-minute
  lag model detrended over the previous hour does not see a level that stops integrating its
  flows. Power generation's falsified voltage peaks at 12.3 (obvious) down to 0.8 (0.9).

### 3. The held-out run is held

At about 4 in 18 on development data, against a bar above 180 in 360, the 360 held-out runs would
most likely measure a gap already visible. The twenty held-out seeds are the only clean test T1
has. So the held-out run is **not** declared here, and no held-out corpus exists. It is declared
when a change, developed on development seeds only, gives a reason to expect a different answer,
or when Elijah decides to measure regardless. Either way the predicate, seeds and share stay
ADR 0094's.

## Consequences

T1 is unmeasured, with the reason recorded. The development figures above are synthetic (R4),
from four development seeds, and judge nothing. Work that would change them: a consistency model
that sees slow divergence (a longer lag or an integrating relation, as a new named detector, since
`atlas-v1-consistency` is frozen), and why the sensor path raises no evidence on power generation.

## What would reverse this

Generating, reading or scoring a held-out seed before a declaration; tuning anything on 94001–94020;
or reporting the development figures as a T1 result.
