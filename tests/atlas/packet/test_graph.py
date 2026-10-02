"""Tests for the device-command graph: what it learns, and the three changes it can surface."""

from collections.abc import Callable
from datetime import timedelta

import pytest

from phos.atlas.packet import Direction, FunctionCode, MalformedFrame, UnparsedMessage
from phos.atlas.packet.commands import CommandStreamStats, device_entity_id
from phos.atlas.packet.dissect import DissectionResult
from phos.atlas.packet.graph import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
    CommandEdge,
    DeviceCommandGraph,
    GraphComparePolicy,
    compare_to_graph,
    learn_device_command_graph,
    render_graph,
)
from phos.ontology import Domain, Observation

from .conftest import (
    DEFAULT_CAPTURE,
    EPOCH,
    ISSUER_IP,
    TARGET_IP,
    command_series,
    make_modbus_message,
)

ONE_MINUTE = timedelta(minutes=1)
ISSUER = device_entity_id(ISSUER_IP)
TARGET = device_entity_id(TARGET_IP)
INTRUDER_IP = "10.0.0.99"
INTRUDER = device_entity_id(INTRUDER_IP)

# 121 commands one second apart span exactly 120 seconds, so the learned rate is 121/120 per
# second and a 60-second window expects 60.5 of them.
LEARNING_COUNT = 121
LEARNED_SPAN_SECONDS = 120.0
EXPECTED_PER_WINDOW = LEARNING_COUNT / LEARNED_SPAN_SECONDS * 60.0


def normal_traffic() -> list[DissectionResult]:
    """The learning corpus: one device polling one PLC on function 3, steadily."""
    return list(command_series(LEARNING_COUNT))


def learned() -> DeviceCommandGraph:
    """The graph normal traffic teaches."""
    return learn_device_command_graph(normal_traffic())


def by_feature(observations: list[Observation], feature: str) -> list[Observation]:
    """Return the observations carrying ``feature``, in order."""
    return [o for o in observations if o.feature == feature]


class TestLearning:
    def test_a_single_relationship_is_learned_with_its_function_codes(self) -> None:
        graph = learned()

        assert len(graph.edges) == 1
        edge = graph.edges[0]
        assert (edge.issuer, edge.target) == (ISSUER, TARGET)
        assert (edge.issuer_ip, edge.target_ip) == (ISSUER_IP, TARGET_IP)
        assert edge.function_codes == (FunctionCode.READ_HOLDING_REGISTERS,)
        assert edge.command_count == LEARNING_COUNT

    def test_several_function_codes_on_one_edge_are_all_kept_and_sorted(self) -> None:
        messages = command_series(
            60,
            function_codes=(
                FunctionCode.WRITE_MULTIPLE_REGISTERS,
                FunctionCode.READ_HOLDING_REGISTERS,
                FunctionCode.READ_COILS,
            ),
        )
        (edge,) = learn_device_command_graph(messages).edges

        assert edge.function_codes == (
            FunctionCode.READ_COILS,
            FunctionCode.READ_HOLDING_REGISTERS,
            FunctionCode.WRITE_MULTIPLE_REGISTERS,
        )

    def test_distinct_pairs_become_distinct_edges(self) -> None:
        messages = [
            *command_series(10, src_ip="10.0.0.9", dst_ip="10.0.0.20"),
            *command_series(10, src_ip="10.0.0.9", dst_ip="10.0.0.21", first_frame_index=100),
            *command_series(10, src_ip="10.0.0.10", dst_ip="10.0.0.20", first_frame_index=200),
        ]
        graph = learn_device_command_graph(messages)

        assert len(graph.edges) == 3
        assert graph.devices == (
            device_entity_id("10.0.0.10"),
            device_entity_id("10.0.0.20"),
            device_entity_id("10.0.0.21"),
            device_entity_id("10.0.0.9"),
        )

    def test_direction_is_part_of_the_relationship(self) -> None:
        # A commands B is not the same fact as B commands A, and an undirected graph would let a
        # PLC start commanding its engineering station without anything noticing.
        messages = [
            *command_series(5, src_ip="10.0.0.9", dst_ip="10.0.0.20"),
            *command_series(5, src_ip="10.0.0.20", dst_ip="10.0.0.9", first_frame_index=100),
        ]
        graph = learn_device_command_graph(messages)

        assert len(graph.edges) == 2
        assert graph.edge(ISSUER, TARGET) is not None
        assert graph.edge(TARGET, ISSUER) is not None

    def test_the_learned_span_and_edge_window_are_recorded(self) -> None:
        graph = learned()

        assert graph.learned_span == (EPOCH, EPOCH + timedelta(seconds=120))
        assert graph.edges[0].first_seen == EPOCH
        assert graph.edges[0].last_seen == EPOCH + timedelta(seconds=120)
        assert graph.horizon == timedelta(minutes=1)
        # 121 commands at t=0..120, two one-minute stretches; the span-end command sits on the
        # last bin's exclusive end and is folded into that comparable stretch.
        assert graph.edges[0].horizon_counts == (60, 61)

    def test_every_edge_names_the_frames_it_was_learned_from(self) -> None:
        assert learned().edges[0].frames == f"{DEFAULT_CAPTURE}:0-120"

    def test_responses_teach_nothing(self) -> None:
        # An edge learned from responses would record the PLC as commanding its client.
        messages = [
            make_modbus_message(direction=Direction.RESPONSE, frame_index=i) for i in range(5)
        ]
        assert learn_device_command_graph(messages).edges == ()

    def test_unparsed_and_malformed_traffic_teaches_nothing_but_is_counted(
        self,
        unparsed_message: Callable[..., UnparsedMessage],
        malformed_frame: Callable[..., MalformedFrame],
    ) -> None:
        stats = CommandStreamStats()
        graph = learn_device_command_graph(
            [unparsed_message(), malformed_frame(frame_index=1)], stats
        )

        assert graph.edges == ()
        assert (stats.unparsed, stats.malformed) == (1, 1)
        assert stats.accounts_for_every_result()

    def test_an_empty_stream_learns_an_empty_graph(self) -> None:
        graph = learn_device_command_graph([])

        assert graph.edges == ()
        assert graph.devices == ()
        assert graph.command_count == 0

    def test_edges_are_ordered_deterministically(self) -> None:
        forward = command_series(5, src_ip="10.0.0.9", dst_ip="10.0.0.20")
        backward = command_series(5, src_ip="10.0.0.10", dst_ip="10.0.0.21", first_frame_index=50)

        first = learn_device_command_graph([*forward, *backward])
        second = learn_device_command_graph([*backward, *forward])

        assert first.edges == second.edges


