"""Turning enterprise events into per-user behaviour: the starter counts, and what they cannot see.

An `EnterpriseEvent` is a fact; a behavioural model needs a *quantity*. This module aggregates the
event stream into ontology `Observation`s, one per ``(user, day, feature)``, which is the shape
`phos.models` already knows how to baseline and `phos.eval` already knows how to score.

**This is a starter set and the code says so.** Eight features, all of them classic UEBA counts,
all of them describing one user in isolation:

| Feature | What it is | The CERT scenario it exists for |
| --- | --- | --- |
| ``logon_count`` | Logons in the day | Baseline activity level |
| ``distinct_pcs`` | Machines touched | 3, 4 — using someone else's machine |
| ``off_hours_logon_count`` | Logons outside working hours | 1 — "begins logging in after hours" |
| ``removable_device_connects`` | Thumb-drive connects | 1, 2, 3 — data theft to removable media |
| ``file_access_count`` | Files touched | 2, 4 — bulk collection |
| ``distinct_files`` | Distinct files touched | 4 — "searches for interesting files" |
| ``external_email_count`` | Mails with a recipient outside the org | 3, 4 — mailing data home |
| ``distinct_http_hosts`` | Distinct web hosts visited | 1, 2, 5 — wikileaks, job sites, dropbox |

PART 6A adds a second, richer set beside it. `FeatureSet` selects between them and the starter set
remains the default, so every existing caller — and the PART 6·D baseline that must stay
reproducible for the comparison to mean anything — is unaffected.

The enriched set keeps all eight starter counts and adds three families, in the priority order
PART 6A sets out:

1. **Baseline-relative** (`*_dev`) — each starter count re-expressed as a signed z-score against
   that same user's own trailing history (`phos.sentiel.history`). This is the enrichment that
   matters most: an insider's tell is rarely "did a thing", it is "did markedly more of a thing
   than they ever do", and a raw count cannot say that.
2. **Temporal** (`*_diff`, `*_trend`) — the movement of a level rather than the level. Applied to
   the three signals CERT's own scenario descriptions frame as an onset or an escalation.
3. **First-order relationship** — per-entity summaries of who and what a user connects to,
   including counts of counterparties that are new *for that user*.

Every one of them is computed from a single user's own events and own history. Nothing here reads
another user to answer a question about this one: peer-group baselining is PART 6B, and keeping the
boundary out of this layer is what makes it testable rather than merely asserted.

Aggregation is single-pass and streaming. Events arrive in non-decreasing timestamp order, so once
a later day is seen every earlier day is complete and can be emitted and dropped. Peak memory is
one day of per-user accumulators plus a bounded trailing history per user, not the corpus.
"""

import logging
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import Domain, Observation
from phos.sentiel.entities import user_entity_id
from phos.sentiel.evaluation import SENTIEL_CAVEATS
from phos.sentiel.events import (
    DETAIL_FILENAME,
    DETAIL_PC,
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_RECIPIENTS,
    DETAIL_URL_HOST,
    DETAIL_VALUE_SEPARATOR,
    EnterpriseEvent,
    EventKind,
)
from phos.sentiel.history import HistoryPolicy, TrailingHistory
from phos.sentiel.peers import PeerGroups, PeerHistory

__all__ = [
    "BASELINE_RELATIVE_FEATURES",
    "COUNTERPARTY_KINDS",
    "ENRICHED_CAVEATS",
    "ENRICHED_FEATURES",
    "ONSET_SIGNALS",
    "PEER_CAVEATS",
    "PEER_FEATURES",
    "PEER_RELATIVE_FEATURES",
    "RELATIONSHIP_FEATURES",
    "STARTER_FEATURES",
    "SUPERSEDED_CAVEAT_MARKER",
    "SUPERSEDED_ENRICHED_MARKERS",
    "TEMPORAL_FEATURES",
    "FeatureSet",
    "Featuriser",
    "WorkingHours",
    "enriched_source_note",
    "peer_source_note",
]

logger = logging.getLogger(__name__)

STARTER_FEATURES: Final[tuple[str, ...]] = (
    "logon_count",
    "distinct_pcs",
    "off_hours_logon_count",
    "removable_device_connects",
    "file_access_count",
    "distinct_files",
    "external_email_count",
    "distinct_http_hosts",
)
"""The PART 6·D starter features, in the order they are emitted.

Exported so a caller can assert it got what it expected, and so a later PART adding features has
one list to extend rather than a scattering of string literals. PART 6A extends rather than
replaces it: `ENRICHED_FEATURES` opens with exactly this tuple, so the enriched set is a strict
superset and any change in the measured numbers is attributable to what was *added*.
"""

