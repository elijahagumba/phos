"""Tests for command-behaviour features: hand-computed values, sparsity, provenance, determinism."""

from collections.abc import Callable
from datetime import timedelta

import pytest

from phos.atlas.packet import Direction, FunctionCode, MalformedFrame, ModbusMessage
from phos.atlas.packet.behaviour import (
    COMMAND_BASELINE_CAVEATS,
    COMMAND_COUNT,
    COMMAND_INTERVAL_CV,
    COMMAND_INTERVAL_MEAN_MS,
    DISTINCT_WRITE_ADDRESSES,
    REGISTER_WRITE_VALUE_MAX,
    REGISTER_WRITE_VALUE_MEAN,
    REGISTER_WRITE_VALUE_MIN,
    WRITE_ADDRESS_MAX,
    WRITE_ADDRESS_MIN,
    WRITE_COMMAND_SHARE,
    CommandFeaturePolicy,
    featurise_commands,
    function_count_feature,
)
from phos.atlas.packet.commands import CommandStreamStats, device_entity_id
from phos.atlas.packet.dissect import DissectionResult
from phos.models import GaussianBaseline, model_key
from phos.ontology import Domain, Observation

from .conftest import (
    DEFAULT_CAPTURE,
    EPOCH,
    ISSUER_IP,
    command_series,
    make_modbus_message,
)

ONE_MINUTE = timedelta(minutes=1)
ISSUER = device_entity_id(ISSUER_IP)

# 121 commands one second apart span exactly two minutes, which tiles into two whole windows of
# sixty commands each. The 121st sits on the boundary of a third window that the span does not
# cover, so it is dropped — see `tile_windows`.
TWO_WINDOW_COUNT = 121
PER_WINDOW = 60


def features_for(observations: list[Observation], window_index: int = 0) -> dict[str, float]:
    """Return ``{feature: value}`` for one window, keyed by the window's start timestamp."""
    start = EPOCH + ONE_MINUTE * window_index
    return {o.feature: o.value for o in observations if o.timestamp == start}


class TestVolumeAndFrequency:
    def test_a_known_rhythm_yields_the_hand_computed_counts(self) -> None:
        # Three reads to every write, one command a second, for two minutes.
        messages = command_series(
            TWO_WINDOW_COUNT,
            function_codes=(
                FunctionCode.READ_HOLDING_REGISTERS,
                FunctionCode.READ_HOLDING_REGISTERS,
                FunctionCode.READ_HOLDING_REGISTERS,
                FunctionCode.WRITE_SINGLE_REGISTER,
            ),
        )
        window = features_for(featurise_commands(messages))

        assert window[COMMAND_COUNT] == PER_WINDOW
        assert window[function_count_feature(FunctionCode.READ_HOLDING_REGISTERS)] == 45
        assert window[function_count_feature(FunctionCode.WRITE_SINGLE_REGISTER)] == 15
        assert window[WRITE_COMMAND_SHARE] == pytest.approx(0.25)

    def test_both_whole_windows_are_featured_and_the_partial_tail_is_not(self) -> None:
        observations = featurise_commands(command_series(TWO_WINDOW_COUNT))
        starts = sorted({o.timestamp for o in observations})

        assert starts == [EPOCH, EPOCH + ONE_MINUTE]
        assert features_for(observations, 1)[COMMAND_COUNT] == PER_WINDOW

    def test_features_are_keyed_to_the_issuing_device(self) -> None:
        observations = featurise_commands(command_series(TWO_WINDOW_COUNT))
        assert {tuple(o.entity_ids) for o in observations} == {(ISSUER,)}
        assert {o.domain for o in observations} == {Domain.ATLAS}

    def test_two_devices_are_featured_independently(self) -> None:
        busy = command_series(TWO_WINDOW_COUNT, src_ip="10.0.0.9")
        quiet = command_series(
            TWO_WINDOW_COUNT // 4,
            src_ip="10.0.0.11",
            interval=timedelta(seconds=4),
            first_frame_index=1000,
        )
        observations = featurise_commands([*busy, *quiet])

        counts = {
            o.entity_ids[0]: o.value
            for o in observations
            if o.feature == COMMAND_COUNT and o.timestamp == EPOCH
        }
        assert counts[device_entity_id("10.0.0.9")] == PER_WINDOW
        assert counts[device_entity_id("10.0.0.11")] == 15

    def test_a_function_the_device_did_not_issue_this_window_counts_zero_not_nothing(self) -> None:
        # A device that polls all day and writes in one window only: every other window must say
        # "zero writes", because a measured zero is what makes the one write visible as a change.
        polls = command_series(TWO_WINDOW_COUNT)
        write = make_modbus_message(
            FunctionCode.WRITE_SINGLE_REGISTER,
            timestamp=EPOCH + timedelta(seconds=90),
            frame_index=500,
        )
        observations = featurise_commands([*polls, write])
        write_feature = function_count_feature(FunctionCode.WRITE_SINGLE_REGISTER)

        assert features_for(observations, 0)[write_feature] == 0.0
        assert features_for(observations, 1)[write_feature] == 1.0

    def test_a_zero_is_only_claimed_for_a_window_the_device_was_active_in(self) -> None:
        # Silence is the graph's business. A device absent from a window cannot be distinguished
        # from a device that was never on this wire, so nothing is emitted for it.
        early = command_series(PER_WINDOW, first_frame_index=0)
        late = command_series(
            PER_WINDOW,
            src_ip="10.0.0.11",
            start=EPOCH + ONE_MINUTE,
            first_frame_index=1000,
        )
        observations = featurise_commands([*early, *late])
        first_window = {o.entity_ids[0] for o in observations if o.timestamp == EPOCH}

        assert first_window == {ISSUER}


