"""Every value a public chart plots is the value its record holds (ADR 0381).

The value half reads the committed records through ``chart_records`` — standard library only —
and checks each plate shows exactly those values, so it runs everywhere, including the public
repository, where the overlay lands at the root. Assertions are whole phrases rather than bare
numbers so they cannot be satisfied by the embedded font's payload. The rebuild half redraws the
plates and compares them to what is committed; it needs the font tooling the plates embed and is
skipped where that library is absent, which is the intended direction of failure: a plate that
cannot be rebuilt is checked by the value half, and a record whose shape moved raises in
``chart_records`` rather than quietly plotting a shorter series.
"""

import importlib
import re
from html import unescape
from pathlib import Path
from typing import Final

import pytest
from public.figures.chart_records import a2_rows, lane3_dial, lane4_knots

_ROOT: Final = Path(__file__).resolve().parents[2]
_PLATES: Final = (
    _ROOT / "public" / "overlay" / ".github" / "assets" / "readme"
    if (_ROOT / "public" / "overlay" / ".github" / "assets" / "readme").is_dir()
    else _ROOT / ".github" / "assets" / "readme"
)
_LANE3: Final = "chart-lane3-delay.svg"
_LANE4: Final = "chart-lane4-quiet.svg"
_OLDER: Final = "chart-older-engine.svg"


def _visible_text(name: str) -> str:
    svg = (_PLATES / name).read_text(encoding="utf-8")
    without_style = re.sub(r"<style.*?</style>", " ", svg, flags=re.DOTALL)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", without_style)))


def test_the_lane3_plate_plots_the_lane3_record() -> None:
    dial = lane3_dial()
    text = _visible_text(_LANE3)
    assert f"OF {dial.attacks}" in text
    assert f"frozen engine {dial.frozen_caught} {dial.frozen_delay_seconds} s" in text
    for setting in dial.settings:
        assert f"{setting.cap:.2f} {setting.caught} {setting.delay_seconds} s" in text


def test_the_lane4_plate_plots_the_lane4_record() -> None:
    table = lane4_knots()
    text = _visible_text(_LANE4)
    assert f"OF {table.attacks}" in text
    for setting in table.settings:
        name = "0, the frozen engine" if setting.is_frozen else str(setting.knots)
        assert f"{name} {setting.caught} {setting.false_alarms_per_day:.2f}" in text


def test_the_older_engine_plate_plots_the_a2_record() -> None:
    text = _visible_text(_OLDER)
    for row in a2_rows():
        assert row.corpus.replace("hai-", "HAI ") in text
        assert f"{row.caught} of {row.attacks}, Atlas" in text
        assert f"{row.opponent_caught} of {row.attacks}, baseline" in text


def test_the_committed_plates_are_what_the_builder_draws() -> None:
    pytest.importorskip("fontTools", reason="the plates embed Inter, which needs fonttools")
    build_charts = importlib.import_module("public.figures.build_charts")
    for name, svg in build_charts.charts().items():
        assert (_PLATES / name).read_text(encoding="utf-8") == svg
