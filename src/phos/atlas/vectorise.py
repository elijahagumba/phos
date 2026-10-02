"""Reshaping ontology observations into the ``(time x signal)`` matrix a joint model needs.

The ontology stores an observation as one scalar for one ``(entity, feature)`` at one instant,
which is right for evidence and wrong for correlation: to learn that a pump's flow moves with a
valve's position you need both numbers side by side, at the same moment, in a fixed column order.
This module is the only place in PHOS that performs that reshape, so that the judgement calls it
requires are made once, in the open, and tested.

There is really only one judgement call, and it is what to do about a signal with no reading at
some timestamp. The tempting answer is a zero, and it is a lie: it fabricates a measurement that
was never taken, and every correlation learned afterwards is partly learned from fiction. The
policy here is stated instead of assumed:

1. **Carry the last reading forward**, for at most `VectorisePolicy.forward_fill_rows` rows. An
   industrial signal that was not re-sampled this instant is still, physically, at its last known
   value — that is what makes the carry defensible over a short gap and indefensible over a long
   one.
2. **Otherwise drop the whole timestamp.** A row with a hole in it cannot be projected onto a
   learned subspace, and the honest response to "I do not know what the plant was doing" is to
   say nothing about that instant rather than to guess.
3. **Never substitute a value that was not measured or carried.** No zero-fill, no mean-fill.

A carried cell is marked `NO_OBSERVATION` in `VectorisedSeries.source_index`. That is what keeps
Constitution §3.2 intact downstream: a model may *use* a carried value to reconstruct the rest of
the plant, but it cannot raise a `Deviation` about one, because there is no measurement at that
instant for the deviation to point back to.
"""

import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Self

import numpy
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.models import ModelKey, model_key
from phos.ontology import Observation

__all__ = [
    "NO_OBSERVATION",
    "SignalSpace",
    "VectorisePolicy",
    "VectorisedSeries",
    "vectorise",
]

logger = logging.getLogger(__name__)

_NOTEWORTHY_LOSS: Final = 0.1
"""Share of timestamps that may be discarded before the loss is worth an operator's attention.

Below it, a handful of ragged samples is ordinary. Above it, the corpus has real gaps and every
number computed from what remains describes a different corpus than the one on disk.
"""

NO_OBSERVATION: Final = -1
"""Marks a cell of `VectorisedSeries.source_index` that no observation stands behind.

Such a cell was carried forward from an earlier row. Its value is the plant's last known state
and is legitimate input to a reconstruction; it is not a fresh measurement, so nothing may raise
a `Deviation` about it.
"""


class SignalSpace(BaseModel):
    """The ordered set of ``(entity_id, feature)`` signals a joint model spans.

    Order is the contract. A fitted multivariate model stores its parameters as plain numbers
    indexed by column, so the space is what says which column is which signal — and the same
    space must be used to vectorise training and scoring data or the parameters address the wrong
    plant.

    Attributes:
        signals: The signals, in column order. No signal appears twice.
    """

    model_config = ConfigDict(frozen=True)

    signals: tuple[ModelKey, ...] = ()

    @model_validator(mode="after")
    def _check_distinct(self) -> Self:
        seen: set[ModelKey] = set()
        for signal in self.signals:
            if signal in seen:
                raise ValueError(f"signal {signal!r} appears more than once in the space")
            seen.add(signal)
        return self

    @classmethod
    def from_observations(cls, observations: Sequence[Observation]) -> Self:
        """Learn the space from a training corpus.

        Args:
            observations: The training observations. Order is irrelevant.

        Returns:
            A space holding every distinct ``(entity_id, feature)`` present, sorted so that two
            runs over the same corpus produce the same column order (Constitution §3.7).
        """
        return cls(signals=tuple(sorted({model_key(o) for o in observations})))

    @property
    def size(self) -> int:
        """Number of signals, which is the width of the matrices this space describes."""
        return len(self.signals)

    def index_of(self, signal: ModelKey) -> int | None:
        """Return the column ``signal`` occupies, or ``None`` if the space does not span it.

        ``None`` rather than an exception: a signal outside the space is *unknown*, and a joint
        model has nothing to say about it — which is not the same as it being anomalous.
        """
        try:
            return self.signals.index(signal)
        except ValueError:
            return None

    def select(self, columns: Collection[int]) -> "SignalSpace":
        """Return the sub-space holding only ``columns``, in the order given.

        Used at fit time to drop signals the model cannot learn anything about.

        Raises:
            ValueError: If a column is outside the space, which would silently mis-address the
                signals that remain.
        """
        for column in columns:
            if not 0 <= column < self.size:
                raise ValueError(f"column {column} is outside a space of {self.size} signal(s)")
        return SignalSpace(signals=tuple(self.signals[column] for column in columns))


