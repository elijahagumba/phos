# ADR 0268 — The build record reaches the public tree, and the scorecard link resolves

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** public repository CI; the public record
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0267](0267-role-files-reach-the-public-tree.md)

## Context

ADR 0267 said the public test job could pass once its tree was exported and the role files were
committed there. That export was made and pushed as public revision `ac458c6`. The job did not
pass. GitHub run 39428218185 reports **1 failed, 4365 passed, 43 skipped, 45 deselected**, down
from the 26 failures of run 39399903146. The surviving failure is
`tests/scripts/test_reproduce_v1.py::test_committed_pin_matches_the_checkout`, with
`FileNotFoundError` on `eval_runs/build/v1/tools/reproduce-pin.json`.

The file is present in the lab, is tracked there, and the export writes it into the public
checkout. `git check-ignore -v eval_runs/build/v1/tools/reproduce-pin.json` in that checkout
reports `.gitignore:7`, the bare `build/` of the Python section. It matches `eval_runs/build/` at
any depth, so `git add` skipped the whole tree.

The lab gitignore has carried the fix since the October build was declared: `build/` on line 7,
then `!eval_runs/build/` and `!eval_runs/build/**` with a comment naming ADR 0144.
`public/overlay/.gitignore` is a separate file and never received those two lines.

What that hid is not one pin. **94 files, 1.7 MB, all of them `.json`, `.md` and `.svg`, every one
tracked in the lab, had zero tracked counterparts in the public repository.** Among them is
`eval_runs/build/v1/REPORT.md`, the v1 scorecard that
`public/overlay/docs/bets/002-atlas-and-sentiel-v1.md` links from the sentence recording 8 of 12.
Fetching that path from `elijahagumba/phos` returns HTTP 404. The public front page cited a record
that was not published.

## Decision

1. **`public/overlay/.gitignore` un-ignores `eval_runs/build/` and everything under it**, in the
   two lines the lab file already uses, with a comment naming this record. Nothing else in the
   ignore list moves. `dist/` and `build/` keep their Python meaning everywhere else.
2. **The failing test is not made to skip.** ADR 0267's absent-pin skip was the right answer for
   files the manifest does not export. This pin is exported, is the record
   `scripts/reproduce_v1.py` reads, and sits in the same tree as the scorecard a public page
   cites. A skip would have left the 404 standing and called the job green.
3. **The 94 files are published.** They are results and records, not payloads: no `.csv`, no
   `.parquet`, no corpus bytes. The export guard ran over them before this record was written and
   refused nothing.

## Consequences

The public test job can pass on the next export. The scorecard link resolves, so the public claim
of 8 of 12 can be checked against the file it cites. Bet 001's result file,
`eval_runs/build/lane-a/bet-001.json`, is published for the same reason.

No measurement moved. No frozen row was touched. v1 stays at 8 of 12 (ADR 0264).

## What would reverse this

Ignoring the build record again, publishing a corpus payload under `eval_runs/build/`, or making a
test skip in order to turn a job green while a published page still cites a file that is not there.
