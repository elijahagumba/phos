"""Aggregated entity-window scoring: the floor PART 6A measured, reproduced and then removed.

PART 6A's finding was precise: a wide feature set scored one-alert-per-feature has an irreducible
floor of alerts clamped to `MAX_MAGNITUDE`, containing no true positive, that no threshold below
``1e6`` can exclude. Below that floor the enriched set is not worse than the narrow one, it is
unusable.

The fixture in ``TestTheFloor`` is built to reproduce exactly that failure — sparse features whose
per-``(user, feature)`` training slices never varied, firing once each in the test half — and the
tests then show the two mechanisms that remove it, separately, so it is clear which does what:

- **The unit of an alert.** One score per entity-window instead of one per feature per window, so a
  wider feature set adds evidence rather than multiplying alerts.
- **The missing scale.** A departure from a baseline with no spread is *unquantified*, not
  infinitely surprising, and is re-judged against the entity's own centre and the population's
  spread rather than saturating.

Nothing here is tuned to the fixture's insider. The properties asserted — a per-feature ceiling, a
monotone sum, a graded treatment of an unmeasurable departure — hold for every input, and the tests
say so by checking them on inputs that have no insider at all.
"""

import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from phos.eval import Dataset, Detection, Detector, EvalConfig
from phos.models import EwmaBaseline, GaussianBaseline, ModelDetector
from phos.models.base import MAX_MAGNITUDE, StaticRangeFittedModel
from phos.ontology import Domain, ExpectedRange, Observation
from phos.sentiel import (
    AggregatedDetector,
    AggregationPolicy,
    EntityLabelledInterval,
    PrecomputedDetector,
    ScoredWindow,
    ScoringSummary,
    WindowScorer,
    borrowed_scale_range,
    entity_aware_detections,
    evaluate_entity_aware,
    static_range_model,
    stream_scored_windows,
    user_entity_id,
)

START = datetime(2010, 1, 4, tzinfo=UTC)
TRAINING_WINDOW = (START, START + timedelta(days=40))


def _observation(user_id: str, day: int, feature: str, value: float, index: int = 0) -> Observation:
    """Return one per-``(user, day, feature)`` observation, in the shape the featuriser emits."""
    return Observation(
        id=f"obs_{user_id}_{day:03d}_{index:03d}",
        entity_ids=[user_entity_id(user_id)],
        feature=feature,
        value=value,
        timestamp=START + timedelta(days=day),
        domain=Domain.SENTIEL,
    )


def _range(mean: float, stddev: float, feature: str = "f", entity: str = "ent_A") -> ExpectedRange:
    """Return a learned range with the given centre and spread."""
    return ExpectedRange(
        feature=feature,
        entity_id=entity,
        low=mean - 3.0 * stddev,
        high=mean + 3.0 * stddev,
        mean=mean,
        stddev=stddev,
        learned_from_window=TRAINING_WINDOW,
    )


# ================================================================================================
# The bounded contribution — no single feature can dominate, whatever it does
# ================================================================================================


