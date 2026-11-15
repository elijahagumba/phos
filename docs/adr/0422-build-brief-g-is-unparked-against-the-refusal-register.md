# ADR 0422 — Build brief G is unparked, and the criterion it moves is the refusal register

- **Status:** Accepted
- **Date:** 2026-11-05
- **PART:** Build brief G
- **Supersedes:** nothing
- **Depends on:** [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0346](0346-the-packet-foundation-is-judged.md),
  [ADR 0420](0420-one-atlas-engineering-roadmap-and-the-rest-are-closed-or-parked.md)

## Context

ADR 0420 parked build brief G on 3 November 2026 with this reason:

> OPC UA and DNP3 widen coverage and move neither A3 nor A7. Without a partner
> capture a second dissector is specification without evidence.

That judgement is correct about A3 and A7 and is the wrong ruler for the
question. A3 asks whether an Atlas queue ranks. A7 asks whether a stranger can
re-derive the numbers. Neither asks whether Atlas can read the plant at all.
Measuring reach against a ruler built for accuracy returns "moves nothing"
whatever the answer, which is what happened.

On 5 November 2026 Elijah gave the direction: Atlas is to read every essential
plant language, as the first step of a wider standard he calls sovereign grade.
That restates the decision ADR 0344 already recorded on 28 October — name the
protocols now, ahead of a partner naming one — rather than opening a new one.

ADR 0346, written today, judged the brief's foundation **met**. The foundation
has been on `main` since `bf37107` and the suite is green at `2560b6b`
(5416 passed). The programme's next step is therefore a protocol lane, and a
parked programme cannot cut one.

## Decision

**Build brief G is unparked.** ADR 0420's park is lifted for this programme
only. Every other disposition in that record stands: brief E closed, roadmap F
and the daily-leaps contract absorbed, brief H adopted as Acts II–IV with H2–H4
closed until after 6 January 2027, the zero-to-one plan adopted, GENESIS the
method. The Atlas engineering roadmap remains the sequence.

**The criterion it moves is R27 of the refusal register, not A3 and not A7.**

`docs/refusal-register.md` is a deliverable in its own right (ADR 0074, item
U6) — the map of what PHOS cannot do and what would lift it. Read down its
third column and it is the most sovereign-grade artefact in the repository,
because it is the thing a buyer cannot get from any competitor: a vendor
stating its own boundary in advance.

That register has twenty-six entries and **none of them says Atlas cannot read
a plant that does not speak Modbus/TCP.** The limit is real, it has been true
since ADR 0012, and it was never written down. The register's own append
procedure, rule 1, says a refusal discovered in passing is written the moment
it is established. It is appended in the same change as this record, as R27.

Brief G's criterion is therefore stated plainly: **every protocol lane that
reaches a verdict strikes a line through part of R27, and a lane that is
refused sharpens it.** A refused lane is as good a result here as a kept one,
because the register is improved either way. That is a criterion the programme
can actually move, unlike A3 and A7.

### What is not claimed

**Reach is not performance, and this record does not let the two be confused.**
A dissector that reads S7comm says Atlas can see a Siemens plant. It says
nothing about whether Atlas is right when it looks. No lane in this programme
may be quoted as detection, as recall, as a false-alert rate, or as evidence
for A2, A3 or A7. The honest sentence is *Atlas can now read this language*,
and it stops there.

ADR 0420's second clause also stands unchanged: without a partner capture a
dissector is specification without evidence. Brief G already answers it — the
loop's value test ranks a protocol by whether a licence-clean capture exists to
test it against, and the `corpus-researcher` role registers a capture in
`data/registry.json` without committing a byte of it. A lane with no capture is
ranked below one that has it, and says so in its declaration.

### The rank stands, with one gap recorded

The standing rank in `docs/build-brief-2026-10-g.md` is unchanged: foundation,
S7comm, DNP3, IEC 60870-5-104, EtherNet/IP with CIP, OPC UA, IEC 61850,
S7comm-plus, then Profinet and BACnet as optional slots. S7comm stays second
because a software download is the act `program_transfer` already knows, which
is the brief's value test (a), and not because Siemens is large.

**MQTT and Sparkplug B are absent from that rank and this record does not add
them.** The gap is written here so a later session finds it: for a sovereign
posture the flow that crosses from the plant to a cloud matters out of
proportion to its share of plant traffic, and it currently has no slot. Adding
one needs its own record and a number after the reserved block.

## What this record does not do

It does not build a dissector, score a corpus, open a held-out or red-tier
corpus, append `eval_runs/log.jsonl`, or edit `modbus.py`, the six law
predicates, `declared_law.py` or `law_inlet.py`. It does not fill 0277–0284,
merge ADR 0343, or depend on it. It does not start Intelligence, an API, a UI,
a socket, a TAP or a live capture. It does not open H2, H3 or H4 before
6 January 2027. It does not run the ADR 0316 score. v1 stays 8 of 12 and its
freeze date stays 24 January 2027. No frozen number moves. **P1 stays the
blocked human conversation.**

Sovereign grade is a direction Elijah has named, not a standard this record
defines. Defining it needs its own ADR.

## What would reverse this

A lane that is quoted as a detection result; a protocol built with neither an
existing law to act on nor a licence-clean capture, without its declaration
saying so; or a later record re-parking the programme because the register is
not moving.
