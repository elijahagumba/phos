"""What a device's commanding *looks like*, as ontology observations a model can baseline.

A single command says nothing about whether it is normal. "Write 1 to coil 17" is either a routine
setpoint change or the moment a pump was stopped, and the bytes are identical. What separates them
is behaviour over time: how often this device commands, which functions it uses, which registers it
writes and with what values, and how rigid its rhythm is. This module computes those quantities
per device per window and emits each as an `Observation`, so that PART 3's baselines and 5A's joint
models consume command behaviour through exactly the path they already use for sensor telemetry —
no new model, no special case, no private alert format (Constitution §3.1).

**Every feature is a scalar for one device at one instant, because that is what the ontology is.**
The instant is the *window's start*, shared by every feature of every device in that window, which
is what lets `phos.atlas.vectorise` place them side by side on one row instead of a ragged scatter.

**The features, and why these.**

- *Volume and mix* — `command_count`, and one count per function code. Industrial polling is
  regular in both amount and kind, so a change in either is signal.
- *Write targets* — how many distinct addresses were written, and the span of them. Which registers
  a device touches is a stable property of its job.
- *Written values* — the range and mean of 16-bit register writes. Coil writes are excluded and
  `REGISTER_WRITE_FUNCTIONS` says why.
- *Read/write balance* — `write_command_share`, in ``[0, 1]``. The bounded form of the read/write
  ratio, deliberately: a device that stops reading gives the ratio an infinite value, which cannot
  be baselined, cannot serialise, and would break traceability the moment it was stored.
- *Rhythm* — the mean gap between commands and its coefficient of variation. A PLC polling on a
  fixed cycle is more predictable than anything the process itself does, so rigidity is one of the
  strongest behavioural signals an industrial network carries.

**Three refusals, each of which is the honest answer rather than a limitation.**

1. *Too few commands, no features.* A device below `CommandFeaturePolicy.min_commands` in a window
   emits nothing for that window. Four commands do not describe a rhythm, and a baseline learned
   from them would be a baseline of noise — the same policy `PerKeyBehaviouralModel` applies with
   `min_samples`.
2. *A zero is a measurement; an absence is not.* For a window a device was active in, every
   function code it uses anywhere in the stream gets a count, including zero — because "this
   device wrote nothing this minute" is something we looked at and saw. For a window it sent
   nothing in, nothing at all is emitted: a device off the wire and a device that is quiet are
   indistinguishable from here, and the *relationship* going silent is `graph`'s question.
3. *Nothing is computed from a field the wire did not carry.* A write whose address P1 left
   ``None`` contributes to no address feature rather than being placed at register 0.

**The caveat that must travel with every number here.** `COMMAND_BASELINE_CAVEATS`. A baseline is
only as representative as the capture it came from, and a short or partial capture makes normal
look narrower than it is — which does not fail loudly, it inflates every later deviation.
"""

import logging
import math
from collections.abc import Iterable, Sequence
from datetime import timedelta
from itertools import pairwise
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.atlas.packet.commands import (
    CommandEvent,
    CommandStreamStats,
    Window,
    command_events,
    frame_ranges,
    is_register_write,
    is_write,
    stream_span,
    tile_windows,
    window_index,
)
from phos.atlas.packet.dissect import DissectionResult
from phos.ontology import Domain, EntityId, Observation

__all__ = [
    "COMMAND_BASELINE_CAVEATS",
    "COMMAND_COUNT",
    "COMMAND_INTERVAL_CV",
    "COMMAND_INTERVAL_MEAN_MS",
    "DISTINCT_WRITE_ADDRESSES",
    "FUNCTION_COUNT_PREFIX",
    "REGISTER_WRITE_VALUE_MAX",
    "REGISTER_WRITE_VALUE_MEAN",
    "REGISTER_WRITE_VALUE_MIN",
    "SHORT_CAPTURE_CAVEAT",
    "UNREPRESENTATIVE_TRAFFIC_CAVEAT",
    "WRITE_ADDRESS_MAX",
    "WRITE_ADDRESS_MIN",
    "WRITE_COMMAND_SHARE",
    "CommandFeaturePolicy",
    "featurise_commands",
    "function_count_feature",
]

