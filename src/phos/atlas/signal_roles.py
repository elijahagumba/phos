"""What each signal is, sensor, actuator or setpoint, declared from documentation (ADR 0123 §3).

The plant map reconstructs a falsified reading from the signals that drive it, and two of its
rules turn on a signal's role: a setpoint never reconstructs a sensor, because a setpoint says
where a controller wants a reading, which is exactly the assumption a falsified reading breaks.
So a role is a fact about the plant, and like topology (ADR 0010) it is **declared, never
inferred**: not from the data, and not from a tag's name. ``P1_FCV01D`` suggests a valve command,
and a suggestion is not a declaration.

A declaration names its role and the sentence it was read from, or names no role and says why.
A role file may also declare its **control loops** (ADR 0126): which actuators hold which reading,
from the documentation's own loop statements. The map then bars only those controllers, and what
they drive, from vouching for the reading they act on.
A signal with no role gets no reconstruction. The set is total over the corpus, as a topology is:
a signal declared twice, declared but absent, or present but undeclared is refused at
construction, because a role map that is quietly partial reverts the unmapped signals to
guesswork.

This module holds no detection logic and produces no evaluation number.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Collection, Iterable, Mapping
from enum import Enum
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

__all__ = [
    "SCHEMA_VERSION",
    "ControlLoop",
    "RoleDeclaration",
    "RoleError",
    "SignalRole",
    "SignalRoles",
    "load_roles",
]

logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = 1
"""Role-file format this module understands. Any other version is refused, not read hopefully."""

_SOURCE_FIELDS: Final = ("document", "repository", "pin", "sha256")
"""Every role file's ``[source]`` must say which document, where from, at which pin, which bytes."""

_NO_ROLE: Final = "none"


class RoleError(ValueError):
    """A role declaration that cannot be trusted as a statement about the corpus."""


class SignalRole(str, Enum):
    """What a signal is, in the three kinds ADR 0123 reasons about.

    Attributes:
        SENSOR: A measurement of the process, including a value converted from one.
        ACTUATOR: A final control element's command or its reported position, or a controller's
            output to one.
        SETPOINT: A target or demand a controller or simulation is asked to follow.
    """

    SENSOR = "sensor"
    ACTUATOR = "actuator"
    SETPOINT = "setpoint"


class RoleDeclaration(BaseModel):
    """One signal's role, and where it was read.

    Attributes:
        signal: The corpus column.
        role: The declared role, or ``None`` when the documentation supports none.
        cited: Where the statement is: section, table, row and printed page.
        quote: The documentation's own words for the point. Required with a role.
        manual_name: The name the documentation uses, when it is not the column's.
        loop: A control-loop statement that also gives the point's role, when there is one.
        reason: Why there is no role. Required without one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: str = Field(min_length=1)
    role: SignalRole | None
    cited: str
    quote: str | None = None
    manual_name: str | None = None
    loop: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_substance(self) -> Self:
        if not self.cited.strip():
            raise ValueError(f"{self.signal}: cited must say where the statement is")
        if self.role is not None and not (self.quote and self.quote.strip()):
            raise ValueError(f"{self.signal}: a role needs the documentation's quote")
        if self.role is None and not (self.reason and self.reason.strip()):
            raise ValueError(f"{self.signal}: no role needs a reason")
        return self


class ControlLoop(BaseModel):
    """One control loop as the documentation states it (ADR 0126).

    Attributes:
        name: The documentation's name for the loop.
        cited: Where the statement is.
        statement: What the documentation says the loop does.
        reading: The sensor the loop holds, or ``None`` when the statement names none.
        outputs: The actuators the loop moves; empty when the statement names none.
        setpoint: The setpoint it holds the reading at, when the statement names one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    cited: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    reading: str | None = None
    outputs: tuple[str, ...] = ()
    setpoint: str | None = None

    @model_validator(mode="after")
    def _check_substance(self) -> Self:
        if self.reading is None and not self.outputs:
            raise ValueError(f"loop {self.name}: names neither a reading nor an output")
        return self


