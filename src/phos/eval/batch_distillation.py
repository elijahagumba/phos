"""Join the batch-distillation archives into a labelled CSV the shipped adapter can read.

This is not a second adapter. :class:`phos.eval.LabelledCsvAdapter` still reads one timestamped
CSV; this module is the preparation step ADR 0024 recorded as outstanding. It exists because the
corpus is 119 independent experiments across three modality archives, two label sources that
disagree, and a time-of-day clock with no date — none of which a labelled CSV reader can guess at
load time without silently invalidating the measurement.

Invariants this module upholds:

* **One mixture family.** Only ``ternary_butan-1-ol+propan-2-ol+water`` is prepared. The other
  two recipes are left on disk, unread, so a number computed here cannot be quoted as
  cross-recipe generalisation.
* **Both label sources must call an experiment clean before it is fitted on.** A training file
  whose CSV is all zeros but whose YAML carries ``Anomaly`` or ``ConfirmedAnomaly`` is written to
  a held-out probe corpus, never to the fit set (ADR 0024 decision 5). A missing YAML is treated
  as contaminated: absence of evidence is not evidence of absence.
* **Null tails are dropped by joining on Time**, not by guessing. The ragged label file's extra
  rows have null Time; an inner join cannot turn them into attack rows.
* **Experiments are packed onto a continuous clock with a seam row between them.** Day-scale
  synthetic dates would make :meth:`phos.eval.Dataset.normal_duration` count the voids between
  timelines as normal operation, which would flatter every false-positive rate. A seam row with
  label 0 and no signals breaks labelled-window collapse across independent experiments without
  fabricating a measurement.
* **Only the anomalous phase is positive; blind and recovery are unscored (ADR 0082).** The
  shipped classes are phases of one perturbation response: 0 normal, 1 blind, 2 anomalous, 3
  recovery. Class 2 is written as label ``1``. Classes 1 and 3 are written as
  :data:`UNSCORED_LABEL` (``-1``), which :class:`phos.eval.LabelledCsvAdapter` turns into
  ``Dataset.unscored_intervals`` when the manifest declares ``unscored_label_values``: that time
  is neither a recall target nor normal time. An unknown non-zero class is refused, not guessed.
* **Recall is perturbation recall, never attack recall.** The source note says so, because the
  manipulations were performed by the plant's own operators.
* **A declared recipe step is joined when the operation logs carry one.** ``Executing step``
  events are last-observation-carried-forward onto the 1 Hz clock. That is a plant-published
  register, not a cluster. Jump conditions, warnings, and operator-UI events are not steps.
  Experiments whose logs omit the token are left unrouted rather than guessed.

YAML is inspected by a string check, not parsed. ``pyyaml`` is not a PHOS dependency and the
detection path does not make it one.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Self

import pandas
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ACTUATORS_STEM",
    "DEFAULT_MIXTURE",
    "DEFAULT_MIXTURE_DIRNAME",
    "LABELS_STEM",
    "LOGS_STEM",
    "OPERATING_POINT_FEATURE",
    "PERTURBATION_RECALL_CAVEAT",
    "RECIPE_STEP_FEATURE",
    "SENSORS_STEM",
    "UNSCORED_LABEL",
    "ExperimentRef",
    "JoinSpec",
    "PrepareError",
    "PrepareResult",
    "carry_recipe_steps",
    "default_join_spec",
    "discover_experiments",
    "find_logs_root",
    "find_operation_root",
    "join_experiment",
    "normalise_recipe_step",
    "operating_point_ordinal",
    "pack_frames",
    "parse_executing_steps",
    "prepare_corpus",
    "recipe_step_vocabulary",
    "yaml_declares_anomaly",
]

logger = logging.getLogger(__name__)

DEFAULT_MIXTURE: Final = "ternary_butan-1-ol+propan-2-ol+water"
DEFAULT_MIXTURE_DIRNAME: Final = "batch_dist_ternary_butan-1-ol+propan-2-ol+water"
LABELS_STEM: Final = "00_Batch_Distillation_Plant_M-202210_Timeseries_Label_Anomaly_Metadata"
SENSORS_STEM: Final = "01_Batch_Distillation_Plant_M-202210_Timeseries_Sensors"
ACTUATORS_STEM: Final = "02_Batch_Distillation_Plant_M-202210_Timeseries_Actuators"
LOGS_STEM: Final = "07_Batch_Distillation_Plant_M-202210_Tabular_Operation_Logs"
RECIPE_STEP_FEATURE: Final = "recipe_step"
OPERATING_POINT_FEATURE: Final = "operating_point"
_EXECUTING_STEP: Final = "executing step"
UNSCORED_LABEL: Final = -1
"""Prepared label for rows that are neither positive nor normal (blind and recovery phases)."""

PERTURBATION_RECALL_CAVEAT: Final = (
    "Recall measured on this corpus is perturbation recall, never attack recall: the "
    "manipulations were engineered process perturbations performed by the plant's own "
    "operators, not cyber attacks (ADR 0024 decision 7)."
)

_TRAIN_SPLIT: Final = "train_normal"
_TEST_SPLIT: Final = "test_anormal"
_EXPERIMENT_CSV: Final = re.compile(r"(train_normal|test_anormal)_experiment_(\d+)\.csv$")
_CONFIRMED: Final = re.compile(r"class:\s*ConfirmedAnomaly\b")
_ANOMALY: Final = re.compile(r"class:\s*Anomaly\b")
_TIME_FORMAT: Final = "%H:%M:%S"
_OUTPUT_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M:%S%z"


class PrepareError(RuntimeError):
    """Raised when the corpus cannot be joined as the spec describes it."""


class JoinSpec(BaseModel):
    """How to join the batch-distillation archives into prepared CSVs.

    Attributes:
        mixture: Recipe family prepared. Recorded so a number cannot silently cover three.
        mixture_dirname: Directory name under ``Operation/`` for that family.
        labels_stem: Extracted archive folder that holds per-experiment labels and YAML.
        sensors_stem: Extracted archive folder that holds the 18 process signals.
        actuators_stem: Extracted archive folder that holds the 13 actuator signals.
        logs_stem: Extracted archive folder that holds per-experiment operation logs. Optional
            at prepare time: if the folder is absent, ``recipe_step`` is omitted rather than
            invented.
        recipe_step_column: Column written when executing-step events can be carried onto Time.
        train_output_file: Prepared attack-free training CSV, relative to the dataset directory.
        test_output_file: Prepared labelled test CSV, relative to the dataset directory.
        contaminated_output_file: Training experiments the YAML annotators marked anomalous.
        row_stride: Keep every Nth row, labelled by the most severe label in its block. Recorded
            in the source note whenever it is not 1.
        timestamp_column: Column holding the time-of-day clock in the shipped files.
        label_column: Column holding the per-row label in the shipped files.
        positive_label_values: Shipped classes written as prepared label ``1``. Class 2, the
            anomalous phase (ADR 0082).
        unscored_label_values: Shipped classes written as :data:`UNSCORED_LABEL`. Classes 1 and
            3, the blind and recovery phases (ADR 0082). Class 0 is normal; any other class is
            refused.
        epoch: Packed-clock origin, ISO-8601 UTC. Synthetic, and the source note says so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mixture: str
    mixture_dirname: str
    labels_stem: str
    sensors_stem: str
    actuators_stem: str
    logs_stem: str = LOGS_STEM
    recipe_step_column: str = RECIPE_STEP_FEATURE
    train_output_file: str
    test_output_file: str
    contaminated_output_file: str
    row_stride: int = Field(default=10, ge=1)
    timestamp_column: str = "Time"
    label_column: str = "Label (anomaly)"
    positive_label_values: tuple[int, ...] = (2,)
    unscored_label_values: tuple[int, ...] = (1, 3)
    epoch: str = "1970-01-01T00:00:00+0000"

    @model_validator(mode="after")
    def _check_label_classes(self) -> Self:
        if not self.positive_label_values:
            raise ValueError("positive_label_values is empty; nothing could be detected")
        overlap = set(self.positive_label_values) & set(self.unscored_label_values)
        if overlap:
            raise ValueError(f"label classes are both positive and unscored: {sorted(overlap)}")
        if 0 in self.positive_label_values or 0 in self.unscored_label_values:
            raise ValueError("class 0 is normal operation and cannot be positive or unscored")
        return self