logger = logging.getLogger(__name__)

COMMAND_COUNT: Final = "command_count"
"""How many commands the device issued in the window."""

FUNCTION_COUNT_PREFIX: Final = "command_count_fn"
"""Prefix of the per-function-code count features. Build one with `function_count_feature`."""

WRITE_COMMAND_SHARE: Final = "write_command_share"
"""Share of the window's commands that changed plant state, in ``[0, 1]``."""

DISTINCT_WRITE_ADDRESSES: Final = "distinct_write_addresses"
"""How many different coil or register addresses the device wrote to."""

WRITE_ADDRESS_MIN: Final = "write_address_min"
"""Lowest address written."""

WRITE_ADDRESS_MAX: Final = "write_address_max"
"""Highest address written."""

REGISTER_WRITE_VALUE_MIN: Final = "register_write_value_min"
"""Smallest 16-bit value written to a register."""

REGISTER_WRITE_VALUE_MAX: Final = "register_write_value_max"
"""Largest 16-bit value written to a register."""

REGISTER_WRITE_VALUE_MEAN: Final = "register_write_value_mean"
"""Mean 16-bit value written to a register."""

COMMAND_INTERVAL_MEAN_MS: Final = "command_interval_mean_ms"
"""Mean gap between consecutive commands within the window, in milliseconds."""

COMMAND_INTERVAL_CV: Final = "command_interval_cv"
"""Coefficient of variation of those gaps — spread divided by mean, so it is scale-free.

Zero for a perfectly periodic poller. Scale-free on purpose: it makes a device polling every
100 ms and one polling every 10 s comparably rigid, which a raw standard deviation would not.
"""

SHORT_CAPTURE_CAVEAT: Final = (
    "Capture-length dependence: a command baseline describes the capture it was learned from, not "
    "the plant. A short capture sees fewer windows, so normal looks narrower than it is and every "
    "later deviation is inflated. This does not fail loudly — the numbers look the same either "
    "way — so the length and coverage of the learning capture must be reported beside any result "
    "computed from these features."
)

UNREPRESENTATIVE_TRAFFIC_CAVEAT: Final = (
    "Operating-mode dependence: a capture taken during one plant mode contains only that mode's "
    "command behaviour. A shift change, a batch changeover or a seasonal setpoint will look like "
    "a departure from normal because it is absent from what was learned, not because it is "
    "abnormal. Nothing here can distinguish the two; only a capture spanning the modes can."
)

COMMAND_BASELINE_CAVEATS: Final = (SHORT_CAPTURE_CAVEAT, UNREPRESENTATIVE_TRAFFIC_CAVEAT)
"""Everything that must travel with a number computed from these features.

Both say the same thing from two directions: **the baseline is a property of the capture.** They
are stated as constants rather than prose in a docstring so a report can carry them verbatim, the
way `phos.atlas.engine.ATLAS_VERTICAL_CAVEATS` does for the grouping result.
"""

_THIN_CAPTURE_WINDOWS: Final = 10
"""Windows below which a capture is too thin for a baseline worth trusting, and says so."""

_MS_PER_SECOND: Final = 1000.0


def function_count_feature(function_code: int) -> str:
    """Return the feature name counting commands of ``function_code``, e.g. ``command_count_fn3``.

    The code goes in the feature name rather than in `Observation.context` because a baseline is
    keyed by ``(entity, feature)``: a device's read rate and its write rate are different
    behaviours and must be learned as different signals, not averaged into one.
    """
    return f"{FUNCTION_COUNT_PREFIX}{function_code}"


class CommandFeaturePolicy(BaseModel):
    """How command behaviour is sliced, and how much of it is needed before it is described.

    Attributes:
        window: Length of the slice each feature is computed over. One minute by default, which is
            long enough to hold many cycles of typical industrial polling and short enough that a
            change is not averaged away. Windows tile the capture from its first message; the
            partial tail is dropped (see `tile_windows`).
        min_commands: Fewest commands a device must issue in a window before any feature is
            emitted for it there. Below it the window says nothing about the device, and the
            honest report is silence rather than a number computed from three samples.
        min_intervals: Fewest gaps needed before the timing features are emitted. At least two,
            because a single interval has no spread and a coefficient of variation over it is
            always zero — a rigidity claim with no evidence behind it.
    """

    model_config = ConfigDict(frozen=True)

    window: timedelta = timedelta(minutes=1)
    min_commands: int = Field(default=4, ge=1)
    min_intervals: int = Field(default=3, ge=2)

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.window <= timedelta(0):
            raise ValueError(f"window must be positive, not {self.window}")
        return self


