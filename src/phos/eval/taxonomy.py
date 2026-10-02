"""What kind of uncertainty is generating an alert: the error taxonomy behind a false-positive rate.

`atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events` reports **53.26 false positives per
normal hour** on HAI. That is one undifferentiated number. It has always been treated as a quantity
to *reduce* — raise a threshold, widen a window, group harder — and never as a thing to
*understand*. This module is where it gets decomposed: every alert is asked what it is actually
reacting to, and the answer is a category with a written discriminating procedure behind it.

**The ten candidate categories are not a partition, and pretending otherwise is the trap.** Eight
of them answer *what was the plant doing* — normal variation, sensor noise, maintenance, a recipe
change, a start-up, a communication artefact, ageing, something genuinely unusual. Two answer *why
did the model speak* — modelling error and insufficient context. A single alert can have a true
answer on both axes at once, and usually does: the plant did something ordinary **and** the band
did not cover ordinary. `ClassifiedEvent` therefore carries a `primary_category` and the full set
of `co_firing` categories, and the renderer prints both. Collapsing the two axes into one column is
what made 53.26 look like one phenomenon in the first place.

**Nothing is assumed. A category that cannot be distinguished is reported, not split.** Every
category reaches an event through a `CorpusScreen` that first asks whether the corpus carries the
evidence the category needs *at all*. A screen has three verdicts and only one of them lets the
category compete:

* ``assigned`` — the corpus carries the evidence, and the discriminator may fire.
* ``refuted`` — the corpus carries the evidence and it says no. Start-up cannot explain an alert in
  a slice where every declared run-state signal is constant throughout.
* ``not_separable`` — the corpus does not carry the evidence. Maintenance cannot be separated from
  an attack without a work order, and no amount of arithmetic on the signals will change that.

A ``not_separable`` screen carries `what_would_lift_it`, so the screen doubles as a specification
for what PHOS needs from the world rather than a shrug.

**The reference is declared-normal data scored by the same fitted model.** The one measurement that
separates modelling error from everything else is this: take the model exactly as fitted, apply it
to data the corpus itself declares attack-free and which the model never saw, and look at what it
does. If the model produces an equal-or-larger departure there, then the alert under review is
inside the model's own normal-operation noise and the plant's behaviour is not what produced it.
`SignalReference` holds that per signal — the band, the declared-normal exceedance rate, the
declared-normal maximum — and it is the only input here that required a model to build.

**Why attribution goes to the model when both axes fire.** A counterfactual settled by measurement
rather than by preference. Replace the plant's behaviour with declared-normal behaviour and the
alert still occurs, because every one of its departures is one the model produces on declared-normal
data. The plant's behaviour is therefore not the condition without which the alert would not exist,
and `MODEL_FAULT_PRECEDENCE` says so in one place a reader can disagree with. Where no model-side
category fires — where some departure is larger than anything the model managed on declared-normal
data — the plant-side reading is the only reading and takes the slot instead. The procedure does not
presuppose its own answer: on a corpus where the model is adequate, every primary category it
assigns is a plant-side one.

**A reference has a length, and the length is part of the finding.** "No larger than the model
produces on declared-normal data" is a statement about how much declared-normal data is held.
Against a three-hour reference many alerts look unprecedented; against a sixty-hour one they do not.
`SignalReference.reference_hours` travels with every verdict for exactly that reason, and a caller
that reports one reference without its length has hidden the sensitivity rather than measured it.

**What a number from here is not.** It is not a detection claim, it is not a new operating point,
and it does not replace or re-derive 646.58 ungated or 53.26 grouped. Nothing here refits a public
model, searches a threshold, or proposes one. A taxonomy that reduced the alert count would have
answered a different question than the one asked.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ALERT_CATEGORIES",
    "MODEL_FAULT_PRECEDENCE",
    "MODEL_SIDE_CATEGORIES",
    "NOT_SEPARABLE",
    "OVERLAPS_LABELLED_ATTACK",
    "PLANT_SIDE_CATEGORIES",
    "TAXONOMY_CAVEATS",
    "AlertUnderReview",
    "CategoryVerdict",
    "ClassifiedEvent",
    "CorpusScreen",
    "MemberDeparture",
    "SignalReference",
    "classify",
    "classify_event",
    "contributions",
    "signature_of",
    "signature_runs",
]

logger = logging.getLogger(__name__)

PLANT_SIDE_CATEGORIES: Final[tuple[str, ...]] = (
    "normal_process_variation",
    "sensor_noise",
    "maintenance",
    "grade_or_recipe_change",
    "startup_shutdown_transition",
    "communication_artefacts",
    "equipment_ageing",
    "genuinely_unusual_benign",
)
"""Categories that answer *what was the plant doing*. Answerable from the corpus alone."""

MODEL_SIDE_CATEGORIES: Final[tuple[str, ...]] = (
    "modelling_error",
    "insufficient_context",
)
"""Categories that answer *why did the model speak*.