BASELINE_RELATIVE_SUFFIX: Final = "_dev"
DIFFERENCE_SUFFIX: Final = "_diff"
TREND_SUFFIX: Final = "_trend"

BASELINE_RELATIVE_FEATURES: Final[tuple[str, ...]] = tuple(
    f"{feature}{BASELINE_RELATIVE_SUFFIX}" for feature in STARTER_FEATURES
)
"""One signed z-score per starter count, against that user's own trailing history.

Derived from `STARTER_FEATURES` rather than written out, so a starter count can never acquire a
companion by being added to one list and not the other. This is PART 6A's highest-value family:
`file_access_count` says what someone did, `file_access_count_dev` says whether it was unlike them.
"""

ONSET_SIGNALS: Final[tuple[str, ...]] = (
    "off_hours_logon_count",
    "removable_device_connects",
    "file_access_count",
)
"""The starter counts the temporal family is applied to, and why these three.

Not a guess: CERT r3.1's own ``answers/scenarios.txt`` describes its red-team scenarios as onsets
and escalations of exactly these behaviours — a user "who did not previously use removable drives
or work after hours **begins** logging in after hours, using a removable drive" (scenario 1), a user
who uses a thumb drive "**at markedly higher rates than their previous activity**" (scenario 2), and
a user who searches for files and mails them home where "this behavior occurs **more and more
frequently** over a 3 month period" (scenario 4). A level cannot express any of that; a first
difference and a slope can.

The temporal family is deliberately a subset rather than the whole starter set. Each emitted
feature costs roughly 0.34 GB of memory across the real corpus (see ADR 0021) and, because the
baseline models judge every feature independently, each one also adds its own opportunities to
raise a false alarm. `external_email_count` — escalating in scenario 4 alongside the file searches —
was the next candidate and was left out on that budget; its level and its ``_dev`` companion are
still emitted.
"""

TEMPORAL_FEATURES: Final[tuple[str, ...]] = tuple(
    f"{signal}{suffix}" for signal in ONSET_SIGNALS for suffix in (DIFFERENCE_SUFFIX, TREND_SUFFIX)
)
"""A first difference and a trailing slope for each of `ONSET_SIGNALS`."""

RELATIONSHIP_FEATURES: Final[tuple[str, ...]] = (
    "distinct_email_recipients",
    "external_email_ratio",
    "new_pcs",
    "new_counterparties",
)
"""First-order summaries of who and what a user connects to.

**Per-entity summaries of relationships, not peer comparison.** Every one is computed from this
user's own events and this user's own trailing history; none of them reads another user. Peer
comparison is PART 6B and deliberately absent here.

| Feature | What it is | Scenario |
| --- | --- | --- |
| ``distinct_email_recipients`` | Distinct addresses mailed in the window | 3 — a mass email |
| ``external_email_ratio`` | External sends as a share of all sends | 3, 4 — mailing data out |
| ``new_pcs`` | Machines this user has not used recently | 4 — another user's machine |
| ``new_counterparties`` | Recipients and web hosts new to this user | 1, 5 — wikileaks, Dropbox |

Machines are counted apart from recipients and hosts because they answer different questions — a
machine is somewhere a user acts *from*, a recipient or a host is somewhere data can go — and
pooling them would let a steady trickle of new web hosts bury the single new workstation that is
scenario 4's whole tell.
"""

ENRICHED_FEATURES: Final[tuple[str, ...]] = (
    STARTER_FEATURES + RELATIONSHIP_FEATURES + BASELINE_RELATIVE_FEATURES + TEMPORAL_FEATURES
)
"""The PART 6A feature set: every starter count, plus the three enrichment families.

A strict superset of `STARTER_FEATURES`, in emission order. Twenty-six features rather than the
exhaustive cross-product of every family with every count, which would be over fifty: see ADR 0021
for the memory arithmetic and the multiplicity argument that bound it, and for what was left out.
"""

PEER_RELATIVE_SUFFIX: Final = "_peer"

PEER_RELATIVE_FEATURES: Final[tuple[str, ...]] = tuple(
    f"{feature}{PEER_RELATIVE_SUFFIX}" for feature in STARTER_FEATURES
)
"""One signed z-score per starter count, against the entity's **peers** rather than their own past.

Derived from `STARTER_FEATURES` for the same reason `BASELINE_RELATIVE_FEATURES` is, and applied to
exactly the same eight counts, which is a rule rather than a selection: every quantity that has a
level has a peer level, and choosing a subset would have to be justified feature by feature. The
enrichments are **not** given peer companions — a ``_dev`` is already a difference and comparing one
person's difference to their peers' differences is a second-order question that would cost the
multiplicity ADR 0021 measured without answering anything this PART asked.

Each is computed leave-one-out, so the distribution an entity is judged against is made of *other
people*: without that the family would be part self-baseline and collinear with the ``_dev`` family
beside it. See `phos.sentiel.peers`.
"""

