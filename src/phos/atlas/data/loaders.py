"""Plant CSV loaders for the declared physical-role protocol (ADR 0063).

BATADAL and HAI read licence-confirmed prepared files already on disk. SWaT
is form-gated in the registry: this module refuses when the files are absent
and never downloads them.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from phos.atlas.data.mapping import (
    BATADAL_PHYSICAL_ROLES,
    HAI_PHYSICAL_ROLES,
    SHARED_ENTITY_ID,
    SWAT_PHYSICAL_ROLES,
    RoleMap,
    concatenate_role_datasets,
    mapped_tags,
    project_to_physical_roles,
    require_tags_present,
)
from phos.eval.datasets import Dataset, LabelledCsvAdapter
from phos.ontology import Domain

SWAT_FORM_GATED = "form-gated"
"""SWaT access is an iTrust request form. Agents must not fetch around it."""

_SWAT_CANDIDATES = (
    Path("swat") / "swat-train-prepared.csv",
    Path("itrust-swat-wadi") / "swat-train-prepared.csv",
)


class CorpusMissingError(FileNotFoundError):
    """Raised when a plant corpus is not on disk.

    Attributes:
        plant: Registry name of the missing corpus.
        reason: ``form-gated`` for SWaT, otherwise ``absent``.
    """

    def __init__(self, plant: str, reason: str, detail: str) -> None:
        """Record which plant is missing and why.

        Args:
            plant: Registry name of the missing corpus.
            reason: ``form-gated`` for SWaT, otherwise ``absent``.
            detail: Human-readable explanation.
        """
        super().__init__(detail)
        self.plant = plant
        self.reason = reason


def load_batadal(data_root: Path, split: str = "train") -> Dataset:
    """Load prepared BATADAL and project it onto the three physical roles."""
    return _load_prepared(data_root, "batadal", split, BATADAL_PHYSICAL_ROLES)


def load_hai(data_root: Path, split: str = "test") -> Dataset:
    """Load prepared HAI 21.03 and project it onto the three physical roles."""
    return _load_prepared(data_root, "hai", split, HAI_PHYSICAL_ROLES)


def load_swat(data_root: Path, split: str = "train") -> Dataset:
    """Load prepared SWaT if an operator has placed it, else refuse.

    Args:
        data_root: Repository ``data/`` directory.
        split: ``train`` or ``test``. Only a prepared train CSV is sought.

    Returns:
        SWaT projected onto the three physical roles.

    Raises:
        CorpusMissingError: When form-gated files are absent (the expected state).
    """
    del split
    for relative in _SWAT_CANDIDATES:
        path = data_root / relative
        if not path.is_file():
            continue
        header = _csv_header(path)
        require_tags_present(header, SWAT_PHYSICAL_ROLES, "swat")
        adapter = LabelledCsvAdapter(
            path=path,
            timestamp_column="timestamp",
            label_column="label",
            value_columns=list(mapped_tags(SWAT_PHYSICAL_ROLES)),
            name="swat",
            domain=Domain.ATLAS,
            source_note="SWaT operator-provided prepared CSV",
            entity_id=SHARED_ENTITY_ID,
        )
        return project_to_physical_roles(adapter.load(), SWAT_PHYSICAL_ROLES)
    raise CorpusMissingError(
        "swat",
        SWAT_FORM_GATED,
        "SWaT is form-gated (registry itrust-swat-wadi / iTrust request form). "
        "The loader will not fetch it. Place a prepared CSV under data/swat/ "
        "after a human request if this plant should join source training.",
    )


def load_source_train(data_root: Path) -> tuple[Dataset, str]:
    """Return BATADAL train, plus SWaT train when present, already projected.

    Returns:
        ``(train, swat_status)``. ``swat_status`` is ``present`` or
        ``form-gated``.
    """
    batadal = load_batadal(data_root, split="train")
    try:
        swat = load_swat(data_root, split="train")
    except CorpusMissingError as missing:
        if missing.reason != SWAT_FORM_GATED:
            raise
        return batadal, SWAT_FORM_GATED
    combined = concatenate_role_datasets([swat, batadal], name="swat+batadal-physical-roles")
    return combined, "present"


def _load_prepared(
    data_root: Path,
    plant: str,
    split: str,
    role_map: RoleMap,
) -> Dataset:
    """Read a prepared CSV named in ``manifest.json`` and project it."""
    manifest_path = data_root / plant / "manifest.json"
    csv_path = _prepared_path(data_root, manifest_path, split)
    if not csv_path.is_file():
        raise CorpusMissingError(
            plant, "absent", f"{plant} {split} prepared CSV is not at {csv_path}"
        )
    header = _csv_header(csv_path)
    require_tags_present(header, role_map, plant)
    block = _manifest_block(manifest_path, split)
    adapter = LabelledCsvAdapter(
        path=csv_path,
        timestamp_column=str(block.get("timestamp_column", "timestamp")),
        label_column=str(block.get("label_column", "label")),
        value_columns=list(mapped_tags(role_map)),
        name=str(block.get("name", plant)),
        domain=Domain.ATLAS,
        source_note=str(block.get("source_note", plant)),
        entity_id=SHARED_ENTITY_ID,
    )
    return project_to_physical_roles(adapter.load(), role_map)


def _prepared_path(data_root: Path, manifest_path: Path, split: str) -> Path:
    """Resolve the prepared CSV path from the plant manifest."""
    if not manifest_path.is_file():
        raise CorpusMissingError(
            manifest_path.parent.name,
            "absent",
            f"manifest missing: {manifest_path}",
        )
    block = _manifest_block(manifest_path, split)
    return data_root / str(block["path"])


def _manifest_block(manifest_path: Path, split: str) -> dict[str, object]:
    """Return the test block or the nested train block from a plant manifest."""
    loaded: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise CorpusMissingError(
            manifest_path.parent.name,
            "absent",
            f"{manifest_path} is not a JSON object",
        )
    payload: dict[str, object] = loaded
    if split == "train":
        train = payload.get("train")
        if not isinstance(train, dict):
            raise CorpusMissingError(
                manifest_path.parent.name,
                "absent",
                f"{manifest_path} has no train block",
            )
        return train
    if split != "test":
        raise ValueError(f"split must be 'train' or 'test', not {split!r}")
    return payload


def _csv_header(path: Path) -> list[str]:
    """Return the header row of a prepared CSV."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        row = next(reader, None)
    if row is None:
        raise ValueError(f"{path} is empty")
    return row