class ExperimentRef(BaseModel):
    """One experiment as it sits on disk, before any join.

    Attributes:
        operating_point: Directory name, e.g. ``operating_point_001``.
        split: ``train_normal`` or ``test_anormal``, taken from the filename.
        experiment: The experiment number as it appears in the filename, e.g. ``001``.
        relative_csv: Path relative to the mixture directory.
        yaml_text: The sibling YAML, or ``None`` when the file is missing.
    """

    model_config = ConfigDict(frozen=True)

    operating_point: str
    split: str
    experiment: str
    relative_csv: str
    yaml_text: str | None = None

    @property
    def yaml_declares_anomaly(self) -> bool:
        """Return whether the YAML side calls this experiment anomalous.

        A missing YAML cannot confirm cleanliness, so it is treated as contaminated.
        """
        if self.yaml_text is None:
            return True
        return yaml_declares_anomaly(self.yaml_text)


class PrepareResult(BaseModel):
    """What preparation wrote, and the counts that make the write auditable."""

    model_config = ConfigDict(frozen=True)

    train_path: Path
    test_path: Path
    contaminated_path: Path
    n_clean_train: int
    n_contaminated_train: int
    n_test: int
    n_train_rows: int
    n_test_rows: int
    n_test_windows: int
    signal_columns: tuple[str, ...]
    source_note: str
    recipe_step_names: tuple[str, ...] = ()
    n_train_recipe_step_rows: int = Field(default=0, ge=0)
    n_test_recipe_step_rows: int = Field(default=0, ge=0)
    n_test_positive_rows: int = Field(default=0, ge=0)
    n_test_unscored_rows: int = Field(default=0, ge=0)
    n_test_unscored_windows: int = Field(default=0, ge=0)


