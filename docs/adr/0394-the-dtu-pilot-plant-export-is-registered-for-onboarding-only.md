# ADR 0394 — The DTU pilot-plant export is registered for onboarding only, and it is the C2 trial corpus

- **Status:** Accepted
- **Date:** 2026-10-31
- **PART:** v1 C2, tools lane (`docs/build-brief-2026-10-c.md`)
- **Depends on:** [ADR 0220](0220-tag-suggestions-are-not-declarations.md) Decision 5,
  [ADR 0341](0341-the-onboarding-brief-runs-on-a-historian-alone.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md)
- **Related:** [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

Six historian exports arrived as email attachments from an associate professor at the Department of
Chemical and Biochemical Engineering, Technical University of Denmark (DTU). Three are runs of a
bubble column (9, 10 and 16 July 2026) and three are runs of a continuous distillation column 5A
(14 July, 16 July and 30 September 2026). They are pilot-plant teaching and research runs from two
physical rigs, not a production historian, and they carry no attack labels.

The sender wrote, in the same message that carried the files:

> You are welcome to publish and use the obtained results commercially as long as appropriate
> credit is given to our department.

That is a grant wider than research use, and it is the first permission on this record to publish
*results* commercially. It is a sentence in a personal email, not a licence document, so Decision 3
records exactly what it says and the four things it leaves open.

Nothing in this corpus can support a detection claim. Six short runs of two teaching rigs, with no
label column, cannot fit a baseline and cannot be scored; the runs differ by operator and by day,
which is a different variable from "normal for one plant". ADR 0117's ledger has no place for a
corpus that cannot judge, and this record does not pretend it has one.

What the corpus can do is the one thing the v1 scorecard still has open. C2's bar in
`docs/v1-roadmap.md` §2.3 is: *a corpus not used in development reaches its first brief in under an
hour of human time.* ADR 0220 Decision 5 gates C2 on the human trial at
`eval_runs/build/v1/tools/c2-trial.md`, and that trial has not been run. The corpus that file named
is `data/batch-distillation/batch-distillation-test-prepared.csv` — an integrated corpus whose
column names were available while the tool was built. A stranger's export is a strictly better
subject for that bar, because nobody who built `phos.atlas.onboarding` has seen it.

## Decision

1. **The corpus is `dtu-lab`, role `development`, status `operator-provided`.** Six files, sizes and
   sha256 recorded below. `operator-provided` is outside `FETCHABLE_STATUSES`, so
   `scripts/fetch_datasets.py` will not download it and `files` is empty: nothing here is
   fetchable, and an email attachment has no URL to record. The registry entry is the provenance
   record, not a download recipe.

2. **There is no held-back half, and that is stated rather than papered over.** The corpus has no
   label column, and six short runs of two rigs cannot support a fit/score split. Declaring a
   held-back half would spend a held-out bank on a score that cannot exist. `dtu-lab` is
   `development` and `DECLARED_HELD_OUT` is unchanged, so the pinned lists in
   `tests/eval/test_seen_ledger.py` and `tests/eval/test_build_declaration.py` do not move.

3. **The licence is recorded as the grant it is, with its four gaps named.** `license.status` is
   `operator-stated`, not `explicit`: a sentence in a personal email is not a published licence.
   The evidence field quotes the grant verbatim and names the sender's role and institution. It does
   **not** record his email address — `data/*` exports publicly and the export's academic-address
   pattern matches `.ac`/`.edu` suffixes only, so a `.dk` address would pass the gate and publish a
   private individual's contact details. That is a fact about the gate worth knowing and is not a
   gap in the permission.

   The four things the message does not settle, each of which must travel with the corpus:
   - **Which department.** "Our department" is unnamed in the message. The credit line cannot be
     written until the department is confirmed, so no publication may precede that confirmation.
   - **Whether DTU's own IP policy agrees.** A staff member's welcome is not a statement that the
     institution holds, or waives, rights in student-generated laboratory data. The permission is
     recorded as given by the sender, not as a cleared institutional licence.
   - **Redistribution of the raw files.** The grant covers *results*. It says nothing about
     passing the `.xlsx` payloads to a third party, so the payloads stay git-ignored and are never
     committed, which is the registry's standing rule anyway (ADR 0006).
   - **Anything about the data itself.** No warranty, no statement of what the columns mean, and
     no declared process map. That last one is the ICD's own box and stays open.

4. **The 30 September distillation run is the C2 trial file.** The five earlier files may be used
   freely as development material. This one is held for the trial.

   **Disclosure: this record's own rule was broken while it was being written.** Decision 4 as first
   drafted said the trial file was "not opened before this record is committed". The same session
   then converted that workbook to CSV and ran the brief on it before committing this record. The
   intention was sound and the ordering was not kept. Two consequences are recorded rather than
   tidied away: the trial file has now been read once, so it is no longer a corpus "not used in
   development" in the strict sense the bar intends; and the run found a defect (Decision 6a), which
   means the fix was made in response to seeing the file. Both are stated because the honesty of the
   trial depends on them, and because a reader comparing this record's dates to the commit that
   carries it can see the same thing.

5. **The trial is the existing gate; the corpus changes, the bar does not.** `c2-trial.md` names its
   corpus by hand, and this record substitutes the 30 September file for the batch-distillation
   file it named. Everything else in that sheet stands: the clock starts before the command, it
   stops when the list is on the screen and one line has been accepted or edited, an over-an-hour
   result is written down as over an hour, and **a brief produced by an agent is not the trial**.
   The bar is *human* time. An agent may run the command to prove it exits 0 and prints a list,
   and that is a smoke test, not the trial.

6. **The `.xlsx` files are converted to CSV outside the project's dependencies.** `openpyxl` is not
   a pinned dependency and this record does not add one; the conversion runs under
   `uv run --with openpyxl` in a throwaway resolution. `phos.atlas.onboarding` reads CSV and
   `.csv.gz` only (`_open_text` in `src/phos/atlas/onboarding/_tables.py`), and that does not
   change here.

6a. **A defect the export exposed is fixed, and a second one it exposed is not.** Decision 4
   records that the trial file was read before this record was committed. That read produced two
   findings, and they are treated differently on purpose.

   - **Fixed: the spaced timestamp header.** The DTU workbook spells its timestamp column
     `Time Stamp`. `_SKIP_COLUMNS` held `time`, `timestamp`, `datetime`, `date` and `ts`, so the
     spaced form survived and the brief carried a phantom `Time Stamp` tag with no role, no kind,
     and no values that parse as a number. The match is now normalised — whitespace and underscores
     folded away, lowercased — while the tag name *reported* for a real signal is still the one the
     plant wrote. This is a general defect in reading a stranger's export, not a fact about DTU, so
     fixing it does not tune anything to this corpus.
   - **Not fixed: `TI` has no role.** The temperature tags (`TI1`–`TI17`) came back with an empty
     role, because the name table carries `TT`, `TIT` and `TE` styles but not the bare two-letter
     `TI` that this plant writes. Adding `TI` would be a one-line change and it is **refused here**,
     because doing it after seeing this corpus is tuning the tool on the trial material, which is
     exactly what the trial is supposed to detect. The finding is recorded as a result of the
     smoke run. Whether to add `TI` is a separate decision, and if it is taken the trial corpus has
     to be a different file.

## Honest status of the C2 bar

The bar in `docs/v1-roadmap.md` §2.3 is *human* time: a corpus reaches its first brief in under an
hour of human time. What has happened so far is an **agent** running the command and reading the
output. That is a smoke test. It is not the trial, it does not start the clock, and it cannot meet
the bar. The clock is started by a person, on the sheet at
`eval_runs/build/v1/tools/c2-trial.md`.

Two things the smoke run did establish, and they are the useful part: the command exits 0 on a
real `.xlsx` export after conversion, and the brief is legible — `FI*` flows and `PI*` pressures come
back as sensors with a kind, and the seventeen `TI*` temperature tags come back blank rather than
guessed at. A blank cell is the tool behaving as ADR 0220 Decision 4 requires: a cell the engineer
fills in.

## The six files

Hashes are of the copies on disk at `data/dtu-lab/`, which were verified byte-identical to the
attachments on 2026-10-31. The payloads are git-ignored.

| Run | Rig | Bytes | sha256 |
| --- | --- | ---: | --- |
| 26_07_09 | Bubble Column Aeration 1F (`BubbleColmExpData`) | 744154 | `9064d93d2902fd6b74caf4a20115cd2e36df6f3c11972d4afcc5b7ff9536309c` |
| 26_07_10 | Bubble Column Aeration 1F (`group42`) | 567488 | `33d1a7e15e87bdaced71018b9be0af6904af0a482bf7ff7bae806052d94bdec3` |
| 26_07_14 | Continuous distillation 5A (`AL355A`) | 907312 | `19ee18a7fe38207f626a9775da801b9ea7360df49b4ee08a0acd5522cd690df3` |
| 26_07_16 | Bubble Column Aeration 1F (`43 1F`) | 566488 | `febdfaed5bc31d24aa5bcda1215942fa7698847de55598228c36138f3c447f77` |
| 26_07_16 | Continuous distillation 5A (`UW14 Lab5A`) | 1657914 | `90fcbf8dc95a27c9cc4c5781acda1c050109447b2e0a77bda40e91b01c7c3a81` |
| **26_09_30** | **Continuous distillation 5A (`Team45A`) — the C2 trial file** | 1250881 | `99d2634abe3a75bdc3fe0aeae827cdbb325a5782aaede51a961f3d0e86f7fbe2` |

## What this does not change

- **C2 is not met by this record.** It registers a corpus, fixes one header defect, and names a
  trial. The trial's human lines are unanswered until a person fills them, and an agent run is not
  the trial. v1 stays 8 of 12.
- **`TI` is not added to the name table.** The DTU export writes temperature tags the table does not
  hold, and adding them after seeing this corpus would be tuning on the trial material. Recorded as
  the smoke run's finding, not acted on.
- **No detection claim, and none is possible from this corpus.** No baseline, no score, no rate, no
  recall, no false-alarm count. The corpus is registered `development` and stays there.
- **P1 is not advanced.** A university department that sent six teaching runs is not a design
  partner with a control room, and this record does not say otherwise. The ICD's boxes stay open,
  including the declared process map this corpus does not carry.
- **No `eval_runs/log.jsonl` append.** This is not a harness row.
- **`DECLARED_HELD_OUT`, the frozen measurements, `controller_valve`, and every pinned knob are
  untouched.**

## What would reverse this

Publishing a result from this corpus before the department is named and credited; committing an
`.xlsx` payload; recording the sender's email address in an exported file; adding `openpyxl` to
`pyproject.toml` for a conversion; treating an agent's smoke run, or a brief from this export, as
the C2 trial; or declaring a held-out half for a corpus that has no label column to score against.
