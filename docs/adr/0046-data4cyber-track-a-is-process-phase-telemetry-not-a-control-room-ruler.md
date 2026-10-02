# ADR 0046 — Data4Cyber Track A is process-phase telemetry, not a control-room ruler

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Public process types, honest labels (sequence item 3)
- **Supersedes:** nothing
- **Amends:** [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)
  only in that Data4Cyber Track A is now *measured* as process telemetry. It does not amend what
  the corpus still cannot be (command-action windows; FP/hour control-room budget).
- **Depends on:** [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md),
  [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

Command-lead sessions 1–5 are complete. Session 5 refused a labelled public command corpus
(ADR 0040). The cycle still asks for genuine detection on ≥3 distinct public ICS process types
at a staffable ≤2–3 alerts/day-equivalent. HAI (water testbed) and batch-distillation (lab
column, budget refused) were the public plants. Data4Cyber is a licence-confirmed electrical
distribution grid. Its zip was already on disk for session-5 inspection. The labels are 1 Hz
**process phases**, not command-action windows. Aggregate normal CSV time is 5,880 seconds
(~1.6 h). S0 itself is ~30 minutes.

The question this record answers is not "did we hit 2–3/day?" It is: can Atlas read this grid
as Track A, with the labels as they actually are, without turning reconnaissance into command
ground truth and without quoting a false-positive rate whose denominator cannot support a
control room.

## Decision 1 — Join at preparation time; do not grow `LabelledCsvAdapter`

`phos.eval.data4cyber.prepare_corpus` writes two CSVs. The shipped adapter reads them
unmodified. That is ADR 0025 Decision 1 applied to a corpus that arrives as scenario folders
rather than a single table.

Fit **only** on `S0_benign_baseline`. Score **only** `S1_industroyer_pv` for this row. S2–S6
are different recordings and are not packed onto one clock (ADR 0025 Decision 2 taught why
voids between independent timelines flatter `normal_duration`). They are not this number.

The plant vector is S0's process columns. Named leak columns and any `Attacker.*` column are
dropped even if they parse as numeric. Train and test carry identical signal columns.

`attack_active` is used as shipped, including reconnaissance seconds. Those seconds are counted
on the prepare result (`n_reconnaissance_rows = 11` on S1) so a recall figure cannot pretend
they were held out.

Rejected: registering `format="pcap"` with `attack_intervals` copied from CSV clocks; feeding
`attack_phase` through `default_attack_when`; packing S0–S6 into one plant.

## Decision 2 — Designed protocol only

S0 and S1 are two independent ~30-minute recordings on different calendar days. A prefix
carved from S1 is not an attack-free learn stretch. A three-way split of S1 is not the
publisher's train/test. `scripts/evaluate_atlas.py` therefore skips prefix and three-way for
`data4cyber`. The only protocol that may be logged is **designed**: fit S0, score S1.

## Decision 3 — The number, and what it is not

Logged `data4cyber[designed]`, seed 11, threshold 3.0, `eval_runs/log.jsonl`. `git_commit` on
the row is `927bd9f` (HEAD when the row was written; Track A prepare was in the working tree).

| Detector | Window recall | FPs | FP/normal-hr | Precision |
|---|---:|---:|---:|---:|
| `model:gaussian` | 1.00 | 15,438 | 62,727.77 | 0.5068 |
| `model:atlas-pca` | 1.00 | 116,519 | 473,440.63 | 0.5051 |
| `model:atlas-mahalanobis` | 1.00 | 2,326 | 9,451.02 | 0.5701 |

Mahalanobis vs Gaussian at matched recall: **6.6×** fewer false positives. That is **not** a
10× claim. PCA lost (more FPs than the per-signal Gaussian), as on HAI.

Five `phase_seq` signals were constant in S0 and were dropped from the joint models (145 of
151 columns remained). S1 has **two** labelled windows (recon run; manipulation run). Window
recall 1.00 on n=2 is process-phase recall on `attack_active`, including 11 nmap seconds. It
is not command-action recall, not a graded public attack set, and not a field rate.

Precision ~0.57 sits next to a test slice that is ~51% attack rows (913/1,798). That is not
the high-confidence ≥0.6 contract, and it is not a staffable detector.

The FP/hour denominator on the test file is ~885 normal seconds (~0.246 h). 2,326 false
positives in that stretch is a flood. **Do not quote 9,451 FP/normal-hour as a control-room
budget.** ADR 0003's ruler still stands; this corpus cannot support it. Distillation 2–3/day
remains refused (ADR 0031). The ≥70% command-lead contract remains unearned (ADR 0040).
Known-station 0/16 and unknown-master 1/4 were not remeasured and were not pooled.

## Consequences

**Gained.** A third distinct public process type — electrical distribution grid — has a
designed harness row with honest label semantics. Confirmation is no longer why this plant is
untouched.

**Cost.** Cross-plant at ≤2–3/day is still unearned. The queue on this row is unusable. Joint
reduction on this corpus is 6.6×, not 10×, and must not be averaged with HAI 13.0× or
distillation 8.6× into a cycle claim.

**Rejected:** mapping process-phase clocks onto pcapng to invent command windows; quoting
prefix or three-way on this corpus; treating precision 0.57 as calibrated high-confidence;
growing `atlas/templates.py` to chase a quieter queue here.

## What would revisit this record

A declared command-action ground truth on a capture Atlas already dissects, with an
attack-free learn stretch long enough for ADR 0003, scored with issuer kinds apart. Until
that exists, Track B on this zip stays inspection, not a command row.
`test_real_dataset_labels_are_not_degenerate` still requires a normal-time fraction above 0.5 on HAI, BATADAL, and distillation — that is the BATADAL `-999` trap. S1 is ~51% `attack_active` as shipped (913/1,798 rows). That case pins a band `(0.45, 0.55)` so a 95% misread still fails. The global threshold is not weakened.

