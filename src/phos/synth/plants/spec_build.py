"""The parts of drawing a plant that every family does the same way.

PART R2. A family's real content is its physics and its bounds. Around that sits a quantity of
assembly — rendering a tag for every role, inverting that into the role map, laying register
blocks out without overlapping, granting the operator its setpoints and nobody else anything —
which is identical from family to family and worth getting right once.

Everything here is a pure function of what it is given. Nothing draws: a family draws its numbers
through `phos.synth.families.bounded` so they land in the declared table, and hands the results
here. The one exception is `draw_naming_scheme`, which is a draw and says so in its name.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from phos.synth.command import WriteAuthority
from phos.synth.plant import ControlNetwork, NetworkNode, PhysicalUnit, RegisterBlock
from phos.synth.plant_spec import SignalRole
from phos.synth.randomise import NamingScheme, NumberStyle, StreamDraw

__all__ = [
    "SEPARATORS",
    "SUFFIXES",
    "RolePosition",
    "draw_naming_scheme",
    "modbus_network",
    "operator_authority",
    "render_tags",
    "roles_from_tags",
    "stage_units",
]

SEPARATORS: Final = ("_", "-", ".")
"""What a drawn tag name may join its parts with. Every real site picks one and sticks to it."""

SUFFIXES: Final = ("", ".PV", "_VAL")
"""Trailing text a drawn tag may carry, as a historian's attribute suffix."""

RolePosition = tuple[str, int, int]
"""A ``(role, train, stage)`` triple: where a signal sits in its process, independently of names."""


def draw_naming_scheme(draw: StreamDraw, prefixes: Sequence[str]) -> NamingScheme:
    """Draw how one plant spells its tag names.

    Args:
        draw: The naming stream. Kept separate from every other stream so that changing a site's
            tag convention cannot move a single physical parameter.
        prefixes: The prefixes this family's sites might use. Include ``""``: plenty of real
            sites have no prefix at all, and a detector that only ever saw prefixed tags has
            learned something about the generator rather than about plants.

    Returns:
        The scheme.
    """
    return NamingScheme(
        prefix=draw.choice("tag_prefix", tuple(prefixes)),
        separator=draw.choice("tag_separator", SEPARATORS),
        number_style=NumberStyle(
            draw.choice("tag_number_style", tuple(style.value for style in NumberStyle))
        ),
        upper=draw.uniform("tag_upper", 0.0, 1.0) < 0.5,
        suffix=draw.choice("tag_suffix", SUFFIXES),
        abbreviate=draw.uniform("tag_abbreviate", 0.0, 1.0) < 0.5,
    )


def render_tags(
    scheme: NamingScheme, positions: Sequence[tuple[RolePosition, str]]
) -> dict[RolePosition, str]:
    """Render a tag name for every role position a plant has.

    Args:
        scheme: How this plant spells its names.
        positions: Each role position with the engineering unit its signal carries, in a fixed
            order. Order decides nothing about the names, but it is what makes the result
            reproducible, so a caller must not pass a set or an unsorted mapping's items.

    Returns:
        The tag name for each position.

    Raises:
        ValueError: If two positions render to the same tag name. A plant with a duplicated tag
            would be refused later by `phos.synth.plant.PlantDescription` with a less useful
            message, and the fault is here: the family gave two instruments one name.
    """
    tags: dict[RolePosition, str] = {}
    seen: dict[str, RolePosition] = {}
    for position, unit in positions:
        role, train, stage = position
        name = scheme.tag(role, train, stage, unit)
        clash = seen.get(name)
        if clash is not None:
            raise ValueError(
                f"naming scheme renders {clash} and {position} both as {name!r}; two instruments "
                "cannot share a tag"
            )
        seen[name] = position
        tags[position] = name
    return tags


def roles_from_tags(tags: Mapping[RolePosition, str]) -> dict[str, SignalRole]:
    """Invert rendered tags into the role map a drawn plant carries as ground truth."""
    return {
        tag: SignalRole(role=role, train=train, stage=stage)
        for (role, train, stage), tag in tags.items()
    }