These two point in opposite directions and the phase turns on which dominates. If modelling error
dominates, the answer is a better model. If insufficient context dominates, the answer is more
evidence and no algorithm work will help.
"""

NOT_SEPARABLE: Final = "not_separable"
"""Residual for an event two or more categories claim with no declared rule to break the tie.

Stated rather than distributed. An event pushed into one of its claimants to tidy the table would
be a guess wearing a count.
"""

OVERLAPS_LABELLED_ATTACK: Final = "overlaps_labelled_attack"
"""Not a false alert, and therefore outside the taxonomy's subject.

Kept as its own bucket rather than dropped, because every alert in the queue must be accounted for
and because *which* category such an event would otherwise have fallen into is informative: a true
alert indistinguishable from the false ones explains why no severity ranks the queue.
"""

ALERT_CATEGORIES: Final[tuple[str, ...]] = (
    *PLANT_SIDE_CATEGORIES,
    *MODEL_SIDE_CATEGORIES,
    NOT_SEPARABLE,
    OVERLAPS_LABELLED_ATTACK,
)
"""Every bucket an alert may land in. Exhaustive: `classify` assigns one of these to each alert."""

CategoryVerdict = Literal["assigned", "refuted", "not_separable"]
"""What a corpus screen concluded about a category before any event was looked at."""

DISCRIMINATED: Final[frozenset[str]] = frozenset(
    {
        "modelling_error",
        "normal_process_variation",
        "genuinely_unusual_benign",
        "insufficient_context",
    }
)
"""Categories `classify_event` can decide per alert. Every other one is settled by its screen.

This is a statement about the procedure, not about plants. The six categories outside this set —
sensor noise, maintenance, a recipe change, a start-up, a communication artefact, ageing — are
decided by a `CorpusScreen` that measures whether the corpus carries their evidence at all, and on
a corpus that refutes them or cannot separate them that is the whole answer. A screen that marks one
of them ``assigned`` is therefore an error rather than a licence: it would put a category into
competition that nothing would ever assign, and the silence would read as a measured zero.
`classify_event` refuses it.
"""

MODEL_FAULT_PRECEDENCE: Final = (
    "When a model-side and a plant-side category are both true of one alert, the model-side one "
    "takes the primary slot. The test is a counterfactual settled by measurement rather than by "
    "preference: replace the plant's behaviour with declared-normal behaviour and the alert still "
    "occurs, because every one of its departures is one the same model produces on data the corpus "
    "declares attack-free. The plant's behaviour is therefore not the condition without which the "
    "alert would not exist, and the condition that is gets the slot. Where no model-side category "
    "fires — where some departure is larger than anything the model produced on declared-normal "
    "data — the plant-side reading is the only reading, and it takes the slot instead. The rule "
    "therefore does not presuppose its own answer: on a corpus where the model is adequate, every "
    "primary category here is a plant-side one."
)
"""The one precedence rule, written out so a reader can disagree with it in one place.