PEER_FEATURES: Final[tuple[str, ...]] = ENRICHED_FEATURES + PEER_RELATIVE_FEATURES
"""The PART 6B feature set: the whole PART 6A set, plus a peer companion for each starter count.

A strict superset of `ENRICHED_FEATURES` and therefore of `STARTER_FEATURES`, in emission order, so
a change in the measured numbers is attributable to what was *added*. Thirty-four features.

Unlike every other family here, these are **not emitted for every user**: an entity with no declared
group attribute, or one whose group has fewer members than `phos.sentiel.peers.PeerPolicy` requires,
emits none of them at all. That is deliberate and is not a cold start — see `phos.sentiel.peers`.
"""

COUNTERPARTY_PC: Final = "pc"
COUNTERPARTY_EXTERNAL: Final = "counterparty"

COUNTERPARTY_KINDS: Final[tuple[str, ...]] = (COUNTERPARTY_PC, COUNTERPARTY_EXTERNAL)
"""The counterparty memories `phos.sentiel.history` keeps per user, kept separate on purpose."""


class FeatureSet(str, Enum):
    """Which set of features a `Featuriser` emits.

    ``str``-backed so it serialises to readable JSON and can be written straight into
    ``Observation.context["feature_set"]``, which is where a stored observation records the set it
    came from. The values are the names PART 6·D already stamped there, so an enriched corpus is
    distinguishable from a starter one by inspection rather than by reconstruction.
    """

    STARTER = "sentiel-starter-v1"
    ENRICHED = "sentiel-enriched-v1"
    PEER = "sentiel-peer-v1"

    @property
    def features(self) -> tuple[str, ...]:
        """Return the features this set emits, in emission order.

        For `FeatureSet.PEER` this is the widest set a user *may* receive; a user with no usable
        peer group receives the `ENRICHED_FEATURES` prefix of it and nothing else. See
        `PEER_FEATURES`.
        """
        if self is FeatureSet.STARTER:
            return STARTER_FEATURES
        if self is FeatureSet.ENRICHED:
            return ENRICHED_FEATURES
        return PEER_FEATURES

    @property
    def needs_history(self) -> bool:
        """Return whether this set needs a per-entity `TrailingHistory` to be computed."""
        return self is not FeatureSet.STARTER

    @property
    def needs_peers(self) -> bool:
        """Return whether this set needs declared peer groups to be computed."""
        return self is FeatureSet.PEER


SUPERSEDED_CAVEAT_MARKER: Final = "per-entity STARTER set"
"""The phrase identifying the one `phos.sentiel.SENTIEL_CAVEATS` entry an enriched run outdates.

PART 6·D's second caveat asserts that the featurisation is the eight-count starter set with no
relationship context. Half of it is still true — there is still no peer context — and half of it
stops being true the moment an enriched run is logged. `enriched_source_note` therefore drops that
one entry and states both halves correctly in `ENRICHED_CAVEATS`, rather than editing the constant:
PART 6A must not modify the entity-aware evaluation, and a source note that carried both claims
would be a note that contradicts itself.

A test asserts this marker still matches exactly one entry, so if a later PART rewrites that caveat
the substitution fails loudly instead of silently stamping a stale claim onto every report.
"""

ENRICHED_CAVEATS: Final[tuple[str, ...]] = (
    "The featurisation is the PART 6A ENRICHED per-entity set: 26 features over a one-day window "
    "— the 8 starter counts, a signed z-score of each against that user's own trailing history, a "
    "first difference and a trailing slope for the 3 signals CERT's own scenario descriptions "
    "frame as an onset or escalation, and 4 first-order relationship summaries. This SUPERSEDES "
    "the starter-set caveat carried by phos.sentiel.SENTIEL_CAVEATS.",
    "Still NO PEER CONTEXT. Every feature is computed from one user's own events and one user's "
    "own history. The insider who is unremarkable against their own past and remarkable against "
    "their team's is still invisible, and that is the class PART 6B exists to catch. Richer "
    "per-entity features are not a substitute for it and this run does not test it.",
    "BASELINE-RELATIVE FEATURES OVERFIT A SHORT HISTORY. A user barely past the cold-start "
    "boundary has a trailing mean and spread estimated from a handful of windows, so their "
    "deviations swing on little evidence. The cold-start policy makes the boundary explicit — "
    "every baseline-relative read is a documented neutral 0.0 until the history is long enough — "
    "but the windows just past it are noisy and are counted like any other.",
    "ONLY 2 USERS are labelled malicious in r3.1, so window recall can take only the values 0, 0.5 "
    "and 1.0. It is not independently quotable and must not be read as a continuous rate. "
    "Precision, and its multiple over the trivial alert-on-everything floor, are the honest "
    "headline.",
)
"""The four things PART 6A §6 requires to travel with every enriched number.

Data rather than prose in a docstring so `enriched_source_note` can stamp them onto every report
and a test can assert they are present.
"""


