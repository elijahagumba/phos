"""A synthetic plant's declared roles, loops and couplings, read from its own definition (ADR 0123).

The plant map is checked against the couplings (§8: how many declared links it recovers), and
the roles feed its reconstruction rules. All come straight from the `PlantDescription`: a role is
the signal's declared `SignalKind`, and a link is one driver of one declared `Coupling`. Nothing
is inferred. The map reads one kind of coupling as input, and only as ADR 0126's loops: a
`CONTROL` coupling's driven actuator is the output of a loop on each sensor that drives it
(ADR 0127). Every other coupling is only ever a check.

It lives here rather than in `phos.synth` because the generator may not import the detector
(`tests/synth/test_anti_bias.py`), and a role map is Atlas's type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from phos.atlas.signal_roles import ControlLoop, RoleDeclaration, SignalRole, SignalRoles
from phos.synth.plant import CouplingKind, PlantDescription, SignalKind
from phos.synth.plants.batch import BATCH_DESCRIPTION
from phos.synth.plants.power import POWER_DESCRIPTION
from phos.synth.plants.water import WATER_DESCRIPTION

__all__ = ["DeclaredLink", "declared_links", "declared_loops", "description_for", "plant_roles"]

_DESCRIPTIONS: Final = {
    d.plant_id: d for d in (WATER_DESCRIPTION, POWER_DESCRIPTION, BATCH_DESCRIPTION)
}

_ROLE_OF_KIND: Final = {
    SignalKind.SENSOR: SignalRole.SENSOR,
    SignalKind.ACTUATOR: SignalRole.ACTUATOR,
    SignalKind.SETPOINT: SignalRole.SETPOINT,
}


@dataclass(frozen=True)
class DeclaredLink:
    """One declared dependency: ``driven`` depends on ``driver`` in the way ``kind`` names."""

    driver: str
    driven: str
    kind: CouplingKind


def description_for(plant_id: str) -> PlantDescription:
    """Return a synthetic plant's declaration by its id.

    Raises:
        KeyError: If no synthetic plant has that id.
    """
    return _DESCRIPTIONS[plant_id]


def declared_loops(description: PlantDescription) -> tuple[ControlLoop, ...]:
    """One loop per sensor driving a declared `CONTROL` coupling, its actuator the output.

    A controller driven only by setpoints or phases holds no reading and declares no loop.
    """
    kind_of = {spec.key: spec.kind for spec in description.signals}
    loops: list[ControlLoop] = []
    for coupling in description.couplings:
        if coupling.kind is not CouplingKind.CONTROL:
            continue
        setpoints = [d for d in coupling.drivers if kind_of[d] is SignalKind.SETPOINT]
        for reading in (d for d in coupling.drivers if kind_of[d] is SignalKind.SENSOR):
            loops.append(
                ControlLoop(
                    name=f"{coupling.driven} on {reading}",
                    cited=f"{description.plant_id} PlantDescription, CONTROL coupling",
                    statement=coupling.relation,
                    reading=reading,
                    outputs=(coupling.driven,),
                    setpoint=setpoints[0] if setpoints else None,
                )
            )
    return tuple(loops)


def plant_roles(description: PlantDescription) -> SignalRoles:
    """Return every signal's role, which is its declared `SignalKind`, and its declared loops."""
    where = f"{description.plant_id} PlantDescription"
    return SignalRoles(
        [
            RoleDeclaration(
                signal=spec.key,
                role=_ROLE_OF_KIND[spec.kind],
                cited=f"{where}, signal {spec.key}",
                quote=f"{spec.label} (kind {spec.kind.value})",
            )
            for spec in description.signals
        ],
        description.signal_keys(),
        source=f"declared SignalKind in the {where}",
        loops=declared_loops(description),
    )


def declared_links(description: PlantDescription) -> tuple[DeclaredLink, ...]:
    """Return one link per declared driver of each coupling, in declaration order."""
    return tuple(
        DeclaredLink(driver=driver, driven=coupling.driven, kind=coupling.kind)
        for coupling in description.couplings
        for driver in coupling.drivers
    )