Deliberately **not** keyed on `SignalReference.band_covers_declared_normal`. That comparison puts
a conditional band beside a marginal standard deviation, and a correct conditional band is
legitimately much narrower than the marginal spread wherever the conditional relation is real. It is
reported as *mechanism* — why the model behaves as it does — and never used to decide an event,
because deciding on it would attribute an alert to a band width on the strength of a comparison that
does not hold. The deciding test is the empirical one: what the model does on declared-normal data.
"""

TAXONOMY_CAVEATS: Final[tuple[str, ...]] = (
    "A category assignment is a diagnosis of an alert, not a detection claim. Nothing here is a "
    "new operating point and nothing here replaces or re-derives a frozen row.",
    "'No larger than the model produces on declared-normal data' is relative to a reference of a "
    "stated length. A shorter reference contains fewer tails and makes more alerts look "
    "unprecedented. Read every verdict with its reference_hours.",
    "A declared-normal reference is declared normal by the corpus author, not verified by PHOS. "
    "An unlabelled attack inside it would be learned as normal.",
    "A refuted screen is refuted for this corpus and this slice only. It says the evidence was "
    "present and said no, never that the category cannot occur on a plant.",
    "A not_separable screen means the corpus does not carry the evidence the category needs. It is "
    "not a statement that the category is absent, and it must not be read as one.",
    "Categories are not a partition. primary_category is one reading under a declared precedence; "
    "co_firing carries the rest, and both must be read together.",
    "A not_separable count of zero is not a claim that nothing was ambiguous. Only the categories "
    "in DISCRIMINATED reach a per-event test at all, and where a corpus supports only two of them "
    "the residual can be structurally zero because no two can fire at once. Read it with the "
    "screen, which is where the categories nothing could decide are recorded.",
)
"""What must be read with every number this module produces."""


class MemberDeparture(BaseModel):
    """One per-signal departure inside an alert, as the taxonomy needs to see it.

    Attributes:
        signal: The signal that departed.
        magnitude: How far outside the model's band it went, in learned spreads.
        value: The reading itself, in the signal's own units.
    """

    model_config = ConfigDict(frozen=True)

    signal: str
    magnitude: float = Field(ge=0.0)
    value: float


class AlertUnderReview(BaseModel):
    """One alert, reduced to what a category test needs. No store, no model, no corpus.

    Attributes:
        evidence_id: The subsystem event's id, so a verdict leads back to the ontology.
        timestamp: The event's stamp — its earliest member's instant.
        subsystem: The declared physical unit the event belongs to.
        members: Every per-signal departure collapsed into this event. At least one.
        overlaps_attack: Whether any member fell inside a labelled attack window, by the
            overlap-aware rule the vertical already counts with.
    """

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    timestamp: datetime
    subsystem: str
    members: tuple[MemberDeparture, ...] = Field(min_length=1)
    overlaps_attack: bool = False

    @property
    def strongest(self) -> MemberDeparture:
        """Return the member that departed furthest — the event's reported magnitude."""
        return max(self.members, key=lambda member: member.magnitude)

    @property
    def breadth(self) -> int:
        """Return how many distinct signals of the unit departed."""
        return len({member.signal for member in self.members})


