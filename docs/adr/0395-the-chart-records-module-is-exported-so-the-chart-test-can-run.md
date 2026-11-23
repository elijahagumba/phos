# ADR 0395 — The chart-records module is exported, so the chart test can run

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** Public record and export discipline
- **Supersedes:** nothing. [ADR 0381](0381-the-front-door-is-corrected-and-the-freeze-opens-for-figures.md)
  stands unchanged; this record repairs the export that decision's test depends on
- **Depends on:** [ADR 0381](0381-the-front-door-is-corrected-and-the-freeze-opens-for-figures.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0267](0267-the-public-test-job-runs-a-fresh-clone.md)

## Context

ADR 0381 admitted explanatory figures on one condition: **every value a chart plots is the value
its record holds.** `tests/public/test_charts_match_records.py` enforces it, and its value half
reads the committed records through `public/figures/chart_records.py` and checks each plate shows
exactly those values. That test is exported, because `tests/*` is an `include` pattern.

`public/figures/chart_records.py` was not. No pattern in `public/manifest.toml` names
`public/figures/`, and `public/` reaches the public tree only as `public/overlay`. The module was
therefore never selected for export.

`scripts/export_public.py` replaces the destination rather than merging into it, which its own
docstring states: *"Everything in it except `.git` is removed and rewritten."* A file present in the
public repository and absent from the export is deleted on the next run.

That is what had happened before. Commit `55cab7d` in the public repository, 29 October 2026,
<!-- evidence-ack: 55cab7d — a commit in the public repository (elijahagumba/phos), which is what the sentence says; the lab's object store does not hold it and no tag may be made to resolve it -->
imported the module **by hand into the destination** and recorded why:

> `tests/public/test_charts_match_records.py` imports `public.figures.chart_records`, and that
> module was missing from this repository, so `uv run mypy` failed, the tests step behind it was
> skipped, and `uv run pytest -q` — the command the front page gives a reader — stopped on a
> collection error instead of running.

The repair was made in the destination. The manifest was not changed. So the next export undid it,
and on 1 November 2026 one did: the run deleted the module and would have restored the collection
error for any reader who cloned the repository.

This is the second time the same fault has appeared, and the first time its cause is recorded. A
fix applied to the destination is overwritten by the tool that generates the destination; only a
fix in the manifest survives.

## Decision

1. **`public/manifest.toml` `[export].include` gains `"public/figures/chart_records.py"`.** One
   line, with a comment naming this record and the test that needs the module. Nothing else about
   the export changes.

2. **The module is the right thing to publish, not the test the wrong thing to publish.** ADR 0381
   admits charts only under the value condition, and the plates it admits are already public: the
   overlay carries `chart-lane3-delay.svg`, `chart-lane4-quiet.svg` and the rest, and the front page
   embeds two of them. Excluding the test instead would leave those plates unchecked on the public
   tree while the record claimed they were checked. The module is standard library only and reads
   three records already exported under `eval_runs/*`, so it discloses nothing the public tree does
   not already hold.

3. **The repair is verified on the destination, not asserted.** After the export, `uv run pytest -q`
   in a checkout of the public repository reports **4848 passed, 44 skipped, 45 deselected** in
   238.35 s, and `git status` shows no deletion.

4. **A destination-only fix is not a fix.** Where the export tool rewrites a tree, a repair belongs
   in `public/manifest.toml` or in the lab source, never in the generated checkout alone. This
   record is the standing home of that rule; a later session finding a hand-patched public file
   should look here before repeating the practice.

## Consequences

- The public test suite can be collected on a fresh clone, so the command the front page gives a
  reader runs. `55cab7d`'s intent now survives regeneration.
- The exported file count moves from 1395 to 1396. No other path's selection, sanitising or
  forbidden-content check changes.
- The commercial-content gate was re-run as part of this export and did not fire.
- **No measurement moved.** `eval_runs/log.jsonl` was not appended, no corpus was opened, no
  frozen row was read or rewritten, and v1 stays **8 of 12**. C2 is still unmet: it is a human
  time trial and its sheet is unfilled.

## What would reverse this

Removing the module from `include` while keeping the test exported; excluding the chart test to
make the export clean; hand-adding the module to a public checkout again without a manifest change;
or reporting this export as a measurement of anything.
