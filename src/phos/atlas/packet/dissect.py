"""The seam: how a frame finds a dissector, and what happens when none wants it.

`dissect_capture` is the one entry point P2 consumes — a capture path in, a lazy stream of typed
outcomes out. Everything between is arranged around a single constraint: **adding DNP3, S7comm or
EtherNet/IP later must not edit anything that already works.** A new protocol is a new object
implementing `ProtocolDissector` and one more entry in a registry. `tests/atlas/packet/
test_dissect.py` proves that with a stub dissector for a protocol PHOS does not implement, which
is the only honest way to test a seam: if the test needs `modbus.py`, the seam is decorative.

**Dispatch is first-claim-wins, and the registry is immutable.** `with_dissector` returns a new
registry rather than mutating one, so a registry passed to a running pipeline cannot change under
it and two callers cannot fight over global state (Constitution §6). Order is registration order,
which makes precedence between two dissectors that both claim a port a caller's declaration rather
than a dictionary's whim. `claims` may look at the payload. The first dissector that returns true
is the only one that runs. A decline falls through.

**A registry is a claim about coverage, so it is never implicit.** `dissect_capture` requires one.
There is no default, because a default would let a caller believe a capture had been examined for
protocols the registry never contained, and the resulting silence would look identical to a clean
capture.

**Nothing is swallowed here.** A dissector that raises is a PHOS defect, not hostile input, and
dispatch deliberately does not catch it: converting a bug into a `MalformedFrame` would turn a
crash into a quietly wrong coverage number, which is the failure mode this package exists to
prevent. Safety against hostile bytes is the dissector's own job, done by bounds-checking before
reading rather than by a net underneath — and `test_hardening.py` is what makes that claim
inspectable rather than aspirational. See ADR 0012.
"""

import logging
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from phos.atlas.packet.capture import CaptureStats, read_frames
from phos.atlas.packet.frame import RawFrame
from phos.atlas.packet.messages import IcsMessage, MalformedFrame, UnparsedMessage

__all__ = [
    "DissectionResult",
    "DissectorRegistry",
    "ProtocolDissector",
    "dissect_capture",
]

logger = logging.getLogger(__name__)

DissectionResult = IcsMessage | MalformedFrame
"""What dissecting one frame can produce: a message understood, or a refusal recorded.

`UnparsedMessage` is an `IcsMessage`, so unclaimed traffic arrives on the first branch carrying
nothing decoded — present in the stream, and impossible to mistake for a decoded message.
"""


@runtime_checkable
class ProtocolDissector(Protocol):
    """What a protocol implementation must provide to join the pipeline.

    Two responsibilities, kept apart on purpose. `claims` decides *whether* a frame is this
    dissector's business and must be cheap, because it runs on every frame of every capture.
    `dissect` decodes, and runs only on frames already claimed.

    **The contract `dissect` must honour: it does not raise.** Every frame it is handed contains
    adversary-chosen bytes, and a dissector that throws takes the pipeline down with it. Malformed
    input is a `MalformedFrame` return value, never an exception. Nothing enforces this at runtime
    — a net underneath would hide defects — so a new dissector earns its place in a registry by
    passing the fuzz suite in `tests/atlas/packet/test_hardening.py`.
    """

    @property
    def name(self) -> str:
        """Protocol name this dissector decodes, unique within a registry."""
        ...

    def claims(self, frame: RawFrame) -> bool:
        """Whether this dissector is responsible for the frame.

        Args:
            frame: The peeled frame.

        Returns:
            True if this dissector should decode it. Claiming a frame and then refusing it is a
            `MalformedFrame`, which is a finding; declining to claim it is a coverage gap. The two
            are different answers and the choice here is what separates them.
        """
        ...

    def dissect(self, frame: RawFrame) -> DissectionResult:
        """Decode a claimed frame, or record why it could not be decoded.

        Args:
            frame: The peeled frame, whose payload is entirely untrusted.

        Returns:
            The decoded message, or a `MalformedFrame` naming what failed. Never raises.
        """
        ...


class DissectorRegistry:
    """An ordered, immutable set of dissectors, and the dispatch rule over them.

    Not a Pydantic model: it holds behaviour rather than data, and its invariant — no two
    dissectors under one name — is checked once at construction and then cannot be violated,
    because there is no mutation API.
    """

    def __init__(self, dissectors: Sequence[ProtocolDissector] = ()) -> None:
        """Build a registry over the given dissectors, in precedence order.

        Args:
            dissectors: The dissectors to dispatch to, most specific first. An empty registry is
                valid and leaves every frame unparsed, which is the honest result of having
                declared no coverage at all.

        Raises:
            ValueError: If two dissectors share a name. Every message carries the name of the
                dissector that produced it, so a duplicate makes that field ambiguous and any
                per-protocol count taken from a capture wrong.
        """
        self._dissectors = tuple(dissectors)
        self._names = tuple(dissector.name for dissector in self._dissectors)
        duplicates = sorted({name for name in self._names if self._names.count(name) > 1})
        if duplicates:
            raise ValueError(f"two dissectors registered under one name: {', '.join(duplicates)}")

    @property
    def dissectors(self) -> tuple[ProtocolDissector, ...]:
        """The registered dissectors, in precedence order."""
        return self._dissectors

    @property
    def names(self) -> tuple[str, ...]:
        """The registered protocol names, in precedence order."""
        return self._names

    def with_dissector(self, dissector: ProtocolDissector) -> "DissectorRegistry":
        """Return a new registry with ``dissector`` appended at lowest precedence.

        Args:
            dissector: The dissector to add.

        Returns:
            A new registry. This one is unchanged, so a registry already handed to a running
            pipeline cannot shift underneath it.

        Raises:
            ValueError: If the name is already registered.
        """
        return DissectorRegistry([*self._dissectors, dissector])

    def dispatch(self, frame: RawFrame) -> DissectionResult:
        """Hand a frame to the first dissector that claims it.

        Args:
            frame: The peeled frame.

        Returns:
            Whatever the claiming dissector returned, or an `UnparsedMessage` if none claimed it.
            Traffic on a protocol no dissector implements still produces an object, so the gap in
            coverage is a number rather than a silence.
        """
        for dissector in self._dissectors:
            if dissector.claims(frame):
                return dissector.dissect(frame)
        return UnparsedMessage(
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            payload_length=len(frame.payload),
        )


def dissect_capture(
    path: Path, registry: DissectorRegistry, stats: CaptureStats | None = None
) -> Iterator[DissectionResult]:
    """Read a capture and dissect every frame in it, lazily.

    The one public entry point for turning a file into typed messages, and the function P2 will
    build command-behaviour features on top of.

    Args:
        path: The ``.pcap`` or ``.pcapng`` file to read.
        registry: The dissectors to dispatch to. Required rather than defaulted: it is a
            declaration of what this run claims to understand.
        stats: Optional caller-owned capture accumulator, updated as iteration advances. Frames
            that never became a `RawFrame` are counted there and appear nowhere in this stream,
            which is why reading it matters for any coverage claim.

    Yields:
        One `IcsMessage` or `MalformedFrame` per frame that carried a transport payload, in
        capture order.

    Raises:
        CaptureError: If the file is not a readable capture. Surfaces on first iteration.
    """
    logger.debug("dissecting %s with dissectors: %s", path, ", ".join(registry.names) or "none")
    for frame in read_frames(path, stats):
        yield registry.dispatch(frame)
