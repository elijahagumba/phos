"""Score ADR 0146's six identity features apart from the frozen 34.

The register is an input. This module does not fill it, does not read labels,
and does not weight `PEER_FEATURES`. An empty register matches nothing, so every
count it emits is zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from phos.ontology import Observation
from phos.sentiel.entities import EntityCatalogue
from phos.sentiel.events import (
    DETAIL_PC,
    DETAIL_RECIPIENTS,
    DETAIL_URL,
    DETAIL_URL_HOST,
    DETAIL_VALUE_SEPARATOR,
    EnterpriseEvent,
    EventKind,
)
from phos.sentiel.named_counterparties import (
    IDENTITY_FEATURES,
    MATCHED_IDENTITIES,
    REGISTER_SHA256,
    DeclaredIdentities,
    IdentityFeaturiser,
    register_sha256,
)
from phos.sentiel.traces import EntityDayTrace

__all__ = [
    "EMPTY_REGISTER_SHA256",
    "directory_destination_register",
    "events_from_trace",
    "score_traces",
    "summarise_identity",
    "summarise_traces",
]

EMPTY_REGISTER_SHA256: str = register_sha256(DeclaredIdentities())
"""Hash of the empty register. ADR 0146 ships the register empty."""


def directory_destination_register(catalogue: EntityCatalogue) -> DeclaredIdentities:
    """Return the directory's own email addresses, and nothing else.

    Hosts and machines stay empty. The names are the organisation chart, not a
    labelled insider's traffic and not a web host from an activity log. An
    address the directory does not hold is not invented. Building this does not
    read ``insiders.csv``.

    Args:
        catalogue: Users read from a CERT LDAP directory.

    Returns:
        A register whose destinations are those email addresses.
    """
    destinations = {
        email
        for entity in catalogue.entities.values()
        if (email := entity.attributes.get("email", "").strip())
    }
    return DeclaredIdentities(destinations=frozenset(destinations))


def events_from_trace(trace: EntityDayTrace) -> Iterator[EnterpriseEvent]:
    """Yield the hosts, recipients and machines on one cached person-day.

    The cache already holds those sets. Replaying them is how the identity
    featuriser sees the same names the 34 counted, without a second corpus read.
    Every event shares the window timestamp, which is non-decreasing across a
    cache that is already in day order.

    Args:
        trace: One entity-day.

    Yields:
        At least one event, so an active day still emits the six features.
    """
    when = trace.day
    pc = trace.pcs[0] if trace.pcs else ""
    emitted = False
    for host in trace.hosts:
        emitted = True
        yield EnterpriseEvent(
            timestamp=when,
            user_id=trace.user_id,
            event_kind=EventKind.HTTP_REQUEST,
            details={DETAIL_URL_HOST: host, DETAIL_URL: f"http://{host}/", DETAIL_PC: pc},
        )
    if trace.recipients:
        emitted = True
        yield EnterpriseEvent(
            timestamp=when,
            user_id=trace.user_id,
            event_kind=EventKind.EMAIL_SEND,
            details={
                DETAIL_RECIPIENTS: DETAIL_VALUE_SEPARATOR.join(trace.recipients),
                DETAIL_PC: pc,
            },
        )
    for machine in trace.pcs:
        emitted = True
        yield EnterpriseEvent(
            timestamp=when,
            user_id=trace.user_id,
            event_kind=EventKind.LOGON,
            details={DETAIL_PC: machine},
        )
    if not emitted:
        yield EnterpriseEvent(
            timestamp=when,
            user_id=trace.user_id,
            event_kind=EventKind.LOGON,
            details={},
        )


def score_traces(
    traces: Iterable[EntityDayTrace],
    register: DeclaredIdentities | None = None,
) -> list[Observation]:
    """Run `IdentityFeaturiser` over ``traces`` with ``register``.

    Args:
        traces: Person-days in non-decreasing day order.
        register: Declared names. ``None`` is the empty register.

    Returns:
        The six-feature observations.
    """
    identities = DeclaredIdentities() if register is None else register
    featuriser = IdentityFeaturiser(identities=identities)

    def events() -> Iterator[EnterpriseEvent]:
        for trace in traces:
            yield from events_from_trace(trace)

    return featuriser.observations(events())


def summarise_traces(
    traces: Iterable[EntityDayTrace],
    register: DeclaredIdentities | None = None,
) -> dict[str, object]:
    """Summarise `IdentityFeaturiser` over ``traces`` without retaining every observation.

    Args:
        traces: Person-days in non-decreasing day order.
        register: Declared names. ``None`` is the empty register.
    """
    identities = DeclaredIdentities() if register is None else register
    featuriser = IdentityFeaturiser(identities=identities)

    def events() -> Iterator[EnterpriseEvent]:
        for trace in traces:
            yield from events_from_trace(trace)

    return summarise_identity(featuriser.stream(events()))


def summarise_identity(observations: Iterable[Observation]) -> dict[str, object]:
    """Return the sum and max of each identity feature, and whether every value is zero.

    Args:
        observations: Observations emitted by `IdentityFeaturiser`.

    Returns:
        A JSON-ready summary. It does not contain a confidence. ``destinations_named``
        counts destination observations that carried at least one matched address.
        The addresses themselves are not copied into the summary.

    Raises:
        ValueError: If an observation is not one of the six features, or the
            observations name more than one register hash.
    """
    totals = dict.fromkeys(IDENTITY_FEATURES, 0.0)
    maxima = dict.fromkeys(IDENTITY_FEATURES, 0.0)
    counts = dict.fromkeys(IDENTITY_FEATURES, 0)
    hashes: set[str] = set()
    destinations_named = 0
    for observation in observations:
        if observation.feature not in totals:
            raise ValueError(f"not an identity feature: {observation.feature}")
        totals[observation.feature] += observation.value
        maxima[observation.feature] = max(maxima[observation.feature], observation.value)
        counts[observation.feature] += 1
        hashes.add(observation.context.get(REGISTER_SHA256, ""))
        if observation.feature == "declared_destination_count" and observation.context.get(
            MATCHED_IDENTITIES, ""
        ):
            destinations_named += 1
    if len(hashes) > 1:
        raise ValueError(f"observations name more than one register: {sorted(hashes)}")
    return {
        "features": {
            name: {"n": counts[name], "sum": totals[name], "max": maxima[name]}
            for name in IDENTITY_FEATURES
        },
        "all_zero": all(value == 0.0 for value in totals.values()) and all(counts.values()),
        "n_observations": sum(counts.values()),
        "register_sha256": next(iter(hashes)) if hashes else None,
        "destinations_named": destinations_named,
    }
