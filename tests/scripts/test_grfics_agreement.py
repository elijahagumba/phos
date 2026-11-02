"""The GRFICS agreement diagnosis judges the three declared bars and no more (ADR 0407).

These tests pin the judgement, not the numbers: a fabricated pair exercises each bar, so the pass
and fail paths are both covered without depending on the captured data. The captured pair is
analysed by running the script, and its verdict is recorded in ADR 0408.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "grfics" / "agreement.py"
_spec = importlib.util.spec_from_file_location("grfics_agreement", _SCRIPT)
assert _spec is not None and _spec.loader is not None
agreement = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = agreement
_spec.loader.exec_module(agreement)


def obs(tag: str, distinct: int, changes: int, register: int = 100) -> agreement.TagObservation:
    return agreement.TagObservation(
        tag=tag, register=register, samples=100, register_distinct=distinct, hmi_changes=changes
    )


def test_a_tag_is_live_when_its_register_moved() -> None:
    assert obs("X", distinct=2, changes=0).live_on_ics is True


def test_a_tag_is_not_live_when_its_register_never_moved() -> None:
    assert obs("X", distinct=1, changes=0).live_on_ics is False


def test_a_single_change_counts_as_tracking() -> None:
    assert obs("X", distinct=2, changes=1).hmi_tracked is True


def test_zero_changes_is_not_tracking() -> None:
    assert obs("X", distinct=2, changes=0).hmi_tracked is False


def test_the_tell_is_kept_when_physical_tracks_and_cyber_freezes() -> None:
    # Level is live only in the cyber run: the physical fault froze its register at the source, so
    # it carries no physical evidence and is excluded from bar 1 (ADR 0407).
    kept, failures = agreement.judge(
        [obs("Level", distinct=1, changes=0), obs("Pressure", distinct=900, changes=400)],
        [obs("Level", distinct=900, changes=0), obs("Pressure", distinct=900, changes=0)],
    )
    assert kept is True
    assert failures == []


def test_a_frozen_hmi_in_the_physical_run_fails_bar_one() -> None:
    kept, failures = agreement.judge(
        [obs("Pressure", distinct=900, changes=0)],
        [obs("Pressure", distinct=900, changes=0)],
    )
    assert kept is False
    assert any("bar 1" in f for f in failures)


def test_a_tracking_hmi_in_the_cyber_run_fails_bar_two() -> None:
    kept, failures = agreement.judge(
        [obs("Pressure", distinct=900, changes=400)],
        [obs("Pressure", distinct=900, changes=400)],
    )
    assert kept is False
    assert any("bar 2" in f for f in failures)


def test_bar_three_is_the_explicit_no_tag_satisfies_both_check() -> None:
    # Bars 1 and 2 already catch any single tag that is wrong in one run. Bar 3 is the conjunction
    # stated outright, so it is tested against the sets directly rather than through a pair that
    # would trip bar 1 first.
    physical = [
        obs("Pressure", distinct=900, changes=400),
        obs("ProductFlow", distinct=900, changes=400),
    ]
    cyber = [
        obs("Pressure", distinct=900, changes=0),
        obs("ProductFlow", distinct=900, changes=0),
    ]
    _, failures = agreement.judge(physical, cyber)
    assert failures == []
    both = {o.tag for o in physical if o.live_on_ics and o.hmi_tracked} & {
        o.tag for o in cyber if o.live_on_ics and o.hmi_tracked
    }
    assert both == set()


def test_a_tag_tracking_in_both_runs_is_named_by_bar_one_and_bar_two() -> None:
    kept, failures = agreement.judge(
        [obs("Pressure", distinct=900, changes=400), obs("BComp", distinct=900, changes=0)],
        [obs("Pressure", distinct=900, changes=0), obs("BComp", distinct=900, changes=400)],
    )
    assert kept is False
    assert any("bar 1" in f and "BComp" in f for f in failures)
    assert any("bar 2" in f and "BComp" in f for f in failures)


def test_a_tag_constant_on_the_ics_side_is_excluded_from_the_bars() -> None:
    # AValve never moves, so it is neither agreement nor disagreement and must not fail anything.
    kept, failures = agreement.judge(
        [obs("AValve", distinct=1, changes=0), obs("Pressure", distinct=900, changes=400)],
        [obs("AValve", distinct=1, changes=0), obs("Pressure", distinct=900, changes=0)],
    )
    assert kept is True
    assert failures == []


def test_no_live_tag_in_the_physical_run_is_a_refusal_not_a_pass() -> None:
    kept, failures = agreement.judge(
        [obs("AValve", distinct=1, changes=0)],
        [obs("Pressure", distinct=900, changes=0)],
    )
    assert kept is False
    assert any("nothing to judge" in f for f in failures)


def test_no_live_tag_in_the_cyber_run_is_a_refusal_not_a_pass() -> None:
    kept, failures = agreement.judge(
        [obs("Pressure", distinct=900, changes=400)],
        [obs("AValve", distinct=1, changes=0)],
    )
    assert kept is False
    assert any("nothing to judge" in f for f in failures)


def test_the_report_states_it_is_not_a_detection_result() -> None:
    text = agreement.render([obs("Pressure", 900, 400)], [obs("Pressure", 900, 0)], True, [])
    assert "not a detection result" in text
    assert "recall" in text


def test_the_report_names_the_corpus_and_disclaims_the_declared_one() -> None:
    text = agreement.render([obs("Pressure", 900, 400)], [obs("Pressure", 900, 0)], True, [])
    assert "grfics-v3-bridge" in text
    assert "Not `grfics-v3`" in text


def test_a_kept_report_carries_every_observation() -> None:
    physical = [obs("Level", 500, 0, 109), obs("Pressure", 900, 400, 108)]
    cyber = [obs("Level", 900, 0, 109), obs("Pressure", 900, 0, 108)]
    text = agreement.render(physical, cyber, True, [])
    for tag in ("Level", "Pressure"):
        assert f"`{tag}`" in text


def test_a_refused_report_lists_every_failure() -> None:
    text = agreement.render(
        [obs("Pressure", 900, 0)],
        [obs("Pressure", 900, 400)],
        False,
        ["bar 1: broken", "bar 2: broken"],
    )
    assert "**Refused.**" in text
    assert "bar 1: broken" in text
    assert "bar 2: broken" in text


def test_the_report_says_what_it_does_not_say() -> None:
    text = agreement.render([obs("Pressure", 900, 400)], [obs("Pressure", 900, 0)], True, [])
    assert "does not say Atlas detects anything" in text
    assert "does not describe a real plant" in text
    assert "cross-zone" in text


def test_the_transition_window_matches_the_one_the_capture_declared() -> None:
    # ADR 0406 declared it in capture.py before the recapture; this script must not drift from it.
    capture_spec = importlib.util.spec_from_file_location(
        "grfics_capture_for_agreement", _SCRIPT.parent / "capture.py"
    )
    assert capture_spec is not None and capture_spec.loader is not None
    capture = importlib.util.module_from_spec(capture_spec)
    sys.modules[capture_spec.name] = capture
    capture_spec.loader.exec_module(capture)
    assert agreement.TRANSITION_SAMPLES == capture.TRANSITION_SAMPLES


def test_the_tag_map_matches_the_one_the_capture_declared() -> None:
    capture_spec = importlib.util.spec_from_file_location(
        "grfics_capture_tags", _SCRIPT.parent / "capture.py"
    )
    assert capture_spec is not None and capture_spec.loader is not None
    capture = importlib.util.module_from_spec(capture_spec)
    sys.modules[capture_spec.name] = capture
    capture_spec.loader.exec_module(capture)
    assert agreement.TAGS == capture.HMI_TAGS


def test_an_absent_run_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="absent"):
        agreement.read_rows(tmp_path, "hmi_values.csv")


def test_misaligned_streams_are_refused(tmp_path: Path) -> None:
    (tmp_path / "hmi_values.csv").write_text("t,phase\n1,event\n2,event\n", encoding="utf-8")
    (tmp_path / "modbus.csv").write_text("t,phase\n1,event\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="share one clock"):
        agreement.analyse(tmp_path)
