"""S7 process parquet is unlabelled Track A telemetry, not a scored plant (ADR 0047).

The shipped adapter is not extended. Packets parquet is not a pcap. ``normal`` is not an
attack. This suite pins the refusal so a silent join of packet labels cannot look like a
cycle win.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.eval.s7_process import (
    NOT_A_COMMAND_CORPUS_CAVEAT,
    PACKETS_ARE_NOT_PCAP_CAVEAT,
    SHIPPED_MD5,
    SHIPPED_N_ROWS,
    SHIPPED_PROCESS_COLUMNS,
    UNLABELLED_PROCESS_CAVEAT,
    PrepareError,
    is_data_modification,
    label_columns,
    prepare_labelled_track_a,
    process_table_is_unlabelled,
    require_shipped_process_schema,
)

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "data" / "registry.json"
RAW = REPO / "data" / "s7-data-modification" / "process_dataset.parquet"


def test_normal_is_not_data_modification() -> None:
    """The SWaT trap: a textual 'normal' must not score as an attack."""
    assert is_data_modification("normal") is False
    assert is_data_modification("Normal") is False
    assert is_data_modification("data_modification") is True
    assert is_data_modification("DATA_MODIFICATION") is True
    assert is_data_modification(0) is False


def test_shipped_header_has_no_label_column() -> None:
    assert process_table_is_unlabelled(SHIPPED_PROCESS_COLUMNS) is True
    assert label_columns(SHIPPED_PROCESS_COLUMNS) == ()
    assert "label" not in SHIPPED_PROCESS_COLUMNS
    assert len(SHIPPED_PROCESS_COLUMNS) == 21


def test_actuator_on_off_is_not_a_label() -> None:
    assert label_columns(("out_pv_on_off", "out_batt_target_power")) == ()


def test_a_label_column_is_detected() -> None:
    assert label_columns(("archive_recv_ts", "label", "in_batt_voltage")) == ("label",)
    assert process_table_is_unlabelled(("timestamp", "attack_active", "v")) is False


def test_prepare_refuses_the_shipped_unlabelled_schema() -> None:
    with pytest.raises(PrepareError, match="no label column"):
        prepare_labelled_track_a(SHIPPED_PROCESS_COLUMNS)
    assert "ADR 0047" in UNLABELLED_PROCESS_CAVEAT
    assert "pcap" in PACKETS_ARE_NOT_PCAP_CAVEAT
    assert "command" in NOT_A_COMMAND_CORPUS_CAVEAT.lower()


def test_a_new_label_column_forces_the_adr_to_be_revisited() -> None:
    with pytest.raises(PrepareError, match="revisited"):
        require_shipped_process_schema(("archive_recv_ts", "label", "in_batt_voltage"))


def test_registry_does_not_treat_s7_as_pcap_or_labelled_track_a() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = next(item for item in registry["datasets"] if item["name"] == "s7-data-modification")
    assert entry.get("format") != "pcap"
    assert entry.get("status") != "integrated"
    labels = entry["labels"]
    assert labels.get("unverified") is False
    note = str(labels.get("note", "")).lower()
    assert "no label" in note or "absent" in note
    caveats = " ".join(entry.get("caveats") or [])
    assert "pcap" in caveats.lower() or "command" in caveats.lower()
    files = entry.get("files") or []
    names = [item.get("filename") for item in files]
    assert "packets_dataset.parquet" not in names
    assert "process_dataset.parquet" in names
    process = next(item for item in files if item["filename"] == "process_dataset.parquet")
    assert process["md5"] == SHIPPED_MD5
    assert process["size_bytes"] == 359657


@pytest.mark.skipif(not RAW.is_file(), reason="s7 process parquet is not on disk")
def test_shipped_file_matches_the_unlabelled_schema() -> None:
    """Files win: 13,912 rows, 21 process columns, no label (ADR 0047)."""
    pyarrow = pytest.importorskip("pyarrow")
    del pyarrow
    pandas = pytest.importorskip("pandas")
    frame = pandas.read_parquet(RAW)
    header = tuple(str(column) for column in frame.columns)
    require_shipped_process_schema(header)
    assert len(frame) == SHIPPED_N_ROWS
    with pytest.raises(PrepareError, match="no label column"):
        prepare_labelled_track_a(header)
