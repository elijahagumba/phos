# Reproduce the v1 numbers

One command checks every recorded v1 number in this checkout against the committed record and
prints a pass or fail table. It does not recompute those numbers. A recompute would open the
validation corpora and would take hours, so a passing row says `record intact`.

This is a check of the record, not a reproduction. v1's A7 asks for one command that regenerates
every number, run by someone outside the project; this command does not regenerate, so running it
does not meet A7 (ADR 0230). It tells you whether the committed numbers are the ones the record
pins.

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

HAI 21.03, HAI 22.04, HAI 23.05, and BATADAL are validation corpora. This command does not open
them. It checks the digits in the files above. Where those datasets are described for a person
who wants the bytes themselves, the list is `data/registry.json`. This command does not fetch it.

## The command

From the checkout:

```bash
uv run python scripts/reproduce_v1.py
```

## How to read the table

The table has three columns: `status`, `record`, `detail`.

- `record intact` means the file is at the pinned path, its sha256 matches the pin in
  `eval_runs/build/v1/tools/reproduce-pin.json`, and every pinned digit in it matches. Nothing
  was rescored.
- `fail` means a checksum or a recorded digit does not match. The detail names the pointer, the
  digit in the file, and the pinned digit. The process exits with status 1.

A row with no digits, only a sha256, is a markdown twin of a JSON record. `sha256 ok` means that
file is unchanged.

Exit status 0 means every row is `record intact`. Exit status 2 means the pin itself could not
be read.