class TestUnknownRelationship:
    def test_a_device_commanding_one_it_never_has_is_surfaced(self) -> None:
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        findings = by_feature(compare_to_graph(learned(), live), UNKNOWN_COMMAND_RELATIONSHIP)

        assert len(findings) == 2
        assert [f.value for f in findings] == [60.0, 60.0]
        assert findings[0].entity_ids == [INTRUDER, TARGET]
        assert findings[0].domain is Domain.ATLAS

    def test_the_finding_names_the_functions_and_the_frames(self) -> None:
        live = command_series(
            LEARNING_COUNT,
            src_ip=INTRUDER_IP,
            function_codes=(FunctionCode.WRITE_SINGLE_COIL,),
        )
        finding = by_feature(compare_to_graph(learned(), live), UNKNOWN_COMMAND_RELATIONSHIP)[0]

        assert finding.context["function_codes"] == str(FunctionCode.WRITE_SINGLE_COIL)
        assert finding.context["issuer_ip"] == INTRUDER_IP
        assert finding.context["target_ip"] == TARGET_IP
        assert finding.context["frames"] == f"{DEFAULT_CAPTURE}:0-59"

    def test_a_new_edge_is_not_also_reported_as_an_unexpected_function(self) -> None:
        # The whole relationship is new. Reporting the function code separately would count one
        # change twice and inflate whatever later weighs the evidence.
        live = command_series(
            LEARNING_COUNT,
            src_ip=INTRUDER_IP,
            function_codes=(FunctionCode.WRITE_MULTIPLE_REGISTERS,),
        )
        findings = compare_to_graph(learned(), live)

        assert by_feature(findings, UNKNOWN_COMMAND_RELATIONSHIP)
        assert by_feature(findings, UNEXPECTED_COMMAND_FUNCTION) == []


