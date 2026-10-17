"""Grade C of the plant model: control relations a controller's own traffic shows (ADR 0130).

A statistical map guesses direction from co-movement. A controller's network traffic states part
of it outright: when controller *P* reads point *X* from another device, *X* is an input to logic
running on *P*, and the only things that logic can drive are the actuators *P* hosts. So each
such read is a claim, **"X drives one of P's actuators"**, and the claim is a set, not a guess at
one member. It is narrowed to a single actuator only when a statistical link agrees.

**What counts.** A device is a controller when it both serves points (other devices read or
write them on it) and reads points from others. A supervisory client that only reads, such as
an operator console or a historian, is not a controller: polling every point says nothing about
what drives what, so it makes no claim. Neither does a device that serves nothing, whoever it is.

**What it cannot see.** A controller reads its own I/O locally, off the network. So the network
shows cross-controller relations only, never a loop closed inside one controller. That is a
property of the evidence, recorded with every result rather than hidden.

The roles come from the role file (`phos.atlas.signal_roles`); a point with no declared actuator
role is never a claimed output. This module holds no detection logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from phos.atlas.signal_roles import ControlLoop, SignalRole, SignalRoles

__all__ = [
    "Exchange",
    "NetworkClaim",
    "network_claims",
    "score_claims",
]


@dataclass(frozen=True)
class Exchange:
    """One read or write: ``client`` asked ``server`` about ``point``."""

    client: str
    server: str
    function: str
    point: str


@dataclass(frozen=True)
class NetworkClaim:
    """``point`` drives one of ``actuators``, because ``controller`` reads it over the network.

    ``narrowed`` is the single actuator a statistical link agrees with, if exactly one does.
    """

    controller: str
    point: str
    actuators: tuple[str, ...]
    reads: int
    narrowed: str | None = None


def network_claims(
    exchanges: Iterable[Exchange],
    roles: SignalRoles,
    statistical: Mapping[str, Iterable[str]] | None = None,
) -> tuple[NetworkClaim, ...]:
    """Every grade-C claim the traffic supports, in (controller, point) order.

    Args:
        exchanges: The observed traffic, from attack-free development data.
        roles: The corpus's declared roles; only declared actuators can be claimed outputs.
        statistical: Per point, the signals a statistical map says it drives. Used only to narrow.
    """
    hosted: dict[str, str] = {}
    servers: set[str] = set()
    reads: dict[tuple[str, str], int] = {}
    for exchange in exchanges:
        servers.add(exchange.server)
        hosted.setdefault(exchange.point, exchange.server)
        if exchange.function == "read":
            key = (exchange.client, exchange.point)
            reads[key] = reads.get(key, 0) + 1
    declared = set(roles.signals)
    actuators_on: dict[str, tuple[str, ...]] = {}
    for point, server in sorted(hosted.items()):
        if point in declared and roles.role_of(point) is SignalRole.ACTUATOR:
            actuators_on[server] = (*actuators_on.get(server, ()), point)
    claims: list[NetworkClaim] = []
    for (client, point), count in sorted(reads.items()):
        if client not in servers or hosted.get(point) == client or point not in declared:
            continue
        outputs = actuators_on.get(client, ())
        if not outputs:
            continue
        agreeing = [a for a in outputs if a in set((statistical or {}).get(point, ()))]
        narrowed = agreeing[0] if len(agreeing) == 1 else None
        claims.append(NetworkClaim(client, point, outputs, count, narrowed))
    return tuple(claims)


def _true(claim: NetworkClaim, loops: Iterable[ControlLoop], narrowed: bool) -> bool:
    outputs = {claim.narrowed} if narrowed and claim.narrowed else set(claim.actuators)
    return any(
        claim.point in {loop.reading, loop.setpoint} and outputs & set(loop.outputs)
        for loop in loops
    )


def score_claims(
    claims: Iterable[NetworkClaim], roles: SignalRoles, hosted: Mapping[str, str]
) -> dict[str, object]:
    """Judge claims against the declared loops (ADR 0130 falsifier 1).

    A claim is true when some declared loop reads its point, or holds it as its setpoint, and
    moves an actuator in its set. Recall counts only the declared loops the network could show:
    those whose reading is hosted on a different device from every one of its outputs.
    """
    claimed = tuple(claims)
    loops = roles.loops
    true = [c for c in claimed if _true(c, loops, narrowed=False)]
    narrowed = [c for c in claimed if c.narrowed is not None]
    narrowed_true = [c for c in narrowed if _true(c, loops, narrowed=True)]
    visible = [
        loop
        for loop in loops
        if loop.reading is not None
        and loop.reading in hosted
        and all(hosted.get(o) not in {None, hosted[loop.reading]} for o in loop.outputs)
    ]
    found = [
        loop
        for loop in visible
        if any(c.point == loop.reading and set(c.actuators) & set(loop.outputs) for c in claimed)
    ]
    return {
        "claims": len(claimed),
        "true": len(true),
        "precision": len(true) / len(claimed) if claimed else None,
        "narrowed": len(narrowed),
        "narrowed_true": len(narrowed_true),
        "loops_declared": len(loops),
        "loops_visible_on_the_network": len(visible),
        "visible_loops_found": len(found),
        "recall_of_visible": len(found) / len(visible) if visible else None,
    }
