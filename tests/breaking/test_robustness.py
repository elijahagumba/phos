"""Input-hostile measurement: classifying what escapes, and never calling it detection."""

import json
from datetime import timedelta
from pathlib import Path

import pandas
import pytest
from tests.breaking.conftest import RUN_START

from phos.atlas.topology import TopologyError
from phos.breaking.corpus import CorpusNotFoundError
from phos.breaking.outcome import RobustnessVerdict
from phos.breaking.robustness import (
    EXPECTED_REFUSALS,
    CorpusRobustness,
    _verdict_for,
    out_of_band_rate,
    run_robustness,
)
from phos.eval import Dataset
from phos.ontology import Domain, Observation
from phos.synth import PlantDescription
from phos.synth.attacks import AttackManifest, AttackType

# --- classification ------------------------------------------------------


def test_a_clean_run_completed() -> None:
    verdict, error_type, detail = _verdict_for(None)
    assert verdict is RobustnessVerdict.COMPLETED
    assert error_type == ""
    assert "ran to completion" in detail


@pytest.mark.parametrize(
    "error",
    [
        ValueError("bad column"),
        TopologyError("signal outside the map"),
        CorpusNotFoundError("no such corpus"),
        pandas.errors.ParserError("expected 17 fields, saw 18"),
        pandas.errors.EmptyDataError("no columns to parse"),
    ],
)
def test_a_documented_failure_is_a_loud_refusal_rather_than_a_crash(error: Exception) -> None:
    """A security product handed rubbish should decline it and say why. That is not a defect."""
    verdict, error_type, detail = _verdict_for(error)
    assert verdict is RobustnessVerdict.REFUSED
    assert error_type == type(error).__name__
    assert "refused loudly" in detail


@pytest.mark.parametrize(
    "error", [IndexError("list index out of range"), AttributeError("NoneType"), KeyError("k")]
)
def test_an_undocumented_escape_is_a_crash(error: Exception) -> None:
    """An IndexError out of a parser is a parser that did not know its input was short."""
    verdict, error_type, _ = _verdict_for(error)
    assert verdict is RobustnessVerdict.CRASHED
    assert error_type == type(error).__name__


def test_the_refusal_list_names_the_parser_errors_a_corpus_can_produce() -> None:
    """Guards the list, because widening it silently would reclassify a crash as acceptable."""
    assert pandas.errors.ParserError in EXPECTED_REFUSALS
    assert ValueError in EXPECTED_REFUSALS
    assert IndexError not in EXPECTED_REFUSALS
    assert Exception not in EXPECTED_REFUSALS


def test_a_long_error_message_is_truncated_rather_than_pasted_whole() -> None:
    _, _, detail = _verdict_for(ValueError("x" * 5000))
    assert len(detail) <= 400


# --- a corpus that defeats the reader ------------------------------------


def test_a_corpus_that_cannot_be_read_is_recorded_rather_than_raised(tmp_path: Path) -> None:
    """D2 ships corpora built to defeat a reader. One succeeding is a result, not a crash."""
    result = run_robustness(tmp_path / "missing-corpus")
    assert not result.loaded
    assert len(result.outcomes) == 1
    assert result.outcomes[0].verdict is RobustnessVerdict.REFUSED
    assert result.outcomes[0].error_type == "CorpusNotFoundError"
    assert result.all_safe


