"""Which signals sit on the same piece of plant, declared rather than inferred.

PART 5A models the plant jointly and attributes a joint anomaly back to the signal that broke the
structure. That is the right unit for *explaining* an anomaly and the wrong unit for *counting*
one. When a pump falters, every instrument on that pump departs from expectation at the same
instant, and Atlas emits one `Deviation` for each. Ten sensors on one pump produce ten deviations
and an operator with ten things to investigate, when there was one thing.

Collapsing those ten into one needs a fact nothing in PHOS currently holds: which signals share a
physical unit. That fact is not statistical. It is a claim about plumbing, and this module is
where it is written down.

**Topology is declared, never inferred, and that is a policy rather than a convenience.**

The tempting shortcut is to cluster signals by how they co-move over the training window and call
the clusters subsystems. It is circular. Grouping exists to answer "did these deviations share a
cause?", so if membership is itself derived from co-movement then the answer is being computed
from the same statistics that raised the deviations. Signals would be grouped *because* they move
together, and their moving together would then be counted as one event *on the grounds that they
are grouped*. The reduction would be real in the log and meaningless in the plant.

So membership comes from outside the data — process documentation, P&ID diagrams, the corpus
authors' published description of the testbed — and every subsystem carries a `source` naming the
document it came from. A subsystem whose source reads "clustered by correlation" is visibly wrong
to a reviewer, which is the point. See ADR 0010.

**Membership is a partition, and construction is where that is enforced.** A signal belongs to
exactly one subsystem, every corpus signal belongs to one, and nothing is declared that the corpus
does not contain. All four failures raise at construction, name the offending signals, and are
unrecoverable at runtime: a partially mapped corpus silently reverts to per-signal counting for
the unmapped remainder, which is worse than having no map at all because the failure is invisible.

This module builds no detection logic and produces no evaluation number.
"""

import logging
import tomllib
from collections.abc import Collection, Iterator, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

__all__ = [
    "SCHEMA_VERSION",
    "Subsystem",
    "SubsystemMap",
    "TopologyError",
    "load_topology",
    "render_topology",
]

logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = 1
"""Declaration-file format this module understands.

Bumped when the file layout changes incompatibly. A file carrying any other version is refused
rather than read optimistically, because a topology read half-correctly is a partition that is
quietly wrong.
"""


class TopologyError(ValueError):
    """A topology that cannot be trusted as a statement about the plant.

    Subclasses `ValueError` so a caller that only knows about the built-in still catches it, while
    a caller that wants to distinguish "this topology does not describe this corpus" from any
    other bad argument can catch this instead.
    """


