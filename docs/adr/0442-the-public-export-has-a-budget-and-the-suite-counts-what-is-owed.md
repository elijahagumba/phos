# ADR 0442 — The public export has a budget, and the suite counts what is owed

- **Status:** Accepted
- **Date:** 2026-11-15
- **PART:** Method. The door [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md) does not govern
- **Supersedes:** nothing. ADR 0044 stands; it governs the three surfaces inside the repository and this record governs the door out of it
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md), [ADR 0342](0342-commercial-records-are-not-published.md)

## Context

The lab is private. `github.com/elijahagumba/phos` is an export of the subset
`public/manifest.toml` allows, built by `scripts/export_public.py`, which never commits and never
pushes: a person reads the diff before the world does.

Nothing made the export happen. Between **2 and 15 November 2026** it did not run. By the time
somebody asked "what about the public repo", **24 decision records and 15 notes** were owed, and
ADR 0346 stood in the public tree as an 859-byte reservation stub telling a reader the packet
foundation was unjudged — which it had not been for ten days.

No rule was broken, because there was no rule. ADR 0044 requires `encyclopedia/`, `easy to reads/`
and `README.md` to move with every advancement **on `main`**, and says nothing about the export.
That gap is the whole of this record.

## What was found while settling it

Three failures this month have the same shape, and it is worth naming because the shape is the
finding:

- ADR 0348's verdict was built and merged on 29 October and sat on `main` unjudged for a week
  (ADR 0346).
- The ADR 0316 score was declared on 23 October and taken on 9 November, seventeen days later
  (ADR 0425).
- The public export went thirteen days.

Each was found by a person happening to look. None had a guard. The project's own method says the
record exists so a claim can be checked without trusting that somebody read something — and in all
three cases the thing that needed checking was whether a step had happened at all.

A day-based bar was considered and rejected. It reddens an unrelated change because a clock moved,
which is a check firing for a reason nobody caused, and a check like that gets raised until it is
quiet. A count of records owed only moves when somebody writes a record, so it reddens the change
that crossed the line, in front of the person who can act on it.

## Decision

1. **`public/last-export.json` records what the last real export published**: the lab commit, its
   committer date, the file count, and the sha256 of the manifest that selected it. It is written
   by `export_public.py` on a real export, never on `--dry-run`, and committed in the lab. It does
   not leave the lab — `include` does not match it — because the public repository's history is a
   separate chain of export commits that records nothing about where its contents came from.

2. **The export refuses an uncommitted exportable tree.** An export built from working-tree edits
   cannot be reproduced from any commit, so the marker it would write would name a commit that is
   not what was published. Dirt outside the exported subset is ignored: a modified `PROGRESS.md`
   or a scratch file under `data/` does not change what the public tree would receive. `--dry-run`
   is unaffected, so local checking still works.

3. **The budget is ten owed records, counted by the suite** —
   `tests/scripts/test_public_export_freshness.py`. A budget, not a target: the intended cadence
   is one export per programme. Ten is wider than a single programme's output, the plant generator
   being nine records (ADRs 0433–0441), and far inside the lapse this closes, which reached
   **forty-five** by this count. A tighter budget would fire during ordinary work and be raised to
   quieten it, which is the one failure this guard may not have. **Raising `OWED_BUDGET` to make
   the suite pass needs a record that supersedes this one**, and the failure message says so.

4. **Owed means added or changed, and numbered.** Changed and not merely added, because ADR 0346's
   stub-to-verdict was a modification and counting additions alone would have called that export
   complete. Numbered, because `docs/adr/README.md` and `easy to reads/README.md` move with almost
   every record and would put two on every cycle, making the stated budget two narrower than it
   reads.

5. **The withholding list keeps one home.** Owed records are filtered through the export's own
   `select`, so ADR 0334, ADR 0369 and note 132 — held back under ADR 0342 — are not counted. A
   second copy of that list in a test would be a second thing to drift.

6. **No assertion that the manifest still matches.** The marker carries the manifest's digest as
   provenance, and the suite checks only that it is a digest. Most manifest edits do not change
   what the published tree should contain: excluding a lab-only file the public tree never had is
   the very commit that added this guard. A gate there would fire with nothing owed, which is the
   failure Decision 3 is written to avoid.

7. **The marker is seeded by hand, once.** The 15 November export ran before this script could
   record it, so `public/last-export.json` was written from that export's own facts:
   `f39cb74`, `2026-11-15T14:55:15Z`, 1551 files, manifest `b2ad62c2…87a6d`. Every later marker is
   written by the script.

## What is not claimed

**This cannot see the public repository.** The core is offline (constitution §3.8), so the marker
is a claim the script makes about what it published, and drift is measured against that claim. A
hand-edited marker defeats the guard exactly as a hand-edited frozen row defeats a measurement
freeze. It is a guard against forgetting, not against lying.

It does not assert the public repository is correct, only that it is not far behind. A manifest
that publishes the wrong subset, a `forbidden` pattern that misses something, or an export pushed
and then force-replaced are all outside it; the content guard in `violations` is what refuses the
first two, and it runs before anything is written.

This is not a measurement. No corpus was opened, no score taken, no detector built,
`eval_runs/log.jsonl` was not appended, and no data file was committed. No frozen number moves and
v1 stays 8 of 12. P1 stays the blocked human conversation, with Intelligence, the API and the UI
closed behind it. ADR numbers 0277–0284 stay unwritten and H2's scoring stays closed until after
6 January 2027.

Four records are owed as this is written — ADRs 0421 and 0428 and notes 176 and 181, waiting on
their pull request — and the suite is green, which is the budget working rather than a gap in it.