class TestNoSingleFeatureCanDominate:
    """The ceiling is structural: it holds for every input, including an infinite magnitude."""

    def _scored(self, values: dict[str, float], spreads: dict[str, float]) -> float:
        """Score one entity-window against hand-made baselines and return its aggregate."""
        model = GaussianBaseline(min_samples=2)
        training = [
            _observation("A", day, feature, mean + spreads[feature] * ((-1) ** day), index)
            for day in range(10)
            for index, (feature, mean) in enumerate(dict.fromkeys(values, 0.0).items())
        ]
        fitted = static_range_model(model.fit(training))
        window = [
            _observation("A", 50, feature, value, index)
            for index, (feature, value) in enumerate(values.items())
        ]
        scored = list(stream_scored_windows(window, fitted))
        return scored[0].score if scored else 0.0

    def test_one_clamped_feature_contributes_at_most_one(self) -> None:
        """A feature the model has no scale for cannot outweigh the whole rest of the window."""
        score = self._scored({"quiet": 0.0, "clamped": 900.0}, {"quiet": 1.0, "clamped": 0.0})
        assert 0.0 < score <= 1.0

    def test_several_measured_departures_outrank_one_unmeasurable_one(self) -> None:
        """The point of the ceiling: broad evidence beats one degenerate feature, always."""
        lone_clamp = self._scored(
            {"a": 0.0, "b": 0.0, "c": 0.0, "clamped": 900.0},
            {"a": 1.0, "b": 1.0, "c": 1.0, "clamped": 0.0},
        )
        broad = self._scored(
            {"a": 12.0, "b": 12.0, "c": 12.0, "clamped": 0.0},
            {"a": 1.0, "b": 1.0, "c": 1.0, "clamped": 0.0},
        )
        assert lone_clamp <= 1.0 < broad

    def test_the_score_is_bounded_by_the_number_of_features(self) -> None:
        values = dict.fromkeys("abcdef", 900.0)
        score = self._scored(values, dict.fromkeys("abcdef", 0.0))
        assert score <= len(values)

    def test_the_score_is_exactly_the_sum_of_its_stored_contributions(self) -> None:
        """Traceability: the number is reconstructable from its parts, not asserted."""
        model = GaussianBaseline(min_samples=2)
        fitted = static_range_model(
            model.fit(
                [
                    _observation("A", day, feature, float(day % 3), index)
                    for day in range(10)
                    for index, feature in enumerate(("a", "b", "c"))
                ]
            )
        )
        window = [_observation("A", 50, f, 20.0, i) for i, f in enumerate(("a", "b", "c"))]
        scored = next(iter(stream_scored_windows(window, fitted)))
        assert scored.score == pytest.approx(
            sum(item.contribution for item in scored.contributions)
        )
        assert scored.contributions[0].feature == scored.leading_feature

    def test_an_absurd_value_still_lands_under_the_ceiling(self) -> None:
        """Whatever a feature reports, an `Observation` and a report must be able to carry it."""
        score = self._scored({"a": 1e300}, {"a": 0.0})
        assert math.isfinite(score)
        assert score <= 1.0


# ================================================================================================
# The missing scale — a departure with no units is graded, not saturated
# ================================================================================================


