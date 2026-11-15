# ADR 0347 — The S7comm lane is declared, and it is the ISO-on-TCP envelope that is read

- **Status:** Accepted
- **Date:** 2026-11-05
- **PART:** Build brief G, S7comm lane
- **Supersedes:** nothing
- **Depends on:** [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0345](0345-the-packet-foundation-is-declared.md),
  [ADR 0346](0346-the-packet-foundation-is-judged.md),
  [ADR 0422](0422-build-brief-g-is-unparked-against-the-refusal-register.md)
- **Spec-audit:** `eval_runs/build/lane-g/s7comm/spec-audit.md`

## Context

Build brief G's standing rank puts S7comm second, behind only the foundation.
The foundation is judged met (ADR 0346). This record declares the lane's bar
and is committed before a line of `s7comm.py` exists. It is not a result.

The pick, written before this record, is one sentence: **S7comm first because a
software download is the act `program_transfer` already knows — brief G's value
test (a) — and because RFC 1006 and RFC 905 make its transport the one layer
this lane can cite from primary text, which is value test (c).** DNP3 outranks
it only on capture availability, and no licence-clean S7comm capture is
registered either, so the two are equal on test (b) and S7comm wins on (a).

A spec-auditor who did not write this record ran before it and produced
`eval_runs/build/lane-g/s7comm/spec-audit.md`. It signed eight of the brief's
nine constant groups and found **four places where the brief is wrong**. This
record follows the auditor, not the brief, and says where.

## Decision

### The lane reads the envelope, and names it honestly

**The dissector decodes TPKT and COTP. It does not decode an S7 application
message, because no primary source publishes one.** The message type it emits
is therefore named `iso-tsap` — the IANA service name registered on this port —
and never `s7comm`. A consumer that reads `protocol == "iso-tsap"` knows Atlas
has read the transport that S7 travels in and has not read S7.

This is not a retreat from the lane. It is the lane's honest ceiling, and the
brief states it: *"The transport may still be judged met."*

### The claim rule, and the ambiguity this record resolves

ADR 0345 froze: *"TCP port 102 is not a port claim for S7comm or for MMS.
Neither protocol is named from the port alone."* Brief G's done-list then asks
that *a version other than 3 on a claimed frame is `BAD_HEADER_FIELD`*, which is
unreachable if the version is part of the selector.

**Resolved as follows, and recorded because it is an ambiguity rather than a
restatement.** Port 102 **is** a port claim — for `iso-tsap`. IANA registers
exactly one service on 102, `iso-tsap`, described "ISO-TSAP Class 0", for both
tcp and udp. Claiming that port carries ISO-on-TCP is a claim about the
registry, which is a primary source. What ADR 0345 forbids, and this record
keeps forbidden, is **naming S7 or MMS from the port alone**. The dissector:

- claims TCP frames with port 102 at either end, whatever the payload;
- decodes the envelope, and refuses a malformed one rather than falling through
  to `UnparsedMessage`;
- reports `iso-tsap`, never `s7comm`, never `mms`.

Claiming by port and then refusing is the Modbus precedent (ADR 0012): traffic
that is not Modbus on 502 is still a Modbus refusal, because falling through to
`UnparsedMessage` reads as "no dissector covers this", which is the wrong thing
to say about rubbish aimed at a PLC. The same argument holds on 102, and the
same discipline applies — the refusal is recorded, and it is a finding.

A consequence, stated so nobody discovers it: **an IEC 61850 MMS frame on 102
is decoded by this module as a valid `iso-tsap` message** with its application
payload unread. That is correct. An MMS frame *is* an ISO-on-TCP frame. The
module does not claim it is S7 and does not claim it is MMS.

### Constants, and their citations

Every value below was signed by the spec-auditor against the primary text named.
No constant came from Wireshark, Scapy, Snap7, python-snap7, pycomm3 or any
other dissector.

