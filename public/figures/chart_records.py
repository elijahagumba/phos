"""Read the committed records the public charts plot.

Nothing here draws. Every value a chart shows is read from a file in this repository at build
time, so a chart cannot carry a number the record does not hold (ADR 0381). A record whose shape
has moved raises here rather than quietly plotting a shorter series: the records are markdown and
JSON written by the harnesses, and a silently empty table would be worse than a failed build.

Three records are read:

* ``eval_runs/build/lane-e/lane3-development.md`` for lane 3's dial (ADR 0286). The per-class
  table gives the frozen engine's catches and the attack total; the dial table gives each cap's
  catches and the paired median delay.
* ``eval_runs/build/lane-e/lane4-development.md`` for lane 4's knots (ADR 0288). The knot table
  gives catches, benign events alerting, and false alarms a day in sample and leave-one-out.
* ``eval_runs/v1/a2-status.json`` for the older engine against the best grouped checked opponent
  on the three later HAI editions (ADR 0116).

This module imports nothing outside the standard library, so a test can read the records without
the font tooling the plates need.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
LANE3_RECORD: Final = REPO_ROOT / "eval_runs" / "build" / "lane-e" / "lane3-development.md"
LANE4_RECORD: Final = REPO_ROOT / "eval_runs" / "build" / "lane-e" / "lane4-development.md"
A2_RECORD: Final = REPO_ROOT / "eval_runs" / "v1" / "a2-status.json"

#: The three later HAI editions the public page quotes, in the order it quotes them.
A2_CORPORA: Final[tuple[str, ...]] = ("hai-21.03", "hai-22.04", "hai-23.05")

_ROW: Final = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_DELAY: Final = re.compile(r"^(?P<frozen>\d+)\s*s\s*(?:→|->)\s*(?P<lane>\d+)\s*s$")
_KNOTS: Final = re.compile(r"^(?P<knots>\d+)")


class RecordShapeError(RuntimeError):
    """A record no longer holds the table or field a chart reads from it."""


@dataclass(frozen=True)
class DialSetting:
    """One setting of lane 3's one free parameter.

    Attributes:
        cap: The contribution cap the row measured.
        caught: Attacks caught within the budget at that cap.
        delay_seconds: Lane 3's paired median detection delay, in seconds.
    """

    cap: float
    caught: int
    delay_seconds: int


@dataclass(frozen=True)
class Lane3Dial:
    """Lane 3's whole dial, with the frozen engine it was measured against.

    Attributes:
        attacks: Attacks in the corpus.
        frozen_caught: Attacks the frozen engine caught.
        frozen_delay_seconds: The frozen engine's paired median delay, in seconds.
        settings: One row per cap, in the order the record lists them.
    """

    attacks: int
    frozen_caught: int
    frozen_delay_seconds: int
    settings: tuple[DialSetting, ...]


@dataclass(frozen=True)
class KnotSetting:
    """One knot count of lane 4's hinge basis.

    Attributes:
        knots: Knots in the basis. Zero is the frozen engine itself.
        label: How the record names the row.
        caught: Attacks caught within the budget.
        false_alarms_per_day: False alarms a day, leave one out, the honest reading.
    """

    knots: int
    label: str
    caught: int
    false_alarms_per_day: float

    @property
    def is_frozen(self) -> bool:
        """Whether this row is the frozen engine rather than a bent predictor."""
        return self.knots == 0


@dataclass(frozen=True)
class Lane4Table:
    """Lane 4's knot table.

    Attributes:
        attacks: Attacks in the corpus.
        settings: One row per knot count, in the order the record lists them.
    """

    attacks: int
    settings: tuple[KnotSetting, ...]


@dataclass(frozen=True)
class A2Row:
    """One corpus from the A2 status, as the record holds it.

    Attributes:
        corpus: The corpus name.
        attacks: Attacks in that corpus.
        caught: Attacks the older engine caught within eight alerts a shift.
        opponent_caught: Attacks the best grouped checked opponent caught, scored the same way.
        opponent: The opponent's detector name.
        exposure: What the record says about whether the engine had seen that corpus.
    """

    corpus: str
    attacks: int
    caught: int
    opponent_caught: int
    opponent: str
    exposure: str


def _table(text: str, heading: str) -> tuple[tuple[str, ...], ...]:
    """Return the body rows of the markdown table whose first cell is ``heading``.

    Args:
        text: The whole record.
        heading: The first cell of the table's header row.

    Returns:
        One tuple of stripped cells per body row, alignment row dropped.

    Raises:
        RecordShapeError: If no table in the record starts with that heading.
    """
    rows: list[tuple[str, ...]] = []
    found = False
    for line in text.splitlines():
        match = _ROW.match(line)
        if match is None:
            if found:
                break
            continue
        cells = tuple(cell.strip() for cell in match.group("cells").split("|"))
        if not found:
            if cells[0] == heading:
                found = True
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(cells)
    if not found or not rows:
        raise RecordShapeError(f"no table headed {heading!r}")
    return tuple(rows)


def _plain(cell: str) -> str:
    """Return a table cell without the record's emphasis markers."""
    return cell.replace("**", "").strip()


