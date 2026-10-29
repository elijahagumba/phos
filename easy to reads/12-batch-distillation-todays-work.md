# The distillation column: first number

**What this is:** taking a **real laboratory batch-distillation plant** from a licence check to a
**logged baseline**, on **one mixture family only**. The quieter-queue work that followed is
[the next note](13-quieter-queues-and-honest-ranking.md).

**Why it exists:** Atlas had been measured on published **water** plants (HAI, BATADAL) and on a
**simulator PHOS wrote**. Every cross-plant claim — different process types, a false-alarm budget
that survives more than one recipe — was blocked on missing data, not on a missing model. A real
batch column is also the only public check on the [phase and settling fixes](09-when-the-recipe-changes.md)
that were tuned on our own dummy plant.

This note covers two commits in sequence: intake and rules (ADR 0024), then join and the first
number (ADR 0025).

## What we brought in

- **Corpus:** Batch distillation data from RPTU Kaiserslautern-Landau, plant M-202210, Zenodo
  **version 1.1.2** (record `21535243`), licence **CC-BY-4.0 confirmed on two surfaces** (Zenodo
  licence field and the descriptor paper).
- **Size discipline:** the deposit is ~95 GB including audio and images. PHOS fetched the **47.5 MB**
  of labels, sensors, actuators, and plant metadata it can actually read.
- **One mixture only:** `ternary_butan-1-ol+propan-2-ol+water`. A number here is **not** a
  cross-recipe claim.

## Teaching from the healthiest hours only

Two label sources (a per-row CSV and YAML notes) **disagree** on which training experiments are
clean. Atlas **fits only on the 15 experiments both call clean**, out of 38 `train_normal` files
in this mixture. Thirteen YAML-contaminated “normal” files are prepared separately and **were not
scored** in this baseline. Missing YAML on train is treated as contaminated: absence of a note is
not proof of health.

When this note was written, non-zero row labels (1, 2, 3) all counted as anomalous and their
meanings were unverified. **Update (ADR 0082):** the paper names them as phases of one disturbance.
1 is the *blind* phase: the disturbance has started but no sensor shows it yet. 2 is the
*anomalous* phase: it shows. 3 is *recovery*: the cause is gone but the effects linger. Only 2 now
counts as something Atlas should catch. 1 and 3 are set aside: an alarm there is neither right nor
wrong, and that time is not counted as quiet, normal running either. Counting it as normal would
have added about 14 hours of disturbed plant to the "normal hours" every false-alarm rate is
divided by. The numbers quoted below were measured under the old rule and have not been re-run.

## Joining without cheating the ruler

The corpus arrives as a **tree of experiments**, not one CSV. Preparation **joins** sensors,
actuators, and labels on `Time` (inner join, so ragged empty tails cannot become fake attacks),
writes ordinary labelled CSVs, and leaves the existing CSV adapter **unchanged**. YAML is a
string check, not a new YAML library.

**Packed clock, not a fake calendar.** Giving each experiment its own calendar day would insert
empty days between runs. Those empty days would inflate “hours of normal operation” and make false
alarms look ~20× rarer than the traffic supports — like counting the museum as “quiet and safe”
all night with the cameras off. Experiments are laid end-to-end from `1970-01-01`, with a
**seam row** (labelled normal, **no sensor values**) between them so a perturbation at the end of
one run cannot glue to the start of the next.

**Stride 10** (keep every 10th row), same practicality HAI needed. The shortest labelled run is
11 seconds; all **131** perturbation windows survive. A stride that would erase a window is
**refused**.

The honest split on this corpus is the publisher’s **designed** train/test, not “the first half of
the packed file in sort order.”

## The first number (designed protocol)

Fit: 15 dual-clean experiments, 338,024 observations after stride.
Score: 63 test experiments, 1,227,662 observations, **131 windows**, **73.13 hours** of
labelled-normal operation. Threshold 3.0, seed 11.

**This is perturbation recall, never attack recall.** The knobs were turned by the plant’s own
operators.

| Detector | Perturbation recall | False alarms per normal hour | Precision |
| --- | ---: | ---: | ---: |
| Per-signal Gaussian | 0.92 | 160.55 | 0.549 |
| Atlas PCA | 0.86 | 655.43 | 0.515 |
| Atlas Mahalanobis (joint) | 0.60 | **18.72** | 0.740 |

Mahalanobis is about **8.6× quieter** than the Gaussian and pays for it in recall (0.92 → 0.60).
PCA loses, as it did on HAI. Four signals were constant in the fit set and sit outside the joint
model: `AV709`, `AV716`, `LS702`, `P301`.

Lines are in `eval_runs/log.jsonl`. Re-run:
`uv run python scripts/evaluate_atlas.py batch-distillation --protocol designed`.

## What this number does not license

**18.72 false alarms per normal hour is about 449 alerts per day-equivalent.** The sprint budget
is **2–3 actionable alerts per day** (~0.1 per hour). The joint model is quieter than the
univariate baseline and still about **150× too loud**. 8.6× is the measured reduction, **not** a
10× claim, **not** cross-plant generalisation, **not** command ranking, **not** calibrated
hypothesis confidence, **not** phase-conditional modelling on this corpus yet.

ADR 0018 (per-phase models) is no longer blocked on a missing column. The operation logs
declare `Executing step`. Scoring that register **raised** recall and **raised** false
alarms ([ADR 0048](../docs/adr/0048-distillation-declared-phase-is-louder.md),
[note 20](20-the-recipe-log-made-atlas-louder.md)). The 2–3/day budget is **still refused**.
What shipped without the register is a **distance gate** on the pooled joint model: quieter
(~49 alerts/day-equivalent at the moment unit) and **half the perturbation recall**. That
story, and what it still is not, is
[quieter queues](13-quieter-queues-and-honest-ranking.md).

## What you can assume exists now

- Join/prepare: `src/phos/eval/batch_distillation.py`
- Registry status `integrated`; committed `data/batch-distillation/manifest.json`
- Decision records: [ADR 0024](../docs/adr/0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md),
  [ADR 0025](../docs/adr/0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md)
- Engineering log: `PROGRESS.md` PART C2

The other two mixture families in the deposit are untouched. That is scope, not forgetfulness.