| Constant | Value | Source |
|---|---|---|
| Service on port 102 | `iso-tsap`, tcp and udp, "ISO-TSAP Class 0" | IANA Service Name and Transport Protocol Port Number Registry |
| TPKT header | 4 octets: version (8 bits), reserved (8 bits), packet length (16 bits) | RFC 1006 §6 |
| Version | always **3** | RFC 1006 §6 |
| Packet length | min **7**, max **65535**, counting the header | RFC 1006 §6 |
| Maximum TPDU | **65531** octets | RFC 1006 §6 |
| Reserved octet | record it; never refuse it for its value | RFC 1006 §6 (silent) + RFC 2126 §4.3, §6.10 |
| CR | `1110 xxxx`, credit `0000` in class 0 | RFC 905 §13.1 Table 8, §13.3.3 |
| CC | `1101 xxxx` | RFC 905 §13.1 Table 8 |
| DR | `1000 0000` | RFC 905 §13.1 Table 8, §13.5.3 |
| DT | `1111 0000` in class 0 | RFC 905 §13.1 Table 8, §13.7.3 |
| ER | `0111 0000` | RFC 905 §13.1 Table 8, §13.12.3 |
| ED | `0001 0000`, permitted on this port though not a class-0 TPDU | RFC 905 §13.1 Table 8, §13.8; RFC 1006 §5, §6 |
| Class-0 DT fixed part | octets 2 and 3 | RFC 905 §13.7.3 |
| EOT | bit 8 of octet 3 (mask `0x80`) | RFC 905 §13.7.3 |
| TPDU-NR | bits 7–1 of octet 3, zero in class 0 | RFC 905 §13.7.3 |
| Bit numbering | bit 8 is the high bit; bit 1 the low | RFC 905 §13.2 |
| Length indicator | octet 1; max **254**; **255** reserved for extensions | RFC 905 §13.2.1 |
| LI counts | header including parameters, **excluding** itself and user data | RFC 905 §13.2.1 |
| CR maximum | **128** octets | RFC 905 §13.3 |
| Preferred class | CR/CC octet 7 bits 8–5; `0000` = class 0 | RFC 905 §13.3.3 e) |
| Port 102 carries S7 | yes, ISO-on-TCP per RFC 1006 | Siemens *Communication Function Manual*, **11/2025 A5E03735815-AN**, §5.2, printed p.38 |

**No `ProgramAct` is constructible from this lane.** The application opcode is
unverified from a primary source and the auditor found positive evidence that
none will be published: the same Siemens manual states S7 communication is
"vendor-specific communication between SIMATIC CPUs (not an open standard)"
(§9, printed p.161). This is a publication decision, not a failed search.

### Where this record overrules the brief

The auditor found four defects. Each changes what may be coded.

1. **`65524` is not a bound and is not coded.** RFC 1006 §6 says a 65535-octet
   packet "permits a maximum TSDU size of 65524 octets", which is 65531 − 7 —
   but RFC 905 §13.7.5 limits the user-data field to the negotiated TPDU size
   **minus 3 octets** in classes 0 and 1, because the class-0 DT header is three
   octets. 65531 − 3 = **65528**. The memo contradicts its own rule and no
   erratum resolves it. Only **65535** (TPKT) and **65531** (TPDU) are coded.
   `65524` is recorded here as quoted-and-not-used.
2. **A non-zero reserved octet is never refused.** RFC 1006 never defines the
   octet. RFC 2126 §6.10 is the positive authority: it "should be ignored on
   input" to avoid interoperability problems with RFC 1006.
3. **A COTP class other than 0 is never refused for being non-zero.** Siemens
   labels its ISO-on-TCP open-communication transport "(Class 4)" (11/2025 -AN
   §8.2, Table 8-1), and RFC 2126 adds class 2 over TCP. A hard class check
   would manufacture false malformations on real Siemens traffic. The octet is
   recorded and nothing is inferred from it.
4. **A CR or CC carrying user data, or more than two parameters, is never
   refused.** RFC 905 §8.2.2 c) and d) forbid both in bare ISO class 0, but
   RFC 1006 §5 opens with "identical to the protocol for ISO transport class 0,
   **with the following exceptions**", the first being that initial data "may be
   exchanged during connection establishment". A dissector that refused it
   would refuse lawful RFC 1006 setup. What is kept from that clause is the
   genuine bound in RFC 905 §13.3: a CR TPDU shall not exceed 128 octets.