def featurise_commands(
    results: Iterable[DissectionResult],
    policy: CommandFeaturePolicy | None = None,
    stats: CommandStreamStats | None = None,
) -> list[Observation]:
    """Turn a dissected message stream into per-device, per-window behavioural observations.

    Args:
        results: What `dissect_capture` yields. **Consumed whole**, unlike everything in P1: a
            window's features cannot be computed until the window has closed, and the tiling
            cannot be laid out until the span is known. Order does not matter — events are sorted
            before use, so a capture with out-of-order timestamps gives the same answer.
        policy: How to slice and how much is enough. Defaults to `CommandFeaturePolicy`.
        stats: Optional accumulator, filled in with everything that was *not* a command. Reading
            it is the only way to tell a network with no commands from a capture P2 cannot read.

    Returns:
        The observations, ordered by ``(window start, device, feature)`` so two runs over one
        capture produce byte-identical output but for the opaque ids (Constitution §3.7). Empty
        when the stream holds no commands, or spans less than one whole window — both of which are
        facts about the capture and are reported as nothing rather than as zeroes.
    """
    policy = policy or CommandFeaturePolicy()
    materialised = list(results)
    events = list(command_events(materialised, stats))

    span = stream_span(materialised)
    if span is None:
        logger.debug("no results to featurise")
        return []

    windows = tile_windows(span[0], span[1], policy.window)
    if not windows:
        logger.warning(
            "capture spans %s, less than one %s window: no command behaviour can be described, "
            "and reporting a partial window would understate every device's command volume",
            span[1] - span[0],
            policy.window,
        )
        return []
    if len(windows) < _THIN_CAPTURE_WINDOWS:
        logger.warning(
            "only %d whole window(s) of command behaviour: a baseline learned from this makes "
            "normal look narrower than it is. %s",
            len(windows),
            SHORT_CAPTURE_CAVEAT,
        )

    grouped, functions_by_device = _group(events, windows)
    observations: list[Observation] = []
    for (index, device), window_events in grouped.items():
        if len(window_events) < policy.min_commands:
            logger.debug(
                "skipping %s in window %d: %d < min_commands=%d",
                device,
                index,
                len(window_events),
                policy.min_commands,
            )
            continue
        observations.extend(
            _describe(windows[index], device, window_events, functions_by_device[device], policy)
        )

    observations.sort(key=lambda o: (o.timestamp, o.entity_ids[0], o.feature))
    logger.info(
        "featurised %d command(s) into %d observation(s) over %d window(s) and %d device(s)",
        len(events),
        len(observations),
        len(windows),
        len(functions_by_device),
    )
    return observations


def _event_order(event: CommandEvent) -> tuple[object, ...]:
    """Total order over events: by time, then by where the bytes came from.

    The tie-break matters. Two commands can share a timestamp — captures record microseconds, and
    industrial devices are fast — and without a deterministic second key the interval series would
    depend on dictionary iteration order.
    """
    return (event.timestamp, event.source.capture, event.source.frame_index)


def _group(
    events: Sequence[CommandEvent], windows: Sequence[Window]
) -> tuple[dict[tuple[int, EntityId], list[CommandEvent]], dict[EntityId, set[int]]]:
    """Bucket events by ``(window, issuer)`` and record which functions each device ever issued.

    The function set is built from events that landed *inside* a window, not from the whole
    stream: a function code seen only in the dropped partial tail was never measured, and claiming
    a zero for it in every earlier window would put a count against traffic nothing describes.
    """
    grouped: dict[tuple[int, EntityId], list[CommandEvent]] = {}
    functions_by_device: dict[EntityId, set[int]] = {}
    for event in sorted(events, key=_event_order):
        index = window_index(event.timestamp, windows)
        if index is None:
            continue
        grouped.setdefault((index, event.issuer), []).append(event)
        functions_by_device.setdefault(event.issuer, set()).add(event.function_code)
    return grouped, functions_by_device


