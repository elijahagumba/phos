# The recipe log was there. Using it made Atlas louder.

**What this is:** the distillation column **does** publish a recipe step. Atlas **did**
route on it. False alarms went **up**, not down.

**Why it exists:** for a while the story was "we cannot try the batch-phase model until
someone finds a phase column." The column was in the operation logs the whole time
(`Executing step`: Heat, Distillation, and the rest). Preparation was not joining those
events, so the model that already exists for recipe-shaped plants never ran. That was a
join bug, not a missing idea.

## What the logs actually say

Each experiment can ship a small event file. When the plant's recipe engine names a step,
the row looks like `Executing step, Heat1`. Jump-if conditions, tank warnings, and "the
operator opened the recipe window" are **not** that. Some experiments only have the
operator-UI chatter. Those get a register value meaning **no named step**, not a guess.

The folder name `operating_point_001` is a second declared grouping key — which recipe
setpoint this run used. It is written as a column now and **stripped out** of the pooled
comparison so yesterday's 18.72 number does not quietly change meaning.

## What we measured (same split, same threshold)

Fit on the 15 dual-clean train experiments. Score the 63 test experiments. Seed 11,
threshold 3.0. **Perturbation recall, never attack recall.**

| Detector | Perturbation recall | False alarms per normal hour |
| --- | ---: | ---: |
| Pooled Mahalanobis (registers not used as signals) | 0.60 | **18.72** |
| One model per named recipe step | 0.75 | **235.64** |
| One model per operating point | 0.74 | **140.40** |

The pooled number **reconfirmed**. The recipe-step model catches more of the operator
knob-turns and pages about **twelve times** as often on healthy hours. The operating-point
model is the same shape, a bit less loud, still far worse than pooled.

Most training rows have **no** named executing-step: the Heat1–Heat9 events in the one
rich log sit *before* that run's sensor clock starts. An operating point usually has **one**
clean training experiment. Tight bands on a single laboratory run do not travel.

On our dummy batch reactor, pooling was *blind* (bands too wide). Here pooling already
sees the perturbations. Tightening the bands does not earn a quiet control-room queue.

## What this does not license

**2–3 alerts per day is still refused.** The missing-column excuse is gone. The authorized
model is louder. Raising dwell or the joint gate to hide that is still not allowed.

Lines are in `eval_runs/log.jsonl`. Decision: [ADR 0048](../docs/adr/0048-distillation-declared-phase-is-louder.md).
The first (loud, honest) pooled number is still [note 12](12-batch-distillation-todays-work.md).