class SignalReference(BaseModel):
    """What the same fitted model does to one signal on data the corpus declares attack-free.

    This is the instrument that separates modelling error from a plant phenomenon, and it is built
    without looking at a single label on the side being judged: the reference is declared normal by
    the corpus author, and the model scoring it is the model exactly as fitted.

    Attributes:
        signal: The signal this describes.
        band_high: Upper edge of the model's reported band, in the signal's own units.
        declared_normal_stddev: The signal's standard deviation over the reference.
        declared_normal_exceedance: Fraction of reference moments whose departure exceeded the
            band. A signal with a substantial rate here alerts in normal operation as a matter of
            course, so a departure on it carries correspondingly little information.
        declared_normal_max_magnitude: The largest departure the model produced on the reference.
        reference_hours: How much declared-normal data the two figures above rest on. Travels with
            the verdict because a shorter reference holds fewer tails.
        at_shrinkage_floor: Whether the band came from this signal's own variation or from the
            shrinkage floor, which in a mixed-scale plant is set by the largest-scale tag and is
            the same for every floored signal.
        envelope_low: Smallest value the signal took over the reference.
        envelope_high: Largest value the signal took over the reference.
    """

    model_config = ConfigDict(frozen=True)

    signal: str
    band_high: float = Field(ge=0.0)
    declared_normal_stddev: float = Field(ge=0.0)
    declared_normal_exceedance: float = Field(ge=0.0, le=1.0)
    declared_normal_max_magnitude: float = Field(ge=0.0)
    reference_hours: float = Field(gt=0.0)
    at_shrinkage_floor: bool
    envelope_low: float
    envelope_high: float

    @property
    def band_covers_declared_normal(self) -> bool:
        """Whether the band is at least as wide as the signal's own declared-normal variation.

        A band narrower than the signal's own normal swing must alert in normal operation; that is
        arithmetic, not a tuning preference, and it is the clearest statement of *why* a model
        behaves as it does.

        **Reported, never used to decide an event.** This puts a conditional band beside a marginal
        standard deviation, and a correct conditional band is legitimately much narrower than the
        marginal spread wherever the conditional relation is real. `MODEL_FAULT_PRECEDENCE` records
        why the deciding test is `covers` instead — what the model actually does on declared-normal
        data, which needs no such assumption.
        """
        return self.band_high >= self.declared_normal_stddev

    def covers(self, magnitude: float) -> bool:
        """Whether the model produced an equal-or-larger departure on declared-normal data."""
        return magnitude <= self.declared_normal_max_magnitude

    def inside_envelope(self, value: float) -> bool:
        """Whether a reading falls inside the range the signal took over the reference."""
        return self.envelope_low <= value <= self.envelope_high


class CorpusScreen(BaseModel):
    """What the corpus can say about one category, decided before any event was looked at.

    Attributes:
        category: One of `ALERT_CATEGORIES`.
        verdict: Whether the category may compete, was refuted, or cannot be separated.
        basis: The measurement behind the verdict, specific enough to re-run.
        what_would_lift_it: For a ``not_separable`` verdict, what evidence would settle it. Required
            there and forbidden elsewhere, so the screen cannot become a shrug.
    """

    model_config = ConfigDict(frozen=True)

    category: str
    verdict: CategoryVerdict
    basis: str
    what_would_lift_it: str | None = None

    @property
    def may_compete(self) -> bool:
        """Whether a discriminator for this category is allowed to fire on an event."""
        return self.verdict == "assigned"


class ClassifiedEvent(BaseModel):
    """One alert's verdict, with everything needed to argue with it.

    Attributes:
        evidence_id: The event classified.
        timestamp: Its stamp.
        subsystem: Its declared physical unit.
        breadth: How many of the unit's signals departed.
        strongest_signal: The member that departed furthest.
        strongest_magnitude: How far, in learned spreads.
        overlaps_attack: Whether it overlaps a labelled attack window.
        primary_category: The single category assigned, under `MODEL_FAULT_PRECEDENCE`.
        co_firing: Every other category whose discriminator also fired, in declared order.
        basis: Why this event got this category, in one sentence.
    """

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    timestamp: datetime
    subsystem: str
    breadth: int = Field(ge=1)
    strongest_signal: str
    strongest_magnitude: float = Field(ge=0.0)
    overlaps_attack: bool
    primary_category: str
    co_firing: tuple[str, ...] = ()
    basis: str


def _screened(screens: Sequence[CorpusScreen]) -> Mapping[str, CorpusScreen]:
    """Index screens by category, refusing a category screened twice."""
    indexed: dict[str, CorpusScreen] = {}
    for screen in screens:
        if screen.category in indexed:
            raise ValueError(f"category {screen.category!r} is screened more than once")
        indexed[screen.category] = screen
    return indexed


