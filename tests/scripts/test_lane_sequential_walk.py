"""The walk-lane harness, exercised on a hand-made corpus and never on the real one.

The harness has to be right before it is declared, and looking at the real corpus to find out
whether it is right is the tuning-before-the-bar this cycle exists to avoid. So the fixture here is
built from literals: two normal runs and one walk run, with a known answer for each printed number.

The real corpus's column order is copied from a `process.csv` header — the header only, which is
schema, not measurement — so that a column-order mistake would still be caught here.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import numpy
import pytest

#: The real header, verbatim. Reading a header is reading a schema, not a value.
KEYS: tuple[str, ...] = (
    "tank_level_value",
    "tank_level_min",
    "tank_level_max",
    "tank_input_valve_status",
    "tank_output_valve_status",
    "tank_input_flow_value",
    "tank_output_flow_value",
    "bottle_level_value",
    "bottle_level_min",
    "bottle_level_max",
    "bottle_filling_level",
    "bottle_distance_to_filler_value",
    "bottle_output_flow_value",
    "conveyor_speed_value",
    "conveyor_speed_min",
    "conveyor_speed_max",
    "tank_input_flow_rate",
    "tank_output_flow_rate",
)

#: The script is not a package module, so it is loaded by path the way the tests do it elsewhere.
_HARNESS = Path(__file__).resolve().parents[2] / "scripts" / "lane_sequential_walk.py"


def test_the_harness_path_resolves() -> None:
    """A test for the path itself, because a wrong parent fails as a confusing collection error."""
    assert _HARNESS.is_file(), _HARNESS


def _load_harness() -> ModuleType:
    import sys

    spec = importlib.util.spec_from_file_location("lane_sequential_walk", _HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves its annotations through `sys.modules[cls.__module__]`, so a module
    # that is executed but never registered fails in the decorator rather than in this test.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_run(
    directory: Path,
    level_max: numpy.ndarray,
    level_value: numpy.ndarray,
    events: list[dict[str, object]],
) -> None:
    """Write one fixture run in the corpus's own layout: process.csv and events.json."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = level_max.shape[0]
    with (directory / "process.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", *KEYS])
        for row in range(rows):
            values = [0.0] * len(KEYS)
            values[KEYS.index("tank_level_value")] = float(level_value[row])
            values[KEYS.index("tank_level_min")] = 4.0
            values[KEYS.index("tank_level_max")] = float(level_max[row])
            writer.writerow([1_767_225_600.0 + row, *values])
    (directory / "events.json").write_text(json.dumps(events))


def _corpus(root: Path) -> Path:
    """Two normal runs and one run holding a walk and a single step."""
    normal = numpy.full(40, 7.0, dtype=numpy.float64)
    # One legitimate write in training, so the learned run is 1 and not 0.
    written = normal.copy()
    written[20:] = 6.9
    _write_run(root / "normal-1", normal, numpy.full(40, 7.0), [])
    _write_run(root / "normal-2", written, numpy.full(40, 7.0), [])

    walked = numpy.full(120, 7.0, dtype=numpy.float64)
    walked[40:100] = numpy.linspace(6.5, 7.5, 60)
    _write_run(
        root / "subfloor-1",
        walked,
        numpy.full(120, 4.0),
        [
            {"kind": "subfloor_walk", "label": "attack", "start": 40.0, "end": 99.0},
            {"kind": "setpoint", "label": "benign", "start": 110.0, "end": 111.0},
        ],
    )
    return root


def test_the_harness_prints_the_denominator_it_was_given(tmp_path: Path) -> None:
    """The event count is what the corpus holds, not the nine the real one holds."""
    module = _load_harness()
    corpus = _corpus(tmp_path / "corpus")
    assert module.main(["--corpus", str(corpus)]) == 0


def test_a_ramp_is_caught_by_the_run_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fixture's one walk ramps, so the sequential column's miss count is 0."""
    module = _load_harness()
    corpus = _corpus(tmp_path / "corpus")
    module.main(["--corpus", str(corpus)])
    printed = capsys.readouterr().out
    assert "walk events: 1" in printed
    assert "walk misses sequential: 0" in printed
    assert "subfloor-1" in printed
    assert "NO" not in printed.split("caught")[1]


def test_the_range_diagnostic_counts_samples_the_ramp_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ramp ends above the training maximum, so the order-blind half sees it too.

    The fixture ramp climbs to 7.5 while training topped out at 7.0, so this walk is *not* the
    clean separation the real corpus might be. That is the point of having both numbers: a fixture
    where only one is large shows the harness can tell them apart at all.
    """
    module = _load_harness()
    corpus = _corpus(tmp_path / "corpus")
    module.main(["--corpus", str(corpus)])
    printed = capsys.readouterr().out
    outside = int(
        next(line for line in printed.splitlines() if line.startswith("walk samples outside range"))
        .split(":")[1]
        .strip()
    )
    assert outside > 0


def test_a_held_step_is_not_a_walk() -> None:
    """A single in-band write on the scored tag produces no event, so it is not a caught walk.

    This is the fixture-level statement of what the mechanism can and cannot see, and it does not
    need the harness: it is `events` over one hand-made column.
    """
    from phos.atlas.consistency import events
    from phos.atlas.sequential_consistency import SequentialModel, sequential_scores

    stepped = numpy.full((120, 1), 7.0, dtype=numpy.float64)
    stepped[40:] = 7.4
    model = SequentialModel(column=0, longest_run=1)
    found = events(sequential_scores(model, stepped), threshold=1.0)
    assert found == []


