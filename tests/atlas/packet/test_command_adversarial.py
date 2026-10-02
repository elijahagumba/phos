"""Aimed tests for the defects random inputs never reach.

P1 learned this the expensive way: a fuzz suite that has never caught anything is unproven, and
the bugs that matter hide where *several fields must agree in exactly the wrong way*. Random
traffic will not find them, because it never lands three values on the same knife edge.

So every test here is aimed. Each names a specific way the feature or graph code could be quietly
wrong while still returning plausible numbers — an off-by-one at a window edge, an interval
measured across a boundary it should not cross, a denominator taken from the wrong stream, a
function code suppressed because some *other* link had seen it. Each is arranged so that the wrong
answer is a *different number*, not an exception: a defect that crashes is a defect that gets
fixed, and these are the ones that would not.

`scripts/mutate_command_behaviour.py` is the check on this file. It injects each of these defects
into the source and asserts the suite goes red; a test that survives its own mutation is decoration.
"""

from collections.abc import Callable
from datetime import timedelta

import pytest

from phos.atlas.packet import Direction, FunctionCode, MalformedFrame, UnparsedMessage
from phos.atlas.packet.behaviour import (
    COMMAND_COUNT,
    COMMAND_INTERVAL_MEAN_MS,
    WRITE_ADDRESS_MAX,
    WRITE_ADDRESS_MIN,
    WRITE_COMMAND_SHARE,
    CommandFeaturePolicy,
    featurise_commands,
    function_count_feature,
)
from phos.atlas.packet.commands import device_entity_id
from phos.atlas.packet.dissect import DissectionResult
from phos.atlas.packet.graph import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
    compare_to_graph,
    learn_device_command_graph,
)
from phos.ontology import Observation

from .conftest import EPOCH, ISSUER_IP, TARGET_IP, command_series, make_modbus_message

ONE_MINUTE = timedelta(minutes=1)
ISSUER = device_entity_id(ISSUER_IP)
TARGET = device_entity_id(TARGET_IP)


def counts_by_window(observations: list[Observation], feature: str = COMMAND_COUNT) -> list[float]:
    """Return one feature's value per window, in window order."""
    return [o.value for o in observations if o.feature == feature]


class TestWindowEdges:
    def test_a_command_on_a_boundary_lands_in_exactly_one_window(self) -> None:
        # The defect this aims at: half-open bounds written as closed. A command at t=60 would
        # then be counted in both windows, and every boundary in the capture would inflate two
        # numbers at once — plausible everywhere, wrong everywhere.
        messages = command_series(121)
        observations = featurise_commands(messages)

        assert counts_by_window(observations) == [60.0, 60.0]

    def test_per_window_counts_reconcile_with_the_commands_inside_the_tiling(self) -> None:
        # 181 commands across three whole windows: 180 land inside, the 181st sits on the start of
        # a fourth window the span does not cover and must appear in no count at all.
        observations = featurise_commands(command_series(181))
        per_window = counts_by_window(observations)

        assert per_window == [60.0, 60.0, 60.0]
        assert sum(per_window) == 180.0

    def test_the_first_command_is_never_lost_to_the_tiling(self) -> None:
        # The tiling is anchored on the span start, so window zero opens on the first command.
        # An anchor computed one interval late would silently drop it.
        observations = featurise_commands(command_series(121))
        first = next(o for o in observations if o.feature == COMMAND_COUNT)

        assert first.context["frames"].endswith(":0-59")

    def test_a_span_of_exactly_two_windows_yields_two_not_three(self) -> None:
        messages = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=index * 10), frame_index=index)
            for index in range(13)
        ]
        assert counts_by_window(featurise_commands(messages)) == [6.0, 6.0]


class TestIntervalIsolation:
    def test_a_gap_between_windows_never_enters_either_window_rhythm(self) -> None:
        # A device polling every second for the first ten seconds of each minute. If intervals
        # were computed over the device's whole stream and then sliced, the fifty-second silence
        # would land in one of the windows and roughly quintuple its mean — a plausible number
        # from an implementation that never crosses a boundary correctly.
        messages = [
            make_modbus_message(
                timestamp=EPOCH + timedelta(minutes=minute, seconds=second),
                frame_index=minute * 100 + second,
            )
            for minute in range(2)
            for second in range(10)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=999)
        observations = featurise_commands([*messages, tail], CommandFeaturePolicy(min_commands=4))

        assert counts_by_window(observations, COMMAND_INTERVAL_MEAN_MS) == [1000.0, 1000.0]

    def test_the_interval_count_is_one_fewer_than_the_command_count(self) -> None:
        # Exactly at the floor: four commands make three intervals, which is min_intervals. Three
        # commands make two, which is not. An off-by-one either way moves this boundary.
        def window_zero(count: int) -> dict[str, float]:
            messages = [
                make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
                for index in range(count)
            ]
            tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=99)
            return {
                o.feature: o.value
                for o in featurise_commands([*messages, tail], CommandFeaturePolicy(min_commands=3))
                if o.timestamp == EPOCH
            }

        assert COMMAND_INTERVAL_MEAN_MS in window_zero(4)
        assert COMMAND_INTERVAL_MEAN_MS not in window_zero(3)


