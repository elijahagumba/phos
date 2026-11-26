"""Measuring the L5X reader: what it matches, what it misses, and why neither is a score.

The fixtures are authored here, from the documented schema, for the same reason the reader's own
tests are: no real control program is in this repository, and a measurement built on a file whose
origin is unclear measures the file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.atlas.l5x import parse_export
from phos.atlas.l5x_agreement import Agreement, compare, hand_written_setpoints

REPO_ROOT = Path(__file__).resolve().parents[2]

_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<RSLogix5000Content SchemaRevision="1.0">\n'


def _export(tmp_path: Path, rungs: list[str]) -> Path:
    """Write a ladder export holding ``rungs`` and return its path."""
    body = "".join(
        f'<Rung Number="{i}" Type="N"><Text><![CDATA[{text}]]></Text></Rung>'
        for i, text in enumerate(rungs, start=1)
    )
    xml = (
        _HEADER
        + '  <Controller Name="c">\n'
        + '    <Routines><Routine Name="Main" Type="RLL"><RLLContent>\n'
        + body
        + "\n    </RLLContent></Routine></Routines>\n"
        + "  </Controller>\n</RSLogix5000Content>\n"
    )
    path = tmp_path / "e.L5X"
    path.write_text(xml, encoding="utf-8")
    return path


def test_the_hand_written_record_is_readable_and_has_setpoints() -> None:
    """A comparison against an empty record would look like perfect agreement."""
    setpoints = hand_written_setpoints(REPO_ROOT)
    assert setpoints, "the hand-written record should name at least one setpoint"
    assert all(entry.signal for entry in setpoints)


def test_a_matching_tag_is_counted_as_matched(tmp_path: Path) -> None:
    """The matched count must move, or it is not measuring anything."""
    written = hand_written_setpoints(REPO_ROOT)
    tag = written[0].signal
    path = _export(tmp_path, [f"GRT({tag},90.0)OTE(Alarm_HH)"])
    agreement = compare(parse_export(path), written)

    assert tag in agreement.matched
    assert tag not in agreement.missed


def test_a_tag_the_record_does_not_mention_is_counted_separately(tmp_path: Path) -> None:
    """A derived rule on an unknown tag is not a match and must not be folded into one."""
    written = hand_written_setpoints(REPO_ROOT)
    path = _export(tmp_path, ["GRT(Some_Tag_Nowhere,90.0)OTE(Alarm_HH)"])
    agreement = compare(parse_export(path), written)

    assert "Some_Tag_Nowhere" in agreement.derived_only
    assert "Some_Tag_Nowhere" not in agreement.matched


def test_a_written_setpoint_with_no_rule_is_counted_as_missed(tmp_path: Path) -> None:
    """The missed count is the one that says what the parser failed to find."""
    written = hand_written_setpoints(REPO_ROOT)
    path = _export(tmp_path, ["GRT(Some_Tag_Nowhere,90.0)OTE(Alarm_HH)"])
    agreement = compare(parse_export(path), written)

    assert set(agreement.missed) == {entry.signal for entry in written}
    assert len(agreement.matched) == 0


def test_the_summary_refuses_to_combine_the_three_counts_into_a_score() -> None:
    """A single number here would hide which half failed, so the summary must not offer one."""
    agreement = Agreement(
        matched=("a",), derived_only=("b",), missed=("c", "d"), hand_written_total=3
    )
    summary = agreement.summary()

    assert "1 of 3" in summary
    assert "2 were missed" in summary
    assert "1 derived rule(s)" in summary
    assert "not combined into a score" in summary


def test_the_summary_says_why_agreement_is_weak_evidence() -> None:
    """The by-construction caveat has to travel with the numbers, not live in a docstring."""
    agreement = Agreement(matched=(), derived_only=(), missed=("a",), hand_written_total=1)
    assert "shared vocabulary" in agreement.summary()


def test_an_empty_hand_written_record_says_so_rather_than_dividing_by_zero() -> None:
    """A record with no setpoints cannot support a comparison, and must not pretend to."""
    agreement = Agreement(matched=(), derived_only=(), missed=(), hand_written_total=0)
    assert "nothing can be compared" in agreement.summary()


def test_a_register_with_no_rules_misses_everything(tmp_path: Path) -> None:
    """An export this reader cannot use must report a total miss, not an empty comparison."""
    written = hand_written_setpoints(REPO_ROOT)
    path = _export(tmp_path, ["ADD(A,B,C)OTE(D)"])
    agreement = compare(parse_export(path), written)

    assert agreement.matched == ()
    assert len(agreement.missed) == len(written)


def test_the_measurement_does_not_require_a_real_export_to_be_present() -> None:
    """The suite must pass in an offline checkout with no third-party files.

    A test depending on a fetched sample would report a broken build for a network problem, so no
    sample is committed and none is read here. The measurement behind this reader was taken against
    three public sample projects, each fetched to a temporary directory and none redistributed.
    Their licences were established by fetching and reading the licence text rather than trusting a
    badge: `hutcheb/acd` (Apache-2.0, `resources/ACDTestsWithAOI.L5X`), `tnunnink/L5Sharp` (MIT,
    `Tests.Samples/Projects/Test.L5X`) and `JeremyMedders/LogixLibraries` (MIT,
    `src/Process/Dev_PackML_State_Program.L5X` and `src/Numeric/Numeric_Program.L5X`). All three
    permit use, modification and redistribution with attribution; nothing is redistributed here
    regardless. They are named inline because the lab's fuller record of the check is not published.
    """
    with pytest.raises(FileNotFoundError):
        hand_written_setpoints(Path("/nonexistent/root"))
