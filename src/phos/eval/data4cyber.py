"""Join Data4Cyber scenario CSVs into a labelled table the shipped adapter can read.

This is Track A — process telemetry — not a command corpus. The packet captures stay unread.
``LabelledCsvAdapter`` is not extended. Preparation exists because the shipped files mix the
answer into extra columns (``attack_phase``, ``Attacker.*``) and because ``attack_active`` is a
boolean process-phase flag, including reconnaissance, not a command-action window.

Invariants this module upholds:

* **Fit only on S0.** The benign baseline must be attack-free. A True in ``attack_active`` there
  is contamination, not training data.
* **The plant is S0's instrumented grid.** Value columns are S0's process signals. Extra columns
  on a test scenario (attacker copies, MQTT event, multi-label phase) are dropped, never fitted.
* **Leak columns never become signals.** Named leaks and any ``Attacker.*`` column are excluded
  even if they happen to parse as numeric.
* **Reconnaissance stays labelled.** ``attack_active`` is used as shipped. Recon seconds are
  counted in the result so a recall figure cannot pretend they were held out.
* **Recall is process-phase recall, not command recall.** The source note says so.
* **False-positives-per-normal-hour is not a control-room budget.** Aggregate normal time is
  about 1.6 hours and S0 itself is about 30 minutes (ADR 0033 / 0040).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import pandas
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FP_HOUR_RULER_CAVEAT",
    "LEAK_COLUMNS",
    "NOT_A_COMMAND_CORPUS_CAVEAT",
    "PROCESS_PHASE_RECALL_CAVEAT",
    "Data4CyberPrepareSpec",
    "PrepareError",
    "PrepareResult",
    "default_prepare_spec",
    "is_attack_active",
    "is_leak_column",
    "is_reconnaissance_phase",
    "prepare_corpus",
    "process_columns",
]

logger = logging.getLogger(__name__)

LEAK_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "attack_active",
        "attack_phase",
        "attack_phase_all",
        "Attacker.event",
        "Attacker.new_value",
        "Attacker.old_value",
        "MQTT-Price-Signal.event",
    }
)

NOT_A_COMMAND_CORPUS_CAVEAT: Final = (
    "Not a labelled command corpus (ADR 0040): attack_active and attack_phase are 1 Hz "
    "process phases, not command-action windows. discover_labelled_command_corpora must "
    "stay empty. Do not copy attack-phases.json clocks onto pcapng."
)

FP_HOUR_RULER_CAVEAT: Final = (
    "Do not quote a Data4Cyber false-positives-per-normal-hour figure as a control-room "
    "budget: aggregate normal CSV time is 5880 seconds (~1.6 h) and S0 is ~30 minutes "
    "(ADR 0033 / 0040)."
)

PROCESS_PHASE_RECALL_CAVEAT: Final = (
    "Recall measured here is process-phase recall on attack_active as shipped, including "
    "reconnaissance seconds. It is not command-action recall and not a field detection rate."
)

_SOURCE_NOTE: Final = (
    "data4cyber Zenodo 19965384 Track A: fit on S0_benign_baseline, score "
    "S1_industroyer_pv. "
    + PROCESS_PHASE_RECALL_CAVEAT
    + " "
    + NOT_A_COMMAND_CORPUS_CAVEAT
    + " "
    + FP_HOUR_RULER_CAVEAT
)


class PrepareError(RuntimeError):
    """Raised when Data4Cyber cannot be prepared as Track A process telemetry."""


class Data4CyberPrepareSpec(BaseModel):
    """How to turn two scenario folders into prepared train/test CSVs.

    Attributes:
        dataset_root: Extracted zip folder under the dataset directory.
        train_scenario: Folder that must be attack-free (S0).
        test_scenario: Folder scored as the labelled test (default S1).
        train_output_file: Prepared attack-free CSV, relative to the dataset directory.
        test_output_file: Prepared labelled test CSV, relative to the dataset directory.
        timestamp_column: Column holding the row clock in the shipped files.
        label_column: Column holding ``attack_active``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_root: str = "data4cyber_dataset"
    train_scenario: str = "S0_benign_baseline"
    test_scenario: str = "S1_industroyer_pv"
    train_output_file: str = "data4cyber-s0-train-prepared.csv"
    test_output_file: str = "data4cyber-s1-test-prepared.csv"
    timestamp_column: str = "timestamp"
    label_column: str = "attack_active"


class PrepareResult(BaseModel):
    """What preparation wrote, and the counts that make the write auditable."""

    model_config = ConfigDict(frozen=True)

    train_path: Path
    test_path: Path
    signal_columns: tuple[str, ...]
    n_train_rows: int = Field(ge=0)
    n_test_rows: int = Field(ge=0)
    n_test_attack_rows: int = Field(ge=0)
    n_reconnaissance_rows: int = Field(ge=0)
    n_test_windows: int = Field(ge=0)
    n_signals: int = Field(ge=0)
    source_note: str


def default_prepare_spec() -> Data4CyberPrepareSpec:
    """Return the campaign default: S0 fit, S1 score, one grid, not a packed plant."""
    return Data4CyberPrepareSpec()


