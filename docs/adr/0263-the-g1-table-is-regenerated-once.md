# ADR 0263 — The G1 table is regenerated once from the files

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** v1 A1 and A7, before the validation files are opened
- **Depends on:** [ADR 0210](0210-the-g1-table-reprints-its-validation-rows.md),
  [ADR 0221](0221-the-v1-command-checks-the-record.md)

## Context

A1 is unmet because `scripts/measure_baseline_table.py` recomputes HAI 20.07, batch
distillation and Data4Cyber, and reprints HAI 21.03, 22.04, 23.05 and BATADAL from
the committed JSON (ADR 0210). A7 is unmet because `scripts/reproduce_v1.py` checks
checksums and does not regenerate (ADR 0221). Elijah asked for those two bars, and
for the C2 trial, to be finished. C2's pass is a person's timed reading of the
brief. This record does not fill that sheet.

The four validation corpora are not to be iterated on. This is one check that the
committed G1 digits come back out of the same readers. It is not a new score and
not a place to change a detector.

## Decision

1. **One command recomputes every G1 corpus.** `scripts/measure_baseline_table.py`
   reads HAI 20.07, HAI 21.03 (train1 and test1 through the integrated copies under
   `data/hai/`), HAI 22.04, HAI 23.05, BATADAL, batch distillation and Data4Cyber.
   HAI 22.04 and 23.05 use the clean-run reader. The others use the baseline reader.
   The grouped section of the markdown is still the committed block. A missing file
   is a refusal. The markdown is written only when the rebuilt text equals the
   committed file. Nothing is appended to `eval_runs/log.jsonl`.
2. **`scripts/reproduce_v1.py` runs that command, then checks the pin.**
   `--check-only` skips the recompute. The benchmark, A2 and consistency pins stay
   checks of the committed files. They are not rescored here.
3. **This commit is the declaration.** The validation files are opened only after
   it. The result, match or mismatch, is a later record. Payloads are not committed.

## Consequences

A1 is met only if that run matches the committed table. A7 is met only if one
command regenerates every pinned v1 number and someone outside the project has run
it. This command regenerates the G1 rows. It does not regenerate the benchmark,
A2 or consistency rows, and nobody outside the project has run it. C2 stays unmet
until the sheet in `eval_runs/build/v1/tools/c2-trial.md` is filled by a person.

## What would reverse this

Tuning a detector after a mismatch, editing a committed digit so the check passes,
or treating a copied grouped section as a regenerated one.
