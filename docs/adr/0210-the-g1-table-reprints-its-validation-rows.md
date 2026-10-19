# ADR 0210 — The G1 table's one command checks development rows and reprints validation rows

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** v1 sprint, lane A, criterion A1
- **Depends on:** [ADR 0095](0095-g1-baseline-table.md),
  [ADR 0102](0102-the-clean-hai-run-and-where-atlas-loses.md),
  [ADR 0100](0100-grouped-g1-rows-and-where-atlas-loses.md)

## Context

Roadmap A1 is met when the table exists, marks each opponent checked or unchecked,
and regenerates with one command. `eval_runs/v1/g1-baseline-table.md` already
covers HAI 20.07, 21.03, 22.04, 23.05, BATADAL, batch distillation and Data4Cyber
with recall within budget, eTaPR and point-adjusted F1, for Atlas and the three
reproduced methods, each marked checked or unchecked. The command that used to
write that file, `scripts/measure_baseline_table.py`, still marked HAI 22.04 and
23.05 absent and would have opened HAI 21.03 and BATADAL. Those four corpora are
validation data. Their CSV payloads are not on disk. A second look at them is
forbidden. Running the old command would have replaced scored rows with absent
rows.

## Decision

The command is:

`uv run python scripts/measure_baseline_table.py`

It recomputes hai-20.07, batch-distillation and data4cyber from the files on disk
and checks every published field, including each file's scores, against
`eval_runs/v1/g1-baseline-table.json`. It rebuilds hai-21.03, hai-22.04,
hai-23.05 and batadal from that JSON. It copies the grouped section from the
committed markdown. It does not open a validation file. It writes the markdown
only when the rebuilt text is identical to the committed markdown, so no recorded
digit changes. It does not rewrite the JSON. It does not append the experiment log.

This run matched. The development rows agreed with the committed JSON, and git
shows no change to `eval_runs/v1/g1-baseline-table.md` or `.json`.

A1 is not met. The validation rows are reprinted from the committed JSON. They
are not regenerated from the corpora. Regenerating them would be a second look,
which this lane does not take. The grouped section, including the development
grouped rows, is reprinted with them for the same reason: that section is one
block and it contains validation corpora.

## Consequences

The old command can no longer mark HAI 22.04 or 23.05 absent. A later run that
disagrees with the committed development rows exits without writing. A1 stays
open until a command can recompute the validation rows from the files without
that second look. This record does not invent a number and does not retune a
detector.

## What would reverse this

A committed decision that opening the validation files to regenerate the G1 table
is allowed, followed by one run that recomputes those rows and matches the
committed digits. Editing the table to make the command look green does not.
