"""OT library catalogue: hundreds of labelled windows, no overlaps, caveats on the record."""

from datetime import timedelta
from itertools import pairwise
from pathlib import Path

from phos.library.ot import (
    ot_catalogue_payload,
    ot_packs,
    ot_scenario_count,
    ot_trains,
    write_ot_catalogue,
)
from phos.synth.attacks.spec import AttackType


def test_the_catalogue_declares_hundreds_of_labelled_windows() -> None:
    packs = ot_packs()
    assert ot_scenario_count(packs) >= 300
    assert len(packs) >= 18
    plants = {pack.plant_id for pack in packs}
    assert plants == {"water-treatment", "power-generation", "batch-reactor"}


def test_every_pack_has_non_overlapping_windows() -> None:
    for pack in ot_packs():
        windows = sorted(
            (plan.start_hours, plan.start_hours + plan.duration_hours, plan.attack_id)
            for plan in pack.attacks
        )
        for earlier, later in pairwise(windows):
            assert earlier[1] <= later[0], f"{pack.name}: {earlier[2]} overlaps {later[2]}"


def test_attack_identifiers_are_unique_across_the_library() -> None:
    ids = [plan.attack_id for pack in ot_packs() for plan in pack.attacks]
    assert len(ids) == len(set(ids))


def test_the_dial_and_the_command_kinds_are_both_present() -> None:
    subtleties = {plan.subtlety for pack in ot_packs() for plan in pack.attacks}
    types = {plan.type for pack in ot_packs() for plan in pack.attacks}
    assert 0.0 in subtleties
    assert 0.9 in subtleties
    assert AttackType.STEALTH_DRIFT in types
    assert AttackType.ROGUE_COMMAND in types
    assert AttackType.LIAR in types
    assert AttackType.MIMIC in types


def test_batch_command_packs_have_no_wire_attacks() -> None:
    for pack in ot_packs():
        if pack.plant_id != "batch-reactor" or "command" not in pack.name:
            continue
        assert all(not plan.type.is_command_attack for plan in pack.attacks)


def test_fitting_corpora_are_attack_free_and_per_plant() -> None:
    trains = ot_trains()
    assert len(trains) == 3
    assert all(train.role == "train" for train in trains)
    assert {train.plant_id for train in trains} == {pack.plant_id for pack in ot_packs()}


def test_the_catalogue_carries_the_honesty_caveats(tmp_path: Path) -> None:
    payload = ot_catalogue_payload()
    caveats = payload["caveats"]
    assert isinstance(caveats, list)
    joined = " ".join(str(item) for item in caveats)
    assert "NOT A PUBLIC CORPUS" in joined
    assert "WE designed" in joined
    path = write_ot_catalogue(tmp_path)
    assert path.is_file()
    assert path.name == "catalogue.json"


def test_a_one_attack_pack_generates_and_labels_through_the_ordinary_csv(tmp_path: Path) -> None:
    """A short water-treatment blatant run is a Dataset the harness already knows how to score."""
    from datetime import UTC, datetime

    from phos.eval import LabelledCsvAdapter
    from phos.ontology import Domain
    from phos.synth.attacks.battery import AttackDatasetConfig
    from phos.synth.attacks.generate import TELEMETRY_FILE, generate_attack_dataset
    from phos.synth.attacks.spec import AttackPlan
    from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN

    plan = AttackPlan(
        attack_id="probe-blatant",
        type=AttackType.BLATANT,
        subtlety=0.0,
        start_hours=2.0,
        duration_hours=1.0,
        target="intake_pump_speed_pct",
        note="Unit-test probe.",
    )
    config = AttackDatasetConfig(
        name="lib-ot-probe",
        plant_id="water-treatment",
        seed=3,
        start=datetime(2026, 6, 1, tzinfo=UTC),
        duration_hours=6.0,
        sample_interval_seconds=60.0,
        role="attack",
        attacks=(plan,),
    )
    directory, manifest = generate_attack_dataset(config, tmp_path, with_capture=False)
    assert manifest.attacked_samples > 0
    dataset = LabelledCsvAdapter(
        name=config.name,
        path=directory / TELEMETRY_FILE,
        timestamp_column=TIMESTAMP_COLUMN,
        label_column=LABEL_COLUMN,
        domain=Domain.ATLAS,
    ).load()
    assert len(dataset.attack_intervals) == 1
    span = dataset.attack_intervals[0].end - dataset.attack_intervals[0].start
    assert span >= timedelta(minutes=50)
