# ADR 0269 — The A7 regeneration matched every record it rebuilds; A7 stays not met

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** v1 A7, the one run
- **Supersedes:** nothing
- **Depends on:** [ADR 0264](0264-the-g1-regeneration-matched.md),
  [ADR 0268](0268-the-a7-regeneration-is-declared.md)

## Context

ADR 0268 was committed as `dad1890` before this run, with the third validation
exception added to `docs/rules/data-tiers.md` in the same commit. The payloads were
read from the lab's own `data/` through symlinks and were not committed. CERT has no
payload in this checkout at all, so the command could not have opened it. The
command, run once:

```
uv run python scripts/reproduce_v1.py
```

It exited 0.

## Decision

**Four records were rebuilt from the files and all four matched.**

| Record | Rebuilt from | Result |
| --- | --- | --- |
| `eval_runs/v1/g1-baseline-table.json` and `.md` | hai-20.07, hai-21.03, hai-22.04, hai-23.05, batadal, batch-distillation, data4cyber | matched, **including the grouped block** |
| `eval_runs/v1/a2-status.json` and `.md` | the five judging corpora | matched |
| `eval_runs/v1/consistency-batadal.json` and `.md` | batadal | matched |
| `eval_runs/v1/consistency-identity-hai.json` and `.md` | hai-22.04, hai-23.05 | matched |

The pin table then printed `record intact` on all ten rows: 54 digits across the five
JSON records, and a sha256 on each of the five markdown twins.

**The grouped block is no longer a copy.** ADR 0264 recorded that the grouped section
of the G1 markdown was the committed text, copied because the headline matched, and
that calling it regenerated would reverse that record. It is now rendered from
recomputed scores and it matched: grouped Atlas 5 of 58 on hai-22.04 against grouped
MinMax 10, and 5 of 52 on hai-23.05 against 6. That caveat on A1 is closed. The
ungrouped rows are unchanged — hai-22.04 Atlas 5 of 58 and hai-23.05 3 of 52 — and
nothing about A1's verdict moves, since A1 was already met.

The figures the run recomputed, for the record: ungrouped Atlas 5/58 on hai-22.04,
3/52 on hai-23.05, 5/5 on batadal, 26/126 on batch-distillation, 1/2 on data4cyber;
A2's recall within budget 37/38 on hai-20.07 and 42/50 on hai-21.03. Every one is the
committed digit. No frozen row was rewritten and no new result name was created.

**Nothing was written.** `git status` shows no change under `eval_runs/`.
`eval_runs/log.jsonl` still holds 185 rows and was not appended. `--compare` writes
nothing by construction, and the baseline-table command writes only when the rebuilt
text equals the committed text.

**A7 is not met.** Both reasons ADR 0268 gave stand, and this run changes neither:

1. The benchmark record is checked, not regenerated. Its three headline numbers are
   constants in `src/phos/eval/benchmark.py`, and roadmap §5 rule 2 keeps those rows
   frozen with new results taking new names, so there is no way to regenerate them
   under their own names. A7 asks for every v1 number. Four records of five is not
   every, and the sentence is not narrowed to fit what works.
2. Nobody outside the project has run the command.

**v1 stands at 8 of 12.** Met: A1, A2, A4, A5, A6, C1, S1, S2. Not met: A3, A7, S3,
C2. C2 is the only row still reachable before the 24 January freeze, and it needs a
person at a keyboard for a timed trial.

## Consequences

One command now rebuilds four of the five pinned v1 records from the corpora and
checks the fifth, and an outside runner would need only Python, uv and the four
openly licensed corpora to do the same — CERT is not on that path. A7 is unreachable
as written unless Elijah decides something about the three frozen benchmark
constants, which is a change to v1's own rules and is not this record's to make.

## What would reverse this

A second run that does not match, editing a committed digit so the command passes,
recomputing a frozen benchmark row under its existing name, or reporting A7 as met
because the records that can regenerate did.
