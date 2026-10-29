# Learning what normal looks like

**What this is:** the first things in PHOS that actually detect: models of *normal*, not blacklists
of *bad*.

**Why it exists:** you cannot notice a departure until you have a picture of ordinary operation —
and that picture must be learned on time that is **not** the exam.

## Study hall, then an unseen exam

Fitting (learning) and scoring (judging new moments) are **separate types** in code. An unfitted
model has no `score` method to call. That is not a style choice. It makes “accidentally testing on
the homework” a type error, not a late-night bug.

Splits refuse to put labelled attack time into the training half. If the usual 50/50 cut would have
swallowed an attack, the split moves. Analogy: you do not include the answer key in the revision
pack.

## Simple thermometers, on purpose

Before Atlas’s joint plant model, PHOS shipped baselines that **fail differently**:

- **Gaussian** — “how many standard deviations from the average?” Fast, familiar, and easily
  wrecked by a couple of absurd outliers that drag the average with them.
- **EWMA** — a moving average that forgets the distant past. It can track slow drift, and the same
  readings in reverse order can produce a different score (order matters).
- **IQR (Tukey’s fence)** — uses the middle of the data, so two insane spikes of 1000 in a series
  around 10 do not explode the “normal” band. A genuine move to 20 can be caught by IQR and
  **missed entirely** by Gaussian. On a count that is almost always the same integer, the fence
  collapses to that integer.
- **Empirical** — the band is read off the values that actually occurred, at the same thin tail
  a three-sigma bell curve claims (about 0.135% each side). A pile of identical gaps that the
  bell curve excludes can sit inside this band. The demo uses it for command behaviour
  ([the fifteen-second gap](47-the-fifteen-second-gap-was-ordinary.md)). The frozen public rows
  still use the Gaussian thermometer.

They exist so later, fancier models have something to beat on the **same ruler**, and so we can see
*how* a method fails.

## Per-key, with an honest fallback

Normal is often learned per (entity, signal) pair: this pump’s flow, not “flow in general.” If that
pair is unseen, the model may fall back to a feature-level baseline and **name the fallback in the
evidence** so nobody thinks it was a bespoke pump model. If even the feature is unseen, it emits
**nothing**. Silence is preferred to a made-up number.

## Confidence on this path

Early detectors squash scores into a 0–1 “confidence.” That squash was **measurably wrong** (ECE
around 0.5 on the simple methods). Calibration later takes a held-out slice, learns a mapping, and
is the only detector path allowed to show a probability to a user. The uncalibrated squash is kept
so we still have something to measure calibration *against*.

## What this is not

- Not Atlas’s joint model (that is the next chapter).
- Not a signature pack. None of these methods look up known attack names.
- Not permission to train on “mostly normal” files that annotators also marked as anomalous. That
  rule is [data hygiene](11-data-hygiene-and-label-disagreements.md).

## Where to read more

- Code: `src/phos/models/`
- Decision: [ADR 0005](../docs/adr/0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md)
- Calibration: [ADR 0007](../docs/adr/0007-the-evidence-boundary-and-a-calibrated-confidence.md)