class TestTheBorrowedScale:
    """A constant baseline means *unquantified*, not *infinitely surprising*."""

    def test_it_keeps_the_entitys_centre_and_takes_the_populations_spread(self) -> None:
        borrowed = borrowed_scale_range(_range(4.0, 0.0), _range(20.0, 5.0))
        assert borrowed.mean == 4.0
        assert borrowed.stddev == 5.0
        assert (borrowed.low, borrowed.high) == (4.0 - 15.0, 4.0 + 15.0), "band shape preserved"

    def test_it_spans_both_training_windows_so_the_evidence_says_what_it_read(self) -> None:
        own = _range(4.0, 0.0)
        population = ExpectedRange(
            feature="f",
            entity_id="ent_featurelevel",
            low=-5.0,
            high=25.0,
            mean=10.0,
            stddev=5.0,
            learned_from_window=(START - timedelta(days=5), START + timedelta(days=99)),
        )
        borrowed = borrowed_scale_range(own, population)
        assert borrowed.learned_from_window == (
            START - timedelta(days=5),
            START + timedelta(days=99),
        )

    def test_a_population_with_no_spread_offers_nothing_to_borrow(self) -> None:
        with pytest.raises(ValueError, match="no spread either"):
            borrowed_scale_range(_range(4.0, 0.0), _range(20.0, 0.0))

    def _sparse_fitted(self) -> tuple[Detector, GaussianBaseline]:
        """Fit a corpus where one user never varies a feature and the population does."""
        model = GaussianBaseline(min_samples=4)
        training = [
            _observation(user, day, "device_connects", 0.0 if user == "QUIET" else float(day % 5))
            for day in range(20)
            for user in ("QUIET", "BUSY", "OTHER", "MORE")
        ]
        return ModelDetector(fitted=model.fit(training)), model

    def _quiet_user_fitted(self) -> StaticRangeFittedModel:
        """Fit a corpus where QUIET never varies a feature and the population does."""
        return static_range_model(
            GaussianBaseline(min_samples=4).fit(
                [
                    _observation(
                        user, day, "device_connects", 0.0 if user == "QUIET" else float(day % 5)
                    )
                    for day in range(20)
                    for user in ("QUIET", "BUSY", "OTHER", "MORE")
                ]
            )
        )

    def test_the_old_shape_cannot_tell_the_two_departures_apart(self) -> None:
        """Never touching a thumb drive and then connecting one, or forty: the same alert."""
        fitted = self._quiet_user_fitted()
        for value in (1.0, 40.0):
            deviations = fitted.score([_observation("QUIET", 50, "device_connects", value)])
            assert deviations[0].magnitude == MAX_MAGNITUDE

    def test_an_ordinary_departure_from_a_constant_stops_being_an_alert(self) -> None:
        """One connection is under a population standard deviation, so it falls below the bar.

        This is the floor being removed one alert at a time, and it is the whole difference: the
        old shape reported this at the maximum, forever, with no threshold able to exclude it.
        """
        scored = list(
            stream_scored_windows(
                [_observation("QUIET", 50, "device_connects", 1.0)], self._quiet_user_fitted()
            )
        )
        assert scored[0].contributions == ()
        assert scored[0].score == 0.0

    def test_a_large_departure_from_a_constant_is_measured_rather_than_saturated(self) -> None:
        scored = list(
            stream_scored_windows(
                [_observation("QUIET", 50, "device_connects", 40.0)], self._quiet_user_fitted()
            )
        )
        contribution = scored[0].contributions[0]
        assert contribution.scale_borrowed
        assert 5.0 < contribution.magnitude < MAX_MAGNITUDE, "large, and finite, and measured"

    def test_turning_the_borrow_off_restores_the_saturation_it_replaces(self) -> None:
        """The mechanism named: with `borrow_population_scale` off, PART 6A's behaviour returns."""
        fitted = self._quiet_user_fitted()
        policy = AggregationPolicy(borrow_population_scale=False)
        scored = list(
            stream_scored_windows(
                [_observation("QUIET", 50, "device_connects", 1.0)], fitted, policy
            )
        )
        assert scored[0].contributions[0].magnitude == MAX_MAGNITUDE
        assert scored[0].contributions[0].unquantified

    def test_a_departure_nothing_can_scale_is_counted_rather_than_dropped(self) -> None:
        """No spread anywhere is a real departure and an unmeasured one. Both facts are recorded."""
        model = GaussianBaseline(min_samples=4)
        fitted = static_range_model(
            model.fit(
                [
                    _observation(user, day, "never_varies", 0.0)
                    for day in range(20)
                    for user in "ABCD"
                ]
            )
        )
        scorer = WindowScorer(fitted)
        scorer.push(_observation("A", 50, "never_varies", 3.0))
        scored = scorer.close()
        assert scored[0].contributions[0].unquantified
        assert scored[0].contributions[0].magnitude == MAX_MAGNITUDE
        summary = scorer.summary()
        assert summary.unquantified == 1
        assert "UNMEASURED" in summary.note()

    def test_a_feature_training_never_saw_is_skipped_not_alerted_on(self) -> None:
        """`resolve_range`'s existing rule, carried through unchanged: unknown is not anomalous."""
        model = GaussianBaseline(min_samples=4)
        fitted = static_range_model(
            model.fit([_observation("A", day, "known", float(day % 3)) for day in range(20)])
        )
        scorer = WindowScorer(fitted)
        scorer.push(_observation("A", 50, "brand_new_feature", 9_999.0))
        scored = scorer.close()
        assert scored[0].score == 0.0
        assert scorer.summary().unmodelled == 1


# ================================================================================================
# The floor: reproduced under the old shape, removed under the new one
# ================================================================================================

