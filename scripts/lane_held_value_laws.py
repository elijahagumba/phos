"""Ask whether a single held value fires each of the six laws, under each historian reading.

Cycle 1 found that `subfloor_walk` fires on `held_setpoint` under ``step_source="row"`` and is
silent under ``"change"``. That leaves a question the matrix cannot answer, because the matrix
scores classes rather than laws: is the row reading wrong for **every** law, or only this one?

The distinction matters and it is mechanical. A held value is one write followed by rows that repeat
it. Under ``row`` each repeated row is a step, so a value held for N seconds presents as N steps.
Under ``change`` the repetition collapses and it presents as one step. Any law that reads a run of
steps therefore sees a different world under the two readings, whatever class it names. A law that
does not read runs should see no difference.

So the measurement is a matrix of six laws against two readings, one cell per law per reading, with
the fact of whether it fired. What a bar can ask for:

- A law that names no run-reading behaviour should not fire on a held value at all.
- A law that does read runs will fire under ``row`` and may not under ``change``. That is the law
  being sensitive to the reading, which is a property to report rather than to score, so it is
  counted and printed beside the bars rather than being one.

This harness deliberately does not reuse the class fixtures from `law_discrimination_matrix.py`:
the question is per-law, and a class fixture would tie the answer to the thirteen classes that
script happens to construct. It builds one held value and asks all six laws about it.

Nothing here edits a law, a predicate, a constant, a frozen number or an inlet default. The digest
of the module under test is printed so a reader can see which implementation was measured.

Usage::

    uv run python scripts/lane_held_value_laws.py --report <path>
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from phos.atlas.declared_law import LAWS, LawRegister, assess_plant  # noqa: E402
from phos.atlas.law_inlet import HistorianRow, StepSource, inlet_from_tables  # noqa: E402

#: The tag held in every construction below. A value inside the ordinary band, so nothing about it
#: is a departure in itself.
TAG: Final = "tank_level_max"

#: The value held, and how many rows hold it. Inside the band 6.5 to 7.5 that the walk class uses.
VALUE: Final = 6.9

#: How many rows hold the value. Seven hundred and twenty, which is the construction ADR 0465 and
#: cycle 1's matrix both used. A much shorter hold fires nothing at all, which was tried first and
#: is why this number is not arbitrary: the walk law's own learned threshold decides when a run of
#: repeated values counts as a walk, and forty rows is below it.
HOLD_ROWS: Final = 720

#: One second apart.
STEP: Final = timedelta(seconds=1)

#: The first row's time. Fixed, so two runs of this harness compare.
T0: Final = datetime(2026, 1, 1, tzinfo=UTC)

#: The six law names, in the order the register states them. Read from the register rather than
#: typed, so a law added or removed is a refusal below rather than a silent mismatch.
LAW_NAMES: Final = tuple(law.name for law in LAWS)

#: The register the inlet is built over.
REGISTER: Final = LawRegister(LAWS)


def held_rows() -> list[HistorianRow]:
    """Return the held value as rows: the same value written once and then repeated.

    Returns:
        One row per second, all carrying ``VALUE``.
    """
    return [HistorianRow(TAG, T0 + STEP * index, VALUE) for index in range(HOLD_ROWS)]


def fired_laws(reading: StepSource) -> dict[str, bool]:
    """Return which laws fire on a single held value, under one historian reading.

    Args:
        reading: ``"row"`` or ``"change"``.

    Returns:
        Law name to whether it appeared among the register's broken laws.
    """
    inlet = inlet_from_tables(
        register=REGISTER,
        historian=held_rows(),
        setpoint_tags=frozenset({TAG}),
        step_source=reading,
    )
    report = assess_plant(
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
    broken = {item.name for item in report.broken}
    return {name: name in broken for name in LAW_NAMES}


def law_count() -> int:
    """Return how many laws the register states.

    Returns:
        The count, which must be six for this harness to mean what it says.
    """
    return len(LAWS)


def module_digest() -> str:
    """Return the SHA-256 of the declared-law module, so a reader knows what was measured.

    Returns:
        The hex digest.
    """
    import phos.atlas.declared_law as module

    source = Path(module.__file__).read_bytes()
    return hashlib.sha256(source).hexdigest()


def measure() -> dict[str, float]:
    """Return the metrics the declaration names.

    Returns:
        Metric name to value.
    """
    row = fired_laws("row")
    change = fired_laws("change")
    row_names = [name for name, fired in row.items() if fired]
    change_names = [name for name, fired in change.items() if fired]
    return {
        # How many laws fire at all on a value whose class is not any of theirs.
        "laws_fired_row": float(len(row_names)),
        "laws_fired_change": float(len(change_names)),
        # Laws whose answer differs between the readings. These read runs, so the reading matters.
        "laws_reading_sensitive": float(
            sum(1 for name in LAW_NAMES if row[name] != change[name])
        ),
        # The law names, as a count each, so a bar can require a specific one to be silent.
        "subfloor_walk_fired_row": 1.0 if row["subfloor_walk"] else 0.0,
        "subfloor_walk_fired_change": 1.0 if change["subfloor_walk"] else 0.0,
    }


def render(metrics: dict[str, float], path: Path) -> None:
    """Write the report a reader can check the numbers against.

    Args:
        metrics: The measured metrics.
        path: Where to write it.
    """
    row = fired_laws("row")
    change = fired_laws("change")
    lines = [
        "# A single held value, and which laws fire on it",
        "",
        f"Written by `scripts/lane_held_value_laws.py` on {datetime.now(UTC).date().isoformat()}.",
        "",
        f"One tag, `{TAG}`, held at `{VALUE}` for {HOLD_ROWS} one-second rows. The value is inside "
        "the ordinary band, so nothing in it is a departure. The class it belongs to is not any of "
        "the six classes the laws name.",
        "",
        f"The digest of the module under test is `{module_digest()}`.",
        "",
        "## Which laws fire",
        "",
        "| law | row reading | change reading | differs |",
        "|---|---|---|---|",
    ]
    for name in LAW_NAMES:
        differs = "yes" if row[name] != change[name] else ""
        marks = {True: "**fires**", False: "silent"}
        lines.append(f"| `{name}` | {marks[row[name]]} | {marks[change[name]]} | {differs} |")
    lines += [
        "",
        "## The metrics",
        "",
        "| metric | value |",
        "|---|---|",
    ]
    for key, value in metrics.items():
        lines.append(f"| `{key}` | {value:g} |")
    lines += [
        "",
        "## What a reader should take from this",
        "",
        "A law that fires here is firing on a value whose class it does not name. A law that fires "
        "under one reading and not the other is reading runs rather than individual values, and "
        "the historian reading decides what a run is. Neither is edited by this harness.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """Run the measurement and write the report.

    Returns:
        0 on success.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if law_count() != len(LAW_NAMES):
        print(
            f"refused: the register states {law_count()} laws, and this harness names "
            f"{len(LAW_NAMES)}. "
            "The harness would measure a set the register no longer holds.",
            file=sys.stderr,
        )
        return 2

    metrics = measure()
    render(metrics, args.report)
    print("result: atlas-held-value-laws")
    for key, value in metrics.items():
        print(f"{key}: {value:g}")
    print()
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
