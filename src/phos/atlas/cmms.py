"""Reading a real maintenance system's export into the work-order inlet.

Session E3 built the inlet: `phos.atlas.work_orders` promotes sanctioned-change facts into stamped
`Evidence`, and `phos.atlas.templates` already spends them — a work-order fact **supports**
`engineering_maintenance` and **contradicts** `unauthorised_control_activity`. That pairing is the
only thing in Atlas that separates a commissioning engineer from an attacker on a known station,
which ADR 0027 and the category roadmap both name as the wall the engine cannot climb on process
telemetry alone.

What E3 did not build is any way to *get* a work order in. `promote_work_orders` takes
`Sequence[Observation]`, so every caller so far has hand-built its facts and every test has been a
fixture. This module is the missing half: it reads a computerised maintenance management system's
own export and turns it into those observations.

**The schemas are declared, never sniffed.** `SAP_PM_SCHEMA` and `MAXIMO_SCHEMA` name the columns
those two systems actually export — `AUFNR`/`EQUNR`/`GSTRP`/`GLTRP` and
`WONUM`/`ASSETNUM`/`SCHEDSTART`/`SCHEDFINISH` respectively. A caller whose site renames columns
declares its own `CmmsSchema`. Nothing here guesses which column is a date by looking at the
values, because a column guessed wrong would silently exonerate the wrong window.

**Four refusals, and each exists because the failure it prevents is invisible.**

* **No export, no claim.** `load_work_order_export` raises `CmmsExportMissingError` when the file
  is absent rather than returning an empty tuple. Empty means "this plant had no maintenance in
  the window", which is a *finding*; missing means "we were never told", which is not. Collapsing
  the two would let an absent file read as a plant-wide alibi for nobody.
* **Declared assets only.** An order naming an asset outside the plant's declared set is refused,
  not dropped. A typo in an export that silently matches nothing would make every alert look
  unexplained; one that silently matched everything would explain them all away.
* **Exact asset identity.** No substring, prefix or fuzzy match — `P-101` never covers `P-1010`.
* **Status must sanction.** An order that was cancelled, or is still a draft, did not authorise
  anything. Sanctioning statuses are declared per schema; anything else is counted and logged,
  never silently treated as cover.

**What a covering order is not.** It is not proof the change was benign — an attacker who can read
the maintenance calendar can hide inside a window, and a forged export is a forged export. It is
evidence that maintenance is a live explanation, weighed against the others, with the losers still
visible. Nothing here raises or lowers a detection score, and nothing here writes to
`eval_runs/log.jsonl`.

**No public corpus carries work orders.** HAI, BATADAL, distillation and Data4Cyber label attack
windows, not sanctioned change. `discover_work_order_exports` is the tripwire that keeps that true:
while it returns nothing, a coverage claim on a public corpus is refused, in the same idiom as
`discover_labelled_command_corpora` (ADR 0040). Do not infer a maintenance window from a process
clock.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import Domain, Observation

__all__ = [
    "MAXIMO_SCHEMA",
    "SAP_PM_SCHEMA",
    "WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE",
    "WORK_ORDER_FEATURE_NAME",
    "CmmsExportMissingError",
    "CmmsSchema",
    "UndeclaredAssetError",
    "WorkOrderRecord",
    "covering_order",
    "discover_work_order_exports",
    "load_work_order_export",
    "observations_from_work_orders",
]

logger = logging.getLogger(__name__)

WORK_ORDER_FEATURE_NAME: Final = "work_order"
"""Feature name on a sanctioned-change observation. Matches `work_orders.WORK_ORDER_FEATURE`."""

WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE: Final = (
    "A covering work order makes sanctioned maintenance a live explanation; it does not prove the "
    "change was benign. An attacker with the maintenance calendar can act inside a window, and a "
    "forged export is a forged export. Losers stay visible."
)


class CmmsExportMissingError(FileNotFoundError):
    """Raised when a declared CMMS export is not on disk.

    Distinct from an export that is present and empty. Empty is the measurable statement "no
    sanctioned change in this window"; missing is "we were never told", and only the first may
    be reasoned from.
    """


class UndeclaredAssetError(ValueError):
    """Raised when an export names an asset the plant did not declare.

    Refused rather than dropped: an export whose asset ids do not line up with the plant's own is
    a mapping error, and silently discarding those rows would make every alert on those units look
    unexplained while the file appeared to load cleanly.
    """


class CmmsSchema(BaseModel):
    """How one maintenance system spells a work order.

    Attributes:
        name: Identifies the schema in logs and errors.
        order_id_column: Column holding the work-order number.
        asset_column: Column holding the equipment or asset identifier.
        start_column: Column holding the scheduled or basic start.
        end_column: Column holding the scheduled or basic finish.
        status_column: Column holding the order status.
        order_type_column: Column holding the order type, when the system exports one.
        sanctioning_statuses: Statuses that authorise a change. Compared case-insensitively.
            Anything outside this set does not sanction and is counted, never silently accepted.
        timestamp_formats: `strptime` patterns tried in order. Declared because a date column
            read with the wrong format is a window shifted rather than an error.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    order_id_column: str
    asset_column: str
    start_column: str
    end_column: str
    status_column: str
    order_type_column: str | None = None
    sanctioning_statuses: frozenset[str]
    timestamp_formats: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _statuses_are_lowercased(self) -> CmmsSchema:
        """Sanctioning statuses are matched case-insensitively, so they are stored folded."""
        if any(status != status.casefold() for status in self.sanctioning_statuses):
            raise ValueError(
                f"schema {self.name!r} declares sanctioning statuses that are not casefolded: "
                "store them lowercase so matching cannot depend on how the export was written"
            )
        return self

    def required_columns(self) -> tuple[str, ...]:
        """Return every column that must be present for an export to be readable."""
        columns = [
            self.order_id_column,
            self.asset_column,
            self.start_column,
            self.end_column,
            self.status_column,
        ]
        if self.order_type_column:
            columns.append(self.order_type_column)
        return tuple(columns)