SUPERSEDED_ENRICHED_MARKERS: Final[tuple[str, ...]] = (
    "PART 6A ENRICHED per-entity set",
    "Still NO PEER CONTEXT",
)
"""The `ENRICHED_CAVEATS` entries a PART 6B run outdates, matched by substring.

The first describes a 26-feature per-entity set and this one emits 34 with peer companions; the
second says there is no peer context at all, which is the sentence 6B exists to delete. The other
two enriched caveats — short baseline-relative histories being noisy, and two labelled insiders
making recall unquotable — are as true here as they were there and are carried forward unchanged.

Substituting rather than editing follows ADR 0021 Decision 8: the constants belong to earlier PARTs
and their tests, and a source note asserting both "26 features" and "34 features" would be one no
reader could trust. A test asserts each marker still matches **exactly one** entry, so if a later
PART rewrites those caveats the substitution fails loudly instead of stamping a stale claim onto
every report.
"""

PEER_CAVEATS: Final[tuple[str, ...]] = (
    "The featurisation is the PART 6B PEER set: 34 features over a one-day window — the whole 26-"
    "feature PART 6A enriched set, plus a signed z-score of each of the 8 starter counts against "
    "the entity's PEER GROUP, computed leave-one-out so the distribution is made of other people. "
    "This SUPERSEDES the 26-feature and no-peer-context caveats carried by ENRICHED_CAVEATS.",
    "PEER GROUPS ARE DECLARED, NOT INFERRED. They are cut from one attribute of the corpus's own "
    "LDAP directory, never from behaviour: a group derived from how people act would define normal "
    "using the very anomaly being hunted. The consequence is that peer coverage is PARTIAL — a "
    "user absent from the directory, carrying no value for the grouping attribute, or in a group "
    "below the minimum size emits NO peer feature at all, and is judged on the 26 per-entity "
    "features alone. The run's own grouping summary states how many users that was.",
    "THE ALERT UNIT CHANGED. This run scores one alert per ENTITY-WINDOW, aggregated across every "
    "feature, where PARTs 6·D and 6A scored one alert per FEATURE per entity-window. A threshold "
    "therefore means a different thing here and the numbers are NOT comparable to those runs at a "
    "fixed threshold; they are comparable at a matched ALERT BUDGET, which is the constraint an "
    "analyst actually has, and every comparison in this report is made that way.",
    "THE AGGREGATE SCORE IS UNCALIBRATED. It is a sum of bounded per-feature evidence weights, "
    "squashed to [0,1] for the confidence field by the same monotone function PART 3 uses. It is "
    "not a probability that an insider was present and must not be shown to a user as one "
    "(Constitution §3.3). The reported calibration error is a measurement of that fact, not a "
    "claim about it.",
)
"""The four things PART 6B requires to travel with every peer-set number.

Data rather than prose in a docstring so `peer_source_note` can stamp them onto every report and a
test can assert they are present.
"""


def enriched_source_note(prefix: str, base_rate: str = "") -> str:
    """Return a `Dataset.source_note` for an enriched run, with every caveat that still holds.

    The PART 6·D caveats are reused rather than restated, minus the one `SUPERSEDED_CAVEAT_MARKER`
    identifies as outdated by this feature set, plus `ENRICHED_CAVEATS`.

    Args:
        prefix: Provenance for this particular corpus — release, files, split, feature count.
        base_rate: How many user-windows are malicious versus benign, when known.

    Returns:
        One string, suitable for `Dataset.source_note` and therefore copied onto every
        `EvaluationReport` the corpus produces.
    """
    kept = [caveat for caveat in SENTIEL_CAVEATS if SUPERSEDED_CAVEAT_MARKER not in caveat]
    parts = [prefix, *([base_rate] if base_rate else []), *kept, *ENRICHED_CAVEATS]
    return " | ".join(part.strip() for part in parts if part.strip())


