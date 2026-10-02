# ADR 0012 — dpkt, the dissector seam, and containing hostile packet input

- **Status:** Accepted
- **Date:** 2026-08-14
- **PART:** P1 — Atlas packet adapter: ingestion and protocol dissection
- **Supersedes / amends:** amends the Constitution §4 stack entry for PCAP parsing (see Decision 1).
  Builds on nothing; `phos.atlas.packet` is a new subpackage and no existing module changed except a
  re-export line and a now-false sentence in `src/phos/atlas/__init__.py`.

## Context

Atlas reads a plant's sensor *values* and is deaf to its *commands* — the control messages flowing
between engineering stations, PLCs, RTUs and SCADA servers. That gap bounds what Atlas can ever
conclude. A tank level leaving its expected range says something is wrong; only the command stream
can begin to separate an operator who opened a valve from an attacker who sent the identical write.

P1 builds the ingestion layer for those commands and nothing above it: no behavioural features, no
`Observation`s, no device-command graph, no engine integration. What makes it more than a parsing
exercise is where it sits. **Every byte this code reads was chosen by whoever sent the frame.** A
packet parser inside a security product is an attack surface pointed directly at the thing meant to
be watching, and it is reached before any authentication, any filtering, any model. That framing
drove every decision below.

## Decision 1 — dpkt, not scapy, and the Constitution entry is amended

**Decided:** `dpkt==1.9.8`, pinned in `pyproject.toml`. Not scapy. Not both.

**First, a correction to the premise.** The PART's prerequisites describe scapy as "already a
dependency". It was not. Constitution §4 names scapy for PCAP parsing, but it was never in
`pyproject.toml` and no code imported it. So this was never a choice between an incumbent and a
challenger — nothing was installed, and either option was a new dependency. Constitution §4 permits
substitution with an ADR, and the PART requires an ADR on the choice regardless; this is it.

**Why dpkt.**

1. **The library is inside the trust boundary, so its size is a security property.** Whatever parses
   the frame gets the adversary's bytes before we do. dpkt is a few thousand lines of pure Python
   whose `unpack` methods raise `dpkt.UnpackError`/`NeedData` on a short buffer — small, auditable,
   and failing in one catchable way. scapy is two orders of magnitude larger, guesses layers, and
   carries a correspondingly larger surface for a malformed frame to find something in.
2. **Constitution §3.8 requires the core to be pure and offline.** scapy touches host network
   configuration on import — route tables, interfaces — and can open sockets. dpkt parses bytes and
   does nothing else. For a module whose whole job is to read a file, that difference is the rule.
3. **Streaming.** `dpkt.pcap.UniversalReader` is an iterator over the file, and handles both pcap
   and pcapng behind one type. Measured before committing: taking one frame from a 500-frame
   capture performed three file reads, not five hundred. Industrial captures are gigabytes, so this
   is a requirement rather than a preference.
4. **Determinism** (Constitution §3.7). dpkt holds no global configuration that changes how a byte
   is interpreted between runs.

**Cost accepted.** dpkt ships no `py.typed`, so `mypy --strict` cannot see through it and
`pyproject.toml` carries an `ignore_missing_imports` override. The override is made safe by
Decision 2's containment: exactly one function touches dpkt, and everything crosses back as `str`,
`int` or `bytes`, so no untyped value reaches a signature or a stored field. This mirrors what
PART 4A did for scikit-learn.

## Decision 2 — How hostile input is contained (the centre of this ADR)

The requirement is that malformed, truncated, oversized or lying packets never crash the pipeline,
never read out of bounds, never hang, and never allocate unboundedly. Three mechanisms, and the
boundaries between them are the decision.

### 2a. Containment by construction, not by a net underneath

**Decided:** `modbus.dissect` has no `try`/`except` anywhere in it. It cannot raise because every
read is preceded by a check that the bytes are there, not because something catches what it throws.

The rejected alternative — wrapping the decode in `except Exception: return MalformedFrame(...)` —
looks strictly safer and is worse. It makes a genuine defect in PHOS indistinguishable from a
hostile frame, and the symptom of that confusion is a *quietly shrinking* count of understood
traffic: exactly the failure this package exists to prevent, arriving disguised as robustness.
Constitution §6 forbids swallowing exceptions silently, and this is the case it was written for.

The same reasoning applies one level up: `DissectorRegistry.dispatch` does not catch either. A
dissector that raises is a bug, and the fuzz suite is what makes it safe to say so.

### 2b. Where the trust boundary actually sits

Third-party parsing of untrusted bytes *is* expected to fail, so those failures are caught — but
only around the exact calls that parse untrusted data, and only for named exception types:

| Location | Caught | Outcome |
| --- | --- | --- |
| `capture._peel_layers` — the only dpkt call site | `dpkt.UnpackError`, `struct.error`, `ValueError` | frame counted undecodable |
| `capture.read_frames` — container open, record iteration | same | `CaptureError`, or read stops and `truncated` is recorded |
| `capture._to_utc` — timestamp conversion | `OverflowError`, `OSError`, `ValueError` | frame counted undecodable |

