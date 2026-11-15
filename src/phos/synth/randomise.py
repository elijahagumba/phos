"""Seed to parameter set: drawing one plant from a family, reproducibly.

PART R2. A family (`phos.synth.families`) says what may vary and between what bounds; this module
does the drawing. Three things here are load-bearing and each is a decision rather than a detail.

**Streams are addressed by name, not by index.** `numpy.random.SeedSequence.spawn` is
deterministic by *child index*, which is exactly wrong for a generator still being written: adding
a stream for a new component shifts every stream after it, and every plant drawn before that day
becomes a different plant. So a stream is derived from the master seed and a stable hash of its
name — ``SeedSequence(entropy=master, spawn_key=(hash_of(name),))`` — and `blake2b` does the
hashing because Python's own `hash` is salted per process and would not reproduce tomorrow.
Adding `streams.for_("agitation")` leaves `streams.for_("sensors")` bit-identical, which is a
property `tests/synth/test_randomise.py` asserts rather than assumes.

**Every draw is recorded.** A `Draw` is a generator with a notebook: it answers `uniform`,
`log_uniform`, `integer` and `choice`, and it keeps what it drew under the name it was asked for.
`phos.synth.manifest` is where a corpus states how to regenerate itself, and a drawn plant's
parameter set belongs there beside its seed, so a reviewer can see what was drawn without
rerunning the draw — and so an implausible plant can be argued about from the record.

**Nothing here perturbs a signal.** Randomisation acts on the plant's *description*, before a
single step is integrated. A drawn value that breaks a physical relation is PART R3's problem and
is refused there with the relation named; it is never quietly clipped, because a clipped parameter
set is one the family said was impossible and the generator produced anyway.

**Tag names are drawn too, and that is the point.** `NamingScheme` renders a signal's role into a
tag — ``LT_201.PV`` under one scheme, ``tank2_level_m`` under another, ``AI_0203`` under a third —
so that nothing downstream can key off a name. What a tag *means* survives in
`phos.synth.plant_spec.SignalRole`, which is ground truth and travels in the output.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

import numpy
from numpy.random import Generator, SeedSequence

__all__ = [
    "DRAWN_DIGITS",
    "DrawError",
    "NamingScheme",
    "NumberStyle",
    "SeedStreams",
    "StreamDraw",
    "settled",
    "stream_key",
]

_HASH_BYTES: Final = 8
"""Width of the stable name hash. 64 bits is far more than enough to keep stream names apart."""


class DrawError(ValueError):
    """Raised when a draw is asked for something that is not a draw."""


def stream_key(name: str) -> int:
    """Return the stable integer a stream name hashes to.

    Stable across processes, machines and Python versions, which `hash` is not: the interpreter
    salts string hashing per process, so a generator built on it would produce a different plant
    every time it was run.

    Args:
        name: The stream's name.

    Returns:
        The key, as a 64-bit unsigned integer.
    """
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=_HASH_BYTES).digest()
    return int.from_bytes(digest, "big")


@dataclass(frozen=True)
class SeedStreams:
    """Named independent random streams, all derived from one master seed.

    Attributes:
        master_seed: The seed the whole plant is drawn from. With the code version this is the
            entire regeneration recipe.

    Invariants:
        Two `SeedStreams` with the same master seed give byte-identical streams for the same
        name, and a stream's numbers do not depend on which other streams were asked for, or in
        what order, or on how many exist.
    """

    master_seed: int

    def for_(self, name: str) -> Generator:
        """Return the generator for one named stream.

        Args:
            name: What this stream is for — ``"structure"``, ``"sizing"``, ``"tuning"``,
                ``"instruments"``, ``"naming"``, ``"disturbance"``. Any string; the name is the
                address.

        Returns:
            A fresh generator, at the start of that stream. Calling twice with one name gives two
            generators producing the same numbers, which is what makes a draw reproducible
            without having to thread one object through everything.
        """
        return numpy.random.default_rng(
            SeedSequence(entropy=self.master_seed, spawn_key=(stream_key(name),))
        )

    def draw(self, name: str) -> StreamDraw:
        """Return a recording draw on one named stream."""
        return StreamDraw(name=name, generator=self.for_(name))


DRAWN_DIGITS: Final = 12
"""Significant digits kept on every drawn float.

**A draw is not bit-reproducible across processor architectures, and rounding is what makes it so.**
`numpy`'s `uniform` computes `low + (high - low) * x`. On arm64 that multiply-add can be *fused*,
rounding once where x86-64 rounds twice, so the two give doubles differing in the last bit.
`log_uniform` is worse: it goes through `math.log` and `math.exp`, whose last bits are a property of
the platform's libm rather than of the standard.

That was not theory. The six standard corpora's manifests were byte-identical on macOS/arm64 and
differed on Linux/x86-64 in exactly one leaf of 404 — a drawn setpoint, `3.55187675975025` against
`3.5518767597502494` — which is one unit in the last place. The data files were identical on both,
because telemetry is written at fixed precision; only the documents that carry a raw drawn float
showed it (ADR 0441).

