"""Tests for observations, expected ranges, deviations and forecasts."""

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology.enums import Domain
from phos.ontology.observations import (
    Deviation,
    ExpectedRange,
    Forecast,
    ForecastMiss,
    Observation,
)

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)


def make_observation() -> Observation:
    return Observation(
        id="obs_000000000001",
        entity_ids=["ent_000000000001", "ent_000000000002"],
        feature="interpacket_interval_ms",
        value=48.0,
        timestamp=T0,
        domain=Domain.ATLAS,
        context={"protocol": "modbus"},
    )


def make_expected_range() -> ExpectedRange:
    return ExpectedRange(
        feature="interpacket_interval_ms",
        entity_id="ent_000000000001",
        low=95.0,
        high=105.0,
        mean=100.0,
        stddev=2.0,
        learned_from_window=(T0, T1),
    )


def make_deviation() -> Deviation:
    return Deviation(
        id="dev_000000000001",
        observation_id="obs_000000000001",
        expected=make_expected_range(),
        magnitude=26.0,
        timestamp=T0,
    )


def make_forecast() -> Forecast:
    return Forecast(
        id="fc_000000000001",
        entity_id="ent_000000000001",
        feature="interpacket_interval_ms",
        predicted_value=100.0,
        horizon=(T0, T1),
    )


def make_forecast_miss() -> ForecastMiss:
    return ForecastMiss(
        id="fc_000000000002",
        forecast_id="fc_000000000001",
        observed_value=48.0,
        error=-52.0,
        timestamp=T1,
    )


class TestObservation:
    def test_constructs_and_defaults(self) -> None:
        observation = make_observation()
        assert observation.feature == "interpacket_interval_ms"
        assert observation.value == 48.0
        assert observation.entity_ids == ["ent_000000000001", "ent_000000000002"]
        assert (
            Observation(
                entity_ids=["ent_1"], feature="f", value=1.0, timestamp=T0, domain=Domain.SENTIEL
            ).context
            == {}
        )

    def test_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            make_observation().value = 1.0  # type: ignore[misc]

    def test_requires_at_least_one_entity(self) -> None:
        with pytest.raises(ValidationError):
            Observation(entity_ids=[], feature="f", value=1.0, timestamp=T0, domain=Domain.ATLAS)

    def test_json_round_trip(self) -> None:
        observation = make_observation()
        assert Observation.model_validate_json(observation.model_dump_json()) == observation


class TestExpectedRange:
    def test_contains_is_inclusive(self) -> None:
        expected = make_expected_range()
        assert expected.contains(100.0) is True
        assert expected.contains(95.0) is True
        assert expected.contains(105.0) is True
        assert expected.contains(94.9) is False
        assert expected.contains(105.1) is False

    def test_zscore_hand_computed(self) -> None:
        expected = make_expected_range()  # mean 100.0, stddev 2.0
        assert expected.zscore(100.0) == 0.0
        assert expected.zscore(104.0) == 2.0
        assert expected.zscore(48.0) == -26.0

    def test_zscore_with_zero_stddev(self) -> None:
        constant = ExpectedRange(
            feature="cycle_time_ms",
            entity_id="ent_1",
            low=50.0,
            high=50.0,
            mean=50.0,
            stddev=0.0,
            learned_from_window=(T0, T1),
        )
        assert constant.zscore(50.0) == 0.0
        assert constant.zscore(51.0) == math.inf
        assert constant.zscore(49.0) == -math.inf

    def test_rejects_negative_stddev(self) -> None:
        with pytest.raises(ValidationError):
            ExpectedRange(
                feature="f",
                entity_id="ent_1",
                low=0.0,
                high=1.0,
                mean=0.5,
                stddev=-1.0,
                learned_from_window=(T0, T1),
            )

    def test_rejects_inverted_bounds(self) -> None:
        with pytest.raises(ValidationError, match="low"):
            ExpectedRange(
                feature="f",
                entity_id="ent_1",
                low=10.0,
                high=1.0,
                mean=5.0,
                stddev=1.0,
                learned_from_window=(T0, T1),
            )

    def test_rejects_inverted_window(self) -> None:
        with pytest.raises(ValidationError, match="window"):
            ExpectedRange(
                feature="f",
                entity_id="ent_1",
                low=0.0,
                high=1.0,
                mean=0.5,
                stddev=1.0,
                learned_from_window=(T1, T0),
            )

    def test_json_round_trip(self) -> None:
        expected = make_expected_range()
        assert ExpectedRange.model_validate_json(expected.model_dump_json()) == expected


class TestDeviation:
    def test_constructs(self) -> None:
        deviation = make_deviation()
        assert deviation.observation_id == "obs_000000000001"
        assert deviation.expected.mean == 100.0
        assert deviation.magnitude == 26.0

    def test_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            make_deviation().magnitude = 0.0  # type: ignore[misc]

    def test_rejects_negative_magnitude(self) -> None:
        with pytest.raises(ValidationError):
            Deviation(
                observation_id="obs_1",
                expected=make_expected_range(),
                magnitude=-0.1,
                timestamp=T0,
            )

    def test_json_round_trip(self) -> None:
        deviation = make_deviation()
        assert Deviation.model_validate_json(deviation.model_dump_json()) == deviation


class TestForecast:
    def test_constructs_and_defaults(self) -> None:
        forecast = make_forecast()
        assert forecast.predicted_value == 100.0
        assert forecast.horizon == (T0, T1)
        assert Forecast(
            entity_id="ent_1", feature="f", predicted_value=1.0, horizon=(T0, T1)
        ).id.startswith("fc_")

    def test_rejects_inverted_horizon(self) -> None:
        with pytest.raises(ValidationError, match="horizon"):
            Forecast(entity_id="ent_1", feature="f", predicted_value=1.0, horizon=(T1, T0))

    def test_json_round_trip(self) -> None:
        forecast = make_forecast()
        assert Forecast.model_validate_json(forecast.model_dump_json()) == forecast


class TestForecastMiss:
    def test_constructs_with_signed_error(self) -> None:
        miss = make_forecast_miss()
        assert miss.forecast_id == "fc_000000000001"
        assert miss.error == -52.0

    def test_default_id_uses_the_forecast_prefix(self) -> None:
        miss = ForecastMiss(forecast_id="fc_1", observed_value=1.0, error=1.0, timestamp=T0)
        assert miss.id.startswith("fc_")

    def test_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            make_forecast_miss().error = 0.0  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        miss = make_forecast_miss()
        assert ForecastMiss.model_validate_json(miss.model_dump_json()) == miss
