# 45 — Teaching Atlas from ordinary days, not from the attack file

Note 40 found that Atlas's false alarms on HAI were modelling error: we had taught the plant model
from **twenty-nine minutes** of history because that was what the labelled file left after the
calibrator took its cut. Pointing the same model at sixty hours of ordinary running dropped the
alarms from thousands to under a hundred, at the same recall — and we deliberately did **not**
publish that quieter figure until the calibrator question was answered.

## What was stuck

The Atlas vertical's evidence weights come from an isotonic calibrator. That calibrator needs
examples of both "normal" and "attack" to fit. The long attack-free file has no attacks. So the
vertical splits the *labelled* file instead, and on HAI the attacks sit so early that almost none of
that file can be used for training. Short fit → wrong sense of normal → alarms on ordinary
operation.

## What landed

ADR 0083 shipped a **normal-score CDF** calibrator: it learns what ordinary magnitudes look like
from held-out attack-free data alone. That is a weight, not an attack probability — and the code
says so.

On HAI, same test slice as the frozen vertical, seed 11: **31** grouped alerts at **3.55** false
positives per normal hour, recall still **1.00**. That row is now in `eval_runs/log.jsonl` under
`hai[designed-normal-score][after]`, **beside** the frozen isotonic grouped row at 53.26 — not
instead of it.

On the batch-distillation plant, detection metrics stayed exactly where designed already was. Dual-
corpus success was not met.

---

**The short version.** We can teach Atlas from ordinary days without inventing attack labels. On
HAI that quiets the queue at the same recall, and that quieter figure is now logged under its own
name. On distillation it does not move the detector. 53.26 stays frozen.

*Record: ADR 0083. Log: `hai[designed-normal-score][after]`. Measurement:
`eval_runs/sandbox/adr0083-normal-score/`.*