class TestSufficiencyBoundaries:
    def test_exactly_the_command_floor_is_enough_and_one_fewer_is_not(self) -> None:
        def observations_for(count: int) -> list[Observation]:
            messages = [
                make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
                for index in range(count)
            ]
            tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=99)
            return [o for o in featurise_commands([*messages, tail]) if o.timestamp == EPOCH]

        assert observations_for(4)
        assert observations_for(3) == []


class TestMeasuredZeros:
    def test_a_function_seen_only_in_the_dropped_tail_earns_no_zeros(self) -> None:
        # Three fields must agree for this to go wrong: the tail is dropped from the tiling, the
        # function set is built from *somewhere*, and every active window then reports a count.
        # Building the set from the whole stream puts a "zero writes" measurement into every
        # window on the strength of one write nothing ever measured.
        polls = command_series(121)
        tail_write = make_modbus_message(
            FunctionCode.WRITE_SINGLE_REGISTER,
            timestamp=EPOCH + timedelta(seconds=120),
            frame_index=500,
        )
        observations = featurise_commands([*polls, tail_write])
        write_feature = function_count_feature(FunctionCode.WRITE_SINGLE_REGISTER)

        assert write_feature not in {o.feature for o in observations}

    def test_an_absent_device_gets_no_zero_even_when_the_wire_was_live(
        self, unparsed_message: Callable[..., UnparsedMessage]
    ) -> None:
        # Unparsed traffic extends the span, so windows one and two exist. The device sent nothing
        # in them — and a device off the wire cannot be told from a device that has gone quiet, so
        # the honest output is no observation rather than a zero.
        commands = command_series(60)
        live_wire = unparsed_message(timestamp=EPOCH + timedelta(minutes=3), frame_index=900)
        observations = featurise_commands([*commands, live_wire])

        assert {o.timestamp for o in observations} == {EPOCH}

    def test_a_measured_zero_and_an_absence_are_different_outputs(self) -> None:
        # Same device, same capture: window 0 is a measured zero because the device was active
        # there; the device is simply missing from window 1. The pair is the whole distinction.
        polls = command_series(60)
        later_write = make_modbus_message(
            FunctionCode.WRITE_SINGLE_REGISTER,
            timestamp=EPOCH + timedelta(seconds=61),
            frame_index=500,
        )
        others = command_series(121, src_ip="10.0.0.77", first_frame_index=1000)
        observations = featurise_commands([*polls, later_write, *others])
        write_feature = function_count_feature(FunctionCode.WRITE_SINGLE_REGISTER)
        mine = [o for o in observations if o.entity_ids[0] == ISSUER]

        assert any(o.feature == write_feature and o.value == 0.0 for o in mine)
        assert {o.timestamp for o in mine} == {EPOCH}


