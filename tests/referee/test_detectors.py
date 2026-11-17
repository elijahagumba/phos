"""`phos.referee.detectors`: the Atlas adapter, the baseline path, and the third-party template."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from phos.atlas import MahalanobisModel, Subsystem, SubsystemMap
from phos.eval import Dataset, Detector
from phos.models import GaussianBaseline
from phos.ontology import Domain, Observation
from phos.reasoning import FittedPlattCalibrator
from phos.referee.detectors import (
    AtlasDetector,
    ThirdPartyDetectorTemplate,
    baseline_detector,
    leading_hypothesis,
)

ENTITY = "ent_test0000000001"
SIGNALS = ("FT01", "FT01Z", "PT01")
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
STEP = timedelta(seconds=30)


def _topology() -> SubsystemMap:
    return SubsystemMap(
        [
            Subsystem(
                subsystem_id="unit-a", label="Unit A", signals=frozenset(SIGNALS), source="test"
            )
        ],
        frozenset(SIGNALS),
    )


def _reading(signal: str, row: int) -> float:
    cycle = 100.0 + 5.0 * math.sin(row / 6.0)
    gains = {"FT01": 1.0, "FT01Z": 0.5, "PT01": -0.2}
    return gains[signal] * cycle


def _corpus(
    n_rows: int, *, surge: dict[str, float] | None = None, surge_rows: range = range(0)
) -> Dataset:
    observations: list[Observation] = []
    for row in range(n_rows):
        for column, signal in enumerate(SIGNALS):
            value = _reading(signal, row)
            if surge and row in surge_rows:
                value += surge.get(signal, 0.0)
            observations.append(
                Observation(
                    id=f"obs_r{row:05d}c{column:02d}",
                    entity_ids=[ENTITY],
                    feature=signal,
                    value=value,
                    timestamp=EPOCH + row * STEP,
                    domain=Domain.ATLAS,
                )
            )
    return Dataset(name="fixture", domain=Domain.ATLAS, observations=observations)


def _atlas_detector() -> AtlasDetector:
    fitted = MahalanobisModel().fit(_corpus(40).observations)
    calibrator = FittedPlattCalibrator(coefficient=0.1, intercept=0.0)
    return AtlasDetector(fitted=fitted, calibrator=calibrator, subsystem_map=_topology())


def test_satisfies_the_detector_protocol() -> None:
    assert isinstance(_atlas_detector(), Detector)


def test_run_returns_detections_for_a_disturbed_corpus() -> None:
    detector = _atlas_detector()
    disturbed = _corpus(
        60, surge={"FT01": 40.0, "FT01Z": 20.0, "PT01": -8.0}, surge_rows=range(40, 46)
    )

    detections = detector.run(disturbed)

    assert detections
    for detection in detections:
        assert 0.0 <= detection.confidence <= 1.0
        assert detection.score == detection.confidence


def test_run_populates_last_store_and_last_narratives() -> None:
    detector = _atlas_detector()
    disturbed = _corpus(
        60, surge={"FT01": 40.0, "FT01Z": 20.0, "PT01": -8.0}, surge_rows=range(40, 46)
    )

    detector.run(disturbed)

    assert detector.last_store is not None
    assert detector.last_narratives
    assert list(detector.last_store.narratives()) == list(detector.last_narratives)


def test_each_run_starts_from_a_fresh_store() -> None:
    """Scoring one plant must never leak evidence into the next plant's narratives."""
    detector = _atlas_detector()
    first = _corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0, "PT01": -8.0}, surge_rows=range(40, 46))
    quiet = _corpus(40)

    detector.run(first)
    assert detector.last_narratives

    detector.run(quiet)
    assert detector.last_narratives == ()
    # Nothing in a quiet corpus is promoted, so the fresh store this run built holds nothing
    # from the previous, disturbed run either.
    assert list(detector.last_store.observations()) == []  # type: ignore[union-attr]


def test_a_quiet_corpus_produces_no_detections() -> None:
    detector = _atlas_detector()
    assert detector.run(_corpus(40)) == []


def test_name_carries_the_model_and_calibrator() -> None:
    detector = _atlas_detector()
    assert detector.name == "atlas-referee:atlas-mahalanobis+platt"


def test_leading_hypothesis_breaks_ties_by_template_id_not_confidence_alone() -> None:
    """Two hypotheses tied on confidence resolve to the alphabetically-first template id."""
    from phos.ontology import Hypothesis, HypothesisStatus

    tied_a = Hypothesis(
        label="a",
        template_id="z_template",
        domain=Domain.ATLAS,
        prior=0.5,
        confidence=0.9,
        status=HypothesisStatus.ACTIVE,
    )
    tied_b = Hypothesis(
        label="b",
        template_id="a_template",
        domain=Domain.ATLAS,
        prior=0.5,
        confidence=0.9,
        status=HypothesisStatus.ACTIVE,
    )
    from phos.ontology import Narrative

    narrative = Narrative(
        title="t", domain=Domain.ATLAS, hypothesis_ids=[tied_a.id, tied_b.id], evidence_ids=[]
    )
    leader = leading_hypothesis(narrative, {tied_a.id: tied_a, tied_b.id: tied_b})
    assert leader is tied_b


def test_leading_hypothesis_returns_none_when_nothing_resolves() -> None:
    from phos.ontology import Narrative

    narrative = Narrative(
        title="t", domain=Domain.ATLAS, hypothesis_ids=["hyp_missing"], evidence_ids=[]
    )
    assert leading_hypothesis(narrative, {}) is None


def test_baseline_detector_wraps_a_fitted_model() -> None:
    # A per-signal Gaussian baseline has no notion of the plant's own correlation structure, so a
    # smoothly periodic corpus (`_corpus`'s shared sine wave) genuinely does look anomalous to it
    # at the extremes of the cycle — that is a property of this baseline, not a bug in the
    # adapter. A constant corpus isolates what this test actually checks: that `baseline_detector`
    # wraps a fitted model into something `phos.eval.Detector` can run, nothing more.
    constant = Dataset(
        name="constant",
        domain=Domain.ATLAS,
        observations=[
            Observation(
                id=f"obs_c{row:03d}",
                entity_ids=[ENTITY],
                feature="FT01",
                value=100.0,
                timestamp=EPOCH + row * STEP,
                domain=Domain.ATLAS,
            )
            for row in range(10)
        ],
    )
    fitted = GaussianBaseline().fit(constant.observations)
    detector = baseline_detector(fitted)
    assert isinstance(detector, Detector)
    assert detector.run(constant) == []


def test_third_party_template_is_structurally_a_detector() -> None:
    class Conforming(ThirdPartyDetectorTemplate):
        @property
        def name(self) -> str:
            return "conforming"

        def run(self, dataset: Dataset) -> list[object]:  # type: ignore[override]
            return []

    assert isinstance(Conforming(), Detector)


def test_third_party_template_itself_is_not_runnable() -> None:
    import pytest

    with pytest.raises(NotImplementedError):
        ThirdPartyDetectorTemplate().run(_corpus(1))
    with pytest.raises(NotImplementedError):
        _ = ThirdPartyDetectorTemplate().name
