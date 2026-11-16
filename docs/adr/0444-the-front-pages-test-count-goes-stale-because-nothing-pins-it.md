# ADR 0444 — The front page's test count goes stale because nothing pins it

- **Status:** Accepted
- **Date:** 2026-11-16
- **PART:** Public record
- **Supersedes:** nothing
- **Depends on:** [0440](0440-the-exported-suite-is-green-and-a-false-green-is-gone.md), [0443](0443-the-front-page-is-shortened-and-the-contracts-pins-follow-it.md), [0441](0441-a-drawn-float-is-rounded-because-a-draw-is-not-bit-reproducible-across-architectures.md), [0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

ADR 0440 replaced a stale `4,943 tests` on the public front page with **6,184**, measured by
exporting into a fresh clone and running the suite there rather than counting in the lab. The
figure was correct when it was taken and was stale within the day.

It drifted twice, and the arithmetic closes exactly:

| Source | Tests |
| --- | --- |
| ADR 0440's measurement | 6,184 |
| `03bd7b9`, ADR 0441's rounding fix, six new tests in `tests/synth/test_randomise.py` | +6 |
| `abdb4ea`, ADR 0443, five added test functions less three renamed away | +2 |
| Measured in the export, 16 November 2026 | **6,192** |

The first drift is the instructive one. ADR 0441 landed on the same day as ADR 0440 and nothing
reported that it had invalidated a published number. ADR 0443 then rewrote the page and carried
`6,184` across without re-measuring it, which is the same failure a second time and is recorded
here rather than in that record, because that record is committed.

**Nothing in the suite pins this number.** The ceiling and the refused word set are pinned to code
constants by `tests/public/test_overlay_readme.py`; the test count is not pinned to anything,
because the thing that would pin it is the suite counting itself. So it goes stale silently, and
only somebody choosing to export and run catches it.

## Decision

The front page reads **6,192 tests pass and 162 skip, each naming why**, in about five minutes,
measured in the exported tree and not in the lab.

The sentence also restores the **skip count**, which ADR 0443 dropped when it shortened the page.
ADR 0440 put it there deliberately: a reader who runs the suite sees 162 skips, and a page that
does not mention them leaves that reader to wonder what was silenced. Brevity is not a reason to
drop it.

**No test is added to pin the count.** A test that asserts its own suite's size fails on every
honest change and teaches people to edit the assertion, which is worse than a number that drifts.
The gap is named instead: a figure measured in the export is stale as soon as a test lands, and
the only remedy that works is re-measuring before publishing. Whoever next exports should run the
exported suite and read this record first.

## Consequences

The count on the page is true as of this record and will go stale again. That is stated on the
record now, so the next drift is a known mechanism rather than a discovery.

ADR 0044: `encyclopedia/12-adr-catalogue.md` gains this record's entry. No plain-English note is
added — `easy to reads/188` quotes no count, and a note restating this one would carry no idea the
record does not. The lab `README.md` quotes no test count.

**This record does not** lift a tier, move v1 off 8 of 12, open a closed rung, fill 0277-0284,
score anything, or unblock P1. The suite's size is not a measurement of the engine.

## Verified

`uv run pytest -q` in a fresh export at `f45095d`: **6,192 passed, 162 skipped, 45 deselected** in
299.12 s. Exit 0. The export itself exited 0 at 1,553 files.
