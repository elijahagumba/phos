"""Preparation of Data4Cyber process telemetry into a labelled CSV (Track A).

This is not a command-corpus path. The shipped adapter is not extended. Labels stay 1 Hz
process phases: ``attack_active`` is the row flag, reconnaissance seconds remain labelled,
and attacker/phase-copy columns never enter the plant vector. False-positives-per-normal-hour
must not be quoted as a control-room budget (ADR 0033 / 0040).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas
import pytest

from phos.eval.data4cyber import (
    FP_HOUR_RULER_CAVEAT,
    LEAK_COLUMNS,
    NOT_A_COMMAND_CORPUS_CAVEAT,
    Data4CyberPrepareSpec,
    PrepareError,
    default_prepare_spec,
    is_attack_active,
    prepare_corpus,
    process_columns,
)
from phos.eval.datasets import LabelledCsvAdapter

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "data4cyber"
REGISTRY = REPO / "data" / "registry.json"


def _spec(**overrides: object) -> Data4CyberPrepareSpec:
    fields: dict[str, object] = {
        "dataset_root": "data4cyber_dataset",
        "train_scenario": "S0_benign_baseline",
        "test_scenario": "S1_industroyer_pv",
        "train_output_file": "train.csv",
        "test_output_file": "test.csv",
    }
    fields.update(overrides)
    return Data4CyberPrepareSpec.model_validate(fields)


def _write_scenario(
    root: Path,
    scenario: str,
    rows: list[dict[str, object]],
) -> None:
    frame = pandas.DataFrame(rows)
    path = root / "data4cyber_dataset" / scenario / "dataset.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _grid_row(
    timestamp: str,
    *,
    attack_active: bool,
    attack_phase: str,
    voltage: float,
    current: float,
    **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "timestamp": timestamp,
        "attack_active": attack_active,
        "attack_phase": attack_phase,
        "Substation-AC-Meter.uln1": voltage,
        "PV-Inverter-AC-Meter.p_sum3": current,
    }
    row.update(extra)
    return row


def test_boolean_true_is_attack_active() -> None:
    assert is_attack_active(True) is True
    assert is_attack_active(False) is False
    assert is_attack_active("True") is True
    assert is_attack_active("true") is True
    assert is_attack_active("1") is True
    assert is_attack_active("False") is False
    assert is_attack_active("normal") is False


def test_process_columns_drop_every_named_leak() -> None:
    header = [
        "timestamp",
        "attack_active",
        "attack_phase",
        "attack_phase_all",
        "Attacker.event",
        "Attacker.new_value",
        "Substation-AC-Meter.uln1",
        "PV-Inverter-AC-Meter.p_sum3",
    ]
    assert process_columns(header) == [
        "Substation-AC-Meter.uln1",
        "PV-Inverter-AC-Meter.p_sum3",
    ]


def test_attacker_prefix_is_a_leak_even_when_not_listed() -> None:
    header = ["timestamp", "attack_active", "Attacker.invented", "meter.v"]
    assert process_columns(header) == ["meter.v"]


def test_prepare_refuses_a_contaminated_s0(tmp_path: Path) -> None:
    _write_scenario(
        tmp_path,
        "S0_benign_baseline",
        [
            _grid_row(
                "2026-03-05 13:19:02.660000+00:00",
                attack_active=True,
                attack_phase="normal",
                voltage=230.0,
                current=1.0,
            )
        ],
    )
    _write_scenario(
        tmp_path,
        "S1_industroyer_pv",
        [
            _grid_row(
                "2026-03-06 10:49:02.510000+00:00",
                attack_active=True,
                attack_phase="s1_industroyer_active_solar_power",
                voltage=220.0,
                current=2.0,
            )
        ],
    )
    with pytest.raises(PrepareError, match="attack-free"):
        prepare_corpus(tmp_path, _spec())


def test_prepare_drops_leaks_and_keeps_s0_plant_identity(tmp_path: Path) -> None:
    _write_scenario(
        tmp_path,
        "S0_benign_baseline",
        [
            _grid_row(
                "2026-03-05 13:19:02.660000+00:00",
                attack_active=False,
                attack_phase="normal",
                voltage=230.0,
                current=1.0,
            ),
            _grid_row(
                "2026-03-05 13:19:03.660000+00:00",
                attack_active=False,
                attack_phase="normal",
                voltage=231.0,
                current=1.1,
            ),
        ],
    )
    _write_scenario(
        tmp_path,
        "S1_industroyer_pv",
        [
            _grid_row(
                "2026-03-06 10:49:02.510000+00:00",
                attack_active=False,
                attack_phase="normal",
                voltage=229.0,
                current=0.9,
                **{"Attacker.event": "none", "attack_phase_all": "normal"},
            ),
            _grid_row(
                "2026-03-06 10:49:03.510000+00:00",
                attack_active=True,
                attack_phase="s1_reconnaissance_nmap_solar_power",
                voltage=210.0,
                current=4.0,
                **{"Attacker.event": "nmap", "attack_phase_all": "recon"},
            ),
            _grid_row(
                "2026-03-06 10:49:04.510000+00:00",
                attack_active=True,
                attack_phase="s1_industroyer_active_solar_power",
                voltage=180.0,
                current=9.0,
                **{"Attacker.event": "write", "attack_phase_all": "manip"},
            ),
        ],
    )
    result = prepare_corpus(tmp_path, _spec())
    train = pandas.read_csv(tmp_path / "train.csv")
    test = pandas.read_csv(tmp_path / "test.csv")
    leak_in_train = set(train.columns) & LEAK_COLUMNS
    leak_in_test = set(test.columns) & LEAK_COLUMNS
    assert leak_in_train == set()
    assert leak_in_test == set()
    assert "Attacker.event" not in test.columns
    assert list(train.columns) == list(test.columns)
    assert list(result.signal_columns) == [
        "Substation-AC-Meter.uln1",
        "PV-Inverter-AC-Meter.p_sum3",
    ]
    assert int(train["label"].sum()) == 0
    assert int(test["label"].sum()) == 2
    assert result.n_reconnaissance_rows == 1
    assert result.n_train_rows == 2
    assert result.n_test_rows == 3
    assert FP_HOUR_RULER_CAVEAT in result.source_note
    assert NOT_A_COMMAND_CORPUS_CAVEAT in result.source_note


def test_prepared_csv_loads_through_the_shipped_adapter(tmp_path: Path) -> None:
    test_prepare_drops_leaks_and_keeps_s0_plant_identity(tmp_path)
    adapter = LabelledCsvAdapter(
        path=tmp_path / "test.csv",
        timestamp_column="timestamp",
        label_column="label",
        name="data4cyber-fixture",
    )
    dataset = adapter.load()
    assert len(dataset.attack_intervals) == 1
    assert dataset.attack_intervals[0].label == "attack"
    features = {obs.feature for obs in dataset.observations}
    assert "attack_phase" not in features
    assert "Attacker.event" not in features


def test_registry_spec_is_s0_train_s1_test_and_not_pcap() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = next(item for item in registry["datasets"] if item["name"] == "data4cyber")
    spec = entry.get("grid_prepare")
    assert isinstance(spec, dict), "data4cyber must carry a grid_prepare spec (Track A)"
    assert spec["train_scenario"] == "S0_benign_baseline"
    assert spec["test_scenario"] == "S1_industroyer_pv"
    assert entry.get("format") != "pcap"
    caveats = entry.get("caveats")
    assert isinstance(caveats, list)
    joined = " ".join(caveats)
    assert "command" in joined.lower()
    assert "false-positives-per-normal-hour" in joined.lower() or "FP/hour" in joined


def test_default_spec_matches_the_campaign_s0_s1_pair() -> None:
    spec = default_prepare_spec()
    assert spec.train_scenario == "S0_benign_baseline"
    assert spec.test_scenario == "S1_industroyer_pv"


@pytest.mark.skipif(
    not (RAW / "data4cyber_dataset" / "S0_benign_baseline" / "dataset.csv").is_file(),
    reason="data4cyber payload is not on disk",
)
def test_shipped_s0_s1_prepare_on_the_real_files(tmp_path: Path) -> None:
    """Files win: S0 is attack-free; S1 recon seconds stay labelled; plant columns match."""
    import shutil

    dest_root = tmp_path / "data4cyber_dataset"
    for scenario in ("S0_benign_baseline", "S1_industroyer_pv"):
        src = RAW / "data4cyber_dataset" / scenario / "dataset.csv"
        dest = dest_root / scenario / "dataset.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    result = prepare_corpus(tmp_path, _spec())
    train = pandas.read_csv(tmp_path / "train.csv")
    test = pandas.read_csv(tmp_path / "test.csv")
    assert int(train["label"].sum()) == 0
    assert result.n_train_rows == 1798
    assert result.n_test_rows == 1798
    assert result.n_reconnaissance_rows == 11
    assert int(test["label"].sum()) == 913
    assert list(train.columns) == list(test.columns)
    for column in LEAK_COLUMNS:
        assert column not in train.columns
        assert column not in test.columns
    assert result.n_signals == 151
    adapter = LabelledCsvAdapter(
        path=tmp_path / "test.csv",
        timestamp_column="timestamp",
        label_column="label",
        name="data4cyber-s1",
    )
    loaded = adapter.load()
    assert loaded.attack_intervals
    assert all(interval.label == "attack" for interval in loaded.attack_intervals)
