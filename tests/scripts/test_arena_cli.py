"""The arena command line's candidate parsing and scorer pin (ADR 0120)."""

from __future__ import annotations

import pytest
from scripts.arena import SCORER_FILES, scorer_sha256, windows_from

from phos.atlas.consistency_windows import FROZEN_WINDOWS


def test_no_overrides_is_the_frozen_windows() -> None:
    assert windows_from({}) == FROZEN_WINDOWS


def test_overrides_replace_only_what_they_name() -> None:
    windows = windows_from({"lags": [0, 30, 600], "detrend_window": 21600})
    assert windows.lags == (0, 30, 600)
    assert windows.detrend_window == 21600
    assert windows.fit_step == FROZEN_WINDOWS.fit_step


@pytest.mark.parametrize(
    "candidate",
    [
        {"invented": 1},
        {"lags": []},
        {"lags": [0, -5]},
        {"lags": [0, 1.5]},
        {"detrend_window": 0},
        {"detrend_window": "3600"},
        {"feature_gap": True},
    ],
)
def test_a_malformed_candidate_is_refused(candidate: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        windows_from(candidate)


def test_the_scorer_pin_covers_the_frozen_detector_and_itself() -> None:
    assert "scripts/arena.py" in SCORER_FILES
    assert "src/phos/atlas/consistency.py" in SCORER_FILES
    assert len(scorer_sha256()) == 64


def test_a_detector_candidate_overrides_only_the_declared_map_settings() -> None:
    from scripts.arena import MAP_OVERRIDES, map_settings_from

    from phos.atlas.plant_map_model import DEFAULT_SETTINGS

    assert map_settings_from({"lags": [0, 5]}) is None
    assert map_settings_from({"detector": "atlas-plant-map-v1"}) == DEFAULT_SETTINGS
    tuned = map_settings_from(
        {"detector": "atlas-plant-map-v1", "map": {"min_gain": 0.02, "horizon_seconds": [60, 900]}}
    )
    assert tuned is not None
    assert (tuned.min_gain, tuned.horizon_seconds) == (0.02, (60, 900))
    assert tuned.lag_seconds == DEFAULT_SETTINGS.lag_seconds
    assert set(MAP_OVERRIDES) == {
        "max_drivers",
        "max_lags_per_driver",
        "min_gain",
        "horizon_seconds",
        "form_horizon_seconds",
        "naming_rules",
        "calibrator",
    }
    rules = map_settings_from(
        {"detector": "atlas-plant-map-v1", "map": {"naming_rules": "adr-0135"}}
    )
    assert rules is not None and rules.naming_rules == "adr-0135"
    bad_candidates: list[dict[str, object]] = [
        {"detector": "atlas-v1-consistency"},
        {"detector": "atlas-plant-map-v1", "map": {"lag_seconds": [5]}},
        {"detector": "atlas-plant-map-v1", "map": {"min_gain": 1.5}},
        {"detector": "atlas-plant-map-v1", "map": {"max_drivers": 0}},
        {"detector": "atlas-plant-map-v1", "lags": [0]},
        {"detector": "atlas-plant-map-v1", "map": {"naming_rules": "mine"}},
        {"detector": "atlas-plant-map-v1", "map": {"calibrator": "mine"}},
    ]
    for bad in bad_candidates:
        with pytest.raises(ValueError):
            map_settings_from(bad)


def test_the_scorer_pins_the_plant_map_s_files() -> None:
    assert "src/phos/atlas/plant_map_detector.py" in SCORER_FILES
    assert "data/hai-20.07/roles.toml" in SCORER_FILES
