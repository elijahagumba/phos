"""The development-seed closure harness refuses every other seed and keeps attacks open."""

from datetime import timedelta
from pathlib import Path

import pytest

from phos.atlas.consistency import RESULT_NAME
from phos.atlas.consistency_windows import FROZEN_WINDOWS, windows_for_period
from phos.atlas.maintenance_closure import close_maintenance_alerts
from phos.eval.build_declaration import BUILD_DEVELOPMENT_SEEDS, SCORECARD
from phos.eval.maintenance_harness import (
    HARNESS_PRACTICE,
    MAINTENANCE_CLOSURE_BAR,
    REGRESSION_ROLE,
    SAMPLE_SECONDS,
    ClosureReport,
    ConsistencyReport,
    UndeclaredSeedError,
    alert_count_phrase,
    build_seed,
    score_consistency,
    score_development_closures,
    synthetic_scorecard,
)
from phos.synth.attacks.spec import AttackType
from phos.synth.maintenance import MaintenancePractice

LOG = Path(__file__).resolve().parents[2] / "eval_runs" / "log.jsonl"


def test_one_attack_alert_is_singular() -> None:
    """A count of one is not written as a plural."""
    assert alert_count_phrase(1) == "1 attack alert"
    assert alert_count_phrase(0) == "0 attack alerts"
    assert alert_count_phrase(27) == "27 attack alerts"


def test_practice_keeps_the_shipped_idle_share() -> None:
    """The interval is compressed so a short run has several jobs. The idle share is not."""
    assert HARNESS_PRACTICE.idle_share == MaintenancePractice().idle_share == 0.15
    assert HARNESS_PRACTICE.routine_interval == timedelta(hours=2)
    assert MAINTENANCE_CLOSURE_BAR == 0.70


def test_refuses_seeds_outside_the_development_block() -> None:
    for seed in (97101, 97120, 94001, 94020, 96001, 96999, 97000, 97021):
        with pytest.raises(UndeclaredSeedError):
            build_seed(seed)


def test_one_second_consistency_windows_are_the_frozen_set() -> None:
    assert SAMPLE_SECONDS == 1.0
    assert windows_for_period(SAMPLE_SECONDS) == FROZEN_WINDOWS


def test_seed_97001_closes_sanctioned_jobs_and_not_the_in_window_mimic() -> None:
    bundle = build_seed(97001)
    alerts = [item.alert for item in bundle.alerts]
    decisions = {item.alert_id: item for item in close_maintenance_alerts(alerts, bundle.records)}
    jobs = [item for item in bundle.alerts if item.role == "job"]
    closed_jobs = [item for item in jobs if decisions[item.alert.alert_id].closed]
    assert len(jobs) == bundle.orders
    assert len(closed_jobs) == bundle.sanctioning_orders
    assert bundle.sanctioning_orders > 0
    regression = next(item for item in bundle.alerts if item.role == REGRESSION_ROLE)
    regression_decision = decisions[regression.alert.alert_id]
    assert regression.kind == AttackType.MIMIC.value
    assert regression.alert.citations == ()
    assert regression_decision.closed is False
    assert regression_decision.reason == "no_citation"
    for decision in decisions.values():
        if decision.closed:
            assert decision.reason == "cited"
            assert decision.citation is not None
            assert decision.citation.startswith("sap-pm:")


def test_development_seeds_meet_the_closure_bar() -> None:
    report = score_development_closures()
    assert report.seeds == BUILD_DEVELOPMENT_SEEDS
    _assert_closure_contract(report)


def test_consistency_on_one_seed_uses_the_champion_name() -> None:
    """One seed, so the suite stays short. The measurement script scores all twenty."""
    before = LOG.stat().st_size if LOG.is_file() else None
    report = score_consistency((97001,))
    after = LOG.stat().st_size if LOG.is_file() else None
    assert after == before
    assert report.detector == RESULT_NAME == "atlas-v1-consistency"
    assert report.per_seed[0].detector == RESULT_NAME
    assert 0.0 <= report.catches_within_budget <= 1.0
    assert report.false_alerts_per_shift >= 0.0
    assert report.attacks == 4
    card = synthetic_scorecard(score_development_closures((97001,)), report, runtime_seconds=0.0)
    assert tuple(card) == SCORECARD


def _assert_closure_contract(report: ClosureReport) -> None:
    """The bar, the in-window MIMIC, and the sanctioning invariant, on whatever seeds were run."""
    assert report.maintenance_alerts > 0
    assert report.attack_alerts > 0
    assert report.mimic_alerts > 0
    assert report.maintenance_bar_met
    assert report.no_attack_closed
    assert report.attack_closed == 0
    assert report.mimic_closed == 0
    assert report.maintenance_closure_rate >= MAINTENANCE_CLOSURE_BAR
    assert report.maintenance_closed / report.maintenance_alerts >= MAINTENANCE_CLOSURE_BAR
    for row in report.per_seed:
        assert row.maintenance_closed == row.sanctioning_orders
        assert row.maintenance_alerts == row.orders
        assert row.attack_closed == 0
        assert row.mimic_closed == 0
        assert row.mimic_alerts == 2
        assert row.attack_alerts == 4
        assert row.regression_mimic_closed is False
        assert row.regression_mimic_closed_by_rival is (row.sanctioning_orders > 0)


def test_scorecard_marks_other_lanes_unmeasured() -> None:
    """A hand-built consistency row checks the cell shape without a second detector run."""
    closure = score_development_closures((97001,))
    consistency = ConsistencyReport(
        detector=RESULT_NAME,
        seeds=(97001,),
        attacks=4,
        attacks_caught=1,
        attacks_caught_on_target=1,
        catches_within_budget=0.25,
        catches_on_target=0.25,
        alerts=2,
        unexplained_alerts=0,
        false_alerts_per_shift=0.0,
        shifts=0.75,
        per_seed=(),
        caveat="fixture",
    )
    card = synthetic_scorecard(closure, consistency, runtime_seconds=1.5)
    assert tuple(card) == SCORECARD
    calibration = card["calibration"]
    assert isinstance(calibration, dict)
    assert calibration["measured"] is False
    closures = card["maintenance_closures"]
    assert isinstance(closures, dict)
    assert closures["attack_closed"] == 0
    assert closures["measured"] is True


def test_held_back_builder_refuses_a_development_seed() -> None:
    from phos.eval.maintenance_harness import UndeclaredSeedError, build_held_back_seed

    with pytest.raises(UndeclaredSeedError, match="97101-97120"):
        build_held_back_seed(97001)


def test_development_builder_still_refuses_a_held_back_seed() -> None:
    from phos.eval.maintenance_harness import UndeclaredSeedError, build_seed

    with pytest.raises(UndeclaredSeedError):
        build_seed(97101)