class TestSilentRelationship:
    def test_a_normally_chatty_link_that_stops_is_surfaced(self) -> None:
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        findings = by_feature(compare_to_graph(learned(), live), SILENT_COMMAND_RELATIONSHIP)

        assert len(findings) == 2
        assert findings[0].value == pytest.approx(EXPECTED_PER_WINDOW)
        assert findings[0].entity_ids == [ISSUER, TARGET]

    def test_the_finding_says_what_was_expected_and_where_it_was_learned(self) -> None:
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        finding = by_feature(compare_to_graph(learned(), live), SILENT_COMMAND_RELATIONSHIP)[0]

        assert finding.context["learned_command_count"] == str(LEARNING_COUNT)
        assert finding.context["frames"] == f"{DEFAULT_CAPTURE}:0-120"
        assert finding.context["learned_span_start"] == EPOCH.isoformat()
        # Reconstructable duration match: the comparable stretch is the live window, not the
        # whole train, and both spans sit on the finding so a mismatch cannot hide.
        assert finding.context["learned_span_seconds"] == "120"
        assert finding.context["live_span_seconds"] == "120"
        assert finding.context["horizon_seconds"] == "60"
        assert finding.context["live_span_start"] == EPOCH.isoformat()

    def test_a_multi_day_train_does_not_manufacture_silence_every_minute(self) -> None:
        """Duration mismatch is not one silent act per poller per live minute.

        Twelve commands per poller over five days pass ``min_edge_commands`` and, under the old
        rate ``count / learned_span * window``, still emit a finding every quiet minute. A
        comparable one-minute stretch of that train is typically empty, so a short live capture
        must not flood.
        """
        train_end = EPOCH + timedelta(days=5)
        poller_ips = ("10.0.0.9", "10.0.0.10", "10.0.0.11")
        commands_per_poller = 12
        train: list[DissectionResult] = []
        frame = 0
        for src_ip in poller_ips:
            for index in range(commands_per_poller):
                fraction = index / (commands_per_poller - 1)
                train.append(
                    make_modbus_message(
                        src_ip=src_ip,
                        timestamp=EPOCH + (train_end - EPOCH) * fraction,
                        frame_index=frame,
                    )
                )
                frame += 1

        live = command_series(181, src_ip=INTRUDER_IP)
        graph = learn_device_command_graph(train)
        findings = compare_to_graph(graph, live)
        silences = by_feature(findings, SILENT_COMMAND_RELATIONSHIP)

        assert len(graph.edges) == len(poller_ips)
        # Three whole live minutes. The old flood was 3 pollers * 3 minutes = 9 findings.
        assert by_feature(findings, UNKNOWN_COMMAND_RELATIONSHIP)
        assert silences == []

    def test_a_steadily_chatty_link_is_still_silent_per_window_on_a_longer_train(self) -> None:
        """Horizon matching must not starve real silence of a link that typically talks."""
        train = command_series(601)
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        silences = by_feature(
            compare_to_graph(learn_device_command_graph(train), live),
            SILENT_COMMAND_RELATIONSHIP,
        )

        assert len(silences) == 2
        assert all(finding.value == pytest.approx(60.1) for finding in silences)

    def test_a_link_still_talking_is_not_called_silent(self) -> None:
        assert compare_to_graph(learned(), normal_traffic()) == []

    def test_an_edge_seen_too_few_times_to_have_an_expectation_is_not_called_silent(self) -> None:
        # A link observed twice in a whole capture has no rate worth the name, and calling its
        # absence evidence would manufacture a finding out of a sampling accident.
        sparse = [
            *command_series(LEARNING_COUNT),
            *command_series(2, src_ip="10.0.0.77", first_frame_index=500),
        ]
        graph = learn_device_command_graph(sparse)
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        findings = by_feature(compare_to_graph(graph, live), SILENT_COMMAND_RELATIONSHIP)

        assert {tuple(f.entity_ids) for f in findings} == {(ISSUER, TARGET)}

    def test_a_graph_learned_at_one_instant_yields_no_expectation_at_all(self) -> None:
        # Every command at the same timestamp gives a zero-length span, and a rate over zero
        # seconds is not a large number — it is not a number.
        instant = [make_modbus_message(frame_index=index) for index in range(20)]
        graph = learn_device_command_graph(instant)
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)

        assert by_feature(compare_to_graph(graph, live), SILENT_COMMAND_RELATIONSHIP) == []

    def test_the_floor_is_configurable(self) -> None:
        sparse = [
            *command_series(LEARNING_COUNT),
            *command_series(2, src_ip="10.0.0.77", first_frame_index=500),
        ]
        graph = learn_device_command_graph(sparse)
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        findings = by_feature(
            compare_to_graph(graph, live, GraphComparePolicy(min_edge_commands=2)),
            SILENT_COMMAND_RELATIONSHIP,
        )

        assert {tuple(f.entity_ids) for f in findings} == {
            (ISSUER, TARGET),
            (device_entity_id("10.0.0.77"), TARGET),
        }


