"""Library reasoning fixtures are not CERT (ADR 0029)."""

from __future__ import annotations

from phos.reasoning.fixtures import REASONING_FIXTURES, ranking_outcome, score_fixtures


def test_unknown_master_fixture_is_top_one() -> None:
    unknown = "fixture-unknown-master-write"
    fixture = next(item for item in REASONING_FIXTURES if item.incident_id == unknown)
    assert ranking_outcome(fixture) == "top-1"


def test_known_station_tie_fixture_abstains() -> None:
    known_tie = "fixture-known-station-tie"
    fixture = next(item for item in REASONING_FIXTURES if item.incident_id == known_tie)
    assert fixture.abstain is True
    assert ranking_outcome(fixture) == "abstention-when-correct"


def test_fixtures_are_not_a_cert_row() -> None:
    assert all(not item.incident_id.startswith("cert") for item in REASONING_FIXTURES)


def test_sensor_and_process_fixtures_are_top_one_and_scorecard_is_not_cert() -> None:
    sensor_id = "fixture-local-sensor-fault"
    sensor = next(item for item in REASONING_FIXTURES if item.incident_id == sensor_id)
    process = next(
        item for item in REASONING_FIXTURES if item.incident_id == "fixture-process-disturbance"
    )
    assert ranking_outcome(sensor) == "top-1"
    assert ranking_outcome(process) == "top-1"
    scorecard = score_fixtures()
    assert scorecard.n == 4
    assert scorecard.top_1 == 3
    assert scorecard.abstention_when_correct == 1
    assert scorecard.miss == 0
    assert scorecard.is_cert_row is False