def classify_event(
    alert: AlertUnderReview,
    references: Mapping[str, SignalReference],
    screens: Sequence[CorpusScreen],
) -> ClassifiedEvent:
    """Assign one alert a primary category and the full set of categories that fired.

    The procedure, in the order it runs:

    1. An alert overlapping a labelled attack window is `OVERLAPS_LABELLED_ATTACK`. It is not a
       false alert, so the taxonomy records it and moves on — but it is still measured against the
       references, and ``co_firing`` says what it would have been called, because a true alert
       indistinguishable from the false ones is the reason a queue cannot be ranked.
    2. A category whose screen is not ``assigned`` cannot fire. A refuted category was measured and
       said no; a not_separable one has no evidence to fire on.
    3. ``modelling_error`` fires when no departing member's band covers its signal's declared-normal
       variation **and** every member's departure is one the model also produces on declared-normal
       data.
    4. ``normal_process_variation`` fires when every member's reading is inside the declared-normal
       envelope **and** every departure is one the model also produces there. The envelope test
       alone is too weak to carry it: individually in-range readings whose joint departure is
       unprecedented are exactly what a subtle attack looks like, and calling that normal variation
       because no single signal left its range would be the joint model arguing against itself.
    5. ``genuinely_unusual_benign`` fires when some member's departure exceeds anything the model
       produced on declared-normal data.
    6. Two or more primary claimants with no rule between them is `NOT_SEPARABLE`; none at all is
       ``insufficient_context`` — nothing in the data could have decided.

    Args:
        alert: The alert to classify.
        references: Declared-normal behaviour per signal, covering every member's signal.
        screens: One screen per category considered.

    Returns:
        The verdict, its co-firing set, and the sentence that justifies it.

    Raises:
        ValueError: If a member's signal has no reference, which would leave the model-side test
            undecidable while looking as though it had been decided, or if a category is screened
            more than once.
    """
    indexed = _screened(screens)
    undecidable = sorted(
        category
        for category, screen in indexed.items()
        if screen.may_compete and category not in DISCRIMINATED
    )
    if undecidable:
        raise ValueError(
            f"{', '.join(undecidable)} is screened 'assigned' but has no per-event discriminator, "
            "so no alert would ever be assigned to it and its zero would read as a measurement. "
            "Screen it 'refuted' or 'not_separable' with the basis, or implement the discriminator"
        )
    missing = sorted({m.signal for m in alert.members} - set(references))
    if missing:
        raise ValueError(
            f"{alert.evidence_id}: no declared-normal reference for {', '.join(missing)}; the "
            "model-side test cannot be decided for this alert and must not be guessed"
        )
    members = [(member, references[member.signal]) for member in alert.members]
    inside_noise = all(reference.covers(member.magnitude) for member, reference in members)
    inside_envelope = all(reference.inside_envelope(member.value) for member, reference in members)
    unprecedented = [m.signal for m, reference in members if not reference.covers(m.magnitude)]

    fired: list[str] = []
    if inside_noise and indexed["modelling_error"].may_compete:
        fired.append("modelling_error")
    if inside_noise and inside_envelope and indexed["normal_process_variation"].may_compete:
        fired.append("normal_process_variation")
    if unprecedented and indexed["genuinely_unusual_benign"].may_compete:
        fired.append("genuinely_unusual_benign")

    strongest = alert.strongest
    reference = references[strongest.signal]
    if alert.overlaps_attack:
        primary, basis = (
            OVERLAPS_LABELLED_ATTACK,
            (
                f"overlaps a labelled attack window; strongest member {strongest.signal} at "
                f"{strongest.magnitude:.3f} against a declared-normal maximum of "
                f"{reference.declared_normal_max_magnitude:.3f} over "
                f"{reference.reference_hours:.2f} h "
                f"({
                    'unprecedented there'
                    if not reference.covers(strongest.magnitude)
                    else "inside the model's declared-normal noise"
                })"
            ),
        )
    elif not fired:
        primary, basis = (
            "insufficient_context",
            (
                "no discriminator fired: the corpus carries nothing that could decide what "
                "this alert is reacting to"
            ),
        )
    else:
        primary, basis = _primary(fired, strongest, reference)
    return ClassifiedEvent(
        evidence_id=alert.evidence_id,
        timestamp=alert.timestamp,
        subsystem=alert.subsystem,
        breadth=alert.breadth,
        strongest_signal=strongest.signal,
        strongest_magnitude=strongest.magnitude,
        overlaps_attack=alert.overlaps_attack,
        primary_category=primary,
        co_firing=tuple(category for category in fired if category != primary),
        basis=basis,
    )