class TestUnexpectedFunction:
    def _live_with_writes(self) -> list[DissectionResult]:
        writes = [
            make_modbus_message(
                FunctionCode.WRITE_MULTIPLE_REGISTERS,
                timestamp=EPOCH + timedelta(seconds=offset),
                frame_index=500 + index,
            )
            for index, offset in enumerate((10, 70))
        ]
        return [*command_series(LEARNING_COUNT), *writes]

    def test_a_function_never_seen_on_a_known_edge_is_surfaced(self) -> None:
        findings = by_feature(
            compare_to_graph(learned(), self._live_with_writes()), UNEXPECTED_COMMAND_FUNCTION
        )

        assert len(findings) == 2
        assert [f.value for f in findings] == [1.0, 1.0]
        assert findings[0].entity_ids == [ISSUER, TARGET]
        assert findings[0].context["function_code"] == str(FunctionCode.WRITE_MULTIPLE_REGISTERS)

    def test_the_finding_traces_to_the_offending_frames_only(self) -> None:
        finding = by_feature(
            compare_to_graph(learned(), self._live_with_writes()), UNEXPECTED_COMMAND_FUNCTION
        )[0]

        assert finding.context["frames"] == f"{DEFAULT_CAPTURE}:500-500"
        assert finding.context["frame_count"] == "1"

    def test_a_learned_function_raises_nothing(self) -> None:
        assert (
            by_feature(compare_to_graph(learned(), normal_traffic()), UNEXPECTED_COMMAND_FUNCTION)
            == []
        )

    def test_two_unexpected_functions_are_reported_separately(self) -> None:
        # One observation per code, because "it also sent function 5" and "it also sent function
        # 16" are two different things an operator may need to act on differently.
        extras = [
            make_modbus_message(
                code,
                timestamp=EPOCH + timedelta(seconds=10 + index),
                frame_index=500 + index,
            )
            for index, code in enumerate(
                (FunctionCode.WRITE_SINGLE_COIL, FunctionCode.WRITE_MULTIPLE_REGISTERS)
            )
        ]
        findings = by_feature(
            compare_to_graph(learned(), [*command_series(LEARNING_COUNT), *extras]),
            UNEXPECTED_COMMAND_FUNCTION,
        )

        assert [f.context["function_code"] for f in findings] == [
            str(FunctionCode.WRITE_SINGLE_COIL),
            str(FunctionCode.WRITE_MULTIPLE_REGISTERS),
        ]


class TestComparisonBoundaries:
    def test_live_traffic_shorter_than_one_window_yields_nothing(self) -> None:
        # Not "everything is normal" — there is no window over which to say anything at all.
        assert compare_to_graph(learned(), command_series(10)) == []

    def test_an_empty_live_stream_yields_nothing(self) -> None:
        assert compare_to_graph(learned(), []) == []

    def test_an_empty_graph_makes_every_live_relationship_unknown(self) -> None:
        empty = learn_device_command_graph([])
        findings = compare_to_graph(empty, command_series(LEARNING_COUNT))

        assert by_feature(findings, UNKNOWN_COMMAND_RELATIONSHIP)
        assert by_feature(findings, SILENT_COMMAND_RELATIONSHIP) == []

    def test_non_command_traffic_is_counted_rather_than_compared(
        self, malformed_frame: Callable[..., MalformedFrame]
    ) -> None:
        stats = CommandStreamStats()
        mixed: list[DissectionResult] = [*normal_traffic(), malformed_frame(frame_index=900)]
        compare_to_graph(learned(), mixed, stats=stats)

        assert stats.malformed == 1
        assert stats.accounts_for_every_result()

    def test_findings_are_ordered_deterministically(self) -> None:
        live = [
            *command_series(LEARNING_COUNT, src_ip=INTRUDER_IP),
            *command_series(LEARNING_COUNT, src_ip="10.0.0.50", first_frame_index=500),
        ]
        keys = [
            (o.timestamp, o.entity_ids[0], o.entity_ids[1], o.feature)
            for o in compare_to_graph(learned(), live)
        ]

        assert keys == sorted(keys)

    def test_two_comparisons_of_one_stream_agree(self) -> None:
        live = command_series(LEARNING_COUNT, src_ip=INTRUDER_IP)
        graph = learned()

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

        assert comparable(compare_to_graph(graph, live)) == comparable(
            compare_to_graph(graph, live)
        )


