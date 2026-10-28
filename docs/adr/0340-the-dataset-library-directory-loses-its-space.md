# ADR 0340: the dataset library directory loses its space

- **Date:** 28 October 2026
- **Status:** accepted
- **PART:** the synthetic dataset library, its path only
- **Supersedes / amends:** the path named in
  [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md) Decision 1. Everything else
  in that record stands, including every caveat about what the library is not.

## Context

ADR 0029 Decision 1 fixed the library at `dataset library/`, a tracked directory whose name
contains a space. That was invisible while the tree was private. It is not invisible now: the
repository is public, and a reader who opens the file list sees one directory name that does not
match the discipline of everything around it. A space in a tracked path also has to be quoted in
every shell command that touches it, which is a trap for a contributor writing a one-line script
and a reason for a glob to silently match nothing.

Accepted records are immutable, so ADR 0029 is not edited. This record is where the path moves.

## Decision

The library lives at **`dataset-library/`**.

A hyphen, to match how every other multi-word name in this repository is written, from the decision
record filenames to the plain-English notes.

Nothing else about the library changes. The OT and IT catalogues stay committed JSON. Generated
payloads stay under `generated/` and stay git-ignored, which is ADR 0006's rule. Regeneration is
still `scripts/generate_dataset_library.py`. No catalogue content, no window count, no persona
count and no result name moves, and this record reports no measurement.

Every caveat in ADR 0029 survives unchanged and is worth restating, because a rename is exactly the
kind of change that lets a caveat go missing: **a library recall is not HAI attack recall, not
distillation perturbation recall, and not CERT insider recall.** The library is not a public corpus.

## What this touches

- `LIBRARY_DIRNAME` in `src/phos/library/ot.py`, which is the single source of the name.
- `library_root` in `src/phos/library/evaluate.py` and the test that asserts the path in
  `tests/library/test_evaluate.py`.
- `scripts/generate_dataset_library.py` and `scripts/evaluate_dataset_library.py`.
- `.gitignore`, so the generated payloads stay ignored at the new path.
- `public/manifest.toml`, so the catalogues still reach the public tree.
- The three public surfaces ADR 0044 requires, which carry the path in prose.

## What is deliberately left alone

[ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md) and
[ADR 0084](0084-non-saturating-aggregation-for-sentiel.md) name the old path. They are accepted
records and they stay as written. A reader who follows one of them to a path that no longer exists
finds this record, which is the point of a numbered supersession rather than a quiet edit.

Prose that calls the thing "the dataset library" is a name, not a path, and is not rewritten. Only
paths move.

## Consequences

A contributor can write `ls dataset-library/OT` without quoting. A stranger reading the tree sees
one fewer thing that looks unfinished. Against that, two accepted records now cite a path that is
not on disk, which is a cost this record accepts openly rather than hiding by editing them.

No measurement is affected. v1 stays where the record left it.
