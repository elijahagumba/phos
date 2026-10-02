"""Who commands whom: the learned device-command graph, and what changes in it look like.

`behaviour` describes each device on its own. This module describes the *structure between* them —
which devices command which, over which functions — because some of the most consequential changes
on an industrial network are invisible in any single device's statistics. A workstation that has
never spoken to a safety PLC and now does may be issuing an entirely ordinary write, at an entirely
ordinary rate, using an entirely ordinary function. Nothing about the command is abnormal. The
*relationship* is.

**Edges are observed command relationships, not wiring.** An edge means "this device was seen
commanding that one in this capture", nothing more. It is not a claim about cabling, routing,
process design or authorisation, and it must never be read as one — a link absent from the graph
may be perfectly legitimate and simply unexercised while the capture ran. That is the same
`COMMAND_BASELINE_CAVEATS` limit `behaviour` carries, and it bites harder here: a device's *rate*
degrades gracefully as a capture shortens, but its *relationships* are all-or-nothing, so a link
used once a shift is either in the graph or reported as new the first time it appears.

This is also why the graph is deliberately **not** the declared topology `phos.atlas.topology`
holds. That module refuses to infer which signals share a pump, because grouping derived from
co-movement and then used to count co-movement is circular. Nothing circular happens here: the
graph is learned from one corpus and compared against a *different* one, and it never feeds back
into what it learned from.

**Three changes, and each is a measurement rather than a flag.** `compare_to_graph` emits ordinary
`Observation`s — no private finding type (Constitution §3.1) — whose value quantifies the change,
so a larger number always means a larger departure:

- `unknown_command_relationship` — commands on a link the graph has never seen, counted.
- `silent_command_relationship` — how much traffic a comparable stretch of the learned graph
  says the link should have carried, and did not, in commands. A live window is judged against
  learned stretches of the same duration, not against a rate whose denominator is the entire
  train span.
- `unexpected_command_function` — commands using a function code never seen on that link, counted.

**Promoting any of these to evidence is P3's job, not this module's.** Nothing here reasons, scores
a confidence, or writes an OT template. A finding is a measured departure from an observed
baseline; whether it is maintenance, misconfiguration or an intruder is a question this layer is
not equipped to answer and does not pretend to.
"""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from statistics import median
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.atlas.packet.commands import (
    CommandEvent,
    CommandStreamStats,
    Window,
    command_events,
    format_frame_ranges,
    frame_ranges,
    stream_span,
    tile_windows,
    window_index,
)
from phos.atlas.packet.dissect import DissectionResult
from phos.ontology import Domain, EntityId, Observation, UtcDatetime

__all__ = [
    "DEFAULT_GRAPH_HORIZON",
    "SILENT_COMMAND_RELATIONSHIP",
    "UNEXPECTED_COMMAND_FUNCTION",
    "UNKNOWN_COMMAND_RELATIONSHIP",
    "CommandEdge",
    "DeviceCommandGraph",
    "GraphComparePolicy",
    "compare_to_graph",
    "learn_device_command_graph",
    "render_graph",
]

logger = logging.getLogger(__name__)

UNKNOWN_COMMAND_RELATIONSHIP: Final = "unknown_command_relationship"
"""Commands observed on a link the learned graph does not contain.

Value: how many. The entities are ``[issuer, target]``, so `phos.models.model_key` attributes the
observation to the device that *acted* — which is the one an operator will want to look at first.
"""

SILENT_COMMAND_RELATIONSHIP: Final = "silent_command_relationship"
"""A learned link that carried no commands at all in a window, against a comparable stretch.

Value: mean command count across learned stretches of the same duration as the live window — so a
busy link falling silent reports a larger number than a quiet one. A finding is emitted only when
a *typical* (median) comparable stretch carried at least one command; a fractional rate smeared
across a multi-day train is not silence.

Context records ``learned_span_seconds``, ``live_span_seconds`` and ``horizon_seconds`` so a
duration mismatch is reconstructable from the observation.
"""

DEFAULT_GRAPH_HORIZON: Final = timedelta(minutes=1)
"""Occupancy-bin duration used when learning a graph, matching `GraphComparePolicy.window`.

A live window is comparable to a learned stretch only when the two durations agree (or the live
window is an integer multiple of this bin). It is not a D2-fitted knob.
"""

_TYPICAL_SILENCE_FLOOR: Final = 1.0
"""A live window is silent only if a typical learned stretch of the same duration carried a command.

``1`` means "a comparable stretch typically had a command". It is not ``min_edge_commands`` and
must not be raised to starve silence until an attack uniquely leads.
"""

