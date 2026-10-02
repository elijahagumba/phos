"""The maintenance register: independent of the attacks, and readable by the real adapter.

Three things are under test, and only the first is ordinary.

**The register is plausible.** Routine orders repeat on their interval, reactive callouts arrive
at random, shutdowns cover every asset at once, and a share of orders carry a status that
sanctions nothing.

**The register is causally independent of the attacks.** This is the property the whole exercise
rests on, and it is checked structurally — the signature of `plan_maintenance`, and this module's
import graph — rather than by inspecting outputs, because an output check can only ever say "these
two happened not to line up this time". The stronger statement is that the generator *cannot* see
an attack schedule. `test_anti_bias.py` carries the enforcement; the tests here pin the behaviour
that makes it meaningful, including that the same practice and seed give the same calendar whether
or not any attack exists.

**The exports are read by the real reader.** `phos.atlas.cmms.load_work_order_export` with the
shipped `SAP_PM_SCHEMA` and `MAXIMO_SCHEMA` parses what this module writes. Nothing in
`maintenance.py` imports that reader — the columns are literals there — so this is the generator
being held to the reader's standard rather than to its own, which is the same argument
`test_traffic.py` makes about the Modbus dissector.
"""

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import numpy
import pytest
from pydantic import ValidationError

from phos.atlas.cmms import (
    MAXIMO_SCHEMA,
    SAP_PM_SCHEMA,
    covering_order,
    load_work_order_export,
    observations_from_work_orders,
)
from phos.synth.maintenance import (
    MAXIMO_COLUMNS,
    SAP_PM_COLUMNS,
    MaintenanceCalendar,
    MaintenanceKind,
    MaintenancePractice,
    WorkOrder,
    plan_maintenance,
    write_maximo_export,
    write_sap_pm_export,
)
from phos.synth.plant import RunSpec

START = datetime(2026, 3, 1, tzinfo=UTC)
ASSETS = ("intake", "dosing", "filtration", "clearwell", "distribution")


