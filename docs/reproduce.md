# Reproduce the v1 numbers

One command recomputes the G1 baseline table from the files, then checks every pinned v1
number against the committed record and prints a pass or fail table. A row that matches says
`record intact`.

The recompute is the G1 table (ADR 0263). The benchmark, A2 and consistency numbers are
checked, not recomputed. v1's A7 asks for one command that regenerates every number, run by
someone outside the project. This command does not yet regenerate every number, and an
outside run has not happened, so A7 stays unmet (ADR 0230, ADR 0263).

## Install

You need Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/elijahagumba/phos.git
cd phos
uv sync
```

## Public datasets

You do not download anything to run the check. The committed records already name the corpora:

| Record | What it holds |
| --- | --- |
| `eval_runs/v1/a2-status.json` | Recall within budget for `atlas-v1-consistency` on HAI 20.07, HAI 21.03, HAI 22.04, HAI 23.05, and BATADAL |
| `eval_runs/v1/g1-baseline-table.json` | The G1 baseline table, including batch distillation and Data4Cyber |
| `eval_runs/benchmark/phos-benchmark-v1.json` | The public rulers: HAI Mahalanobis 646.58 false positives per hour, batch distillation 18.72, CERT 6B precision 0.104 at 48 alerts |
| `eval_runs/v1/consistency-batadal.json` | The committed BATADAL consistency score |
| `eval_runs/v1/consistency-identity-hai.json` | The committed HAI 22.04 and 23.05 identity check |

HAI 21.03, HAI 22.04, HAI 23.05, and BATADAL are validation corpora. The default command opens
them once, inside `scripts/measure_baseline_table.py`, to recompute the G1 table and check it
against the committed file (ADR 0263). It does not fetch them. `--check-only` does not open
them. Where those datasets are described for a person who wants the bytes themselves, the list
is `data/registry.json`.

## The command

From the checkout:

```bash
uv run python scripts/reproduce_v1.py
```

## How to read the table

The table has three columns: `status`, `record`, `detail`.

- `record intact` means the file is at the pinned path, its sha256 matches the pin in
  `eval_runs/build/v1/tools/reproduce-pin.json`, and every pinned digit in it matches. The G1
  recompute, when it ran, did not change those digits.
- `fail` means a checksum or a recorded digit does not match. The detail names the pointer, the
  digit in the file, and the pinned digit. The process exits with status 1.

A row with no digits, only a sha256, is a markdown twin of a JSON record. `sha256 ok` means that
file is unchanged.

Exit status 0 means every row is `record intact`. Exit status 2 means the pin itself could not
be read.