USERS = 100
TRAIN_DAYS = 40
TEST_DAYS = 20
DENSE = ("bytes_out", "logon_count", "file_access_count", "distinct_pcs", "hosts", "mails")
SPARSE = tuple(f"sparse_{index:02d}" for index in range(12))
INSIDER = "USER007"
INSIDER_DAYS = (TRAIN_DAYS + 17, TRAIN_DAYS + 18, TRAIN_DAYS + 19)
DORMANT_FIRING_DAYS = 15
"""Dormant pairs fire only in the first fifteen test days.

So that no clamped alert can land inside the labelled window by coincidence: PART 6A's floor
contained *no* true positive, and a fixture whose floor accidentally caught the insider would not
be reproducing it.
"""


def _is_dormant(user: int, feature: int) -> bool:
    """Whether this ``(user, sparse feature)`` pair never varies in training.

    Two thirds of them, deliberately: PART 6A's enrichments are sparse by construction — a ``_dev``
    is a documented neutral throughout cold start, and ``new_pcs``, ``_diff`` and ``_trend`` are
    zero on most days for most people — so most training slices really are constant.
    """
    return (user + feature) % 3 != 0


def _corpus() -> tuple[Dataset, Dataset, list[EntityLabelledInterval]]:
    """Return ``(training, test, labels)`` for a corpus that reproduces PART 6A's failure.

    Deterministic by construction rather than by seed: every value is a function of the user index,
    the day and the feature index, so the floor below has an exact, checkable size.
    """
    training: list[Observation] = []
    test: list[Observation] = []
    for day in range(TRAIN_DAYS + TEST_DAYS):
        rows = training if day < TRAIN_DAYS else test
        for user in range(USERS):
            user_id = f"USER{user:03d}"
            insider_day = user_id == INSIDER and day in INSIDER_DAYS
            index = 0
            for position, feature in enumerate(DENSE):
                # A dense feature always varies, so its baseline has a spread and its departures
                # are measurable. The insider's are eight of those spreads, across every one.
                base = 100.0 + 10.0 * position + ((day * 7 + user * 3 + position) % 5)
                rows.append(
                    _observation(
                        user_id, day, feature, base + (40.0 if insider_day else 0.0), index
                    )
                )
                index += 1
            for position, feature in enumerate(SPARSE):
                if _is_dormant(user, position):
                    # Constant zero throughout training, then exactly one firing in the test half:
                    # one clamped, unremovable, false alert per dormant pair.
                    fires = day == TRAIN_DAYS + ((user * 7 + position) % DORMANT_FIRING_DAYS)
                    value = 1.0 if fires else 0.0
                else:
                    value = 1.0 if (day + user + position) % 7 == 0 else 0.0
                rows.append(_observation(user_id, day, feature, value, index))
                index += 1

    labels = [
        EntityLabelledInterval(
            user_id=INSIDER,
            start=START + timedelta(days=INSIDER_DAYS[0]),
            end=START + timedelta(days=INSIDER_DAYS[-1], hours=23),
            scenario="fixture",
            release="fixture",
        )
    ]
    return (
        Dataset(name="floor-train", domain=Domain.SENTIEL, observations=training),
        Dataset(name="floor-test", domain=Domain.SENTIEL, observations=test),
        labels,
    )


DORMANT_PAIRS = sum(
    1 for user in range(USERS) for position in range(len(SPARSE)) if _is_dormant(user, position)
)


@pytest.fixture(scope="module")
def floor_corpus() -> tuple[Dataset, Dataset, list[EntityLabelledInterval]]:
    return _corpus()


def _alerts(detections: list[Detection], threshold: float) -> list[Detection]:
    return [detection for detection in detections if detection.score >= threshold]


def _hits(detections: list[Detection], labels: list[EntityLabelledInterval]) -> int:
    return len(entity_aware_detections(detections, labels)[0])


