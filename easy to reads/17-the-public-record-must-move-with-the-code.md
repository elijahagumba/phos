# The public record has to move with the code

**What this is:** a standing rule, not a new detector.

**Why it exists:** PHOS can be honest in the laboratory notebook and stale on the front door.
That is how a frozen number gets misquoted.

## Three readers, three surfaces

Imagine a night-shift operator, a new engineer, and a visitor who only has five minutes.

- The visitor reads **README.md**. It has to stay true, and short. It is not allowed to invent a
  number the experiment log does not have.
- The operator who should not start at architecture decision records reads **easy to reads/**.
  Analogies live here. When a new idea lands, an existing note grows, or a new numbered note is
  added.
- The engineer who needs a file name reads **encyclopedia/**. Volumes expand; a new topic gets a
  new volume.

None of these three is the experiment log. `PROGRESS.md` and the ADRs still exist, and they still
win if a figure disagrees. They do not *replace* the three.

## What “done on main” now means

An advancement that lands on **main** — a PART, a measurement, a refusal, a new ADR — is unfinished
until all three surfaces have moved with it.

Work that stays in `experimental/` and never merges is exempt. The moment it merges onto main, the
three surfaces catch up in that merge. Typo-only edits are not advancements.

Honesty still outranks completeness. If the files cannot support a claim, the public record says
so. It does not paper the gap.

## Where the lock lives

`.cursor/rules/docs-on-main.mdc` (always on), Constitution §8 item 8, ADR 0044, and a freeze test
that turns red if the rule is deleted.

This note is itself the easy-to-read for that law.