UNEXPECTED_COMMAND_FUNCTION: Final = "unexpected_command_function"
"""Commands on a known link using a function code never learned on it.

Value: how many. One observation per code, because "it also sent function 5" and "it also sent
function 16" are separate things that may warrant separate action.
"""

_Pair = tuple[EntityId, EntityId]


class CommandEdge(BaseModel):
    """One observed command relationship, with what was seen on it and where.

    Attributes:
        issuer: Entity id of the commanding device.
        target: Entity id of the commanded device.
        issuer_ip: The commanding device's address, so a rendering names it without a lookup.
        target_ip: The commanded device's address.
        function_codes: Every function code seen on this link, ascending and distinct. Ordered so
            two graphs learned from one capture serialise identically (Constitution §3.7).
        command_count: How many commands were observed. At least one — an edge exists because
            something was seen.
        first_seen: Timestamp of the earliest command on this link.
        last_seen: Timestamp of the latest.
        frames: Where the evidence is, as `format_frame_ranges` renders it.
        horizon_counts: Commands in successive ``DeviceCommandGraph.horizon`` bins covering the
            learned span. Compact occupancy, not a list of events: the stored graph stays
            proportional to links * bins. Empty on a hand-built edge that never learned occupancy.

    Invariants:
        ``function_codes`` is strictly ascending, ``first_seen <= last_seen``, and every
        occupancy count is non-negative.
    """

    model_config = ConfigDict(frozen=True)

    issuer: EntityId = Field(min_length=1)
    target: EntityId = Field(min_length=1)
    issuer_ip: str = Field(min_length=1)
    target_ip: str = Field(min_length=1)
    function_codes: tuple[int, ...] = Field(min_length=1)
    command_count: int = Field(ge=1)
    first_seen: UtcDatetime
    last_seen: UtcDatetime
    frames: str = Field(min_length=1)
    horizon_counts: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _check_ordering(self) -> Self:
        codes = self.function_codes
        if any(earlier >= later for earlier, later in pairwise(codes)):
            raise ValueError(f"function codes must be sorted and distinct, got {codes}")
        if self.first_seen > self.last_seen:
            raise ValueError(f"edge window is inverted: {self.first_seen} > {self.last_seen}")
        if any(count < 0 for count in self.horizon_counts):
            raise ValueError(f"occupancy counts must be non-negative, got {self.horizon_counts}")
        return self

    @property
    def pair(self) -> _Pair:
        """The ``(issuer, target)`` key this edge is identified by."""
        return (self.issuer, self.target)


class DeviceCommandGraph(BaseModel):
    """Which devices were observed commanding which, learned from one corpus.

    Attributes:
        edges: The observed relationships, ordered by ``(issuer, target)`` and each appearing once.
        learned_span: ``(earliest, latest)`` instant the learning corpus covered, or ``None`` when
            it held no commands. Still recorded on every silent finding. It is no longer the
            denominator of a per-minute rate used to manufacture silence: comparable stretches
            come from ``horizon`` occupancy bins.
        horizon: Duration of one occupancy bin, matching `GraphComparePolicy.window` at learn
            time. A live window is judged against learned stretches of this duration.

    Invariants:
        Edges are strictly ordered and unique by pair; the span, where present, is non-inverted;
        ``horizon`` is positive; occupancy-bin lengths agree across edges that have them.
    """

    model_config = ConfigDict(frozen=True)

    edges: tuple[CommandEdge, ...] = ()
    learned_span: tuple[UtcDatetime, UtcDatetime] | None = None
    horizon: timedelta = DEFAULT_GRAPH_HORIZON

    @model_validator(mode="after")
    def _check_edges(self) -> Self:
        pairs = [edge.pair for edge in self.edges]
        repeated = sorted({pair for pair in pairs if pairs.count(pair) > 1})
        if repeated:
            raise ValueError(f"relationship(s) present more than once: {repeated}")
        if any(earlier > later for earlier, later in pairwise(pairs)):
            raise ValueError("edges must be sorted by (issuer, target)")
        if self.learned_span is not None and self.learned_span[0] > self.learned_span[1]:
            raise ValueError(f"learned_span is inverted: {self.learned_span}")
        if self.edges and self.learned_span is None:
            raise ValueError("a graph with edges must record the span it learned them over")
        if self.horizon <= timedelta(0):
            raise ValueError(f"horizon must be positive, not {self.horizon}")
        lengths = {len(edge.horizon_counts) for edge in self.edges if edge.horizon_counts}
        if len(lengths) > 1:
            raise ValueError(f"edges disagree on occupancy-bin count: {sorted(lengths)}")
        return self

    @property
    def devices(self) -> tuple[EntityId, ...]:
        """Every device that appeared at either end of a relationship, sorted."""
        return tuple(sorted({end for edge in self.edges for end in (edge.issuer, edge.target)}))

    @property
    def command_count(self) -> int:
        """How many commands the graph was learned from."""
        return sum(edge.command_count for edge in self.edges)

    def edge(self, issuer: EntityId, target: EntityId) -> CommandEdge | None:
        """Return the relationship from ``issuer`` to ``target``, or ``None`` if there is none.

        ``None`` rather than an exception: a link the graph has never seen is *unknown*, which is
        a thing the caller must decide about, not an error.
        """
        for edge in self.edges:
            if edge.pair == (issuer, target):
                return edge
        return None


