"""Tests for the candidate / out-of-band / evidence boundary.

The refusal tests are the point of this module. PART 3 left `Deviation` meaning "candidate", not
"departure from normal", and PART 4B builds hypotheses on `Evidence`. If an in-band candidate
could become `Evidence`, every hypothesis downstream would rest on a non-event. These tests are
what makes that unrepresentable.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.ontology import Deviation, Domain, EvidenceKind, ExpectedRange, Observation
from phos.reasoning.boundary import (
    evidence_from_deviation,
    evidence_from_relationship_change,
    is_out_of_band,
)

T0 = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"


def expected_range(
    low: float, high: float, *, mean: float = 10.0, stddev: float = 2.0
) -> ExpectedRange:
    return ExpectedRange(
        feature=FEATURE,
        entity_id=ENTITY,
        low=low,
        high=high,
        mean=mean,
        stddev=stddev,
        learned_from_window=(T0 - timedelta(hours=1), T0),
    )


def observation(value: float, *, identifier: str = "obs_00000000000a") -> Observation:
    return Observation(
        id=identifier,
        entity_ids=[ENTITY],
        feature=FEATURE,
        value=value,
        timestamp=T0,
        domain=Domain.ATLAS,
    )


def deviation(
    observed: Observation, expected: ExpectedRange, *, magnitude: float = 1.5
) -> Deviation:
    return Deviation(
        id="dev_00000000000a",
        observation_id=observed.id,
        expected=expected,
        magnitude=magnitude,
        timestamp=observed.timestamp,
    )


# ------------------------------------------------------------------------------------------------
# is_out_of_band
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "out_of_band"),
    [
        (10.0, False),  # dead centre
        (4.0, False),  # exactly the lower bound — inclusive
        (16.0, False),  # exactly the upper bound — inclusive
        (3.999, True),  # a hair below
        (16.001, True),  # a hair above
        (-100.0, True),
        (100.0, True),
    ],
)
def test_out_of_band_is_decided_by_the_bounds(value: float, out_of_band: bool) -> None:
    """The bounds decide, and they are inclusive, exactly as `ExpectedRange.contains` says."""
    expected = expected_range(4.0, 16.0)
    observed = observation(value)

    assert is_out_of_band(deviation(observed, expected), observed) is out_of_band


def test_out_of_band_ignores_magnitude() -> None:
    """A large magnitude does not make a value out of band, and a small one does not save it.

    This is why the boundary is a value-vs-range test rather than a magnitude threshold: the three
    baselines do not agree on what a magnitude means. An IQR magnitude is an overshoot beyond a
    fence, a Gaussian magnitude is a z-score, and a threshold that separates them correctly for one
    model separates them wrongly for another.
    """
    expected = expected_range(4.0, 16.0)

    loud = observation(15.9)
    assert is_out_of_band(deviation(loud, expected, magnitude=999.0), loud) is False

    quiet = observation(16.1)
    assert is_out_of_band(deviation(quiet, expected, magnitude=0.0), quiet) is True


def test_out_of_band_handles_a_degenerate_range() -> None:
    """A constant training window admits exactly one value as normal."""
    expected = expected_range(7.0, 7.0, mean=7.0, stddev=0.0)

    assert is_out_of_band(deviation(observation(7.0), expected), observation(7.0)) is False
    assert is_out_of_band(deviation(observation(7.01), expected), observation(7.01)) is True


def test_out_of_band_refuses_a_mismatched_pair() -> None:
    """Judging a deviation against someone else's observation would break traceability.

    The deviation names the observation it came from. Answering a question about a different one
    would silently produce evidence whose stored `source_id` does not lead back to the measurement
    it describes, which is precisely what Constitution §3.2 forbids.
    """
    expected = expected_range(4.0, 16.0)
    theirs = observation(5.0, identifier="obs_00000000000a")
    mine = observation(99.0, identifier="obs_00000000000b")

    with pytest.raises(ValueError, match="does not describe observation"):
        is_out_of_band(deviation(theirs, expected), mine)


# ------------------------------------------------------------------------------------------------
# evidence_from_deviation
# ------------------------------------------------------------------------------------------------


def test_evidence_is_built_from_an_out_of_band_deviation() -> None:
    expected = expected_range(4.0, 16.0)
    observed = observation(20.0)
    source = deviation(observed, expected, magnitude=5.0)

    evidence = evidence_from_deviation(source, observed, 0.75, summary="flow_rate above normal")

    assert evidence.kind is EvidenceKind.DEVIATION
    assert evidence.source_id == source.id
    assert evidence.entity_ids == observed.entity_ids
    assert evidence.timestamp == observed.timestamp
    assert evidence.domain is observed.domain
    assert evidence.weight == 0.75
    assert evidence.summary == "flow_rate above normal"


def test_evidence_is_traceable_back_to_the_measurement() -> None:
    """source_id → deviation → observation_id → observation. The whole chain, with no gaps.

    This is Constitution §3.2 stated as a test: anything a user could see must be reconstructable
    from stored evidence.
    """
    expected = expected_range(4.0, 16.0)
    observed = observation(20.0)
    source = deviation(observed, expected, magnitude=5.0)
    by_id = {source.id: source}
    observations = {observed.id: observed}

    evidence = evidence_from_deviation(source, observed, 0.75, summary="above normal")

    recovered_deviation = by_id[evidence.source_id]
    recovered_observation = observations[recovered_deviation.observation_id]
    assert recovered_observation is observed
    assert recovered_deviation.expected.contains(recovered_observation.value) is False


def test_evidence_refuses_an_in_band_deviation() -> None:
    """The hard line PART 4B relies on: a candidate inside its own range is not a departure.

    This is the PART 3 debt settled. With ``emit_k < band_k`` a model emits candidates for
    observations that never left their expected range; they exist to give the harness a dense
    threshold sweep. Reasoning must never see them.
    """
    expected = expected_range(4.0, 16.0)
    observed = observation(15.0)  # inside [4, 16] — a candidate, not a departure
    source = deviation(observed, expected, magnitude=2.5)

    with pytest.raises(ValueError, match="in-band"):
        evidence_from_deviation(source, observed, 0.75, summary="should never be built")


def test_evidence_refuses_a_mismatched_pair() -> None:
    expected = expected_range(4.0, 16.0)
    theirs = observation(20.0, identifier="obs_00000000000a")
    mine = observation(21.0, identifier="obs_00000000000b")

    with pytest.raises(ValueError, match="does not describe observation"):
        evidence_from_deviation(deviation(theirs, expected), mine, 0.5, summary="mismatched")


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0])
def test_evidence_refuses_a_confidence_outside_zero_one(confidence: float) -> None:
    """The weight is a calibrated probability, so a value outside [0, 1] is not one.

    `Evidence.weight` is merely non-negative — it is a general-purpose reasoning weight. This
    boundary is stricter on purpose: it only ever writes a calibrated probability there, and
    silently accepting 2.0 would put a number on a user-facing path that cannot mean what §3.3
    says a confidence means.
    """
    expected = expected_range(4.0, 16.0)
    observed = observation(20.0)

    with pytest.raises(ValueError, match="calibrated probability"):
        evidence_from_deviation(
            deviation(observed, expected), observed, confidence, summary="bad weight"
        )


def test_evidence_round_trips_as_json() -> None:
    from phos.ontology import Evidence

    expected = expected_range(4.0, 16.0)
    observed = observation(20.0)
    evidence = evidence_from_deviation(
        deviation(observed, expected), observed, 0.9, summary="above normal"
    )

    assert Evidence.model_validate_json(evidence.model_dump_json()) == evidence


@pytest.mark.parametrize(
    ("style", "low", "high", "mean", "stddev"),
    [
        # Gaussian: mean ± band_k·stddev, so symmetric about the mean.
        ("gaussian", 4.0, 16.0, 10.0, 2.0),
        # IQR: Q1 - k·IQR to Q3 + k·IQR, which is asymmetric about the mean whenever the training
        # distribution is skewed. This is the case a z-score shortcut would get wrong.
        ("iqr", 2.0, 30.0, 8.0, 1.5),
        # EWMA: a band around a moving level, so the mean recorded on the range need not sit at the
        # band's centre at all.
        ("ewma", 50.0, 60.0, 51.0, 3.0),
    ],
)
def test_out_of_band_holds_across_every_baselines_range_shape(
    style: str, low: float, high: float, mean: float, stddev: float
) -> None:
    """The boundary is the stored bounds, whatever shape the model gave them.

    A regression guard with teeth: the obvious "simplification" of `is_out_of_band` is to compare
    a z-score against a constant, which is correct for a symmetric Gaussian band and silently wrong
    for an asymmetric IQR fence or an EWMA band whose recorded mean is off-centre. Each row below
    puts a value just inside and just outside bounds that a z-score test would misjudge.
    """
    expected = expected_range(low, high, mean=mean, stddev=stddev)

    for value in (low, high, (low + high) / 2.0):
        observed = observation(value)
        assert is_out_of_band(deviation(observed, expected), observed) is False, (
            f"{style}: {value} is inside [{low}, {high}]"
        )

    for value in (low - 0.001, high + 0.001):
        observed = observation(value)
        assert is_out_of_band(deviation(observed, expected), observed) is True, (
            f"{style}: {value} is outside [{low}, {high}]"
        )


# ------------------------------------------------------------------------------------------------
# The relationship-change boundary
# ------------------------------------------------------------------------------------------------
#
# A structural change has no `ExpectedRange` behind it — there is no learned band for "this link
# has never existed" — so it cannot come through `evidence_from_deviation` without inventing one.
# These tests hold the second door to the same standard as the first: it refuses a non-event, and
# it refuses a weight that is not a probability.


def finding(value: float, *, feature: str = "unknown_command_relationship") -> Observation:
    """Build a relationship-change finding of the shape `phos.atlas.packet.graph` emits."""
    return Observation(
        id="obs_00000000000f",
        entity_ids=["ent_10.0.0.9", "ent_10.0.0.20"],
        feature=feature,
        value=value,
        timestamp=T0,
        domain=Domain.ATLAS,
        context={"frames": "/captures/plant.pcap:10-14", "frame_count": "5"},
    )


def test_relationship_change_evidence_carries_the_findings_own_facts() -> None:
    evidence = evidence_from_relationship_change(finding(5.0), 0.75, summary="a new link")

    assert evidence.kind is EvidenceKind.RELATIONSHIP_CHANGE
    assert evidence.source_id == "obs_00000000000f"
    assert evidence.entity_ids == ["ent_10.0.0.9", "ent_10.0.0.20"]
    assert evidence.timestamp == T0
    assert evidence.domain is Domain.ATLAS
    assert evidence.weight == 0.75
    assert evidence.summary == "a new link"


def test_relationship_change_evidence_traces_back_to_the_frames() -> None:
    """The whole traceability chain, walked: evidence -> finding -> the frames that justify it."""
    source = finding(5.0)
    evidence = evidence_from_relationship_change(source, 0.5, summary="a new link")

    assert evidence.source_id == source.id
    assert source.context["frames"] == "/captures/plant.pcap:10-14"


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_relationship_change_evidence_refuses_a_non_event(value: float) -> None:
    """The analogue of the in-band refusal: nothing changed, so nothing may rest on it."""
    with pytest.raises(ValueError, match="non-event"):
        evidence_from_relationship_change(finding(value), 0.5, summary="nothing happened")


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_relationship_change_evidence_refuses_a_confidence_outside_zero_one(
    confidence: float,
) -> None:
    with pytest.raises(ValueError, match="calibrated probability"):
        evidence_from_relationship_change(finding(3.0), confidence, summary="a new link")


def test_relationship_change_evidence_refuses_another_engines_kind_of_measurement() -> None:
    """A finding that is really a scalar reading of one entity is not a relationship change."""
    lone = Observation(
        entity_ids=["ent_10.0.0.9"],
        feature="command_count",
        value=42.0,
        timestamp=T0,
        domain=Domain.ATLAS,
    )
    with pytest.raises(ValueError, match="not a structure"):
        evidence_from_relationship_change(lone, 0.5, summary="not a relationship")
