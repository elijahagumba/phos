"""Session C9: 3W Petrobras is faults, not cyber-attacks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.eval import default_attack_when
from phos.eval.joint_table import THREE_W_OFFSHORE_WELLS
from phos.eval.three_w import (
    FAULT_CLASSES,
    FAULT_RECALL_NOT_ATTACK_CAVEAT,
    PrepareError,
    is_attack_class,
    is_fault_class,
    is_normal_class,
    prepare_attack_track,
)

REPO = Path(__file__).resolve().parents[2]


def test_class_zero_is_normal_and_not_a_fault() -> None:
    assert is_normal_class(0) is True
    assert is_fault_class(0) is False
    assert is_attack_class(0) is False


@pytest.mark.parametrize("value", sorted(FAULT_CLASSES))
def test_classes_one_through_nine_are_faults_not_attacks(value: int) -> None:
    assert is_fault_class(value) is True
    assert is_attack_class(value) is False
    assert is_normal_class(value) is False


def test_default_attack_when_would_collapse_a_fault_the_trap() -> None:
    """default_attack_when(1) is True; is_attack_class(1) is False. Files win."""
    assert default_attack_when(1) is True
    assert is_attack_class(1) is False


def test_prepare_attack_track_refuses() -> None:
    with pytest.raises(PrepareError, match="faults, not cyber-attacks"):
        prepare_attack_track()
    assert "ADR 0033" in FAULT_RECALL_NOT_ATTACK_CAVEAT


def test_joint_table_names_offshore_wells_without_invented_fp_hour() -> None:
    assert THREE_W_OFFSHORE_WELLS.process_type == "offshore-wells"
    assert THREE_W_OFFSHORE_WELLS.recall_kind == "fault"
    assert THREE_W_OFFSHORE_WELLS.files_present is False
    assert THREE_W_OFFSHORE_WELLS.command_corpus is False
    assert THREE_W_OFFSHORE_WELLS.cyber_claim is False


def test_registry_still_has_empty_files_and_fault_labels() -> None:
    registry = json.loads((REPO / "data" / "registry.json").read_text(encoding="utf-8"))
    row = next(item for item in registry["datasets"] if item["name"] == "3w-petrobras")
    assert row["files"] == []
    assert row["labels"]["attack_values"] == []
    assert "fault" in row["labels"]["note"].lower()