**`RawFrame` construction sits deliberately outside every one of those handlers.** Pydantic's
`ValidationError` subclasses `ValueError`, so a handler wide enough to catch dpkt would also
swallow our own validation failing — turning a PHOS bug into a silently lower frame count. The
handlers are placed to make that impossible.

### 2c. Field bounds as a tripwire, and why the two claims interlock

An out-of-bounds *index* in Python raises. An out-of-bounds *slice* is silent, so "it never raises"
is not on its own evidence that nothing read past a buffer. Every numeric field on `ModbusMessage`
is therefore range-bounded by the model. A decode that ran off the end of a buffer or misread a
field width produces a value outside the protocol's range, which raises `ValidationError` — which
the "never raises" assertion then catches. Neither claim is sufficient alone; together they cover
both the loud and the quiet failure.

### 2d. Cap before allocating, and the defect that found

Nothing sizes a read or an allocation from a wire value that has not first been capped. The MBAP
length field is bounded to 254 before anything else uses it, which bounds the PDU to 253 bytes.

**This was not enough, and mutation testing is what showed it.** After the suite went green, eight
deliberate bugs were injected into `modbus.py` one at a time to check the fuzz suite could detect
them. Seven were caught; removing the MBAP length cap was not. Chasing why exposed a real defect:
a 253-byte PDU leaves room for a read-response byte count of 251, which unpacks to **2,008 coils —
eight past `MAX_READ_COILS`, the protocol's own limit** and past the bound the hardening suite
asserts. Random fuzzing never found it because reaching it needs three fields to agree exactly, and
mutation produces disagreement.

The fix is `_MAX_READ_RESPONSE_BYTES`: a read response may declare at most 250 data bytes, which is
both 125 registers and 2,000 coils. Two directed tests now cover it, and re-running all eight
mutations gives **8/8 caught**.

The general lesson, recorded because it will recur in P2 and P3: *a fuzz suite that has never
caught anything is unproven*. Fuzzing finds the failures reachable by random walk. The bugs that
need several fields to agree need a directed test, and mutation testing is how you find out which
kind you are missing.

### 2e. Termination

The parser contains no unbounded loop: every loop is over a `range` whose bound was checked before
the loop began. The suite runs 4,000 generated inputs inside a wall-clock budget with roughly two
orders of magnitude of headroom, so it can only fail if something genuinely hangs.

## Decision 3 — A pluggable seam, with Modbus as the only implementation

**Decided:** `ProtocolDissector` is a `Protocol` with `name`, `claims` and `dissect`.
`DissectorRegistry` is immutable and dispatches first-claim-wins. Adding DNP3 is a new object and a
registry entry; nothing existing is edited.

**Why Modbus first:** it is the most widely deployed and best documented ICS protocol, and P1's
standard is that one protocol done correctly beats five done badly. DNP3, S7comm and EtherNet/IP
are deliberately not implemented — the PART says leave the seam, do not fill it.

**How the seam is proved rather than asserted.** `tests/atlas/packet/test_dissect.py` registers a
stub dissector for a protocol PHOS does not implement and dispatches to it. If that test needed
`modbus.py`, the seam would be decorative. It does not.

**The registry is immutable and rejects duplicate names.** `with_dissector` returns a new registry,
so one already handed to a running pipeline cannot shift underneath it (Constitution §6, no global
mutable state). Two dissectors under one name would make every message's `protocol` field ambiguous
and any per-protocol count wrong, so it raises at construction.

**`dissect_capture` requires a registry and has no default.** A registry is a declaration of what a
run claims to understand. A default would let a caller believe a capture had been examined for
protocols the registry never held, and that silence is indistinguishable from a clean capture.

## Decision 4 — Three typed outcomes, not one type with a status field

**Decided:** `IcsMessage` (understood), `UnparsedMessage` (nobody claimed it), `MalformedFrame`
(claimed and refused). All frozen and validated. No dictionaries flow downstream.

`MalformedFrame` deliberately does **not** inherit `IcsMessage`. The difference between "we did not
look at this" and "we looked and it was wrong" is the difference between a coverage gap and a
finding, and a consumer that can confuse them will eventually report one as the other. Keeping the
refusal off the message branch means no `isinstance` check downstream can be tricked.

`MalformedFrame` records the payload by **length only**. Retaining adversary-chosen bytes in memory
and passing them downstream buys nothing P2 needs and widens what the rest of the system must be
safe against; the frame index is enough to go back and look.

**Fields are populated only where the wire carried them.** A Modbus read response carries a byte
count but not the address that was read, so `reference_address` is `None` there rather than
back-filled — recovering it needs request/response correlation, which is stateful and is not P1. A
`None` means "the bytes did not say", never "we did not bother", and never a guess.

## Decision 5 — One ADU per frame; pipelined ADUs are `TRAILING_BYTES`

**Decided:** a payload longer than its MBAP length declares is refused as
`MalformedReason.TRAILING_BYTES`. Approved by the operator before implementation.

