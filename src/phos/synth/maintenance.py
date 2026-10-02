"""A plant's maintenance register, generated from maintenance practice and nothing else.

`phos.atlas.cmms` reads a real SAP PM or Maximo export into the work-order inlet, and
`phos.atlas.templates` already spends what comes out: a covering order **supports**
`engineering_maintenance` and **contradicts** `unauthorised_control_activity`. ADR 0069 built that
path and measured nothing with it, because no public corpus ships a maintenance calendar. This
module is the calendar that lets the join be exercised.

**The generator cannot see the attacks, and that is enforced rather than intended.**
`plan_maintenance` takes a plant's assets and a `MaintenancePractice`; it takes no attack schedule,
no scenario, no window list, and this module imports nothing that could supply one. The reason is
the whole point of the exercise. A calendar laid out around where the attacks are would make every
covered attack a covered attack *by construction*, and a harness that then reported "the CMMS join
changed the ranking" would be reporting the agreement of two things the same author wrote. Coverage
here is a **coincidence between two independent schedules**, which is what it is in a real plant.

Both schedules are drawn from the run's own clock and a declared practice, so an attack landing
inside a covered window happens at the rate the two rhythms happen to collide — and the hard case
ADR 0014 and ADR 0069 both name, *an attacker operating inside a sanctioned window*, appears
because the arithmetic produced it. `covered_windows` reports where that happened after the fact,
for labelling; nothing consults it while either schedule is being built.

**The exports are written by hand and read back by the real adapter.** Nothing here imports
`phos.atlas.cmms`; the column names are literals, and `tests/synth/test_maintenance.py` loads what
this writes through `load_work_order_export` with the shipped `SAP_PM_SCHEMA` and `MAXIMO_SCHEMA`.
A writer that used the reader's own schema objects would be testing the reader against itself, the
same argument `phos.synth.traffic` makes for building Modbus bytes with `struct`.

**Not every order sanctions anything.** Real exports carry drafts and cancellations, and ADR 0069
refuses to read those as cover. The practice draws a share of them so that the refusal is
exercised by data rather than only by a fixture.

**A covering order is not innocence.** It makes maintenance a live explanation weighed against the
others, with the losers still visible. Nothing here raises or lowers a detection score, and no
number measured against this calendar is a detection result.
"""

import csv
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Final

from numpy.random import Generator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import UtcDatetime
from phos.synth.plant import RunSpec

__all__ = [
    "MAINTENANCE_IS_INDEPENDENT_OF_ATTACKS_CAVEAT",
    "MAXIMO_COLUMNS",
    "SAP_PM_COLUMNS",
    "WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE_CAVEAT",
    "MaintenanceCalendar",
    "MaintenanceKind",
    "MaintenancePractice",
    "WorkOrder",
    "plan_maintenance",
    "write_maximo_export",
    "write_sap_pm_export",
]

logger = logging.getLogger(__name__)

MAINTENANCE_IS_INDEPENDENT_OF_ATTACKS_CAVEAT: Final = (
    "This maintenance calendar was generated from a declared maintenance practice — routine "
    "intervals, reactive callouts and planned shutdowns — with no access to the attack schedule. "
    "Where an attack falls inside a covered window it is a collision between two independent "
    "schedules, not a case anybody placed. That is the only construction under which the CMMS "
    "join can be exercised without the result restating its author's intent."
)

WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE_CAVEAT: Final = (
    "A covering work order makes sanctioned maintenance a live explanation; it does not prove the "
    "change was benign. An attacker holding the maintenance calendar can act inside a window. "
    "Nothing generated here raises or lowers a detection score."
)

SAP_PM_COLUMNS: Final = ("AUFNR", "EQUNR", "GSTRP", "GLTRP", "STTXT", "AUART")
"""SAP Plant Maintenance order-export columns, as SAP spells them. Literals on purpose."""

MAXIMO_COLUMNS: Final = ("WONUM", "ASSETNUM", "SCHEDSTART", "SCHEDFINISH", "STATUS", "WORKTYPE")
"""IBM Maximo WORKORDER export columns, as Maximo spells them. Literals on purpose."""

