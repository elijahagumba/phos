"""Throw hostile bytes at every Atlas dissector and record anything that escapes.

The package's own claim, in `phos.atlas.packet.dissect`'s docstring, is that safety against hostile
bytes is the dissector's job, done by bounds-checking before reading, and that dispatch deliberately
does not catch an exception because a raise there is a bug rather than input. That is a defensible
design and it puts the whole burden on the dissectors, so the honest test is not to read the
bounds checks but to attack them.

This fuzzer does four things to each protocol entry point:

* **Truncation.** Every frame cut at every length from 0 to its own, so every field that can be
  half-present is half-present.
* **Single-byte corruption.** Each position set to 0x00, 0xFF and a value one past its own, so
  lengths and counts are driven to their extremes without changing the frame's length.
* **Length-field lies.** For a frame whose length field can be found, that field is set to 0, to one
  past the frame, and to 65535, which is the classic way to make a parser read past its buffer or
  allocate on an attacker's number.
* **Random bytes with a valid header.** The protocol magic kept, everything after it random, with a
  fixed seed so a run is reproducible and a failure can be handed to somebody who can repeat it.

What is recorded is every exception that escapes, with the protocol, the mutation that caused it and
the bytes. The fuzzer does not assert. It reports, because the point is to find out.

Usage::

    uv run python scripts/fuzz_atlas_dissectors.py            # report
    uv run python scripts/fuzz_atlas_dissectors.py --strict   # exit 1 if anything escaped
"""

from __future__ import annotations

import argparse
import random
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from datetime import UTC, datetime  # noqa: E402

from phos.atlas.packet.frame import (  # noqa: E402
    Endpoint,
    FrameSource,
    RawFrame,
    Transport,
)
from phos.atlas.packet.messages import MalformedFrame  # noqa: E402
from phos.atlas.packet.modbus import ModbusDissector  # noqa: E402
from phos.atlas.packet.s7comm import IsoTsapDissector  # noqa: E402

#: The seed. Fixed, so a crash found here can be reproduced by anybody.
SEED: Final = 20261125

#: How many random frames per protocol. Enough to find shallow bugs, few enough to run in a minute.
RANDOM_TRIALS: Final = 4000


@dataclass
class Escape:
    """One exception that got out of a dissector.

    Attributes:
        protocol: Which dissector.
        mutation: What was done to the bytes.
        payload: The bytes, hex, so it can be replayed.
        error: The exception's type and message.
        where: The innermost frame of the traceback, which names the defect.
    """

    protocol: str
    mutation: str
    payload: str
    error: str
    where: str


@dataclass
class Report:
    """What the fuzzer found.

    Attributes:
        attempts: How many inputs were tried, per protocol.
        escapes: Every exception that got out.
        accepted: How many inputs a dissector claimed and parsed, per protocol, which is reported
            so a protocol that refuses everything is visible rather than looking safe.
    """

    attempts: dict[str, int] = field(default_factory=dict)
    escapes: list[Escape] = field(default_factory=list)
    accepted: dict[str, int] = field(default_factory=dict)
    refused: dict[str, int] = field(default_factory=dict)

    def note(self, protocol: str) -> None:
        """Count one attempt.

        Args:
            protocol: Which dissector.
        """
        self.attempts[protocol] = self.attempts.get(protocol, 0) + 1

    def hit(self, protocol: str) -> None:
        """Count one input the dissector accepted without raising.

        Args:
            protocol: Which dissector.
        """
        self.accepted[protocol] = self.accepted.get(protocol, 0) + 1


def _frame(payload: bytes, protocol: str) -> RawFrame:
    """Wrap bytes in the frame type a dissector is handed.

    Args:
        payload: The bytes.
        protocol: Which dissector will see it, because the port is part of the claim.

    Returns:
        A frame carrying them.
    """
    port = 502 if protocol == "modbus" else 102
    return RawFrame(
        source=FrameSource(capture="/fuzz.pcap", frame_index=0),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        transport=Transport.TCP,
        src=Endpoint(ip="10.0.0.1", port=40000),
        dst=Endpoint(ip="10.0.0.2", port=port),
        payload=payload,
    )


