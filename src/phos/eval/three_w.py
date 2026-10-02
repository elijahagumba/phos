"""3W Petrobras: offshore-well *fault* labels, never cyber-attacks (Session C9 / ADR 0033).

Licence is two-surface confirmed (CC-BY-4.0). Payloads are not fetched in this repository
(``files: []``). This module exists so a later fetch cannot silently collapse classes 1-9
through `default_attack_when` (nonzero => attack).

Invariants:

* Class 0 is normal operation.
* Classes 1-9 are **faults**. Detection of faults is not a cyber claim.
* There is no attack class on this corpus.
* Real / simulated / hand-drawn provenances must stay split when files arrive.
* Not a command corpus.
"""

from __future__ import annotations

from typing import Final, NoReturn

__all__ = [
    "FAULT_CLASSES",
    "FAULT_RECALL_NOT_ATTACK_CAVEAT",
    "NORMAL_CLASS",
    "NOT_A_COMMAND_CORPUS_CAVEAT",
    "PrepareError",
    "is_attack_class",
    "is_fault_class",
    "is_normal_class",
    "prepare_attack_track",
]


NORMAL_CLASS: Final = 0
FAULT_CLASSES: Final[frozenset[int]] = frozenset(range(1, 10))

FAULT_RECALL_NOT_ATTACK_CAVEAT: Final = (
    "3W class labels 1-9 are faults, not cyber-attacks (ADR 0033 / Session C9). Fault recall "
    "must never be quoted as attack recall. Do not collapse them through default_attack_when."
)

NOT_A_COMMAND_CORPUS_CAVEAT: Final = (
    "3W is process/fault telemetry on offshore wells, not a labelled command corpus "
    "(ADR 0040). discover_labelled_command_corpora must stay empty."
)


class PrepareError(ValueError):
    """3W cannot be prepared as an attack corpus, or files are absent."""


def is_normal_class(value: object) -> bool:
    """Return whether a 3W class cell is normal operation (class 0)."""
    return _as_int(value) == NORMAL_CLASS


def is_fault_class(value: object) -> bool:
    """Return whether a 3W class cell is a fault (classes 1-9)."""
    parsed = _as_int(value)
    return parsed is not None and parsed in FAULT_CLASSES


def is_attack_class(value: object) -> bool:
    """3W has no cyber-attack class. Always false."""
    return False


def prepare_attack_track() -> NoReturn:
    """Refuse a cyber-attack Track A. Faults are not attacks."""
    raise PrepareError(FAULT_RECALL_NOT_ATTACK_CAVEAT)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        if number.is_integer():
            return int(number)
    return None
