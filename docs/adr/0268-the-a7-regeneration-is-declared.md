# ADR 0268 — The A7 regeneration is declared, and the benchmark is not part of it

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** v1 A7, the one command
- **Supersedes:** nothing
- **Depends on:** [ADR 0221](0221-the-v1-command-checks-the-record.md),
  [ADR 0230](0230-v1-stands-at-six-of-twelve.md),
  [ADR 0263](0263-the-g1-table-is-regenerated-once.md),
  [ADR 0264](0264-the-g1-regeneration-matched.md)

## Context

A7's frozen sentence, `docs/v1-roadmap.md` §2.1: "One command regenerates every v1
number, and someone outside the project has run it."

`scripts/reproduce_v1.py` regenerates the G1 table's ungrouped rows (ADR 0263) and
checks the other four pinned records by sha256 and digit. Checking is not
regenerating, and ADR 0264 recorded two further gaps: the grouped block of
`eval_runs/v1/g1-baseline-table.md` is the committed copy, and the A2, benchmark
and consistency records are checks. This record declares what the one command
regenerates, before it is run, and settles the part of A7 that cannot be met as
frozen.

## Decision

**1. What the command regenerates.** `uv run python scripts/reproduce_v1.py` runs
these producers in order, then prints the pin table:

| Producer | Record | Corpora it opens |
| --- | --- | --- |
| `scripts/measure_baseline_table.py` | `eval_runs/v1/g1-baseline-table.json` and `.md`, **including the grouped block** | hai-20.07, hai-21.03 (with `hai`), hai-22.04, hai-23.05, batadal, batch-distillation, data4cyber |
| `scripts/measure_a2_status.py --compare` | `eval_runs/v1/a2-status.json` and `.md` | hai-20.07, hai-21.03 (with `hai`), hai-22.04, hai-23.05, batadal |
| `scripts/measure_consistency_batadal.py --compare` | `eval_runs/v1/consistency-batadal.json` and `.md` | batadal |
| `scripts/measure_consistency_identity.py --compare` | `eval_runs/v1/consistency-identity-hai.json` and `.md` | hai-22.04, hai-23.05 |

The baseline-table command writes only when the rebuilt markdown equals the
committed markdown. `--compare` writes nothing at all: it recomputes, compares to
the committed file, and reports the first difference. **A mismatch is the result.**
It is not fixed, and no committed digit is edited to make the command pass.
`--check-only` runs no producer and opens no corpus.

**2. The benchmark is not regenerated, and A7 is therefore not met as frozen.**
`eval_runs/benchmark/phos-benchmark-v1.json` carries three numbers that are
constants in `src/phos/eval/benchmark.py`, not computations:
`HAI_MAHALANOBIS_FP_PER_HOUR = 646.58` (line 58),
`DISTILLATION_UNGATED_FP_PER_HOUR = 18.72` (line 64) and
`CERT_SIX_B_PRECISION_AT_48 = 0.104` (line 68). `scripts/evaluate_phos_benchmark.py`
cites them and refuses unsupported cells. Roadmap §5 rule 2 says those rows stay
frozen and that a new result takes a new name, so recomputing them under their own
names would not regenerate these rows — it would create different ones beside them.

That is a conflict inside v1's own rules, and this record resolves it the only way
that does not move a criterion after the fact: **the benchmark record is checked,
not regenerated, and A7 as frozen is not met.** Roadmap §5 rule 1 forbids rewording
a criterion after a measurement it judges, so "every v1 number" is not narrowed to
the records that do regenerate. A7 stays unmet for two independent reasons — this
one, and that nobody outside the project has run the command.

**3. The CERT row is not opened at all.** Regenerating the 0.104 row would need
CERT, whose payload licence is the restrictive end-user agreement in
`data/registry.json` (`payload_license`), with roadmap §4's lawyer question still
open. The command does not open CERT, by any path, and does not read the trace
caches.

**4. The validation exception.** This run opens hai-21.03, hai-22.04, hai-23.05 and
batadal. `docs/rules/data-tiers.md` is amended in the same commit as this record to
name a third exception: these four producers, scored once, nothing tuned on the
result. ADR 0263's G1 exception is spent and is not reused for this.

**5. Not in scope.** `eval_runs/log.jsonl` is not appended. No frozen row is
overwritten. No threshold, parameter or window is touched — A6's one configuration
is unchanged. The C2 trial sheet is not filled by this record.

**Command, run once after this record is committed:**

```
uv run python scripts/reproduce_v1.py
```

**Result name.** `v1-reproduce:a7-regeneration`. The verdict is its own ADR and
reports, per record, whether the recompute equalled the committed file.

## Consequences

After the run, one command regenerates four of the five pinned v1 records from the
files and checks the fifth. A7 still fails its own sentence, and the verdict says so
rather than claiming a pass. What would make A7 reachable is a decision about the
three frozen benchmark constants, which is a change to v1's rules and belongs to
Elijah, not to this record.

## What would reverse this

Editing a committed digit so the command passes, recomputing a frozen benchmark row
under its existing name, opening CERT from this command, reusing ADR 0263's spent
exception, or reporting A7 as met because four records of five regenerate.