def peer_source_note(prefix: str, base_rate: str = "", grouping: str = "") -> str:
    """Return a `Dataset.source_note` for a peer-set run, with every caveat that still holds.

    Both earlier caveat blocks are reused rather than restated, each minus the entries this feature
    set outdates — `SUPERSEDED_CAVEAT_MARKER` from PART 6·D's and `SUPERSEDED_ENRICHED_MARKERS`
    from PART 6A's — plus `PEER_CAVEATS`.

    Args:
        prefix: Provenance for this particular corpus — release, files, split, feature count.
        base_rate: How many user-windows are malicious versus benign, when known.
        grouping: `phos.sentiel.peers.PeerGroups.summary`, so a reader can judge the peer grouping
            rather than assume it. Carried here because a peer number whose grouping is unstated is
            a number nobody can check.

    Returns:
        One string, suitable for `Dataset.source_note` and therefore copied onto every
        `EvaluationReport` the corpus produces.
    """
    kept_starter = [caveat for caveat in SENTIEL_CAVEATS if SUPERSEDED_CAVEAT_MARKER not in caveat]
    kept_enriched = [
        caveat
        for caveat in ENRICHED_CAVEATS
        if not any(marker in caveat for marker in SUPERSEDED_ENRICHED_MARKERS)
    ]
    parts = [
        prefix,
        *([base_rate] if base_rate else []),
        *([grouping] if grouping else []),
        *kept_starter,
        *kept_enriched,
        *PEER_CAVEATS,
    ]
    return " | ".join(part.strip() for part in parts if part.strip())


_CERT_ORG_DOMAIN: Final = "dtaa.com"
"""The fictional organisation every CERT release is set inside.

A default, not a constant to rely on: `Featuriser.org_domains` is configurable, and
`EntityCatalogue.dominant_email_domain` reads the real answer off the corpus's own directory,
which is what ``scripts/evaluate_sentiel_baseline.py`` passes.
"""


class WorkingHours(BaseModel):
    """When the organisation considers itself open.

    "Off-hours" is not a property of a timestamp; it is a property of a timestamp *and* a working
    pattern, so the pattern is data rather than a magic number buried in a comparison.

    Attributes:
        start_hour: First hour of the working day, inclusive. Default 8.
        end_hour: Hour at which the working day ends, exclusive. Default 18, so 17:59 is inside
            working hours and 18:00 is not.
        workdays: Weekday numbers that are working days, Monday being 0 — `datetime.weekday`'s
            convention. Default Monday to Friday, so all weekend activity is off-hours.
    """

    model_config = ConfigDict(frozen=True)

    start_hour: int = Field(default=8, ge=0, le=23)
    end_hour: int = Field(default=18, ge=1, le=24)
    workdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})

    def contains(self, when: datetime) -> bool:
        """Return whether ``when`` falls inside working hours on a working day."""
        return when.weekday() in self.workdays and self.start_hour <= when.hour < self.end_hour


