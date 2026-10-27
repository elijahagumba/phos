#!/usr/bin/env python3
"""Count the law-page invariants on a development corpus (ADR 0333).

ADR 0325 named the inlet. ADR 0333 declares this run: the eight structural bars from
section 4 of ``docs/zero-to-one-master-plan.md``, each one a count whose bar is 0. This
command reports counts. **It reports no detection rate, no recall, no false-alarm rate,
no latency and no magnitude**, and nothing it prints may be restated as one.

None of the residual page builders or consistency modules ADR 0325 lists is imported.
``eval_runs/log.jsonl`` is never appended. Development only: a path whose name contains
``heldout`` is refused.

Three inlets per run, because one ``inlet_from_tables`` call cannot carry both a setpoint
series over the run and a controller sample at a single instant: ``series`` (the setpoint
tags, with the station set the plant named), ``series-unstated`` (the same rows with an
empty station set, so ``allowed_writer`` is unstated rather than broken), and ``instant``
(the ten controller tags at one shared time, no setpoint tags).

Bars 5 to 8 are not reachable from ordinary rows. Their cases are built in
``scripts/lane_law_inlet_probes.py``, which returns values and counts nothing; the
thresholds live here. The report says which counts are corpus and which are probe.

Usage::

    uv run python scripts/lane_law_inlet_invariants.py --corpus data/phos-icssim-dev
"""

from __future__ import annotations

import argparse
import logging
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lane_law_inlet_probes import (  # noqa: E402
    empty_register_inlet,
    magnitude_break,
    probe_breaks,
    refused_frames,
)

from phos.atlas.declared_law import (  # noqa: E402
    LAWS,
    OPERATOR_PAGE_CEILING,
    LawRegister,
    LawReport,
    WriterWrite,
    assess_plant,
    page_from_report,
)
from phos.atlas.icssim_adapter import read_run, read_traffic  # noqa: E402
from phos.atlas.law_inlet import (  # noqa: E402
    PLC1_CONTROLLER_TAGS,
    HistorianRow,
    LawInlet,
    inlet_from_tables,
)

logger = logging.getLogger("lane_law_inlet_invariants")

#: The result name ADR 0333 reserved. Nothing else names this run.
RESULT_NAME: Final = "law-inlet:invariants"

#: The six tags ADR 0333 names as this corpus's setpoints. Read from ``roles.toml`` and
#: compared with this set, so a corpus whose roles moved is refused rather than scored.
DECLARED_SETPOINT_TAGS: Final[frozenset[str]] = frozenset(
    {
        "tank_input_valve_mode",
        "tank_level_min",
        "tank_level_max",
        "tank_output_valve_mode",
        "conveyor_belt_engine_mode",
        "bottle_level_max",
    }
)

#: The stations the plant is taken to have named. A write from anywhere else breaks
#: ``allowed_writer``. ``attacker`` is deliberately absent; it is a role the corpus writes.
DEFAULT_ALLOWED_STATIONS: Final[tuple[str, ...]] = ("operator", "plc1", "plc2")

#: The words a placed sentence may not carry. The same five ``declared_law`` refuses.
_SCORE_WORDS: Final[tuple[str, ...]] = (
    "confidence",
    "probability",
    "weight",
    "magnitude",
    "score",
)

#: What the counts are not. Printed in the report so a reader cannot take them for a rate.
_CAVEAT: Final = (
    "Bars 1 to 4 are counted over corpus-built pages. Bar 5 is counted over corpus pages and"
    " over a constructed twelve-break page per run, because ordinary rows need not produce a"
    " ninth break. Bars 6, 7 and 8 are probes. None of these counts is a detection rate, a"
    " false-alarm rate, a recall, a latency or a magnitude, and none may be restated as one."
    " A break is a false law, not an attack. The page does not name the cause. An empty page"
    " is not a safe plant. Synthetic results are a simulated diagnosis, not a field rate"
    " (ADR 0073)."
)


