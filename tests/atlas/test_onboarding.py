"""Onboarding suggestions (ADR 0220): tokens, statistics, and a capture, never a declaration.

Hand fixtures lock the rules. The HAI 20.07 check uses column names from ``roles.toml`` and does
not pass the declared role into the suggester. Development names are not the C2 pass bar.
"""

from __future__ import annotations

import ast
import gzip
import tomllib
from pathlib import Path

import pytest

from phos.atlas.onboarding import (
    SUGGESTION_IS_NOT_A_DECLARATION,
    CaptureHit,
    TagKind,
    TagSample,
    format_brief,
    main,
    parse_capture,
    parse_historian,
    suggest,
)
from phos.atlas.signal_roles import SignalRole

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "phos" / "atlas" / "onboarding"
ROLES = ROOT / "data" / "hai-20.07" / "roles.toml"


def _stepped() -> tuple[float, ...]:
    return (1.5,) * 20 + (3.0,) * 20


def _varying() -> tuple[float, ...]:
    return tuple(index * 0.1 for index in range(40))


def test_flow_transmitter_token_is_a_flow_sensor() -> None:
    suggestion = suggest((TagSample(tag="P1_FT01"),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert suggestion.kind is TagKind.FLOW
    assert suggestion.evidence[0].token == "FT"
    assert "flow transmitter" in suggestion.evidence_text


def test_valve_command_suffix_is_a_valve_actuator() -> None:
    suggestion = suggest((TagSample(tag="P1_FCV01D"),))[0]
    assert suggestion.role is SignalRole.ACTUATOR
    assert suggestion.kind is TagKind.VALVE
    assert "token FCV" in suggestion.evidence_text
    assert "suffix D (command)" in suggestion.evidence_text


def test_valve_position_suffix_stays_an_actuator() -> None:
    suggestion = suggest((TagSample(tag="P1_FCV01Z"),))[0]
    assert suggestion.role is SignalRole.ACTUATOR
    assert suggestion.kind is TagKind.VALVE
    assert "suffix Z (reported position)" in suggestion.evidence_text


def test_transmitter_suffix_z_stays_a_sensor() -> None:
    suggestion = suggest((TagSample(tag="P1_FT01Z"),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert suggestion.kind is TagKind.FLOW
    assert "role stays sensor" in suggestion.evidence_text


def test_level_setpoint_words() -> None:
    suggestion = suggest((TagSample(tag="clearwell_level_setpoint_m"),))[0]
    assert suggestion.role is SignalRole.SETPOINT
    assert suggestion.kind is TagKind.LEVEL
    assert any(item.token == "level" for item in suggestion.evidence)
    assert any(item.token == "setpoint" for item in suggestion.evidence)


def test_pump_command_words() -> None:
    suggestion = suggest((TagSample(tag="intake_pump_command"),))[0]
    assert suggestion.role is SignalRole.ACTUATOR
    assert suggestion.kind is TagKind.PUMP
    assert "token command (actuator)" in suggestion.evidence_text


def test_inflow_word_is_a_flow_sensor() -> None:
    suggestion = suggest((TagSample(tag="raw_inflow_m3ph"),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert suggestion.kind is TagKind.FLOW
    assert suggestion.evidence[0].token == "inflow"


def test_temperature_transmitter_has_no_kind() -> None:
    suggestion = suggest((TagSample(tag="P1_TIT01"),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert suggestion.kind is None
    assert "not one of flow, pressure, level, pump, valve" in suggestion.evidence_text


def test_opaque_name_without_values_is_not_guessed() -> None:
    suggestion = suggest((TagSample(tag="P1_B2004"),))[0]
    assert suggestion.role is None
    assert suggestion.kind is None
    assert suggestion.evidence[0].token == "none"


def test_opaque_stepped_sample_is_a_setpoint_with_no_kind() -> None:
    suggestion = suggest((TagSample(tag="B2004", values=_stepped()),))[0]
    assert suggestion.role is SignalRole.SETPOINT
    assert suggestion.kind is None
    statistic = next(item for item in suggestion.evidence if item.statistic is not None)
    assert statistic.statistic is not None
    assert "2 distinct values in 40 samples" in statistic.statistic
    assert "sits, then steps" in statistic.text


def test_opaque_varying_sample_is_a_sensor() -> None:
    suggestion = suggest((TagSample(tag="B4005", values=_varying()),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert suggestion.kind is None
    assert "keeps moving" in suggestion.evidence_text


def test_constant_sample_does_not_pick_a_role() -> None:
    suggestion = suggest((TagSample(tag="B4002", values=(4.0,) * 40),))[0]
    assert suggestion.role is None
    assert "stuck sensor" in suggestion.evidence_text


def test_short_sample_is_not_a_role() -> None:
    suggestion = suggest((TagSample(tag="B2016", values=(1.0,) * 5),))[0]
    assert suggestion.role is None
    assert "below 20" in suggestion.evidence_text


def test_values_in_a_span_do_not_invent_a_kind() -> None:
    values = tuple(float(index) for index in range(40))
    suggestion = suggest((TagSample(tag="X100", values=values),))[0]
    assert suggestion.kind is None
    assert suggestion.role is SignalRole.SENSOR


def test_token_wins_when_the_statistic_disagrees() -> None:
    suggestion = suggest((TagSample(tag="P1_FT01", values=_stepped()),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert suggestion.kind is TagKind.FLOW
    assert "disagrees with the token" in suggestion.evidence_text
    assert "keeps the token" in suggestion.evidence_text


def test_capture_write_does_not_override_a_sensor_token() -> None:
    suggestion = suggest(
        (TagSample(tag="P1_FT01"),),
        (CaptureHit(tag="P1_FT01", access="write", count=3),),
    )[0]
    assert suggestion.role is SignalRole.SENSOR
    capture = next(item for item in suggestion.evidence if item.capture is not None)
    assert capture.capture == "writes=3"
    assert "contradicts a sensor token" in capture.text


def test_writes_alone_do_not_choose_actuator_or_setpoint() -> None:
    suggestion = suggest((), (CaptureHit(tag="B3004", access="write", count=2),))[0]
    assert suggestion.tag == "B3004"
    assert suggestion.role is None
    assert "not which one" in suggestion.evidence_text


def test_reads_alone_are_not_a_role() -> None:
    suggestion = suggest((), (CaptureHit(tag="B3005", access="read", count=9),))[0]
    assert suggestion.role is None
    assert "reads alone are not a role" in suggestion.evidence_text


def test_capture_only_tag_is_appended_after_historian_tags() -> None:
    suggestions = suggest(
        (TagSample(tag="P1_LIT01"),),
        (CaptureHit(tag="P3_LT01", access="read", count=1),),
    )
    assert [item.tag for item in suggestions] == ["P1_LIT01", "P3_LT01"]
    assert suggestions[1].role is SignalRole.SENSOR
    assert suggestions[1].kind is TagKind.LEVEL


def test_repeated_historian_tag_keeps_the_first_sample() -> None:
    suggestions = suggest(
        (
            TagSample(tag="B2004", values=_stepped()),
            TagSample(tag="B2004", values=_varying()),
        )
    )
    assert len(suggestions) == 1
    assert suggestions[0].role is SignalRole.SETPOINT


def test_wide_historian_skips_time_and_label_columns() -> None:
    rows = [
        ["time", "FT-101", "attack"],
        ["0", "1.25", "0"],
        ["1", "1.50", "0"],
    ]
    samples = parse_historian(rows, sample_rows=10)
    assert [sample.tag for sample in samples] == ["FT-101"]
    assert samples[0].values == (1.25, 1.5)


def test_long_historian_caps_values_per_tag() -> None:
    rows = [["tag", "value"], *[["FT-101", "1.0"] for _ in range(5)], ["LT-1", "2.5"]]
    samples = parse_historian(rows, sample_rows=2)
    by_tag = {sample.tag: sample.values for sample in samples}
    assert by_tag == {"FT-101": (1.0, 1.0), "LT-1": (2.5,)}


def test_capture_table_requires_a_tag_column() -> None:
    with pytest.raises(ValueError, match="tag column"):
        parse_capture([["name", "access"], ["FT-101", "read"]])


def test_brief_is_a_list_an_engineer_can_edit() -> None:
    brief = format_brief(suggest((TagSample(tag="P1_PIT01"),)))
    assert brief.startswith("# Suggestions are not declarations")
    assert "\nP1_PIT01\tsensor\tpressure\t" in brief
    assert "token PIT" in brief
    assert SUGGESTION_IS_NOT_A_DECLARATION


def test_main_prints_the_brief(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    historian = tmp_path / "historian.csv"
    historian.write_text(
        "time,FT_101,clearwell_level_setpoint_m\n0,1.0,2.0\n",
        encoding="utf-8",
    )
    capture = tmp_path / "capture.csv"
    capture.write_text("tag,access,count\nFT_101,read,4\n", encoding="utf-8")
    out = tmp_path / "brief.tsv"
    code = main(["--historian", str(historian), "--capture", str(capture), "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "FT_101\tsensor\tflow\t" in printed
    assert "clearwell_level_setpoint_m\tsetpoint\tlevel\t" in printed
    assert out.read_text(encoding="utf-8") == printed


def test_main_missing_file_exits_nonzero(tmp_path: Path) -> None:
    code = main(
        ["--historian", str(tmp_path / "missing.csv"), "--capture", str(tmp_path / "also.csv")]
    )
    assert code == 2


def test_main_runs_on_a_historian_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """ADR 0341: a plant engineer has a historian export long before a capture."""
    historian = tmp_path / "historian.csv"
    historian.write_text("time,FT_101\n0,1.0\n", encoding="utf-8")
    assert main(["--historian", str(historian)]) == 0
    assert "FT_101\tsensor\tflow\t" in capsys.readouterr().out


def test_a_historian_alone_matches_an_empty_capture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No capture removes capture evidence and nothing else (ADR 0341)."""
    historian = tmp_path / "historian.csv"
    historian.write_text("time,FT_101,P1_B2004\n0,1.0,7.0\n", encoding="utf-8")
    empty = tmp_path / "capture.csv"
    empty.write_text("tag\n", encoding="utf-8")

    assert main(["--historian", str(historian)]) == 0
    alone = capsys.readouterr().out
    assert main(["--historian", str(historian), "--capture", str(empty)]) == 0
    assert capsys.readouterr().out == alone


def test_a_capture_that_cannot_be_read_is_still_refused(tmp_path: Path) -> None:
    """Optional is not ignored: a named capture that is absent is an error (ADR 0341)."""
    historian = tmp_path / "historian.csv"
    historian.write_text("time,FT_101\n0,1.0\n", encoding="utf-8")
    assert main(["--historian", str(historian), "--capture", str(tmp_path / "gone.csv")]) == 2


def test_a_historian_is_still_required() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_gzip_historian(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "tags.csv.gz"
    capture = tmp_path / "capture.csv"
    capture.write_text("tag\n", encoding="utf-8")
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("time,P3_LCP01D\n0,10\n")
    code = main(["--historian", str(path), "--capture", str(capture)])
    assert code == 0
    assert "P3_LCP01D\tactuator\tpump\t" in capsys.readouterr().out


def test_suggester_does_not_import_a_network_or_a_role_loader() -> None:
    names: set[str] = set()
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "roles.toml" not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    names.add(node.module.split(".")[0])
                names.update(alias.name for alias in node.names)
    assert names.isdisjoint(
        {"socket", "urllib", "requests", "httpx", "http", "subprocess", "load_roles"}
    )


def test_empty_tables_and_a_bad_sample_size() -> None:
    assert parse_historian([]) == ()
    assert parse_capture([]) == ()
    with pytest.raises(ValueError, match="sample_rows"):
        parse_historian([["FT-101"], ["1"]], sample_rows=0)


def test_capture_count_must_be_a_non_negative_integer() -> None:
    with pytest.raises(ValueError, match="not an integer"):
        parse_capture([["tag", "count"], ["FT-101", "many"]])
    with pytest.raises(ValueError, match=">= 0"):
        parse_capture([["tag", "count"], ["FT-101", "-1"]])


def test_unknown_capture_access_is_not_a_role() -> None:
    suggestion = suggest((), (CaptureHit(tag="B9", access="unknown", count=4),))[0]
    assert suggestion.role is None
    assert "no read or write access" in suggestion.evidence_text


def test_statistic_that_agrees_with_the_token_is_kept() -> None:
    suggestion = suggest((TagSample(tag="P1_FT01", values=_varying()),))[0]
    assert suggestion.role is SignalRole.SENSOR
    assert "keeps moving" in suggestion.evidence_text
    assert "disagrees" not in suggestion.evidence_text


def test_in_between_sample_is_not_used_as_a_role() -> None:
    values = (1.0,) * 10 + (2.0,) * 10
    suggestion = suggest((TagSample(tag="B9", values=values),))[0]
    assert suggestion.role is None
    assert "not used as a role" in suggestion.evidence_text


def test_hai_20_07_column_names_follow_the_token_rules() -> None:
    raw = tomllib.loads(ROLES.read_text(encoding="utf-8"))
    signals = [str(point["signal"]) for point in raw["points"]]
    suggestions = suggest(tuple(TagSample(tag=signal) for signal in signals))
    by_tag = {item.tag: item for item in suggestions}
    assert list(by_tag) == signals
    expected: dict[str, tuple[SignalRole | None, TagKind | None]] = {
        "P1_FT01": (SignalRole.SENSOR, TagKind.FLOW),
        "P1_FT01Z": (SignalRole.SENSOR, TagKind.FLOW),
        "P1_PIT01": (SignalRole.SENSOR, TagKind.PRESSURE),
        "P1_LIT01": (SignalRole.SENSOR, TagKind.LEVEL),
        "P1_FCV01D": (SignalRole.ACTUATOR, TagKind.VALVE),
        "P1_FCV01Z": (SignalRole.ACTUATOR, TagKind.VALVE),
        "P1_LCV01D": (SignalRole.ACTUATOR, TagKind.VALVE),
        "P1_PCV01D": (SignalRole.ACTUATOR, TagKind.VALVE),
        "P3_LCP01D": (SignalRole.ACTUATOR, TagKind.PUMP),
        "P3_LT01": (SignalRole.SENSOR, TagKind.LEVEL),
        "P1_TIT01": (SignalRole.SENSOR, None),
        "P2_SIT01": (SignalRole.SENSOR, None),
        "P4_ST_PT01": (SignalRole.SENSOR, TagKind.PRESSURE),
        "P4_ST_TT01": (SignalRole.SENSOR, None),
        "P1_B2004": (None, None),
    }
    for tag, (role, kind) in expected.items():
        assert by_tag[tag].role is role
        assert by_tag[tag].kind is kind
        assert by_tag[tag].evidence