@dataclass
class _EdgeAccumulator:
    """Running totals for one relationship while a corpus is being read.

    Frame provenance is kept as per-capture bounds rather than as a list of events. Command times
    are held only while the corpus is being read, then compacted to occupancy bins on the edge so
    the stored graph stays proportional to links * bins, not commands.
    """

    issuer_ip: str
    target_ip: str
    first_seen: datetime
    last_seen: datetime
    command_count: int = 0
    function_codes: set[int] = field(default_factory=set)
    frame_bounds: dict[str, tuple[int, int]] = field(default_factory=dict)
    timestamps: list[datetime] = field(default_factory=list)

    def absorb(self, event: CommandEvent) -> None:
        """Fold one more command into the totals."""
        self.command_count += 1
        self.function_codes.add(event.function_code)
        self.first_seen = min(self.first_seen, event.timestamp)
        self.last_seen = max(self.last_seen, event.timestamp)
        self.timestamps.append(event.timestamp)
        index = event.source.frame_index
        low, high = self.frame_bounds.get(event.source.capture, (index, index))
        self.frame_bounds[event.source.capture] = (min(low, index), max(high, index))


def learn_device_command_graph(
    results: Iterable[DissectionResult], stats: CommandStreamStats | None = None
) -> DeviceCommandGraph:
    """Learn which devices command which from a corpus of dissected traffic.

    Args:
        results: What `dissect_capture` yields. Should be traffic believed normal — the graph is a
            model of *observed* behaviour and will happily learn an intrusion as routine if one is
            in the corpus, exactly as any behavioural baseline does.
        stats: Optional accumulator for everything that was not a command.

    Returns:
        The graph. Empty when the corpus holds no commands, which is a fact about the corpus and
        is reported as an empty graph rather than as a failure — though comparing anything against
        an empty graph makes every live relationship unknown, so a caller should check.
    """
    accumulators: dict[_Pair, _EdgeAccumulator] = {}
    earliest: datetime | None = None
    latest: datetime | None = None

    for event in command_events(results, stats):
        accumulator = accumulators.get((event.issuer, event.target))
        if accumulator is None:
            accumulator = _EdgeAccumulator(
                issuer_ip=event.issuer_ip,
                target_ip=event.target_ip,
                first_seen=event.timestamp,
                last_seen=event.timestamp,
            )
            accumulators[(event.issuer, event.target)] = accumulator
        accumulator.absorb(event)
        earliest = event.timestamp if earliest is None else min(earliest, event.timestamp)
        latest = event.timestamp if latest is None else max(latest, event.timestamp)

    occupancy_horizon = DEFAULT_GRAPH_HORIZON
    occupancy_bins: tuple[Window, ...] = ()
    if earliest is not None and latest is not None:
        occupancy_bins = tile_windows(earliest, latest, occupancy_horizon)
    edges = tuple(
        CommandEdge(
            issuer=issuer,
            target=target,
            issuer_ip=accumulator.issuer_ip,
            target_ip=accumulator.target_ip,
            function_codes=tuple(sorted(accumulator.function_codes)),
            command_count=accumulator.command_count,
            first_seen=accumulator.first_seen,
            last_seen=accumulator.last_seen,
            frames=format_frame_ranges(accumulator.frame_bounds),
            horizon_counts=_place_in_bins(accumulator.timestamps, occupancy_bins),
        )
        for (issuer, target), accumulator in sorted(accumulators.items())
    )
    span = None if earliest is None or latest is None else (earliest, latest)
    logger.info(
        "learned %d command relationship(s) among %d device(s) from %d command(s)",
        len(edges),
        len({end for edge in edges for end in edge.pair}),
        sum(edge.command_count for edge in edges),
    )
    return DeviceCommandGraph(edges=edges, learned_span=span, horizon=occupancy_horizon)