SAP_PM_SCHEMA: Final = CmmsSchema(
    name="sap-pm",
    order_id_column="AUFNR",
    asset_column="EQUNR",
    start_column="GSTRP",
    end_column="GLTRP",
    status_column="STTXT",
    order_type_column="AUART",
    # REL = released, TECO = technically complete. A CRTD draft has not authorised anything and
    # a DLFL deletion flag has withdrawn it.
    sanctioning_statuses=frozenset({"rel", "teco"}),
    timestamp_formats=("%Y%m%d", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"),
)
"""SAP Plant Maintenance order export. Columns are SAP's own field names."""

MAXIMO_SCHEMA: Final = CmmsSchema(
    name="maximo",
    order_id_column="WONUM",
    asset_column="ASSETNUM",
    start_column="SCHEDSTART",
    end_column="SCHEDFINISH",
    status_column="STATUS",
    order_type_column="WORKTYPE",
    # APPR = approved, INPRG = in progress, COMP = complete. WAPPR is awaiting approval and CAN
    # is cancelled; neither authorised a change.
    sanctioning_statuses=frozenset({"appr", "inprg", "comp"}),
    timestamp_formats=("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"),
)
"""IBM Maximo WORKORDER export. Columns are Maximo's own attribute names."""


class WorkOrderRecord(BaseModel):
    """One sanctioned change window on one asset.

    Attributes:
        order_id: The work-order number, as the maintenance system spells it.
        asset_id: The equipment identifier, exactly as declared. Never fuzzy-matched.
        start: First instant the order authorises, UTC, inclusive.
        end: Last instant the order authorises, UTC, inclusive.
        status: Raw status string from the export, kept for traceability.
        order_type: Raw order type, when the system exports one.
        schema_name: Which `CmmsSchema` read it.

    Invariants:
        ``start <= end``.
    """

    model_config = ConfigDict(frozen=True)

    order_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    start: datetime
    end: datetime
    status: str
    order_type: str | None = None
    schema_name: str

    @model_validator(mode="after")
    def _window_is_not_inverted(self) -> WorkOrderRecord:
        if self.start > self.end:
            raise ValueError(
                f"work order {self.order_id!r} finishes before it starts "
                f"({self.start} > {self.end}): a window that runs backwards cannot cover anything"
            )
        return self

    def covers(self, timestamp: datetime, asset_id: str) -> bool:
        """Return whether this order authorises a change to ``asset_id`` at ``timestamp``.

        Asset identity is exact. ``P-101`` never covers ``P-1010``, because a prefix match would
        let one order exonerate a unit it never named.
        """
        return self.asset_id == asset_id and self.start <= timestamp <= self.end


def _parse_timestamp(raw: str, schema: CmmsSchema, order_id: str, column: str) -> datetime:
    """Parse one export timestamp against the schema's declared formats."""
    text = raw.strip()
    for pattern in schema.timestamp_formats:
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(
        f"work order {order_id!r} has {column}={raw!r}, which matches none of schema "
        f"{schema.name!r}'s declared formats {schema.timestamp_formats}: a date read with the "
        "wrong format is a window silently shifted, so this is refused rather than guessed"
    )


def load_work_order_export(
    path: Path,
    schema: CmmsSchema,
    declared_assets: Iterable[str] | None = None,
) -> tuple[WorkOrderRecord, ...]:
    """Read a CMMS export into sanctioned change windows.

    Args:
        path: The export CSV.
        schema: How this maintenance system spells its columns.
        declared_assets: The plant's own asset identifiers. When given, an order naming anything
            outside it is refused. When ``None``, no cross-check is performed and the caller is
            trusting the export's identifiers, which is recorded in the log line.

    Returns:
        Sanctioning orders only, earliest start first. Orders whose status does not sanction are
        excluded and counted in the log.

    Raises:
        CmmsExportMissingError: If ``path`` is not a file. Distinct from an empty export.
        ValueError: If a declared column is absent, or a timestamp matches no declared format.
        UndeclaredAssetError: If an order names an asset outside ``declared_assets``.
    """
    if not path.is_file():
        raise CmmsExportMissingError(
            f"no CMMS export at {path}: an absent file is not an empty one. An empty export says "
            "'no sanctioned change in this window', which may be reasoned from; a missing export "
            "says nothing at all, and must not read as a plant-wide alibi"
        )

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = [name for name in schema.required_columns() if name not in columns]
        if missing:
            raise ValueError(
                f"{path} is missing column(s) {missing} required by schema {schema.name!r}; "
                f"found {sorted(columns)}. Columns are declared, never sniffed"
            )
        rows = list(reader)

    allowed = set(declared_assets) if declared_assets is not None else None
    records: list[WorkOrderRecord] = []
    unsanctioned = 0
    for row in rows:
        order_id = (row[schema.order_id_column] or "").strip()
        asset_id = (row[schema.asset_column] or "").strip()
        status = (row[schema.status_column] or "").strip()
        if allowed is not None and asset_id not in allowed:
            raise UndeclaredAssetError(
                f"work order {order_id!r} names asset {asset_id!r}, which the plant did not "
                "declare. Refused rather than dropped: a mapping error that silently discarded "
                "these rows would make every alert on that unit look unexplained"
            )
        if status.casefold() not in schema.sanctioning_statuses:
            unsanctioned += 1
            continue
        records.append(
            WorkOrderRecord(
                order_id=order_id,
                asset_id=asset_id,
                start=_parse_timestamp(
                    row[schema.start_column], schema, order_id, schema.start_column
                ),
                end=_parse_timestamp(row[schema.end_column], schema, order_id, schema.end_column),
                status=status,
                order_type=(
                    (row[schema.order_type_column] or "").strip() or None
                    if schema.order_type_column
                    else None
                ),
                schema_name=schema.name,
            )
        )

    records.sort(key=lambda record: (record.start, record.order_id))
    logger.info(
        "%s: read %d sanctioning work order(s) from %d row(s) under schema %s; "
        "%d did not sanction; asset cross-check %s",
        path.name,
        len(records),
        len(rows),
        schema.name,
        unsanctioned,
        "on" if allowed is not None else "OFF (export identifiers trusted)",
    )
    return tuple(records)


def covering_order(
    records: Sequence[WorkOrderRecord],
    timestamp: datetime,
    asset_ids: Iterable[str],
) -> WorkOrderRecord | None:
    """Return the earliest order covering any of ``asset_ids`` at ``timestamp``, or ``None``.

    ``None`` means *no order covers this*, which is only meaningful when an export was actually
    loaded. A caller that never loaded one has "unknown", not "uncovered", and must not use this
    function's ``None`` as though it were the former.
    """
    covering = [
        record for record in records for asset_id in asset_ids if record.covers(timestamp, asset_id)
    ]
    if not covering:
        return None
    return min(covering, key=lambda record: (record.start, record.order_id))


def observations_from_work_orders(
    records: Sequence[WorkOrderRecord],
    domain: Domain = Domain.ATLAS,
) -> list[Observation]:
    """Turn sanctioned change windows into observations the E3 inlet can promote.

    Each observation names the order and the asset — in that order, because
    `phos.atlas.work_orders.promote_work_orders` summarises using the **last** entity as the unit
    the change was made to. ``value`` is the window's duration in seconds, which is a measured
    property of the order rather than a score.

    Args:
        records: Sanctioning orders, from `load_work_order_export`.
        domain: Which engine's world these facts belong to.

    Returns:
        One observation per order, earliest first. Feed straight to `promote_work_orders`.
    """
    return [
        Observation(
            entity_ids=[record.order_id, record.asset_id],
            feature=WORK_ORDER_FEATURE_NAME,
            value=(record.end - record.start).total_seconds(),
            timestamp=record.start,
            domain=domain,
            context={
                "order_id": record.order_id,
                "asset_id": record.asset_id,
                "status": record.status,
                "schema": record.schema_name,
                "window_end": record.end.isoformat(),
                **({"order_type": record.order_type} if record.order_type else {}),
            },
        )
        for record in sorted(records, key=lambda item: (item.start, item.order_id))
    ]


def discover_work_order_exports(
    registry: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
) -> tuple[str, ...]:
    """Return the corpora that ship a labelled maintenance export. Empty is the honest answer.

    The tripwire behind this module's standing refusal, in the same idiom as
    `phos.atlas.discover_labelled_command_corpora` (ADR 0040). No public ICS corpus PHOS uses
    labels sanctioned change: HAI, BATADAL, distillation and Data4Cyber label attack windows and
    process phases. While this returns empty, a work-order coverage claim on a public corpus is
    **refused**, and a maintenance window must not be inferred from a process clock.

    Args:
        registry: Registry contents. Accepts the shipped shape — ``registry.json``'s ``datasets``
            list, whose entries carry their own ``name`` — or a name-keyed mapping. Both are
            supported so this can be pointed at the real file rather than a rewritten copy of it.

    Returns:
        Names of corpora declaring a ``work_order_export``, sorted. Empty until one exists.
    """
    if not registry:
        return ()

    entries: list[tuple[str, Mapping[str, object]]] = []
    if isinstance(registry, Mapping):
        entries = [
            (str(name), entry) for name, entry in registry.items() if isinstance(entry, Mapping)
        ]
    else:
        entries = [
            (str(entry.get("name", "")), entry)
            for entry in registry
            if isinstance(entry, Mapping) and entry.get("name")
        ]

    named = tuple(sorted(name for name, entry in entries if entry.get("work_order_export")))
    if named:
        logger.info("registry declares work-order exports for: %s", ", ".join(named))
    return named
