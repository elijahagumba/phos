"""Tests for the three-way train/calib/test split.

The refusal tests carry most of the weight. A three-way split exists so a calibrator can be fitted
on data the final metrics never see; every way that guarantee can rot — an empty slice, a
calibration slice with nothing to learn from, a test slice with nothing to be right about — has to
fail loudly, because each of them produces a number that looks like a result.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.eval import Dataset, LabelledInterval
from phos.models import SplitPolicy, train_test_split
from phos.ontology import Domain, Observation
from phos.reasoning.splits import (
    CalibrationSplitPolicy,
    DegenerateSplitError,
    prefix_split,
    train_calib_test_split,
)

T0 = datetime(2026, 7, 29, 0, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"

DEFAULT_POLICY = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)


def corpus(
    *, points: int = 100, attacks: list[tuple[int, int]] | None = None, name: str = "fixture"
) -> Dataset:
    """A corpus of ``points`` minute-spaced observations with attacks over the given index spans."""
    observations = [
        Observation(
            id=f"obs_{index:012d}",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=10.0,
            timestamp=T0 + timedelta(minutes=index),
            domain=Domain.ATLAS,
        )
        for index in range(points)
    ]
    intervals = [
        LabelledInterval(
            start=T0 + timedelta(minutes=start),
            end=T0 + timedelta(minutes=end),
            label="attack",
        )
        for start, end in (attacks or [])
    ]
    return Dataset(
        name=name,
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=intervals,
        source_note="fixture",
    )


def attack_count(dataset: Dataset) -> int:
    return sum(1 for o in dataset.observations if dataset.is_attack(o.timestamp))


# ------------------------------------------------------------------------------------------------
# The policy
# ------------------------------------------------------------------------------------------------


def test_policy_requires_a_remainder_for_test() -> None:
    """Train + calib must leave something over; test is the remainder, not an afterthought."""
    with pytest.raises(ValueError, match="leave a test remainder"):
        CalibrationSplitPolicy(train_fraction=0.6, calib_fraction=0.4)


@pytest.mark.parametrize(
    ("train_fraction", "calib_fraction"),
    [(0.0, 0.3), (0.4, 0.0), (-0.1, 0.3), (0.4, 1.2)],
)
def test_policy_rejects_degenerate_fractions(train_fraction: float, calib_fraction: float) -> None:
    with pytest.raises(ValueError):
        CalibrationSplitPolicy(train_fraction=train_fraction, calib_fraction=calib_fraction)


# ------------------------------------------------------------------------------------------------
# The split
# ------------------------------------------------------------------------------------------------


def test_split_is_a_time_ordered_partition() -> None:
    """Disjoint, contiguous, and losing nothing: every observation lands in exactly one slice."""
    dataset = corpus(attacks=[(45, 50), (80, 85)])

    train, calib, test = train_calib_test_split(dataset, DEFAULT_POLICY)

    ids = [[o.id for o in part.observations] for part in (train, calib, test)]
    assert ids[0] + ids[1] + ids[2] == [o.id for o in dataset.observations]
    assert len(set(ids[0]) | set(ids[1]) | set(ids[2])) == len(dataset.observations)
    assert train.observations[-1].timestamp < calib.observations[0].timestamp
    assert calib.observations[-1].timestamp < test.observations[0].timestamp


def test_train_is_attack_free() -> None:
    """The invariant inherited from PART 3: a model never learns an attack as normal."""
    dataset = corpus(attacks=[(45, 50), (80, 85)])

    train, _, _ = train_calib_test_split(dataset, DEFAULT_POLICY)

    assert train.attack_intervals == []
    assert attack_count(train) == 0


def test_calib_and_test_both_carry_labels_of_both_classes() -> None:
    dataset = corpus(attacks=[(45, 50), (80, 85)])

    _, calib, test = train_calib_test_split(dataset, DEFAULT_POLICY)

    for part in (calib, test):
        assert attack_count(part) >= 1, f"{part.name} has no attack points"
        assert attack_count(part) < len(part.observations), f"{part.name} has no normal points"
        assert part.attack_intervals


def test_split_is_deterministic() -> None:
    dataset = corpus(attacks=[(45, 50), (80, 85)])

    first = train_calib_test_split(dataset, DEFAULT_POLICY)
    second = train_calib_test_split(dataset, DEFAULT_POLICY)

    assert first == second


def test_train_is_cut_short_by_an_early_attack_and_calib_absorbs_the_slack() -> None:
    """The training prefix yields to the first attack; the calibration slice starts where it ends.

    An attack at 10% of the timeline leaves far less training data than ``train_fraction`` asked
    for. PART 3 already resolves that in favour of an attack-free prefix, and this split inherits
    it rather than re-deciding: what it adds is that the space given up is handed to calibration
    instead of being dropped.
    """
    dataset = corpus(attacks=[(10, 12), (45, 50), (80, 85)])

    train, calib, _ = train_calib_test_split(dataset, DEFAULT_POLICY)

    assert len(train.observations) == 10, "prefix stops strictly before the attack at minute 10"
    assert attack_count(train) == 0
    assert calib.observations[0].timestamp == T0 + timedelta(minutes=10)


def test_calib_boundary_follows_the_policy_fractions() -> None:
    """Calib ends at ``train_fraction + calib_fraction`` of the *corpus* timeline."""
    dataset = corpus(points=101, attacks=[(45, 50), (80, 85)])  # span is exactly 100 minutes

    _, calib, test = train_calib_test_split(dataset, DEFAULT_POLICY)

    assert calib.observations[-1].timestamp == T0 + timedelta(minutes=70)
    assert test.observations[0].timestamp == T0 + timedelta(minutes=71)


def test_split_names_and_provenance_record_the_split() -> None:
    dataset = corpus(attacks=[(45, 50), (80, 85)], name="batadal-test")

    train, calib, test = train_calib_test_split(dataset, DEFAULT_POLICY)

    assert (train.name, calib.name, test.name) == (
        "batadal-test-train",
        "batadal-test-calib",
        "batadal-test-test",
    )
    for part in (train, calib, test):
        assert "train_fraction=0.4" in part.source_note
        assert "calib_fraction=0.3" in part.source_note


def test_intervals_are_clipped_to_the_slice_that_contains_them() -> None:
    dataset = corpus(attacks=[(45, 50), (80, 85)])

    _, calib, test = train_calib_test_split(dataset, DEFAULT_POLICY)

    assert len(calib.attack_intervals) == 1
    assert len(test.attack_intervals) == 1
    assert calib.attack_intervals[0].start == T0 + timedelta(minutes=45)
    assert test.attack_intervals[0].start == T0 + timedelta(minutes=80)


# ------------------------------------------------------------------------------------------------
# Refusals
# ------------------------------------------------------------------------------------------------


def test_split_refuses_a_calib_slice_with_no_attacks() -> None:
    """The designed-split case the operator has to resolve, named rather than papered over.

    A corpus whose attacks all fall late leaves a calibration slice with nothing to learn from.
    Fitting on it would raise inside the calibrator anyway, but raising *here* says which slice is
    the problem and which knob moves it.
    """
    dataset = corpus(attacks=[(80, 85), (90, 95)])

    with pytest.raises(DegenerateSplitError, match=r"calib.*no attack"):
        train_calib_test_split(dataset, DEFAULT_POLICY)


def test_split_refuses_a_test_slice_with_no_attacks() -> None:
    """An attack-free test slice makes the calibration win meaningless, so it is refused.

    Every alert on such a slice is a false positive, so a calibrator that answers "0.0" to
    everything scores a *perfect* calibration error. The comparison this PART exists to make would
    report a huge improvement that means nothing. This is the real HAI trap: its attacks are all
    in the first half of the corpus, so a naive 0.4/0.3 split leaves nothing to be right about.
    """
    dataset = corpus(attacks=[(45, 50), (60, 65)])

    with pytest.raises(DegenerateSplitError, match=r"test.*no attack"):
        train_calib_test_split(dataset, DEFAULT_POLICY)


def test_split_refuses_a_calib_slice_with_no_normal_points() -> None:
    dataset = corpus(attacks=[(39, 71), (80, 85)])

    with pytest.raises(DegenerateSplitError, match=r"calib.*no normal"):
        train_calib_test_split(dataset, DEFAULT_POLICY)


def test_split_refuses_a_corpus_with_no_attacks_at_all() -> None:
    with pytest.raises(DegenerateSplitError, match="no attack"):
        train_calib_test_split(corpus(), DEFAULT_POLICY)


def test_split_refuses_an_empty_corpus() -> None:
    empty = Dataset(name="empty", domain=Domain.ATLAS, observations=[])

    with pytest.raises(DegenerateSplitError, match="no observations"):
        train_calib_test_split(empty, DEFAULT_POLICY)


def test_split_refuses_a_corpus_whose_first_observation_is_already_under_attack() -> None:
    """No attack-free prefix means no honest training set, so there is nothing to fit."""
    dataset = corpus(attacks=[(0, 5), (45, 50), (80, 85)])

    with pytest.raises(DegenerateSplitError, match="no attack-free training prefix"):
        train_calib_test_split(dataset, DEFAULT_POLICY)


def test_degenerate_split_error_is_a_value_error() -> None:
    """Callers that only know about ValueError still catch it."""
    assert issubclass(DegenerateSplitError, ValueError)


def test_split_refuses_an_empty_calib_slice() -> None:
    """A sparse corpus can leave the middle slice with no observations in it at all.

    Distinct from the no-attacks case: here the fractions are satisfiable in principle but the
    corpus has no samples in that stretch of the timeline. Three observations at minutes 0, 40 and
    100 put the whole remainder past the calibration cutoff at minute 70.
    """
    sparse = Dataset(
        name="sparse",
        domain=Domain.ATLAS,
        observations=[
            Observation(
                id=f"obs_{minute:012d}",
                entity_ids=[ENTITY],
                feature=FEATURE,
                value=10.0,
                timestamp=T0 + timedelta(minutes=minute),
                domain=Domain.ATLAS,
            )
            for minute in (0, 40, 100)
        ],
        attack_intervals=[
            LabelledInterval(
                start=T0 + timedelta(minutes=100), end=T0 + timedelta(minutes=100), label="attack"
            )
        ],
    )

    with pytest.raises(DegenerateSplitError, match=r"calib slice.*is empty"):
        train_calib_test_split(sparse, DEFAULT_POLICY)


# ------------------------------------------------------------------------------------------------
# prefix_split: train_test_split that respects unscored time (ADR 0082)
# ------------------------------------------------------------------------------------------------


def unscored(start: int, end: int) -> LabelledInterval:
    return LabelledInterval(
        start=T0 + timedelta(minutes=start), end=T0 + timedelta(minutes=end), label="unscored"
    )


def test_prefix_split_stops_the_training_prefix_at_the_first_unscored_window() -> None:
    # A blind phase carries a perturbation the data cannot yet see; fitting on it would teach the
    # model the perturbation as normal.
    data = corpus(points=40, attacks=[(8, 12)]).model_copy(
        update={"unscored_intervals": [unscored(5, 7)]}
    )
    train, test = prefix_split(data, SplitPolicy(train_fraction=1.0))

    assert len(train.observations) == 5
    assert train.attack_intervals == []
    assert train.unscored_intervals == []
    assert test.unscored_intervals == [unscored(5, 7)]
    assert test.attack_intervals == data.attack_intervals
    # Normal time in the test half: minutes 5..39 span 34 min. Unscored 5-7 is 2 min and attack
    # 8-12 is 4 min (inclusive bounds measure end - start); they do not touch, so 34 - 6 = 28.
    assert test.normal_duration() == timedelta(minutes=28)


def test_prefix_split_is_train_test_split_when_nothing_is_unscored() -> None:
    data = corpus(points=100, attacks=[(80, 90)])
    policy = SplitPolicy(train_fraction=0.5)
    assert prefix_split(data, policy) == train_test_split(data, policy)


def test_three_way_split_does_not_count_unscored_points_as_normal() -> None:
    # Calib slice (minutes 40..69) holds an attack and is otherwise all unscored: no normal point.
    data = corpus(points=100, attacks=[(45, 46), (85, 86)]).model_copy(
        update={"unscored_intervals": [unscored(40, 44), unscored(47, 69)]}
    )
    with pytest.raises(DegenerateSplitError, match="no normal points"):
        train_calib_test_split(data, DEFAULT_POLICY)
