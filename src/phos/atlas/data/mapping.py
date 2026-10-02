"""Declared plant-tag to physical-role maps (ADR 0010 / ADR 0063).

Membership is documentation, not co-movement. Unmapped tags are dropped so a
SWaT tank level or an HAI turbine RPM cannot leak into the shared three-role
space. Averaging tags that share a role is a declared reduction, not a learned
alignment.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from phos.eval.datasets import Dataset
from phos.ontology import Domain, Observation

SHARED_ENTITY_ID = "ent_physicalroles"
"""One entity so source and target occupy the same joint signal space."""

MAPPING_NOTE = (
    "projected to declared physical roles {flow, pressure, pump_state}; "
    "unmapped plant tags dropped; TRANSFER_IS_PHYSICAL_ROLES_NOT_IDENTICAL_PLANTS"
)


class PhysicalRole(StrEnum):
    """The only features the cross-plant protocol is allowed to share."""

    FLOW = "flow"
    PRESSURE = "pressure"
    PUMP_STATE = "pump_state"


PHYSICAL_ROLES: tuple[PhysicalRole, ...] = (
    PhysicalRole.FLOW,
    PhysicalRole.PRESSURE,
    PhysicalRole.PUMP_STATE,
)

RoleMap = Mapping[PhysicalRole, tuple[str, ...]]

# BATADAL / C-Town (Taormina et al. 2018). F_* are flows, P_J* junction
# pressures, S_PU* pump on/off. Tank levels L_T* stay plant-private.
BATADAL_PHYSICAL_ROLES: dict[PhysicalRole, tuple[str, ...]] = {
    PhysicalRole.FLOW: (
        "F_PU1",
        "F_PU2",
        "F_PU3",
        "F_PU4",
        "F_PU5",
        "F_PU6",
        "F_PU7",
        "F_PU8",
        "F_PU9",
        "F_PU10",
        "F_PU11",
        "F_V2",
    ),
    PhysicalRole.PRESSURE: (
        "P_J280",
        "P_J269",
        "P_J300",
        "P_J256",
        "P_J289",
        "P_J415",
        "P_J302",
        "P_J306",
        "P_J307",
        "P_J317",
        "P_J14",
        "P_J422",
    ),
    PhysicalRole.PUMP_STATE: (
        "S_PU1",
        "S_PU2",
        "S_PU3",
        "S_PU4",
        "S_PU5",
        "S_PU6",
        "S_PU7",
        "S_PU8",
        "S_PU9",
        "S_PU10",
        "S_PU11",
    ),
}

# HAI 21.03 technical details (process-level instruments). Flow transmitters
# and FIT, PIT / steam-turbine PT, pump demand. Setpoints (*Z), boiler
# internals, P2 turbine RPM, and tank levels stay plant-private.
HAI_PHYSICAL_ROLES: dict[PhysicalRole, tuple[str, ...]] = {
    PhysicalRole.FLOW: ("P1_FT01", "P1_FT02", "P1_FT03", "P3_FIT01"),
    PhysicalRole.PRESSURE: ("P1_PIT01", "P1_PIT02", "P3_PIT01", "P4_ST_PT01"),
    PhysicalRole.PUMP_STATE: ("P1_PP01AD", "P1_PP01BD", "P1_PP02D", "P3_LCP01D"),
}

# SWaT published sensor list (Goh et al. 2016). FIT* flow, PIT*/DPIT* pressure,
# P1xx-P6xx pumps. LIT* levels, MV* valves, AIT* analysers stay plant-private.
SWAT_PHYSICAL_ROLES: dict[PhysicalRole, tuple[str, ...]] = {
    PhysicalRole.FLOW: (
        "FIT101",
        "FIT201",
        "FIT301",
        "FIT401",
        "FIT501",
        "FIT502",
        "FIT503",
        "FIT504",
        "FIT601",
    ),
    PhysicalRole.PRESSURE: ("PIT501", "PIT502", "PIT503", "DPIT301"),
    PhysicalRole.PUMP_STATE: (
        "P101",
        "P102",
        "P201",
        "P202",
        "P203",
        "P204",
        "P205",
        "P206",
        "P301",
        "P302",
        "P401",
        "P402",
        "P403",
        "P404",
        "P501",
        "P502",
        "P601",
        "P602",
        "P603",
    ),
}

PLANT_ROLE_MAPS: dict[str, dict[PhysicalRole, tuple[str, ...]]] = {
    "batadal": BATADAL_PHYSICAL_ROLES,
    "hai": HAI_PHYSICAL_ROLES,
    "swat": SWAT_PHYSICAL_ROLES,
}


def mapped_tags(role_map: RoleMap) -> tuple[str, ...]:
    """Return every native tag the map is willing to read, in role then name order."""
    tags: list[str] = []
    for role in PHYSICAL_ROLES:
        tags.extend(role_map[role])
    return tuple(tags)


def project_to_physical_roles(dataset: Dataset, role_map: RoleMap) -> Dataset:
    """Collapse native tags onto ``{flow, pressure, pump_state}`` and drop the rest.

    Each timestamp keeps a role only when at least one mapped tag is present.
    A timestamp missing any of the three roles is dropped: a joint model must
    not invent a pump state from a flow reading. The shared entity id is
    applied so a model fitted on BATADAL can score HAI.

    Args:
        dataset: Observations still named with plant-specific tags.
        role_map: Declared native-tag membership for this plant.

    Returns:
        A dataset whose features are exactly the three physical roles.

    Raises:
        ValueError: If ``role_map`` is missing a required role or a native tag
            is assigned to two roles.
    """
    feature_to_role = _invert_role_map(role_map)
    buckets: dict[datetime, dict[PhysicalRole, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for observation in dataset.observations:
        role = feature_to_role.get(observation.feature)
        if role is None:
            continue
        buckets[observation.timestamp][role].append(observation.value)

    projected: list[Observation] = []
    for index, timestamp in enumerate(sorted(buckets)):
        present = buckets[timestamp]
        if any(role not in present for role in PHYSICAL_ROLES):
            continue
        for role in PHYSICAL_ROLES:
            values = present[role]
            projected.append(
                Observation(
                    id=f"obs_pr{index:07d}{role.value[:1]}",
                    entity_ids=[SHARED_ENTITY_ID],
                    feature=role.value,
                    value=sum(values) / len(values),
                    timestamp=timestamp,
                    domain=Domain.ATLAS,
                    context={
                        "projection": "declared-physical-roles",
                        "n_tags": str(len(values)),
                    },
                )
            )

    note = dataset.source_note
    source_note = f"{note}; {MAPPING_NOTE}" if note else MAPPING_NOTE
    return Dataset(
        name=f"{dataset.name}-physical-roles",
        domain=Domain.ATLAS,
        observations=projected,
        attack_intervals=list(dataset.attack_intervals),
        source_note=source_note,
    )


def _invert_role_map(role_map: RoleMap) -> dict[str, PhysicalRole]:
    """Return native-tag to role, refusing duplicate or incomplete maps."""
    missing = [role for role in PHYSICAL_ROLES if role not in role_map or not role_map[role]]
    if missing:
        names = ", ".join(role.value for role in missing)
        raise ValueError(f"role map is missing tags for: {names}")
    inverted: dict[str, PhysicalRole] = {}
    for role, tags in role_map.items():
        if role not in PHYSICAL_ROLES:
            raise ValueError(f"undeclared physical role {role!r}")
        for tag in tags:
            existing = inverted.get(tag)
            if existing is not None:
                raise ValueError(f"tag {tag!r} is assigned to both {existing} and {role}")
            inverted[tag] = role
    return inverted


def require_tags_present(columns: Sequence[str], role_map: RoleMap, plant: str) -> None:
    """Raise if a declared tag is absent from the prepared file."""
    present = set(columns)
    missing = [tag for tag in mapped_tags(role_map) if tag not in present]
    if missing:
        raise ValueError(
            f"{plant} prepared file is missing declared role tags: {', '.join(missing)}"
        )


def concatenate_role_datasets(parts: list[Dataset], name: str) -> Dataset:
    """Stack already-projected plants as sequential moments of one shared entity.

    Later plants are time-shifted so two sites cannot occupy the same timestamp.
    That pools role-space snapshots. It does not claim they are one process.
    """
    if not parts:
        raise ValueError("concatenate_role_datasets requires at least one dataset")
    combined: list[Observation] = []
    intervals = []
    offset = timedelta(0)
    notes: list[str] = []
    for part in parts:
        if not part.observations:
            continue
        origin = part.observations[0].timestamp
        shifted: list[Observation] = []
        for observation in part.observations:
            new_stamp = (
                observation.timestamp
                if offset == timedelta(0)
                else (observation.timestamp - origin + offset)
            )
            shifted.append(
                observation.model_copy(
                    update={"timestamp": new_stamp, "entity_ids": [SHARED_ENTITY_ID]}
                )
            )
        span = shifted[-1].timestamp - shifted[0].timestamp
        if offset == timedelta(0):
            intervals.extend(part.attack_intervals)
        else:
            for interval in part.attack_intervals:
                intervals.append(
                    interval.model_copy(
                        update={
                            "start": interval.start - origin + offset,
                            "end": interval.end - origin + offset,
                        }
                    )
                )
        combined.extend(shifted)
        offset = span + timedelta(days=1)
        notes.append(part.name)
    combined.sort(key=lambda item: (item.timestamp, item.feature))
    note = "; ".join(notes)
    return Dataset(
        name=name,
        domain=Domain.ATLAS,
        observations=combined,
        attack_intervals=intervals,
        source_note=f"concatenated physical-role plants: {note}; {MAPPING_NOTE}",
    )