def yaml_declares_anomaly(text: str) -> bool:
    """Return whether a shipped YAML asserts at least one anomaly record.

    Clean files are the two-line form ``anomalies:`` then ``- class: None``. The check is a
    string match on the class tokens ``Anomaly`` and ``ConfirmedAnomaly``, not a YAML parse:
    ``pyyaml`` is not a PHOS dependency (ADR 0024).

    Args:
        text: Contents of a per-experiment YAML file.

    Returns:
        ``True`` when the annotators recorded an anomaly, ``False`` when they recorded none.
    """
    if _CONFIRMED.search(text) is not None:
        return True
    return _ANOMALY.search(text) is not None


def operating_point_ordinal(name: str) -> float:
    """Return the declared operating-point index as a float, e.g. ``operating_point_001`` → 1.0.

    The corpus publishes this in the directory name. It is a routing key, not a process
    signal: pooled comparison models must drop it (see `Dataset.without_features`).
    """
    suffix = name.rsplit("_", 1)[-1]
    try:
        return float(int(suffix))
    except ValueError as error:
        raise PrepareError(f"operating point {name!r} has no integer suffix") from error


def normalise_recipe_step(raw: str) -> str:
    """Return the declared step token, stripped, with ``End``/``END`` folded.

    ``Heat`` and ``Heat1`` stay distinct: the plant published both names. Folding case on
    ``End`` is the one normalisation the files themselves force — the same recipe node is
    logged both ways in one experiment.
    """
    name = raw.strip()
    if not name:
        return ""
    if name.casefold() == "end":
        return "End"
    return name


def parse_executing_steps(text: str) -> list[tuple[str, str]]:
    """Return ``(Time, step)`` pairs from an operation-log CSV body.

    Only rows whose Property token contains ``Executing step`` (after strip, case-insensitive)
    contribute. Jump conditions, warnings, UI clicks, and Python exceptions in the log are
    not a phase register. Blank Time cells are skipped rather than guessed.

    Args:
        text: Contents of one per-experiment operation-log CSV.

    Returns:
        Events in file order. Duplicate clocks are legitimate; :func:`carry_recipe_steps`
        keeps the last write at each clock.
    """
    events: list[tuple[str, str]] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        return events
    for row in reader:
        if len(row) < 3:
            continue
        time = row[0].strip()
        property_name = row[1].strip()
        value = normalise_recipe_step(row[2])
        if not time or not value:
            continue
        if _EXECUTING_STEP not in property_name.casefold():
            continue
        events.append((time, value))
    return events