_SAP_TIMESTAMP: Final = "%Y-%m-%d %H:%M:%S"
_MAXIMO_TIMESTAMP: Final = "%Y-%m-%dT%H:%M:%S"

_SAP_SANCTIONING: Final = ("REL", "TECO")
_SAP_IDLE: Final = ("CRTD", "DLFL")
_MAXIMO_SANCTIONING: Final = ("APPR", "INPRG", "COMP")
_MAXIMO_IDLE: Final = ("WAPPR", "CAN")

_HOURS_PER_YEAR: Final = 8760.0


class MaintenanceKind(str, Enum):
    """Why a work order exists. Drawn from how maintenance is actually planned.

    Attributes:
        ROUTINE: Calendar-based preventive maintenance on a fixed interval — the largest share of
            any real register, and the one whose rhythm is genuinely independent of everything.
        REACTIVE: A callout raised when something needed attention. Placed at random through the
            run, because a fault's arrival is not on a calendar.
        SHUTDOWN: A planned outage covering the whole plant, rare and long.
    """

    ROUTINE = "ROUTINE"
    REACTIVE = "REACTIVE"
    SHUTDOWN = "SHUTDOWN"


class WorkOrder(BaseModel):
    """One maintenance order on one asset.

    Attributes:
        order_id: The order number, as a maintenance system would spell it.
        asset_id: The plant unit the work is on. Exact identity; never prefix-matched.
        kind: Why the order exists.
        start: First instant the order covers, UTC, inclusive.
        end: Last instant it covers, UTC, inclusive.
        sanctioning: Whether this order's status authorises a change. A draft or a cancellation
            does not, and is kept in the register precisely so a reader that treats every row as
            cover is caught by data rather than by a hand-built fixture.
        summary: What the work was, in a phrase.

    Invariants:
        The window is not inverted.
    """

    model_config = ConfigDict(frozen=True)

    order_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    kind: MaintenanceKind
    start: UtcDatetime
    end: UtcDatetime
    sanctioning: bool
    summary: str = ""

    @model_validator(mode="after")
    def _check_window(self) -> "WorkOrder":
        if self.end < self.start:
            raise ValueError(
                f"work order {self.order_id!r} finishes before it starts "
                f"({self.start} > {self.end})"
            )
        return self

    def covers(self, timestamp: datetime, asset_id: str) -> bool:
        """Return whether this order authorises a change to ``asset_id`` at ``timestamp``.

        A non-sanctioning order covers nothing, whatever its window says: a cancelled order
        authorised no change, and reading its dates as cover is the failure ADR 0069 refuses.
        """
        if not self.sanctioning:
            return False
        return self.asset_id == asset_id and self.start <= timestamp <= self.end


class MaintenancePractice(BaseModel):
    """How often a plant of this kind does maintenance, and of what sort.

    Every figure is a claim about maintenance practice, defensible on its own terms and stated
    here rather than buried in the drawing code — the same discipline `PlantDescription` applies
    to physics.

    Attributes:
        routine_interval: Spacing between calendar-based preventive orders on one asset.
        routine_duration: How long a routine order's window is.
        reactive_per_year: Expected reactive callouts per asset per year.
        reactive_duration: How long a reactive order's window is.
        shutdown_interval: Spacing between planned outages. ``None`` for a plant that has none
            inside a run of realistic length.
        shutdown_duration: How long an outage lasts.
        idle_share: Fraction of orders that carry a non-sanctioning status — a draft never
            released, or a cancellation. Real registers carry these.

    Invariants:
        Durations and intervals are positive; ``idle_share`` is a fraction.
    """

    model_config = ConfigDict(frozen=True)

    routine_interval: timedelta = timedelta(days=14)
    routine_duration: timedelta = timedelta(hours=4)
    reactive_per_year: float = Field(default=12.0, ge=0.0)
    reactive_duration: timedelta = timedelta(hours=3)
    shutdown_interval: timedelta | None = None
    shutdown_duration: timedelta = timedelta(hours=12)
    idle_share: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_practice(self) -> "MaintenancePractice":
        for name in ("routine_interval", "routine_duration", "reactive_duration"):
            if getattr(self, name) <= timedelta(0):
                raise ValueError(f"{name} must be positive")
        if self.shutdown_interval is not None and self.shutdown_interval <= timedelta(0):
            raise ValueError("shutdown_interval must be positive when declared")
        if self.shutdown_duration <= timedelta(0):
            raise ValueError("shutdown_duration must be positive")
        return self


