# Reproduce the v1 numbers

One command rebuilds four of the five pinned v1 records from the corpora, then checks every
pinned number against the committed record and prints a pass or fail table. A row that
matches says `record intact`.

What it rebuilds (ADR 0268): the G1 baseline table including its grouped block, the A2
status, and both consistency records. The first writes only when the rebuilt text equals the
committed text; the other three run under `--compare` and write nothing at all. **A mismatch
is the result** — it is not something to fix, and no committed digit is edited to make the
command pass. On 20 October all four matched and all ten rows printed `record intact`
(ADR 0269).

What it does not rebuild: `eval_runs/benchmark/phos-benchmark-v1.json`. Its three headline
numbers are constants in `src/phos/eval/benchmark.py` — HAI Mahalanobis 646.58, batch
distillation 18.72, CERT 6B precision 0.104 at 48 alerts — and the project's own rule keeps
those rows frozen, with any new result taking a new name. So they cannot be regenerated under
their own names, only checked.

v1's A7 asks for one command that regenerates *every* number, run by someone outside the
project. Four records of five is not every, and no outside run has happened, so **A7 is not
met** (ADR 0268, ADR 0269). Narrowing the sentence to the records that do rebuild would be a
pass bought by rewording, which roadmap §5 forbids.

You do not need CERT to run this command, and it will not open it.

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
them, inside the four producers ADR 0268 names, to rebuild those records and check them against
the committed files. Each such look is declared by commit beforehand and taken once; ADR 0263
covered the G1 table, ADR 0268 covers this wider rebuild. It does not fetch them.
`--check-only` runs no producer and opens no corpus. Where those datasets are described
for a person who wants the bytes themselves, the list is `data/registry.json`.

## The command

From the checkout:

```bash
uv run python scripts/reproduce_v1.py
```

## How to read the table

The table has three columns: `status`, `record`, `detail`.

- `record intact` means the file is at the pinned path, its sha256 matches the pin in
  `eval_runs/build/v1/tools/reproduce-pin.json`, and every pinned digit in it matches. The
  rebuilds, where they ran, did not change those digits.
- `fail` means a checksum or a recorded digit does not match. The detail names the pointer, the
  digit in the file, and the pinned digit. The process exits with status 1.

A row with no digits, only a sha256, is a markdown twin of a JSON record. `sha256 ok` means that
file is unchanged.

Exit status 0 means every row is `record intact`. Exit status 2 means the pin itself could not
be read.
