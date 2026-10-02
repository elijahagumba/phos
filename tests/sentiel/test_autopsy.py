"""Budget-queue autopsy does not rewrite the frozen CERT 6B row."""

from datetime import UTC, datetime

from phos.sentiel.autopsy import (
    AUTOPSY_DETECTOR_NAME,
    FROZEN_SIX_B_DETECTOR_NAME,
    autopsy_budget_queue,
    features_for_stem,
    named_subset_detector_name,
    named_subset_policy,
    render_autopsy_markdown,
)
from phos.sentiel.entities import user_entity_id
from phos.sentiel.labels import EntityLabelledInterval
from phos.sentiel.scoring import FeatureContribution, ScoredWindow

START = datetime(2010, 7, 1, tzinfo=UTC)


def _contribution(feature: str, contribution: float) -> FeatureContribution:
    return FeatureContribution(
        feature=feature,
        value=1.0,
        magnitude=1.0,
        contribution=min(contribution, 1.0),
    )


def _window(user: str, score: float, feature: str, day: int) -> ScoredWindow:
    return ScoredWindow(
        entity_id=user_entity_id(user),
        timestamp=START.replace(day=day),
        score=score,
        contributions=(_contribution(feature, min(score, 1.0)),),
    )


def test_autopsy_never_reuses_the_frozen_six_b_detector_name() -> None:
    # Compared as `str` rather than as the two `Final` literals: mypy can prove the ADR 0065
    # invariant statically and reports the check as non-overlapping, but the runtime assertion
    # is the pin. Widening keeps the pin and keeps the type check clean.
    assert str(AUTOPSY_DETECTOR_NAME) != str(FROZEN_SIX_B_DETECTOR_NAME)
    labels = (
        EntityLabelledInterval(
            user_id="alice",
            start=START,
            end=START.replace(day=31),
            scenario="1",
            release="3.1",
        ),
    )
    report = autopsy_budget_queue(
        (_window("alice", 4.0, "removable_media_count", 2), _window("bob", 3.0, "logon_count", 2)),
        labels,
        budget=2,
    )
    assert report.detector_name == AUTOPSY_DETECTOR_NAME
    markdown = render_autopsy_markdown(report)
    assert AUTOPSY_DETECTOR_NAME in markdown
    assert "0.104" in markdown
    assert "not a replacement" in markdown.lower() or "not a replacement" in markdown


def test_budget_queue_ranks_by_score_and_splits_on_entity_labels() -> None:
    labels = (
        EntityLabelledInterval(
            user_id="alice",
            start=START,
            end=START.replace(day=10),
            scenario="1",
            release="3.1",
        ),
    )
    windows = (
        _window("bob", 9.0, "http_count", 2),
        _window("alice", 8.0, "removable_media_count", 2),
        _window("carol", 7.0, "http_count", 2),
    )
    report = autopsy_budget_queue(windows, labels, budget=2)
    assert report.true_positives == 1
    assert report.false_positives == 1
    stems = {row.stem: row for row in report.leading_stems}
    assert stems["removable_media_count"].true_positives == 1
    assert stems["http_count"].false_positives == 1
    assert report.dominant_true_positive_stem() == "removable_media_count"


def test_no_exclusive_stem_means_no_named_subset() -> None:
    labels = (
        EntityLabelledInterval(
            user_id="alice",
            start=START,
            end=START.replace(day=10),
            scenario="1",
            release="3.1",
        ),
    )
    windows = (
        _window("alice", 5.0, "logon_count", 2),
        _window("bob", 4.0, "logon_count", 2),
    )
    report = autopsy_budget_queue(windows, labels, budget=2)
    assert report.dominant_true_positive_stem() is None


def test_named_subset_name_cannot_overwrite_six_b_or_precision() -> None:
    name = named_subset_detector_name("removable_device_connects")
    assert name != FROZEN_SIX_B_DETECTOR_NAME
    assert "peer set (34 features)" not in name
    assert ":precision" not in name
    policy = named_subset_policy("removable_device_connects")
    assert policy.log_tag.startswith("autopsy-subset-")
    assert policy.log_suffix == ":autopsy-subset-removable_device_connects"
    features = features_for_stem(
        ("removable_device_connects", "removable_device_connects_peer", "logon_count"),
        "removable_device_connects",
    )
    assert features == frozenset({"removable_device_connects", "removable_device_connects_peer"})