class GraphComparePolicy(BaseModel):
    """How live traffic is sliced when compared against a learned graph.

    Attributes:
        window: Length of the slice each comparison is made over, and the duration of the
            comparable learned stretch silence is judged against. A relationship is called silent
            for a window it carried nothing in *and* whose typical learned counterpart carried
            traffic. This is not raised to hide a duration-mismatch flood.
        min_edge_commands: Fewest commands a learned link must have carried before its absence
            counts as anything. Below it there is no occupancy worth the name, and reporting the
            absence of a link seen twice in a whole capture would manufacture a finding out of a
            sampling accident. Do not raise this to quiet D2.
    """

    model_config = ConfigDict(frozen=True)

    window: timedelta = DEFAULT_GRAPH_HORIZON
    min_edge_commands: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.window <= timedelta(0):
            raise ValueError(f"window must be positive, not {self.window}")
        return self


def compare_to_graph(
    graph: DeviceCommandGraph,
    results: Iterable[DissectionResult],
    policy: GraphComparePolicy | None = None,
    stats: CommandStreamStats | None = None,
) -> list[Observation]:
    """Compare live traffic against a learned graph and report where the structure differs.

    Args:
        graph: What normal looked like. Should have been learned from a *different* corpus than
            the one being compared; learning and comparing on the same traffic can only ever
            report that nothing changed.
        results: The live stream, consumed whole.
        policy: How to slice, and how much learned traffic an expectation needs.
        stats: Optional accumulator for everything that was not a command.

    Returns:
        The findings, ordered by ``(window start, issuer, target, feature)``. Empty when nothing
        differs — and also when the live stream spans less than one whole window, which is not the
        same thing and is logged rather than passed off as agreement.

    Note:
        A relationship that is *both* unknown and carrying an unfamiliar function code is reported
        only as unknown. The whole link is new, so the function code is not a second finding; two
        observations there would count one change twice for anything that later weighs them.
    """
    policy = policy or GraphComparePolicy()
    materialised = list(results)
    events = list(command_events(materialised, stats))

    span = stream_span(materialised)
    if span is None:
        return []
    windows = tile_windows(span[0], span[1], policy.window)
    if not windows:
        logger.warning(
            "live traffic spans %s, less than one %s window: no relationship can be compared, and "
            "reporting nothing found would read as agreement",
            span[1] - span[0],
            policy.window,
        )
        return []

    live = _bucket_by_window(events, windows)
    expected = _expected_per_window(graph, policy, span)

    observations: list[Observation] = []
    for window, active in zip(windows, live, strict=True):
        for pair in sorted(active):
            observations.extend(_judge_active(graph, window, pair, active[pair]))
        observations.extend(_judge_silent(graph, window, active, expected))

    observations.sort(key=lambda o: (o.timestamp, o.entity_ids[0], o.entity_ids[1], o.feature))
    logger.info(
        "compared %d command(s) against a graph of %d relationship(s): %d finding(s)",
        len(events),
        len(graph.edges),
        len(observations),
    )
    return observations


def _bucket_by_window(
    events: Sequence[CommandEvent], windows: Sequence[Window]
) -> list[dict[_Pair, list[CommandEvent]]]:
    """Group events by window and then by relationship, in a deterministic order."""
    live: list[dict[_Pair, list[CommandEvent]]] = [{} for _ in windows]
    ordered = sorted(events, key=lambda e: (e.timestamp, e.source.capture, e.source.frame_index))
    for event in ordered:
        index = window_index(event.timestamp, windows)
        if index is None:
            continue
        live[index].setdefault((event.issuer, event.target), []).append(event)
    return live


@dataclass(frozen=True)
class _HorizonExpectation:
    """What a comparable stretch of the learned graph carried for one edge."""

    expected: float
    typical: float
    learned_seconds: float
    horizon_seconds: float
    live_seconds: float


@dataclass(frozen=True)
class _SilenceBaseline:
    """Per-edge comparable-stretch expectations plus the live capture's span."""

    per_edge: dict[_Pair, _HorizonExpectation]
    live_span: tuple[datetime, datetime]

    def get(self, pair: _Pair) -> _HorizonExpectation | None:
        """Return the comparable-stretch expectation for ``pair``, or ``None``."""
        return self.per_edge.get(pair)