class TestTheFloor:
    """The measured failure of PART 6A, reproduced here so its removal is demonstrable."""

    def test_the_old_shape_has_an_irreducible_floor_of_false_alerts(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        """One alert per feature per window, and a per-key Gaussian with nothing to divide by."""
        training, test, labels = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        detections = ModelDetector(fitted=fitted).run(test)

        floor = _alerts(detections, MAX_MAGNITUDE)
        assert len(floor) == DORMANT_PAIRS, "one clamped alert per never-varying training slice"
        assert DORMANT_PAIRS > 500, "the fixture must reproduce a floor worth calling a floor"
        assert _hits(floor, labels) == 0, "and not one of them is a true positive"

        for threshold in (10.0, 100.0, 1_000.0, 100_000.0):
            assert len(_alerts(detections, threshold)) >= len(floor), (
                "no threshold below MAX_MAGNITUDE can remove them"
            )

    def test_the_aggregated_shape_reaches_a_hundreds_level_budget_and_keeps_the_signal(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        """The floor removed: an achievable budget in the hundreds that still holds the insider.

        The threshold below is not fitted to the insider; it is the point at which the alert count
        first falls into the hundreds, found by sweeping and reported rather than chosen. What is
        asserted is the property — that such a point exists at all, which under the old shape it
        does not.
        """
        training, test, labels = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        detections = AggregatedDetector(fitted=fitted).run(test)

        assert len(detections) == USERS * TEST_DAYS, (
            "one detection per entity-window, not per feature"
        )

        budgets = {
            threshold: _alerts(detections, threshold)
            for threshold in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0)
        }
        reachable = [
            (threshold, alerts) for threshold, alerts in budgets.items() if len(alerts) < 1_000
        ]
        assert reachable, "a wide feature set must be thresholdable below the old floor"
        _, alerts = min(reachable, key=lambda item: len(item[1]))
        assert len(alerts) < DORMANT_PAIRS, "strictly quieter than the old shape's floor"
        assert _hits(alerts, labels) > 0, "and the insider is still in it"

    def test_a_window_whose_only_evidence_is_one_dormant_feature_is_not_top_ranked(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        """The floor's alerts are still *present* — they are just no longer unbeatable."""
        training, test, labels = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        detections = AggregatedDetector(fitted=fitted).run(test)
        ranked = sorted(detections, key=lambda item: -item.score)
        insider_ranks = [
            position
            for position, detection in enumerate(ranked)
            if entity_aware_detections([detection], labels)[0]
        ]
        assert insider_ranks and max(insider_ranks) < len(INSIDER_DAYS) * 4, (
            "a broad, measured anomaly outranks every window carrying one unmeasurable feature"
        )


# ================================================================================================
# Ontology cleanliness and the reuse of the layers below — acceptance criterion 5
# ================================================================================================


class TestItPlugsIntoWhatAlreadyExists:
    """The aggregated detector is an ordinary PART 2 detector and nothing below it changed."""

    def test_it_satisfies_the_detector_protocol(self) -> None:
        fitted = static_range_model(
            GaussianBaseline(min_samples=2).fit(
                [_observation("A", day, "f", float(day % 4)) for day in range(10)]
            )
        )
        detector = AggregatedDetector(fitted=fitted)
        assert isinstance(detector, Detector)
        assert detector.name == "aggregate:gaussian"

    def test_the_entity_aware_evaluation_scores_it_unchanged(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        training, test, labels = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        report = evaluate_entity_aware(
            AggregatedDetector(fitted=fitted),
            test,
            labels,
            EvalConfig(alert_threshold=2.0, match_tolerance=timedelta(0), seed=7),
        )
        assert report.detector_name == "aggregate:gaussian"
        assert report.n_detections == USERS * TEST_DAYS
        assert 0.0 <= report.precision <= 1.0

    def test_a_precomputed_detector_returns_what_the_aggregated_one_would_have(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        """The streamed path a corpus too big to hold must take, against the direct one."""
        training, test, _ = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        direct = AggregatedDetector(fitted=fitted).run(test)

        scorer = WindowScorer(fitted)
        streamed: list[Detection] = []
        for observation in test.observations:
            streamed += [w.as_detection(3.0) for w in scorer.push(observation)]
        streamed += [w.as_detection(3.0) for w in scorer.close()]

        precomputed = PrecomputedDetector(name="aggregate:gaussian", detections=streamed)
        assert precomputed.run(test) == direct

    def test_every_detection_names_its_entity_and_its_window(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        training, test, _ = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        detections = AggregatedDetector(fitted=fitted).run(test)
        stamps = {observation.timestamp for observation in test.observations}
        for detection in detections:
            assert len(detection.entity_ids) == 1
            assert detection.timestamp in stamps
            assert 0.0 <= detection.confidence <= 1.0
            assert math.isfinite(detection.score)

    def test_it_is_deterministic(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        training, test, _ = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        assert AggregatedDetector(fitted=fitted).run(test) == AggregatedDetector(fitted=fitted).run(
            test
        )

    def test_the_summary_totals_the_evidence_so_two_subsets_can_be_compared(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        """Whether the extra features earned their place becomes a measurement here."""
        training, test, _ = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        whole, narrow = (
            self._summary(fitted, test, features) for features in (None, frozenset(DENSE))
        )
        assert whole.total_score > narrow.total_score
        assert whole.total_score == pytest.approx(
            sum(d.score for d in AggregatedDetector(fitted=fitted).run(test)), rel=1e-9
        )

    @staticmethod
    def _summary(
        fitted: StaticRangeFittedModel, test: Dataset, features: frozenset[str] | None
    ) -> ScoringSummary:
        scorer = WindowScorer(fitted, features=features)
        for observation in test.observations:
            scorer.push(observation)
        scorer.close()
        return scorer.summary()

    def test_scoring_a_subset_of_features_uses_the_same_fitted_model(
        self, floor_corpus: tuple[Dataset, Dataset, list[EntityLabelledInterval]]
    ) -> None:
        """One corpus read, two feature sets, one model: how "did the extra features help?"."""
        training, test, _ = floor_corpus
        fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training.observations))
        whole = AggregatedDetector(fitted=fitted).run(test)
        narrow = AggregatedDetector(fitted=fitted, features=frozenset(DENSE)).run(test)
        assert len(whole) == len(narrow)
        assert sum(d.score for d in narrow) < sum(d.score for d in whole)


class TestAnOrderDependentModelIsRefused:
    """A scorer that restarted an EWMA at every window would look fine and mean nothing."""

    def test_an_ewma_cannot_be_aggregated(self) -> None:
        fitted = EwmaBaseline(min_samples=2).fit(
            [_observation("A", day, "f", float(day % 4)) for day in range(10)]
        )
        with pytest.raises(TypeError, match="judges observations in sequence"):
            static_range_model(fitted)

    def test_a_gaussian_passes_through_unchanged(self) -> None:
        fitted = GaussianBaseline(min_samples=2).fit(
            [_observation("A", day, "f", float(day % 4)) for day in range(10)]
        )
        assert static_range_model(fitted) is fitted


class TestTheStreamIsGuarded:
    def test_an_out_of_order_stream_is_refused(self) -> None:
        fitted = static_range_model(
            GaussianBaseline(min_samples=2).fit(
                [_observation("A", day, "f", float(day % 4)) for day in range(10)]
            )
        )
        scorer = WindowScorer(fitted)
        scorer.push(_observation("A", 20, "f", 1.0))
        with pytest.raises(ValueError, match="time-ordered"):
            scorer.push(_observation("A", 19, "f", 1.0))

    def test_an_empty_stream_scores_nothing(self) -> None:
        fitted = static_range_model(
            GaussianBaseline(min_samples=2).fit(
                [_observation("A", day, "f", float(day % 4)) for day in range(10)]
            )
        )
        assert list(stream_scored_windows(iter([]), fitted)) == []

    def test_windows_come_out_in_time_then_entity_order(self) -> None:
        fitted = static_range_model(
            GaussianBaseline(min_samples=2).fit(
                [
                    _observation(user, day, "f", float(day % 4))
                    for day in range(10)
                    for user in ("A", "B")
                ]
            )
        )
        stream: Iterator[Observation] = iter(
            [
                _observation("B", 20, "f", 9.0),
                _observation("A", 20, "f", 9.0),
                _observation("A", 21, "f", 9.0),
            ]
        )
        scored = list(stream_scored_windows(stream, fitted))
        assert [(w.entity_id, w.timestamp) for w in scored] == [
            (user_entity_id("A"), START + timedelta(days=20)),
            (user_entity_id("B"), START + timedelta(days=20)),
            (user_entity_id("A"), START + timedelta(days=21)),
        ]


class TestPrecisionPolicy:
    """Opt-in discounts: identity by default, and each lever does one named thing."""

    def _window(
        self, values: dict[str, float], policy: AggregationPolicy | None = None
    ) -> ScoredWindow:
        """Score one entity-window against hand-made per-feature baselines."""
        model = GaussianBaseline(min_samples=2)
        training = [
            _observation("A", day, feature, 10.0 + ((-1) ** day), index)
            for day in range(10)
            for index, feature in enumerate(values)
        ]
        fitted = static_range_model(model.fit(training))
        window = [
            _observation("A", 50, feature, value, index)
            for index, (feature, value) in enumerate(values.items())
        ]
        scored = list(stream_scored_windows(window, fitted, policy))
        assert len(scored) == 1
        return scored[0]

    def test_the_default_policy_is_the_part_6b_scorer(self) -> None:
        """A 6B number must not move because a later PART added knobs."""
        values = {"logon_count": 30.0, "file_access_count": 30.0}
        assert self._window(values).score == pytest.approx(
            self._window(values, AggregationPolicy()).score
        )

    def test_a_stem_weight_scales_the_count_and_its_dev_companion(self) -> None:
        full = self._window({"file_access_count": 30.0, "file_access_count_dev": 30.0})
        halved = self._window(
            {"file_access_count": 30.0, "file_access_count_dev": 30.0},
            AggregationPolicy(stem_weights={"file_access_count": 0.5}),
        )
        assert halved.score == pytest.approx(0.5 * full.score)
        assert all(item.contribution <= 0.5 + 1e-12 for item in halved.contributions)

    def test_an_exact_feature_weight_wins_over_the_stem(self) -> None:
        scored = self._window(
            {"file_access_count": 30.0},
            AggregationPolicy(
                stem_weights={"file_access_count": 0.5},
                feature_weights={"file_access_count": 0.25},
            ),
        )
        raw = self._window({"file_access_count": 30.0})
        assert scored.score == pytest.approx(0.25 * raw.score)

    def test_matching_peers_discounts_a_self_relative_departure(self) -> None:
        """Unlike themselves, like their group: the window stays in the stream, ranked down."""
        values = {"logon_count_dev": 30.0, "logon_count_peer": 10.0}
        full = self._window(values, AggregationPolicy())
        discounted = self._window(values, AggregationPolicy(peer_match_factor=0.25))
        assert discounted.score == pytest.approx(0.25 * full.score)
        assert not any(item.feature.endswith("_peer") for item in discounted.contributions)

    def test_an_out_of_band_peer_feature_is_not_a_match(self) -> None:
        values = {"logon_count_dev": 30.0, "logon_count_peer": 30.0}
        full = self._window(values, AggregationPolicy())
        same = self._window(values, AggregationPolicy(peer_match_factor=0.25))
        assert same.score == pytest.approx(full.score)

    def test_no_peer_measurement_is_not_treated_as_a_match(self) -> None:
        """A user with no group is not 'like their peers'; the group was never observed."""
        values = {"logon_count_dev": 30.0}
        full = self._window(values, AggregationPolicy())
        same = self._window(values, AggregationPolicy(peer_match_factor=0.25))
        assert same.score == pytest.approx(full.score)

    def test_a_thumb_drive_onset_is_not_buried_by_a_peer_match(self) -> None:
        values = {"removable_device_connects": 30.0, "logon_count_peer": 10.0}
        full = self._window(values, AggregationPolicy())
        kept = self._window(
            values,
            AggregationPolicy(
                peer_match_factor=0.25, high_signal_stems=("removable_device_connects",)
            ),
        )
        assert kept.score == pytest.approx(full.score)

    def test_a_single_family_window_is_discounted_until_a_second_family_fires(self) -> None:
        policy = AggregationPolicy(min_out_of_band_families=2, single_family_factor=0.2)
        lone = self._window({"logon_count": 30.0}, policy)
        full_lone = self._window({"logon_count": 30.0})
        both = self._window({"logon_count": 30.0, "file_access_count": 30.0}, policy)
        full_both = self._window({"logon_count": 30.0, "file_access_count": 30.0})
        assert lone.score == pytest.approx(0.2 * full_lone.score)
        assert both.score == pytest.approx(full_both.score)

    def test_removable_device_onset_bypasses_the_family_gate(self) -> None:
        policy = AggregationPolicy(
            min_out_of_band_families=2,
            single_family_factor=0.2,
            high_signal_stems=("removable_device_connects",),
        )
        full = self._window({"removable_device_connects": 30.0})
        kept = self._window({"removable_device_connects": 30.0}, policy)
        assert kept.score == pytest.approx(full.score)

    def test_precision_policy_is_opt_in_and_names_itself_on_the_log(self) -> None:
        from phos.sentiel import precision_policy

        policy = precision_policy()
        assert policy.log_suffix == ":precision"
        assert AggregationPolicy().log_suffix == ""
        assert policy.peer_match_factor < 1.0
        assert policy.min_out_of_band_families > 1
        assert policy.chronic_volume_halflife_days is None

    def test_chronic_volume_leaves_the_first_unusual_day_intact(self) -> None:
        policy = AggregationPolicy(chronic_volume_halflife_days=2.0)
        full = self._window({"file_access_count": 30.0})
        first = self._window({"file_access_count": 30.0}, policy)
        assert first.score == pytest.approx(full.score)

    def test_chronic_volume_decays_a_repeated_backup_and_not_a_thumb_drive(self) -> None:
        """Day two of the same file-copy pattern is quieter; a device onset is not."""
        policy = AggregationPolicy(chronic_volume_halflife_days=1.0)
        model = GaussianBaseline(min_samples=2)
        training = [
            _observation("A", day, feature, 10.0 + ((-1) ** day), index)
            for day in range(10)
            for index, feature in enumerate(("file_access_count", "removable_device_connects"))
        ]
        fitted = static_range_model(model.fit(training))
        volume = [
            _observation("A", 50, "file_access_count", 30.0, 0),
            _observation("A", 51, "file_access_count", 30.0, 0),
        ]
        scored = list(stream_scored_windows(volume, fitted, policy))
        assert len(scored) == 2
        assert scored[1].score == pytest.approx(0.5 * scored[0].score)
        device = [
            _observation("A", 50, "removable_device_connects", 30.0, 0),
            _observation("A", 51, "removable_device_connects", 30.0, 0),
        ]
        device_scored = list(stream_scored_windows(device, fitted, policy))
        assert device_scored[1].score == pytest.approx(device_scored[0].score)

    def test_chronic_precision_policy_retags_the_detector(self) -> None:
        from phos.sentiel import precision_policy

        assert precision_policy(chronic_volume_halflife_days=4.0).log_suffix == ":precision-chronic"
        assert precision_policy().log_suffix == ":precision"

    def test_a_weight_outside_zero_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"\(0, 1]"):
            AggregationPolicy(stem_weights={"file_access_count": 0.0})
        with pytest.raises(ValueError, match=r"\(0, 1]"):
            AggregationPolicy(feature_weights={"file_access_count": 1.5})

    def test_the_score_still_equals_the_sum_of_its_contributions(self) -> None:
        from phos.sentiel import precision_policy

        scored = self._window(
            {"logon_count": 30.0, "file_access_count": 30.0, "logon_count_peer": 10.0},
            precision_policy(),
        )
        assert scored.score == pytest.approx(
            sum(item.contribution for item in scored.contributions)
        )
