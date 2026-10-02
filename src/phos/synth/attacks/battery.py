"""The standard graded battery: what the shipped attack corpora are, and where they are declared.

A D1 dataset is fully described by a plant, a seed, a start, a duration and a sampling rate. An
attack dataset is that plus a list of attacks, and it lives in a committed TOML file for the same
reason: the payload is regenerated rather than stored, so **the config is the corpus**.

`AttackDatasetConfig` extends D1's `DatasetConfig` rather than restating it, so an attack corpus
and a normal one agree by construction about what a run is. It adds exactly two things, and refuses
to hold both at once:

* `attacks` — detection attacks, which act on the plant.
* `hostile` — input-hostile cases, which act on the file.

**Why one corpus may not hold both.** They support claims that must never be swapped, and mixing
them would confound each with the other: a malformed record falling inside a labelled attack window
makes it impossible to say whether a detector missed the attack or choked on the rubbish. Keeping
them in separate corpora means every number measured on either one answers exactly one question.
The types already make the confusion unrepresentable per *case*; this makes it unrepresentable per
*corpus*.

Extra keys are forbidden, inherited from D1: these files are written by hand, and a mistyped field
that was quietly ignored would produce a corpus whose attacks are not the attacks it describes.
"""

import logging
import tomllib
from pathlib import Path
from typing import Final, Self

from pydantic import ValidationError, model_validator

from phos.synth.attacks.spec import AttackFlavour, AttackPlan, HostilePlan
from phos.synth.catalogue import CONFIG_SUFFIX, DatasetConfig

__all__ = [
    "AttackDatasetConfig",
    "load_batteries",
    "load_battery",
]

logger = logging.getLogger(__name__)

_ATTACK_ROLE: Final = "attack"
_HOSTILE_ROLE: Final = "input-hostile"


class AttackDatasetConfig(DatasetConfig):
    """One standard attack dataset, as its committed config declares it.

    Attributes:
        attacks: The detection attacks to inject. Empty for an input-hostile corpus.
        hostile: The input-hostile cases to apply. Empty for a detection corpus.

    Invariants:
        Everything `DatasetConfig` requires, plus: exactly one of the two lists is non-empty,
        every identifier is unique within the corpus, and every plan's flavour matches the list it
        was declared in.
    """

    attacks: tuple[AttackPlan, ...] = ()
    hostile: tuple[HostilePlan, ...] = ()

    @model_validator(mode="after")
    def _check_battery(self) -> Self:
        if bool(self.attacks) == bool(self.hostile):
            raise ValueError(
                f"dataset {self.name!r} must declare either attacks or hostile cases and not "
                "both: a malformed record inside a labelled attack window makes it impossible to "
                "say whether a detector missed the attack or choked on the rubbish, and the two "
                "support claims that must never be swapped"
            )
        identifiers = [plan.attack_id for plan in self.attacks]
        identifiers += [plan.attack_id for plan in self.hostile]
        repeated = sorted({name for name in identifiers if identifiers.count(name) > 1})
        if repeated:
            raise ValueError(
                f"dataset {self.name!r} declares an attack identifier twice: {', '.join(repeated)}"
            )
        return self

    @property
    def flavour(self) -> AttackFlavour:
        """Which of the two claims this corpus can support. Never both."""
        return AttackFlavour.DETECTION if self.attacks else AttackFlavour.INPUT_HOSTILE

    @property
    def expected_role(self) -> str:
        """The ``role`` a config of this flavour should declare, for a reader scanning the files."""
        return _ATTACK_ROLE if self.attacks else _HOSTILE_ROLE


def load_battery(path: Path) -> AttackDatasetConfig:
    """Read one attack dataset config.

    Args:
        path: The TOML file.

    Returns:
        The parsed config.

    Raises:
        ValueError: If the file is not readable as TOML or does not describe an attack dataset.
            Both messages name ``path``, because a config that fails silently produces a corpus
            that silently is not there.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path} is not readable as TOML: {error}") from error
    try:
        return AttackDatasetConfig.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"{path} is not a valid attack dataset config: {error}") from error


def load_batteries(directory: Path) -> tuple[AttackDatasetConfig, ...]:
    """Read every attack dataset config in a directory, in filename order.

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
        raise ValueError(f"no attack dataset configs in {directory}")
    configs = tuple(load_battery(path) for path in paths)
    names = [config.name for config in configs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"{directory} declares a dataset name twice: {', '.join(duplicates)}")
    logger.debug("loaded %d attack dataset config(s) from %s", len(configs), directory)
    return configs