def _place_in_bins(timestamps: Sequence[datetime], bins: Sequence[Window]) -> tuple[int, ...]:
    """Count commands in each occupancy bin.

    The learned span is a closed interval ``[earliest, latest]`` while bins are half-open, so a
    command sitting on the last bin's exclusive end — the instant that *defines* the span — is
    folded into that last comparable stretch rather than dropped.
    """
    if not bins:
        return ()
    counts = [0] * len(bins)
    last = len(bins) - 1
    end = bins[last].end
    for moment in timestamps:
        index = window_index(moment, bins)
        if index is None and moment == end:
            index = last
        if index is not None:
            counts[index] += 1
    return tuple(counts)


def _counts_for_horizon(
    counts: tuple[int, ...], native: timedelta, wanted: timedelta
) -> tuple[int, ...]:
    """Resample occupancy bins to stretches matching ``wanted``.

    Returns empty when ``wanted`` is not an integer multiple of the learned bin, because a
    comparable stretch cannot be invented from coarser occupancy.
    """
    if not counts or native <= timedelta(0) or wanted <= timedelta(0):
        return ()
    if wanted == native:
        return counts
    ratio = wanted / native
    steps = round(ratio)
    if steps < 1 or abs(ratio - steps) > 1e-9:
        logger.debug(
            "cannot form a comparable stretch of %s from occupancy bins of %s", wanted, native
        )
        return ()
    usable = len(counts) - len(counts) % steps
    return tuple(sum(counts[index : index + steps]) for index in range(0, usable, steps))


def _context_number(value: float) -> str:
    """Render a span or count as a stable observation-context string."""
    if value == int(value):
        return str(int(value))
    return f"{value:.6g}"


def _expected_per_window(
    graph: DeviceCommandGraph,
    policy: GraphComparePolicy,
    live_span: tuple[datetime, datetime],
) -> _SilenceBaseline:
    """Return how many commands each learned link should carry in a comparable stretch.

    A live window of duration ``policy.window`` is judged against stretches of that same duration
    inside the learned graph, not against a rate whose only denominator is the entire train span.
    Links below ``min_edge_commands`` are absent from the result, and so is every link when the
    learned span is missing or has zero length: a rate over zero seconds is not a large number, it
    is not a number, and a graph learned from a single instant can support no expectation at all.
    """
    if graph.learned_span is None:
        return _SilenceBaseline(per_edge={}, live_span=live_span)
    learned_seconds = (graph.learned_span[1] - graph.learned_span[0]).total_seconds()
    if learned_seconds <= 0.0:
        logger.debug("graph learned over a zero-length span: no silence can be expected")
        return _SilenceBaseline(per_edge={}, live_span=live_span)
    window_seconds = policy.window.total_seconds()
    live_seconds = (live_span[1] - live_span[0]).total_seconds()
    per_edge: dict[_Pair, _HorizonExpectation] = {}
    for edge in graph.edges:
        if edge.command_count < policy.min_edge_commands:
            continue
        counts = _counts_for_horizon(edge.horizon_counts, graph.horizon, policy.window)
        if counts:
            expected_count = sum(counts) / len(counts)
            typical_count = float(median(counts))
        else:
            expected_count = edge.command_count / learned_seconds * window_seconds
            typical_count = expected_count
        per_edge[edge.pair] = _HorizonExpectation(
            expected=expected_count,
            typical=typical_count,
            learned_seconds=learned_seconds,
            horizon_seconds=window_seconds,
            live_seconds=live_seconds,
        )
    return _SilenceBaseline(per_edge=per_edge, live_span=live_span)


def _judge_active(
    graph: DeviceCommandGraph,
    window: Window,
    pair: _Pair,
    events: Sequence[CommandEvent],
) -> list[Observation]:
    """Report what is unusual about a relationship that carried traffic in this window."""
    issuer, target = pair
    edge = graph.edge(issuer, target)
    if edge is None:
        codes = sorted({event.function_code for event in events})
        return [
            _finding(
                UNKNOWN_COMMAND_RELATIONSHIP,
                float(len(events)),
                window,
                pair,
                events,
                {"function_codes": ",".join(str(code) for code in codes)},
            )
        ]

    learned = set(edge.function_codes)
    findings: list[Observation] = []
    for code in sorted({event.function_code for event in events} - learned):
        matching = [event for event in events if event.function_code == code]
        findings.append(
            _finding(
                UNEXPECTED_COMMAND_FUNCTION,
                float(len(matching)),
                window,
                pair,
                matching,
                {
                    "function_code": str(code),
                    "function_name": matching[0].function_name,
                    "learned_function_codes": ",".join(
                        str(learned_code) for learned_code in edge.function_codes
                    ),
                },
            )
        )
    return findings


