# ADR 0344 — Industrial protocol coverage is declared, and its numbers are reserved

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Atlas, build brief G
- **Supersedes:** the "wait for a partner's capture" sentence in
  the operating plan (lab record, not published) section 4, for this
  programme only. The sentence stays in the plan.
- **Depends on:** [ADR 0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md),
  [ADR 0292](0292-a-number-another-branch-already-used-is-refused.md),
  [ADR 0302](0302-a-program-transfer-is-not-a-register-write.md),
  [ADR 0324](0324-the-operating-plan-loads-in-both-tools.md),
  [ADR 0325](0325-the-law-page-inlet-is-a-named-map.md)

## Context

On 28 October 2026 Elijah decided to add industrial protocol dissectors to Atlas
now, ahead of a partner naming one. The operating plan, section 4, says OPC UA
and DNP3 wait until a partner's capture is one of those protocols. That sentence
is still the rule for every other programme. This record is the exception, and
it is only an exception for build brief G.

The packet adapter on this tree dissects Modbus/TCP and nothing else. It does
not reassemble a TCP stream, does not pair a response with its request, and
does not surface the Ethernet header. `modbus.py` claims port 502 by port
alone (ADR 0012). A function code is not a program act (ADR 0302, ADR 0325).

Preflight on 29 October 2026, at `d1e98f0`, with `main` even with `origin/main`:

- The work tree was clean.
- `uv run pytest -q`: 4774 passed, 11 skipped.
- `uv run mypy --strict src`: no issues.
- `uv run ruff check`: clean.
- ADRs 0277–0284 are unwritten on every ref in this clone.
- ADR 0343, the joint-command score, is on
  `claude/phos-outreach-strategy-e182e1` and is not on `main`. This programme
  does not depend on it and does not merge it.
- The next free ADR after every visible branch was 0344. The next free
  plain-English note was 139. Note 138 is taken on that same branch.

Nothing here is a measurement. No corpus was opened. v1 stays 8 of 12. P1 stays
blocked.

## Decision

1. **The programme is `docs/build-brief-2026-10-g.md`.** It is the specification
   the lanes implement against. Constants in it are cited there. A constant the
   brief marks unverified is not coded as if it had been settled.

2. **Each protocol still needs its own declaration before any byte of it is
   parsed.** That is how this programme satisfies "no protocol without a
   declaration." A reserved slot is not that declaration. Filling the slot and
   committing it is.

3. **The numbers below are allocated in this commit.** A lane uses only its own
   rows. The same filename is the record (ADR 0292). A verdict file is not
   renamed when the verdict is met, refused, or needs-work. Reserved files are
   not results.

   | ADR | Note | Slot | Who writes it |
   |---|---|---|---|
   | 0344 | 139 | This programme | Orchestrator, this commit |
   | 0345 | 140 | Foundation declaration | Orchestrator, before foundation code |
   | 0346 | 140 | Foundation verdict | An agent who did not build it |
   | 0347 | 141 | S7comm declaration | `protocol-engineer-s7comm` |
   | 0348 | 141 | S7comm verdict | Not the engineer |
   | 0349 | 142 | DNP3 declaration | `protocol-engineer-dnp3` |
   | 0350 | 142 | DNP3 verdict | Not the engineer |
   | 0351 | 143 | IEC 60870-5-104 declaration | `protocol-engineer-iec104` |
   | 0352 | 143 | IEC 60870-5-104 verdict | Not the engineer |
   | 0353 | 144 | EtherNet/IP declaration | `protocol-engineer-enip` |
   | 0354 | 144 | EtherNet/IP verdict | Not the engineer |
   | 0355 | 145 | OPC UA declaration | `protocol-engineer-opcua` |
   | 0356 | 145 | OPC UA verdict | Not the engineer |
   | 0357 | 146 | IEC 61850 declaration | `protocol-engineer-iec61850` |
   | 0358 | 146 | IEC 61850 verdict | Not the engineer |
   | 0359 | 147 | S7comm-plus declaration | `protocol-engineer-s7plus` |
   | 0360 | 147 | S7comm-plus verdict | Not the engineer |
   | 0361 | 148 | Law-inlet wiring declaration | `rulebook-integrator` |
   | 0362 | 148 | Law-inlet wiring verdict | Not the integrator |
   | 0363 | 149 | Programme close | Orchestrator |
   | 0364 | 150 | Profinet declaration, optional | Only if the loop picks it |
   | 0365 | 150 | Profinet verdict, optional | Not the engineer |
   | 0366 | 151 | BACnet declaration, optional | Only if the loop picks it |
   | 0367 | 151 | BACnet verdict, optional | Not the engineer |

   One plain-English note covers a protocol's declaration and its verdict. The
   note is rewritten when the verdict lands. It is not a second number.

4. **The order in the brief is the default rank, not a promise that every
   dissector lands.** A step that only parses, with no law that can already use
   the act and no licence-clean capture behind it, is ranked below a step that
   has one of those. A refusal is a result.

5. **This programme does not score a detection corpus, open a held-out corpus,
   read a red-tier corpus, edit a residual detector, or edit any of the six law
   predicates.** It does not start Intelligence, an API, a UI, a socket, or a
   TAP. It does not export to the public repository as part of this record.
   Hypothesis confidence stays unsurfaced. v1 stays 8 of 12.

## Consequences

`modbus.py` remains the reference dissector and is not edited to make a later
protocol fit. Shared packet files belong to the orchestrator. A protocol module
belongs to its engineer. The seam test must keep passing without an edit to
`modbus.py`.

0277–0284 stay unwritten. ADR 0343 stays on its branch.

## What would reverse this

A later record that closes the programme, or a decision that a partner's capture
is again required before any of these declarations may be filled. The reserved
numbers are then judged as not done. They are not given to a different subject.