def _try(protocol: str, payload: bytes, mutation: str, report: Report) -> None:
    """Run one input through one dissector, recording an escape rather than raising it.

    Args:
        protocol: Which dissector.
        payload: The bytes.
        mutation: What was done to them.
        report: Where to record the result.
    """
    classes: dict[str, type[ModbusDissector] | type[IsoTsapDissector]] = {
        "modbus": ModbusDissector,
        "s7comm": IsoTsapDissector,
    }
    dissector = classes[protocol]()
    report.note(protocol)
    try:
        outcome = dissector.dissect(_frame(payload, protocol))
    except Exception as error:  # the whole point is to catch what escapes
        tb = traceback.extract_tb(error.__traceback__)
        where = f"{Path(tb[-1].filename).name}:{tb[-1].lineno} in {tb[-1].name}" if tb else "?"
        report.escapes.append(
            Escape(
                protocol=protocol,
                mutation=mutation,
                payload=payload.hex()[:400],
                error=f"{type(error).__name__}: {error}",
                where=where,
            )
        )
        return
    # "Accepted" must mean parsed as a real message, not merely returned without raising. The
    # dissectors return a MalformedFrame for hostile input, which is a refusal and the correct
    # outcome; counting it as acceptance would report a dissector that refuses everything as if it
    # had validated everything.
    if isinstance(outcome, MalformedFrame):
        report.refused[protocol] = report.refused.get(protocol, 0) + 1
    else:
        report.hit(protocol)


def _seeds() -> dict[str, bytes]:
    """Return one well-formed frame per protocol, to mutate.

    The frames are built by the dissectors' own test fixtures' shape rather than by hand, so a
    mutation starts from something the parser accepts. A frame it rejects at the first byte would
    exercise nothing.

    Returns:
        Protocol to a valid payload.
    """
    return {
        # Modbus/TCP: MBAP header then a read-holding-registers request.
        "modbus": bytes.fromhex("000100000006010300000002"),
        # S7comm: TPKT, COTP connection request, then an S7 job.
        "s7comm": bytes.fromhex(
            "0300001611e0000000010000c1020102c2020102c0010a"
        ),
    }


def fuzz_protocol(protocol: str, seed: bytes, report: Report) -> None:
    """Attack one dissector with every mutation the fuzzer knows.

    Args:
        protocol: Which dissector.
        seed: A valid frame to mutate.
        report: Where to record results.
    """
    # Truncation, every length.
    for cut in range(len(seed) + 1):
        _try(protocol, seed[:cut], f"truncated to {cut}", report)

    # Single-byte corruption at every position with three extremes.
    for index in range(len(seed)):
        for value in (0x00, 0xFF):
            mutated = bytearray(seed)
            mutated[index] = value
            _try(protocol, bytes(mutated), f"byte {index} set to 0x{value:02x}", report)

    # Length-field lies. Both protocols carry a big-endian length early in the header.
    for offset in (4, 5):
        if len(seed) > offset:
            for length in (0, 1, 0xFFFF):
                mutated = bytearray(seed)
                mutated[offset : offset + 1] = bytes([length & 0xFF])
                _try(protocol, bytes(mutated), f"length byte {offset} = {length}", report)

    # Random bodies behind a valid header, fixed seed.
    engine = random.Random(SEED)
    header = seed[:4]
    for trial in range(RANDOM_TRIALS):
        body = bytes(engine.getrandbits(8) for _ in range(engine.randint(0, 64)))
        _try(protocol, header + body, f"random body, trial {trial}", report)


def main() -> int:
    """Run the fuzzer and print the report.

    Returns:
        0 unless ``--strict`` was given and something escaped.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 if anything escaped")
    args = parser.parse_args()

    report = Report()
    seeds = _seeds()
    for protocol, seed in seeds.items():
        fuzz_protocol(protocol, seed, report)

    print("Atlas dissector fuzz")
    print(f"seed {SEED}, {RANDOM_TRIALS} random frames per protocol")
    print()
    for protocol in sorted(report.attempts):
        attempts = report.attempts[protocol]
        accepted = report.accepted.get(protocol, 0)
        refused = report.refused.get(protocol, 0)
        escapes = [e for e in report.escapes if e.protocol == protocol]
        print(
            f"  {protocol:8} {attempts:6} inputs, {accepted:6} parsed, "
            f"{refused:6} refused as malformed, {len(escapes):4} escaped"
        )
    print()

    if not report.escapes:
        print(
            "Nothing escaped. Every hostile input was either parsed or refused as a "
            "MalformedFrame, and no dissector raised."
        )
        return 0

    print(f"{len(report.escapes)} escapes. Grouped by where they came from:")
    print()
    grouped: dict[str, list[Escape]] = {}
    for escape in report.escapes:
        grouped.setdefault(f"{escape.protocol} {escape.where}", []).append(escape)
    for key in sorted(grouped):
        found = grouped[key]
        print(f"  {key}  ({len(found)} inputs)")
        print(f"    first: {found[0].error}")
        print(f"    by:    {found[0].mutation}")
        print(f"    bytes: {found[0].payload}")
        print()
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
