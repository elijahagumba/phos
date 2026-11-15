# ADR 0415 — The record store survives two writers, an interrupted write, and a record it cannot read

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. Phase B of the GENESIS architecture proposal
- **Supersedes:** nothing. [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md) stands; this repairs the store it introduced
- **Depends on:** [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md),
  [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md),
  [ADR 0414](0414-the-five-guards-are-functions-and-both-editors-run-them.md)

## Context

The GENESIS mandate's §2 requires that "Claude Code and Cursor must operate on the same canonical
research state" and its §14.9 requires that concurrent access be tested. The architectural audit
tested it and the store failed:

```
eight concurrent `ask` calls  ->  questions written: 1
```

Seven records were **silently lost**. Each process read the same highest id, computed `Q-0001`,
wrote the same path, and the last writer won. No error, no warning, nothing in the tree to say it
had happened. Two editors open on one checkout — the arrangement ADRs 0413 and 0414 exist to
support — could destroy each other's work.

Three distinct defects sat behind that one number. `next_id` read the tree and the caller wrote it
back with no lock between. `write` used `Path.write_text`, which is not atomic, so a process killed
mid-write left a half-written record. And nothing checked whether the path being written already
held something.

A fourth, from §3.2 of the proposal: one unreadable record stopped the world. A truncated file —
what a killed session leaves — made `state` and `report` exit with a Pydantic traceback rather than
report the damage and carry on. `state` is the mandate's §4.1 continuity mechanism and the
charter's §XIII step 1, so a store that cannot be fully read must still say what it does hold.

## Decision

**1. Allocation and writing are one critical section.** `Store.locked()` takes an exclusive
`flock` on `docs/genesis/.lock`, and `Store.create(kind, build)` allocates the id and writes the
record inside it. `flock` is advisory between cooperating processes, which is exactly what two
editors on one checkout are, and the kernel releases it when the holder dies — so a killed session
leaves no stale lock to clear by hand. The lock file and the write temporaries are git-ignored: the
lock is a mutex, not a record.
<!-- evidence-ack: docs/genesis/.lock — created at run time and git-ignored on purpose, so it is absent from a clean checkout; a mutex is not evidence, and a committed lock file would be the defect -->

**2. Every write is atomic.** `_write_atomic` writes to a temporary file **in the destination's own
directory** — `os.replace` is only atomic within one filesystem — flushes, `fsync`s, then replaces.
A reader sees the old file or the new one and never a partial one. A killed process leaves the
temporary behind and the real record untouched; the loader's `*.json` glob does not match it, and a
test asserts that a leftover temporary is not read as a record.

**3. A create that would overwrite is refused.** `create` raises rather than replacing a path that
already holds a record, because the only way that happens is the allocator and the tree
disagreeing, and overwriting would destroy evidence nobody had read. `write` still replaces, which
is the update path `result` and `promote` need.

**4. The store reports its own damage instead of dying.** `_load_all` skips what will not load and
collects a `Broken` for it. `snapshot()` returns the records **and** the unreadable files together,
so a caller that reports a state has to have seen what it could not read. `state` and `report` print
the readable state, then name every unreadable file, then exit 3. `audit` reports them too.

The safe direction is the point, and is tested: a corrupt record the gate cannot see means
*nothing declares this command*, which is a refusal, not an allow. A corrupt question does not stop
the gate reading experiments at all.

## Consequences

**Gained, and measured.** The audit's own probe, re-run: **8 of 8**, then **32 of 32** concurrent
writers, every id distinct, no temporary left behind. `state` on a store with one truncated record
now prints `questions: 1`, names the unreadable file, and exits 3 with no traceback. 20 new tests
under `tests/genesis/test_store_safety.py`, each one tied to a defect the audit measured; the
concurrency test runs real subprocesses rather than threads, because a thread pool would share the
lock's file handle and prove nothing about two editors.

**Cost.** `fcntl.flock` is POSIX. This repository runs on macOS and CI runs on Linux, so that is
covered, but the store is no longer portable to Windows without a second implementation, and this
record is where that is written down rather than discovered. `fsync` on every write is slower than
`write_text`; at one record per write that is not worth measuring, and the proposal's §12 already
says the file store should be revisited rather than assumed when the number of writers grows.

**What this does not fix.** The tier field is still self-asserted — a run on a `never` corpus can
still be declared by labelling it `iterate`, as the audit showed. That is phase C of
`docs/genesis-architecture-proposal.md` and is untouched here. Nor does this change what any guard
decides, or what the ladder requires.

**Not claimed.** That the store is safe for many writers. It is safe for the two editors it exists
to serve, under a lock they both respect, and the limit is stated rather than left implicit. No
corpus was opened, no number produced, no finding at any level, `eval_runs/log.jsonl` not appended,
v1 unmoved, P1 still a blocked human conversation.
