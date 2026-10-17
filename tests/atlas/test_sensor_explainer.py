"""The plant map names a lying sensor on the champion's alerts and does not change them."""

import pytest

from phos.atlas.plant_map_model import DEFAULT_SETTINGS, RESULT_NAME
from phos.atlas.sensor_explainer import (
    EXPLAINER_RESULT_NAME,
    EXPLAINER_SETTINGS,
    FROZEN_SUBJECTS,
    HOLD_SHARE,
    SubjectResult,
    bar_met,
    explainer_is_not_the_default,
    naming_scorecard,
    roles_from_plant,
    score_naming,
    score_subject,
)
from phos.atlas.signal_roles import SignalRole
from phos.eval.build_declaration import BUILD_DEVELOPMENT_SEEDS, BUILD_HELD_BACK_SEEDS
from phos.synth.plant import SignalKind
from phos.synth.plants.water import WATER_DESCRIPTION


def test_roles_quote_the_signal_label_and_use_the_declared_kind() -> None:
    """A role is the plant's SignalKind, and the quote is the label, not the key."""
    roles = roles_from_plant(WATER_DESCRIPTION)
    by_signal = {item.signal: item for item in roles.declarations}
    turbidity = by_signal["filtered_turbidity_ntu"]
    assert turbidity.role is SignalRole.SENSOR
    assert turbidity.quote == "Filtered water turbidity"
    assert turbidity.cited == "water-treatment signal table"
    kinds = {spec.key: spec.kind for spec in WATER_DESCRIPTION.signals}
    for declaration in roles.declarations:
        expected = {
            SignalKind.SENSOR: SignalRole.SENSOR,
            SignalKind.ACTUATOR: SignalRole.ACTUATOR,
            SignalKind.SETPOINT: SignalRole.SETPOINT,
        }[kinds[declaration.signal]]
        assert declaration.role is expected
        assert declaration.quote
    readings = {loop.reading for loop in roles.loops}
    assert readings == {
        "clearwell_level_m",
        "chlorine_residual_mgpl",
        "distribution_pressure_bar",
    }


def test_explainer_settings_are_not_the_frozen_map_defaults() -> None:
    """ADR 0125 stays the default. The explainer is a separate object with ADR 0135's rules."""
    assert explainer_is_not_the_default()
    assert DEFAULT_SETTINGS.naming_rules == "adr-0125"
    assert EXPLAINER_SETTINGS.naming_rules == "adr-0135"
    assert EXPLAINER_SETTINGS is not DEFAULT_SETTINGS
    assert EXPLAINER_RESULT_NAME == "lane-d-plant-map-explainer"
    assert RESULT_NAME == "atlas-plant-map-v1"


def test_the_bar_needs_all_three_frozen_plants_inside_a_tenth() -> None:
    """70% named right, reconstruction within 10% of span, and alerts left as the champion set."""

    def row(plant: str, signal: str, *, right: int = 14, worst: float = 0.09) -> SubjectResult:
        return SubjectResult(
            plant_id=plant,
            signal=signal,
            on_the_bar=True,
            scored=20,
            caught=20,
            named_right=right,
            named_wrong=0,
            reconstruction_max=worst,
            reconstruction_within_tenth=right,
            reconstruction_cells=right,
            alerts_unchanged=True,
        )

    passing = tuple(row(subject.plant_id, subject.signal) for subject in FROZEN_SUBJECTS)
    assert bar_met(passing)
    short = (passing[0], passing[1])
    assert not bar_met(short)
    quiet = row("water-treatment", "filtered_turbidity_ntu", right=0)
    quiet = SubjectResult(
        plant_id=quiet.plant_id,
        signal=quiet.signal,
        on_the_bar=True,
        scored=20,
        caught=0,
        named_right=0,
        named_wrong=0,
        reconstruction_max=None,
        reconstruction_within_tenth=0,
        reconstruction_cells=0,
        alerts_unchanged=True,
    )
    assert not bar_met((quiet, passing[1], passing[2]))
    loud = row("water-treatment", "filtered_turbidity_ntu", worst=0.11)
    assert not bar_met((loud, passing[1], passing[2]))
    numbers = naming_scorecard(passing)
    assert numbers["naming_right"] == 0.7
    assert numbers["naming_wrong"] == 0.0
    assert numbers["reconstruction_error"] == 0.09
    assert numbers["falsified_sensor_passes"] == 1.0
    assert numbers["calibration"] is None
    assert numbers["catches_within_budget"] is None


def test_a_seed_outside_the_named_split_is_refused_before_a_plant_is_built() -> None:
    """Held-back seeds and the spent T1 seeds are not a development measurement."""
    subject = FROZEN_SUBJECTS[0]
    with pytest.raises(ValueError, match="not in the development split"):
        score_subject(subject, split="development", seeds=(BUILD_HELD_BACK_SEEDS[0],))
    with pytest.raises(ValueError, match="not in the development split"):
        score_subject(subject, split="development", seeds=(94001,))
    with pytest.raises(ValueError, match="split must be"):
        score_subject(subject, split="other")


def test_one_development_seed_names_filtered_turbidity_within_a_tenth() -> None:
    """Seed 97002: the champion's alerts on the held turbidity are named, and stay the alerts."""
    subject = FROZEN_SUBJECTS[0]
    assert subject.signal == "filtered_turbidity_ntu"
    assert subject.plant_id == "water-treatment"
    assert HOLD_SHARE == 0.9
    assert 97002 in BUILD_DEVELOPMENT_SEEDS
    result = score_subject(subject, split="development", seeds=(97002,))
    assert result.scored == 1
    assert result.alerts_unchanged
    assert result.caught == 1
    assert result.named_right == 1
    assert result.named_wrong == 0
    assert result.reconstruction_max is not None
    assert result.reconstruction_max <= 0.10
    assert result.seeds_not_named_right == ()


def test_frozen_subjects_on_one_seed_are_named_without_the_survey() -> None:
    """With the survey off, the three bar plants are the whole result."""
    results = score_naming("development", survey=False, seeds=(97002,))
    assert [item.signal for item in results] == [
        "filtered_turbidity_ntu",
        "transformer_oil_temp_c",
        "reactor_temp_c",
    ]
    assert all(item.named_right == 1 and item.named_wrong == 0 for item in results)
