#!/usr/bin/env python3
"""Regenerate the v1 records that are computations, then check every pin (ADR 0268).

The default command runs the G1 table, including its grouped block, then
``--compare`` on the A2 and consistency producers. Each of those writes only when
the recompute equals the committed file, or, for ``--compare``, does not write
at all. A mismatch is the result. The command then checks each pinned file's
sha256 and digits. A passing check says ``record intact``. ``--check-only``
skips every recompute and opens no corpus.

The benchmark file is not regenerated. Its headline numbers are cited constants.
This command does not write an evaluation log and does not open CERT.

Usage::

    uv run python scripts/reproduce_v1.py
    uv run python scripts/reproduce_v1.py --check-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
PIN_RELATIVE: Final = "eval_runs/build/v1/tools/reproduce-pin.json"
SCHEMA: Final = 1
#: Producers the default command runs, in order. The benchmark script is not here:
#: it cites frozen constants and does not recompute them (ADR 0268).
RECOMPUTE: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("scripts/measure_baseline_table.py", ()),
    ("scripts/measure_a2_status.py", ("--compare",)),
    ("scripts/measure_consistency_batadal.py", ("--compare",)),
    ("scripts/measure_consistency_identity.py", ("--compare",)),
)

# Result files only. A path under data/ is refused before it is opened.
_DATA_PREFIX: Final = "data/"
_RECORD_PREFIX: Final = "eval_runs/"
_VALIDATION_PREFIXES: Final = (
    "data/hai-21.03",
    "data/hai-22.04",
    "data/hai-23.05",
    "data/batadal",
    "data/hai/",
)


@dataclass(frozen=True)
class PinnedRecord:
    """One committed result file and the digits this command checks.

    Attributes:
        path: Path relative to the checkout. Must sit under ``eval_runs/``.
        sha256: Hex digest of the file's bytes.
        digits: JSON pointer to the canonical digit string pinned from the record.
    """

    path: str
    sha256: str
    digits: Mapping[str, str]


@dataclass(frozen=True)
class Check:
    """One row of the pass or fail table.

    Attributes:
        record: The relative path that was checked.
        status: ``record intact`` or ``fail``.
        detail: Why the row passed or which digit did not match.
    """

    record: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        """Whether this row matched the pin."""
        return self.status == "record intact"


def canonical_digit(value: object) -> str:
    """Render one recorded number the way the pin stores it.

    Args:
        value: An integer or a float from a result JSON file.

    Returns:
        A stable decimal string. Integers have no decimal point.

    Raises:
        TypeError: If ``value`` is not an integer or a float.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"pinned digit is not a number: {value!r}")
    if isinstance(value, int):
        return str(value)
    return format(value, ".12g")


def lookup(node: object, pointer: str) -> object:
    """Walk a pointer such as ``rows[corpus=hai-20.07].consistency_caught``.

    A dotted name descends into an object. ``[field=value]`` selects the object in a list whose
    field equals that value, and a following selector narrows the same list when several rows
    match. ``[0]`` selects by index.

    Args:
        node: Parsed JSON.
        pointer: The path named in the pin.

    Returns:
        The value at that path.

    Raises:
        KeyError: If a step does not match.
    """
    index = 0
    length = len(pointer)
    while index < length:
        if pointer[index] == ".":
            index += 1
            continue
        if pointer[index] == "[":
            end = pointer.index("]", index)
            matches = _select(node, pointer[index + 1 : end], pointer)
            index = end + 1
            if index < length and pointer[index] == "[":
                node = matches
                continue
            if len(matches) != 1:
                raise KeyError(pointer)
            node = matches[0]
            continue
        end = index
        while end < length and pointer[end] not in ".[":
            end += 1
        key = pointer[index:end]
        index = end
        if not isinstance(node, dict) or key not in node:
            raise KeyError(pointer)
        node = node[key]
    return node


