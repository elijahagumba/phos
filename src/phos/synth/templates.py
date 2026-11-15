"""Which physics a spec's ``process`` names, and how a spec becomes a running plant.

PART R1 split a plant into a document and a recipe: `phos.synth.plant_spec.PlantSpec` says what a
plant *is*, and a named process template holds the arithmetic that makes it run. This module is
the join — the registry that turns ``"water-treatment-v1"`` into the class that implements it, and
`build_from_spec`, which is the one entry point a generated plant is built through.

**Why a registry rather than an import.** PART R2 draws plants from families, and a family names
the template it draws for. Nothing on the drawing side should have to import a plant class, and
nothing on the physics side should have to know a family exists. A string in the middle keeps
them apart, and `PROCESS_TEMPLATES` is the only place that knows both.

**Versioned on purpose.** The names carry ``-v1``. A template whose arithmetic changes gets a new
name rather than a quiet edit, because a spec that was drawn, recorded and reproduced months later
has to find the physics it was drawn against — and ``tests/synth/golden/`` would otherwise be the
only thing that noticed, after the fact.
"""

import importlib
from collections.abc import Mapping
from typing import Protocol

from phos.synth.command import CommandSource
from phos.synth.plant import Plant, RunSpec
from phos.synth.plant_spec import PlantSpec, SpecError
from phos.synth.realism import RealismProfile

__all__ = [
    "ProcessTemplate",
    "build_from_spec",
    "process_names",
    "process_templates",
    "register_template",
]


class ProcessTemplate(Protocol):
    """How every process template is spelled, so the registry can name one type."""

    def __call__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = ...,
        realism: RealismProfile | None = ...,
        plant_spec: PlantSpec | None = ...,
    ) -> Plant:
        """Construct the plant this spec describes, for ``spec``."""


_TEMPLATES: dict[str, ProcessTemplate] = {}
_LOADED = False


def _ensure_loaded() -> None:
    """Import the modules that register templates, once.

    Each process template registers itself at the foot of the module that implements it, so that
    adding one is a single file rather than an edit here as well. Importing those modules from
    inside a function rather than at the top of this one is what keeps the dependency pointing
    one way: a plant module imports the registry, and the registry does not import plant modules
    until somebody actually asks it for one.
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    importlib.import_module("phos.synth.plants")


def process_templates() -> Mapping[str, ProcessTemplate]:
    """Return every physics a spec may name. Read-only; `register_template` is how it grows."""
    _ensure_loaded()
    return dict(_TEMPLATES)


def register_template(process: str, template: ProcessTemplate) -> None:
    """Add a process template to the registry.

    Templates register themselves at import, beside the physics they implement, so that adding
    one is a single module rather than an edit here and an edit there.

    Args:
        process: The versioned name a spec puts in its ``process`` field.
        template: The class or factory implementing it.

    Raises:
        SpecError: If the name is already taken by a different template. Re-registering the same
            object is allowed, because a module may be imported twice under two paths; silently
            replacing one template with another is not, because every spec already drawn against
            the old one would quietly start running on the new.
    """
    existing = _TEMPLATES.get(process)
    if existing is not None and existing is not template:
        raise SpecError(
            f"process template {process!r} is already registered to {existing!r}; a template "
            "whose physics changes takes a new version in its name"
        )
    _TEMPLATES[process] = template


def process_names() -> tuple[str, ...]:
    """Return every registered process name, sorted so listings and errors are stable."""
    _ensure_loaded()
    return tuple(sorted(_TEMPLATES))


def build_from_spec(
    plant_spec: PlantSpec,
    run: RunSpec,
    *,
    commands: CommandSource | None = None,
    realism: RealismProfile | None = None,
) -> Plant:
    """Build the running plant a spec describes.

    This is the path a generated plant takes, and it is the same path the three hand-written
    plants take when they are built from their own specs — deliberately, so that a drawn plant
    cannot be running through code the committed ones never exercise.

    Args:
        plant_spec: The plant to build.
        run: How long to run it for, how often to sample, and from what seed.
        commands: Who writes over the control network, or ``None``. See `phos.synth.plant.Plant`.
        realism: Ordinary trouble to apply, or ``None`` for a quiet profile.

    Returns:
        The constructed plant, ready to be stepped.

    Raises:
        SpecError: If no template implements the spec's ``process``. The message names the ones
            that exist, because a typo here would otherwise surface as a plant that silently is
            not there.
    """
    _ensure_loaded()
    template = _TEMPLATES.get(plant_spec.process)
    if template is None:
        raise SpecError(
            f"plant {plant_spec.plant_id!r} names process {plant_spec.process!r}, which no "
            f"template implements; phos.synth builds {', '.join(process_names())}"
        )
    return template(run, commands=commands, realism=realism, plant_spec=plant_spec)