def is_attack_active(value: object) -> bool:
    """Return whether a shipped ``attack_active`` cell is True.

    Pandas reads the column as bool on the real files. Tests also pass the strings ``True`` /
    ``true`` / ``1``. Anything else, including the phase token ``normal``, is not an attack.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    text = str(value).strip().lower()
    return text in {"true", "1"}


def is_reconnaissance_phase(value: object) -> bool:
    """Return whether ``attack_phase`` names a reconnaissance window."""
    return "reconnaissance" in str(value).strip().lower()


def is_leak_column(name: str) -> bool:
    """Return whether ``name`` is an answer-copy or attacker channel, never a plant signal."""
    if name in LEAK_COLUMNS:
        return True
    return name.startswith("Attacker.")


def process_columns(header: Sequence[str]) -> list[str]:
    """Return S0-style process columns: everything that is not time, label, or a leak."""
    skipped = {"timestamp", "attack_active"}
    return [name for name in header if name not in skipped and not is_leak_column(name)]


def _require_columns(frame: pandas.DataFrame, names: Sequence[str], *, source: Path) -> None:
    present = [str(column) for column in frame.columns]
    missing = [name for name in names if name not in present]
    if missing:
        raise PrepareError(
            f"{source}: missing columns {missing}; the file has: {', '.join(present[:24])}"
        )


def _labels(frame: pandas.DataFrame, column: str) -> pandas.Series:
    return frame[column].map(is_attack_active).astype(int)


def _prepared_frame(
    frame: pandas.DataFrame,
    *,
    timestamp_column: str,
    labels: pandas.Series,
    signals: Sequence[str],
) -> pandas.DataFrame:
    timestamps = pandas.to_datetime(frame[timestamp_column], utc=True)
    numeric = frame.loc[:, list(signals)].apply(pandas.to_numeric, errors="coerce")
    prepared = pandas.concat(
        [
            pandas.DataFrame(
                {
                    "timestamp": timestamps.dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "label": labels.to_numpy(),
                }
            ),
            numeric.reset_index(drop=True),
        ],
        axis=1,
    )
    sorted_frame = prepared.sort_values("timestamp", kind="stable")
    if not isinstance(sorted_frame, pandas.DataFrame):
        raise PrepareError("prepared frame sort did not return a DataFrame")
    return sorted_frame


def _count_label_runs(labels: Sequence[object]) -> int:
    runs = 0
    previous = 0
    for value in labels:
        current = 1 if value == 1 else 0
        if current == 1 and previous != 1:
            runs += 1
        previous = current
    return runs


def prepare_corpus(dataset_dir: Path, spec: Data4CyberPrepareSpec) -> PrepareResult:
    """Write attack-free train and labelled test CSVs from two scenario folders.

    Raises:
        PrepareError: If a source is missing, S0 is not attack-free, a required plant
            column is absent from the test scenario, or no numeric signals survive.
    """
    root = dataset_dir / spec.dataset_root
    train_source = root / spec.train_scenario / "dataset.csv"
    test_source = root / spec.test_scenario / "dataset.csv"
    if not train_source.is_file():
        raise PrepareError(f"cannot prepare {spec.train_output_file}: {train_source} is missing")
    if not test_source.is_file():
        raise PrepareError(f"cannot prepare {spec.test_output_file}: {test_source} is missing")

    train_frame = pandas.read_csv(train_source)
    test_frame = pandas.read_csv(test_source)
    _require_columns(
        train_frame,
        (spec.timestamp_column, spec.label_column),
        source=train_source,
    )
    _require_columns(
        test_frame,
        (spec.timestamp_column, spec.label_column),
        source=test_source,
    )

    signals = process_columns([str(column) for column in train_frame.columns])
    if not signals:
        raise PrepareError(f"{train_source}: no process columns survived leak exclusion")
    missing_on_test = [name for name in signals if name not in test_frame.columns]
    if missing_on_test:
        raise PrepareError(
            f"{test_source}: test scenario is missing S0 plant columns {missing_on_test}"
        )

    train_labels = _labels(train_frame, spec.label_column)
    if int(train_labels.sum()) != 0:
        raise PrepareError(
            f"{train_source}: {spec.train_scenario} must be attack-free; "
            f"found {int(train_labels.sum())} attack_active rows"
        )
    test_labels = _labels(test_frame, spec.label_column)
    if "attack_phase" in test_frame.columns:
        recon = int(test_frame["attack_phase"].map(is_reconnaissance_phase).sum())
    else:
        recon = 0

    train_prepared = _prepared_frame(
        train_frame,
        timestamp_column=spec.timestamp_column,
        labels=train_labels,
        signals=signals,
    )
    test_prepared = _prepared_frame(
        test_frame,
        timestamp_column=spec.timestamp_column,
        labels=test_labels,
        signals=signals,
    )
    if list(train_prepared.columns) != list(test_prepared.columns):
        raise PrepareError("prepared train and test must carry identical columns")

    train_path = dataset_dir / spec.train_output_file
    test_path = dataset_dir / spec.test_output_file
    train_prepared.to_csv(train_path, index=False)
    test_prepared.to_csv(test_path, index=False)
    windows = _count_label_runs(test_prepared["label"].tolist())
    logger.info(
        "  prepared data4cyber Track A: train %d rows, test %d rows (%d attack, %d recon), "
        "%d signals; FP/hour is not a control-room budget",
        len(train_prepared),
        len(test_prepared),
        int(test_labels.sum()),
        recon,
        len(signals),
    )
    return PrepareResult(
        train_path=train_path,
        test_path=test_path,
        signal_columns=tuple(signals),
        n_train_rows=len(train_prepared),
        n_test_rows=len(test_prepared),
        n_test_attack_rows=int(test_labels.sum()),
        n_reconnaissance_rows=recon,
        n_test_windows=windows,
        n_signals=len(signals),
        source_note=_SOURCE_NOTE,
    )