class TestWriteTargetBehaviour:
    def _writes(self) -> list[ModbusMessage]:
        # Sixty writes a second apart across two minutes: addresses 40, 41, 42 in rotation, and
        # values that climb so min, max and mean are all distinct and hand-checkable.
        return [
            make_modbus_message(
                FunctionCode.WRITE_SINGLE_REGISTER,
                timestamp=EPOCH + timedelta(seconds=index),
                frame_index=index,
                reference_address=40 + index % 3,
                values=(index,),
            )
            for index in range(TWO_WINDOW_COUNT)
        ]

    def test_the_written_address_span_is_reported(self) -> None:
        window = features_for(featurise_commands(self._writes()))

        assert window[DISTINCT_WRITE_ADDRESSES] == 3
        assert window[WRITE_ADDRESS_MIN] == 40
        assert window[WRITE_ADDRESS_MAX] == 42

    def test_the_written_value_range_is_reported(self) -> None:
        window = features_for(featurise_commands(self._writes()))

        assert window[REGISTER_WRITE_VALUE_MIN] == 0
        assert window[REGISTER_WRITE_VALUE_MAX] == 59
        assert window[REGISTER_WRITE_VALUE_MEAN] == pytest.approx(29.5)

    def test_every_value_of_a_multi_register_write_counts(self) -> None:
        messages = [
            make_modbus_message(
                FunctionCode.WRITE_MULTIPLE_REGISTERS,
                timestamp=EPOCH + timedelta(seconds=index),
                frame_index=index,
                reference_address=40,
                quantity=3,
                values=(10, 20, 30),
            )
            for index in range(TWO_WINDOW_COUNT)
        ]
        window = features_for(featurise_commands(messages))

        assert window[REGISTER_WRITE_VALUE_MIN] == 10
        assert window[REGISTER_WRITE_VALUE_MAX] == 30
        assert window[REGISTER_WRITE_VALUE_MEAN] == pytest.approx(20.0)

    def test_a_coil_write_reports_its_address_but_not_a_value_range(self) -> None:
        # 0xFF00 means "on" and would land three orders of magnitude from a register value. The
        # address features still describe what was touched; see REGISTER_WRITE_FUNCTIONS.
        messages = [
            make_modbus_message(
                FunctionCode.WRITE_SINGLE_COIL,
                timestamp=EPOCH + timedelta(seconds=index),
                frame_index=index,
                reference_address=17,
                values=(0xFF00,),
            )
            for index in range(TWO_WINDOW_COUNT)
        ]
        window = features_for(featurise_commands(messages))

        assert window[WRITE_ADDRESS_MIN] == 17
        assert window[DISTINCT_WRITE_ADDRESSES] == 1
        assert REGISTER_WRITE_VALUE_MAX not in window
        assert REGISTER_WRITE_VALUE_MEAN not in window

    def test_a_device_that_only_reads_reports_no_write_features(self) -> None:
        window = features_for(featurise_commands(command_series(TWO_WINDOW_COUNT)))

        assert window[WRITE_COMMAND_SHARE] == 0.0
        assert WRITE_ADDRESS_MIN not in window
        assert DISTINCT_WRITE_ADDRESSES not in window

    def test_a_write_without_an_address_contributes_no_address_features(self) -> None:
        # P1 leaves reference_address None where the wire did not carry one. Substituting a zero
        # would put a device on register 0 it never touched.
        messages = [
            make_modbus_message(
                FunctionCode.WRITE_SINGLE_REGISTER,
                timestamp=EPOCH + timedelta(seconds=index),
                frame_index=index,
                reference_address=None,
                values=(5,),
            )
            for index in range(TWO_WINDOW_COUNT)
        ]
        window = features_for(featurise_commands(messages))

        assert WRITE_ADDRESS_MIN not in window
        assert DISTINCT_WRITE_ADDRESSES not in window
        assert window[REGISTER_WRITE_VALUE_MIN] == 5


