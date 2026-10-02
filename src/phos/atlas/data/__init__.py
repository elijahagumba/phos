"""Declared physical-role loaders for cross-plant Atlas measurement (ADR 0063).

This package is the canonical home for SWaT / BATADAL / HAI intake used by the
zero-shot transfer protocol. The constitution's layout is ``src/phos/atlas/`` —
there is no ``src/atlas/data/`` tree. SWaT remains form-gated: loaders refuse
when the files are absent and never fetch them.
"""

from phos.atlas.data.loaders import (
    SWAT_FORM_GATED,
    CorpusMissingError,
    load_batadal,
    load_hai,
    load_source_train,
    load_swat,
)
from phos.atlas.data.mapping import (
    BATADAL_PHYSICAL_ROLES,
    HAI_PHYSICAL_ROLES,
    PHYSICAL_ROLES,
    SHARED_ENTITY_ID,
    SWAT_PHYSICAL_ROLES,
    PhysicalRole,
    concatenate_role_datasets,
    project_to_physical_roles,
)
from phos.atlas.data.transfer import (
    PHYSICAL_ROLES_DETECTOR_NAME,
    TRANSFER_CAVEAT,
    evaluate_available_transfer,
    run_zero_shot,
    write_zero_shot_log,
)

__all__ = [
    "BATADAL_PHYSICAL_ROLES",
    "HAI_PHYSICAL_ROLES",
    "PHYSICAL_ROLES",
    "PHYSICAL_ROLES_DETECTOR_NAME",
    "SHARED_ENTITY_ID",
    "SWAT_FORM_GATED",
    "SWAT_PHYSICAL_ROLES",
    "TRANSFER_CAVEAT",
    "CorpusMissingError",
    "PhysicalRole",
    "concatenate_role_datasets",
    "evaluate_available_transfer",
    "load_batadal",
    "load_hai",
    "load_source_train",
    "load_swat",
    "project_to_physical_roles",
    "run_zero_shot",
    "write_zero_shot_log",
]
