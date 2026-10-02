"""Reading a real maintenance system's export into the Session E3 work-order inlet.

E3 built the inlet and wired the templates: a work-order fact supports `engineering_maintenance`
and contradicts `unauthorised_control_activity`. It left no way to get a work order *in* —
`promote_work_orders` takes observations, so every caller so far hand-built them. These tests
cover the adapter that closes that gap.

Three properties carry the weight:

- **Missing is not empty.** An absent export raises rather than returning nothing, because an
  empty export is the finding "no sanctioned change in this window" and a missing one is silence.
  Letting them collapse would make a forgotten file read as an alibi for the whole plant.
- **Identity is exact and declared.** `P-101` never covers `P-1010`, columns are never sniffed,
  and an order naming an undeclared asset is refused rather than dropped.
- **The join actually moves the explanation.** The end-to-end test walks a Maximo export all the
  way to a template match and asserts the two roles E3 wired.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    WORK_ORDER_MARKER,
    atlas_library,
    promote_work_orders,
    work_order_feature_of,
)
from phos.atlas.cmms import (
    MAXIMO_SCHEMA,
    SAP_PM_SCHEMA,
    CmmsExportMissingError,
    CmmsSchema,
    UndeclaredAssetError,
    WorkOrderRecord,
    covering_order,
    discover_work_order_exports,
    load_work_order_export,
    observations_from_work_orders,
)
from phos.ontology import EvidenceRole
from phos.reasoning import FittedPlattCalibrator

CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
NOON = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

MAXIMO_EXPORT = """WONUM,ASSETNUM,SCHEDSTART,SCHEDFINISH,STATUS,WORKTYPE
WO-1001,P-101,2026-03-01T10:00:00,2026-03-01T14:00:00,APPR,PM
WO-1002,P-102,2026-03-01T09:00:00,2026-03-01T09:30:00,CAN,CM
WO-1003,P-101,2026-03-02T08:00:00,2026-03-02T12:00:00,COMP,CM
"""

SAP_EXPORT = """AUFNR,EQUNR,GSTRP,GLTRP,STTXT,AUART
400001,P-101,20260301,20260301,REL,PM01
400002,P-102,20260301,20260301,CRTD,PM01
"""


def write(tmp_path: Path, name: str, body: str) -> Path:
    """Write one export fixture and return its path."""
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def record(asset: str, start: datetime, end: datetime, order_id: str = "WO-1") -> WorkOrderRecord:
    """Build one sanctioning record directly, for coverage tests."""
    return WorkOrderRecord(
        order_id=order_id,
        asset_id=asset,
        start=start,
        end=end,
        status="APPR",
        schema_name="maximo",
    )


class TestMissingIsNotEmpty:
    """An absent export is silence. An empty one is a finding. They must not collapse."""

    def test_an_absent_export_raises_rather_than_returning_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(CmmsExportMissingError, match="not an empty one"):
            load_work_order_export(tmp_path / "nope.csv", MAXIMO_SCHEMA)

    def test_an_export_with_no_rows_loads_as_an_empty_result(self, tmp_path: Path) -> None:
        path = write(tmp_path, "wo.csv", "WONUM,ASSETNUM,SCHEDSTART,SCHEDFINISH,STATUS,WORKTYPE\n")
        assert load_work_order_export(path, MAXIMO_SCHEMA) == ()


class TestColumnsAreDeclaredNeverSniffed:
    """A column guessed wrong is a window silently shifted."""

    def test_a_missing_declared_column_is_refused_and_named(self, tmp_path: Path) -> None:
        path = write(tmp_path, "wo.csv", "WONUM,ASSETNUM,STATUS\nWO-1,P-101,APPR\n")
        with pytest.raises(ValueError, match="SCHEDSTART"):
            load_work_order_export(path, MAXIMO_SCHEMA)

    def test_a_timestamp_matching_no_declared_format_is_refused(self, tmp_path: Path) -> None:
        body = (
            "WONUM,ASSETNUM,SCHEDSTART,SCHEDFINISH,STATUS,WORKTYPE\n"
            "WO-1,P-101,01/03/2026,2026-03-01T14:00:00,APPR,PM\n"
        )
        with pytest.raises(ValueError, match="matches none of schema"):
            load_work_order_export(write(tmp_path, "wo.csv", body), MAXIMO_SCHEMA)

    def test_both_shipped_schemas_read_their_own_field_names(self, tmp_path: Path) -> None:
        maximo = load_work_order_export(write(tmp_path, "m.csv", MAXIMO_EXPORT), MAXIMO_SCHEMA)
        sap = load_work_order_export(write(tmp_path, "s.csv", SAP_EXPORT), SAP_PM_SCHEMA)
        assert [item.order_id for item in maximo] == ["WO-1001", "WO-1003"]
        assert [item.order_id for item in sap] == ["400001"]

    def test_a_schema_must_declare_casefolded_statuses(self) -> None:
        with pytest.raises(ValueError, match="casefolded"):
            CmmsSchema(
                name="shouty",
                order_id_column="WONUM",
                asset_column="ASSETNUM",
                start_column="S",
                end_column="E",
                status_column="STATUS",
                sanctioning_statuses=frozenset({"APPR"}),
                timestamp_formats=("%Y-%m-%d",),
            )


class TestOnlySanctioningOrdersCount:
    """A cancelled order and a draft authorised nothing."""

    def test_a_cancelled_maximo_order_does_not_sanction(self, tmp_path: Path) -> None:
        loaded = load_work_order_export(write(tmp_path, "m.csv", MAXIMO_EXPORT), MAXIMO_SCHEMA)
        assert all(item.order_id != "WO-1002" for item in loaded)

    def test_a_draft_sap_order_does_not_sanction(self, tmp_path: Path) -> None:
        loaded = load_work_order_export(write(tmp_path, "s.csv", SAP_EXPORT), SAP_PM_SCHEMA)
        assert all(item.status.casefold() != "crtd" for item in loaded)

    def test_records_come_back_earliest_first(self, tmp_path: Path) -> None:
        loaded = load_work_order_export(write(tmp_path, "m.csv", MAXIMO_EXPORT), MAXIMO_SCHEMA)
        assert [item.start for item in loaded] == sorted(item.start for item in loaded)


class TestAssetIdentityIsExactAndDeclared:
    """A prefix match would let one order exonerate a unit it never named."""

    def test_an_undeclared_asset_is_refused_not_dropped(self, tmp_path: Path) -> None:
        path = write(tmp_path, "m.csv", MAXIMO_EXPORT)
        with pytest.raises(UndeclaredAssetError, match="P-10"):
            load_work_order_export(path, MAXIMO_SCHEMA, declared_assets={"P-999"})

    def test_a_declared_asset_set_that_covers_the_export_loads(self, tmp_path: Path) -> None:
        path = write(tmp_path, "m.csv", MAXIMO_EXPORT)
        loaded = load_work_order_export(path, MAXIMO_SCHEMA, declared_assets={"P-101", "P-102"})
        assert len(loaded) == 2

    def test_a_prefix_is_not_a_match(self) -> None:
        order = record("P-101", NOON, NOON + timedelta(hours=2))
        assert order.covers(NOON, "P-101") is True
        assert order.covers(NOON, "P-1010") is False

    def test_window_bounds_are_inclusive(self) -> None:
        order = record("P-101", NOON, NOON + timedelta(hours=2))
        assert order.covers(NOON, "P-101") is True
        assert order.covers(NOON + timedelta(hours=2), "P-101") is True
        assert order.covers(NOON - timedelta(seconds=1), "P-101") is False

    def test_a_backwards_window_cannot_be_built(self) -> None:
        with pytest.raises(ValueError, match="finishes before it starts"):
            WorkOrderRecord(
                order_id="WO-1",
                asset_id="P-101",
                start=NOON,
                end=NOON - timedelta(hours=1),
                status="APPR",
                schema_name="maximo",
            )


class TestCoveringOrder:
    """Which order, if any, authorised this moment on this unit."""

    def test_returns_the_earliest_covering_order(self) -> None:
        late = record("P-101", NOON - timedelta(hours=1), NOON + timedelta(hours=1), "WO-B")
        early = record("P-101", NOON - timedelta(hours=3), NOON + timedelta(hours=1), "WO-A")
        found = covering_order([late, early], NOON, ["P-101"])
        assert found is not None
        assert found.order_id == "WO-A"

    def test_returns_none_when_nothing_covers(self) -> None:
        order = record("P-101", NOON, NOON + timedelta(hours=1))
        assert covering_order([order], NOON + timedelta(days=1), ["P-101"]) is None
        assert covering_order([order], NOON, ["P-102"]) is None

    def test_any_of_the_units_signals_may_match(self) -> None:
        order = record("P-102", NOON, NOON + timedelta(hours=1))
        assert covering_order([order], NOON, ["P-101", "P-102"]) is not None


class TestTheJoinMovesTheExplanation:
    """The point of the whole module: a real export reaches the templates and changes the story."""

    def test_a_maximo_export_reaches_the_inlet_and_is_stamped(self, tmp_path: Path) -> None:
        records = load_work_order_export(write(tmp_path, "m.csv", MAXIMO_EXPORT), MAXIMO_SCHEMA)
        facts = promote_work_orders(observations_from_work_orders(records), CERTAIN)
        assert len(facts) == 2
        for fact in facts:
            assert fact.evidence.summary.startswith(WORK_ORDER_MARKER)
            assert work_order_feature_of(fact.evidence) == "work_order"

    def test_an_exported_order_supports_maintenance_and_contradicts_unauthorised_control(
        self, tmp_path: Path
    ) -> None:
        records = load_work_order_export(write(tmp_path, "m.csv", MAXIMO_EXPORT), MAXIMO_SCHEMA)
        fact = promote_work_orders(observations_from_work_orders(records), CERTAIN)[0]
        roles = {
            match.template.template_id: match.role
            for match in atlas_library().matches(fact.evidence, {})
        }
        assert roles[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
        assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY

    def test_the_observation_names_the_order_then_the_asset(self, tmp_path: Path) -> None:
        # promote_work_orders summarises using the LAST entity as the unit changed.
        records = load_work_order_export(write(tmp_path, "m.csv", MAXIMO_EXPORT), MAXIMO_SCHEMA)
        first = observations_from_work_orders(records)[0]
        assert first.entity_ids == ["WO-1001", "P-101"]
        assert first.context["status"] == "APPR"
        assert first.value == pytest.approx(4 * 3600.0)

    def test_an_empty_export_promotes_nothing_so_atlas_is_unchanged(self, tmp_path: Path) -> None:
        path = write(tmp_path, "wo.csv", "WONUM,ASSETNUM,SCHEDSTART,SCHEDFINISH,STATUS,WORKTYPE\n")
        records = load_work_order_export(path, MAXIMO_SCHEMA)
        assert promote_work_orders(observations_from_work_orders(records), CERTAIN) == []


class TestNoPublicCorpusCarriesWorkOrders:
    """The standing refusal, in ADR 0040's tripwire idiom."""

    def test_discovery_is_empty_so_a_public_coverage_claim_is_refused(self) -> None:
        assert discover_work_order_exports() == ()
        assert discover_work_order_exports({}) == ()

    def test_a_registry_that_declares_an_export_would_be_found(self) -> None:
        registry = {"partner-plant": {"work_order_export": "wo.csv"}, "hai": {"path": "hai.csv"}}
        assert discover_work_order_exports(registry) == ("partner-plant",)

    def test_no_shipped_corpus_declares_one_today(self) -> None:
        import json

        repo = Path(__file__).resolve().parents[2]
        registry = json.loads((repo / "data" / "registry.json").read_text(encoding="utf-8"))
        assert discover_work_order_exports(registry.get("datasets", {})) == ()
