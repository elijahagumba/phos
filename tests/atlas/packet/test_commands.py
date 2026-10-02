"""Tests for the command-stream normalisation layer: identity, extraction, coverage, windows."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.packet import (
    Direction,
    FunctionCode,
    MalformedFrame,
    ModbusMessage,
    UnparsedMessage,
)
from phos.atlas.packet.commands import (
    REGISTER_WRITE_FUNCTIONS,
    WRITE_FUNCTIONS,
    CommandEvent,
    CommandStreamStats,
    Window,
    command_events,
    device_entity_id,
    is_register_write,
    is_write,
    stream_span,
    tile_windows,
    window_index,
)

from .conftest import EPOCH, ISSUER_IP, TARGET_IP, make_modbus_message


class TestDeviceEntityId:
    def test_is_derived_from_the_address_and_is_readable(self) -> None:
        assert device_entity_id("10.0.0.9") == "ent_10.0.0.9"

    def test_is_stable_across_calls(self) -> None:
        assert device_entity_id("10.0.0.9") == device_entity_id("10.0.0.9")

    def test_distinct_addresses_never_collide(self) -> None:
        addresses = ["10.0.0.1", "10.0.0.2", "10.0.0.10", "2001::1", "2001::2"]
        assert len({device_entity_id(address) for address in addresses}) == len(addresses)

    def test_ipv6_is_carried_verbatim(self) -> None:
        assert device_entity_id("2001:db8::4") == "ent_2001:db8::4"

    def test_an_empty_address_is_refused(self) -> None:
        # A blank id would silently merge every unidentified device into one entity, and every
        # feature keyed to it would describe a device that does not exist.
        with pytest.raises(ValueError, match="non-empty"):
            device_entity_id("")


class TestWriteClassification:
    @pytest.mark.parametrize(
        "function_code",
        [
            FunctionCode.WRITE_SINGLE_COIL,
            FunctionCode.WRITE_SINGLE_REGISTER,
            FunctionCode.WRITE_MULTIPLE_COILS,
            FunctionCode.WRITE_MULTIPLE_REGISTERS,
        ],
    )
    def test_the_four_write_functions_are_writes(self, function_code: int) -> None:
        assert is_write(function_code)
        assert function_code in WRITE_FUNCTIONS

    @pytest.mark.parametrize(
        "function_code",
        [
            FunctionCode.READ_COILS,
            FunctionCode.READ_DISCRETE_INPUTS,
            FunctionCode.READ_HOLDING_REGISTERS,
            FunctionCode.READ_INPUT_REGISTERS,
        ],
    )
    def test_the_four_read_functions_are_not_writes(self, function_code: int) -> None:
        assert not is_write(function_code)

    def test_only_register_writes_carry_comparable_values(self) -> None:
        assert REGISTER_WRITE_FUNCTIONS == frozenset(
            {FunctionCode.WRITE_SINGLE_REGISTER, FunctionCode.WRITE_MULTIPLE_REGISTERS}
        )
        assert is_register_write(FunctionCode.WRITE_MULTIPLE_REGISTERS)
        # Coil writes are writes, but their value field is a different encoding — see the module
        # docstring for why they are excluded from the value features rather than mixed in.
        assert is_write(FunctionCode.WRITE_MULTIPLE_COILS)
        assert not is_register_write(FunctionCode.WRITE_MULTIPLE_COILS)

    def test_an_unknown_function_code_is_not_guessed_into_a_write(self) -> None:
        # 0x86 is an exception response code, and 99 is not a Modbus function at all. Neither may
        # be assumed to write: attributing a write a device never made is manufactured evidence.
        assert not is_write(0x86)
        assert not is_write(99)


class TestCommandExtraction:
    def test_a_request_becomes_a_command_event(self) -> None:
        message = make_modbus_message(
            FunctionCode.WRITE_SINGLE_REGISTER, reference_address=40, values=(7,)
        )
        (event,) = list(command_events([message]))

        assert event.issuer == device_entity_id(ISSUER_IP)
        assert event.target == device_entity_id(TARGET_IP)
        assert event.issuer_ip == ISSUER_IP
        assert event.target_ip == TARGET_IP
        assert event.function_code == FunctionCode.WRITE_SINGLE_REGISTER
        assert event.reference_address == 40
        assert event.values == (7,)
        assert event.timestamp == EPOCH

    def test_provenance_survives_into_the_event(self) -> None:
        message = make_modbus_message(frame_index=417, capture="/captures/day2.pcap")
        (event,) = list(command_events([message]))

        assert event.source.capture == "/captures/day2.pcap"
        assert event.source.frame_index == 417

    def test_a_response_is_not_a_command(self) -> None:
        message = make_modbus_message(direction=Direction.RESPONSE)
        assert list(command_events([message])) == []

    def test_an_undirected_message_is_not_a_command(self) -> None:
        # P1 reports UNKNOWN when the transport cannot settle the question. Treating it as a
        # request would attribute a command to whichever end happened to send the bytes.
        message = make_modbus_message(direction=Direction.UNKNOWN)
        assert list(command_events([message])) == []

    def test_unparsed_traffic_is_not_a_command(
        self, unparsed_message: Callable[..., UnparsedMessage]
    ) -> None:
        assert list(command_events([unparsed_message()])) == []

    def test_a_malformed_frame_is_not_a_command(
        self, malformed_frame: Callable[..., MalformedFrame]
    ) -> None:
        assert list(command_events([malformed_frame()])) == []

    def test_the_gateway_unit_id_is_preserved_but_not_folded_into_identity(self) -> None:
        # Two unit ids behind one gateway address are one entity here, and the sub-address is kept
        # so a later PART can refine the granularity without re-reading the capture.
        first = make_modbus_message(unit_id=3)
        second = make_modbus_message(unit_id=9)
        events = list(command_events([first, second]))

        assert events[0].unit_id == 3
        assert events[1].unit_id == 9
        assert events[0].target == events[1].target

    def test_extraction_is_lazy(self) -> None:
        consumed = 0

        def stream() -> object:
            nonlocal consumed
            for index in range(500):
                consumed += 1
                yield make_modbus_message(frame_index=index)

        iterator = command_events(stream())  # type: ignore[arg-type]
        next(iterator)
        assert consumed == 1
        next(iterator)
        assert consumed == 2


class TestCommandStreamStats:
    def test_every_result_lands_in_exactly_one_counter(
        self,
        unparsed_message: Callable[..., UnparsedMessage],
        malformed_frame: Callable[..., MalformedFrame],
    ) -> None:
        results: list[ModbusMessage | UnparsedMessage | MalformedFrame] = [
            make_modbus_message(),
            make_modbus_message(direction=Direction.RESPONSE),
            make_modbus_message(direction=Direction.UNKNOWN),
            unparsed_message(),
            malformed_frame(),
        ]
        stats = CommandStreamStats()
        list(command_events(results, stats))

        assert stats.results_seen == 5
        assert stats.commands == 1
        assert stats.responses == 1
        assert stats.undirected == 1
        assert stats.unparsed == 1
        assert stats.malformed == 1
        assert stats.accounts_for_every_result()

    def test_a_protocol_p2_cannot_read_is_counted_not_dropped(self) -> None:
        # A dissector for a protocol P1 does not implement could still land an IcsMessage here.
        # It has no function code, so it cannot become a command — and saying nothing about it
        # would report a coverage gap as an absence of commands.
        from phos.atlas.packet.messages import IcsMessage

        template = make_modbus_message()
        foreign = IcsMessage(
            protocol="dnp3",
            source=template.source,
            timestamp=EPOCH,
            src=template.src,
            dst=template.dst,
            direction=Direction.REQUEST,
        )

        stats = CommandStreamStats()
        assert list(command_events([foreign], stats)) == []
        assert stats.uninterpreted == 1
        assert stats.commands == 0
        assert stats.accounts_for_every_result()

    def test_a_lost_result_makes_the_reconciliation_fail(self) -> None:
        # The guard is only worth having if it can say no.
        stats = CommandStreamStats(results_seen=5, commands=1)
        assert not stats.accounts_for_every_result()


class TestStreamSpan:
    def test_the_span_covers_every_result_not_just_the_commands(
        self, unparsed_message: Callable[..., UnparsedMessage]
    ) -> None:
        # Unparsed traffic is still evidence that the wire was live at that instant, so it bounds
        # the span. Ignoring it would shorten the observed period and inflate every rate.
        results = [
            make_modbus_message(timestamp=EPOCH + timedelta(seconds=30)),
            unparsed_message(timestamp=EPOCH),
            unparsed_message(timestamp=EPOCH + timedelta(minutes=5)),
        ]
        assert stream_span(results) == (EPOCH, EPOCH + timedelta(minutes=5))

    def test_an_empty_stream_has_no_span(self) -> None:
        assert stream_span([]) is None

    def test_out_of_order_timestamps_still_yield_the_true_span(self) -> None:
        results = [
            make_modbus_message(timestamp=EPOCH + timedelta(minutes=2)),
            make_modbus_message(timestamp=EPOCH),
            make_modbus_message(timestamp=EPOCH + timedelta(minutes=1)),
        ]
        assert stream_span(results) == (EPOCH, EPOCH + timedelta(minutes=2))


class TestTileWindows:
    def test_windows_tile_the_span_from_its_start(self) -> None:
        windows = tile_windows(EPOCH, EPOCH + timedelta(minutes=3), timedelta(minutes=1))

        assert [window.index for window in windows] == [0, 1, 2]
        assert windows[0].start == EPOCH
        assert windows[0].end == EPOCH + timedelta(minutes=1)
        assert windows[2].end == EPOCH + timedelta(minutes=3)

    def test_a_partial_trailing_window_is_dropped(self) -> None:
        # 2m30s of traffic at a one-minute window is two whole windows and a half. Counting the
        # half would report a device's command volume as half what it was and look like silence.
        windows = tile_windows(EPOCH, EPOCH + timedelta(seconds=150), timedelta(minutes=1))
        assert len(windows) == 2

    def test_a_span_shorter_than_one_window_yields_none(self) -> None:
        assert tile_windows(EPOCH, EPOCH + timedelta(seconds=30), timedelta(minutes=1)) == ()

    def test_an_instantaneous_span_yields_none(self) -> None:
        assert tile_windows(EPOCH, EPOCH, timedelta(minutes=1)) == ()

    def test_an_inverted_span_is_refused(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            tile_windows(EPOCH + timedelta(minutes=1), EPOCH, timedelta(minutes=1))

    @pytest.mark.parametrize("duration", [timedelta(0), timedelta(seconds=-1)])
    def test_a_non_positive_window_is_refused(self, duration: timedelta) -> None:
        with pytest.raises(ValueError, match="positive"):
            tile_windows(EPOCH, EPOCH + timedelta(minutes=1), duration)

    def test_window_bounds_are_half_open(self) -> None:
        windows = tile_windows(EPOCH, EPOCH + timedelta(minutes=2), timedelta(minutes=1))
        boundary = EPOCH + timedelta(minutes=1)

        assert not windows[0].contains(boundary)
        assert windows[1].contains(boundary)


class TestWindowIndex:
    def test_a_timestamp_maps_to_the_window_holding_it(self) -> None:
        windows = tile_windows(EPOCH, EPOCH + timedelta(minutes=3), timedelta(minutes=1))
        assert window_index(EPOCH + timedelta(seconds=90), windows) == 1

    def test_a_timestamp_in_the_dropped_trailing_window_maps_to_nothing(self) -> None:
        windows = tile_windows(EPOCH, EPOCH + timedelta(seconds=150), timedelta(minutes=1))
        assert window_index(EPOCH + timedelta(seconds=140), windows) is None

    def test_a_timestamp_before_the_span_maps_to_nothing(self) -> None:
        windows = tile_windows(EPOCH, EPOCH + timedelta(minutes=2), timedelta(minutes=1))
        assert window_index(EPOCH - timedelta(seconds=1), windows) is None

    def test_no_windows_means_no_index(self) -> None:
        assert window_index(EPOCH, ()) is None


class TestWindowModel:
    def test_an_inverted_window_is_refused(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            Window(index=0, start=EPOCH + timedelta(minutes=1), end=EPOCH)

    def test_a_window_is_frozen(self) -> None:
        window = Window(index=0, start=EPOCH, end=EPOCH + timedelta(minutes=1))
        with pytest.raises(ValueError, match="frozen"):
            window.index = 1  # type: ignore[misc]


class TestCommandEventModel:
    def test_an_event_is_frozen(self) -> None:
        (event,) = list(command_events([make_modbus_message()]))
        with pytest.raises(ValueError, match="frozen"):
            event.function_code = 3  # type: ignore[misc]

    def test_an_event_round_trips_through_json(self) -> None:
        (event,) = list(command_events([make_modbus_message(values=(1, 2, 3))]))
        assert CommandEvent.model_validate_json(event.model_dump_json()) == event

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValueError):
            CommandEvent(
                issuer="ent_a",
                target="ent_b",
                issuer_ip="10.0.0.1",
                target_ip="10.0.0.2",
                protocol="modbus",
                function_code=3,
                function_name="read_holding_registers",
                unit_id=1,
                timestamp=datetime(2026, 8, 14, 9, 0),
                source=make_modbus_message().source,
            )

    def test_a_timestamp_is_normalised_to_utc(self) -> None:
        offset = datetime(2026, 8, 14, 11, 0, tzinfo=UTC).astimezone()
        event = CommandEvent(
            issuer="ent_a",
            target="ent_b",
            issuer_ip="10.0.0.1",
            target_ip="10.0.0.2",
            protocol="modbus",
            function_code=3,
            function_name="read_holding_registers",
            unit_id=1,
            timestamp=offset,
            source=make_modbus_message().source,
        )
        assert event.timestamp.tzinfo is UTC