class TestProvenancePrecision:
    def test_a_write_feature_cannot_borrow_the_read_frames(self) -> None:
        # Reads and writes are given disjoint frame ranges, so a provenance that fell back to the
        # whole window would report a range that visibly includes frames it did not use.
        reads = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
            for index in range(30)
        ]
        writes = [
            make_modbus_message(
                FunctionCode.WRITE_SINGLE_REGISTER,
                timestamp=EPOCH + timedelta(seconds=30 + index),
                frame_index=800 + index,
                reference_address=40 + index,
                values=(index,),
            )
            for index in range(30)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=9999)
        observations = featurise_commands([*reads, *writes, tail])
        by_feature = {o.feature: o for o in observations if o.timestamp == EPOCH}

        assert by_feature[WRITE_ADDRESS_MIN].context["frames"].endswith(":800-829")
        assert by_feature[COMMAND_COUNT].context["frames"].endswith(":0-829")
        assert by_feature[WRITE_ADDRESS_MIN].value == 40.0
        assert by_feature[WRITE_ADDRESS_MAX].value == 69.0

    def test_a_ratio_cites_the_frames_behind_its_denominator_too(self) -> None:
        # Found by mutation testing. The share is writes over *all* commands, so citing only the
        # write frames leaves an auditor able to recompute the numerator and nothing else — which
        # is not a reconstructable value. Reads and writes are given disjoint frame ranges so the
        # narrower provenance is visible rather than merely arguable.
        reads = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
            for index in range(30)
        ]
        writes = [
            make_modbus_message(
                FunctionCode.WRITE_SINGLE_REGISTER,
                timestamp=EPOCH + timedelta(seconds=30 + index),
                frame_index=800 + index,
                values=(1,),
            )
            for index in range(30)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=9999)
        share = next(
            o
            for o in featurise_commands([*reads, *writes, tail])
            if o.feature == WRITE_COMMAND_SHARE and o.timestamp == EPOCH
        )

        assert share.value == 0.5
        assert share.context["frames"].endswith(":0-829")
        assert share.context["frame_count"] == "60"

    def test_the_write_share_denominator_is_this_window_not_the_stream(self) -> None:
        # Window 0 is all reads, window 1 is all writes. A denominator taken from the device's
        # whole stream would report 0.5 in both — a number that is wrong in a way no single
        # window's data can reveal.
        reads = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=index), frame_index=index)
            for index in range(60)
        ]
        writes = [
            make_modbus_message(
                FunctionCode.WRITE_SINGLE_REGISTER,
                timestamp=EPOCH + timedelta(seconds=60 + index),
                frame_index=100 + index,
                values=(1,),
            )
            for index in range(60)
        ]
        tail = make_modbus_message(timestamp=EPOCH + timedelta(minutes=2), frame_index=9999)
        observations = featurise_commands([*reads, *writes, tail])

        assert counts_by_window(observations, WRITE_COMMAND_SHARE) == [0.0, 1.0]


class TestIdentityCollisions:
    def test_addresses_that_share_a_prefix_stay_distinct(self) -> None:
        # 10.0.0.1 is a prefix of 10.0.0.10. Any identity scheme that truncates, or that compares
        # by prefix, merges two devices into one and averages their behaviour together.
        first = command_series(121, src_ip="10.0.0.1")
        second = command_series(121, src_ip="10.0.0.10", first_frame_index=500)
        observations = featurise_commands([*first, *second])
        devices = {o.entity_ids[0] for o in observations}

        assert devices == {device_entity_id("10.0.0.1"), device_entity_id("10.0.0.10")}

    def test_a_device_commanding_and_being_commanded_keeps_one_identity(self) -> None:
        # A PLC that answers one station and commands another is one node, two edges.
        inbound = command_series(10, src_ip="10.0.0.9", dst_ip="10.0.0.20")
        outbound = command_series(10, src_ip="10.0.0.20", dst_ip="10.0.0.30", first_frame_index=100)
        graph = learn_device_command_graph([*inbound, *outbound])

        assert len(graph.edges) == 2
        assert graph.devices.count(device_entity_id("10.0.0.20")) == 1


