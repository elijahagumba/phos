# C2 morning trial

The pass bar is unchanged, from `docs/v1-roadmap.md` §2.3:

> A corpus not used in development reaches its first brief in under an hour of human time.

This trial has not been run. Running the tests does not meet the bar. Do not open `hai`, `hai-21.03`,
`hai-22.04`, `hai-23.05`, or `batadal`.

The tool was built on hand-written fixtures and on the column names in `data/hai-20.07/roles.toml`.
Those files do not count. This session did not open the file below.

## Before the clock

Work in `~/dev/phos` on `main`. The onboarding command is `python -m phos.atlas.onboarding`.
Python 3.12 and uv are already what this checkout uses. If `uv run` cannot import `phos`, run
`uv sync` once you have started the clock. An agent confirmed on 20 October 2026 that the command
below exits 0 and writes a brief. That confirmation is not this trial, and it does not start
the clock.

## Start the clock

Start it before the next step, and leave it running through the accept-or-edit.

## File

Historian (wide CSV, one column per tag):

`data/batch-distillation/batch-distillation-test-prepared.csv`

If that file is not on disk, stop. Do not substitute a validation corpus. Write "file absent" on
the sheet and stop the clock.

Capture: this command reads a CSV of tag references, not a pcap. Batch distillation has no such
table in this trial. Create one with only a header:

```bash
printf 'tag,access,count\n' > /tmp/c2-capture.csv
```

An empty capture means the brief has no wire evidence. If you already have a tag-reference table
for this corpus, point `--capture` at that file instead of creating this one.

## Command

From `~/dev/phos`:

```bash
uv run python -m phos.atlas.onboarding \
  --historian data/batch-distillation/batch-distillation-test-prepared.csv \
  --capture /tmp/c2-capture.csv \
  --sample-rows 500 \
  --out /tmp/c2-brief.tsv
```

The command reads the header and at most 500 data rows. It does not score a detector, does not
open a network connection, and does not start an agent. Suggestions are not declarations
(ADR 0123, ADR 0220).

## First brief

The first brief is the printed list: one line per tag, columns `tag`, `role`, `kind`, `evidence`.
The same list is in `/tmp/c2-brief.tsv`. A blank role or kind is a cell the tool would not guess.
You can accept a line as printed or change its role or kind.

## Stop the clock

Stop when that list is on the screen and you have either left one line as printed or changed one
line. Do not wait until every tag is reviewed.

If the list is not on the screen within 60 minutes, stop at 60 and write "over an hour".

## Sheet

Fill this in when you stop. Until these lines are filled, the trial has not been run.

- Clock start:
- Clock stop:
- Elapsed:
- Line accepted or edited (tag, and whether you kept or changed it):
- Under one hour: yes / no