class TestTiming:
    def test_a_perfectly_periodic_poller_has_zero_timing_spread(self) -> None:
        window = features_for(featurise_commands(command_series(TWO_WINDOW_COUNT)))

        assert window[COMMAND_INTERVAL_MEAN_MS] == pytest.approx(1000.0)
        assert window[COMMAND_INTERVAL_CV] == pytest.approx(0.0)

    def test_a_jittery_device_has_a_positive_coefficient_of_variation(self) -> None:
        # Gaps of 1s, 3s, 1s, 3s: mean 2000ms, spread exactly 1000ms, so the CV is exactly 0.5.
        offsets = [0.0, 1.0, 4.0, 5.0, 8.0]
        messages = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=offset), frame_index=index)
            for index, offset in enumerate(offsets)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=99)
        window = features_for(featurise_commands([*messages, tail]))

        assert window[COMMAND_INTERVAL_MEAN_MS] == pytest.approx(2000.0)
        assert window[COMMAND_INTERVAL_CV] == pytest.approx(0.5)

    def test_intervals_do_not_reach_across_a_window_boundary(self) -> None:
        # Window 1 holds sixty commands and therefore fifty-nine intervals, not sixty: the gap
        # from the last command of window 0 belongs to neither window on its own.
        observations = featurise_commands(command_series(TWO_WINDOW_COUNT))
        second = features_for(observations, 1)

        assert second[COMMAND_INTERVAL_MEAN_MS] == pytest.approx(1000.0)

    def test_commands_at_one_instant_report_a_mean_but_no_spread(self) -> None:
        # A mean interval of zero has no scale to normalise a spread against, so the coefficient
        # of variation is undefined and is omitted rather than reported as zero.
        burst = [
            make_modbus_message(timestamp=EPOCH, frame_index=index) for index in range(PER_WINDOW)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=999)
        window = features_for(featurise_commands([*burst, tail]))

        assert window[COMMAND_INTERVAL_MEAN_MS] == 0.0
        assert COMMAND_INTERVAL_CV not in window


class TestSparsity:
    def test_a_device_below_the_command_floor_emits_nothing(self) -> None:
        busy = command_series(TWO_WINDOW_COUNT)
        occasional = [
            make_modbus_message(
                src_ip="10.0.0.50",
                timestamp=EPOCH + timedelta(seconds=index),
                frame_index=900 + index,
            )
            for index in range(3)
        ]
        observations = featurise_commands([*busy, *occasional])

        assert device_entity_id("10.0.0.50") not in {o.entity_ids[0] for o in observations}

    def test_the_floor_is_configurable_and_admits_the_sparse_device_when_lowered(self) -> None:
        occasional = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
            for index in range(3)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=99)
        policy = CommandFeaturePolicy(min_commands=2, min_intervals=2)
        observations = featurise_commands([*occasional, tail], policy)

        assert features_for(observations)[COMMAND_COUNT] == 3

    def test_too_few_intervals_drops_the_timing_features_and_keeps_the_rest(self) -> None:
        # Two commands make one interval, which has no spread to speak of. The volume features
        # are still real measurements and are kept.
        pair = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
            for index in range(2)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=99)
        window = features_for(
            featurise_commands([*pair, tail], CommandFeaturePolicy(min_commands=2))
        )

        assert window[COMMAND_COUNT] == 2
        assert COMMAND_INTERVAL_MEAN_MS not in window
        assert COMMAND_INTERVAL_CV not in window

    def test_a_capture_shorter_than_one_window_yields_nothing(self) -> None:
        # Not a failure: it is the honest report for a capture too short to describe a rhythm.
        assert featurise_commands(command_series(30)) == []

    def test_an_empty_stream_yields_nothing(self) -> None:
        assert featurise_commands([]) == []

    def test_a_stream_with_no_commands_at_all_yields_nothing(
        self, malformed_frame: Callable[..., MalformedFrame]
    ) -> None:
        results = [
            malformed_frame(timestamp=EPOCH, frame_index=0),
            malformed_frame(timestamp=EPOCH + timedelta(minutes=2), frame_index=1),
        ]
        assert featurise_commands(results) == []


