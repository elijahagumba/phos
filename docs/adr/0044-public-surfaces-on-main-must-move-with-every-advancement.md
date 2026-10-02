# ADR 0044 — Public surfaces on main must move with every advancement

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Process lock (not a detection PART)
- **Supersedes:** nothing
- **Depends on:** Constitution §8 (Definition of Done),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md) (the public record is part of
  reproducibility)

**Numbering.** This record is **0044**, not 0042. ADR 0042 (performance gains do not license
breaking the speech contract) and ADR 0043 (a sandbox does not amend the ranking contract) are
already allocated on `docs/adr-0042-refuse-autonomy-override`. Do not reuse those numbers on
`main`.

## Context

PHOS is built by agents as well as by a person. The technical record (`PROGRESS.md`, `docs/adr/`,
`eval_runs/`) can stay honest while the front door (`README.md`), the plain-English walkthrough
(`easy to reads/`), and the complete reference (`encyclopedia/`) describe yesterday. That split
is how a frozen number gets misquoted: the harness is right and the reader never opens it.

The three surfaces serve different readers:

| Surface | Reader |
|---|---|
| `README.md` | First encounter; how to run; what exists vs what is unearned |
| `easy to reads/` | Someone who should not start at ADRs |
| `encyclopedia/` | Someone who needs a path, a package, and the frozen quote |

None of them is the experiment log. They must still *move* when `main` moves, or they rot.

## Decision

1. An advancement that lands on **`main`** is unfinished until `encyclopedia/`, `easy to reads/`,
   and `README.md` are updated or expanded to match it.
2. `PROGRESS.md` and a new ADR remain required when Constitution §8 already says so. They do not
   substitute for the three surfaces.
3. Unmerged work under `experimental/` is not a `main` advancement. When it merges, the three
   surfaces catch up in that merge.
4. Typo-only and format-only edits are not advancements.
5. Honesty still outranks completeness: if the data cannot support a claim, the public surfaces
   record the refusal. They do not invent a number the log does not have.
6. The lock lives in `.cursor/rules/docs-on-main.mdc` (`alwaysApply: true`) and in Constitution
   §8. A freeze test pins that the rule file still names the three surfaces.

## Consequences

- Agents may not call a `main` change done while any of the three is stale.
- Easy to reads grow by expanding an existing note or adding the next numbered note, not by
  rewriting frozen measurements to look earned.
- The encyclopedia grows by editing the matching volume or adding a volume, not by duplicating
  `eval_runs/log.jsonl`.
- This decision does not earn the ≥70% command-lead contract, un-refuse distillation 2–3/day, or
  authorise Intelligence, API, or UI.

## Revisit when

A different public-doc architecture replaces these three surfaces *and* an ADR supersedes this
one. Do not silently drop the update duty.