def stage_units(
    trains: int, stages: int, *, label: str, extra: Sequence[tuple[str, str]] = ()
) -> tuple[PhysicalUnit, ...]:
    """Return one physical unit per stage of every train, plus any the family adds.

    Args:
        trains: How many parallel trains.
        stages: How many stages in each.
        label: What one stage is called — ``"stage"``, ``"loop"``, ``"segment"``. Rendered as
            ``"Train 2, stage 3"``.
        extra: Further ``(unit_id, label)`` pairs, such as a common header or a shared utility.

    Returns:
        The units, trains outermost and stages innermost, with the extras last.
    """
    units = [
        PhysicalUnit(
            unit_id=stage_unit_id(train, stage),
            label=f"Train {train + 1}, {label} {stage + 1}",
        )
        for train in range(trains)
        for stage in range(stages)
    ]
    units.extend(PhysicalUnit(unit_id=unit_id, label=unit_label) for unit_id, unit_label in extra)
    return tuple(units)


def stage_unit_id(train: int, stage: int) -> str:
    """Return the physical unit identifier one stage's instruments sit on."""
    return f"train{train + 1}_stage{stage + 1}"


def modbus_network(
    *,
    poll_interval_seconds: float,
    subnet: str,
    per_plc: Sequence[tuple[Sequence[str], Sequence[str]]],
) -> ControlNetwork:
    """Return a Modbus/TCP control network with one PLC per train.

    The shape is the one every plant in this package uses and the one `phos.synth.traffic` knows
    how to put on the wire: a SCADA server that cyclically reads every block, an operator HMI that
    writes setpoints, a PLC per train holding the registers, and an engineering workstation that
    is on the network and emits nothing.

    **The quiet workstation is deliberate.** A write from it is from a device that issued no
    command in the baseline capture — the unknown-master shape ADR 0027 measures — which is a
    different thing from an unexpected write from the SCADA server, and the two are scored apart
    (ADR 0034). A family that declared no such device would make one of the two unmeasurable.

    Args:
        poll_interval_seconds: How often the poller reads every block.
        subnet: The first three octets of the plant's address range, e.g. ``"10.2"`` gives
            ``10.2.0.5`` for the SCADA server and ``10.2.1.11`` for the first PLC.
        per_plc: One entry per train: the signals that PLC exposes read-only, and the signals an
            operator may write. Register addresses are laid out sequentially across the whole
            plant, so no two blocks overlap however many trains there are.

    Returns:
        The network.

    Raises:
        ValueError: If no train was given, or a train exposes nothing. `ControlNetwork` needs at
            least one block, and a PLC holding no registers is a device with nothing to say.
    """
    if not per_plc:
        raise ValueError("a control network needs at least one PLC")
    nodes = [
        NetworkNode(node_id="scada", label="SCADA server", ip=f"{subnet}.0.5", role="scada"),
        NetworkNode(node_id="hmi", label="Operator HMI", ip=f"{subnet}.0.20", role="hmi"),
        NetworkNode(
            node_id="engineering",
            label="Engineering workstation",
            ip=f"{subnet}.0.40",
            role="engineering",
        ),
    ]
    blocks: list[RegisterBlock] = []
    address = 0
    for index, (readable, writable) in enumerate(per_plc):
        if not readable and not writable:
            raise ValueError(f"PLC {index + 1} exposes no registers")
        node_id = f"plc{index + 1}"
        nodes.append(
            NetworkNode(
                node_id=node_id,
                label=f"Train {index + 1} PLC",
                ip=f"{subnet}.1.{index + 11}",
                role="plc",
            )
        )
        if readable:
            blocks.append(
                RegisterBlock(node_id=node_id, start_address=address, signals=tuple(readable))
            )
            address += len(readable)
        if writable:
            blocks.append(
                RegisterBlock(
                    node_id=node_id,
                    start_address=address,
                    signals=tuple(writable),
                    writable=True,
                )
            )
            address += len(writable)
    return ControlNetwork(
        nodes=tuple(nodes),
        blocks=tuple(blocks),
        poller="scada",
        operator="hmi",
        poll_interval_seconds=poll_interval_seconds,
    )


def operator_authority(
    tags: Mapping[RolePosition, str], setpoint_roles: Sequence[str]
) -> WriteAuthority:
    """Return a policy granting the operator's HMI every setpoint and nothing else.

    Args:
        tags: The plant's rendered tags.
        setpoint_roles: Which roles are setpoints an operator moves.

    Returns:
        The policy. The engineering workstation appears in no grant, which is what makes a write
        from it unauthorised by declaration rather than by inference.
    """
    wanted = frozenset(setpoint_roles)
    granted = frozenset(tag for (role, _, _), tag in tags.items() if role in wanted)
    return WriteAuthority(grants={"hmi": granted})
