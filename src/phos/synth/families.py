"""Plant families: the structural templates a randomised plant is drawn from.

PART R2. `phos.synth.plants` holds three plants — water treatment, power generation, batch
chemistry — each hand-written, each fixed. A seed varies their sensor noise, their drift and their
benign-event schedule; it does not vary the plant. Six tanks stay six tanks, a controller's gain
stays the gain somebody typed, and the topology is the same partition every run. A model trained
on all three has seen three plants, and one that does well on them may have learned those three
rather than how a plant behaves.

A **family** is the structure held fixed and the parameters left free: what kind of process this
is, with the stage count, the parallel trains, the capacities, the gains, the time constants, the
instrument characteristics, the scan period, the tag-naming convention and the disturbance
schedule all drawn per seed. Two plants from one family are the same process at different sizes
and tunings, which is what two real plants of the same kind are.

**A family declares its bounds as data.** `ParameterBound` is a record, not a docstring, so the
table in ``docs/sim/README.md`` is rendered from the registry rather than written beside it and
left to rot — and `tests/synth/test_families.py` fails if the two disagree. A bound that is not
declared cannot be drawn: `PlantFamily.draw` goes through `bounded`, which refuses a parameter the
family never named.

**Sealed families are a loading switch and nothing else.** A sealed family lives in
`phos.synth.families_sealed`, is absent from the default registry and from every listing, and is
importable only when ``PHOS_SYNTH_ALLOW_SEALED=1`` is set in the environment. That is the whole
mechanism. No scoring lives here, no exam logic, and nothing in this module knows what a sealed
family is *for* — PART S6's referee owns that, and the separation is deliberate: a generator that
knew which of its plants were the exam could favour them.

**The standing caveat is not weakened by volume.** A family generates models of an industrial
process, not plants. Unlimited draws from it are unlimited models. See ``MODEL_NOT_REALITY_CAVEAT``
in `phos.synth`; nothing here may be described as real plant data.
"""

from __future__ import annotations

import importlib
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from phos.synth.plant_spec import PlantSpec
from phos.synth.randomise import SeedStreams, StreamDraw

__all__ = [
    "SEALED_ENV_VAR",
    "BoundScale",
    "FamilyError",
    "ParameterBound",
    "PlantFamily",
    "bounded",
    "bounds_table",
    "family_ids",
    "get_family",
    "list_families",
    "register_family",
    "sealed_allowed",
]

logger = logging.getLogger(__name__)

SEALED_ENV_VAR: Final = "PHOS_SYNTH_ALLOW_SEALED"
"""Set to ``1`` to make sealed families importable. Absent or anything else keeps them out."""


class FamilyError(ValueError):
    """Raised when a family is asked for something it cannot give."""


class BoundScale(str, Enum):
    """How a parameter's range is sampled, which is part of what the range *means*.

    Attributes:
        LINEAR: Evenly between the bounds. For a quantity whose plausible values span less than
            about a decade — a plan area, a gain, a setpoint.
        LOG: Evenly in the logarithm. For a quantity spanning orders of magnitude, where drawing
            evenly would put nine plants in ten at the top of the range.
        INTEGER: A whole number, both bounds included. For counts — stages, trains, tap positions
            — where a value between two of them means nothing.
        CHOICE: One of a fixed set of values, given in ``options``. For a design decision that is
            discrete rather than continuous: an island runs at 50 Hz or at 60 Hz, and 54 is not a
            conservative middle, it is a plant that does not exist.
    """

    LINEAR = "LINEAR"
    LOG = "LOG"
    INTEGER = "INTEGER"
    CHOICE = "CHOICE"