class VectorisePolicy(BaseModel):
    """How much missing data the reshape will tolerate before it discards a timestamp.

    Attributes:
        forward_fill_rows: How many consecutive rows a reading may be carried across before it is
            considered stale. ``0`` disables carrying entirely, so any hole drops its timestamp.
            Counted in rows rather than seconds so the policy means the same thing on BATADAL's
            hourly SCADA readings and HAI's ten-second ones.
    """

    model_config = ConfigDict(frozen=True)

    forward_fill_rows: int = Field(default=1, ge=0)


@dataclass(frozen=True)
class VectorisedSeries:
    """A corpus expressed as one row per timestamp and one column per signal.

    Not a Pydantic model: it holds numpy arrays, which are computation rather than ontology, and
    nothing here is stored or served. Everything a `Deviation` needs is derived from it and then
    expressed in ontology types.

    Attributes:
        signal_space: The space whose column order this matrix follows.
        timestamps: One entry per surviving row, ascending.
        matrix: ``(n_rows x n_signals)`` of float values.
        source_index: ``(n_rows x n_signals)`` of indices into the observation sequence that was
            vectorised, or `NO_OBSERVATION` where the cell was carried forward. This is the
            traceability link: a model reads it to name the measurement a deviation came from.
        dropped_timestamps: How many timestamps were discarded for having an unfillable hole.
            Reported rather than hidden, because a corpus that loses most of its rows here is a
            corpus whose subsequent numbers deserve suspicion.
    """

    signal_space: SignalSpace
    timestamps: tuple[datetime, ...]
    matrix: NDArray[numpy.float64]
    source_index: NDArray[numpy.int64]
    dropped_timestamps: int

    @property
    def n_rows(self) -> int:
        """Number of surviving timestamps."""
        return len(self.timestamps)


def vectorise(
    observations: Sequence[Observation],
    signal_space: SignalSpace,
    policy: VectorisePolicy | None = None,
) -> VectorisedSeries:
    """Assemble ``observations`` into a ``(time x signal)`` matrix over ``signal_space``.

    Args:
        observations: The measurements to reshape. Need not be sorted — rows come out in
            ascending timestamp order whatever order they went in. Observations for signals
            outside ``signal_space`` are ignored: the space is the model's world, and a signal it
            never learned has no column to occupy.
        signal_space: The column order to assemble into.
        policy: The missing-signal policy. Defaults to carrying a reading across one row.

    Returns:
        The assembled series. Rows appear in ascending timestamp order.

    Note:
        If one signal is measured twice at the same instant, the later of the two in the input
        order wins. That is a corpus defect rather than a case to model, and taking one reading is
        preferable to averaging two that may not be commensurable.
    """
    policy = policy or VectorisePolicy()
    width = signal_space.size

    columns = {signal: index for index, signal in enumerate(signal_space.signals)}
    by_timestamp: dict[datetime, dict[int, int]] = {}
    for position, observation in enumerate(observations):
        column = columns.get(model_key(observation))
        if column is None:
            continue
        by_timestamp.setdefault(observation.timestamp, {})[column] = position

    rows: list[NDArray[numpy.float64]] = []
    sources: list[NDArray[numpy.int64]] = []
    timestamps: list[datetime] = []
    dropped = 0

    carried = numpy.zeros(width, dtype=numpy.float64)
    staleness = numpy.full(width, policy.forward_fill_rows + 1, dtype=numpy.int64)

    for timestamp in sorted(by_timestamp):
        present = by_timestamp[timestamp]
        staleness = staleness + 1
        for column, position in present.items():
            carried[column] = observations[position].value
            staleness[column] = 0

        if width and int(numpy.max(staleness)) > policy.forward_fill_rows:
            dropped += 1
            continue

        source_row = numpy.full(width, NO_OBSERVATION, dtype=numpy.int64)
        for column, position in present.items():
            source_row[column] = position

        timestamps.append(timestamp)
        rows.append(carried.copy())
        sources.append(source_row)

    matrix = (numpy.vstack(rows) if rows else numpy.empty((0, width), dtype=numpy.float64)).astype(
        numpy.float64
    )
    source_index = (
        numpy.vstack(sources) if sources else numpy.empty((0, width), dtype=numpy.int64)
    ).astype(numpy.int64)

    offered = len(timestamps) + dropped
    if dropped and dropped > _NOTEWORTHY_LOSS * offered:
        logger.warning(
            "vectorising over %d signals dropped %d of %d timestamps (%.0f%%) for missing data; "
            "anything measured on what survives describes a corpus with holes in it",
            width,
            dropped,
            offered,
            100.0 * dropped / offered,
        )
    else:
        logger.debug(
            "vectorised %d observations over %d signals: %d rows kept, %d timestamps dropped",
            len(observations),
            width,
            len(timestamps),
            dropped,
        )
    return VectorisedSeries(
        signal_space=signal_space,
        timestamps=tuple(timestamps),
        matrix=matrix,
        source_index=source_index,
        dropped_timestamps=dropped,
    )
