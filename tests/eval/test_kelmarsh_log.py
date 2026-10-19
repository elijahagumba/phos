"""The Kelmarsh log rule: held-back names stay closed, and system OK does not explain."""

import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import numpy
import pytest

from phos.atlas.consistency import RESULT_NAME, SHIFT_SECONDS
from phos.atlas.consistency_windows import windows_for_period
from phos.eval.build_declaration import (
    KELMARSH_DEVELOPMENT_FILES,
    KELMARSH_HELD_BACK_FILES,
    SCORECARD,
)
from phos.eval.kelmarsh_log import (
    OK_SERVICE,
    SAMPLE_SECONDS,
    SCORE_END,
    SCORE_START,
    SIGNAL_COLUMNS,
    TRAIN_START,
    ChecksumError,
    FileChecksum,
    HeldBackFileError,
    IncompleteFarmError,
    KelmarshReport,
    SchemaError,
    StatusSpan,
    TurbineSlice,
    build_slice,
    development_checksums,
    kelmarsh_scorecard,
    load_scada_zip,
    merged_explaining,
    parse_status_lines,
    parse_turbine_lines,
    render_kelmarsh_markdown,
    score_halves,
    service_explains,
    time_is_explained,
    verify_file,
    which_half,
)

LOG = Path(__file__).resolve().parents[2] / "eval_runs" / "log.jsonl"
REGISTRY = Path(__file__).resolve().parents[2] / "data" / "registry.json"


def test_ten_minute_windows_collapse_and_are_not_a_new_rule() -> None:
    """ADR 0112 at 600 seconds. Lag 1 is one kept row. The detrend window is six samples."""
    windows = windows_for_period(SAMPLE_SECONDS)
    assert SAMPLE_SECONDS == 600.0
    assert windows.lags == (0, 1)
    assert windows.fit_step == 1
    assert windows.detrend_window == 6
    assert windows.detrend_step == 1
    assert windows.feature_gap == 1
    assert windows.event_window == 1
    assert windows.event_span == 1
    assert windows.second_alert_min_separation == 1


def test_halves_follow_the_year_cut_and_leave_2023_out() -> None:
    assert which_half(TRAIN_START) == "train"
    assert which_half(datetime(2018, 12, 31, 23, 50, tzinfo=UTC)) == "train"
    assert which_half(SCORE_START) == "score"
    assert which_half(datetime(2022, 12, 31, 23, 50, tzinfo=UTC)) == "score"
    assert which_half(SCORE_END) == "outside"
    assert which_half(datetime(2015, 12, 31, 23, 50, tzinfo=UTC)) == "outside"


def test_only_system_ok_fails_to_explain() -> None:
    assert service_explains(OK_SERVICE) is False
    assert service_explains("System OK (32)") is False
    assert service_explains("Manual stop (service)  (9)") is True
    assert service_explains("External stop (low wind speed)  (5)") is True
    assert service_explains("") is True
    ok = StatusSpan("Kelmarsh 1", 0, 100, OK_SERVICE)
    job = StatusSpan("Kelmarsh 1", 0, 100, "Manual stop (service)  (9)")
    assert merged_explaining((ok, job), "Kelmarsh 1") == ((0, 100),)
    assert merged_explaining((ok,), "Kelmarsh 1") == ()
    assert time_is_explained(0, ((0, 100),)) is True
    assert time_is_explained(100, ((0, 100),)) is True
    assert time_is_explained(101, ((0, 100),)) is False


