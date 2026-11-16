# ADR 0428 — Byte code is a run-time artifact, and the gate stopped depending on whether the suite had run

- **Status:** Accepted
- **Date:** 2026-11-10
- **PART:** Method. The defect [ADR 0415](0415-the-record-store-survives-two-writers-and-its-own-damage.md) and [ADR 0417](0417-the-guards-were-observed-firing-and-only-the-claude-shims-were-loaded.md) closed for the GENESIS lock, reaching the same gate from a different directory
- **Supersedes:** nothing. ADR 0348 is not edited and its judgement is untouched
- **Depends on:** [ADR 0415](0415-the-record-store-survives-two-writers-and-its-own-damage.md), [ADR 0417](0417-the-guards-were-observed-firing-and-only-the-claude-shims-were-loaded.md), [ADR 0348](0348-s7comm-dissection-is-judged.md)

## Context

`scripts/audit_evidence.py --strict` is the CI gate on cited evidence. It reads every backticked
path and every hex token in the records, resolves each one, and fails when a citation does not
resolve and nothing beside it explains why.

ADR 0348's red-team section carries this observation, item 2 of three, filed as *not a finding
against the engineer*:

> `grep -rn 65524 src/` also matches a stale
> `src/phos/atlas/packet/__pycache__/s7comm.cpython-312.pyc`. Byte code is not source and the
> tracked tree is clean, but a future `65524` audit that greps the working tree will get a false
> positive from a build artifact.

The record is right, the observation is useful, and the path is correctly spelled. It is also
byte code, so whether it exists depends on whether anything has imported that module in that
checkout.

## What was found

The gate's verdict on ADR 0348 **differed between two machines running the same commit**, and
each verdict was reached honestly:

| Where | `s7comm.cpython-312.pyc` | What the gate saw | Verdict |
|---|---|---|---|
| Local, clean `__pycache__` | absent | a citation that does not resolve | **fails** — nobody has explained it |
| CI, suite already run | present | a citation that resolves | **fails** — the acknowledgement covering it is stale |

Both failures were the gate working as written. Neither was about the record.

The first attempt at a fix was to add the acknowledgement the local run asked for. That is the
move the gate's own error message recommends, and on this citation it is wrong: the marker went
stale in CI within four minutes, because the file the marker said was missing was there. An
acknowledgement cannot describe a path whose existence is an accident of what has run.

`is_runtime_artifact` already held the answer for a different directory. ADR 0415 hit this exact
shape on `docs/genesis/.lock` — "absent in CI and present on any machine that has run `genesis`,
so the same record would fail in one place and pass in the other" — and closed it by not treating
such a path as a citation at all. Byte code is the same defect reached from `src/`, `tests/` and
`scripts/` instead of `docs/genesis/`.

## Decision

1. **Compiled Python byte code is a run-time artifact, not a citation.** A path containing a
   `__pycache__/` segment, or ending `.pyc` or `.pyo`, is not resolved. `scripts/audit_evidence.py`
   gains `BYTECODE_SEGMENT` and `BYTECODE_SUFFIXES` and one branch in `is_runtime_artifact`.

2. **It is a separate constant, not a widening of `RUNTIME_ARTIFACT_DIRS`.** Folding it into that
   prefix tuple would mean adding `src/` to a list whose entries are meant to name a directory
   whose whole contents are ephemeral. The mark that identifies byte code is a path segment, so it
   is matched as one.

3. **ADR 0348 is not edited.** The acknowledgement added to it earlier on this branch is removed
   and the file is byte-identical to `main`'s copy again. The prose was accurate; the gate was
   reading it wrongly. A record is not rewritten to suit a checker.

4. **The exemption is not stretched further.** ADR 0417 added the lock exemption narrowly and the
   roadmap's Act I warns, by name, that `eval_runs/build/lane-daily/joint-champions.md` must not be
   swept into it: that file is real evidence, and a measurement report that does not exist is a
   citation the gate should fail on. Byte code is not evidence under any reading — ADR 0348 says so
   in the same breath as naming it. Nothing under `eval_runs/`, `docs/`, `src/` or `tests/` becomes
   exempt except compiled byte code.

5. **Two tests, both of which fail without the change.** One asserts that three byte-code spellings
   are not citations. The other is the one that matters: it builds a record citing a `.pyc`, runs
   the audit with the file absent, creates the file, runs it again, and asserts the two verdicts
   agree and that neither reports a stale acknowledgement. It is modelled on
   `test_the_gate_does_not_depend_on_whether_the_lock_exists`, which is the same assertion about
   the lock.

## What is not claimed

This is not a measurement. No corpus was opened, no score taken, no detector built, and
`eval_runs/log.jsonl` was not appended. No frozen number moves and v1 stays 8 of 12.

It is not a verdict on ADR 0348, whose judgement of the S7comm lane stands exactly as written, nor
on ADR 0425's result. It does not touch the acknowledgement machinery itself: an unexplained
dangling citation still fails the gate, a marker still has to sit in its citation's own paragraph,
and a marker still needs a stated reason. It does not address the related gap the roadmap names —
an acknowledgement whose citation *legitimately* comes to resolve, as `joint-champions.md` now has
— because that one is about real evidence and wants its own record.

P1 stays the blocked human conversation, with Intelligence, the API and the UI closed behind it.
ADR numbers 0277–0284 stay unwritten and H2's scoring stays closed until after 6 January 2027.
