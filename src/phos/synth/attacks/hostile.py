"""Attacks on the data pipeline, and the claim they are not allowed to support.

An input-hostile case never touches the simulated plant. It corrupts the *file* Atlas reads, and it
asks one question: does the software survive rubbish without crashing, without corrupting its
baseline, and — worst of all — without producing a confident answer that is quietly wrong.

**What passing one means, and what it does not.** Surviving this set is evidence that Atlas handles
hostile input safely. It is **not** evidence that PHOS is secure against a real-world attacker.
That claim needs a live deployment, an exposed attack surface, and an adversary who did not read
this file, none of which exist here. `INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT` travels with every
corpus this module touches, and the code enforces the boundary rather than trusting anyone to
remember it: a `HostileGroundTruth` has no method that produces a `LabelledInterval`, so nothing
here can ever reach a corpus's attack intervals and be scored as a missed detection.

**Four corruptions, each a different thing going wrong.**

* `MALFORMED_RECORD` — records that violate the format: a field missing, a field too many, a value
  that is not a number, a timestamp that is not a timestamp, a field left empty. Five damage kinds,
  cycled, so a corpus exercises all of them rather than the first one many times.
* `OUT_OF_RANGE` — values that are numbers and are physically impossible: ten times the top of the
  instrument's span, far below its bottom, and the two non-finite floats a parser will happily
  hand you if you let it.
* `TRUNCATED` — the file stops early, and the last line stops mid-field. That is what a half-written
  file actually looks like; a clean cut at a line boundary is the easy case and would not test the
  hard one.
* `POISONED_BASELINE` — nothing malformed at all. A slow bias is walked into one column across the
  *fitting* window only, small enough to read as ordinary calibration drift, so that what Atlas
  learns as normal is wrong before it ever sees an attack. This is the one that produces no error
  anywhere and is by far the most dangerous.

**The header is left intact, deliberately.** A corrupted header means the file does not load at
all, which is a real failure but a loud and easily handled one. Leaving it intact keeps the corpus
loadable and puts the question where it belongs: what does Atlas do with the *records* it cannot
trust, in a file it otherwise can.

**Nothing here draws a random number.** Affected rows are chosen by stride, so a corruption is
reproducible from the plan alone and two runs of the same config produce byte-identical rubbish.
"""

import logging
import math
from collections.abc import Sequence
from typing import Final

from phos.synth.attacks.spec import AttackType, HostileGroundTruth, HostilePlan
from phos.synth.plant import PlantDescription

__all__ = [
    "MALFORMED_KINDS",
    "apply_hostile",
]

logger = logging.getLogger(__name__)

MALFORMED_KINDS: Final = (
    "missing_field",
    "extra_field",
    "non_numeric_value",
    "broken_timestamp",
    "empty_field",
)
"""The damage a malformed record can carry, cycled across the affected rows so every kind appears
in any corpus that has more than a handful of them."""

_POISON_BIAS: Final = 0.04
"""How far a poisoned column is walked, as a share of the instrument's span. Small enough to sit
inside what a slow calibration drift would plausibly do, which is exactly why it is dangerous: it
raises no alarm and moves the learned baseline anyway."""

_TIMESTAMP_COLUMN: Final = 0
_LABEL_COLUMN: Final = 1
_FIRST_SIGNAL_COLUMN: Final = 2
"""The prepared-corpus shape D1 established: a timestamp, a label, then one column per signal."""


def apply_hostile(
    lines: Sequence[str], plan: HostilePlan, description: PlantDescription
) -> tuple[tuple[str, ...], HostileGroundTruth]:
    """Corrupt a written corpus and record exactly what was done to it.

    Args:
        lines: The corpus as text lines, header first. Text rather than parsed fields because two
            of these corruptions — a record with the wrong number of fields, and a file that stops
            mid-field — cannot be expressed as parsed fields at all.
        plan: Which corruption to apply, and how much of the file it touches.
        description: The plant, whose declared spans decide what counts as physically impossible.

    Returns:
        ``(corrupted lines, ground truth)``. The ground truth carries no attack interval and there
        is no method on it that would produce one.

    Raises:
        ValueError: If the corpus has no data rows, or if the plan names a column the corpus does
            not carry.
    """
    if len(lines) < 2:
        raise ValueError(
            f"input-hostile case {plan.attack_id!r} has nothing to corrupt: the corpus holds a "
            "header and no data rows"
        )
    corrupted, affected, what = _CORRUPTIONS[plan.type](lines, plan, description)
    logger.debug(
        "applied %s to %d of %d row(s) for %s",
        plan.type.value,
        affected,
        len(lines) - 1,
        plan.attack_id,
    )
    return corrupted, HostileGroundTruth(
        attack_id=plan.attack_id,
        type=plan.type,
        target=plan.target,
        description=what,
        rows_affected=affected,
    )


def _column_of(lines: Sequence[str], plan: HostilePlan) -> int:
    """Return the index of the column a plan names.

    Raises:
        ValueError: If the corpus does not carry it. Silently corrupting the wrong column would
            produce ground truth that names a signal nothing happened to.
    """
    header = lines[0].split(",")
    if plan.target not in header:
        raise ValueError(
            f"input-hostile case {plan.attack_id!r} names column {plan.target!r}, which this "
            f"corpus does not carry; it has {', '.join(header)}"
        )
    return header.index(plan.target)


