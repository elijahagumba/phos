"""The terminal text says only what the run produced, and says a miss is a miss."""

import re
from dataclasses import replace

from phos.demo import DemoResult, Scenario, Stage, Style, render_result, render_stage
from phos.demo.render import WIDTH
from phos.eval.decision_fixtures import atlas_cases
from phos.reasoning.analyst import assess_narrative

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _result(**overrides: object) -> DemoResult:
    case = next(c for c in atlas_cases() if c.case_id == "known-station-write")
    result = DemoResult(
        scenario=Scenario.UNAUTHORISED,
        seed=11,
        plant_label="Water treatment",
        stages=(Stage(name="Learning", detail="86,422 control messages", seconds=9.4),),
        subject="SCADA server → Clearwell and distribution PLC",
        brief=assess_narrative(case.narrative, case.store, case.library),
        findings=("The SCADA server sent write single register (function 6) to the PLC.",),
        other_incidents=0,
        truth=("The SCADA server wrote the clearwell level setpoint. Unauthorised.",),
        writes=1,
        unauthorised=True,
        concerns_truth=True,
    )
    return replace(result, **overrides)  # type: ignore[arg-type]


def _plain(result: DemoResult) -> str:
    return render_result(result, Style(colour=False))


class TestLayout:
    def test_no_colour_means_no_escape_codes(self) -> None:
        assert "\x1b[" not in _plain(_result())

    def test_colour_only_styles_and_never_changes_the_words(self) -> None:
        coloured = render_result(_result(), Style(colour=True))
        assert "\x1b[" in coloured
        assert _ANSI.sub("", coloured) == _plain(_result())

    def test_every_line_fits_the_terminal_width(self) -> None:
        stage = render_stage(_result().stages[0], Style(colour=False))
        for line in [*_plain(_result()).splitlines(), stage]:
            assert len(line) <= WIDTH, line

    def test_the_settling_fact_is_atlas_s_own(self) -> None:
        text = _plain(_result())
        assert "WHAT WOULD SETTLE IT" in text
        assert "A write from a device that has never commanded this target." in text

    def test_the_residual_closes_the_competing_set(self) -> None:
        lines = _plain(_result()).splitlines()
        start = lines.index("  STILL ON THE TABLE")
        rows = [line for line in lines[start + 1 :] if line.startswith(("  ■", "  □"))][:3]
        assert "Insufficient evidence" in rows[-1]

    def test_no_confidence_figure_is_printed(self) -> None:
        assert "%" not in _plain(_result())


class TestClosingLine:
    def test_a_tie_on_the_real_write_is_named_as_a_tie(self) -> None:
        assert "Atlas could not tell which it was." in _plain(_result())

    def test_a_brief_about_something_else_is_a_miss_and_a_false_alarm(self) -> None:
        text = _plain(_result(concerns_truth=False))
        assert "Atlas missed the unauthorised write" in text
        assert "false alarm" in text

    def test_an_authorised_write_that_raised_nothing_is_right(self) -> None:
        text = _plain(_result(concerns_truth=False, unauthorised=False))
        assert "The authorised write raised nothing, which is right." in text

    def test_silence_over_an_unauthorised_write_is_a_miss(self) -> None:
        text = _plain(_result(brief=None, concerns_truth=False))
        assert "The unauthorised write went unseen." in text