class SignalRoles:
    """A corpus's every signal with its declared role or a stated absence of one.

    Construction validates and then freezes, as `phos.atlas.topology.SubsystemMap` does.
    """

    def __init__(
        self,
        declarations: Iterable[RoleDeclaration],
        signal_keys: Collection[str],
        source: str,
        loops: Iterable[ControlLoop] = (),
    ) -> None:
        """Validate declarations against the corpus they describe.

        Args:
            declarations: One per signal, in the order to report them.
            signal_keys: Every signal the corpus contains.
            source: The documentation every declaration was read from.
            loops: The control loops the same documentation states, if it states any.

        Raises:
            RoleError: If a signal is declared twice, declared but absent from the corpus, or in
                the corpus but undeclared, if the source is blank, or if a loop names an unknown
                signal, a reading that is not a sensor, an output that is not an actuator, or a
                setpoint that is not a setpoint.
        """
        declared = tuple(declarations)
        corpus = tuple(signal_keys)
        if not source.strip():
            raise RoleError("a role map must name its source")
        by_signal: dict[str, RoleDeclaration] = {}
        for declaration in declared:
            if declaration.signal in by_signal:
                raise RoleError(f"{declaration.signal!r} is declared twice")
            by_signal[declaration.signal] = declaration
        phantom = sorted(set(by_signal) - set(corpus))
        if phantom:
            raise RoleError(f"declared but not in the corpus: {', '.join(phantom)}")
        missing = [signal for signal in corpus if signal not in by_signal]
        if missing:
            raise RoleError(f"in the corpus with no declaration: {', '.join(missing)}")
        self._declarations = declared
        self._by_signal = by_signal
        self.source = source
        self._loops = tuple(loops)
        for loop in self._loops:
            self._check_loop(loop)
        logger.debug(
            "%d signal role(s) declared, %d without a role", len(declared), len(self.without_role())
        )

    def _check_loop(self, loop: ControlLoop) -> None:
        expected = [(loop.reading, SignalRole.SENSOR, "reading")]
        expected += [(output, SignalRole.ACTUATOR, "output") for output in loop.outputs]
        expected += [(loop.setpoint, SignalRole.SETPOINT, "setpoint")]
        for signal, role, part in expected:
            if signal is None:
                continue
            if signal not in self._by_signal:
                raise RoleError(f"loop {loop.name}: {part} {signal!r} is not in the corpus")
            if self._by_signal[signal].role is not role:
                raise RoleError(
                    f"loop {loop.name}: {part} {signal!r} is not declared a {role.value}"
                )

    @property
    def loops(self) -> tuple[ControlLoop, ...]:
        """Every declared control loop, in file order."""
        return self._loops

    @property
    def declarations(self) -> tuple[RoleDeclaration, ...]:
        """Every declaration, in file order."""
        return self._declarations

    @property
    def signals(self) -> tuple[str, ...]:
        """Every declared signal, in file order."""
        return tuple(declaration.signal for declaration in self._declarations)

    def role_of(self, signal: str) -> SignalRole | None:
        """Return a signal's declared role, or ``None`` if it has none.

        Raises:
            KeyError: If the signal is not in this corpus.
        """
        return self._by_signal[signal].role

    def with_role(self, role: SignalRole) -> tuple[str, ...]:
        """Return the signals declared with one role, in file order."""
        return tuple(d.signal for d in self._declarations if d.role is role)

    def without_role(self) -> tuple[str, ...]:
        """Return the signals the documentation gives no role, in file order."""
        return tuple(d.signal for d in self._declarations if d.role is None)


def load_roles(path: Path, signal_keys: Collection[str]) -> SignalRoles:
    """Read a role file and validate it against the corpus's signals.

    Args:
        path: A role TOML file (``data/<corpus>/roles.toml``).
        signal_keys: Every signal the corpus contains.

    Raises:
        RoleError: If the file is another schema version, its source lacks a required field, a
            point is malformed or names an unknown role, the set is not total over the corpus,
            or a declared loop is malformed or names a signal in the wrong role.
    """
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise RoleError(
            f"{path}: schema_version {raw.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
    source = raw.get("source")
    if not isinstance(source, Mapping):
        raise RoleError(f"{path}: no [source] table")
    absent = [field for field in _SOURCE_FIELDS if not str(source.get(field, "")).strip()]
    if absent:
        raise RoleError(f"{path}: [source] lacks {', '.join(absent)}")
    declarations = [_declaration(point, path) for point in raw.get("points", [])]
    try:
        loops = [ControlLoop.model_validate(loop) for loop in raw.get("loops", [])]
    except ValidationError as error:
        raise RoleError(f"{path}: {error}") from error
    rendered = "; ".join(f"{field} {source[field]}" for field in _SOURCE_FIELDS)
    return SignalRoles(declarations, signal_keys, source=rendered, loops=loops)


def _declaration(point: Mapping[str, object], path: Path) -> RoleDeclaration:
    fields = dict(point)
    role = fields.pop("role", None)
    if role == _NO_ROLE:
        fields["role"] = None
    else:
        try:
            fields["role"] = SignalRole(str(role))
        except ValueError:
            raise RoleError(f"{path}: {fields.get('signal')!r} has unknown role {role!r}") from None
    try:
        return RoleDeclaration.model_validate(fields)
    except ValidationError as error:
        raise RoleError(f"{path}: {error}") from error
