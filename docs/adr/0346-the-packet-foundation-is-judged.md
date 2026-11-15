# ADR 0346 — The packet foundation is judged

- **Status:** Accepted
- **Date:** 2026-11-05
- **PART:** Build brief G, foundation
- **Supersedes:** nothing
- **Depends on:** [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0345](0345-the-packet-foundation-is-declared.md)

## Context

ADR 0345 was committed before the code and froze the bar. The foundation was
then built and merged to `main` as `bf37107`, *feat(atlas): build the packet
foundation inside its declared caps*. That commit moved `encyclopedia/08-atlas.md`,
`easy to reads/140-the-stream-stops-at-a-cap.md` and `README.md` with it, so
ADR 0044 was satisfied at the time it landed.

The verdict was never written. Between 29 October and 5 November 2026 the
foundation sat on `main` as working code whose declaration had no result
against it, which is the one state the record exists to make visible. ADR 0420
parked build brief G on 3 November without noticing that this step of it was
finished and unjudged; parking a programme does not settle a debt inside it.

This record is the missing verdict. The judging session did not build the
foundation and did not write ADR 0345, which is what brief G's step 4 requires.
It judged against the declaration as committed, not against a restatement.

## Decision

**Met.**

Each bar in ADR 0345's *What met means*, checked at `2560b6b`:

| Declared bar | Evidence |
|---|---|
| The caps are the declared values | `MAX_BUFFERED_BYTES_PER_FLOW` 131072, `MAX_CONCURRENT_FLOWS` 256, `MAX_OUT_OF_ORDER_SEGMENTS` 16, `MAX_SEGMENT_OCTETS` 65535 in `reassembly.py`; `MAX_OPEN_PAIRS` 256 and `PAIR_EXPIRY` 60s in `pairing.py`. All six match the declaration digit for digit |
| Reassembly does not import Modbus | `reassembly.py` imports only `collections.abc`, `dataclasses`, `typing` and `packet.frame` |
| A refusal is a value, not an exception | `FlowRefusal` is returned from `push`; six named reasons — `SEGMENT_TOO_LONG`, `BYTE_CAP`, `FLOW_CAP`, `REORDER_CAP`, `OVERLAP`, `PDU_LENGTH` |
| An overlap refuses the flow | `OVERLAP` fires both for octets already delivered and for a stored segment (`reassembly.py:242`, `:245`). There is no last-write-wins branch |
| The fuzz corpus is as declared | Seed `20261029`, `LISTS = 2000`, `BUDGET_SECONDS = 30.0` in `test_foundation_hardening.py` |
| The existing suite stays green | `uv run pytest -q` → **5416 passed, 24 skipped, 45 deselected in 237.41s**. The packet suite alone is 416 passed in 3.83s |
| `mypy --strict src` is clean | *Success: no issues found in 294 source files* |
| `ruff check` is clean | *All checks passed!* |
| `modbus.py` has an empty diff | `git diff bf37107^ bf37107 -- src/phos/atlas/packet/modbus.py` is empty |

None of ADR 0345's *What refuses this* conditions hold. No cap is honoured by
shortening a buffer. No overlap keeps a copy. `modbus.py` did not change.

**One raise exists in the foundation and it is not a refusal of this step.**
`pairing.py:144` raises `ValueError` when the caller passes a timezone-naive
capture timestamp. Its own docstring says *"That is a caller bug, not a
capture."* ADR 0345's refusal is a `FlowRefusal` raised instead of returned, and
a raise on hostile wire bytes. This is neither: it is an API precondition on a
value the caller constructs, on a path no packet reaches. Recorded here so that
a later reader finds it in the verdict rather than in the source.

## What this record does not do

It does not build a protocol module, and it is not permission to cut a lane
branch. Brief G stays parked by ADR 0420 until a record unparks it. It scores
no corpus, opens no held-out file, reads no red-tier corpus, appends nothing to
`eval_runs/log.jsonl`, and edits none of the six law predicates. Modbus/TCP
remains the only dissector. v1 stays 8 of 12. A3 and A7 are untouched by this.
P1 stays the blocked human conversation.

## What would reverse this

A rerun of the suite at this commit that is not green, a cap in the source that
does not match ADR 0345, or a demonstration that an overlap is spliced rather
than refused.