def _judge_silent(
    graph: DeviceCommandGraph,
    window: Window,
    active: Mapping[_Pair, Sequence[CommandEvent]],
    expected: _SilenceBaseline,
) -> list[Observation]:
    """Report every learned relationship that carried nothing in this window.

    Absence is a finding only when a typical comparable stretch of the learned graph carried at
    least one command. A stretch that is usually empty is the duration mismatch, not silence.
    """
    findings: list[Observation] = []
    learned_span = graph.learned_span
    if learned_span is None:
        return findings
    live_start, live_end = expected.live_span
    for edge in graph.edges:
        if edge.pair in active:
            continue
        horizon = expected.get(edge.pair)
        if horizon is None:
            continue
        if horizon.typical < _TYPICAL_SILENCE_FLOOR:
            continue
        findings.append(
            Observation(
                entity_ids=[edge.issuer, edge.target],
                feature=SILENT_COMMAND_RELATIONSHIP,
                value=horizon.expected,
                timestamp=window.start,
                domain=Domain.ATLAS,
                context={
                    "issuer_ip": edge.issuer_ip,
                    "target_ip": edge.target_ip,
                    "window_start": window.start.isoformat(),
                    "window_end": window.end.isoformat(),
                    "observed_command_count": "0",
                    "learned_command_count": str(edge.command_count),
                    "learned_function_codes": ",".join(str(c) for c in edge.function_codes),
                    # Present by construction: `expected` is empty without a span, so nothing
                    # reaches here unless the graph recorded the period it learned over.
                    "learned_span_start": learned_span[0].isoformat(),
                    "learned_span_end": learned_span[1].isoformat(),
                    "learned_span_seconds": _context_number(horizon.learned_seconds),
                    "live_span_start": live_start.isoformat(),
                    "live_span_end": live_end.isoformat(),
                    "live_span_seconds": _context_number(horizon.live_seconds),
                    "horizon_seconds": _context_number(horizon.horizon_seconds),
                    "typical_learned_count": _context_number(horizon.typical),
                    # There are no live frames — that absence *is* the finding — so provenance
                    # points at the corpus the expectation was learned from instead.
                    "frames": edge.frames,
                    "frame_count": str(edge.command_count),
                },
            )
        )
    return findings


def _finding(
    feature: str,
    value: float,
    window: Window,
    pair: _Pair,
    evidence: Sequence[CommandEvent],
    extra: Mapping[str, str],
) -> Observation:
    """Build one relationship finding, traceable to the frames that justify it."""
    issuer, target = pair
    context = {
        "issuer_ip": evidence[0].issuer_ip,
        "target_ip": evidence[0].target_ip,
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "frames": frame_ranges(evidence),
        "frame_count": str(len(evidence)),
        "protocol": ",".join(sorted({event.protocol for event in evidence})),
        **extra,
    }
    return Observation(
        entity_ids=[issuer, target],
        feature=feature,
        value=value,
        timestamp=window.start,
        domain=Domain.ATLAS,
        context=context,
    )


def render_graph(graph: DeviceCommandGraph) -> str:
    """Render a complete, human-readable listing of a learned graph.

    This is the audit path, and it matters more here than the numbers do. A learned graph is only
    as good as an engineer's ability to look at it and say "that workstation should not be talking
    to that PLC at all" — and finding *that* in the baseline is worth more than any comparison run
    against it afterwards.

    Args:
        graph: The graph to render.

    Returns:
        A multi-line listing, deterministic for a given graph.
    """
    lines = [
        f"{len(graph.edges)} command relationship(s) among {len(graph.devices)} device(s), "
        f"learned from {graph.command_count} command(s)"
    ]
    if not graph.edges:
        lines.append("  (no command relationships observed)")
    for edge in graph.edges:
        codes = ", ".join(f"fn {code}" for code in edge.function_codes)
        lines.append("")
        lines.append(f"  {edge.issuer_ip} -> {edge.target_ip}")
        lines.append(f"    commands: {edge.command_count} over [{codes}]")
        lines.append(f"    seen: {edge.first_seen.isoformat()} .. {edge.last_seen.isoformat()}")
        lines.append(f"    frames: {edge.frames}")
    return "\n".join(lines)