Twelve significant digits sits about four orders of magnitude clear of where that difference lives
and far finer than any physical quantity this package models, and being *significant* digits rather
than decimal places it keeps the same relative precision for a gain of 1e-4 and a capacity of 1e6.

It is a mitigation and not a proof: a 1-ULP difference landing exactly on the twelfth-digit rounding
boundary would still diverge. Nothing in a rounding scheme can rule that out. What catches it is
that development happens on arm64 and CI runs the golden corpus check on x86-64, which is precisely
how this was found."""


def settled(value: float) -> float:
    """Return a drawn float rounded to `DRAWN_DIGITS` significant digits.

    Applied at the moment of the draw rather than when a value is written, so that every
    consequence of a draw — the plant's description, its manifest, the physics it drives — follows
    from the same number on every machine.

    Args:
        value: The raw drawn value.

    Returns:
        The value rounded to `DRAWN_DIGITS` significant digits.
    """
    return float(f"{value:.{DRAWN_DIGITS}g}")


@dataclass
class StreamDraw:
    """One named stream, and a record of everything taken from it.

    Mutable by design — a draw *is* its history — so one belongs to one plant and is never
    shared. The record is what travels into the manifest.

    Attributes:
        name: The stream this draws from.
        generator: The stream itself.
    """

    name: str
    generator: Generator
    _taken: dict[str, float] = field(default_factory=dict, repr=False)

    @property
    def taken(self) -> Mapping[str, float]:
        """Everything drawn so far, by the name it was asked for, in the order it was drawn."""
        return dict(self._taken)

    def uniform(self, what: str, low: float, high: float) -> float:
        """Draw a value evenly between two bounds.

        Args:
            what: What is being drawn, e.g. ``"clearwell_area_m2"``. Recorded under this name.
            low: Lower bound, included.
            high: Upper bound.

        Returns:
            The drawn value.

        Raises:
            DrawError: If the bounds are inverted or equal. A family declaring an empty range for
                a parameter has said something about the family, and quietly returning the one
                value in it would hide that.
        """
        self._check_range(what, low, high)
        return self._record(what, settled(float(self.generator.uniform(low, high))))

    def log_uniform(self, what: str, low: float, high: float) -> float:
        """Draw a value evenly in the logarithm, for a quantity that spans orders of magnitude.

        A time constant that may be thirty seconds or an hour is not uniform between them: drawn
        evenly, nine plants in ten would be slow. Drawn evenly in the log, a decade is a decade
        wherever it sits.

        Args:
            what: What is being drawn. Recorded under this name.
            low: Lower bound. Must be positive, because a logarithm says so.
            high: Upper bound.

        Returns:
            The drawn value.

        Raises:
            DrawError: If the bounds are inverted, equal, or not positive.
        """
        self._check_range(what, low, high)
        if low <= 0.0:
            raise DrawError(
                f"{what!r} is drawn in the log but its lower bound is {low}; a quantity that can "
                "be zero does not span orders of magnitude"
            )
        drawn = math.exp(float(self.generator.uniform(math.log(low), math.log(high))))
        return self._record(what, settled(drawn))

    def integer(self, what: str, low: int, high: int) -> int:
        """Draw a whole number between two bounds, both included.

        For the structural draws — how many stages, how many parallel trains — where a value
        between two counts means nothing.

        Args:
            what: What is being drawn. Recorded under this name.
            low: Lowest value allowed.
            high: Highest value allowed, included.

        Returns:
            The drawn count.

        Raises:
            DrawError: If the bounds are inverted.
        """
        if low > high:
            raise DrawError(f"{what!r} has an inverted range: {low} exceeds {high}")
        drawn = int(self.generator.integers(low, high + 1))
        self._record(what, float(drawn))
        return drawn

    def choice(self, what: str, options: Sequence[str]) -> str:
        """Draw one of a fixed set of options — a naming style, a layout.

        Args:
            what: What is being drawn. Recorded as the chosen option's index.
            options: What may be chosen, in a fixed order. Order matters: it is what makes the
                choice reproducible, so a caller must not pass a set or an unsorted dict's keys.

        Returns:
            The chosen option.

        Raises:
            DrawError: If there is nothing to choose from.
        """
        if not options:
            raise DrawError(f"{what!r} has no options to choose from")
        index = int(self.generator.integers(0, len(options)))
        self._record(what, float(index))
        return options[index]

    def _check_range(self, what: str, low: float, high: float) -> None:
        """Refuse a range that is not a range.

        Raises:
            DrawError: If ``low`` is not strictly below ``high``.
        """
        if not low < high:
            raise DrawError(
                f"{what!r} has an empty range: low={low} is not below high={high}. A family that "
                "fixes a parameter should not declare it as drawn."
            )

    def _record(self, what: str, value: float) -> float:
        """Keep a drawn value under the name it was asked for.

        Raises:
            DrawError: If that name has already been drawn on this stream. Drawing the same
                parameter twice means two values claim one name in the manifest, and the record
                would say whichever came last.
        """
        if what in self._taken:
            raise DrawError(
                f"{what!r} was already drawn on stream {self.name!r}; the record would carry "
                "only one of the two values"
            )
        self._taken[what] = value
        return value


class NumberStyle(str, Enum):
    """How a naming scheme numbers the instruments it names.

    Attributes:
        PLAIN: ``1``, ``2``, ``3`` — counting, with no padding.
        PADDED: ``01``, ``02`` — two digits, as a small site numbers its loops.
        LOOP: ``101``, ``201`` — the stage in the hundreds and the item in the units, which is how
            a great many real plants number a loop.
    """

    PLAIN = "PLAIN"
    PADDED = "PADDED"
    LOOP = "LOOP"


@dataclass(frozen=True)
class NamingScheme:
    """How one drawn plant spells its tag names.

    Real plants do not agree on this, and that disagreement is the point: a detector that learned
    anything from a tag *name* has learned the convention of the site it was trained on, which is
    the one thing guaranteed not to transfer. A family draws a scheme per plant so no name is ever
    the same twice, and `phos.synth.plant_spec.SignalRole` carries what each one means.

    Attributes:
        prefix: Leading text, e.g. ``"WTW"`` or ``""``.
        separator: What joins the parts — ``"_"``, ``"-"`` or ``"."``.
        number_style: How the stage and train numbers are rendered.
        upper: Whether the tag is upper-cased.
        suffix: Trailing text, e.g. ``".PV"`` on a site whose historian tags carry the attribute.
        abbreviate: Whether a role is shortened to its instrument letters — ``level`` to ``LT``,
            ``flow`` to ``FT`` — as an ISA-style tag does, rather than spelled out.
    """

    prefix: str = ""
    separator: str = "_"
    number_style: NumberStyle = NumberStyle.PLAIN
    upper: bool = False
    suffix: str = ""
    abbreviate: bool = False

    def tag(self, role: str, train: int, stage: int, unit: str) -> str:
        """Render one signal's tag name.

        Args:
            role: What the signal is, from the family's vocabulary.
            train: Which parallel train, counting from zero.
            stage: Which stage within it, counting from zero.
            unit: Engineering unit, appended when the scheme spells roles out rather than
                abbreviating them, because ``tank2_level_m`` says more than ``tank2_level``.

        Returns:
            The tag name.
        """
        body = _ABBREVIATIONS.get(role, role[:2].upper()) if self.abbreviate else role
        number = self._number(train, stage)
        parts = [part for part in (self.prefix, body, number) if part]
        if not self.abbreviate and unit:
            parts.append(_unit_token(unit))
        name = self.separator.join(parts) + self.suffix
        return name.upper() if self.upper else name

    def _number(self, train: int, stage: int) -> str:
        """Render the position part of a tag."""
        if self.number_style is NumberStyle.LOOP:
            return f"{(stage + 1) * 100 + train + 1}"
        ordinal = train * 10 + stage + 1
        return f"{ordinal:02d}" if self.number_style is NumberStyle.PADDED else f"{ordinal}"


_ABBREVIATIONS: Final[Mapping[str, str]] = {
    "level": "LT",
    "flow": "FT",
    "inflow": "FT",
    "outflow": "FT",
    "pressure": "PT",
    "temperature": "TT",
    "temperature_setpoint": "TC",
    "level_setpoint": "LC",
    "pressure_setpoint": "PC",
    "flow_setpoint": "FC",
    "pump_speed": "SC",
    "valve_position": "ZT",
    "power": "JT",
    "quality": "AT",
    "duty": "YC",
    "fuel": "FV",
    "frequency": "SQ",
    "output": "JT",
    "excitation": "EX",
    "bus_voltage": "ET",
    "dispatch_setpoint": "JC",
    "voltage_setpoint": "EC",
    "feeder_power": "WT",
    "feeder_current": "IT",
    "power_factor": "PF",
    "ambient": "TA",
    "conversion": "QT",
    "phase": "SI",
    "charge": "WI",
    "agitator_speed": "SC",
    "agitator_power": "JI",
    "jacket_temperature": "TJ",
    "segment_pressure": "PT",
    "compressor_speed": "SZ",
    "suction_pressure": "PI",
}
"""ISA-style instrument letters, for the schemes that abbreviate. A role with no entry takes its
first two letters, which is wrong in the way a real site's one-off tag is wrong rather than in a
way that loses the mapping — `SignalRole` is where the meaning actually lives."""


def _unit_token(unit: str) -> str:
    """Return an engineering unit as it appears inside a tag name — ``m3/h`` becomes ``m3ph``."""
    return unit.replace("/", "p").replace("%", "pct").replace("°", "").replace(" ", "")