class MaintenanceCalendar(BaseModel):
    """A plant's maintenance register over one run.

    Attributes:
        orders: Every order raised, earliest start first, sanctioning or not.
        practice: What the register was generated from, kept so a reader can judge it.
    """

    model_config = ConfigDict(frozen=True)

    orders: tuple[WorkOrder, ...] = ()
    practice: MaintenancePractice = MaintenancePractice()

    def covering(self, timestamp: datetime, asset_id: str) -> WorkOrder | None:
        """Return the earliest sanctioning order covering ``asset_id`` at ``timestamp``."""
        covering = [order for order in self.orders if order.covers(timestamp, asset_id)]
        if not covering:
            return None
        return min(covering, key=lambda order: (order.start, order.order_id))

    def sanctioning(self) -> tuple[WorkOrder, ...]:
        """Return only the orders whose status authorises a change."""
        return tuple(order for order in self.orders if order.sanctioning)

    def covered_windows(
        self, moments: Mapping[str, Sequence[datetime]]
    ) -> tuple[tuple[str, datetime, WorkOrder], ...]:
        """Report which of ``moments`` fall inside a sanctioned window. Labelling, after the fact.

        Called once both schedules exist, to find out where they happened to collide. Nothing in
        this module consults it while a schedule is being drawn — see the module docstring.

        Args:
            moments: ``{asset_id: instants of interest on that asset}``.

        Returns:
            One entry per covered moment: the asset, the instant, and the covering order.
        """
        found = [
            (asset_id, moment, order)
            for asset_id, instants in moments.items()
            for moment in instants
            if (order := self.covering(moment, asset_id)) is not None
        ]
        return tuple(sorted(found, key=lambda item: (item[1], item[0])))


def plan_maintenance(
    rng: Generator,
    spec: RunSpec,
    assets: Sequence[str],
    practice: MaintenancePractice | None = None,
) -> MaintenanceCalendar:
    """Lay a maintenance register over a run, from practice alone.

    Note what this signature does not accept: no attack schedule, no scenario, no list of windows
    to avoid or to cover. It cannot place an order relative to an attack because it is never told
    where one is. `tests/synth/test_anti_bias.py` asserts that as a property of the signature and
    of this module's imports, so the guarantee survives an edit that forgets why it mattered.

    Args:
        rng: Drawn from once, here, in the idiom `phos.synth.plant.lay_out_events` uses.
        spec: The run to cover.
        assets: The plant's declared unit identifiers.
        practice: How this plant maintains itself. Defaults to `MaintenancePractice()`.

    Returns:
        The register, earliest start first.

    Raises:
        ValueError: If no assets are given — a register naming nothing cannot cover anything.
    """
    if not assets:
        raise ValueError("a maintenance calendar needs at least one asset to raise orders against")
    practice = MaintenancePractice() if practice is None else practice

    # Every instant is drawn to a whole second. A maintenance system schedules to the second at
    # finest, and a microsecond offset is the one thing a CSV export cannot carry back — so a
    # window that survived planning but not the round trip would be a silently shifted window.
    run_end = spec.start + spec.duration
    run_hours = spec.duration.total_seconds() / 3600.0
    orders: list[WorkOrder] = []
    counter = 0

    def add(asset: str, kind: MaintenanceKind, start: datetime, length: timedelta) -> None:
        nonlocal counter
        counter += 1
        end = min(start + length, run_end)
        orders.append(
            WorkOrder(
                order_id=f"WO-{counter:05d}",
                asset_id=asset,
                kind=kind,
                start=start,
                end=end,
                sanctioning=bool(rng.random() >= practice.idle_share),
                summary=f"{kind.value.lower()} maintenance on {asset}",
            )
        )

    for asset in assets:
        # Routine work starts somewhere inside the first interval and repeats on its own rhythm.
        offset = round(float(rng.random()) * practice.routine_interval.total_seconds())
        moment = spec.start + timedelta(seconds=offset)
        while moment < run_end:
            add(asset, MaintenanceKind.ROUTINE, moment, practice.routine_duration)
            moment += practice.routine_interval

        expected = practice.reactive_per_year * run_hours / _HOURS_PER_YEAR
        for _ in range(int(rng.poisson(expected))):
            start = spec.start + timedelta(
                seconds=round(float(rng.random()) * spec.duration.total_seconds())
            )
            add(asset, MaintenanceKind.REACTIVE, start, practice.reactive_duration)

    if practice.shutdown_interval is not None:
        offset = round(float(rng.random()) * practice.shutdown_interval.total_seconds())
        moment = spec.start + timedelta(seconds=offset)
        while moment < run_end:
            for asset in assets:
                add(asset, MaintenanceKind.SHUTDOWN, moment, practice.shutdown_duration)
            moment += practice.shutdown_interval

    ordered = tuple(sorted(orders, key=lambda order: (order.start, order.order_id)))
    logger.info(
        "planned %d work order(s) across %d asset(s); %d sanctioning",
        len(ordered),
        len(assets),
        sum(1 for order in ordered if order.sanctioning),
    )
    return MaintenanceCalendar(orders=ordered, practice=practice)