def _count(cell: str) -> int:
    """Return a cell as a count.

    Args:
        cell: The cell text, emphasis included.

    Returns:
        The integer the cell holds.

    Raises:
        RecordShapeError: If the cell is not a plain count.
    """
    value = _plain(cell)
    if not value.isdigit():
        raise RecordShapeError(f"{value!r} is not a count")
    return int(value)


def lane3_dial() -> Lane3Dial:
    """Return lane 3's dial and the frozen engine beside it (ADR 0286).

    The frozen catches and the attack total are summed from the per-class table, where every
    attack class carries its own frozen count and its own ``Of``. The dial table gives each cap.

    Returns:
        The dial, in the order the record lists its caps.

    Raises:
        RecordShapeError: If either table has moved or a delay cell is not two times in seconds.
    """
    text = LANE3_RECORD.read_text(encoding="utf-8")
    attacks = 0
    frozen_caught = 0
    for cells in _table(text, "Label"):
        if _plain(cells[0]) != "attack":
            continue
        frozen_caught += _count(cells[2])
        attacks += _count(cells[4])
    if attacks == 0:
        raise RecordShapeError("the per-class table holds no attack rows")

    settings: list[DialSetting] = []
    frozen_delays: set[int] = set()
    for cells in _table(text, "Cap"):
        delay = _DELAY.match(_plain(cells[3]))
        if delay is None:
            raise RecordShapeError(f"{_plain(cells[3])!r} is not a paired delay")
        frozen_delays.add(int(delay.group("frozen")))
        settings.append(
            DialSetting(
                cap=float(_plain(cells[0])),
                caught=_count(cells[1]),
                delay_seconds=int(delay.group("lane")),
            )
        )
    if len(frozen_delays) != 1:
        raise RecordShapeError("the dial table gives the frozen engine more than one delay")
    return Lane3Dial(
        attacks=attacks,
        frozen_caught=frozen_caught,
        frozen_delay_seconds=frozen_delays.pop(),
        settings=tuple(settings),
    )


def lane4_knots() -> Lane4Table:
    """Return lane 4's knot table (ADR 0288).

    The attack total is the table's own heading, ``Attacks caught of 70``, so the denominator is
    read from the record rather than assumed.

    Returns:
        The knot table, in the order the record lists its settings.

    Raises:
        RecordShapeError: If the table has moved or its heading carries no attack total.
    """
    text = LANE4_RECORD.read_text(encoding="utf-8")
    heading = "Knots"
    attacks: int | None = None
    for line in text.splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        header = [cell.strip() for cell in match.group("cells").split("|")]
        if header[0] != heading:
            continue
        total = re.search(r"of\s+(\d+)", header[1])
        if total is None:
            raise RecordShapeError(f"{header[1]!r} names no attack total")
        attacks = int(total.group(1))
        break
    if attacks is None:
        raise RecordShapeError(f"no table headed {heading!r}")

    settings: list[KnotSetting] = []
    for cells in _table(text, heading):
        label = _plain(cells[0])
        knots = _KNOTS.match(label)
        if knots is None:
            raise RecordShapeError(f"{label!r} does not open with a knot count")
        settings.append(
            KnotSetting(
                knots=int(knots.group("knots")),
                label=label,
                caught=_count(cells[1]),
                false_alarms_per_day=float(_plain(cells[4])),
            )
        )
    return Lane4Table(attacks=attacks, settings=tuple(settings))


def a2_rows() -> tuple[A2Row, ...]:
    """Return the older engine against the best grouped checked opponent (ADR 0116).

    Only the three later HAI editions the public page quotes are returned, in that order.

    Returns:
        One row per corpus in :data:`A2_CORPORA`.

    Raises:
        RecordShapeError: If the record is missing one of those corpora or a field.
    """
    payload = json.loads(A2_RECORD.read_text(encoding="utf-8"))
    by_corpus = {row["corpus"]: row for row in payload["rows"]}
    rows: list[A2Row] = []
    for corpus in A2_CORPORA:
        row = by_corpus.get(corpus)
        if row is None:
            raise RecordShapeError(f"{corpus} is not in {A2_RECORD.name}")
        try:
            rows.append(
                A2Row(
                    corpus=corpus,
                    attacks=int(row["attacks"]),
                    caught=int(row["consistency_caught"]),
                    opponent_caught=int(row["opponent_caught"]),
                    opponent=str(row["best_grouped_checked_opponent"]),
                    exposure=str(row["exposure"]),
                )
            )
        except KeyError as missing:
            raise RecordShapeError(f"{corpus} has no {missing}") from missing
    return tuple(rows)
