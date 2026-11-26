"""The L5X reader, tested only on exports authored here from the documented schema.

Every fixture in this file is written by hand in `_export`, from the shape Rockwell documents: a
`RSLogix5000Content` root, a `Controller`, `Programs`, `Routine` elements carrying a `Name`, and
`Rung` elements each holding a `Text` child with the ladder text. No real project file is used,
because none is in this repository and because a test built on a file whose origin is unclear is
not a test of the parser, it is a test of that file.

The point of each test is stated as what breaks if it fails, not as what the code does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.atlas.l5x import (
    DraftRule,
    DraftRuleKind,
    L5XError,
    RuleRegister,
    parse_export,
)

#: The schema header a Logix export carries. Written once so every fixture agrees.
_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<RSLogix5000Content SchemaRevision="1.0">\n'


def _export(tmp_path: Path, rungs: list[str], *, routine: str = "MainRoutine") -> Path:
    """Write an export holding ``rungs`` in one routine and return its path.

    Args:
        tmp_path: Where to write.
        rungs: The ladder text of each rung, in order.
        routine: The routine's name.

    Returns:
        The path.
    """
    body = "".join(
        f'<Rung Number="{i}" Type="N"><Text><![CDATA[{text}]]></Text></Rung>'
        for i, text in enumerate(rungs, start=1)
    )
    xml = (
        _HEADER
        + '  <Controller Name="TestController">\n'
        + "    <Programs>\n"
        + '      <Program Name="MainProgram">\n'
        + "        <Routines>\n"
        + f'          <Routine Name="{routine}" Type="RLL">\n'
        + "            <RLLContent>\n"
        + body
        + "\n            </RLLContent>\n"
        + "          </Routine>\n"
        + "        </Routines>\n"
        + "      </Program>\n"
        + "    </Programs>\n"
        + "  </Controller>\n"
        + "</RSLogix5000Content>\n"
    )
    path = tmp_path / "export.L5X"
    path.write_text(xml, encoding="utf-8")
    return path


def test_a_comparison_that_drives_an_output_becomes_one_interlock(tmp_path: Path) -> None:
    """An interlock is the most common rule in a controller.

    Missing it would lose most of the code, so this is the shape that matters most.
    """
    path = _export(tmp_path, ["XIC(Level_OK)GRT(Tank_Level,85.0)OTE(Pump_Run)"])
    register = parse_export(path)

    assert len(register.rules) == 1
    rule = register.rules[0]
    assert rule.kind != DraftRuleKind.ALARM_THRESHOLD
    assert rule.tag == "Tank_Level"
    assert rule.threshold == 85.0
    assert rule.routine == "MainRoutine"
    assert "Pump_Run" in rule.statement


def test_every_derived_rule_is_a_draft_and_cannot_be_anything_else(tmp_path: Path) -> None:
    """The whole promise of the stage is that nothing activates itself.

    If this fails, a derived rule could be constructed as a law in force, and the sign-off
    requirement would be a comment rather than a property.
    """
    path = _export(tmp_path, ["GRT(Level,90.0)OTE(Alarm_HH)"])
    rule = parse_export(path).rules[0]

    assert rule.standing == "draft"
    assert rule.signed_off_by == ""
    with pytest.raises(ValueError, match="cannot be constructed as anything else"):
        DraftRule(
            name="x",
            statement="y",
            kind=DraftRuleKind.INTERLOCK,
            tag="t",
            threshold=1.0,
            unit=None,
            routine="r",
            file="f",
            line=1,
            standing="held",
        )


def test_a_sign_off_with_no_name_is_refused() -> None:
    """A blank sign-off is how a signature becomes a formality."""
    with pytest.raises(ValueError, match="must name the engineer"):
        DraftRule(
            name="x",
            statement="y",
            kind=DraftRuleKind.INTERLOCK,
            tag="t",
            threshold=1.0,
            unit=None,
            routine="r",
            file="f",
            line=1,
            signed_off_by="   ",
        )


def test_an_alarm_tag_makes_it_a_threshold_and_says_the_classification_was_by_name(
    tmp_path: Path,
) -> None:
    """The reader classifies by tag name, which is a guess, so the rule must say so."""
    path = _export(tmp_path, ["GRT(Tank_Level,92.0)OTE(Tank_High_Alarm)"])
    rule = parse_export(path).rules[0]

    assert rule.kind == DraftRuleKind.ALARM_THRESHOLD
    assert "by the tag's own name" in rule.statement


def test_a_timer_preset_is_read_as_a_number(tmp_path: Path) -> None:
    """A pump start delay is a rule an operator relies on, and its preset is a number."""
    # Logix writes TON(Timer,Preset,Accum), where the preset is a literal in milliseconds.
    path = _export(tmp_path, ["XIC(Pump_Request)TON(Pump_Delay,10000,0)OTE(Pump_Run)"])
    register = parse_export(path)
    timers = register.of_kind(DraftRuleKind.TIMER_PRESET)

    assert len(timers) == 1
    assert timers[0].threshold == 10000.0
    assert timers[0].tag == "Pump_Delay"
    assert "preset of 10000" in timers[0].statement


def test_a_timer_preset_that_is_another_tag_is_listed_not_guessed(tmp_path: Path) -> None:
    """A preset computed at run time is not a number the code states, so it is not a rule."""
    path = _export(tmp_path, ["TON(Timer_A,Preset_Tag,0)OTE(Out)"])
    register = parse_export(path)

    assert register.rules == ()
    assert len(register.unreadable) == 1
    assert "a tag rather than a number" in register.unreadable[0].reason


def test_the_number_may_come_first_and_the_rule_says_the_reading_reversed(
    tmp_path: Path,
) -> None:
    """Logix writes comparisons either way round, and a silent reversal is a wrong rule."""
    path = _export(tmp_path, ["LES(50.0,Tank_Level)OTE(Pump_Run)"])
    rule = parse_export(path).rules[0]

    assert rule.threshold == 50.0
    assert rule.tag == "Tank_Level"
    assert "number is written first" in rule.statement


def test_an_instruction_the_reader_does_not_model_is_listed_with_its_name(
    tmp_path: Path,
) -> None:
    """A guessed translation of an unknown instruction is the failure mode being prevented."""
    path = _export(tmp_path, ["ADD(Level,Offset,Level)GRT(Level,90.0)OTE(Alarm)"])
    register = parse_export(path)

    assert register.rules == ()
    assert len(register.unreadable) == 1
    assert "ADD" in register.unreadable[0].reason
    assert "rather than guessed" in register.unreadable[0].reason


def test_two_comparisons_on_one_rung_are_listed_not_conjoined(tmp_path: Path) -> None:
    """Translating a conjunction badly would turn two conditions into one wrong rule."""
    path = _export(tmp_path, ["GRT(A,1.0)LES(B,2.0)OTE(Out)"])
    register = parse_export(path)

    assert register.rules == ()
    assert "more than one comparison" in register.unreadable[0].reason


def test_an_indirect_reference_is_listed(tmp_path: Path) -> None:
    """``Tag[Index]`` names a different tag at run time, so nothing static can be stated."""
    path = _export(tmp_path, ["GRT(Tank_Level[Index],90.0)OTE(Alarm)"])
    register = parse_export(path)

    assert register.rules == ()
    assert "through an index" in register.unreadable[0].reason


def test_a_comparison_that_writes_nothing_is_listed(tmp_path: Path) -> None:
    """A comparison with no output guards nothing this reader can name."""
    path = _export(tmp_path, ["XIC(A)GRT(B,5.0)"])
    register = parse_export(path)

    assert register.rules == ()
    assert "writes no output" in register.unreadable[0].reason


def test_two_number_operands_are_listed(tmp_path: Path) -> None:
    """A comparison between two constants constrains no tag."""
    path = _export(tmp_path, ["EQU(1,1)OTE(Always_On)"])
    register = parse_export(path)

    assert register.rules == ()
    assert "no tag is constrained" in register.unreadable[0].reason


def test_a_rung_with_no_number_and_no_timer_is_listed(tmp_path: Path) -> None:
    """Contacts alone state no rule with a number, and the reader says so rather than inventing."""
    path = _export(tmp_path, ["XIC(Start)OTE(Motor)"])
    register = parse_export(path)

    assert register.rules == ()
    assert "no comparison and no timer" in register.unreadable[0].reason


def test_every_rule_carries_the_file_and_line_it_came_from(tmp_path: Path) -> None:
    """A rule a reviewer cannot locate is a rule that cannot be signed off."""
    path = _export(tmp_path, ["GRT(Level,90.0)OTE(Alarm_HH)"])
    rule = parse_export(path).rules[0]

    assert rule.file == "export.L5X"
    assert rule.line > 0
    text = path.read_text(encoding="utf-8").splitlines()
    assert "GRT(Level,90.0)" in text[rule.line - 1]


def test_the_summary_accounts_for_both_counts_and_says_nothing_is_in_force(
    tmp_path: Path,
) -> None:
    """A register that reports only its rules hides what it dropped."""
    path = _export(tmp_path, ["GRT(Level,90.0)OTE(Alarm_HH)", "ADD(A,B,C)OTE(Out)"])
    summary = parse_export(path).summary()

    assert "1 draft rule(s)" in summary
    assert "1 ladder rung(s)" in summary
    assert "Nothing here is in force" in summary


def test_a_file_that_is_not_xml_is_refused(tmp_path: Path) -> None:
    """A CSV or a PDF renamed .L5X must fail loudly, not parse as an empty register."""
    path = tmp_path / "not.L5X"
    path.write_text("this is not xml at all", encoding="utf-8")

    with pytest.raises(L5XError, match="is not XML that parses"):
        parse_export(path)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is an error, not an empty register."""
    with pytest.raises(L5XError, match="cannot be read"):
        parse_export(tmp_path / "absent.L5X")