class _Accumulator:
    """One user's counters and distinct-value sets within one window.

    A plain mutable class rather than a frozen model: it is written once per event over tens of
    millions of events, and it never leaves this module.
    """

    __slots__ = (
        "distinct_files",
        "distinct_hosts",
        "distinct_pcs",
        "emails",
        "external_emails",
        "file_accesses",
        "logons",
        "off_hours_logons",
        "recipients",
        "removable_connects",
    )

    def __init__(self) -> None:
        self.logons = 0
        self.off_hours_logons = 0
        self.removable_connects = 0
        self.file_accesses = 0
        self.emails = 0
        self.external_emails = 0
        self.distinct_pcs: set[str] = set()
        self.distinct_files: set[str] = set()
        self.distinct_hosts: set[str] = set()
        self.recipients: set[str] = set()

    def add(
        self, event: EnterpriseEvent, working_hours: WorkingHours, org_domains: frozenset[str]
    ) -> None:
        """Fold one event into the running counts."""
        if pc := event.details.get(DETAIL_PC, ""):
            self.distinct_pcs.add(pc)

        if event.event_kind is EventKind.LOGON:
            self.logons += 1
            if not working_hours.contains(event.timestamp):
                self.off_hours_logons += 1
        elif event.event_kind is EventKind.DEVICE_CONNECT:
            self.removable_connects += 1
        elif event.event_kind is EventKind.FILE_ACCESS:
            self.file_accesses += 1
            if filename := event.details.get(DETAIL_FILENAME, ""):
                self.distinct_files.add(filename)
        elif event.event_kind is EventKind.HTTP_REQUEST:
            if host := event.details.get(DETAIL_URL_HOST, ""):
                self.distinct_hosts.add(host)
        elif event.event_kind is EventKind.EMAIL_SEND:
            self.emails += 1
            # Lowercased here rather than at the reader: the reader keeps recipients verbatim so a
            # row stays checkable against its source file, and counterparty *identity* is this
            # module's concern. Without it "Bob@dtaa.com" and "bob@dtaa.com" are two people.
            self.recipients.update(
                address.lower()
                for address in event.details.get(DETAIL_RECIPIENTS, "").split(
                    DETAIL_VALUE_SEPARATOR
                )
                if address
            )
            domains = {
                domain
                for domain in event.details.get(DETAIL_RECIPIENT_DOMAINS, "").split(
                    DETAIL_VALUE_SEPARATOR
                )
                if domain
            }
            if domains - org_domains:
                self.external_emails += 1

    def values(self) -> tuple[float, ...]:
        """Return this window's feature values, in `STARTER_FEATURES` order."""
        return (
            float(self.logons),
            float(len(self.distinct_pcs)),
            float(self.off_hours_logons),
            float(self.removable_connects),
            float(self.file_accesses),
            float(len(self.distinct_files)),
            float(self.external_emails),
            float(len(self.distinct_hosts)),
        )

    def counterparties(self) -> dict[str, frozenset[str]]:
        """Return this window's counterparties, keyed by `COUNTERPARTY_KINDS`.

        This is what `TrailingHistory.observe` remembers, and therefore what "new for this user"
        is measured against in later windows.
        """
        return {
            COUNTERPARTY_PC: frozenset(self.distinct_pcs),
            COUNTERPARTY_EXTERNAL: frozenset(self.recipients | self.distinct_hosts),
        }

    def enriched_values(
        self, user_id: str, history: TrailingHistory, starter: tuple[float, ...]
    ) -> tuple[float, ...]:
        """Return this window's values in `ENRICHED_FEATURES` order.

        Args:
            user_id: The corpus's own identifier for the user.
            history: This user's trailing history, holding **only** windows before this one. It is
                read here and advanced by the caller afterwards; see `Featuriser._flush`.
            starter: This window's `values`, passed in rather than recomputed so the same numbers
                are emitted as levels and used as the basis of every enrichment.

        Returns:
            The starter values, the relationship summaries, one deviation per starter count, and
            the temporal terms for `ONSET_SIGNALS` — concatenated in `ENRICHED_FEATURES` order.
        """
        by_feature = dict(zip(STARTER_FEATURES, starter, strict=True))
        relationship = (
            float(len(self.recipients)),
            # A day with no mail at all and a day of purely internal mail both score 0.0: neither
            # sent anything out, which is what the feature is asking about.
            (self.external_emails / self.emails) if self.emails else 0.0,
            history.new_counterparties(user_id, COUNTERPARTY_PC, self.distinct_pcs),
            history.new_counterparties(
                user_id, COUNTERPARTY_EXTERNAL, self.recipients | self.distinct_hosts
            ),
        )
        baseline_relative = tuple(
            history.deviation(user_id, feature, value) for feature, value in by_feature.items()
        )
        temporal = tuple(
            read(user_id, signal, by_feature[signal])
            for signal in ONSET_SIGNALS
            for read in (history.difference, history.trend)
        )
        return starter + relationship + baseline_relative + temporal

    def peer_values(
        self, user_id: str, peers: PeerHistory, starter: tuple[float, ...]
    ) -> tuple[float | None, ...]:
        """Return this window's values in `PEER_RELATIVE_FEATURES` order.

        Args:
            user_id: The corpus's own identifier for the user.
            peers: The peer history, holding **only** windows before this one. It is read here and
                advanced by the caller once the whole window has been emitted; see
                `Featuriser._flush`.
            starter: This window's `values`, so the same numbers are emitted as levels and used as
                the basis of every peer comparison.

        Returns:
            One signed z-score per starter count against the entity's peers, or a tuple of
            ``None`` when the entity has no usable peer group — in which case the caller emits no
            peer observation at all. The answer is all-or-nothing by construction: whether an
            entity has a group is a property of the entity, not of a feature.
        """
        return tuple(
            peers.deviation(user_id, feature, value)
            for feature, value in zip(STARTER_FEATURES, starter, strict=True)
        )

    def observations(
        self,
        user_id: str,
        window_start: datetime,
        window: timedelta,
        feature_set: FeatureSet,
        history: TrailingHistory | None,
        peers: PeerHistory | None = None,
    ) -> Iterator[Observation]:
        """Yield one `Observation` per feature in ``feature_set`` for this user and window.

        Args:
            user_id: The corpus's own identifier for the user.
            window_start: Start of the window, which is the observations' timestamp.
            window: The aggregation window's length, recorded in context.
            feature_set: Which features to emit.
            history: The user's trailing history when ``feature_set`` needs one, otherwise
                ``None``. It is only read here; the caller advances it once the window is emitted.
            peers: The peer history when ``feature_set`` is `FeatureSet.PEER`, otherwise ``None``.
                Read here and advanced by the caller once the **whole window** has been emitted.

        Raises:
            ValueError: If a set is asked for without the history it needs to compute. That would
                silently emit neutral values for every enrichment and report them as measurements.

        Note:
            A feature whose value is ``None`` is **not emitted**. That is how a user with no peer
            group receives the 26 per-entity features and none of the 8 peer ones. Indices in the
            emitted `Observation.id` stay tied to the feature's position in ``feature_set``, so an
            id remains traceable to a named feature whether or not its neighbours were emitted.
        """
        entity_id = user_entity_id(user_id)
        # One dict shared by every observation of this user-window. At tens of millions of
        # observations a per-observation dict is gigabytes of identical strings.
        context = {
            "user_id": user_id,
            "window_seconds": str(int(window.total_seconds())),
            "feature_set": feature_set.value,
        }
        starter = self.values()
        values: tuple[float | None, ...]
        if feature_set is FeatureSet.STARTER:
            values = starter
        elif history is None:
            raise ValueError(
                f"{feature_set.value} needs a trailing history to compute its baseline-relative, "
                "temporal and new-counterparty features; none was given"
            )
        else:
            values = self.enriched_values(user_id, history, starter)
            if feature_set.needs_peers:
                if peers is None:
                    raise ValueError(
                        f"{feature_set.value} needs a peer history to compute its peer-relative "
                        "features; none was given"
                    )
                values = values + self.peer_values(user_id, peers, starter)

        for index, (feature, value) in enumerate(zip(feature_set.features, values, strict=True)):
            if value is None:
                continue
            yield Observation(
                id=_observation_id(user_id, window_start.date(), index),
                entity_ids=[entity_id],
                feature=feature,
                value=value,
                timestamp=window_start,
                domain=Domain.SENTIEL,
                context=context,
            )


