"""The batch summary describes what was generated, and has nowhere to put a score.

PART R5 asks for a distribution summary over a directory of runs: how many of each family, the
range of each parameter, how often the validity gate refused a candidate, and what fraction of a
run is normal. Two things about it need pinning rather than trusting.

The first is that it reads the *manifests and labels only*. A summary that opened every
``telemetry.csv`` would be slow on a batch of two hundred and would also be able to say things
about the data it is supposed to merely count — so a plant here is given a deliberately corrupt
payload, and the summary is expected not to notice.

The second is that it scores nothing. That is asserted structurally, on the fields a plant record
carries, rather than by searching the printed text for the word "recall" — a text search would
also fire on a caption explaining that nothing is scored, which is how that test fails for the
wrong reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.summarise_plants import (
    HEADLINE_PARAMETERS,
    PlantRecord,
    Summary,
    load_plants,
    main,
    summarise,
)

START = "2026-03-01T00:00:00+00:00"


def _event(
    kind: str,
    layer: str,
    start_hour: int,
    end_hour: int,
    *,
    physical: bool = True,
    in_range: bool = False,
) -> dict[str, Any]:
    """Return one scripted event in the shape the labels file carries."""
    return {
        "event_id": f"{kind}-{layer}-{start_hour}",
        "kind": kind,
        "type": f"{kind}_thing",
        "layer": layer,
        "started_at": f"2026-03-01T{start_hour:02d}:00:00+00:00",
        "ended_at": f"2026-03-01T{end_hour:02d}:00:00+00:00",
        "signals": ["level_m"],
        "physical_effect": physical,
        "within_normal_range": in_range,
        "technique": "a described technique",
        "issuer": None,
        "detail": "what happened",
    }


def _write_plant(
    root: Path,
    name: str,
    *,
    family: str = "level_flow",
    seed: int = 1,
    rejections: int = 0,
    samples: int = 1200,
    parameters: dict[str, float] | None = None,
    scripted: list[dict[str, Any]] | None = None,
    benign: int = 0,
) -> Path:
    """Write a plant directory holding only the two documents the summary reads."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "plant_id": name,
                "family_id": family,
                "master_seed": seed,
                "rejections": rejections,
                "samples": samples,
                "parameters": parameters if parameters is not None else {"trains": 2.0},
            }
        ),
        encoding="utf-8",
    )
    (directory / "labels.json").write_text(
        json.dumps(
            {
                "scripted_events": scripted or [],
                "benign_events": [{"kind": "operator_setpoint"} for _ in range(benign)],
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_a_missing_directory_is_an_error_rather_than_an_empty_batch(tmp_path: Path) -> None:
    """A typo'd path reporting "0 plants" reads as a batch that failed to generate."""
    with pytest.raises(FileNotFoundError):
        load_plants(tmp_path / "nowhere")


def test_an_empty_directory_summarises_to_a_sentence(tmp_path: Path) -> None:
    lines = summarise(load_plants(tmp_path), ())

    assert lines == ["No generated plants found."]


def test_every_plant_is_read_with_its_family_seed_and_gate_count(tmp_path: Path) -> None:
    _write_plant(tmp_path, "a", family="level_flow", seed=11, rejections=2)
    _write_plant(tmp_path, "b", family="thermal", seed=12, rejections=0)

    summary = load_plants(tmp_path)

    assert len(summary.plants) == 2
    assert sorted(summary.by_family()) == ["level_flow", "thermal"]
    assert summary.by_family()["level_flow"][0].master_seed == 11
    assert summary.by_family()["level_flow"][0].rejections == 2


def test_the_gate_cost_is_reported_as_draws_per_plant(tmp_path: Path) -> None:
    """Two kept plants that cost four draws is the number that says a family is drawn too wide."""
    _write_plant(tmp_path, "a", rejections=1)
    _write_plant(tmp_path, "b", rejections=1)

    lines = summarise(load_plants(tmp_path), ())

    assert any("2 candidate(s) refused for 2 kept (2.00 draws per plant)" in line for line in lines)


def test_a_directory_with_no_manifest_is_listed_rather_than_skipped(tmp_path: Path) -> None:
    _write_plant(tmp_path, "good")
    (tmp_path / "half-written").mkdir()

    summary = load_plants(tmp_path)
    lines = summarise(summary, ())

    assert summary.unreadable == ["half-written: no manifest.json"]
    assert any("could not be read" in line for line in lines)


def test_an_unparsable_manifest_is_listed_rather_than_raising(tmp_path: Path) -> None:
    """One corrupt directory must not cost the report on the other hundred and ninety-nine."""
    _write_plant(tmp_path, "good")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text("{not json", encoding="utf-8")

    summary = load_plants(tmp_path)

    assert len(summary.plants) == 1
    assert len(summary.unreadable) == 1
    assert "broken:" in summary.unreadable[0]


def test_the_payload_is_never_opened(tmp_path: Path) -> None:
    """The summary counts runs; it does not read them. A corrupt payload proves it.

    Written as unreadable bytes rather than as an absent file, because an absent file would also
    pass a summary that tried to read it and handled the error.
    """
    directory = _write_plant(tmp_path, "a")
    (directory / "telemetry.csv").write_bytes(b"\x00\xff\xfe not a csv at all")
    (directory / "capture.pcap").write_bytes(b"\x00\x01")

    lines = summarise(load_plants(tmp_path), ())

    assert any("1 generated plant(s)" in line for line in lines)


def test_parameter_ranges_cover_the_structural_parameters_without_being_asked(
    tmp_path: Path,
) -> None:
    _write_plant(tmp_path, "a", parameters={"trains": 1.0, "stages": 3.0, "tank_area_m2": 10.0})
    _write_plant(tmp_path, "b", parameters={"trains": 4.0, "stages": 3.0, "tank_area_m2": 40.0})

    lines = summarise(load_plants(tmp_path), ())

    assert any("trains" in line and "1" in line and "4" in line for line in lines)
    assert any("stages" in line for line in lines)
    assert not any("tank_area_m2" in line for line in lines), (
        "a family has forty parameters; a table of all of them describes nothing"
    )


def test_a_named_parameter_is_reported_as_well_as_the_structural_ones(tmp_path: Path) -> None:
    _write_plant(tmp_path, "a", parameters={"trains": 1.0, "tank_area_m2": 10.0})

    lines = summarise(load_plants(tmp_path), ("tank_area_m2",))

    assert any("tank_area_m2" in line for line in lines)
    assert any("trains" in line for line in lines)


def test_a_structural_parameter_asked_for_twice_is_not_printed_twice(tmp_path: Path) -> None:
    _write_plant(tmp_path, "a", parameters={"trains": 1.0})

    lines = summarise(load_plants(tmp_path), ("trains",))

    assert sum(1 for line in lines if "trains" in line) == 1
    assert "trains" in HEADLINE_PARAMETERS


def test_a_normal_corpus_says_so_rather_than_printing_an_empty_table(tmp_path: Path) -> None:
    _write_plant(tmp_path, "a", scripted=[])

    lines = summarise(load_plants(tmp_path), ())

    assert any("every sample of these runs is normal" in line for line in lines)


def test_events_are_counted_by_kind_and_by_layer(tmp_path: Path) -> None:
    _write_plant(
        tmp_path,
        "a",
        scripted=[
            _event("attack", "sensor", 1, 2),
            _event("attack", "network", 4, 5),
            _event("fault", "process", 7, 8),
            _event("maintenance", "actuator", 10, 11),
        ],
    )

    lines = summarise(load_plants(tmp_path), ())
    counts = next(line for line in lines if "scripted events" in line)

    assert "'attack': 2" in counts
    assert "'fault': 1" in counts
    assert "'maintenance': 1" in counts
    assert "'network': 1" in counts
    assert "'process': 1" in counts


def test_the_two_measured_facts_are_tallied_against_the_total(tmp_path: Path) -> None:
    """``physical_effect`` and ``within_normal_range`` are measured by the generator, not declared.

    The summary's job is to count them, so a batch can be read as "of 30 attacks, 4 stayed inside
    normal ranges" without opening a single run.
    """
    _write_plant(
        tmp_path,
        "a",
        scripted=[
            _event("attack", "sensor", 1, 2, physical=True, in_range=False),
            _event("attack", "sensor", 4, 5, physical=False, in_range=True),
            _event("fault", "process", 7, 8, physical=True, in_range=True),
        ],
    )

    lines = summarise(load_plants(tmp_path), ())

    assert any("2/3 moved the process, 2/3 stayed inside normal ranges" in line for line in lines)


def test_overlapping_windows_of_one_kind_are_not_double_counted() -> None:
    record = PlantRecord(
        plant_id="a",
        family_id="level_flow",
        master_seed=1,
        rejections=0,
        samples=100,
        parameters={},
        scripted=(
            _event("attack", "sensor", 1, 4),
            _event("attack", "network", 2, 6),
            _event("maintenance", "actuator", 1, 6),
        ),
    )

    # Attacks cover 01:00 to 06:00 of a 01:00-06:00 span: all of it, counted once, not 9/5.
    assert record.covered_fraction("attack") == pytest.approx(1.0)
    assert record.covered_fraction("maintenance") == pytest.approx(1.0)
    assert record.covered_fraction("fault") == 0.0


def test_the_fractions_by_kind_are_not_presented_as_a_partition(tmp_path: Path) -> None:
    """A maintenance window and an attack window may overlap, so they can sum past one.

    The caption has to say so, because a reader who assumed a partition would read a 60% attack
    and a 60% maintenance figure as an arithmetic error rather than as two overlapping windows.
    """
    _write_plant(
        tmp_path,
        "a",
        scripted=[_event("attack", "sensor", 1, 6), _event("maintenance", "actuator", 1, 6)],
    )

    lines = summarise(load_plants(tmp_path), ())
    fractions = [line for line in lines if "covers" in line]

    assert len(fractions) == 2
    assert any("not a partition" in line for line in lines)


def test_an_event_free_plant_contributes_no_fraction_rather_than_a_zero(tmp_path: Path) -> None:
    """A plant whose family cannot host a leak would otherwise drag every range down to 0.0%."""
    _write_plant(tmp_path, "a", scripted=[_event("attack", "sensor", 1, 6)])
    _write_plant(tmp_path, "b", scripted=[])

    lines = summarise(load_plants(tmp_path), ())

    assert any("attack" in line and "covers 100.0% to 100.0%" in line for line in lines)


def test_benign_operations_are_reported_apart_from_the_scripted_events(tmp_path: Path) -> None:
    """An operator moving a setpoint is ground truth, not a target, and is counted separately."""
    _write_plant(tmp_path, "a", benign=5, scripted=[_event("attack", "sensor", 1, 2)])

    lines = summarise(load_plants(tmp_path), ())

    assert any("benign operations     5" in line for line in lines)


def test_a_plant_record_carries_no_field_a_score_could_be_written_into() -> None:
    """Asserted on the fields rather than on the printed words.

    Adding a ``recall`` or ``alerts`` field to this script would make it a scorer, and PART S6's
    referee is the only thing in the programme entitled to produce one. Pinning the field set
    means that change has to come here and be argued for.
    """
    assert set(PlantRecord.__dataclass_fields__) == {
        "plant_id",
        "family_id",
        "master_seed",
        "rejections",
        "samples",
        "parameters",
        "scripted",
        "benign",
    }
    assert set(Summary.__dataclass_fields__) == {"plants", "unreadable"}


def test_the_report_states_that_it_scores_nothing(tmp_path: Path) -> None:
    _write_plant(tmp_path, "a")

    lines = summarise(load_plants(tmp_path), ())

    assert any("Nothing here scores a detector" in line for line in lines)


def test_the_command_line_reports_a_batch_and_refuses_a_missing_directory(tmp_path: Path) -> None:
    _write_plant(tmp_path, "a")

    assert main([str(tmp_path)]) == 0
    assert main([str(tmp_path / "nowhere")]) == 2