def _write_export(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    """Write one CSV export. Shared by both schemas so the two cannot drift in their quoting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)
    logger.info("wrote %d work order(s) to %s", len(rows), path)


def write_sap_pm_export(calendar: MaintenanceCalendar, path: Path) -> None:
    """Write the register as an SAP Plant Maintenance order export.

    Statuses are SAP's own: ``REL`` released and ``TECO`` technically complete sanction a change;
    ``CRTD`` (a draft) and ``DLFL`` (deletion-flagged) do not. Both appear, so a reader that
    treats every row as cover fails on the data rather than only on a fixture.

    Args:
        calendar: The register to export.
        path: Destination CSV. Parent directories are created.
    """
    rows = [
        {
            "AUFNR": order.order_id,
            "EQUNR": order.asset_id,
            "GSTRP": order.start.strftime(_SAP_TIMESTAMP),
            "GLTRP": order.end.strftime(_SAP_TIMESTAMP),
            "STTXT": (
                _SAP_SANCTIONING[index % len(_SAP_SANCTIONING)]
                if order.sanctioning
                else _SAP_IDLE[index % len(_SAP_IDLE)]
            ),
            "AUART": "PM01" if order.kind is MaintenanceKind.REACTIVE else "PM02",
        }
        for index, order in enumerate(calendar.orders)
    ]
    _write_export(path, SAP_PM_COLUMNS, rows)


def write_maximo_export(calendar: MaintenanceCalendar, path: Path) -> None:
    """Write the register as an IBM Maximo WORKORDER export.

    Statuses are Maximo's own: ``APPR``/``INPRG``/``COMP`` sanction a change; ``WAPPR`` (awaiting
    approval) and ``CAN`` (cancelled) do not.

    Args:
        calendar: The register to export.
        path: Destination CSV. Parent directories are created.
    """
    rows = [
        {
            "WONUM": order.order_id,
            "ASSETNUM": order.asset_id,
            "SCHEDSTART": order.start.strftime(_MAXIMO_TIMESTAMP),
            "SCHEDFINISH": order.end.strftime(_MAXIMO_TIMESTAMP),
            "STATUS": (
                _MAXIMO_SANCTIONING[index % len(_MAXIMO_SANCTIONING)]
                if order.sanctioning
                else _MAXIMO_IDLE[index % len(_MAXIMO_IDLE)]
            ),
            "WORKTYPE": "CM" if order.kind is MaintenanceKind.REACTIVE else "PM",
        }
        for index, order in enumerate(calendar.orders)
    ]
    _write_export(path, MAXIMO_COLUMNS, rows)