### The bar this lane is judged against

Done, and the judge tests exactly these:

1. A payload shorter than four octets is `SHORT_HEADER`.
2. A TPKT version other than 3 is `BAD_HEADER_FIELD`.
3. A declared packet length below 7 is `FIELD_OUT_OF_RANGE`, checked **before**
   any slice is taken.
4. A declared length greater than the bytes present is `LENGTH_MISMATCH`, never
   a read past the buffer and never an allocation of the declared size.
5. A declared length smaller than the bytes present is `TRAILING_BYTES`.
6. A length indicator of 255 is `FIELD_OUT_OF_RANGE` (reserved for extensions).
7. An LI that claims more header than the packet contains is
   `INCONSISTENT_COUNT`; for a DT, a LI below 2 is `INCONSISTENT_COUNT` because
   the class-0 fixed part needs octets 2 and 3.
8. `reserved` is recorded on every decoded message and is never a refusal
   reason, for any value.
9. A COTP class other than 0 is recorded and never a refusal reason.
10. A CR/CC with user data or a third parameter decodes; it is never refused.
11. EOT is bit 8 of octet 3 and TPDU-NR is bits 7–1 of octet 3 on a DT; no
    other bit position is used.
12. No `ProgramAct`, no station, no peer role and no application value is
    produced by any input.
13. The seeded fuzz corpus (seed **20261105**, declared below) passes the four
    claims in `tests/atlas/packet/test_hardening.py`.
14. `modbus.py` is untouched and `tests/atlas/packet/test_dissect.py` still
    passes.
15. Every decoded message and every refusal traces to the frame it came from.

Refused, in brief G's sense — any one of these is the lane refused:

- the module emits a `ProgramAct`, a station, or an application field;
- the dissector reports `protocol == "s7comm"` or claims to have read S7;
- a non-zero `reserved`, a class other than 0, or a CR/CC with user data
  becomes a `MalformedFrame`;
- `65524` appears in the source as a bound;
- a declared length sizes an allocation or a slice before it is compared with
  the bytes present and with 65535;
- the implementation raises on any input, or wraps the decode in `try`.

Also refused, and it is not a defect to be fixed: **the act mapping.** No job
byte is cited, so no act is built. The wiring lane (ADR 0361) may construct a
`ProgramAct` only from a job this record's auditor signed, and it signed none.

### The seeded corpus

Seed **20261105**, fixed and written here. Two thousand random payloads on port
102 and two thousand mutated valid envelopes, in the style of
`test_hardening.py`, plus a truncation sweep at every byte of every valid
fixture and a length-lie sweep over the 16-bit field. Changing the seed is
changing the experiment.

### Files

- `src/phos/atlas/packet/s7comm.py`
- `tests/atlas/packet/test_s7comm.py`, `tests/atlas/packet/test_s7comm_hardening.py`
- this record, and `0348-s7comm-dissection-is-judged.md` for the verdict

The message type lives in `s7comm.py` as a subclass of `IcsMessage`, so the
shared `messages.py` is not widened. Package exports are added by the
orchestrator, not the engineer.

## What this record does not do

It scores nothing. It opens no held-out or red-tier corpus, appends no row to
`eval_runs/log.jsonl`, and gives no capture bytes. It does not edit `modbus.py`,
the six law predicates in `declared_law.py`, `law_inlet.py`, or any brief H
file. It starts no Intelligence, API, UI, socket, TAP or live capture. It fills
none of 0277–0284 and does not merge ADR 0343. **No lane output may be quoted
as recall, precision, a false-alert rate, or evidence for A2, A3 or A7.** Reach
is not performance (ADR 0422).

## What would reverse this

A primary source that names an S7 job byte, which would let the application be
read and the act mapping be attempted; or a later record finding that claiming
port 102 mislabels traffic in a way this record's argument does not cover.
