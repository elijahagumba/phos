# ADR 0098 — HAI 22.04 and 23.05 are on disk, and they are not scored

- **Status:** Accepted
- **Date:** 2026-10-05
- **PART:** v1, registry, before any grouped configuration is scored
- **Depends on:** [ADR 0087](0087-every-hai-version-is-registered.md),
  [ADR 0096](0096-sandbox-event-grouping-explains-the-budget-gap.md),
  [ADR 0097](0097-hai-21-03-payloads-are-on-disk.md)

## Context

ADR 0096 says HAI 22.04 and 23.05, once fetched, are the clean test for any grouped
configuration. They have to be on disk before that test is declared, and they must not
be scored in the same step that fetches them. Scoring them now would spend the one
clean look.

## Decision

Both entries are `on-disk`, outside `FETCHABLE_STATUSES`. `git lfs` is not installed
here. The publisher's LFS batch API returned 403: the repository exceeded its LFS
budget. The raw GitHub URL still returns pointer text, so `--all` must not download it.

The payloads are at `data/hai-22.04/` and `data/hai-23.05/`. They were read from
`media.githubusercontent.com` at commit `2a814cebc9a66b06c9e5cd545e2d72e65d383737`.
A HEAD of `hai-22.04/test1.csv` returned content-length 50536532 and an etag equal to
the registered oid. Every file's sha256 equals the Git LFS oid already in the registry.
The 22.04 summary texts, which are ordinary blobs, now have a sha256 of the text on
disk. The payloads are not in git.

Nothing is scored on either edition. The G1 table's rows for them stay `not_scored`.
That table still says the CSV is not on disk. That sentence is now false, and it is
corrected when the rows are scored, not before. `hai-20.07` and `haiend-23.05` stay
`registered-not-fetched`.

## Consequences

The next score on these two editions is the one clean run of every grouped and
ungrouped detector, and it happens only after the grouping wrapper and the grouped
rows on the already-seen corpora are committed.

## What would reverse this

A payload whose sha256 is not the oid in the registry, or a score written against
either edition before that declared run.
