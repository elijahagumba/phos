# ADR 0292 — A number another branch already used is refused

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Process, the public record
- **Supersedes:** nothing
- **Depends on:** [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0291](0291-the-colliding-adr-and-note-numbers-are-resolved.md)

## Context

ADR 0291 settled two collisions and recorded the cause as unfixed. Two sessions on two branches
each take the next free number from the tree they can see. `ls docs/adr/` on one branch says
nothing about the other. ADR 0273's reserved block, 0273–0284, covers one programme's steps and
nothing else. ADR 0291 says a third instance should be treated as tooling rather than another
renumber.

The settled pair is still visible on an unmerged branch under the old filenames. A check that
scanned every file on every branch and failed the build would be red forever for a decision that
stands.

## Decision

`scripts/check_number_allocation.py` refuses a change that adds or renames onto an ADR or a
plain-English note whose number already belongs to a different filename on any local branch or
remote-tracking branch in the clone. The same filename on two branches is one record. Two new
files that take the same number in one change refuse each other.

Only the files the change adds are judged. That is why the settled 0268/0269 pair, and the two
notes that already share number 70, are not reopened. A further file under 70, or under 0268,
for a different name, is refused.

The lab workflow fetches every origin branch and runs the check on the commits being pushed or
proposed. The public repository's workflow file carries the same step and does not run it:
`elijahagumba/phos` is a separate history and does not hold the lab branches. The hook is
`scripts/git-hooks/pre-commit`. A clone runs it by pointing `.git/hooks/pre-commit` at that
file. CI does not depend on the link.

## Consequences

A number is free only when no visible branch has given it to a different file. A branch that has
not been fetched is invisible, which is the remaining gap, and the workflow's fetch is what
closes it for pushes to the lab. A third collision is a reason to fix this check. It is not a
reason to renumber around it.

Nothing was measured. v1 stays 8 of 12.

## What would reverse this

A single committed register that allocates the next number, which is the other reversal ADR 0291
already names. After that, this check is history rather than the control. Or a deliberate decision
that two records may share a number, in which case the refusal is the wrong rule.