@dataclass
class Tally:
    """The eight bars, and the counts reported beside them.

    Every ``bar_`` field is a violation count whose declared bar is 0. Every other field
    is a count for the verdict to quote and is not a threshold.
    """

    bar1_uncited_sentences: int = 0
    bar2_score_word_sentences: int = 0
    bar3_pages_over_ceiling: int = 0
    bar4_partition_faults: int = 0
    bar5_misordered_pages: int = 0
    bar6_subclasses_admitted: int = 0
    bar7_inlets_from_refused_frames: int = 0
    bar8_empty_register_faults: int = 0

    runs: int = 0
    inlets: int = 0
    pages: int = 0
    sentences: int = 0
    reports_over_ceiling: int = 0
    frames_refused: int = 0
    page_lengths: dict[int, int] = field(default_factory=dict)

    @property
    def bars(self) -> tuple[tuple[str, int], ...]:
        """Return each bar's name and count, in the order ADR 0333 lists them."""
        return (
            ("1 placed sentence does not name its law", self.bar1_uncited_sentences),
            ("2 placed sentence carries a score-word", self.bar2_score_word_sentences),
            ("3 page longer than the ceiling", self.bar3_pages_over_ceiling),
            ("4 register name not in exactly one list", self.bar4_partition_faults),
            ("5 page is not the earliest eight", self.bar5_misordered_pages),
            ("6 LawBreak subclass admitted", self.bar6_subclasses_admitted),
            ("7 inlet built from a refused frame", self.bar7_inlets_from_refused_frames),
            ("8 empty register not three empty lists", self.bar8_empty_register_faults),
        )

    @property
    def met(self) -> bool:
        """Whether every bar is 0. A bar is met or not met; there is no tolerance."""
        return all(count == 0 for _name, count in self.bars)


def _at(unix: float) -> datetime:
    """Return a timezone-aware UTC time for a corpus timestamp."""
    return datetime.fromtimestamp(unix, tz=UTC)


def _setpoint_tags(corpus: Path) -> frozenset[str]:
    """Read the setpoint tags from the corpus's own ``roles.toml``.

    Args:
        corpus: The corpus directory.

    Returns:
        The tags whose declared role is ``setpoint``.

    Raises:
        SystemExit: If the file is absent, or the set is not the one ADR 0333 names. A
            corpus whose roles moved is refused here rather than scored against a bar
            that was declared for a different set of tags.
    """
    path = corpus / "roles.toml"
    if not path.is_file():
        raise SystemExit(f"{path} is absent; this run needs the corpus's declared roles")
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    points = document.get("points", [])
    tags = frozenset(
        str(point["signal"]) for point in points if str(point.get("role", "")) == "setpoint"
    )
    if tags != DECLARED_SETPOINT_TAGS:
        raise SystemExit(
            f"{path} marks {sorted(tags)} as setpoints; ADR 0333 names "
            f"{sorted(DECLARED_SETPOINT_TAGS)}. The run is refused, not adjusted."
        )
    return tags


def _historian(
    keys: tuple[str, ...],
    times: list[float],
    values: list[list[float]],
    wanted: frozenset[str],
) -> tuple[HistorianRow, ...]:
    """Build rows for the wanted tags only, so a 13-column file is not copied whole.

    Args:
        keys: The ``process.csv`` header without ``timestamp``.
        times: Unix seconds, one per row.
        values: Rows of values, in ``keys`` order.
        wanted: The tags to build rows for. Others are left out.

    Returns:
        One row per wanted tag per sample, in file order.
    """
    columns = [(index, key) for index, key in enumerate(keys) if key in wanted]
    rows: list[HistorianRow] = []
    for row_index, unix in enumerate(times):
        at = _at(unix)
        for index, key in columns:
            rows.append(HistorianRow(tag=key, at=at, value=values[row_index][index]))
    return tuple(rows)


def _writes(directory: Path) -> tuple[WriterWrite, ...]:
    """Return one write per writing Modbus message, with the station the corpus recorded.

    The station is the ``role`` column, which the corpus supplies. No station is inferred
    from a function code, and no function code becomes a program act.

    Args:
        directory: One run directory.

    Returns:
        The writes, in file order.
    """
    return tuple(
        WriterWrite(station=command.role, at=_at(command.at))
        for command in read_traffic(directory, writes_only=True)
        if command.role != ""
    )