def test_the_learned_threshold_is_what_the_harness_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A guard for the bug this harness had: `events` defaulted to the frozen `THRESHOLD`.

    Under the default a run of one — one legitimate setpoint write — opens an episode. Under the
    learned threshold it does not. The fixture below is a single step, and the two calls disagree,
    so a regression to the default fails here rather than silently inflating the false-alert count.
    """
    from phos.atlas.consistency import events
    from phos.atlas.sequential_consistency import SequentialModel, sequential_scores

    stepped = numpy.full((120, 1), 7.0, dtype=numpy.float64)
    stepped[40:] = 7.4
    scores = sequential_scores(SequentialModel(column=0, longest_run=1), stepped)

    under_default = events(scores)
    under_learned = events(scores, threshold=1.0)
    assert under_learned == []
    # The default is `THRESHOLD`, which is 1.0 and strict, so both agree here; the difference
    # appears only when training never moved, which the next assertion covers.
    assert under_default == under_learned

    never_moved = events(
        sequential_scores(SequentialModel(column=0, longest_run=0), stepped), threshold=0.0
    )
    assert never_moved, "with a learned run of 0 a single write is the strongest thing there is"


def test_a_step_only_corpus_reports_the_walk_as_missed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end: a corpus whose only walk-shaped event is a step must show one miss."""
    module = _load_harness()
    corpus = tmp_path / "corpus"
    normal = numpy.full(40, 7.0, dtype=numpy.float64)
    written = normal.copy()
    written[20:] = 6.9
    _write_run(corpus / "normal-1", normal, numpy.full(40, 7.0), [])
    _write_run(corpus / "normal-2", written, numpy.full(40, 7.0), [])

    stepped = numpy.full(120, 7.0, dtype=numpy.float64)
    stepped[40:] = 7.4
    _write_run(
        corpus / "subfloor-1",
        stepped,
        numpy.full(120, 4.0),
        [{"kind": "subfloor_walk", "label": "attack", "start": 40.0, "end": 99.0}],
    )
    module.main(["--corpus", str(corpus)])
    printed = capsys.readouterr().out
    assert "walk events: 1" in printed
    assert "walk misses sequential: 1" in printed
    assert "NO" in printed


def test_a_heldout_path_is_refused(tmp_path: Path) -> None:
    """The script is development only, and refuses by the path's name."""
    module = _load_harness()
    with pytest.raises(SystemExit, match="development only"):
        module.main(["--corpus", str(tmp_path / "phos-icssim-heldout4-walk")])


def test_a_corpus_with_no_attack_runs_is_refused(tmp_path: Path) -> None:
    """The denominator has to exist before it can be counted."""
    module = _load_harness()
    empty = tmp_path / "corpus"
    _write_run(empty / "normal-1", numpy.full(40, 7.0), numpy.full(40, 7.0), [])
    with pytest.raises(SystemExit, match="attack runs"):
        module.main(["--corpus", str(empty)])


def test_a_mismatched_column_order_is_refused(tmp_path: Path) -> None:
    """Two runs scored against one column order must agree on it, or the index means nothing."""
    module = _load_harness()
    corpus = tmp_path / "corpus"
    _write_run(corpus / "normal-1", numpy.full(40, 7.0), numpy.full(40, 7.0), [])
    _write_run(corpus / "normal-2", numpy.full(40, 7.0), numpy.full(40, 7.0), [])
    swapped = list(KEYS)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    rows = (corpus / "normal-2" / "process.csv").read_text().splitlines()
    rows[0] = "timestamp," + ",".join(swapped)
    (corpus / "normal-2" / "process.csv").write_text("\n".join(rows) + "\n")
    _write_run(
        corpus / "subfloor-1",
        numpy.full(120, 7.0),
        numpy.full(120, 4.0),
        [{"kind": "subfloor_walk", "label": "attack", "start": 40.0, "end": 99.0}],
    )
    with pytest.raises(SystemExit, match="column order"):
        module.main(["--corpus", str(corpus)])


def test_a_walk_window_holding_no_sample_is_skipped_not_crashed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A window outside the run's own clock cannot be scored, and says so rather than raising."""
    module = _load_harness()
    corpus = tmp_path / "corpus"
    _write_run(corpus / "normal-1", numpy.full(40, 7.0), numpy.full(40, 7.0), [])
    _write_run(
        corpus / "subfloor-1",
        numpy.full(120, 7.0),
        numpy.full(120, 4.0),
        [{"kind": "subfloor_walk", "label": "attack", "start": 5000.0, "end": 6000.0}],
    )
    module.main(["--corpus", str(corpus)])
    assert any("holds no sample" in record.message for record in caplog.records)


def test_a_run_with_no_labelled_walks_reports_zero_walks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty denominator must not be divided by, and the report has to say so."""
    module = _load_harness()
    corpus = tmp_path / "corpus"
    _write_run(corpus / "normal-1", numpy.full(40, 7.0), numpy.full(40, 7.0), [])
    _write_run(
        corpus / "subfloor-1",
        numpy.full(120, 7.0),
        numpy.full(120, 4.0),
        [{"kind": "setpoint", "label": "benign", "start": 40.0, "end": 41.0}],
    )
    module.main(["--corpus", str(corpus)])
    printed = capsys.readouterr().out
    assert "walk events: 0" in printed
    assert "walk min outside range: 0" in printed