`dissect` returns one message per frame, so a segment carrying two pipelined ADUs has no honest
channel for the second. Silently parsing the first and discarding the rest violates P1's coverage
standard; calling it malformed is a slightly wrong label attached to a completely visible,
countable, specifically-named outcome. Visible-and-mislabelled beats silent-and-half-parsed. The
same applies in reverse to an ADU split across segments, refused as `LENGTH_MISMATCH`.

**P1 does no TCP stream reassembly.** That is the real limitation these two reasons report, and
reassembly would go behind the same seam in P2 or P3 without changing the message model.

## Decision 6 — `claims()` is port-only, with no structural pre-check

**Decided:** the Modbus dissector claims TCP frames with port 502 at either end, and does not look
at the payload. Approved by the operator before implementation.

A cheap structural pre-check would be easy and would be wrong. Bytes that are not Modbus arriving
on port 502 would stop being claimed and would fall through to `UnparsedMessage`, which reads as
"no dissector covers this protocol" — precisely the wrong thing to say about rubbish aimed at a
PLC. Claiming by port means such traffic reaches the dissector and is recorded as malformed, which
is a finding. This is what satisfies the PART's requirement that non-Modbus bytes on 502 produce a
`MalformedFrame`.

## Ambiguities in the PART, and how each was resolved

| Ambiguity | Resolution |
| --- | --- |
| §5.1 lists both `frame_index` and a `FrameSource` (which also holds the index) on `RawFrame` | `frame_index` is a `computed_field` reading `source.frame_index`. Two stored copies can disagree, and a disagreement between "which frame was this" and "which frame do we say this was" makes the audit trail worthless. |
| §5.1 requires capture-level stats but `read_frames` returns an iterator | `CaptureStats` is an optional caller-owned accumulator, updated as iteration advances. Counts are complete only once the iterator is exhausted, which a lazy reader cannot avoid and should not hide. |
| §5.1 does not say what to do with a frame that peels cleanly but carries no payload | Counted in `frames_without_payload`, not yielded. A bare TCP ACK is not undecodable and has nothing to dissect. The four counters must sum to frames read, and `accounts_for_every_frame()` asserts it. |
| §5.2 says `values: tuple[int, ...]` without saying what a value *is* across function codes | Register functions give one entry per 16-bit register; bit-packed payloads give one entry per coil (0/1), unpacked LSB-first. Where the coil count is on the wire (FC 15) exactly that many are unpacked; where it is not (FC 1/2 responses) all `byte_count * 8` are, and up to seven trailing entries are padding — reported rather than guessed away. FC 5 carries a genuine 16-bit field and is reported raw. |
| Whether an illegal-but-well-formed value (FC 5 with a value other than `0x0000`/`0xFF00`) is a parse failure | No. The frame is structurally sound; whether a device should have sent it is a behavioural question for P2. Reported as it arrived. |
| §5.4 says direction comes from "structure + port direction", which can conflict | Direction is a transport fact decided by which end holds port 502. The exception bit is a structural fact and drives exception decoding regardless of direction. When both ends are port 502 the answer is `UNKNOWN` and the body is left undecoded rather than read through a possibly-wrong layout. |
| What to do with a capture whose link type is not Ethernet | Every frame counted undecodable, with `link_type` recorded so a capture that yields nothing explains itself. Peeling a non-Ethernet frame as Ethernet would produce confident nonsense. |
| What to do with a corrupt record header mid-capture | Stop the read and set `truncated`. Record framing has no marker to resynchronise on, so scanning forward is guesswork whose outcome an adversary picks. Everything read before it is still delivered. |
| Test layout: §4 says one test module per source module, but the fuzz suite spans all of them | `test_hardening.py` is a fifth module. §6.4 calls it the defining criterion and it tests a property of the pipeline rather than of any one file. |

## Consequences

**Good.** Atlas can ingest industrial captures and produce typed, traceable Modbus messages that
are safe against hostile input, measured by 205 tests, 100% line and branch coverage on the new
subpackage, and 8/8 injected bugs caught. The seam for further protocols is proved by a stub. One
real defect was found and fixed before it could reach P2.

**Costs and limits, carried forward.**

- No TCP stream reassembly, so pipelined or split ADUs are refused rather than decoded (Decision 5).
- Stateless dissection, so no request/response correlation and no back-filled fields (Decision 4).
- Ethernet link type only; other DLTs are counted, not peeled.
- One protocol. A capture that is mostly DNP3 will be mostly `UnparsedMessage`, which the coverage
  counters will say plainly.
- dpkt is untyped, mitigated by confining it to one function (Decision 1).

## What P2 may assume exists

- `from phos.atlas.packet import dissect_capture, DissectorRegistry, ModbusDissector` — and the
  same three names from `phos.atlas`.
- `dissect_capture(path, registry, stats=None)` is the entry point: lazy, and yielding
  `IcsMessage | MalformedFrame` in capture order.
- Every result carries a `FrameSource`, so any feature P2 derives can be traced to a specific frame
  in a specific file (Constitution §3.2).
- `CaptureStats` is how P2 states coverage honestly. Frames that never became a `RawFrame` appear
  in no stream and only in those counters.
- Adding a protocol means implementing `ProtocolDissector` and registering it. A new dissector
  earns its place by passing the fuzz suite; that is a contract on the seam, not a convention.