def recipe_step_vocabulary(events: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """Return the sorted unique step names in ``events``."""
    names = {step for _, step in events if step}
    return tuple(sorted(names))


def carry_recipe_steps(
    row_times: Sequence[str],
    events: Sequence[tuple[str, str]],
    vocabulary: Sequence[str],
) -> list[float]:
    """Carry the last executing-step onto each 1 Hz clock as a 1-based ordinal.

    Times are compared as ``HH:MM:SS`` strings, which is how both the logs and the sensor
    files store them. A row whose clock precedes every event, or whose experiment has no
    executing-step at all, is encoded as ``0`` — **no declared step**, a real register
    value, not a missing measurement. Encoding it as NaN made ``vectorise`` drop those
    timestamps from the phase-conditional fallback and the fallback then learned from the
    8% of the plant that happened to be mid-recipe.

    Args:
        row_times: Experiment timestamps in sensor order.
        events: ``(Time, step)`` from :func:`parse_executing_steps`.
        vocabulary: Sorted unique names; index 0 encodes as ``1.0``. Ordinal ``0`` is
            reserved for "the log did not name a step".

    Returns:
        One float per ``row_times`` entry.
    """
    index = {name: float(position) for position, name in enumerate(vocabulary, start=1)}
    by_time: dict[str, str] = {}
    for time, step in events:
        by_time[time] = step
    ordered = sorted(by_time.items())
    cursor = 0
    current: str | None = None
    carried: list[float] = []
    for time in row_times:
        while cursor < len(ordered) and ordered[cursor][0] <= time:
            current = ordered[cursor][1]
            cursor += 1
        if current is None:
            carried.append(0.0)
        else:
            carried.append(index.get(current, 0.0))
    return carried


def find_logs_root(dataset_dir: Path, spec: JoinSpec) -> Path | None:
    """Return the extracted operation-log archive, or ``None`` when it is not on disk.

    Unlike :func:`find_operation_root`, absence is not a prepare failure. The logs were
    fetched; a tree that has not unpacked them yet still produces the sensor join. Inventing
    a phase to fill the gap is what ADR 0031 forbade.

    Args:
        dataset_dir: Corpus directory.
        spec: Supplies ``logs_stem`` and ``mixture_dirname``.

    Returns:
        The directory named ``logs_stem`` that contains ``mixture_dirname``.

    Raises:
        PrepareError: If more than one such directory exists.
    """
    matches = [
        path
        for path in dataset_dir.rglob(spec.logs_stem)
        if path.is_dir() and (path / spec.mixture_dirname).is_dir()
    ]
    if not matches:
        return None
    if len(matches) > 1:
        found = ", ".join(str(path) for path in matches)
        raise PrepareError(f"multiple extracted archives named {spec.logs_stem!r}: {found}")
    return matches[0]


def find_operation_root(dataset_dir: Path, archive_stem: str) -> Path:
    """Return the extracted archive directory that contains ``Operation/``.

    Searches ``dataset_dir`` recursively so an intake layout that nested the extract under
    ``raw/ex00/`` is found as readily as a fetch that unpacked at the dataset root.

    Args:
        dataset_dir: Corpus directory, typically ``data/batch-distillation``.
        archive_stem: Folder name of the extracted archive, without ``.zip``.

    Returns:
        The directory named ``archive_stem`` that contains ``Operation/``.

    Raises:
        PrepareError: If no such directory exists, or more than one does.
    """
    matches = [
        path
        for path in dataset_dir.rglob(archive_stem)
        if path.is_dir() and (path / "Operation").is_dir()
    ]
    if not matches:
        raise PrepareError(
            f"no extracted archive {archive_stem!r} with an Operation/ directory "
            f"under {dataset_dir}"
        )
    if len(matches) > 1:
        found = ", ".join(str(path) for path in matches)
        raise PrepareError(f"multiple extracted archives named {archive_stem!r}: {found}")
    return matches[0]


def discover_experiments(labels_root: Path, spec: JoinSpec) -> list[ExperimentRef]:
    """Return every experiment of ``spec.mixture_dirname`` under the label archive.

    Args:
        labels_root: Result of :func:`find_operation_root` for the label archive.
        spec: Join configuration; only ``mixture_dirname`` is read here.

    Returns:
        Experiments sorted by operating point and filename, so packing is deterministic.

    Raises:
        PrepareError: If the mixture directory is absent.
    """
    mixture_dir = labels_root / "Operation" / spec.mixture_dirname
    if not mixture_dir.is_dir():
        raise PrepareError(f"mixture directory {mixture_dir} does not exist")

    found: list[ExperimentRef] = []
    for csv_path in sorted(mixture_dir.rglob("*.csv")):
        match = _EXPERIMENT_CSV.search(csv_path.name)
        if match is None:
            continue
        relative = csv_path.relative_to(mixture_dir).as_posix()
        yaml_path = csv_path.with_suffix(".yaml")
        yaml_text = yaml_path.read_text(encoding="utf-8") if yaml_path.is_file() else None
        found.append(
            ExperimentRef(
                operating_point=csv_path.parent.name,
                split=match.group(1),
                experiment=match.group(2),
                relative_csv=relative,
                yaml_text=yaml_text,
            )
        )
    return found


def join_experiment(
    experiment: ExperimentRef,
    spec: JoinSpec,
    sensors_root: Path,
    actuators_root: Path,
    labels_root: Path,
    logs_root: Path | None = None,
    vocabulary: Sequence[str] = (),
) -> pandas.DataFrame:
    """Inner-join sensors, actuators and labels for one experiment on Time.

    Null Time rows — the ragged-file tail — drop out of the join rather than becoming labelled
    attacks. The label column is mapped by :func:`_prepared_label`: the anomalous phase becomes
    ``1``, the blind and recovery phases become :data:`UNSCORED_LABEL`, normal stays ``0``.
    When ``logs_root`` and ``vocabulary`` are supplied, the declared executing-step is carried
    onto the same clock as ``recipe_step``.

    Args:
        experiment: The experiment to join.
        spec: Column names and mixture directory.
        sensors_root: Extracted sensor archive.
        actuators_root: Extracted actuator archive.
        labels_root: Extracted label archive.
        logs_root: Extracted operation-log archive, or ``None`` to omit the register.
        vocabulary: Sorted unique step names used to encode the register.

    Returns:
        A frame with ``Time``, every sensor and actuator column, a ``label`` in
        ``{0, 1, UNSCORED_LABEL}``, and
        optionally ``recipe_step``.

    Raises:
        PrepareError: If a file or required column is missing, or the join is empty.
    """
    sensors = _read_modality(sensors_root, spec, experiment, "sensors")
    actuators = _read_modality(actuators_root, spec, experiment, "actuators")
    labels = _read_modality(labels_root, spec, experiment, "labels")
    if spec.label_column not in labels.columns:
        raise PrepareError(
            f"{experiment.relative_csv}: label column {spec.label_column!r} not found; "
            f"the file has: {', '.join(str(column) for column in labels.columns)}"
        )

    labels = labels[[spec.timestamp_column, spec.label_column]].copy()
    labels["label"] = _prepared_label(labels[spec.label_column], spec, experiment.relative_csv)
    labels = labels.drop(columns=[spec.label_column])

    overlap = (set(sensors.columns) & set(actuators.columns)) - {spec.timestamp_column}
    if overlap:
        raise PrepareError(
            f"{experiment.relative_csv}: sensor and actuator columns collide: {sorted(overlap)}"
        )

    joined = sensors.merge(actuators, on=spec.timestamp_column, how="inner")
    joined = joined.merge(labels, on=spec.timestamp_column, how="inner")
    if joined.empty:
        raise PrepareError(f"{experiment.relative_csv}: inner join on Time produced no rows")
    joined = joined.sort_values(spec.timestamp_column, kind="stable").reset_index(drop=True)
    joined[OPERATING_POINT_FEATURE] = operating_point_ordinal(experiment.operating_point)
    if logs_root is not None and vocabulary:
        joined[spec.recipe_step_column] = _recipe_step_column(
            experiment, spec, logs_root, joined[spec.timestamp_column], vocabulary
        )
    return joined


def _recipe_step_column(
    experiment: ExperimentRef,
    spec: JoinSpec,
    logs_root: Path,
    row_times: pandas.Series,
    vocabulary: Sequence[str],
) -> list[float]:
    """Encode the carried executing-step for one experiment; ``0`` where the log is silent."""
    path = logs_root / spec.mixture_dirname / experiment.relative_csv
    if not path.is_file():
        return [0.0] * len(row_times)
    events = parse_executing_steps(path.read_text(encoding="utf-8", errors="replace"))
    times = [str(value).strip() for value in row_times.tolist()]
    return carry_recipe_steps(times, events, vocabulary)


def _collect_vocabulary(
    logs_root: Path, spec: JoinSpec, experiments: Sequence[ExperimentRef]
) -> tuple[str, ...]:
    """Return the sorted union of executing-step names across ``experiments``."""
    events: list[tuple[str, str]] = []
    for experiment in experiments:
        path = logs_root / spec.mixture_dirname / experiment.relative_csv
        if not path.is_file():
            continue
        events.extend(parse_executing_steps(path.read_text(encoding="utf-8", errors="replace")))
    return recipe_step_vocabulary(events)


def pack_frames(frames: Sequence[pandas.DataFrame], spec: JoinSpec) -> pandas.DataFrame:
    """Remap experiments onto a continuous clock, inserting a seam row between them.

    Each experiment keeps its 1 Hz internal spacing. A seam row one second after the last sample
    carries label 0 and no signal values, so consecutive attack-labelled rows in adjacent
    experiments cannot collapse into one labelled interval. The next experiment starts one second
    after the seam.

    Args:
        frames: Per-experiment frames as :func:`join_experiment` (and optional stride) produced
            them. Must share a column set.
        spec: Supplies the time-of-day column name and the packed-clock epoch.

    Returns:
        One frame with ``timestamp`` (ISO-8601 UTC) and ``label``, signals preserved.

    Raises:
        PrepareError: If a clock runs backwards, or ``frames`` is empty.
    """
    if not frames:
        raise PrepareError("no experiments to pack")

    cursor = pandas.to_datetime(spec.epoch, utc=True)
    packed: list[pandas.DataFrame] = []
    signal_columns = _signal_columns(frames[0], spec)

    for index, frame in enumerate(frames):
        remapped = _remap_clock(frame, spec, cursor)
        if index > 0:
            seam_at = cursor - pandas.Timedelta(seconds=1)
            packed.append(_seam_row(seam_at, remapped.columns.tolist()))
        packed.append(remapped)
        last = pandas.to_datetime(remapped["timestamp"].iloc[-1], utc=True)
        cursor = last + pandas.Timedelta(seconds=2)

    combined = pandas.concat(packed, ignore_index=True)
    ordered = ["timestamp", "label", *signal_columns]
    return combined.loc[:, ordered]


def prepare_corpus(dataset_dir: Path, spec: JoinSpec) -> PrepareResult:
    """Join, pack and write the prepared CSVs for one mixture family.

    Args:
        dataset_dir: Corpus directory containing the extracted archives.
        spec: Which mixture to prepare and where to write the outputs.

    Returns:
        Paths and counts for the three written files.

    Raises:
        PrepareError: If discovery, joining, striding or writing fails.
    """
    labels_root = find_operation_root(dataset_dir, spec.labels_stem)
    sensors_root = find_operation_root(dataset_dir, spec.sensors_stem)
    actuators_root = find_operation_root(dataset_dir, spec.actuators_stem)
    logs_root = find_logs_root(dataset_dir, spec)
    experiments = discover_experiments(labels_root, spec)
    vocabulary = _collect_vocabulary(logs_root, spec, experiments) if logs_root is not None else ()
    if logs_root is None:
        logger.info(
            "%s: operation logs %r not on disk; recipe_step omitted",
            spec.mixture,
            spec.logs_stem,
        )
    elif not vocabulary:
        logger.info(
            "%s: operation logs present but no Executing step events; recipe_step omitted",
            spec.mixture,
        )

    train_clean = [
        item
        for item in experiments
        if item.split == _TRAIN_SPLIT and not item.yaml_declares_anomaly
    ]
    train_dirty = [
        item for item in experiments if item.split == _TRAIN_SPLIT and item.yaml_declares_anomaly
    ]
    test = [item for item in experiments if item.split == _TEST_SPLIT]
    if not train_clean:
        logger.warning("no dual-clean training experiments under %s", spec.mixture_dirname)
    if not test:
        logger.warning("no test experiments under %s", spec.mixture_dirname)

    train_frames = [
        _prepare_experiment(
            item,
            spec,
            sensors_root,
            actuators_root,
            labels_root,
            logs_root,
            vocabulary,
            require_clean=True,
        )
        for item in train_clean
    ]
    dirty_frames = [
        _prepare_experiment(
            item,
            spec,
            sensors_root,
            actuators_root,
            labels_root,
            logs_root,
            vocabulary,
            require_clean=True,
        )
        for item in train_dirty
    ]
    test_frames = [
        _prepare_experiment(
            item,
            spec,
            sensors_root,
            actuators_root,
            labels_root,
            logs_root,
            vocabulary,
            require_clean=False,
        )
        for item in test
    ]

    note = _source_note(
        spec,
        n_clean=len(train_clean),
        n_dirty=len(train_dirty),
        n_test=len(test),
        recipe_step_names=vocabulary,
    )

    train_frame = pack_frames(train_frames, spec) if train_frames else _empty_output_columns()
    dirty_frame = pack_frames(dirty_frames, spec) if dirty_frames else _empty_output_columns()
    test_frame = pack_frames(test_frames, spec) if test_frames else _empty_output_columns()

    train_path = _write_csv(dataset_dir / spec.train_output_file, train_frame)
    dirty_path = _write_csv(dataset_dir / spec.contaminated_output_file, dirty_frame)
    test_path = _write_csv(dataset_dir / spec.test_output_file, test_frame)

    test_labels = test_frame["label"].tolist() if not test_frame.empty else []
    windows = _count_label_runs(test_labels)
    unscored_windows = _count_label_runs(test_labels, UNSCORED_LABEL)
    test_label_values = pandas.to_numeric(pandas.Series(test_labels), errors="coerce")
    n_positive = int((test_label_values == 1).sum())
    n_unscored = int((test_label_values == UNSCORED_LABEL).sum())
    signal_columns = tuple(
        column for column in test_frame.columns if column not in {"timestamp", "label"}
    )
    n_train_routed = _count_routed(train_frame, spec.recipe_step_column)
    n_test_routed = _count_routed(test_frame, spec.recipe_step_column)
    logger.info(
        "prepared %s: %d dual-clean train rows, %d contaminated, %d test rows, %d windows "
        "(%d positive rows), %d unscored windows (%d rows), %d recipe-step names, "
        "%d/%d train rows routed, %d/%d test rows routed",
        spec.mixture,
        len(train_frame),
        len(dirty_frame),
        len(test_frame),
        windows,
        n_positive,
        unscored_windows,
        n_unscored,
        len(vocabulary),
        n_train_routed,
        len(train_frame),
        n_test_routed,
        len(test_frame),
    )
    return PrepareResult(
        train_path=train_path,
        test_path=test_path,
        contaminated_path=dirty_path,
        n_clean_train=len(train_clean),
        n_contaminated_train=len(train_dirty),
        n_test=len(test),
        n_train_rows=len(train_frame),
        n_test_rows=len(test_frame),
        n_test_windows=windows,
        signal_columns=signal_columns,
        source_note=note,
        recipe_step_names=vocabulary,
        n_train_recipe_step_rows=n_train_routed,
        n_test_recipe_step_rows=n_test_routed,
        n_test_positive_rows=n_positive,
        n_test_unscored_rows=n_unscored,
        n_test_unscored_windows=unscored_windows,
    )


def _prepare_experiment(
    experiment: ExperimentRef,
    spec: JoinSpec,
    sensors_root: Path,
    actuators_root: Path,
    labels_root: Path,
    logs_root: Path | None,
    vocabulary: Sequence[str],
    *,
    require_clean: bool,
) -> pandas.DataFrame:
    """Join one experiment and apply the configured stride."""
    joined = join_experiment(
        experiment,
        spec,
        sensors_root,
        actuators_root,
        labels_root,
        logs_root=logs_root,
        vocabulary=vocabulary,
    )
    if require_clean and bool((joined["label"] != 0).any()):
        raise PrepareError(
            f"{experiment.relative_csv}: training split carries "
            f"{int((joined['label'] != 0).sum())} non-normal rows; the CSV is not clean"
        )
    return _stride(joined, spec, experiment.relative_csv)


def _read_modality(
    root: Path,
    spec: JoinSpec,
    experiment: ExperimentRef,
    role: str,
) -> pandas.DataFrame:
    """Read one experiment's CSV from a modality archive, dropping rows with null Time."""
    path = root / "Operation" / spec.mixture_dirname / experiment.relative_csv
    if not path.is_file():
        raise PrepareError(f"{role} file missing for {experiment.relative_csv}: {path}")
    frame = pandas.read_csv(path)
    frame.columns = pandas.Index([str(column).strip() for column in frame.columns])
    if spec.timestamp_column not in frame.columns:
        raise PrepareError(
            f"{path.name}: timestamp column {spec.timestamp_column!r} not found; "
            f"the file has: {', '.join(str(column) for column in frame.columns)}"
        )
    frame = frame.dropna(subset=[spec.timestamp_column]).copy()
    frame[spec.timestamp_column] = frame[spec.timestamp_column].astype(str).str.strip()
    return frame


def _prepared_label(raw: pandas.Series, spec: JoinSpec, origin: str) -> pandas.Series:
    """Map shipped phase classes onto the prepared label (ADR 0082).

    Positive classes become ``1``, unscored classes :data:`UNSCORED_LABEL`, class 0 stays ``0``.
    An unreadable cell is ``0``, as before: the ragged tail never reaches here because the join
    on Time drops it. Any other class is refused rather than guessed.

    Raises:
        PrepareError: If a readable class is neither normal, positive nor unscored.
    """
    numeric = pandas.to_numeric(raw, errors="coerce").fillna(0)
    known = {0, *spec.positive_label_values, *spec.unscored_label_values}
    unknown = sorted({float(value) for value in numeric.unique() if value not in known})
    if unknown:
        raise PrepareError(
            f"{origin}: label classes {unknown} are not mapped; known classes are {sorted(known)}"
        )
    prepared = pandas.Series(0, index=raw.index, dtype=int)
    prepared[numeric.isin(spec.positive_label_values)] = 1
    prepared[numeric.isin(spec.unscored_label_values)] = UNSCORED_LABEL
    return prepared


def _stride(frame: pandas.DataFrame, spec: JoinSpec, origin: str) -> pandas.DataFrame:
    """Keep every Nth row, labelling it by the most severe label in the block it stands for.

    Each kept row represents the ``row_stride`` seconds that start at it. Its label is positive
    if any second in that block is positive, otherwise unscored if any second is unscored,
    otherwise normal (ADR 0082). Sampling the kept row's own label instead would let a run
    shorter than the stride fall between samples: 33 of 69 blind-phase runs in the prepared
    mixture are under ten seconds, and their time would be counted as normal. Pooling cannot
    erase a window. It can merge two runs of one class that sit less than a stride apart, or
    fold a short unscored run into an adjacent positive block, so window counts can fall.
    """
    if spec.row_stride == 1:
        return frame
    labels = frame["label"].to_numpy()
    before = _count_label_runs(labels.tolist())
    before_unscored = _count_label_runs(labels.tolist(), UNSCORED_LABEL)
    severity = pandas.Series(labels).map({0: 0, UNSCORED_LABEL: 1, 1: 2}).fillna(0)
    pooled = severity.groupby(severity.index // spec.row_stride).max()
    strided = frame.iloc[:: spec.row_stride].reset_index(drop=True)
    strided["label"] = pooled.map({0: 0, 1: UNSCORED_LABEL, 2: 1}).astype(int).to_numpy()
    after = _count_label_runs(strided["label"].tolist())
    after_unscored = _count_label_runs(strided["label"].tolist(), UNSCORED_LABEL)
    logger.info(
        "  strided  %s every %dth row, block-pooled: positive windows %d -> %d, "
        "unscored windows %d -> %d",
        origin,
        spec.row_stride,
        before,
        after,
        before_unscored,
        after_unscored,
    )
    return strided


def _remap_clock(
    frame: pandas.DataFrame, spec: JoinSpec, start: pandas.Timestamp
) -> pandas.DataFrame:
    """Rewrite the time-of-day column onto a packed UTC clock beginning at ``start``."""
    parsed = pandas.to_datetime(frame[spec.timestamp_column], format=_TIME_FORMAT)
    deltas = parsed - parsed.iloc[0]
    if pandas.notna(deltas.min()) and deltas.min() < pandas.Timedelta(0):
        raise PrepareError("experiment clock runs backwards")
    stamps = start + deltas
    remapped = frame.drop(columns=[spec.timestamp_column]).copy()
    remapped.insert(0, "timestamp", stamps.dt.strftime(_OUTPUT_TIME_FORMAT))
    return remapped


def _seam_row(timestamp: pandas.Timestamp, columns: Sequence[str]) -> pandas.DataFrame:
    """Return one labelled-normal row with no signal values, to break interval collapse."""
    row: dict[str, object] = dict.fromkeys(columns, pandas.NA)
    row["timestamp"] = timestamp.strftime(_OUTPUT_TIME_FORMAT)
    row["label"] = 0
    return pandas.DataFrame([row])


def _signal_columns(frame: pandas.DataFrame, spec: JoinSpec) -> list[str]:
    """Return value columns, excluding the time-of-day clock and the binary label."""
    reserved = {spec.timestamp_column, "timestamp", "label", spec.label_column}
    return [str(column) for column in frame.columns if str(column) not in reserved]


def _empty_output_columns() -> pandas.DataFrame:
    """Return an empty prepared frame so a missing split still writes a stable header."""
    return pandas.DataFrame(columns=["timestamp", "label"])


def _write_csv(path: Path, frame: pandas.DataFrame) -> Path:
    """Write ``frame`` and return ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def _source_note(
    spec: JoinSpec,
    *,
    n_clean: int,
    n_dirty: int,
    n_test: int,
    recipe_step_names: Sequence[str] = (),
) -> str:
    """Return the provenance string copied onto every report this corpus produces."""
    stride = (
        f"downsampled to every {spec.row_stride}th row with block-pooled labels"
        if spec.row_stride > 1
        else "full 1 Hz resolution"
    )
    phase = (
        f" recipe_step carried from operation-log Executing step events "
        f"({len(recipe_step_names)} declared names: {', '.join(recipe_step_names)})."
        if recipe_step_names
        else " No declared Executing step register was joined."
    )
    return (
        f"batch-distillation v1.1.2 (Zenodo record 21535243), mixture {spec.mixture}, "
        f"{n_clean} dual-clean train experiments / {n_dirty} YAML-contaminated train "
        f"held out / {n_test} test experiments, {stride}, packed clock from {spec.epoch} "
        f"with a labelled-normal seam row between experiments.{phase} Label: shipped classes "
        f"{list(spec.positive_label_values)} (anomalous phase) are positive; "
        f"{list(spec.unscored_label_values)} (blind, recovery) are unscored, neither recall "
        f"target nor normal time (ADR 0082). {PERTURBATION_RECALL_CAVEAT}"
    )


def _count_routed(frame: pandas.DataFrame, column: str) -> int:
    """Return how many rows carry a named executing-step (ordinal ≥ 1), not the 0 sentinel."""
    if column not in frame.columns or frame.empty:
        return 0
    numeric = pandas.to_numeric(frame[column], errors="coerce")
    return int((numeric >= 1.0).sum())


def _count_label_runs(labels: Sequence[object], value: int = 1) -> int:
    """Return the number of maximal runs of ``value`` in ``labels``."""
    target = {str(value), f"{float(value)}"}
    runs = 0
    previous = False
    for cell in labels:
        current = str(cell).strip() in target
        if current and not previous:
            runs += 1
        previous = current
    return runs


def default_join_spec() -> JoinSpec:
    """Return the join spec pinned for the first baseline (ADR 0024 decision 6)."""
    return JoinSpec(
        mixture=DEFAULT_MIXTURE,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        labels_stem=LABELS_STEM,
        sensors_stem=SENSORS_STEM,
        actuators_stem=ACTUATORS_STEM,
        train_output_file="batch-distillation-train-prepared.csv",
        test_output_file="batch-distillation-test-prepared.csv",
        contaminated_output_file="batch-distillation-contaminated-train-prepared.csv",
        row_stride=10,
    )