def _assess(inlet: LawInlet) -> LawReport:
    """Pass an inlet's fields to ``assess_plant`` and nothing else."""
    return assess_plant(
        inlet.steps,
        inlet.transfers,
        register=inlet.register,
        bookings=inlet.bookings,
        work_orders=inlet.work_orders,
        tag_bookings=inlet.tag_bookings,
        writes=inlet.writes,
        allowed_stations=inlet.allowed_stations,
        controller=inlet.controller,
    )


def _check_report(report: LawReport, register: LawRegister, tally: Tally) -> None:
    """Count bars 1 to 5 over one report, re-deriving each property independently.

    ``law_page`` guards itself, so a violation would surface as a raise rather than as a
    bad page. Each property is checked again here on the placed output, so the count does
    not rest on the function under test agreeing with itself.

    Args:
        report: One assessment.
        register: The laws the plant named.
        tally: The counts to add to.
    """
    page = page_from_report(report, register=register)
    tally.pages += 1
    tally.page_lengths[len(page)] = tally.page_lengths.get(len(page), 0) + 1

    for placed in page:
        tally.sentences += 1
        if not placed.statement.startswith(f"{placed.name}. "):
            tally.bar1_uncited_sentences += 1
        folded = placed.statement.casefold()
        if any(word in folded for word in _SCORE_WORDS):
            tally.bar2_score_word_sentences += 1

    if len(page) > OPERATOR_PAGE_CEILING:
        tally.bar3_pages_over_ceiling += 1

    appearances: dict[str, set[str]] = {law.name: set() for law in register.laws}
    for outcome in report.held:
        appearances.setdefault(outcome.name, set()).add("held")
    for broken in report.broken:
        appearances.setdefault(broken.name, set()).add("broken")
    for outcome in report.unstated:
        appearances.setdefault(outcome.name, set()).add("unstated")
    tally.bar4_partition_faults += sum(1 for lists in appearances.values() if len(lists) != 1)

    if len(report.broken) > OPERATOR_PAGE_CEILING:
        tally.reports_over_ceiling += 1
    expected = tuple(sorted(report.broken, key=lambda item: (item.time, item.name)))
    if page != expected[:OPERATOR_PAGE_CEILING]:
        tally.bar5_misordered_pages += 1


def _score_run(
    directory: Path,
    *,
    register: LawRegister,
    tags: frozenset[str],
    allowed: frozenset[str],
    max_rows: int,
    tally: Tally,
) -> datetime:
    """Build this run's three inlets, count bars 1 to 5, and probe the ceiling.

    Args:
        directory: One run directory holding ``process.csv``.
        register: The laws the plant named.
        tags: The corpus's declared setpoint tags.
        allowed: The stations the plant named.
        max_rows: A positive cap on rows read, or 0 for every row.
        tally: The counts to add to.

    Returns:
        The run's first sample time.

    Raises:
        SystemExit: If the run has no column for a controller tag.
    """
    run = read_run(directory)
    limit = len(run.times) if max_rows == 0 else min(max_rows, len(run.times))
    times = [float(value) for value in run.times[:limit]]
    values = [[float(cell) for cell in row] for row in run.values[:limit]]
    series = _historian(run.keys, times, values, tags)
    writes = _writes(directory)

    for stations in (allowed, frozenset()):
        inlet = inlet_from_tables(
            register=register,
            historian=series,
            setpoint_tags=tags,
            writes=writes,
            allowed_stations=stations,
        )
        tally.inlets += 1
        _check_report(_assess(inlet), register, tally)

    wanted = frozenset(PLC1_CONTROLLER_TAGS.values())
    missing = wanted - set(run.keys)
    if missing:
        raise SystemExit(f"{directory} has no column for {sorted(missing)}")
    instant = inlet_from_tables(
        register=register,
        historian=_historian(run.keys, times[:1], values[:1], wanted),
        controller_tags=PLC1_CONTROLLER_TAGS,
    )
    tally.inlets += 1
    _check_report(_assess(instant), register, tally)

    at = _at(times[0])
    _check_report(
        LawReport(held=(), broken=probe_breaks(register, at), unstated=()), register, tally
    )
    tally.runs += 1
    return at