def _affected_rows(row_count: int, fraction: float) -> list[int]:
    """Return which data rows a corruption touches, chosen by stride rather than at random.

    Deterministic by construction: two runs of the same config produce byte-identical rubbish, so
    a result measured on a hostile corpus is reproducible like every other result in PHOS.
    """
    if fraction <= 0.0 or row_count == 0:
        return []
    wanted = max(1, round(row_count * fraction))
    stride = max(1, row_count // wanted)
    return list(range(0, row_count, stride))[:wanted]


def _malformed(
    lines: Sequence[str], plan: HostilePlan, description: PlantDescription
) -> tuple[tuple[str, ...], int, str]:
    """Damage the format of a share of the records, cycling through every kind of damage."""
    rows = list(lines[1:])
    targets = _affected_rows(len(rows), plan.fraction)
    for position, row in enumerate(targets):
        rows[row] = _damage(rows[row], MALFORMED_KINDS[position % len(MALFORMED_KINDS)])
    return (
        (lines[0], *rows),
        len(targets),
        f"{len(targets)} record(s) made malformed, cycling through {', '.join(MALFORMED_KINDS)}; "
        "the header is intact so the corpus still loads and the question is what happens to the "
        "records it cannot trust",
    )


def _damage(row: str, kind: str) -> str:
    """Return one record with one specific thing wrong with it."""
    fields = row.split(",")
    if kind == "missing_field":
        return ",".join(fields[:-1])
    if kind == "extra_field":
        return ",".join([*fields, "0.00000"])
    if kind == "non_numeric_value":
        fields[_FIRST_SIGNAL_COLUMN] = "not-a-number"
        return ",".join(fields)
    if kind == "broken_timestamp":
        fields[_TIMESTAMP_COLUMN] = "2026-13-45T99:99:99"
        return ",".join(fields)
    fields[_FIRST_SIGNAL_COLUMN] = ""
    return ",".join(fields)


def _out_of_range(
    lines: Sequence[str], plan: HostilePlan, description: PlantDescription
) -> tuple[tuple[str, ...], int, str]:
    """Put values in one column that are numbers and are physically impossible."""
    column = _column_of(lines, plan)
    spec = description.signal(plan.target)
    span = spec.high - spec.low
    impossible = (
        f"{spec.high + 10.0 * span:.5f}",
        f"{spec.low - 10.0 * span:.5f}",
        "inf",
        "-inf",
        "nan",
    )
    rows = list(lines[1:])
    targets = _affected_rows(len(rows), plan.fraction)
    for position, row in enumerate(targets):
        fields = rows[row].split(",")
        fields[column] = impossible[position % len(impossible)]
        rows[row] = ",".join(fields)
    return (
        (lines[0], *rows),
        len(targets),
        f"{len(targets)} value(s) of {plan.target} made physically impossible for an instrument "
        f"calibrated {spec.low:g} to {spec.high:g} {spec.unit}, including the two non-finite "
        "floats a float parser will hand you if you let it",
    )


def _truncated(
    lines: Sequence[str], plan: HostilePlan, description: PlantDescription
) -> tuple[tuple[str, ...], int, str]:
    """Cut the tail off the file, leaving the last surviving record stopping mid-field."""
    rows = list(lines[1:])
    # At least one record always survives, so the corpus stays loadable and the question stays
    # "what does a reader do with a bad tail" rather than "what does it do with an empty file".
    removed = min(len(rows) - 1, max(1, round(len(rows) * plan.fraction)))
    kept = rows[: len(rows) - removed]
    # Mid-field, not at a line boundary. A clean cut is the easy case; a half-written final
    # record is what a process killed during a flush actually leaves behind.
    kept[-1] = kept[-1][: max(1, len(kept[-1]) // 2)]
    return (
        (lines[0], *kept),
        removed,
        f"{removed} record(s) removed from the end of the file and the last surviving record cut "
        "mid-field, as a write interrupted part-way through leaves it",
    )


def _poisoned(
    lines: Sequence[str], plan: HostilePlan, description: PlantDescription
) -> tuple[tuple[str, ...], int, str]:
    """Walk a slow bias into one column across the fitting window, and nothing else.

    Nothing is malformed. Every value stays inside the instrument's span and every record parses.
    The corpus is wrong in the one way that raises no error anywhere: what a model fitted on it
    learns as normal is not normal.
    """
    column = _column_of(lines, plan)
    spec = description.signal(plan.target)
    bias = _POISON_BIAS * (spec.high - spec.low)
    rows = list(lines[1:])
    window = round(len(rows) * plan.fraction)
    for row in range(window):
        fields = rows[row].split(",")
        value = float(fields[column]) + bias * (row / window)
        fields[column] = f"{min(max(value, spec.low), spec.high):.5f}"
        rows[row] = ",".join(fields)
    return (
        (lines[0], *rows),
        window,
        f"{plan.target} walked {bias:+.4f} {spec.unit} across the first {window} record(s) — the "
        "fitting window — at a rate a calibration drift would plausibly produce. Nothing is "
        "malformed and nothing raises an error; the baseline learned from this corpus is simply "
        "not the plant's",
    )


_CORRUPTIONS: Final = {
    AttackType.MALFORMED_RECORD: _malformed,
    AttackType.OUT_OF_RANGE: _out_of_range,
    AttackType.TRUNCATED: _truncated,
    AttackType.POISONED_BASELINE: _poisoned,
}
"""One corruption per input-hostile type. A type absent from this table raises at application
rather than producing a corpus that claims a corruption it does not carry."""


def is_finite_row(row: str, column: int) -> bool:
    """Return whether a record's value in one column is a finite number.

    Offered so a test — or D3 — can say what a corrupted corpus contains without re-deriving the
    parsing rules each time.
    """
    fields = row.split(",")
    if column >= len(fields):
        return False
    try:
        return math.isfinite(float(fields[column]))
    except ValueError:
        return False
