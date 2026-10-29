# How we keep score

**What this is:** the ruler. Every detection claim in PHOS has to pass through the same evaluation
harness.

**Why it exists:** a model that “looks good” on a slide is easy. A model that is honest about missed
incidents **and** operator load is harder. The harness exists so those two cannot be mixed up.

## Catching the burglary, not every footstep

**Recall** here is mostly **window-level**. If an attack (or a labelled perturbation) lasts twenty
minutes, we ask: *did we raise an alert that overlaps that window?* Catching the incident once is
what matters. Counting every noisy second inside it as a separate “hit” inflates the score without
helping an operator.

Analogy: the police need to know a burglary happened. They do not get extra credit for photographing
every shoeprint.

## False alarms per quiet hour — the fire-alarm budget

A detector that flags constantly will show high recall and still be useless. So false positives are
counted **per hour of labelled-normal operation**, not as a vague percentage of rows.

Analogy: a fire alarm is judged by how often it screams when there is **no fire**, during ordinary
days. If you secretly insert empty overnight hours into the calendar — hours with no sensors at all
— the rate looks quieter than the building really is. That trick is forbidden. (It comes back in
[the distillation join](12-batch-distillation-todays-work.md).)

Industrial target, as a contract rather than a claim already earned: about **2–3 actionable
alerts per day** under normal traffic. Enterprise (Sentiel) target: about **30–50 per day** at SOC
scale. Numbers measured so far are often far louder. After a joint-distance gate, the distillation
column is still about **49 alerts/day-equivalent**, at half the perturbation recall of the ungated
joint model. That budget claim is **refused** on distillation until a declared phase exists
([ADR 0031](../docs/adr/0031-distillation-budget-refused-without-declared-phase.md)).
[Quieter queues](13-quieter-queues-and-honest-ranking.md) records the gated row. The gap is
reported, not rounded away.

## Calibration — a weather forecast that means what it says

If a weather app says “70% chance of rain,” it should rain on about seven of ten such days. That
match between *said probability* and *what happened* is **calibration**.

PHOS measures this with expected calibration error (ECE) and Brier score. A raw model score
squeezed into 0–1 is **not** a user-facing confidence. Constitution rule: only a calibrated
probability may be surfaced, and hypothesis confidences are still **not** in that state for the
reasoning layer. Evidence weights, separately, can be.

## One adapter, many corpora

Real plants arrive as CSVs (or as trees that we **prepare into** CSVs). A synthetic generator exists
for tests. Both go through the same adapter interface so the harness never learns a private format
for “the HAI dataset” versus “the distillation dataset.” The packed
[dataset library](14-the-dataset-library-is-not-a-public-corpus.md) uses that same CSV adapter.
Library recall is still **not** public-corpus recall.

## What this is not

- Not a licence to quote paper-described labels when the files disagree. Files win
  ([data hygiene](11-data-hygiene-and-label-disagreements.md)).
- Not a claim that high recall on a toy synthetic spike is a product result. Early Gaussian numbers
  on a 25-sigma injected bump were a **smoke test of the machinery**.

## Where to read more

- Code: `src/phos/eval/`
- Decision: [ADR 0003](../docs/adr/0003-window-level-recall-and-false-positives-per-normal-hour.md)
- Experiment log: `eval_runs/log.jsonl` (each line carries seed and git commit)
- Latest distillation and SOC scoring notes: [quieter queues](13-quieter-queues-and-honest-ranking.md)
- Packed synthetic campaign: [the dataset library](14-the-dataset-library-is-not-a-public-corpus.md)