def _count_probes(register: LawRegister, at: datetime, tally: Tally) -> None:
    """Count bars 6, 7 and 8 from the constructed cases.

    Args:
        register: The laws the plant named.
        at: A time taken from the corpus, so the cases sit on the run's own clock.
        tally: The counts to add to.
    """
    offered = magnitude_break(register, at)
    try:
        placed = page_from_report(
            LawReport(held=(), broken=(offered,), unstated=()), register=register
        )
    except ValueError:
        placed = ()
    tally.bar6_subclasses_admitted += len(placed)

    for refused in refused_frames(at):
        tally.frames_refused += 1
        try:
            inlet_from_tables(register=register, malformed=(refused,))
        except ValueError:
            continue
        tally.bar7_inlets_from_refused_frames += 1

    report = _assess(empty_register_inlet(at))
    if report.held != () or report.broken != () or report.unstated != ():
        tally.bar8_empty_register_faults += 1


def _report_markdown(corpus: Path, tally: Tally, allowed: frozenset[str]) -> str:
    """Render the counts as the report ADR 0333 names. No rate appears in it."""
    lines = [
        f"# {RESULT_NAME}",
        "",
        f"- **Corpus:** `{corpus}` (development tier; held-out is refused by this script)",
        "- **Declared by:** ADR 0333",
        f"- **Runs:** {tally.runs} · **inlets:** {tally.inlets} · **pages:** {tally.pages}"
        f" · **placed sentences:** {tally.sentences}",
        f"- **Stations the plant named:** {sorted(allowed)}",
        f"- **Ceiling:** {OPERATOR_PAGE_CEILING}",
        "",
        "## Bars (each declared 0)",
        "",
        "| Bar | Count | Met |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {name} | {count} | {'yes' if count == 0 else 'NO'} |" for name, count in tally.bars
    ]
    lines += [
        "",
        f"**All eight met:** {'yes' if tally.met else 'no'}",
        "",
        "## Reported beside the bars, and not a bar",
        "",
        f"- Corpus reports with more breaks than the ceiling: {tally.reports_over_ceiling}",
        f"- Frames the dissector refused and the inlet was offered: {tally.frames_refused}",
        "- Page lengths: "
        + ", ".join(f"{length}: {count}" for length, count in sorted(tally.page_lengths.items())),
        "",
        _CAVEAT,
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Count the eight invariants and write the report. Held-out paths are refused."""
    parser = argparse.ArgumentParser(description="Law-page invariant counts (ADR 0333).")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "eval_runs/build/lane-law-inlet/invariants.md"
    )
    parser.add_argument("--max-rows", type=int, default=0, help="0 reads every row of each run")
    parser.add_argument(
        "--allowed-stations",
        default=",".join(DEFAULT_ALLOWED_STATIONS),
        help="comma-separated stations the plant named",
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpus: Path = arguments.corpus
    if "heldout" in corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    if not corpus.is_dir():
        raise SystemExit(f"{corpus} is not a directory; generate the development corpus first")
    if arguments.max_rows < 0:
        raise SystemExit("--max-rows is 0 for every row, or a positive cap")
    allowed = frozenset(
        part.strip() for part in str(arguments.allowed_stations).split(",") if part.strip()
    )
    if not allowed:
        raise SystemExit("--allowed-stations is not empty; the empty set is the second inlet")

    tags = _setpoint_tags(corpus)
    register = LawRegister(laws=LAWS)
    tally = Tally()
    runs = [
        child
        for child in sorted(corpus.iterdir())
        if child.is_dir() and (child / "process.csv").is_file()
    ]
    if not runs:
        raise SystemExit(f"{corpus} holds no run with a process.csv")

    first: datetime | None = None
    for directory in runs:
        at = _score_run(
            directory,
            register=register,
            tags=tags,
            allowed=allowed,
            max_rows=arguments.max_rows,
            tally=tally,
        )
        first = at if first is None else first
        logger.info("%s: %s pages so far", directory.name, tally.pages)
    if first is None:
        raise SystemExit("no run produced a sample time")
    _count_probes(register, first, tally)

    out: Path = arguments.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_report_markdown(corpus, tally, allowed))
    for name, count in tally.bars:
        logger.info("bar %s: %s", name, count)
    logger.info("%s: all eight met = %s; report at %s", RESULT_NAME, tally.met, out)
    return 0 if tally.met else 1


if __name__ == "__main__":
    raise SystemExit(main())