class TestTraceability:
    def test_every_observation_names_the_frames_it_was_computed_from(self) -> None:
        observations = featurise_commands(command_series(TWO_WINDOW_COUNT))

        for observation in observations:
            assert observation.context["frames"].startswith(f"{DEFAULT_CAPTURE}:")
            assert int(observation.context["frame_count"]) >= 1
            assert observation.context["device_ip"] == ISSUER_IP
            assert observation.context["window_start"]
            assert observation.context["window_end"]

    def test_the_frame_range_matches_the_window(self) -> None:
        observations = featurise_commands(command_series(TWO_WINDOW_COUNT))
        count = features_for(observations, 1)
        by_feature = {o.feature: o for o in observations if o.timestamp == EPOCH + ONE_MINUTE}

        assert count[COMMAND_COUNT] == PER_WINDOW
        assert by_feature[COMMAND_COUNT].context["frames"] == f"{DEFAULT_CAPTURE}:60-119"
        assert by_feature[COMMAND_COUNT].context["frame_count"] == "60"

    def test_a_write_feature_traces_only_to_the_write_frames(self) -> None:
        # Precision matters here: the evidence for "this device wrote register 40" is the write
        # frames, not every frame in the window.
        messages = command_series(
            TWO_WINDOW_COUNT,
            function_codes=(
                FunctionCode.READ_HOLDING_REGISTERS,
                FunctionCode.WRITE_SINGLE_REGISTER,
            ),
            reference_address=40,
            values=(5,),
        )
        observations = featurise_commands(messages)
        address = next(
            o for o in observations if o.feature == WRITE_ADDRESS_MIN and o.timestamp == EPOCH
        )

        assert address.context["frame_count"] == "30"
        assert address.context["frames"] == f"{DEFAULT_CAPTURE}:1-59"

    def test_a_zero_count_traces_to_the_frames_that_prove_the_zero(self) -> None:
        # There are no frames of that function, so the evidence is the window's whole command set
        # — the frames that were looked at and did not contain one.
        polls = command_series(TWO_WINDOW_COUNT)
        write = make_modbus_message(
            FunctionCode.WRITE_SINGLE_REGISTER,
            timestamp=EPOCH + timedelta(seconds=90),
            frame_index=500,
        )
        observations = featurise_commands([*polls, write])
        zero = next(
            o
            for o in observations
            if o.feature == function_count_feature(FunctionCode.WRITE_SINGLE_REGISTER)
            and o.timestamp == EPOCH
        )

        assert zero.value == 0.0
        assert zero.context["frame_count"] == "60"
        assert zero.context["frames"] == f"{DEFAULT_CAPTURE}:0-59"

    def test_frames_from_two_captures_are_reported_separately(self) -> None:
        # A frame index only means something alongside the file it counts within, so a window
        # drawing on two captures reports two ranges rather than one pooled and meaningless one.
        first = command_series(30, capture="/captures/a.pcap")
        second = command_series(
            30,
            start=EPOCH + timedelta(seconds=30),
            first_frame_index=0,
            capture="/captures/b.pcap",
        )
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=999)
        observations = featurise_commands([*first, *second, tail])
        window_zero = next(
            o for o in observations if o.feature == COMMAND_COUNT and o.timestamp == EPOCH
        )

        assert window_zero.context["frames"] == "/captures/a.pcap:0-29;/captures/b.pcap:0-29"
        assert window_zero.context["frame_count"] == "60"


