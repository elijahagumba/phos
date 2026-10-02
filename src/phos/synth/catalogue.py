"""The standard normal datasets: what they are, and where their definitions live.

A dataset the engine produces is fully described by a plant identifier, a seed, a start, a
duration and a sampling rate. Those five things live in a committed TOML file rather than in code,
for the reason the Constitution gives for pinning anything: the payload is regenerated rather than
stored, so the config *is* the dataset. Change the file and you have a different corpus; keep it
and you can reproduce this one on any machine.

**Each plant gets a pair.** A longer run to fit and calibrate on, and a shorter one from a
different seed to measure against. That is how the evaluation harness is used everywhere else in
PHOS — a model may never be scored on data it was fitted on — and shipping the pair means a later
PART does not have to invent a split policy for synthetic data or, worse, quietly not have one.

**Every dataset here is normal.** D1 builds no attacks. What these are for is the baseline: the
thing D2 injects into, and the thing D3 measures a false-positive rate against.
"""

import logging
import tomllib
from datetime import timedelta
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from phos.ontology import UtcDatetime
from phos.synth.plant import RunSpec
from phos.synth.run import PLANT_IDS

__all__ = [
    "CONFIG_SUFFIX",
    "DatasetConfig",
    "load_config",
    "load_configs",
]

logger = logging.getLogger(__name__)

CONFIG_SUFFIX: Final = ".toml"


class DatasetConfig(BaseModel):
    """One standard dataset, as its committed config file declares it.

    Attributes:
        name: Dataset name. Also the directory the payload is written into, so it has to be
            filesystem-safe.
        plant_id: Which plant to run. Checked against the registry at load, not at generation.
        seed: Seeds the plant — its sensor noise and its event schedule.
        traffic_seed: Seeds the capture's timing jitter only. Separate so that regenerating the
            capture with different jitter cannot move a single telemetry reading.
        start: First sample instant, UTC.
        duration_hours: How long to simulate.
        sample_interval_seconds: Spacing between samples, and the integration step.
        role: What the dataset is for — ``"train"`` or ``"holdout"``. Descriptive; nothing in the
            engine branches on it, but a corpus whose purpose is unrecorded gets used for the
            wrong thing.
        note: Why this dataset exists, in a sentence.

    Invariants:
        The plant is one the engine builds, and the name has no path separators in it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    seed: int
    traffic_seed: int = 1
    start: UtcDatetime
    duration_hours: float = Field(gt=0.0)
    sample_interval_seconds: float = Field(gt=0.0)
    role: str = "train"
    note: str = ""

    @model_validator(mode="after")
    def _check_config(self) -> Self:
        if self.plant_id not in PLANT_IDS:
            raise ValueError(
                f"no plant {self.plant_id!r}; phos.synth builds {', '.join(PLANT_IDS)}"
            )
        if "/" in self.name or "\\" in self.name or self.name in {".", ".."}:
            raise ValueError(f"dataset name {self.name!r} is used as a directory name")
        return self

    def run_spec(self) -> RunSpec:
        """Return the run this config describes.

        Raises:
            ValidationError: If the duration and interval do not hold at least one sample.
        """
        return RunSpec(
            seed=self.seed,
            start=self.start,
            duration=timedelta(hours=self.duration_hours),
            sample_interval=timedelta(seconds=self.sample_interval_seconds),
        )


def load_config(path: Path) -> DatasetConfig:
    """Read one dataset config.

    Args:
        path: The TOML file.

    Returns:
        The parsed config.

    Raises:
        ValueError: If the file is not readable as TOML or does not describe a dataset. Both
            messages name ``path``, because a config that fails silently produces a corpus that
            silently is not there.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path} is not readable as TOML: {error}") from error
    try:
        return DatasetConfig.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"{path} is not a valid dataset config: {error}") from error


def load_configs(directory: Path) -> tuple[DatasetConfig, ...]:
    """Read every dataset config in a directory, in filename order.

    Args:
        directory: The directory holding the committed configs.

    Returns:
        The configs, sorted by filename so a generation run is reproducible in its ordering too.

    Raises:
        ValueError: If the directory holds no configs, if any is unreadable, or if two declare the
            same dataset name — which would have the second silently overwrite the first.
    """
    paths = sorted(directory.glob(f"*{CONFIG_SUFFIX}"))
    if not paths:
        raise ValueError(f"no dataset configs in {directory}")
    configs = tuple(load_config(path) for path in paths)
    names = [config.name for config in configs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"{directory} declares a dataset name twice: {', '.join(duplicates)}")
    logger.debug("loaded %d dataset config(s) from %s", len(configs), directory)
    return configs