@dataclass(frozen=True)
class ParameterBound:
    """One thing a family varies, and the range it varies it over.

    Attributes:
        name: The parameter, as it appears in the drawn `PlantSpec.parameters` or as the name the
            structural draw was recorded under.
        low: Bottom of the range.
        high: Top of the range. Included for an integer bound, approached for the others.
        scale: How the range is sampled.
        unit: Engineering unit, or ``""`` for a dimensionless ratio or a count.
        why: What this parameter is and why the range is what it is, in a sentence a process
            engineer could disagree with. This is the part that makes the bound reviewable rather
            than merely declared, and it is rendered into the public table.
        options: For a ``CHOICE`` bound, the values it may take, in a fixed order. Empty for
            every other scale, where ``low`` and ``high`` are the range.

    Invariants:
        A ranged bound is non-empty and a log-scaled one is positive; a choice bound names at
        least two options and no range.
    """

    name: str
    low: float
    high: float
    scale: BoundScale
    unit: str = ""
    why: str = ""
    options: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a bound that does not describe what may be drawn.

        Raises:
            FamilyError: If a ranged bound is inverted or empty, a log range reaches zero, a
                choice bound has fewer than two options, or options are given for a scale that
                does not use them.
        """
        if self.scale is BoundScale.CHOICE:
            if len(self.options) < 2:
                raise FamilyError(
                    f"bound {self.name!r} is a choice but names {len(self.options)} option(s); a "
                    "parameter with one value is fixed, not drawn"
                )
            if len(set(self.options)) != len(self.options):
                raise FamilyError(f"bound {self.name!r} names the same option twice")
            return
        if self.options:
            raise FamilyError(
                f"bound {self.name!r} is {self.scale.value} but names options; only a CHOICE "
                "bound has them"
            )
        if not self.low < self.high:
            raise FamilyError(
                f"bound {self.name!r} is empty: low={self.low} is not below high={self.high}"
            )
        if self.scale is BoundScale.LOG and self.low <= 0.0:
            raise FamilyError(
                f"bound {self.name!r} is sampled in the log but reaches {self.low}; a quantity "
                "that can be zero does not span orders of magnitude"
            )

    @classmethod
    def among(
        cls, name: str, options: tuple[float, ...], unit: str = "", why: str = ""
    ) -> ParameterBound:
        """Return a choice bound, without having to pass a range it does not have."""
        return cls(
            name=name,
            low=min(options) if options else 0.0,
            high=max(options) if options else 0.0,
            scale=BoundScale.CHOICE,
            unit=unit,
            why=why,
            options=options,
        )


def bounded(draw: StreamDraw, bounds: Mapping[str, ParameterBound], name: str) -> float:
    """Draw one parameter from its declared bound.

    This is the only way a family's `draw` should take a number, because it is what makes the
    declared table and the drawn plant the same thing. A parameter drawn directly would not
    appear in ``docs/sim/README.md`` and nothing would notice.

    Args:
        draw: The stream to draw from.
        bounds: The family's bounds, by name.
        name: Which parameter.

    Returns:
        The drawn value. An integer-scaled bound still returns a float, because
        `PlantSpec.parameters` is a mapping of floats; the template rounds it.

    Raises:
        FamilyError: If the family never declared a bound for this parameter.
    """
    bound = bounds.get(name)
    if bound is None:
        raise FamilyError(
            f"{name!r} has no declared bound, so it cannot be drawn; add it to the family's "
            "bounds() or stop drawing it"
        )
    if bound.scale is BoundScale.CHOICE:
        picked = draw.choice(name, tuple(str(option) for option in bound.options))
        return float(picked)
    if bound.scale is BoundScale.INTEGER:
        return float(draw.integer(name, int(bound.low), int(bound.high)))
    if bound.scale is BoundScale.LOG:
        return draw.log_uniform(name, bound.low, bound.high)
    return draw.uniform(name, bound.low, bound.high)


class PlantFamily(ABC):
    """A kind of process, with the numbers left open.

    A family owes four things: what it is, which process template its drawn plants run on, what
    it varies and between what bounds, and how to turn a seed into a `PlantSpec`.

    Subclasses are registered with `register_family` at the foot of the module that implements
    them, beside the template they draw for.
    """

    @property
    @abstractmethod
    def family_id(self) -> str:
        """Stable identifier, used on the command line and in a drawn plant's manifest."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable name."""

    @property
    @abstractmethod
    def process(self) -> str:
        """The `phos.synth.templates` process every plant from this family runs on."""

    @property
    @abstractmethod
    def industry(self) -> str:
        """The sector this process belongs to."""

    @property
    @abstractmethod
    def summary(self) -> str:
        """What the process does, in a sentence or two, for someone who is not an engineer."""

    @property
    def sealed(self) -> bool:
        """Whether this family is held back from the default registry. Almost always ``False``."""
        return False

    @abstractmethod
    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return every parameter this family varies, and its range.

        Returns:
            The bounds, in a fixed order — the order they are rendered in, so the public table
            does not reshuffle itself between commits.
        """

    @abstractmethod
    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one plant from this family.

        Args:
            master_seed: Seeds every draw. With the code version this is the whole regeneration
                recipe.

        Returns:
            The drawn plant. Valid as a `PlantSpec` — the structure, the roles and the loops all
            hold together — but **not** yet checked for whether it could physically exist. That
            is PART R3's validity gate, which refuses a plant rather than clipping it.
        """

    def bounds_by_name(self) -> Mapping[str, ParameterBound]:
        """Return this family's bounds keyed by parameter name, for `bounded`."""
        return {bound.name: bound for bound in self.bounds()}

    def streams(self, master_seed: int) -> SeedStreams:
        """Return the named random streams a draw from this family takes its numbers from."""
        return SeedStreams(master_seed=master_seed)