class TestCoverageAndHonesty:
    def test_non_command_traffic_is_counted_rather_than_featured(
        self, malformed_frame: Callable[..., MalformedFrame]
    ) -> None:
        results: list[DissectionResult] = [
            *command_series(TWO_WINDOW_COUNT),
            make_modbus_message(direction=Direction.RESPONSE, frame_index=900),
            malformed_frame(frame_index=901),
        ]
        stats = CommandStreamStats()
        featurise_commands(results, stats=stats)

        assert stats.commands == TWO_WINDOW_COUNT
        assert stats.responses == 1
        assert stats.malformed == 1
        assert stats.accounts_for_every_result()

    def test_the_representativeness_caveat_is_stated_in_code(self) -> None:
        assert COMMAND_BASELINE_CAVEATS
        joined = " ".join(COMMAND_BASELINE_CAVEATS).lower()
        assert "capture" in joined

    def test_a_thin_capture_is_logged_as_thin(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            featurise_commands(command_series(121))
        assert any("window" in record.message for record in caplog.records)


class TestPolicy:
    @pytest.mark.parametrize("window", [timedelta(0), timedelta(seconds=-1)])
    def test_a_non_positive_window_is_refused(self, window: timedelta) -> None:
        with pytest.raises(ValueError):
            CommandFeaturePolicy(window=window)

    def test_a_zero_command_floor_is_refused(self) -> None:
        with pytest.raises(ValueError):
            CommandFeaturePolicy(min_commands=0)

    def test_fewer_than_two_intervals_is_refused(self) -> None:
        # One interval has no spread, so a coefficient of variation over it is always zero and
        # always meaningless.
        with pytest.raises(ValueError):
            CommandFeaturePolicy(min_intervals=1)

    def test_the_policy_is_frozen(self) -> None:
        policy = CommandFeaturePolicy()
        with pytest.raises(ValueError, match="frozen"):
            policy.min_commands = 2  # type: ignore[misc]


class TestDeterminism:
    def test_two_runs_over_one_stream_agree_on_everything_but_ids(self) -> None:
        messages = command_series(
            TWO_WINDOW_COUNT,
            function_codes=(
                FunctionCode.READ_HOLDING_REGISTERS,
                FunctionCode.WRITE_SINGLE_REGISTER,
            ),
            values=(9,),
        )

        def comparable(observations: list[Observation]) -> list[tuple[object, ...]]:
            return [
                (
                    o.timestamp,
                    tuple(o.entity_ids),
                    o.feature,
                    o.value,
                    tuple(sorted(o.context.items())),
                )
                for o in observations
            ]

        assert comparable(featurise_commands(messages)) == comparable(featurise_commands(messages))

    def test_input_order_does_not_change_the_output(self) -> None:
        messages = command_series(TWO_WINDOW_COUNT)
        forward = featurise_commands(messages)
        reversed_stream = featurise_commands(list(reversed(messages)))

        assert [(o.feature, o.value, o.timestamp) for o in forward] == [
            (o.feature, o.value, o.timestamp) for o in reversed_stream
        ]

    def test_output_is_ordered_by_window_then_device_then_feature(self) -> None:
        both = [
            *command_series(TWO_WINDOW_COUNT, src_ip="10.0.0.20"),
            *command_series(TWO_WINDOW_COUNT, src_ip="10.0.0.9", first_frame_index=500),
        ]
        observations = featurise_commands(both)
        keys = [(o.timestamp, o.entity_ids[0], o.feature) for o in observations]

        assert keys == sorted(keys)


class TestModelPathIntegration:
    def test_features_fit_and_score_through_the_existing_per_key_model(self) -> None:
        # The acceptance criterion for "no special-casing": PART 3's baseline, untouched, learns
        # from these observations and scores them.
        messages = command_series(601, function_codes=(FunctionCode.READ_HOLDING_REGISTERS,))
        observations = featurise_commands(messages)
        assert observations

        fitted = GaussianBaseline(name="command-behaviour", min_samples=4).fit(observations)
        assert fitted.expected_ranges

        counts = [o for o in observations if o.feature == COMMAND_COUNT]
        assert model_key(counts[0]) == (ISSUER, COMMAND_COUNT)
        assert fitted.resolve_range(counts[0]) is not None
        assert fitted.score(counts) == []

    def test_a_volume_collapse_scores_as_a_deviation(self) -> None:
        # Ten quiet minutes of steady polling, then a minute at a fifth of the rate.
        steady = command_series(600, function_codes=(FunctionCode.READ_HOLDING_REGISTERS,))
        drop = [
            make_modbus_message(
                timestamp=EPOCH + timedelta(minutes=10, seconds=index * 5), frame_index=700 + index
            )
            for index in range(12)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=11), frame_index=999)
        observations = featurise_commands([*steady, *drop, tail])

        counts = [o for o in observations if o.feature == COMMAND_COUNT]
        training = counts[:-1]
        fitted = GaussianBaseline(name="command-behaviour", min_samples=4).fit(training)
        deviations = fitted.score([counts[-1]])

        assert len(deviations) == 1
        assert deviations[0].magnitude > 0

    def test_features_vectorise_alongside_each_other_on_one_row(self) -> None:
        from phos.atlas import SignalSpace, vectorise

        observations = featurise_commands(
            command_series(
                601,
                function_codes=(
                    FunctionCode.READ_HOLDING_REGISTERS,
                    FunctionCode.WRITE_SINGLE_REGISTER,
                ),
                values=(3,),
            )
        )
        space = SignalSpace.from_observations(observations)
        series = vectorise(observations, space)

        # Every feature of every device in a window shares the window's start timestamp, so the
        # joint models see one complete row per window rather than a ragged scatter.
        assert series.n_rows == 10
        assert series.dropped_timestamps == 0
