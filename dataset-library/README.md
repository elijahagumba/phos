# Dataset library

Synthetic evaluation corpora for Atlas (OT) and Sentiel (IT). **Not public data. Not a live plant. Not a live SOC.**

```
dataset-library/
  README.md                 <- this file
  OT/
    catalogue.json          <- committed: every labelled process/command window
    generated/              <- git-ignored payloads, regenerated from src/phos/library
  IT/
    catalogue.json          <- committed: personas and person-day counts
    generated/              <- git-ignored observations + entity-scoped labels
```

## What this is

PHOS already has a plant simulator (`phos.synth`) and a graded attack library (D2). This directory is a **combinatorial expansion** of that engine: three plants, three seeds, six points on the difficulty dial, process manipulations and command/mimic windows, plus a 48-person behavioural fixture for Sentiel.

Every catalogue and every `eval_runs/log.jsonl` row produced from these files carries the same caveats:

- These are attacks and personas **we designed**. A detection rate here is an upper bound on this library, never a lower bound on reality.
- A plant here is a **model**, not a plant (`MODEL_NOT_REALITY_CAVEAT`).
- IT rows are ontology `Observation`s (counts). They are not malware, not credential-theft tooling, and not CERT r3.1.
- **Do not quote these numbers as HAI / BATADAL / distillation / CERT recall.** Distillation perturbation recall is a different ruler. Public-corpus claims still need a confirmed licence and a harness row on that corpus.

## Generate and score

```bash
PYTHONPATH=src python scripts/generate_dataset_library.py
PYTHONPATH=src python scripts/evaluate_dataset_library.py
```

Telemetry is scored through `LabelledCsvAdapter` unchanged. Sentiel is scored through `evaluate_entity_aware` with entity-scoped labels. Reports append to `eval_runs/log.jsonl`.

## Cycle contract

The 2–3 Atlas alerts/day and Sentiel 30–50 alerts/day numbers are **not claimed** by generating this library. They are claimed only when a harness row on the relevant corpus says so.

Plain-English walkthrough: easy to reads/14 (lab record, not published).
