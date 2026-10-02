"""Zero-shot Atlas protocol on declared physical roles (ADR 0063).

Fit Mahalanobis on source-plant role vectors. Score HAI role vectors with the
public ungated threshold (3.0) and seed 11. Do not search a threshold on HAI.
Do not overwrite public log names ``hai`` / ``atlas-mahalanobis``.
"""

from __future__ import annotations

from pathlib import Path

from phos.atlas.data.mapping import SHARED_ENTITY_ID
from phos.atlas.multivariate import MahalanobisModel
from phos.eval.datasets import Dataset
from phos.eval.harness import EvalConfig, evaluate
from phos.eval.report import DEFAULT_LOG_PATH, EvaluationReport, append_to_experiment_log
from phos.models.detector import ModelDetector

TRANSFER_CAVEAT = "TRANSFER_IS_PHYSICAL_ROLES_NOT_IDENTICAL_PLANTS"
"""Plants share three documented roles, not a process, a P&ID, or a unit system."""

PHYSICAL_ROLES_DETECTOR_NAME = "atlas-mahalanobis-physical-roles"
ZERO_SHOT_PREFIX = "zero-shot:"
PUBLIC_ALERT_THRESHOLD = 3.0
PUBLIC_SEED = 11


def run_zero_shot(train: Dataset, test: Dataset) -> EvaluationReport:
    """Fit on ``train`` role vectors and score ``test`` without reading its labels.

    The operating point is the public Atlas threshold and seed. HAI is not used
    to choose either.
    """
    aligned_train = _with_shared_entity(train)
    aligned_test = _with_shared_entity(test)
    fitted = MahalanobisModel(name=PHYSICAL_ROLES_DETECTOR_NAME).fit(aligned_train.observations)
    scored = Dataset(
        name=_zero_shot_name(aligned_test.name),
        domain=aligned_test.domain,
        observations=aligned_test.observations,
        attack_intervals=aligned_test.attack_intervals,
        source_note=_transfer_note(aligned_train.name, aligned_test.source_note),
    )
    return evaluate(
        ModelDetector(fitted=fitted),
        scored,
        EvalConfig(alert_threshold=PUBLIC_ALERT_THRESHOLD, seed=PUBLIC_SEED),
    )


def write_zero_shot_log(report: EvaluationReport, path: Path | str = DEFAULT_LOG_PATH) -> None:
    """Append a zero-shot report under its own log names."""
    if not report.dataset_name.startswith(ZERO_SHOT_PREFIX):
        raise ValueError(
            f"refusing to log {report.dataset_name!r}: zero-shot rows must use "
            f"the {ZERO_SHOT_PREFIX!r} prefix so public hai rows stay frozen"
        )
    if report.detector_name in {"atlas-mahalanobis", "model:atlas-mahalanobis"}:
        raise ValueError("refusing to log under the public atlas-mahalanobis name")
    append_to_experiment_log(report, path)


def evaluate_available_transfer(data_root: Path) -> EvaluationReport:
    """Train on BATADAL (and SWaT if present); zero-shot score HAI test."""
    from phos.atlas.data.loaders import load_hai, load_source_train

    train, swat_status = load_source_train(data_root)
    test = load_hai(data_root, split="test")
    tagged = Dataset(
        name="hai-physical-roles",
        domain=test.domain,
        observations=test.observations,
        attack_intervals=test.attack_intervals,
        source_note=(
            f"{test.source_note}; source={train.name}; SWAT_STATUS={swat_status}; {TRANSFER_CAVEAT}"
        ),
    )
    return run_zero_shot(train, tagged)


def _with_shared_entity(dataset: Dataset) -> Dataset:
    """Force every observation onto the shared physical-role entity."""
    observations = [
        observation.model_copy(update={"entity_ids": [SHARED_ENTITY_ID]})
        for observation in dataset.observations
    ]
    return dataset.model_copy(update={"observations": observations})


def _zero_shot_name(name: str) -> str:
    """Prefix a dataset name so it cannot collide with public HAI log rows."""
    if name.startswith(ZERO_SHOT_PREFIX):
        return name
    return f"{ZERO_SHOT_PREFIX}{name}"


def _transfer_note(train_name: str, existing: str) -> str:
    """Attach the transfer caveat without dropping corpus provenance."""
    extra = f"zero-shot source={train_name}; {TRANSFER_CAVEAT}"
    return f"{existing}; {extra}" if existing else extra