def spec(days: int = 30, seed: int = 5) -> RunSpec:
    """Return a run spec covering ``days`` days at one-minute samples."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(days=days),
        sample_interval=timedelta(minutes=1),
    )


def calendar(
    seed: int = 5, days: int = 30, practice: MaintenancePractice | None = None
) -> MaintenanceCalendar:
    """Plan a register over ``days`` with a fresh generator."""
    rng = numpy.random.default_rng(seed)
    return plan_maintenance(rng, spec(days, seed), ASSETS, practice or MaintenancePractice())


class TestTheRegisterIsPlausible:
    """A calendar a maintenance planner would recognise."""

    def test_it_raises_orders_against_every_asset(self) -> None:
        assert {order.asset_id for order in calendar().orders} == set(ASSETS)

    def test_routine_orders_repeat_on_their_interval(self) -> None:
        register = calendar(days=90)
        routine = [
            order
            for order in register.orders
            if order.kind is MaintenanceKind.ROUTINE and order.asset_id == "intake"
        ]
        gaps = {later.start - earlier.start for earlier, later in pairwise(routine)}
        assert gaps == {register.practice.routine_interval}

    def test_a_shutdown_covers_every_asset_at_once(self) -> None:
        register = calendar(
            days=90, practice=MaintenancePractice(shutdown_interval=timedelta(days=45))
        )
        shutdowns = [o for o in register.orders if o.kind is MaintenanceKind.SHUTDOWN]
        assert shutdowns
        by_start: dict[datetime, set[str]] = {}
        for order in shutdowns:
            by_start.setdefault(order.start, set()).add(order.asset_id)
        assert all(assets == set(ASSETS) for assets in by_start.values())

    def test_reactive_callouts_appear_and_are_not_on_a_grid(self) -> None:
        reactive = [o for o in calendar(days=180).orders if o.kind is MaintenanceKind.REACTIVE]
        assert len(reactive) > 1
        starts = sorted(order.start for order in reactive)
        gaps = {later - earlier for earlier, later in pairwise(starts)}
        assert len(gaps) > 1

    def test_some_orders_sanction_nothing(self) -> None:
        """Drafts and cancellations, so a reader treating every row as cover fails on data."""
        register = calendar(days=180)
        assert any(not order.sanctioning for order in register.orders)
        assert any(order.sanctioning for order in register.orders)

    def test_no_order_runs_past_the_end_of_the_run(self) -> None:
        run = spec(30)
        assert all(order.end <= run.start + run.duration for order in calendar().orders)

    def test_orders_are_earliest_first(self) -> None:
        starts = [order.start for order in calendar(days=90).orders]
        assert starts == sorted(starts)

    def test_the_practice_is_carried_with_the_register(self) -> None:
        """A reader has to be able to judge what the calendar was generated from."""
        assert calendar().practice.routine_interval == timedelta(days=14)


class TestCoverageMeansSomethingSpecific:
    """`covers` is the primitive the whole CMMS tie rests on."""

    def test_a_sanctioning_order_covers_its_own_asset_inside_its_window(self) -> None:
        order = WorkOrder(
            order_id="WO-1",
            asset_id="intake",
            kind=MaintenanceKind.ROUTINE,
            start=START,
            end=START + timedelta(hours=4),
            sanctioning=True,
        )
        assert order.covers(START + timedelta(hours=1), "intake") is True

    def test_a_non_sanctioning_order_covers_nothing_inside_its_own_window(self) -> None:
        """ADR 0069: a cancelled order authorised no change, whatever its dates say."""
        order = WorkOrder(
            order_id="WO-1",
            asset_id="intake",
            kind=MaintenanceKind.ROUTINE,
            start=START,
            end=START + timedelta(hours=4),
            sanctioning=False,
        )
        assert order.covers(START + timedelta(hours=1), "intake") is False

    def test_asset_identity_is_exact(self) -> None:
        order = WorkOrder(
            order_id="WO-1",
            asset_id="P-101",
            kind=MaintenanceKind.ROUTINE,
            start=START,
            end=START + timedelta(hours=4),
            sanctioning=True,
        )
        assert order.covers(START + timedelta(hours=1), "P-1010") is False

    def test_an_inverted_window_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="finishes before it starts"):
            WorkOrder(
                order_id="WO-1",
                asset_id="intake",
                kind=MaintenanceKind.ROUTINE,
                start=START + timedelta(hours=4),
                end=START,
                sanctioning=True,
            )

    def test_covering_returns_the_earliest_of_several(self) -> None:
        register = calendar(days=180)
        order = next(o for o in register.orders if o.sanctioning)
        found = register.covering(order.start, order.asset_id)
        assert found is not None
        assert found.start <= order.start

    def test_covering_returns_none_where_nothing_covers(self) -> None:
        register = MaintenanceCalendar()
        assert register.covering(START, "intake") is None


class TestTheRegisterIsIndependentOfAnyAttack:
    """The property the CMMS exercise rests on, pinned as behaviour."""

    def test_the_same_seed_and_practice_give_the_same_register(self) -> None:
        assert calendar(seed=7).orders == calendar(seed=7).orders

    def test_a_different_seed_gives_a_different_register(self) -> None:
        assert calendar(seed=7).orders != calendar(seed=8).orders

    def test_planning_needs_no_attack_and_produces_orders_anyway(self) -> None:
        """No attack exists anywhere in this test, and the register is still full."""
        assert len(calendar(days=90).orders) > 10

    def test_covered_windows_is_computed_after_the_fact(self) -> None:
        """Labelling: hand it moments, get back the collisions. It places nothing."""
        register = calendar(days=90)
        sanctioning = register.sanctioning()
        assert sanctioning
        inside = sanctioning[0].start + timedelta(minutes=1)
        outside = register.orders[-1].end + timedelta(days=400)
        found = register.covered_windows({sanctioning[0].asset_id: [inside, outside]})
        assert [moment for _, moment, _ in found] == [inside]

    def test_covered_windows_is_empty_when_nothing_collides(self) -> None:
        register = calendar(days=30)
        far_future = START + timedelta(days=900)
        assert register.covered_windows({"intake": [far_future]}) == ()

    def test_an_empty_asset_list_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one asset"):
            plan_maintenance(numpy.random.default_rng(1), spec(), ())


class TestTheRealAdapterReadsWhatIsWritten:
    """The generator held to the reader's standard, not to its own."""

    def test_sap_export_round_trips_through_the_shipped_schema(self, tmp_path: Path) -> None:
        register = calendar(days=90)
        path = tmp_path / "sap.csv"
        write_sap_pm_export(register, path)
        records = load_work_order_export(path, SAP_PM_SCHEMA, declared_assets=ASSETS)
        assert len(records) == len(register.sanctioning())

    def test_maximo_export_round_trips_through_the_shipped_schema(self, tmp_path: Path) -> None:
        register = calendar(days=90)
        path = tmp_path / "maximo.csv"
        write_maximo_export(register, path)
        records = load_work_order_export(path, MAXIMO_SCHEMA, declared_assets=ASSETS)
        assert len(records) == len(register.sanctioning())

    def test_the_reader_drops_exactly_the_non_sanctioning_orders(self, tmp_path: Path) -> None:
        """The refusal ADR 0069 D5 names, exercised by generated data rather than a fixture."""
        register = calendar(days=180)
        path = tmp_path / "maximo.csv"
        write_maximo_export(register, path)
        records = load_work_order_export(path, MAXIMO_SCHEMA, declared_assets=ASSETS)
        assert {record.order_id for record in records} == {
            order.order_id for order in register.sanctioning()
        }

    def test_windows_survive_the_round_trip_to_the_second(self, tmp_path: Path) -> None:
        register = calendar(days=90)
        path = tmp_path / "sap.csv"
        write_sap_pm_export(register, path)
        records = load_work_order_export(path, SAP_PM_SCHEMA, declared_assets=ASSETS)
        by_id = {order.order_id: order for order in register.sanctioning()}
        for record in records:
            assert record.start == by_id[record.order_id].start
            assert record.end == by_id[record.order_id].end

    def test_the_reader_agrees_with_the_generator_about_coverage(self, tmp_path: Path) -> None:
        """Two independent implementations of "is this covered", asked the same question."""
        register = calendar(days=90)
        path = tmp_path / "maximo.csv"
        write_maximo_export(register, path)
        records = load_work_order_export(path, MAXIMO_SCHEMA, declared_assets=ASSETS)
        order = register.sanctioning()[0]
        moment = order.start + timedelta(minutes=1)
        assert covering_order(records, moment, [order.asset_id]) is not None
        assert register.covering(moment, order.asset_id) is not None

    def test_the_export_reaches_the_work_order_inlet(self, tmp_path: Path) -> None:
        """The last hop: observations the E3 inlet accepts."""
        register = calendar(days=90)
        path = tmp_path / "sap.csv"
        write_sap_pm_export(register, path)
        records = load_work_order_export(path, SAP_PM_SCHEMA, declared_assets=ASSETS)
        observations = observations_from_work_orders(records)
        assert len(observations) == len(records)
        assert all(len(observation.entity_ids) == 2 for observation in observations)

    def test_an_undeclared_asset_is_refused_by_the_reader(self, tmp_path: Path) -> None:
        register = calendar(days=30)
        path = tmp_path / "sap.csv"
        write_sap_pm_export(register, path)
        with pytest.raises(Exception, match=r"intake|dosing|filtration|clearwell|distribution"):
            load_work_order_export(path, SAP_PM_SCHEMA, declared_assets=("something-else",))

    def test_the_columns_are_the_systems_own_field_names(self) -> None:
        assert SAP_PM_COLUMNS == ("AUFNR", "EQUNR", "GSTRP", "GLTRP", "STTXT", "AUART")
        assert MAXIMO_COLUMNS == (
            "WONUM",
            "ASSETNUM",
            "SCHEDSTART",
            "SCHEDFINISH",
            "STATUS",
            "WORKTYPE",
        )


class TestThePracticeIsValidated:
    """A practice that cannot happen is a declaration mistake, not a schedule."""

    @pytest.mark.parametrize("field", ["routine_interval", "routine_duration", "reactive_duration"])
    def test_a_non_positive_duration_is_refused(self, field: str) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            MaintenancePractice(**{field: timedelta(0)})  # type: ignore[arg-type]

    def test_a_non_positive_shutdown_interval_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="shutdown_interval must be positive"):
            MaintenancePractice(shutdown_interval=timedelta(0))

    def test_an_idle_share_outside_a_fraction_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            MaintenancePractice(idle_share=1.5)

    def test_every_order_sanctions_when_the_idle_share_is_zero(self) -> None:
        assert all(
            order.sanctioning
            for order in calendar(days=90, practice=MaintenancePractice(idle_share=0.0)).orders
        )

    def test_no_order_sanctions_when_the_idle_share_is_one(self) -> None:
        assert not any(
            order.sanctioning
            for order in calendar(days=90, practice=MaintenancePractice(idle_share=1.0)).orders
        )
