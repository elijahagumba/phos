# ADR 0345 — The packet foundation is declared before it is built

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Build brief G, foundation
- **Supersedes:** nothing
- **Depends on:** [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md)

## Context

ADR 0344 opened the programme and left this file reserved. No foundation code
exists. `read_frames` peels Ethernet and then drops the header. It does not
reassemble TCP. `ModbusDissector.dissect` takes one `RawFrame`. Modbus claims
port 502 by port alone.

This record freezes the bar. It does not report a result.

## Decision

**The foundation is a bounded stream beside the old path, not a change to Modbus.**

`modbus.py` is not edited. `dissect_capture` still yields one result per
non-empty TCP or UDP payload. Empty TCP acknowledgements stay out of that
stream. New fields on `RawFrame` are optional and default to absent, so a frame
built the old way still validates.

### Link fields

RFC 894 places a 48-bit destination, a 48-bit source, and a 16-bit type after
them. `read_frames` copies those onto `RawFrame` as `dst_mac`, `src_mac`
(lowercase hex, colon-separated), and `ethertype` (the integer in that 16-bit
field). A value of `0x8100` is not called a VLAN. IEEE 802.1Q is not quoted
here, so the reader does not skip a tag and does not rename the field.

TCP sequence numbers are the 32-bit values RFC 9293 defines, arithmetic modulo
2^32. A TCP frame also carries `tcp_seq`. UDP leaves it absent.

### Reassembly

New module `src/phos/atlas/packet/reassembly.py`. It does not import `modbus`.

A flow is one direction: source IP, source port, destination IP, destination
port. Caps, all PHOS limits:

| Name | Value |
|---|---|
| `MAX_BUFFERED_BYTES_PER_FLOW` | 131072 |
| `MAX_CONCURRENT_FLOWS` | 256 |
| `MAX_OUT_OF_ORDER_SEGMENTS` | 16 |
| `MAX_SEGMENT_OCTETS` | 65535 |

A segment longer than 65535 octets is refused and not stored. A segment that
would push the flow's buffered octets over 131072 is refused and not stored.
The 17th stored out-of-order segment is refused and not stored. The 257th
concurrent flow is refused and not stored. A byte range that overlaps a byte
already buffered is a refusal of the flow, not a last-write-wins splice. A gap
is waited on, inside the out-of-order cap. It is not filled with zeros.

A refusal is a `FlowRefusal` value. It is not an exception. After a flow is
refused, a later segment on it produces another `FlowRefusal` and is not
buffered. Other flows continue.

`push` returns the contiguous octets that became available, in order, and
nothing else. It does not truncate a segment to fit the cap.

### Framing

`ContiguousStream.take(n)` returns n octets or `None` if fewer are buffered.
`take_pdu(header_octets, length_of)` reads the header only when it is present,
asks `length_of` for the total PDU length, checks that length against the
header size and against `MAX_BUFFERED_BYTES_PER_FLOW` before removing the body,
and returns `None` when the body has not arrived. A length that fails the check
is a `FlowRefusal`, and the stream is not consumed past the failed header.
`length_of` is not allowed to be called on a short header.

### Pairing

New module `src/phos/atlas/packet/pairing.py`.

| Name | Value |
|---|---|
| `MAX_OPEN_PAIRS` | 256 per flow |
| `PAIR_EXPIRY` | 60 seconds of capture timestamp |

The key is the flow plus the transaction id as bytes the caller supplies. The
caller names which observation is the request. A later observation with the
same key and the other direction completes the pair. An observation that would
be the 257th open pair is a recorded miss and is not stored. An open pair whose
capture timestamp is more than 60 seconds behind the observation just offered
is emitted as a recorded miss and then dropped. The drop is the miss. It is not
silent. This module does not write into a `ModbusMessage`.

### Claiming

`DissectorRegistry.dispatch` stays first-true-wins in registration order. A
dissector may look at the payload inside `claims`. The first dissector that
returns true is the only one that runs. A test with two payload-aware stubs
proves a decline falls through, and that registering `ModbusDissector` first
still keeps port 502 from a later stub. `modbus.py` is not edited to make that
test pass.

### Fuzz

Seed `20261029`. At least 2,000 random segment lists. The four claims: nothing
raises, a delivered slice is a prefix of the concatenation of the non-overlapping
in-order bytes, no flow's buffer exceeds 131072 and no reassembler holds more
than 256 flows or 16 out-of-order segments, and the corpus finishes in under
30 seconds.

## What met means

All of the above have tests, the existing suite stays green, `mypy --strict src`
and `ruff check` are clean, and `modbus.py` has an empty diff.

## What refuses this

A cap is honoured by shortening a buffer and continuing. An overlap keeps one
of the two copies. A `FlowRefusal` is raised as an exception instead of
returned. Empty Modbus-port acknowledgements become `MalformedFrame`s on the
old path. `modbus.py` changes. The fuzz corpus raises, or exceeds a cap, or
exceeds 30 seconds.

## What this record does not do

No protocol module. No corpus score. No held-out file. No edit to the six law
predicates. v1 stays 8 of 12. P1 stays blocked.