_FAMILIES: dict[str, PlantFamily] = {}
_LOADED_OPEN = False
_LOADED_SEALED = False


def register_family(family: PlantFamily) -> None:
    """Add a family to the registry.

    Args:
        family: The family. Its ``family_id`` is the key.

    Raises:
        FamilyError: If the identifier is already taken by a different family. Re-registering the
            same object is allowed, because a module may be imported twice under two paths.
    """
    existing = _FAMILIES.get(family.family_id)
    if existing is not None and type(existing) is not type(family):
        raise FamilyError(
            f"family {family.family_id!r} is already registered to {type(existing).__name__}"
        )
    _FAMILIES[family.family_id] = family


def sealed_allowed() -> bool:
    """Return whether sealed families may be loaded in this process.

    Read from the environment every time rather than cached at import, so a test can turn it on
    and off without reloading the package — and so a long-running process cannot have been given
    the answer before the operator set the variable.
    """
    return os.environ.get(SEALED_ENV_VAR) == "1"


def _ensure_loaded() -> None:
    """Import the modules that register families, open ones always and sealed ones only if let.

    The sealed import is attempted on every call rather than once, because `sealed_allowed` can
    become true after the open families have already been loaded.
    """
    global _LOADED_OPEN, _LOADED_SEALED
    if not _LOADED_OPEN:
        _LOADED_OPEN = True
        importlib.import_module("phos.synth.plants")
    if sealed_allowed() and not _LOADED_SEALED:
        _LOADED_SEALED = True
        importlib.import_module("phos.synth.families_sealed")
        logger.debug("sealed families loaded because %s=1", SEALED_ENV_VAR)


def list_families(*, include_sealed: bool = False) -> tuple[PlantFamily, ...]:
    """Return the registered families, sorted by identifier.

    Args:
        include_sealed: Whether to include sealed families. Ignored unless
            ``PHOS_SYNTH_ALLOW_SEALED=1``, because a sealed family that was never imported cannot
            be listed however politely it is asked for.

    Returns:
        The families, in identifier order.
    """
    _ensure_loaded()
    wanted = [
        family
        for family in _FAMILIES.values()
        if not family.sealed or (include_sealed and sealed_allowed())
    ]
    return tuple(sorted(wanted, key=lambda family: family.family_id))


def family_ids(*, include_sealed: bool = False) -> tuple[str, ...]:
    """Return the registered family identifiers, sorted."""
    return tuple(family.family_id for family in list_families(include_sealed=include_sealed))


def get_family(family_id: str) -> PlantFamily:
    """Return one family by identifier.

    Args:
        family_id: Which family.

    Returns:
        The family.

    Raises:
        FamilyError: If no such family is available. A sealed family that exists but has not been
            unlocked is reported exactly as one that does not exist, and the message does not
            hint otherwise — a listing that said "there is one more, but you may not have it"
            would leak the thing sealing is for.
    """
    _ensure_loaded()
    family = _FAMILIES.get(family_id)
    if family is None or (family.sealed and not sealed_allowed()):
        available = family_ids()
        raise FamilyError(
            f"no family {family_id!r}; phos.synth draws {', '.join(available)}"
            if available
            else f"no family {family_id!r} and none are registered"
        )
    return family


def bounds_table(families: Sequence[PlantFamily]) -> str:
    """Render the declared bounds of some families as a Markdown table.

    This is what ``docs/sim/README.md`` carries, generated rather than written, so that a bound
    that changes in code changes in the document too — and a test compares the two.

    Args:
        families: The families to document, in the order they should appear.

    Returns:
        The table, newline-terminated.
    """
    lines: list[str] = []
    for family in families:
        lines.extend(
            [
                f"#### `{family.family_id}` — {family.label}",
                "",
                family.summary,
                "",
                "| Parameter | Range | Unit | What it is |",
                "|---|---|---|---|",
            ]
        )
        for bound in family.bounds():
            lines.append(
                f"| `{bound.name}` | {_render_range(bound)} | {bound.unit or '—'} | {bound.why} |"
            )
        lines.append("")
    return "\n".join(lines)


def _render_range(bound: ParameterBound) -> str:
    """Render a bound's range the way its scale means it."""
    if bound.scale is BoundScale.CHOICE:
        return " or ".join(_number(option) for option in bound.options)
    if bound.scale is BoundScale.INTEGER:
        return f"{int(bound.low)} to {int(bound.high)}"
    rendered = f"{_number(bound.low)} to {_number(bound.high)}"
    return f"{rendered} (log)" if bound.scale is BoundScale.LOG else rendered


def _number(value: float) -> str:
    """Render a bound as a human reads it, without a trailing ``.0`` on a whole number."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:g}"