def _primary(
    fired: Sequence[str],
    strongest: MemberDeparture,
    reference: SignalReference,
) -> tuple[str, str]:
    """Pick the primary category from those that fired, and say why in one sentence."""
    plant = [category for category in fired if category in PLANT_SIDE_CATEGORIES]
    model = [category for category in fired if category in MODEL_SIDE_CATEGORIES]
    if model:
        return model[0], (
            f"every departure is one the model also produces on declared-normal data: strongest "
            f"member {strongest.signal} at {strongest.magnitude:.3f} against a declared-normal "
            f"maximum of {reference.declared_normal_max_magnitude:.3f} over "
            f"{reference.reference_hours:.2f} h, on which the model exceeds its band "
            f"{reference.declared_normal_exceedance:.2%} of the time"
        )
    if len(plant) == 1:
        return plant[0], (
            f"no model-side category fired, so the plant-side reading is the only reading: "
            f"{plant[0]} on {strongest.signal} at {strongest.magnitude:.3f}, against a "
            f"declared-normal maximum of {reference.declared_normal_max_magnitude:.3f}"
        )
    return NOT_SEPARABLE, (
        f"{len(plant)} plant-side categories fired ({', '.join(plant)}) with no declared rule "
        "between them on this corpus"
    )


def classify(
    alerts: Sequence[AlertUnderReview],
    references: Mapping[str, SignalReference],
    screens: Sequence[CorpusScreen],
) -> tuple[ClassifiedEvent, ...]:
    """Classify a whole queue, in the order given. A pure function of its arguments."""
    classified = tuple(classify_event(alert, references, screens) for alert in alerts)
    logger.info(
        "classified %d alert(s) into %d category(ies)",
        len(classified),
        len({event.primary_category for event in classified}),
    )
    return classified


def contributions(classified: Sequence[ClassifiedEvent]) -> dict[str, int]:
    """Return the count per category, every declared category present even at zero.

    Zeroes are kept because a category measured to contribute nothing is a result. A table that
    silently omitted the refuted categories would read as though they had never been tested.
    """
    counted = dict.fromkeys(ALERT_CATEGORIES, 0)
    for event in classified:
        counted[event.primary_category] += 1
    return counted


def signature_of(alert: AlertUnderReview) -> tuple[str, tuple[str, ...]]:
    """Return an alert's ``(subsystem, departing signals)`` signature.

    Two alerts with one signature are the same set of instruments on the same unit. A queue of 424
    events carrying fifteen signatures is not 424 phenomena, and counting the signatures is the
    first thing to do before asking what any of them means.
    """
    return alert.subsystem, tuple(sorted({member.signal for member in alert.members}))


def signature_runs(
    alerts: Sequence[AlertUnderReview], window: timedelta
) -> dict[tuple[str, tuple[str, ...]], tuple[int, int]]:
    """Return ``(events, contiguous runs)`` per signature.

    A run breaks when the same signature goes quiet for longer than ``window``. A signature with
    many events and few runs is one persisting condition re-counted once per window, which is a
    different thing for an operator than many separate findings.

    Args:
        alerts: The queue, in any order.
        window: The grouping window the events were built with. A gap wider than this means the
            condition actually stopped rather than merely landing in the next bucket.

    Returns:
        Signature to ``(event count, run count)``, ordered by event count descending.

    Raises:
        ValueError: If ``window`` is not a positive duration, which would make every event its own
            run and report a persisting condition as hundreds of separate ones.
    """
    if window <= timedelta(0):
        raise ValueError(f"window must be a positive duration, got {window}")
    grouped: dict[tuple[str, tuple[str, ...]], list[datetime]] = {}
    for alert in alerts:
        grouped.setdefault(signature_of(alert), []).append(alert.timestamp)
    summary: dict[tuple[str, tuple[str, ...]], tuple[int, int]] = {}
    for signature, stamps in grouped.items():
        ordered = sorted(stamps)
        breaks = sum(1 for earlier, later in pairwise(ordered) if later - earlier > window)
        summary[signature] = (len(ordered), 1 + breaks)
    return dict(sorted(summary.items(), key=lambda item: (-item[1][0], item[0])))