def test_a_missing_signal_is_dropped_and_a_foreign_period_is_refused() -> None:
    header = "# " + ",".join(("Date and time", *SIGNAL_COLUMNS))
    good = "2018-01-01 00:00:00,1,2,3,4,5"
    missing = "2018-01-01 00:10:00,1,NaN,3,4,5"
    later = "2019-01-01 00:00:00,1,2,3,4,5"
    outside = "2023-01-01 00:00:00,1,2,3,4,5"
    rows, dropped, _steps, _on_grid = parse_turbine_lines(
        ["# Turbine: Kelmarsh 1", header, good, missing, later, outside]
    )
    assert dropped == 1
    assert [item[2] for item in rows] == ["train", "score"]
    assert all(len(item[1]) == 5 for item in rows)
    fast = [header]
    stamp = datetime(2018, 1, 1, tzinfo=UTC).timestamp()
    for offset in range(12):
        text = datetime.fromtimestamp(stamp + offset, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        fast.append(f"{text},1,2,3,4,5")
    with pytest.raises(SchemaError):
        parse_turbine_lines(fast)


def test_status_schema_and_service_cell() -> None:
    lines = [
        "# Turbine: Kelmarsh 1",
        "Timestamp start,Timestamp end,Duration,Status,Code,Message,Comment,"
        "Service contract category,IEC category",
        "2019-06-01 00:00:00,2019-06-01 02:00:00,02:00:00,Stop,1,Manual,,"
        "Manual stop (service)  (9),Scheduled Maintenance",
        "2019-06-02 00:00:00,2019-06-01 00:00:00,0,Stop,1,Backwards,,Warnings (27),Forced outage",
    ]
    spans = parse_status_lines(lines, "Kelmarsh 1")
    assert len(spans) == 1
    assert spans[0].service_category == "Manual stop (service)  (9)"
    assert service_explains(spans[0].service_category) is True
    with pytest.raises(SchemaError):
        parse_status_lines(["Timestamp start,Timestamp end\n"], "Kelmarsh 1")


def test_duplicate_times_and_clock_gaps_are_counted() -> None:
    columns = [[1.0, 1.0, 1.0, 1.0] for _ in SIGNAL_COLUMNS]
    sliced = build_slice("Kelmarsh 1", [0, 0, 600, 1800], columns, dropped_missing=2)
    assert sliced.duplicate_times == 1
    assert sliced.clock_gaps == 1
    assert sliced.dropped_missing == 2
    assert list(sliced.time) == [0, 600, 1800]


def test_held_back_names_are_refused_before_the_path_is_opened(tmp_path: Path) -> None:
    for name in KELMARSH_HELD_BACK_FILES:
        path = tmp_path / name
        with pytest.raises(HeldBackFileError):
            load_scada_zip(path)
        assert not path.exists()


def test_a_held_back_member_inside_a_development_zip_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "Kelmarsh_SCADA_2016_3082.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("Kelmarsh_PMU_4459.zip", b"do not read")
    with pytest.raises(HeldBackFileError):
        load_scada_zip(path)


def test_a_2022_file_named_through_new_year_needs_the_round2_flag(tmp_path: Path) -> None:
    """The 2022 zip labels its span through 2023-01-01. That is not the held-back zip."""
    path = tmp_path / "Kelmarsh_SCADA_2022_4457.zip"
    member = "Turbine_Data_Kelmarsh_1_2022-01-01_-_2023-01-01_228.csv"
    with ZipFile(path, "w") as archive:
        archive.writestr(member, b"not,a,header\n")
    with pytest.raises(HeldBackFileError):
        load_scada_zip(path)
    with pytest.raises(SchemaError):
        load_scada_zip(path, allow_year_end_label=True)


def test_checksum_mismatch_raises_without_being_a_score(tmp_path: Path) -> None:
    path = tmp_path / "Kelmarsh_SCADA_2016_3082.zip"
    path.write_bytes(b"not a zip")
    checksum = FileChecksum(filename=path.name, md5="0" * 32, size_bytes=999)
    with pytest.raises(ChecksumError):
        verify_file(path, checksum)


def test_development_checksums_match_the_declaration_and_omit_held_back() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    found = development_checksums(registry)
    assert tuple(item.filename for item in found) == KELMARSH_DEVELOPMENT_FILES
    assert not any(item.filename in KELMARSH_HELD_BACK_FILES for item in found)
    broken = {
        "datasets": [
            {
                "name": "kelmarsh",
                "files": [
                    {
                        "filename": "Kelmarsh_SCADA_2023_5961.zip",
                        "md5": "ab",
                        "size_bytes": 1,
                    }
                ],
            }
        ]
    }
    with pytest.raises(HeldBackFileError):
        development_checksums(broken)


def test_a_development_zip_keeps_the_year_split_and_the_drop(tmp_path: Path) -> None:
    header = "# " + ",".join(("Date and time", *SIGNAL_COLUMNS))
    body = "\n".join(
        [
            "# Turbine: Kelmarsh 1",
            header,
            "2018-12-31 23:50:00,1,2,3,4,5",
            "2019-01-01 00:00:00,1,NaN,3,4,5",
            "2019-01-01 00:10:00,1,2,3,4,5",
        ]
    )
    status = "\n".join(
        [
            "# Turbine: Kelmarsh 1",
            "Timestamp start,Timestamp end,Duration,Status,Code,Message,Comment,"
            "Service contract category,IEC category",
            "2019-01-01 00:00:00,2019-01-01 01:00:00,01:00:00,Informational,32,OK,,"
            "System OK (32),Full Performance",
        ]
    )
    path = tmp_path / "Kelmarsh_SCADA_2018_3084.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("Turbine_Data_Kelmarsh_1_2018.csv", body)
        archive.writestr("Status_Kelmarsh_1_2018.csv", status)
    loaded = load_scada_zip(path)
    train_stamp = int(datetime(2018, 12, 31, 23, 50, tzinfo=UTC).timestamp())
    score_stamp = int(datetime(2019, 1, 1, 0, 10, tzinfo=UTC).timestamp())
    assert loaded.trains["Kelmarsh 1"][0] == [train_stamp]
    assert loaded.scores["Kelmarsh 1"][0] == [score_stamp]
    assert loaded.trains["Kelmarsh 1"][2] + loaded.scores["Kelmarsh 1"][2] == 1
    assert loaded.spans[0].service_category == OK_SERVICE
    assert service_explains(loaded.spans[0].service_category) is False


def test_system_ok_does_not_explain_a_budgeted_alert_and_a_job_does() -> None:
    """The frozen detector on a toy series. The log rule is what moves the explained count."""
    before = LOG.stat().st_size if LOG.is_file() else None
    train = _noisy_slice("Kelmarsh 1", datetime(2016, 1, 1, tzinfo=UTC), 400, None)
    score = _noisy_slice("Kelmarsh 1", datetime(2019, 6, 1, tzinfo=UTC), 200, (40, 80))
    start = int(score.time[0])
    end = int(score.time[-1])
    ok = StatusSpan("Kelmarsh 1", start, end, OK_SERVICE)
    job = StatusSpan("Kelmarsh 1", start, end, "Manual stop (service)  (9)")
    quiet = score_halves(
        {"Kelmarsh 1": train}, {"Kelmarsh 1": score}, (ok,), turbines=("Kelmarsh 1",)
    )
    explained = score_halves(
        {"Kelmarsh 1": train}, {"Kelmarsh 1": score}, (ok, job), turbines=("Kelmarsh 1",)
    )
    after = LOG.stat().st_size if LOG.is_file() else None
    assert after == before
    assert quiet.detector == RESULT_NAME == "atlas-v1-consistency"
    assert quiet.alerts > 0
    assert quiet.explained_alerts == 0
    assert quiet.explained_share == 0.0
    assert explained.alerts == quiet.alerts
    assert explained.explained_alerts == explained.alerts
    assert explained.explained_share == 1.0
    assert explained.false_alerts_per_shift == 0.0
    assert explained.shifts == pytest.approx(explained.scored_seconds / SHIFT_SECONDS)
    card = kelmarsh_scorecard(explained, runtime_seconds=0.0)
    assert tuple(card) == SCORECARD
    catches = card["catches_within_budget"]
    assert isinstance(catches, dict)
    assert catches["measured"] is False
    text = render_kelmarsh_markdown(explained)
    assert "not a detection claim" in text
    assert "Hypothesis confidence is not reported." in text


def test_a_missing_turbine_is_not_scored_as_the_farm() -> None:
    empty = TurbineSlice(
        "Kelmarsh 1",
        numpy.empty(0, dtype=numpy.int64),
        numpy.empty((0, 5), dtype=numpy.float64),
        0,
        0,
        0,
    )
    with pytest.raises(IncompleteFarmError):
        score_halves({}, {}, (), turbines=("Kelmarsh 1",))
    with pytest.raises(IncompleteFarmError):
        score_halves({"Kelmarsh 1": empty}, {"Kelmarsh 1": empty}, ())


def _noisy_slice(
    turbine: str,
    start: datetime,
    count: int,
    step: tuple[int, int] | None,
) -> TurbineSlice:
    """A smooth series, with an optional step on the first signal. Seeded, not fitted."""
    rng = numpy.random.default_rng(7)
    origin = int(start.timestamp())
    stamps = [origin + index * int(SAMPLE_SECONDS) for index in range(count)]
    columns: list[list[float]] = []
    base = rng.normal(0.0, 1.0, size=(count, len(SIGNAL_COLUMNS)))
    for column in range(len(SIGNAL_COLUMNS)):
        values = 20.0 + base[:, column]
        if step is not None and column == 0:
            values[step[0] : step[1]] += 500.0
        columns.append([float(item) for item in values])
    return build_slice(turbine, stamps, columns, dropped_missing=0)


def test_render_names_the_collapse() -> None:
    """A hand-built report, so the sentence does not depend on a second detector run."""
    report = KelmarshReport(
        measured=True,
        detector=RESULT_NAME,
        sample_seconds=600.0,
        windows_lags=(0, 1),
        detrend_window_samples=6,
        signals=SIGNAL_COLUMNS,
        ok_service=OK_SERVICE,
        turbines=(),
        alerts=0,
        explained_alerts=0,
        unexplained_alerts=0,
        explained_share=None,
        scored_seconds=0.0,
        shifts=0.0,
        false_alerts_per_shift=None,
        caveat="fixture",
        citation="fixture",
    )
    text = render_kelmarsh_markdown(report)
    assert "undefined, because there were no alerts" in text
    assert "(0, 1)" in text