class Featuriser(BaseModel):
    """Aggregates an event stream into per-``(user, window)`` ontology `Observation`s.

    Attributes:
        window: Aggregation window. One day by default, which is the granularity CERT's own ground
            truth is usable at and the granularity a SOC triages insider cases at. Windows are
            aligned to midnight UTC.
        working_hours: The pattern ``off_hours_logon_count`` is measured against.
        org_domains: Mail domains that count as internal. A message with any recipient outside
            these is an external mail.
        feature_set: Which features to emit. `FeatureSet.STARTER` by default — deliberately, so
            that every caller written against PART 6·D keeps its behaviour and the 6·D baseline
            stays reproducible from this same code, which is what makes the PART 6A comparison
            like-for-like rather than a comparison of two code paths.
        history_policy: How far back a user's own trailing history reaches, and how far back the
            peer pools reach. One policy for both, so PHOS gives one answer to "how long is
            recent" and "how many points before you may claim a baseline" rather than two. Only
            read when ``feature_set`` needs a history.
        peer_groups: The declared peer groups, required when ``feature_set`` is `FeatureSet.PEER`
            and ignored otherwise. Built from the corpus's own directory by
            `phos.sentiel.peers.PeerGroups.from_catalogue` and passed in rather than derived here,
            because a featuriser that could construct its own groups could construct them from the
            events it is reading, which is the circularity PART 6B refuses.

    Note:
        Only ``window`` values that divide a day evenly are meaningful, because windows are aligned
        to midnight. The default is one day and nothing in this PART changes it.
    """

    model_config = ConfigDict(frozen=True)

    window: timedelta = timedelta(days=1)
    working_hours: WorkingHours = WorkingHours()
    org_domains: frozenset[str] = frozenset({_CERT_ORG_DOMAIN})
    feature_set: FeatureSet = FeatureSet.STARTER
    history_policy: HistoryPolicy = HistoryPolicy()
    peer_groups: PeerGroups | None = None

    @model_validator(mode="after")
    def _check_peer_groups(self) -> Self:
        """Reject a peer feature set with no groups, which would emit no peer feature ever."""
        if self.feature_set.needs_peers and self.peer_groups is None:
            raise ValueError(
                f"feature_set={self.feature_set.value} needs peer_groups; without them every peer "
                "feature would be absent for every user, silently and forever"
            )
        return self

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Return the features this featuriser emits, in emission order."""
        return self.feature_set.features

    def observations(self, events: Iterable[EnterpriseEvent]) -> list[Observation]:
        """Aggregate ``events`` into observations, time-ordered.

        Args:
            events: The event stream, in non-decreasing timestamp order — which is what
                `phos.sentiel.cert.CertReader.events` yields.

        Returns:
            One `Observation` per ``(user, window, feature)``, ordered by window then user then
            the order of `feature_names`, so the result satisfies `Dataset`'s time-ordering
            invariant directly.

        Note:
            A window in which a user did nothing at all produces no observations. A window in
            which they did *something* produces all eight features, zeros included — an absent
            zero would make the learned baseline for a quiet feature a baseline of only the days
            it happened to fire, which is a materially different and much narrower band.
        """
        return list(self.stream(events))

    def stream(self, events: Iterable[EnterpriseEvent]) -> Iterator[Observation]:
        """Yield observations as each window completes, holding only one window in memory.

        Args:
            events: The event stream, in non-decreasing timestamp order.

        Yields:
            Observations, in the same order `observations` returns them.

        Raises:
            ValueError: If the events are not time-ordered, which would let a completed window be
                reopened after it had already been emitted and silently lose its later events.
        """
        buckets: dict[tuple[str, datetime], _Accumulator] = {}
        open_window: datetime | None = None
        previous: datetime | None = None
        emitted = 0
        # Created here rather than held on the model: it is per-run mutable state, and a frozen
        # model that quietly accumulated it would make two runs over one corpus disagree
        # (Constitution §6). Nothing outside this call can reach it.
        history = TrailingHistory(self.history_policy) if self.feature_set.needs_history else None
        peers = (
            PeerHistory(self.peer_groups, STARTER_FEATURES, self.history_policy)
            if self.feature_set.needs_peers and self.peer_groups is not None
            else None
        )

        for event in events:
            if previous is not None and event.timestamp < previous:
                raise ValueError(
                    f"events must be time-ordered; {event.timestamp} follows {previous}. "
                    "Aggregation emits a window as soon as a later one begins, so an out-of-order "
                    "stream would drop events into a window that had already been reported."
                )
            previous = event.timestamp

            window_start = self._window_start(event.timestamp)
            if open_window is not None and window_start > open_window:
                for observation in self._flush(buckets, open_window, history, peers):
                    emitted += 1
                    yield observation
            open_window = window_start
            buckets.setdefault((event.user_id, window_start), _Accumulator()).add(
                event, self.working_hours, self.org_domains
            )

        if open_window is not None:
            for observation in self._flush(buckets, open_window, history, peers):
                emitted += 1
                yield observation
        logger.info(
            "featurised into %d observations across %s windows using %s (%d features)",
            emitted,
            self.window,
            self.feature_set.value,
            len(self.feature_names),
        )

    def _window_start(self, when: datetime) -> datetime:
        """Return the start of the window ``when`` falls in, aligned to midnight UTC."""
        midnight = datetime.combine(when.date(), time.min, tzinfo=UTC)
        if self.window >= timedelta(days=1):
            return midnight
        elapsed = when - midnight
        return midnight + self.window * int(elapsed // self.window)

    def _flush(
        self,
        buckets: dict[tuple[str, datetime], _Accumulator],
        window_start: datetime,
        history: TrailingHistory | None,
        peers: PeerHistory | None = None,
    ) -> Iterator[Observation]:
        """Emit and drop every bucket at or before ``window_start``, oldest user-window first.

        The **ordering here is the causality guarantee**, and there are two of them because there
        are two histories, folded in at two different moments.

        A user's own history is advanced as soon as *that user's* window has been emitted: a window
        is read against it, emitted, and only then folded in. Windows are flushed strictly in time
        order, so the history a window is judged against holds every earlier window of that user
        and no later one. Moving the `TrailingHistory.observe` call above the ``yield from`` would
        let each window into its own baseline and quietly flatten every spike.

        The **peer** history is advanced only once *every* user in the window has been emitted,
        which is why the loop is grouped by window start and `PeerHistory.observe` takes a whole
        window rather than one user. Advancing it per user would put the first user
        of a window into the pool that judges the second user of the same window — a leak with no
        error and no absurd number, which would quietly drag each peer mean toward the very cohort
        being judged. ``TestCausality`` in ``tests/sentiel/test_history.py``, the peer-causality
        tests in ``tests/sentiel/test_peers.py`` and the featurisation causality tests exist to
        catch both.
        """
        ready: dict[datetime, list[str]] = {}
        for user_id, start in sorted(key for key in buckets if key[1] <= window_start):
            ready.setdefault(start, []).append(user_id)

        for start in sorted(ready):
            pending: dict[str, tuple[float, ...]] = {}
            for user_id in ready[start]:
                accumulator = buckets.pop((user_id, start))
                yield from accumulator.observations(
                    user_id, start, self.window, self.feature_set, history, peers
                )
                starter = accumulator.values()
                if history is not None:
                    history.observe(
                        user_id,
                        dict(zip(STARTER_FEATURES, starter, strict=True)),
                        accumulator.counterparties(),
                    )
                if peers is not None:
                    pending[user_id] = starter
            if peers is not None:
                peers.observe(pending)


def _observation_id(user_id: str, day: date, index: int) -> str:
    """Return a deterministic, readable observation id.

    Derived rather than minted, so two runs over the same corpus produce identical ids and an id
    in a report can be traced back to a user and a day (Constitution §3.7).
    """
    return f"obs_{user_id}_{day:%Y%m%d}_{index:02d}"