def test_an_export_with_no_rungs_is_an_empty_register_not_an_error(tmp_path: Path) -> None:
    """A project of only tag declarations is a legitimate export with nothing to derive."""
    path = tmp_path / "empty.L5X"
    path.write_text(_HEADER + '  <Controller Name="c"/>\n</RSLogix5000Content>\n', encoding="utf-8")
    register = parse_export(path)

    assert register == RuleRegister(rules=(), unreadable=(), source=str(path))
    assert "no rungs" in register.summary()


def test_the_reader_is_deterministic(tmp_path: Path) -> None:
    """Two reads of one file give the same register, so a register can be compared across runs."""
    path = _export(
        tmp_path,
        ["GRT(Level,90.0)OTE(Alarm_HH)", "XIC(A)TON(T,5000,0)OTE(B)", "ADD(A,B,C)OTE(D)"],
    )
    assert parse_export(path) == parse_export(path)


def test_the_reader_does_not_touch_the_declared_laws() -> None:
    """The stage's hard rule: no change to any existing law or detector.

    This asserts the module imports nothing from the declared-law module, so it cannot add, remove
    or edit a law. A derived rule has to be walked to the register by a person, not by an import.
    The check is on imports rather than on the text, because the docstring legitimately names the
    module it refuses to touch.
    """
    source = (Path(__file__).resolve().parents[2] / "src" / "phos" / "atlas" / "l5x.py").read_text(
        encoding="utf-8"
    )
    used_imports = [
        line for line in source.splitlines() if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(used_imports)
    assert "declared_law" not in joined, "the L5X reader must not import the declared laws"
    assert "LawRegister" not in source.replace("`LawRegister`", "")
    assert "DeclaredLaw(" not in source