def test_a_malformed_csv_is_refused_loudly(tmp_path: Path, plant: PlantDescription) -> None:
    corpus_dir = tmp_path / "synth-hostile-fixture"
    corpus_dir.mkdir()
    (corpus_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "synth-hostile-fixture",
                "plant_id": plant.plant_id,
                "flavour": "INPUT_HOSTILE",
                "spec": {
                    "seed": 1,
                    "start": RUN_START.isoformat(),
                    "duration": "PT24H",
                    "sample_interval": "PT30M",
                },
                "samples": 2,
                "description": plant.model_dump(mode="json"),
                "hostile": [
                    {
                        "attack_id": "malformed",
                        "type": "MALFORMED_RECORD",
                        "description": "extra field on one row",
                        "rows_affected": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (corpus_dir / "telemetry.csv").write_text(
        "timestamp,label,level_m\n"
        f"{RUN_START.isoformat()},0,10.0\n"
        f"{(RUN_START + timedelta(minutes=30)).isoformat()},0,10.0,SURPRISE\n",
        encoding="utf-8",
    )

    result = run_robustness(corpus_dir)
    assert not result.loaded
    assert result.outcomes[0].verdict is RobustnessVerdict.REFUSED
    assert result.outcomes[0].error_type == "ParserError"
    assert result.all_safe


# --- the baseline-shift measurement --------------------------------------


def observations(values: list[float], feature: str = "level_m") -> list[Observation]:
    """Build observations at half-hourly spacing."""
    return [
        Observation(
            timestamp=RUN_START + timedelta(minutes=30 * index),
            feature=feature,
            value=value,
            domain=Domain.ATLAS,
            entity_ids=["ent_test0000000001"],
        )
        for index, value in enumerate(values)
    ]


def test_out_of_band_rate_is_zero_for_a_model_that_fits_its_data(plant: PlantDescription) -> None:
    from phos.models import GaussianBaseline

    steady = observations([10.0 + 0.01 * (index % 3) for index in range(60)])
    fitted = GaussianBaseline().fit(steady)
    data = Dataset(name="fixture", domain=Domain.ATLAS, observations=steady)
    assert out_of_band_rate(fitted, data) < 0.2


def test_out_of_band_rate_rises_when_the_data_left_what_was_learned() -> None:
    from phos.models import GaussianBaseline

    steady = observations([10.0 + 0.01 * (index % 3) for index in range(60)])
    fitted = GaussianBaseline().fit(steady)
    shifted = Dataset(
        name="fixture-shifted",
        domain=Domain.ATLAS,
        observations=observations([50.0] * 60),
    )
    assert out_of_band_rate(fitted, shifted) > out_of_band_rate(
        fitted, Dataset(name="f", domain=Domain.ATLAS, observations=steady)
    )


def test_an_empty_corpus_has_no_out_of_band_rate() -> None:
    from phos.models import GaussianBaseline

    fitted = GaussianBaseline().fit(observations([10.0] * 30))
    empty = Dataset(name="f", domain=Domain.ATLAS, observations=[])
    assert out_of_band_rate(fitted, empty) == 0.0


# --- the boundary --------------------------------------------------------


def test_a_robustness_result_offers_no_route_to_a_detection_claim() -> None:
    """The whole point of the type split: there is no `recall` here to accidentally report."""
    result = CorpusRobustness(corpus="fixture")
    for forbidden in ("window_recall", "outcomes_detected", "breaking_points", "detected"):
        assert not hasattr(result, forbidden)
    assert "detected" not in CorpusRobustness.model_fields
    # `all_safe` is the strongest thing it says, and it says nothing about detection.
    assert result.all_safe


def test_a_poisoned_baseline_case_is_the_only_one_carrying_a_shift(
    tmp_path: Path, plant: PlantDescription
) -> None:
    """A shift means nothing for a truncated file, so it is not attached to one."""
    from tests.breaking.test_harness import dataset

    from phos.breaking.corpus import AttackCorpus
    from phos.breaking.robustness import _outcome_for
    from phos.synth.attacks import HostileGroundTruth

    fixture = AttackCorpus(
        manifest=_hostile_manifest(plant),
        dataset=dataset(4),
        truth_path=tmp_path / "truth.csv",
        topology_path=tmp_path / "topology.toml",
        directory=tmp_path,
    )
    poisoned = _outcome_for(
        HostileGroundTruth(attack_id="p", type=AttackType.POISONED_BASELINE, target="level_m"),
        fixture,
        RobustnessVerdict.COMPLETED,
        "",
        "ran",
        0.25,
    )
    truncated = _outcome_for(
        HostileGroundTruth(attack_id="t", type=AttackType.TRUNCATED),
        fixture,
        RobustnessVerdict.COMPLETED,
        "",
        "ran",
        0.25,
    )
    assert poisoned.baseline_shift == pytest.approx(0.25)
    assert truncated.baseline_shift is None


def _hostile_manifest(plant: PlantDescription) -> "AttackManifest":
    """A minimal input-hostile manifest, for the outcome-assembly test above."""
    from phos.synth import RunSpec
    from phos.synth.attacks import AttackFlavour, HostileGroundTruth

    return AttackManifest(
        name="synth-hostile-fixture",
        plant_id=plant.plant_id,
        flavour=AttackFlavour.INPUT_HOSTILE,
        spec=RunSpec(
            seed=1,
            start=RUN_START,
            duration=timedelta(hours=24),
            sample_interval=timedelta(minutes=30),
        ),
        samples=4,
        description=plant,
        hostile=(HostileGroundTruth(attack_id="p", type=AttackType.POISONED_BASELINE),),
    )


def test_an_unloadable_corpus_takes_its_kinds_from_the_manifest_rather_than_guessing(
    tmp_path: Path, plant: PlantDescription
) -> None:
    """The malformed CSV defeated the reader; the manifest beside it is still perfectly readable.

    Naming the corruption from the manifest is the difference between a measurement and a guess. An
    earlier version of this code stamped every unloadable corpus `TRUNCATED`, which mislabelled a
    malformed-records corpus in the report.
    """
    corpus_dir = tmp_path / "synth-hostile-fixture"
    corpus_dir.mkdir()
    (corpus_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "synth-hostile-fixture",
                "plant_id": plant.plant_id,
                "flavour": "INPUT_HOSTILE",
                "spec": {
                    "seed": 1,
                    "start": RUN_START.isoformat(),
                    "duration": "PT24H",
                    "sample_interval": "PT30M",
                },
                "samples": 2,
                "description": plant.model_dump(mode="json"),
                "hostile": [
                    {
                        "attack_id": "malformed",
                        "type": "MALFORMED_RECORD",
                        "description": "extra field on one row",
                        "rows_affected": 58,
                    },
                    {"attack_id": "oor", "type": "OUT_OF_RANGE", "target": "level_m"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (corpus_dir / "telemetry.csv").write_text(
        "timestamp,label,level_m\n"
        f"{RUN_START.isoformat()},0,10.0\n"
        f"{(RUN_START + timedelta(minutes=30)).isoformat()},0,10.0,SURPRISE\n",
        encoding="utf-8",
    )

    result = run_robustness(corpus_dir)
    assert not result.loaded
    kinds = {outcome.attack_type for outcome in result.outcomes}
    assert kinds == {AttackType.MALFORMED_RECORD, AttackType.OUT_OF_RANGE}
    assert {outcome.attack_id for outcome in result.outcomes} == {"malformed", "oor"}
    assert all(o.verdict is RobustnessVerdict.REFUSED for o in result.outcomes)
    assert next(o for o in result.outcomes if o.attack_id == "malformed").rows_affected == 58


def test_a_corpus_with_no_readable_manifest_declares_no_kind_at_all(tmp_path: Path) -> None:
    """With nothing readable there is no ground truth, and `None` says so instead of guessing."""
    corpus_dir = tmp_path / "synth-hostile-shredded"
    corpus_dir.mkdir()
    (corpus_dir / "manifest.json").write_text("{not json at all", encoding="utf-8")
    (corpus_dir / "telemetry.csv").write_text("timestamp,label\n", encoding="utf-8")

    result = run_robustness(corpus_dir)
    assert len(result.outcomes) == 1
    assert result.outcomes[0].attack_type is None
    assert "undeclared" in result.outcomes[0].detail