def load_pin(path: Path) -> tuple[PinnedRecord, ...]:
    """Read the pinned copy of the recorded digits.

    Args:
        path: The pin JSON.

    Returns:
        One record per file the command checks.

    Raises:
        ValueError: If the pin is the wrong schema or a record is malformed.
        OSError: If the pin cannot be read.
        json.JSONDecodeError: If the pin is not JSON.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {raw.get('schema') if isinstance(raw, dict) else None}")
    records = raw.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError(f"{path}: no records")
    loaded: list[PinnedRecord] = []
    for item in records:
        loaded.append(_pinned(item))
    return tuple(loaded)


def check_records(root: Path, records: Sequence[PinnedRecord]) -> tuple[Check, ...]:
    """Check each pinned record. Do not rescore.

    Args:
        root: Checkout root. Only paths under ``eval_runs/`` are opened.
        records: The pin.

    Returns:
        One check per record, in pin order. A match says ``record intact``.
    """
    return tuple(_check_one(root, record) for record in records)


def render_table(results: Sequence[Check]) -> str:
    """Render the pass or fail table.

    Args:
        results: Rows from `check_records`.

    Returns:
        A header and one tab-separated line per record.
    """
    lines = ["status\trecord\tdetail"]
    for item in results:
        detail = item.detail.replace("\t", " ").replace("\n", " ")
        lines.append(f"{item.status}\t{item.record}\t{detail}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print the table and return 0 only when every checked digit matches.

    Args:
        argv: Arguments, excluding the program name. ``None`` reads ``sys.argv``.

    Returns:
        ``0`` when every producer matched and every row is ``record intact``. A producer's
        non-zero status is returned after the pin table is printed. ``1`` when a digit or
        checksum does not match. ``2`` when the pin itself cannot be read.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate computed v1 records, then check pinned digits."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pin", type=Path, default=None)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="check the pin without opening a corpus",
    )
    args = parser.parse_args(argv)
    recompute_status = 0
    if not args.check_only and args.pin is None and args.root.resolve() == ROOT.resolve():
        recompute_status = _recompute()
    pin_path = args.pin if args.pin is not None else args.root / PIN_RELATIVE
    try:
        results = check_records(args.root, load_pin(pin_path))
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as error:
        sys.stderr.write(f"{error}\n")
        return 2
    sys.stdout.write(render_table(results))
    if recompute_status != 0:
        return recompute_status
    return 0 if all(item.ok for item in results) else 1


def _recompute() -> int:
    """Run each producer. Keep going after a mismatch so every record is reported.

    Returns:
        ``0`` when every producer matched. Otherwise the first non-zero status.
    """
    status = 0
    for script, extra in RECOMPUTE:
        completed = subprocess.run(
            [sys.executable, str(ROOT / script), *extra],
            cwd=ROOT,
            check=False,
        )
        if completed.returncode != 0 and status == 0:
            status = completed.returncode
    return status


def _pinned(item: object) -> PinnedRecord:
    if not isinstance(item, dict):
        raise ValueError("a pin record must be an object")
    path = item.get("path")
    digest = item.get("sha256")
    digits = item.get("digits")
    if not isinstance(path, str) or not path:
        raise ValueError("a pin record needs a path")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{path}: sha256 must be 64 hex characters")
    if not isinstance(digits, dict):
        raise ValueError(f"{path}: digits must be an object")
    rendered: dict[str, str] = {}
    for key, value in digits.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"{path}: each digit is a string")
        rendered[key] = value
    return PinnedRecord(path, digest, rendered)


def _check_one(root: Path, record: PinnedRecord) -> Check:
    refused = _refuse(record.path)
    if refused is not None:
        return Check(record.path, "fail", refused)
    path = root / record.path
    if not path.is_file():
        return Check(record.path, "fail", "record missing")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    problems: list[str] = []
    if digest != record.sha256:
        problems.append(f"sha256 recorded {digest} != pinned {record.sha256}")
    if record.digits:
        problems.extend(_digit_problems(path, record))
    if problems:
        return Check(record.path, "fail", "; ".join(problems))
    if record.digits:
        count = len(record.digits)
        noun = "digit matches" if count == 1 else "digits match"
        detail = f"sha256 ok; {count} {noun}"
    else:
        detail = "sha256 ok"
    return Check(record.path, "record intact", detail)


def _digit_problems(path: Path, record: PinnedRecord) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"record is not JSON: {error}"]
    problems: list[str] = []
    for pointer, pinned in record.digits.items():
        try:
            found = lookup(payload, pointer)
            got = canonical_digit(found)
        except (KeyError, TypeError, ValueError) as error:
            problems.append(f"{pointer}: {error}")
            continue
        if got != pinned:
            problems.append(f"{pointer}: recorded {got} != pinned {pinned}")
    return problems


def _refuse(relative: str) -> str | None:
    if relative.startswith("/") or ".." in Path(relative).parts:
        return "refused: path escapes the checkout"
    normalised = Path(relative).as_posix()
    for prefix in _VALIDATION_PREFIXES:
        bare = prefix.rstrip("/")
        if normalised == bare or normalised.startswith(prefix):
            return "refused: validation corpus is not opened"
    if normalised.startswith(_DATA_PREFIX):
        return "refused: data files are not opened"
    if not normalised.startswith(_RECORD_PREFIX):
        return "refused: records must sit under eval_runs/"
    return None


def _select(node: object, selector: str, pointer: str) -> list[object]:
    if not isinstance(node, list):
        raise KeyError(pointer)
    if selector.isdigit():
        return [node[int(selector)]]
    if "=" not in selector:
        raise KeyError(pointer)
    field, value = selector.split("=", 1)
    matches: list[object] = [
        item for item in node if isinstance(item, dict) and str(item.get(field)) == value
    ]
    if not matches:
        raise KeyError(pointer)
    return matches


if __name__ == "__main__":
    raise SystemExit(main())