class TestGraphModel:
    def test_a_graph_round_trips_through_json(self) -> None:
        graph = learned()
        assert DeviceCommandGraph.model_validate_json(graph.model_dump_json()) == graph

    def test_a_graph_is_frozen(self) -> None:
        with pytest.raises(ValueError, match="frozen"):
            learned().edges = ()  # type: ignore[misc]

    def test_edge_lookup_misses_return_none(self) -> None:
        assert learned().edge(INTRUDER, TARGET) is None

    def test_the_command_total_is_the_sum_over_edges(self) -> None:
        assert learned().command_count == LEARNING_COUNT

    def test_an_empty_graph_records_no_learned_span(self) -> None:
        # No commands, no period. A placeholder instant here would quietly become the denominator
        # of every rate drawn from the graph.
        assert learn_device_command_graph([]).learned_span is None

    def test_edges_without_a_learned_span_are_refused(self) -> None:
        with pytest.raises(ValueError, match="must record the span"):
            DeviceCommandGraph(edges=(learned().edges[0],), learned_span=None)

    def test_duplicate_edges_are_refused(self) -> None:
        edge = learned().edges[0]
        with pytest.raises(ValueError, match="more than once"):
            DeviceCommandGraph(edges=(edge, edge), learned_span=(EPOCH, EPOCH))

    def test_unsorted_edges_are_refused(self) -> None:
        # Order is the contract: two graphs over the same traffic must serialise identically.
        first = learned().edges[0]
        second = first.model_copy(update={"issuer": "ent_10.0.0.1"})
        with pytest.raises(ValueError, match="sorted"):
            DeviceCommandGraph(edges=(first, second), learned_span=(EPOCH, EPOCH))

    def test_an_inverted_learned_span_is_refused(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            DeviceCommandGraph(edges=(), learned_span=(EPOCH + ONE_MINUTE, EPOCH))

    def test_a_non_positive_horizon_is_refused(self) -> None:
        with pytest.raises(ValueError, match="horizon"):
            DeviceCommandGraph(edges=(), horizon=timedelta(0))

    def test_negative_occupancy_counts_are_refused(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CommandEdge(
                issuer=ISSUER,
                target=TARGET,
                issuer_ip=ISSUER_IP,
                target_ip=TARGET_IP,
                function_codes=(3,),
                command_count=1,
                first_seen=EPOCH,
                last_seen=EPOCH,
                frames="a:0-1",
                horizon_counts=(1, -1),
            )

    def test_an_edge_with_unsorted_function_codes_is_refused(self) -> None:
        with pytest.raises(ValueError, match="sorted"):
            CommandEdge(
                issuer=ISSUER,
                target=TARGET,
                issuer_ip=ISSUER_IP,
                target_ip=TARGET_IP,
                function_codes=(16, 3),
                command_count=2,
                first_seen=EPOCH,
                last_seen=EPOCH,
                frames="a:0-1",
            )

    def test_an_edge_with_repeated_function_codes_is_refused(self) -> None:
        with pytest.raises(ValueError, match="sorted"):
            CommandEdge(
                issuer=ISSUER,
                target=TARGET,
                issuer_ip=ISSUER_IP,
                target_ip=TARGET_IP,
                function_codes=(3, 3),
                command_count=2,
                first_seen=EPOCH,
                last_seen=EPOCH,
                frames="a:0-1",
            )

    def test_an_edge_with_an_inverted_window_is_refused(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            CommandEdge(
                issuer=ISSUER,
                target=TARGET,
                issuer_ip=ISSUER_IP,
                target_ip=TARGET_IP,
                function_codes=(3,),
                command_count=1,
                first_seen=EPOCH + ONE_MINUTE,
                last_seen=EPOCH,
                frames="a:0-1",
            )


class TestRendering:
    def test_the_graph_renders_every_edge_for_audit(self) -> None:
        rendered = render_graph(learned())

        assert ISSUER_IP in rendered
        assert TARGET_IP in rendered
        assert "read_holding_registers" in rendered or "fn 3" in rendered
        assert str(LEARNING_COUNT) in rendered

    def test_an_empty_graph_says_so_rather_than_rendering_blank(self) -> None:
        assert "no command relationships" in render_graph(learn_device_command_graph([]))

    def test_rendering_is_deterministic(self) -> None:
        assert render_graph(learned()) == render_graph(learned())


class TestPolicy:
    @pytest.mark.parametrize("window", [timedelta(0), timedelta(seconds=-1)])
    def test_a_non_positive_window_is_refused(self, window: timedelta) -> None:
        with pytest.raises(ValueError):
            GraphComparePolicy(window=window)

    def test_a_zero_edge_floor_is_refused(self) -> None:
        with pytest.raises(ValueError):
            GraphComparePolicy(min_edge_commands=0)

    def test_the_policy_is_frozen(self) -> None:
        with pytest.raises(ValueError, match="frozen"):
            GraphComparePolicy().min_edge_commands = 9  # type: ignore[misc]
