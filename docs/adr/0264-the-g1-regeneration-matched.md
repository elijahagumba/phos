# ADR 0264 — The G1 regeneration matched the committed table

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** v1 A1, the one regeneration
- **Depends on:** [ADR 0263](0263-the-g1-table-is-regenerated-once.md)

## Context

ADR 0263 was committed as `6d0d082`, and the path fix as `446dd62`, before this
run. The validation payloads were fetched from the registry URLs, checked against
the recorded sha256, and were not committed. BATADAL was prepared by
`scripts/fetch_datasets.py`. The command was:

```
uv run python scripts/measure_baseline_table.py
```

It exited 0. `git status` shows no change to `eval_runs/v1/g1-baseline-table.md`
or `.json`. Nothing was appended to `eval_runs/log.jsonl`.

## Decision

**The ungrouped G1 rows were regenerated from the files and they match.** That
includes HAI 21.03, HAI 22.04, HAI 23.05 and BATADAL. HAI 22.04 is still 5 of 58
for Atlas. HAI 23.05 is still 3 of 52. The grouped section of the markdown was
not rendered again. It is the committed block, copied because the headline
matched. Calling that block regenerated would reverse this record.

**A1 is met** on ADR 0210's own terms: one command recomputes the validation rows
and the digits match. The grouped block remains the committed copy.

A7 is not met. `scripts/reproduce_v1.py` now runs this command and then checks
the pin. The benchmark, A2 and consistency numbers are still checks, not
recomputations, and nobody outside the project has run the command.

C2 is not met. The trial sheet is blank.

v1 stands at 8 of 12: A1, A2, A4, A5, A6, C1, S1 and S2.

## What would reverse this

A second regeneration that does not match, or a claim that the grouped section
was recomputed in this run.
