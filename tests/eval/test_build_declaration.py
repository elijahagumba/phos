"""ADR 0144: the October build's seeds and file splits are disjoint, and declared."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.fetch_datasets import load_registry
from scripts.icssim.generate_corpus import RUNS

from phos.breaking.liar_arena import (
    ARENA_LIAR_SEEDS,
    CONFIRM_SEEDS,
    CONFIRM_SEEDS_2,
    CONFIRM_SEEDS_3,
    RED_TEAM_SEEDS,
)
from phos.eval.build_declaration import (
    BUILD_DEVELOPMENT_SEEDS,
    BUILD_HELD_BACK_SEEDS,
    DECLARED_HELD_OUT,
    GRFICS_COMMIT,
    GRFICS_DEVELOPMENT_RUNS,
    GRFICS_HELD_BACK_RUNS,
    GRFICS_LICENSE_SHA256,
    LANE_R_HELD_BACK_SEEDS,
    QUEUE_DEVELOPMENT_SEEDS,
    QUEUE_HELD_BACK_SEEDS,
    SCORECARD,
    TRUSTED_DEVELOPMENT_SEEDS,
    TRUSTED_HELD_BACK_SEEDS,
    W5_DEVELOPMENT_SEEDS,
    W5_HELD_BACK_SEEDS,
    build_seed_blocks,
    grfics_run_ok,
    registry_file_halves,
)
from phos.eval.liar_declaration import DEVELOPMENT_SEEDS, LIAR_HELD_OUT_SEEDS
from phos.library.ot import SEEDS

REPO = Path(__file__).resolve().parents[2]


def _icssim_seeds() -> frozenset[int]:
    seeds: set[int] = set()
    for spec in RUNS.values():
        runs = spec["runs"]
        assert isinstance(runs, list)
        for _scenario, seed in runs:
            seeds.add(int(seed))
    return frozenset(seeds)


def _used_blocks() -> dict[str, frozenset[int]]:
    return {
        "t1-held-out": frozenset(LIAR_HELD_OUT_SEEDS),
        "development": frozenset(DEVELOPMENT_SEEDS),
        "library": frozenset(SEEDS),
        "arena": frozenset(ARENA_LIAR_SEEDS),
        "red-team": frozenset(RED_TEAM_SEEDS),
        "confirm": frozenset(CONFIRM_SEEDS),
        "confirm-2": frozenset(CONFIRM_SEEDS_2),
        "confirm-3": frozenset(CONFIRM_SEEDS_3),
        "icssim": _icssim_seeds(),
    }


def test_new_seed_blocks_are_disjoint_from_every_used_set() -> None:
    used: set[int] = set()
    for block in _used_blocks().values():
        used |= block
    fresh = build_seed_blocks()
    names = list(fresh)
    for i, left in enumerate(names):
        assert not fresh[left] & used, left
        for right in names[i + 1 :]:
            shared = fresh[left] & fresh[right]
            assert not shared, f"{left} meets {right}"
    assert len(BUILD_DEVELOPMENT_SEEDS) == 20
    assert len(BUILD_HELD_BACK_SEEDS) == 20
    assert BUILD_DEVELOPMENT_SEEDS[0] == 97001
    assert BUILD_HELD_BACK_SEEDS[0] == 97101
    assert W5_DEVELOPMENT_SEEDS == tuple(range(97401, 97421))
    assert W5_HELD_BACK_SEEDS == tuple(range(97501, 97521))
    assert not frozenset(W5_DEVELOPMENT_SEEDS) & frozenset(W5_HELD_BACK_SEEDS)
    assert LANE_R_HELD_BACK_SEEDS == tuple(range(97701, 97721))
    assert not frozenset(LANE_R_HELD_BACK_SEEDS) & frozenset(W5_DEVELOPMENT_SEEDS)
    assert not frozenset(LANE_R_HELD_BACK_SEEDS) & frozenset(W5_HELD_BACK_SEEDS)
    assert TRUSTED_DEVELOPMENT_SEEDS == tuple(range(97801, 97821))
    assert TRUSTED_HELD_BACK_SEEDS == tuple(range(97901, 97921))
    assert not frozenset(TRUSTED_DEVELOPMENT_SEEDS) & frozenset(TRUSTED_HELD_BACK_SEEDS)
    assert not frozenset(range(97601, 97671)) & frozenset(TRUSTED_DEVELOPMENT_SEEDS)
    assert not frozenset(range(97701, 97721)) & frozenset(TRUSTED_HELD_BACK_SEEDS)
    assert QUEUE_DEVELOPMENT_SEEDS == tuple(range(97651, 97671))
    assert QUEUE_HELD_BACK_SEEDS == tuple(range(97601, 97621))
    assert not frozenset(QUEUE_DEVELOPMENT_SEEDS) & frozenset(QUEUE_HELD_BACK_SEEDS)
    assert len(QUEUE_DEVELOPMENT_SEEDS) == 20
    assert len(QUEUE_HELD_BACK_SEEDS) == 20


def test_the_scorecard_names_the_brief_and_nothing_is_a_number() -> None:
    assert SCORECARD == (
        "catches_within_budget",
        "margin_over_best_simple_rival",
        "margin_over_chance",
        "falsified_sensor_passes",
        "naming_right",
        "naming_wrong",
        "reconstruction_error",
        "maintenance_closures",
        "calibration",
        "false_alerts_per_shift",
        "runtime",
    )


def test_registry_halves_match_the_declaration_and_do_not_overlap() -> None:
    registry = load_registry()
    halves = registry_file_halves()
    development = {"kelmarsh", "penmanshiel", "netresec-4sics-ics-pcap"}
    held_back = {"kelmarsh-heldback", "penmanshiel-heldback", "netresec-4sics-heldout"}
    for name, expected in halves.items():
        entry = registry.by_name(name)
        assert {file.filename for file in entry.files} == expected
        assert not entry.seen, name
        if name in development:
            assert entry.role == "development"
        if name in held_back:
            assert entry.role == "held-out"
    for dev, held in (
        ("kelmarsh", "kelmarsh-heldback"),
        ("penmanshiel", "penmanshiel-heldback"),
        ("netresec-4sics-ics-pcap", "netresec-4sics-heldout"),
    ):
        assert not halves[dev] & halves[held]


def test_wind_checksums_are_recorded_and_4sics_sizes_are_not_invented() -> None:
    registry = load_registry()
    for name in ("kelmarsh", "kelmarsh-heldback", "penmanshiel", "penmanshiel-heldback"):
        for file in registry.by_name(name).files:
            assert file.md5 and len(file.md5) == 32, file.filename
            assert file.size_bytes > 0, file.filename
    for name in ("netresec-4sics-ics-pcap", "netresec-4sics-heldout"):
        for file in registry.by_name(name).files:
            assert file.size_bytes == 0
            assert file.sha256 is None


def test_held_out_bank_is_exactly_the_declared_corpora() -> None:
    held_out = [entry.name for entry in load_registry().datasets if entry.role == "held-out"]
    assert held_out == list(DECLARED_HELD_OUT)


def test_grfics_runs_are_declared_and_the_code_is_not_a_corpus_file() -> None:
    assert all(grfics_run_ok(run) for run in GRFICS_DEVELOPMENT_RUNS + GRFICS_HELD_BACK_RUNS)
    assert len(GRFICS_DEVELOPMENT_RUNS) == 10
    assert len(GRFICS_HELD_BACK_RUNS) == 10
    registry = load_registry()
    dev, held = registry.by_name("grfics-v3"), registry.by_name("grfics-v3-heldout")
    assert dev.role == "development" and dev.files == [] and not dev.seen
    assert held.role == "held-out" and held.files == [] and not held.seen
    assert dev.license.spdx == "GPL-3.0"
    note = dev.status_note + held.status_note
    assert GRFICS_COMMIT in note
    assert GRFICS_LICENSE_SHA256 in note
    raw = json.loads((REPO / "data" / "registry.json").read_text(encoding="utf-8"))
    names = [entry["name"] for entry in raw["datasets"]]
    assert "grfics-v3" in names and "grfics-v3-heldout" in names


def test_tu_wien_split_is_the_two_benign_training_files() -> None:
    """ADR 0163: development is tf_a.zip; held-back is tf_s.zip; attack zips are in neither."""
    registry = load_registry()
    dev = registry.by_name("tu-wien-pilot-factory")
    held = registry.by_name("tu-wien-pilot-factory-heldout")
    assert dev.role == "development" and held.role == "held-out"
    assert not dev.seen and not held.seen
    assert [item.filename for item in dev.files] == ["tf_a.zip"]
    assert [item.filename for item in held.files] == ["tf_s.zip"]
    assert dev.files[0].size_bytes == 43_271_721_723
    assert held.files[0].size_bytes == 57_610_245_633
    assert dev.files[0].md5 == "e1e689c877b45858fc6c41fd000f85da"
    assert held.files[0].md5 == "1a809db9022a5073ff4f30f00639addb"
    assert dev.files[0].sha256 is None and held.files[0].sha256 is None
    assert dev.license.spdx == "CC-BY-4.0"
    assert "0163" in dev.status_note and "0163" in held.status_note
    scored = {item.filename for item in (*dev.files, *held.files)}
    assert "extractions.zip" not in scored
    assert "a_day1.zip" not in scored
    assert "a_day_tuesday_dos.zip" not in scored