class Subsystem(BaseModel):
    """One physical unit of the plant, and the signals instrumented on it.

    Attributes:
        subsystem_id: Stable identifier, unique within a corpus. Used as the grouping key, so it
            is expected to outlive any particular label wording.
        label: Human-readable name, for an operator rather than for code.
        signals: The signal keys instrumented on this unit. In a corpus loaded by
            `LabelledCsvAdapter` a signal key is the CSV column name, which is the `feature` of
            every `Observation` derived from it.
        source: The documentation this assignment came from, named specifically enough that
            someone who has seen the plant can check it. Not decoration — it is the audit path
            that keeps inference from creeping in later, so a blank or whitespace value is
            refused.
    """

    model_config = ConfigDict(frozen=True)

    subsystem_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    signals: frozenset[str]
    source: str = Field(min_length=1)

    @field_validator("source")
    @classmethod
    def _check_source_is_substantive(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must name the documentation the assignment came from")
        return value


class SubsystemMap:
    """A corpus's complete signal set partitioned into physical units.

    Not a Pydantic model: it maintains lookup indices derived from its subsystems, and the whole
    point of the type is that those cannot drift from the declaration. Construction validates and
    then freezes; there is no mutation API and no lazy population.

    Every failure mode is a construction-time raise rather than a runtime surprise, because a map
    that is wrong in any of these ways corrupts every count taken from it, and the corruption
    looks like success.
    """

    def __init__(self, subsystems: Collection[Subsystem], signal_keys: Collection[str]) -> None:
        """Validate a declaration against the corpus it claims to describe.

        Args:
            subsystems: The declared units. Iteration order is preserved for rendering.
            signal_keys: Every signal the corpus actually contains.

        Raises:
            TopologyError: If two subsystems share an identifier, if any subsystem is empty, if
                any signal is assigned twice, if any declared signal is absent from the corpus, or
                if any corpus signal is unassigned.
        """
        declared = tuple(subsystems)
        corpus = frozenset(signal_keys)

        _reject_duplicate_identifiers(declared)
        _reject_empty_subsystems(declared)
        owners = _index_by_signal(declared)
        _reject_phantom_signals(owners, corpus)
        _reject_unassigned_signals(owners, corpus)

        self._subsystems = declared
        self._by_signal = owners
        self._by_id = {subsystem.subsystem_id: subsystem for subsystem in declared}
        logger.debug(
            "topology validated: %d signal(s) across %d subsystem(s)", len(corpus), len(declared)
        )

    @property
    def subsystems(self) -> tuple[Subsystem, ...]:
        """The declared units, in declaration order. A tuple of frozen models, so read-only."""
        return self._subsystems

    def subsystem_for(self, signal_key: str) -> Subsystem:
        """Return the unit ``signal_key`` is instrumented on.

        Total over the corpus signal set by construction, so this raises only for a signal the map
        was never built against — which is a caller error rather than a missing assignment.

        Raises:
            TopologyError: If ``signal_key`` is outside the corpus this map was built against.
        """
        subsystem = self._by_signal.get(signal_key)
        if subsystem is None:
            raise TopologyError(
                f"signal {signal_key!r} is not in the corpus this topology was built against"
            )
        return subsystem

    def signals_in(self, subsystem_id: str) -> frozenset[str]:
        """Return the signals instrumented on ``subsystem_id``.

        Raises:
            TopologyError: If no subsystem carries that identifier.
        """
        subsystem = self._by_id.get(subsystem_id)
        if subsystem is None:
            raise TopologyError(f"no subsystem {subsystem_id!r} in this topology")
        return subsystem.signals

    def __iter__(self) -> Iterator[Subsystem]:
        """Iterate the declared units in declaration order."""
        return iter(self._subsystems)

    def __len__(self) -> int:
        """Number of declared units."""
        return len(self._subsystems)


def _reject_duplicate_identifiers(declared: Sequence[Subsystem]) -> None:
    """Refuse two subsystems sharing an identifier, which makes `signals_in` ill-defined."""
    seen: set[str] = set()
    repeated: set[str] = set()
    for subsystem in declared:
        if subsystem.subsystem_id in seen:
            repeated.add(subsystem.subsystem_id)
        seen.add(subsystem.subsystem_id)
    if repeated:
        raise TopologyError(
            f"subsystem identifier(s) declared more than once: {_quote(sorted(repeated))}"
        )


def _reject_empty_subsystems(declared: Sequence[Subsystem]) -> None:
    """Refuse a declared unit with no instrumentation, which cannot be a physical unit."""
    empty = sorted(s.subsystem_id for s in declared if not s.signals)
    if empty:
        raise TopologyError(f"subsystem(s) declaring no signals: {_quote(empty)}")


def _index_by_signal(declared: Sequence[Subsystem]) -> dict[str, Subsystem]:
    """Build the signal to subsystem index, refusing any signal claimed by two units."""
    owners: dict[str, Subsystem] = {}
    conflicts: dict[str, tuple[str, str]] = {}
    for subsystem in declared:
        for signal in subsystem.signals:
            existing = owners.get(signal)
            if existing is not None:
                conflicts[signal] = (existing.subsystem_id, subsystem.subsystem_id)
                continue
            owners[signal] = subsystem
    if conflicts:
        detail = ", ".join(
            f"{signal!r} ({first}, {second})"
            for signal, (first, second) in sorted(conflicts.items())
        )
        raise TopologyError(
            f"signal(s) assigned to more than one subsystem: {detail}. Membership must be a "
            "partition, not a covering — the grouping key depends on it."
        )
    return owners


def _reject_phantom_signals(owners: dict[str, Subsystem], corpus: frozenset[str]) -> None:
    """Refuse declared signals the corpus does not contain — topology drift, or a typo."""
    phantom = sorted(set(owners) - corpus)
    if phantom:
        raise TopologyError(
            f"topology declares signal(s) not present in the corpus: {_quote(phantom)}"
        )


def _reject_unassigned_signals(owners: dict[str, Subsystem], corpus: frozenset[str]) -> None:
    """Refuse a partially mapped corpus, whose unmapped remainder would count per-signal."""
    unassigned = sorted(corpus - set(owners))
    if unassigned:
        raise TopologyError(
            f"corpus signal(s) not assigned to any subsystem: {_quote(unassigned)}. Totality is "
            "the point; an unmapped signal silently reverts to per-signal counting."
        )


def _quote(names: Sequence[str]) -> str:
    """Render names for an error message, quoted so an empty or padded one is visible."""
    return ", ".join(repr(name) for name in names)


class _TopologyDocument(BaseModel):
    """The on-disk declaration format. Private: callers go through `load_topology`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    corpus: str = Field(min_length=1)
    subsystems: list[Subsystem]


def load_topology(path: Path, signal_keys: Collection[str], *, corpus: str) -> SubsystemMap:
    """Read a topology declaration and validate it against a corpus's signal set.

    Args:
        path: The TOML declaration.
        signal_keys: Every signal the corpus actually contains.
        corpus: The corpus identifier the file is expected to carry. Checked rather than assumed,
            because a topology pointed at the wrong corpus otherwise fails as a confusing wall of
            phantom and unassigned signals instead of as one clear mismatch.

    Returns:
        The validated map.

    Raises:
        TopologyError: If the file is unreadable as TOML, does not match the declaration schema,
            carries an unsupported schema version or a different corpus identifier, or describes a
            topology that violates any construction invariant. Every message names ``path``.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise TopologyError(f"{path} is not readable as TOML: {error}") from error

    try:
        document = _TopologyDocument.model_validate(raw)
    except ValidationError as error:
        raise TopologyError(f"{path} is not a valid topology declaration: {error}") from error

    if document.schema_version != SCHEMA_VERSION:
        raise TopologyError(
            f"{path} declares schema_version {document.schema_version}; this build understands "
            f"{SCHEMA_VERSION}"
        )
    if document.corpus != corpus:
        raise TopologyError(
            f"{path} declares corpus {document.corpus!r}, but was loaded against {corpus!r}"
        )

    try:
        return SubsystemMap(document.subsystems, signal_keys)
    except TopologyError as error:
        raise TopologyError(f"{path}: {error}") from error


def render_topology(topology: SubsystemMap) -> str:
    """Render a complete, human-readable listing of a topology.

    This is the audit path. A declared topology is only as good as a domain expert's ability to
    look at it and say "no, the level transmitter is on the other tank", so every subsystem is
    shown with its label, the documentation it came from, and every signal it claims, in sorted
    order.

    Args:
        topology: The map to render.

    Returns:
        A multi-line listing. Deterministic for a given map.
    """
    total = sum(len(subsystem.signals) for subsystem in topology)
    lines = [f"{total} signal(s) across {len(topology)} subsystem(s)"]
    if len(topology) == 0:
        lines.append("  (no subsystems declared)")
    for subsystem in topology:
        lines.append("")
        lines.append(f"  {subsystem.subsystem_id} — {subsystem.label}")
        lines.append(f"    source: {subsystem.source}")
        lines.append(f"    signals ({len(subsystem.signals)}):")
        lines.extend(f"      {signal}" for signal in sorted(subsystem.signals))
    return "\n".join(lines)