class TestGraphAimed:
    def test_a_function_known_on_another_link_is_still_unexpected_here(self) -> None:
        # Two fields must agree wrongly: the function code is genuinely in the graph, and the
        # membership test is taken against the graph rather than against *this edge*. The result
        # is an intruder's write being waved through because some legitimate station also writes.
        normal = [
            *command_series(121, src_ip="10.0.0.9", dst_ip="10.0.0.20"),
            *command_series(
                121,
                src_ip="10.0.0.11",
                dst_ip="10.0.0.20",
                function_codes=(FunctionCode.WRITE_MULTIPLE_REGISTERS,),
                first_frame_index=500,
            ),
        ]
        graph = learn_device_command_graph(normal)

        live = [
            *command_series(121, src_ip="10.0.0.9", dst_ip="10.0.0.20"),
            make_modbus_message(
                FunctionCode.WRITE_MULTIPLE_REGISTERS,
                src_ip="10.0.0.9",
                dst_ip="10.0.0.20",
                timestamp=EPOCH + timedelta(seconds=10),
                frame_index=900,
            ),
        ]
        findings = [
            o for o in compare_to_graph(graph, live) if o.feature == UNEXPECTED_COMMAND_FUNCTION
        ]

        assert len(findings) == 1
        assert findings[0].entity_ids == [device_entity_id("10.0.0.9"), TARGET]

    def test_silence_is_judged_per_window_not_per_stream(self) -> None:
        # The link talks in window 0 and stops in window 1. A comparison that asked "did this link
        # appear anywhere in the live stream?" would report nothing at all — and missing a link
        # that dies halfway through a capture is precisely the failure the feature exists for.
        graph = learn_device_command_graph(command_series(121))
        live = [
            *command_series(60),
            make_modbus_message(
                src_ip="10.0.0.99", timestamp=EPOCH + timedelta(seconds=119), frame_index=800
            ),
            make_modbus_message(
                src_ip="10.0.0.99", timestamp=EPOCH + timedelta(minutes=2), frame_index=801
            ),
        ]
        silences = [
            o for o in compare_to_graph(graph, live) if o.feature == SILENT_COMMAND_RELATIONSHIP
        ]

        assert len(silences) == 1
        assert silences[0].timestamp == EPOCH + ONE_MINUTE

    def test_the_silence_expectation_comes_from_the_learned_span_not_the_live_one(self) -> None:
        # Learned: 121 commands over 120 seconds, so 60.5 per minute. The live stream is four
        # times longer and carries none of it. A rate computed against the live span would report
        # a quarter of the truth, and the number would look entirely reasonable.
        graph = learn_device_command_graph(command_series(121))
        live = command_series(481, src_ip="10.0.0.99")
        silences = [
            o for o in compare_to_graph(graph, live) if o.feature == SILENT_COMMAND_RELATIONSHIP
        ]

        assert len(silences) == 8
        assert all(o.value == pytest.approx(60.5) for o in silences)
        assert all(o.context["learned_span_seconds"] == "120" for o in silences)
        assert all(o.context["live_span_seconds"] == "480" for o in silences)
        assert all(o.context["horizon_seconds"] == "60" for o in silences)

    def test_a_burst_smeared_over_a_long_train_does_not_flag_every_quiet_minute(self) -> None:
        # 151 commands, almost all in the first two minutes of a two-hour train. The smeared rate
        # is ~1.26 per minute — enough that the old gate (any positive expectation) would fire
        # every quiet live minute. A typical comparable one-minute stretch of the train is empty.
        burst = command_series(150)
        tail = make_modbus_message(
            timestamp=EPOCH + timedelta(hours=2),
            frame_index=150,
        )
        graph = learn_device_command_graph([*burst, tail])
        live = command_series(181, src_ip="10.0.0.99")
        silences = [
            o for o in compare_to_graph(graph, live) if o.feature == SILENT_COMMAND_RELATIONSHIP
        ]

        assert silences == []

    def test_direction_is_not_collapsed_when_a_link_is_compared(self) -> None:
        # The graph knows A commands B. B commanding A is a new relationship, not a known one.
        graph = learn_device_command_graph(command_series(121))
        live = command_series(121, src_ip=TARGET_IP, dst_ip=ISSUER_IP)
        unknown = [
            o for o in compare_to_graph(graph, live) if o.feature == UNKNOWN_COMMAND_RELATIONSHIP
        ]

        assert unknown
        assert unknown[0].entity_ids == [TARGET, ISSUER]

    def test_a_response_on_a_new_link_raises_nothing(
        self, malformed_frame: Callable[..., MalformedFrame]
    ) -> None:
        # A PLC answering an intruder's scan is not the PLC commanding the intruder. Reading a
        # response as a command would invert the arrow on every finding it produced.
        graph = learn_device_command_graph(command_series(121))
        live: list[DissectionResult] = [
            *command_series(121),
            *[
                make_modbus_message(
                    src_ip=TARGET_IP,
                    dst_ip="10.0.0.99",
                    direction=Direction.RESPONSE,
                    timestamp=EPOCH + timedelta(seconds=index),
                    frame_index=700 + index,
                )
                for index in range(30)
            ],
            malformed_frame(frame_index=999),
        ]

        assert compare_to_graph(graph, live) == []

    def test_two_unit_ids_behind_one_gateway_remain_one_relationship(self) -> None:
        # The gateway sub-address is preserved on the event and deliberately not part of identity.
        # Folding it in would split one link into many and report each as new.
        graph = learn_device_command_graph(
            [
                make_modbus_message(
                    unit_id=index % 4,
                    timestamp=EPOCH + timedelta(seconds=index),
                    frame_index=index,
                )
                for index in range(121)
            ]
        )

        assert len(graph.edges) == 1
        assert compare_to_graph(graph, command_series(121)) == []
