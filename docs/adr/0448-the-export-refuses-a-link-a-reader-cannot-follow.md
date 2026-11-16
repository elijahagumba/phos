# ADR 0448 — The export refuses a link a reader cannot follow

- **Status:** Accepted
- **Date:** 2026-11-16
- **PART:** Public record
- **Supersedes:** nothing
- **Depends on:** [0443](0443-the-front-page-is-shortened-and-the-contracts-pins-follow-it.md), [0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md), [0395](0395-the-chart-records-module-is-exported-so-the-chart-test-can-run.md), [0381](0381-the-front-door-is-corrected-and-the-freeze-opens-for-figures.md)

## Context

ADR 0443 shortened the public front page. In reviewing what the shortened page left behind, the
exported record page was found to be showing a broken image: it pointed at
`record-plate.svg`, and the committed asset had been renamed to `record.svg`. The reference was
nine commits old and had been exported, pushed and read by anyone who opened the public record
page in between.

The export had no way to notice. `scripts/export_public.py` checked two things before writing —
forbidden paths and forbidden content — and both are about what must not leave. Nothing checked
that what did leave still held together. The lab can link to a file the manifest does not export,
and the public page is where that stops being true, so the export is the only place the check
belongs.

The figure builders are the reason the name drifted. `public/figures/build_figures.py` writes an
eight-card `*-plate.svg` family — `hero-plate.svg`, `record-plate.svg` and six more — under names
the overlay no longer uses, and the committed assets were renamed by hand at `35e0e1d` without
the builder following. That builder needs `fontTools`, which this environment does not have, so
its output could not be compared to what is committed and its names were **not** changed here. A
guess at which drawing belongs under which name would be worse than the drift.

## Decision

1. **A dangling relative target refuses the export.** `dangling` reads every exported markdown
   file and resolves each relative link and image against the exported file set. A target that
   names nothing exported, or that climbs out of the export, stops the export before anything is
   written, in the same place and the same way as a forbidden-content hit. External links,
   fragments and `mailto:` are not the export's business and are not checked.

2. **An unreferenced image is reported, not refused.** `unreferenced` lists exported images no
   exported page points at. Dead weight is not a broken page, and an asset committed before the
   page that will show it is ordinary. The export prints each one and exits 0.

3. **The unreferenced set is named in a test rather than driven to zero.** Being unreferenced by
   prose is not being unused. Nine images are carried on purpose and
   `tests/scripts/test_export_public.py` names each with its reason: the three marks, the two
   charts the shortened page stopped showing, and the four measurement figures whose records cite
   them in prose rather than as links. A tenth entry fails the test.

4. **Six broken targets are fixed, and nine dead images are removed.** The record page points at
   `record.svg`. The front page's Discussions link is written as its URL, because
   `../../discussions` is a GitHub web idiom and not a path in the repository. Four decision
   records — 0395, 0397, 0398 and 0416 — linked sibling records by filenames nobody had read:
   `0267-the-public-test-job-runs-a-fresh-clone.md`, `0316-the-joint-command-vector-is-declared.md`,
   `0112-a-window-is-a-span-of-seconds.md` and `0143-the-gate-look-is-spent.md`. Every one of those
   four numbers is a real record under a different title, so only the link target changed. No
   claim, number, bar or verdict in those four records was touched.

5. **Two deletions were reverted during the work and that is recorded.** `chart-lane4-quiet.svg`
   and `chart-older-engine.svg` were removed as unreferenced and restored once
   `tests/public/test_charts_match_records.py` was read: it checks both value by value against
   their records. The nine that stayed deleted — `boundary`, `chain`, `company`, `cover`, `index`,
   `laws`, `measured`, `page`, `sentiel` — are read by nothing in the repository. They are
   recoverable with `git show a71d9b0:public/overlay/.github/assets/readme/<name>`.

6. **Byte code is never evidence, so the audit stops resolving it.** ADR 0348 cites
   `src/phos/atlas/packet/__pycache__/s7comm.cpython-312.pyc` in a paragraph whose whole point is
   that byte code is not source. Whether that file exists is an accident of the checkout: CI runs
   the suite before it audits, so the path resolves there, and this machine sets
   `PYTHONDONTWRITEBYTECODE`, so it does not resolve here. `scripts/audit_evidence.py` gains
   `BYTE_CODE_DIR` beside the `RUNTIME_ARTIFACT_DIRS` that already close this exact defect for the
   GENESIS lock, and a `__pycache__` path is now read as a run-time artifact rather than as a
   citation. **No record is edited**: 0348 stands as it was committed.

   The first attempt was an acknowledgement comment in 0348, which passed locally and **failed
   CI**, because an acknowledgement of a citation that resolves vouches for nothing. An
   acknowledgement could only ever have been correct in one of the two places. The honest fix was
   the tool's reading of what a citation is, not a note beside the citation.

## Consequences

The public repository drops 920 KiB of images nobody could see. The export has a third reason to
refuse, and it is the first one that is about the reader rather than about secrecy.

The front page's stated test count moves with this change, and is re-measured rather than
carried: `scripts/audit_evidence.py` and its tests are exported, so the three byte-code cases from
decision 6 reach the public suite and it goes from 6,192 to **6,195**. ADR 0444 named re-measuring
before publishing as the discipline, having twice recorded the opposite; this is the first change
to follow it, and the number was wrong in the working tree until the exported suite was run.

Running `public/figures/build_figures.py` is not a no-op: it writes eight `*-plate.svg` cards
under the old names, and the named-set test in decision 3 is what will say so. Reconciling those
names is owed and is not done here.

Code is not checked, fenced or inline, because backticks stop the link being rendered as one:
there is nothing on the published page for a reader to click. The first version of this check did
read inline spans, on the reasoning that a backticked path in prose is still a path somebody will
try — and it refused the export over the sentence in this record that shows what a quoted link
looks like. The rule is now the renderer's rule rather than a guess at intent.

## Verified

- `uv run ruff check` and `ruff format --check` clean; `mypy --strict` clean.
- `tests/scripts/test_export_public.py` and `tests/public/`: 53 passed, 1 skipped — the skip is
  the plate-rebuild test, which needs `fontTools`.
- `uv run python -m pytest -q`: 6,563 passed, 27 skipped, 45 deselected, exit 0. Exported suite,
  run in the public checkout: 6,195 passed, 162 skipped, 45 deselected, exit 0, 294 s.
- `uv run python scripts/export_public.py <checkout> --dry-run`: refused with six named targets
  before the fixes, exit 0 with 1,547 files after, reporting nine unreferenced images.
- `uv run python scripts/audit_evidence.py --strict`: exit 0 both with the byte code on disk and
  with it removed, and the report is identical in both — 1539 citations resolve, 100 acknowledged
  where they are cited, 0 unexplained. Run the other way round first, the acknowledgement version
  of decision 6 passed here and failed CI, which is how the environment dependence was found.
