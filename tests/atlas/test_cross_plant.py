"""Cross-plant physical-role mapping and zero-shot protocol (ADR 0063).

Does not retune Atlas templates, overwrite HAI 646.58, or fetch SWaT.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.data.loaders import (
    SWAT_FORM_GATED,
    CorpusMissingError,
    load_batadal,
    load_hai,
    load_swat,
)
from phos.atlas.data.mapping import (
    BATADAL_PHYSICAL_ROLES,
    HAI_PHYSICAL_ROLES,
    PHYSICAL_ROLES,
    SWAT_PHYSICAL_ROLES,
    PhysicalRole,
    project_to_physical_roles,
)
from phos.atlas.data.transfer import (
    PHYSICAL_ROLES_DETECTOR_NAME,
    TRANSFER_CAVEAT,
    run_zero_shot,
    write_zero_shot_log,
)
from phos.eval.datasets import Dataset, LabelledInterval
from phos.ontology import Domain, Observation

REPO = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _obs(feature: str, value: float, seconds: int, entity: str = "plant") -> Observation:
    return Observation(
        id=f"obs_{feature}_{seconds:04d}",
        entity_ids=[entity],
        feature=feature,
        value=value,
        timestamp=T0 + timedelta(seconds=seconds),
        domain=Domain.ATLAS,
    )


def _role_dataset(
    name: str,
    *,
    attack_at: int | None = None,
    n: int = 40,
    flow: float = 1.0,
    pressure: float = 2.0,
    pump: float = 0.0,
) -> Dataset:
    observations: list[Observation] = []
    for second in range(n):
        attacked = attack_at is not None and second == attack_at
        observations.extend(
            [
                _obs(PhysicalRole.FLOW.value, flow * 8.0 if attacked else flow, second, name),
                _obs(
                    PhysicalRole.PRESSURE.value,
                    pressure * 8.0 if attacked else pressure,
                    second,
                    name,
                ),
                _obs(PhysicalRole.PUMP_STATE.value, 1.0 if attacked else pump, second, name),
            ]
        )
    intervals: list[LabelledInterval] = []
    if attack_at is not None:
        stamp = T0 + timedelta(seconds=attack_at)
        intervals.append(LabelledInterval(start=stamp, end=stamp, label="attack"))
    return Dataset(
        name=name,
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=intervals,
        source_note="fixture",
    )


def test_physical_roles_are_flow_pressure_pump_only() -> None:
    assert PHYSICAL_ROLES == (
        PhysicalRole.FLOW,
        PhysicalRole.PRESSURE,
        PhysicalRole.PUMP_STATE,
    )
    for plant_map in (HAI_PHYSICAL_ROLES, BATADAL_PHYSICAL_ROLES, SWAT_PHYSICAL_ROLES):
        assert set(plant_map) == set(PHYSICAL_ROLES)


def test_declared_maps_do_not_carry_plant_specific_leftovers() -> None:
    assert "L_T1" not in BATADAL_PHYSICAL_ROLES[PhysicalRole.FLOW]
    assert "P2_CO_rpm" not in HAI_PHYSICAL_ROLES[PhysicalRole.FLOW]
    assert "LIT101" not in SWAT_PHYSICAL_ROLES[PhysicalRole.FLOW]


def test_projection_keeps_only_role_features() -> None:
    plant = Dataset(
        name="toy-swat",
        domain=Domain.ATLAS,
        observations=[
            _obs("FIT101", 10.0, 0),
            _obs("LIT101", 800.0, 0),
            _obs("PIT501", 2.0, 0),
            _obs("P101", 1.0, 0),
        ],
        source_note="fixture",
    )
    projected = project_to_physical_roles(plant, SWAT_PHYSICAL_ROLES)
    features = {item.feature for item in projected.observations}
    assert features == {role.value for role in PHYSICAL_ROLES}
    assert "LIT101" not in features
    assert "FIT101" not in features


def test_swat_loader_refuses_when_the_form_gated_files_are_absent() -> None:
    with pytest.raises(CorpusMissingError, match="form-gated") as raised:
        load_swat(REPO / "data")
    assert raised.value.reason == SWAT_FORM_GATED


def test_zero_shot_on_aligned_fixtures_is_finite_and_not_a_public_log_name() -> None:
    train = _role_dataset("source-plant", n=50, flow=1.0, pressure=2.0, pump=0.0)
    test = _role_dataset(
        "target-plant",
        n=50,
        flow=1.0,
        pressure=2.0,
        pump=0.0,
        attack_at=40,
    )
    report = run_zero_shot(train, test)
    assert report.dataset_name.startswith("zero-shot:")
    assert "hai-21.03" not in report.dataset_name
    assert report.detector_name != "atlas-mahalanobis"
    assert report.detector_name != "model:atlas-mahalanobis"
    assert PHYSICAL_ROLES_DETECTOR_NAME in report.detector_name
    assert TRANSFER_CAVEAT in report.source_note
    assert report.false_positive_rate >= 0.0
    assert 0.0 <= report.window_recall <= 1.0


def test_zero_shot_log_uses_a_new_row_name(tmp_path: Path) -> None:
    train = _role_dataset("source-plant", n=30)
    test = _role_dataset("target-plant", n=30, attack_at=20)
    report = run_zero_shot(train, test)
    log_path = tmp_path / "log.jsonl"
    write_zero_shot_log(report, log_path)
    line = log_path.read_text(encoding="utf-8")
    assert "646.58" not in line
    assert "zero-shot:" in line
    assert PHYSICAL_ROLES_DETECTOR_NAME in line


@pytest.mark.skipif(
    not (REPO / "data" / "batadal" / "batadal-train-prepared.csv").is_file()
    or not (REPO / "data" / "hai" / "hai-21.03-test-prepared.csv").is_file(),
    reason="prepared BATADAL/HAI payloads are not on this machine",
)
def test_batadal_and_hai_loaders_project_to_the_three_roles() -> None:
    batadal = load_batadal(REPO / "data", split="train")
    hai = load_hai(REPO / "data", split="test")
    assert {item.feature for item in batadal.observations} == {
        role.value for role in PHYSICAL_ROLES
    }
    assert {item.feature for item in hai.observations} == {role.value for role in PHYSICAL_ROLES}
    assert "F_PU1" not in {item.feature for item in batadal.observations}
    assert "P1_FT01" not in {item.feature for item in hai.observations}