def _describe(
    window: Window,
    device: EntityId,
    events: Sequence[CommandEvent],
    function_codes: set[int],
    policy: CommandFeaturePolicy,
) -> list[Observation]:
    """Compute every feature this window supports for one device.

    Args:
        window: The slice being described.
        device: The issuing device's entity id.
        events: Its commands in the window, in `_event_order`. Never fewer than
            ``policy.min_commands``.
        function_codes: Every code this device issued anywhere that was measured, so a window
            without one of them reports a measured zero rather than a silence.
        policy: The sufficiency thresholds.

    Returns:
        The observations, unordered — `featurise_commands` sorts.
    """
    observations: list[Observation] = []

    def emit(feature: str, value: float, evidence: Sequence[CommandEvent]) -> None:
        observations.append(
            Observation(
                entity_ids=[device],
                feature=feature,
                value=value,
                timestamp=window.start,
                domain=Domain.ATLAS,
                context=_context(window, evidence),
            )
        )

    emit(COMMAND_COUNT, float(len(events)), events)

    for code in sorted(function_codes):
        matching = [event for event in events if event.function_code == code]
        # An empty match traces to the whole window: those are the frames that were examined and
        # did not contain this function, which is exactly what justifies saying zero.
        emit(function_count_feature(code), float(len(matching)), matching or events)

    writes = [event for event in events if is_write(event.function_code)]
    # Provenance is the whole window, not just the writes. The share is a *ratio*, and its
    # denominator is every command in the window — an auditor handed only the write frames could
    # recompute the numerator and nothing else, which is not a reconstructable value (§3.2).
    emit(WRITE_COMMAND_SHARE, len(writes) / len(events), events)

    addressed = [event for event in writes if event.reference_address is not None]
    if addressed:
        addresses = [
            event.reference_address for event in addressed if event.reference_address is not None
        ]
        emit(DISTINCT_WRITE_ADDRESSES, float(len(set(addresses))), addressed)
        emit(WRITE_ADDRESS_MIN, float(min(addresses)), addressed)
        emit(WRITE_ADDRESS_MAX, float(max(addresses)), addressed)

    valued = [event for event in writes if is_register_write(event.function_code) and event.values]
    if valued:
        values = [value for event in valued for value in event.values]
        emit(REGISTER_WRITE_VALUE_MIN, float(min(values)), valued)
        emit(REGISTER_WRITE_VALUE_MAX, float(max(values)), valued)
        emit(REGISTER_WRITE_VALUE_MEAN, sum(values) / len(values), valued)

    intervals = _intervals_ms(events)
    if len(intervals) >= policy.min_intervals:
        mean = sum(intervals) / len(intervals)
        emit(COMMAND_INTERVAL_MEAN_MS, mean, events)
        if mean > 0.0:
            variance = sum((interval - mean) ** 2 for interval in intervals) / len(intervals)
            emit(COMMAND_INTERVAL_CV, math.sqrt(variance) / mean, events)

    return observations


def _intervals_ms(events: Sequence[CommandEvent]) -> list[float]:
    """Return the gaps between consecutive commands, in milliseconds.

    Note:
        Measured within the window only, so a window holding ``k`` commands yields ``k - 1``
        intervals. The gap spanning a boundary belongs wholly to neither window, and attributing
        it to one would make that window's rhythm depend on when the tiling happened to start.
    """
    return [
        (later.timestamp - earlier.timestamp).total_seconds() * _MS_PER_SECOND
        for earlier, later in pairwise(events)
    ]


def _context(window: Window, evidence: Sequence[CommandEvent]) -> dict[str, str]:
    """Build the traceability context: which device, which window, which frames.

    Together these make a feature value reconstructable from the capture on disk (Constitution
    §3.2): the device and window say what was measured, and ``frames`` says where to look.

    Frames are recorded by `frame_ranges` as a per-capture index range.
    """
    return {
        "device_ip": evidence[0].issuer_ip,
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "frames": frame_ranges(evidence),
        "frame_count": str(len(evidence)),
        "protocol": ",".join(sorted({event.protocol for event in evidence})),
    }
