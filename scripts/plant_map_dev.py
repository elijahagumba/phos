#!/usr/bin/env python3
"""ADR 0123 §8's development measures the arena's scorecard does not carry (ADR 0127).

The arena (`scripts/arena.py`) scores `atlas-plant-map-v1` for passes and HAI 20.07 recall. This
script measures what the map claims beyond detection, on development data only, and writes one
JSON record per measure under ``eval_runs/plant-map/dev/``:

    uv run python scripts/plant_map_dev.py liar      # naming and reconstruction, arena seeds
    uv run python scripts/plant_map_dev.py map       # §9.5: learned links against declarations
    uv run python scripts/plant_map_dev.py halves    # §9.6: HAI 20.07 links, one map per half
    uv run python scripts/plant_map_dev.py replace   # the replace arm, once, as diagnosis
    uv run python scripts/plant_map_dev.py icssim    # §9.7, §9.8, §9.9 on phos-icssim-dev
    uv run python scripts/plant_map_dev.py null      # chance: the same layout, the lie at zero
    uv run python scripts/plant_map_dev.py network   # ADR 0130 grade C on phos-icssim-dev
    uv run python scripts/plant_map_dev.py intervened  # ADR 0132 grade B on phos-icssim-dev
    uv run python scripts/plant_map_dev.py graded    # ADR 0133: A, D, the trusted map, naming

Nothing here reads a validation or held-out corpus, scores the red team's seeds, or writes
``eval_runs/log.jsonl``. Every figure is diagnosis, never a result (R4).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

import numpy

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.arena import HAI_20_07, map_settings_from, scorer_sha256  # noqa: E402
from scripts.measure_baseline_table import _read_hai  # noqa: E402

from phos.atlas import consistency  # noqa: E402
from phos.atlas.consistency import TrainFile, loop_expectation  # noqa: E402
from phos.atlas.interventions import intervened_links  # noqa: E402
from phos.atlas.network_links import network_claims, score_claims  # noqa: E402
from phos.atlas.plant_map_detector import (  # noqa: E402
    Arm,
    detect_alerts,
    fit_detector,
)
from phos.atlas.plant_map_evidence import promote_plant_map  # noqa: E402
from phos.atlas.plant_map_fit import fit_map  # noqa: E402
from phos.atlas.plant_map_model import DEFAULT_SETTINGS, MapSettings, PlantMap  # noqa: E402
from phos.atlas.plant_map_naming import (  # noqa: E402
    Verdict,
    name_instrument,
    reconstruct,
)
from phos.atlas.plant_model import (  # noqa: E402
    declared_pairs,
    intervened_pairs,
    learned_pairs,
    network_pairs,
    stable_pairs,
    trusted_drivers,
    trusted_map,
)
from phos.atlas.plant_model import halves as split_halves  # noqa: E402
from phos.atlas.signal_roles import load_roles  # noqa: E402
from phos.breaking.corpus import AttackCorpus, load_attack_corpus  # noqa: E402
from phos.breaking.declared_roles import declared_links, description_for, plant_roles  # noqa: E402
from phos.breaking.harness import BreakingConfig  # noqa: E402
from phos.breaking.icssim_runs import (  # noqa: E402
    ROLES_FILE,
    load_exchanges,
    load_interventions,
    load_run,
)
from phos.breaking.icssim_truth import reachable  # noqa: E402
from phos.breaking.liar import (  # noqa: E402
    _matrix,
    _Unit,
    fit_inlet,
    inlet_calibrator,
    liar_corpus_config,
    promote_map,
    run_liar_corpus,
)
from phos.breaking.liar_arena import (  # noqa: E402
    ARENA_LIAR_SEEDS,
    CONFIRM_SEEDS,
    CONFIRM_SEEDS_2,
    _liar,
    _normal,
    score_windows,
)
from phos.breaking.liar_diagnosis import refuse_held_out  # noqa: E402
from phos.breaking.truth import load_true_state  # noqa: E402
from phos.eval.liar_declaration import LIAR_PLANTS  # noqa: E402
from phos.library.ot import SEEDS  # noqa: E402
from phos.ontology import EntityId  # noqa: E402
from phos.synth.attacks.generate import generate_attack_dataset  # noqa: E402
from phos.synth.attacks.spec import AttackType  # noqa: E402

OUT: Final = ROOT / "eval_runs" / "plant-map" / "dev"
#: §9.7's tolerance on reconstruction: within this share of the signal's normal range.
NEAR_SHARE: Final = 0.10

#: The configuration measured: ADR 0123's settings, or an arena candidate's (``--candidate``).
_RUN: dict[str, object] = {"settings": DEFAULT_SETTINGS, "label": "DEFAULT_SETTINGS (ADR 0123)"}


def _seeds() -> tuple[int, ...]:
    seeds = _RUN.get("seeds", ARENA_LIAR_SEEDS)
    assert isinstance(seeds, tuple)
    return seeds


def _settings() -> MapSettings:
    settings = _RUN["settings"]
    assert isinstance(settings, MapSettings)
    return settings


def _write(name: str, record: dict[str, object]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    record = {
        **record,
        "settings": _RUN["label"],
        "scorer_sha256": scorer_sha256(),
        "written": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    suffix = f"-{_RUN['tag']}" if _RUN.get("tag") else ""
    (OUT / f"{name}{suffix}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2)[:4000])


def _row_of(stamps: Sequence[datetime], when: datetime) -> int:
    return int(numpy.searchsorted(numpy.asarray([s.timestamp() for s in stamps]), when.timestamp()))


def liar(cache: Path) -> int:
    """Naming and reconstruction on every arena liar run (ADR 0123 §8, first row)."""
    runs: list[dict[str, object]] = []
    for plant in LIAR_PLANTS:
        normal = _normal(plant, cache)
        inlet = fit_inlet(normal, None, _settings())
        assert inlet.detector is not None
        detector = inlet.detector
        names = detector.plant.names
        for seed in _seeds():
            corpus = _liar(plant, seed, cache)
            matrix = _matrix(corpus.dataset, inlet.space)
            promotion = promote_map(inlet, corpus.dataset, _Unit())
            truth = load_true_state(corpus.truth_path)
            predicted, _half = loop_expectation(inlet.model, matrix.values)
            for attack in corpus.manifest.attacks:
                if attack.type is not AttackType.LIAR:
                    continue
                (target,) = attack.target_signals
                column = names.index(target)
                start = _row_of(matrix.timestamps, attack.started_at)
                end = min(_row_of(matrix.timestamps, attack.ended_at), len(matrix.timestamps) - 1)
                inside = [r for r in promotion.records if start <= r.onset <= end]
                map_named = [
                    r for r in inside if r.naming is not None and r.naming.verdict is Verdict.NAMED
                ]
                named = names[map_named[0].naming.instrument] if map_named else None  # type: ignore[union-attr,index]
                broken = any(
                    r.naming is not None
                    and (target in {names[d] for d in r.naming.broken_links} or r.column == column)
                    for r in inside
                    if r.carried_by == "map"
                )
                true = numpy.asarray(truth.values[target], dtype=numpy.float64)
                rows = numpy.arange(start, end + 1)
                rebuilt = reconstruct(detector.plant, matrix.values, column, start, end)
                normal_range = float(detector.plant.high[column] - detector.plant.low[column])
                measure: dict[str, object] = {"reconstructed": rebuilt is not None}
                if rebuilt is not None:
                    error = numpy.abs(rebuilt.centre - true[rows])
                    known = numpy.isfinite(rebuilt.half_width)
                    measure |= {
                        "form": rebuilt.form.value,
                        "near_share": float(numpy.mean(error <= NEAR_SHARE * normal_range)),
                        "median_error": float(numpy.median(error)),
                        "covered": float(numpy.mean(error[known] <= rebuilt.half_width[known]))
                        if known.any()
                        else None,
                        "band_known_share": float(known.mean()),
                    }
                loop_error = numpy.abs(predicted[rows, column] - true[rows])
                finite = numpy.isfinite(loop_error)
                measure |= {
                    "loop_near_share": float(
                        numpy.mean(loop_error[finite] <= NEAR_SHARE * normal_range)
                    )
                    if finite.any()
                    else None,
                    "loop_median_error": float(numpy.median(loop_error[finite]))
                    if finite.any()
                    else None,
                }
                runs.append(
                    {
                        "plant": plant,
                        "seed": seed,
                        "subtlety": attack.subtlety,
                        "target": target,
                        "caught": bool(inside),
                        "map_carried": any(r.carried_by == "map" for r in inside),
                        "named": named,
                        "named_right": named == target,
                        "named_wrong": named is not None and named != target,
                        "broken_link_involves_target": broken,
                        "verdicts": sorted(
                            {r.naming.verdict.value for r in inside if r.naming is not None}
                        ),
                        **measure,
                    }
                )
    caught = [r for r in runs if r["caught"]]
    summary = {
        "runs": len(runs),
        "caught": len(caught),
        "named_right": sum(bool(r["named_right"]) for r in caught),
        "named_wrong": sum(bool(r["named_wrong"]) for r in caught),
        "by_plant": {
            plant: {
                "runs": sum(r["plant"] == plant for r in runs),
                "caught": sum(r["plant"] == plant for r in caught),
                "named_right": sum(r["plant"] == plant and bool(r["named_right"]) for r in caught),
                "named_wrong": sum(r["plant"] == plant and bool(r["named_wrong"]) for r in caught),
            }
            for plant in LIAR_PLANTS
        },
    }
    _write(
        "liar-naming-reconstruction",
        {"adr": "0123 §8, §9.1, §9.7, §9.9", "summary": summary, "runs": runs},
    )
    return 0


def _declared_paths(plant: str) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    direct = {(link.driver, link.driven) for link in declared_links(description_for(plant))}
    two = {(a, c) for a, b in direct for b2, c in direct if b == b2 and a != c}
    return direct, direct | two


def _links(plant: PlantMap) -> list[tuple[str, str, tuple[int, ...]]]:
    return [
        (plant.names[link.driver], plant.names[target], link.lags)
        for target, model in sorted(plant.targets.items())
        for link in model.links
    ]


def mapping(cache: Path) -> int:
    """§9.5: learned links against each synthetic plant's declared couplings."""
    plants: dict[str, object] = {}
    for plant in LIAR_PLANTS:
        inlet = fit_inlet(_normal(plant, cache), None, _settings())
        assert inlet.detector is not None
        learned = {(d, t) for d, t, _lags in _links(inlet.detector.plant)}
        direct, within_two = _declared_paths(plant)
        reverse = {(t, d) for d, t in within_two}
        plants[plant] = {
            "declared_pairs": len(direct),
            "recovered": len(direct & learned),
            "recovered_share": len(direct & learned) / len(direct) if direct else None,
            "learned_links": len(learned),
            "on_a_declared_path": len(learned & within_two),
            "on_a_declared_path_share": len(learned & within_two) / len(learned)
            if learned
            else None,
            "on_a_path_either_direction": len(learned & (within_two | reverse)),
            "missed": sorted(direct - learned),
            "off_path": sorted(learned - within_two),
        }
    _write("map-against-declarations", {"adr": "0123 §9.5", "plants": plants})
    return 0


def halves(data: Path) -> int:
    """§9.6: a map on each of HAI 20.07's two training files; the links both share."""
    directory = data / "hai-20.07"
    trains, _tests = HAI_20_07
    maps = []
    for name in trains:
        grid = _read_hai(directory / name, ";")
        roles = load_roles(directory / "roles.toml", grid.features)
        train = [TrainFile(values=grid.values, attack=numpy.asarray(grid.attack, dtype=bool))]
        maps.append(fit_map(train, grid.features, roles, 1.0, _settings()))
    first, second = ({(d, t): lags for d, t, lags in _links(m)} for m in maps)
    grid_lags = maps[0].lags
    shared = set(first) & set(second)
    union = set(first) | set(second)

    def steps(a: tuple[int, ...], b: tuple[int, ...]) -> int:
        return min(abs(grid_lags.index(x) - grid_lags.index(y)) for x in a for y in b)

    differ = [pair for pair in shared if steps(first[pair], second[pair]) > 1]
    _write(
        "hai-20.07-halves",
        {
            "adr": "0123 §9.6",
            "files": list(trains),
            "links": [len(first), len(second)],
            "shared": len(shared),
            "union": len(union),
            "shared_of_union": len(shared) / len(union) if union else None,
            "shared_of_smaller": len(shared) / min(len(first), len(second)) if shared else 0.0,
            "lag_differs_by_over_one_step": len(differ),
            "lag_differs_share": len(differ) / len(shared) if shared else None,
            "shared_links": sorted(f"{d} -> {t}" for d, t in shared),
        },
    )
    return 0


def replace_arm(data: Path, cache: Path) -> int:
    """The replace arm (map and range only), once on both arena slices, as diagnosis."""
    from scripts.arena import score_hai_20_07

    started = time.monotonic()
    card, _diagnoses = score_windows(
        None, ARENA_LIAR_SEEDS, cache, plant_map=DEFAULT_SETTINGS, arm=Arm.REPLACE
    )
    hai = score_hai_20_07(None, data, DEFAULT_SETTINGS, Arm.REPLACE)
    _write(
        "replace-arm",
        {
            "adr": "0123 §7 (diagnosis, not a candidate)",
            "liar": card.as_dict(),
            "hai-20.07": hai,
            "compute_seconds": round(time.monotonic() - started, 1),
        },
    )
    return 0


#: ADR 0123 §8: the ICSSim events where the plant really moves and every reading is true.
TRUE_READING_KINDS: Final = (
    "setpoint",
    "maintenance",
    "rogue_command",
    "replay",
    "mimic_maintenance",
)
LIAR_KINDS: Final = ("liar_freeze", "liar_offset")
ICSSIM_TARGET: Final = "tank_level_value"


def icssim(data: Path) -> int:
    """The ICSSim slice: liar events, naming, reconstruction and innocence (ADR 0128)."""
    corpus = data / "phos-icssim-dev"
    loaded = [load_run(d) for d in sorted(corpus.iterdir()) if (d / "manifest.json").is_file()]
    normal = [r for r in loaded if r.scenario == "normal"]
    mixed = [r for r in loaded if r.scenario == "mixed"]
    if len(normal) != 3 or len(mixed) != 10:
        raise SystemExit(f"expected 3 normal and 10 mixed runs, found {len(normal)}, {len(mixed)}")
    names = normal[0].names
    roles = load_roles(corpus / ROLES_FILE, names)
    train = [
        TrainFile(values=r.values, attack=numpy.zeros(r.time.size, dtype=bool)) for r in normal
    ]
    champion = consistency.fit(train)
    detector = fit_detector(train, names, roles, 1.0, settings=_settings())
    target = names.index(ICSSIM_TARGET)
    normal_range = float(detector.plant.high[target] - detector.plant.low[target])
    stamps = {r.name: [datetime.fromtimestamp(t).astimezone() for t in r.time] for r in mixed}
    entity = {name: EntityId(f"icssim/{name}") for name in names}
    events: list[dict[str, object]] = []
    for run in mixed:
        ours = set(detect_alerts(detector, run.values, run.time)[0])
        theirs = set(
            consistency.budget_alerts(
                consistency.events(consistency.feature_scores(champion, run.values)), run.time
            )[0]
        )
        promotion = promote_plant_map(
            detector,
            run.values,
            stamps[run.name],
            names,
            entity,
            _Unit(),
            (stamps[run.name][0], stamps[run.name][-1]),
        )
        for event in run.events:
            start, end = run.rows(event)
            inside = [r for r in promotion.records if start <= r.onset <= end]
            named = [
                names[r.naming.instrument]
                for r in inside
                if r.naming is not None
                and r.naming.verdict is Verdict.NAMED
                and r.naming.instrument is not None
            ]
            item: dict[str, object] = {
                "run": run.name,
                "kind": event.kind,
                "label": event.label,
                "caught": any(start <= row <= end for row in ours),
                "champion_caught": any(start <= row <= end for row in theirs),
                "named": named[0] if named else None,
                "plant_changed": any(
                    r.naming is not None and r.naming.verdict is Verdict.PLANT_CHANGED
                    for r in inside
                ),
            }
            if event.kind in LIAR_KINDS:
                rebuilt = reconstruct(detector.plant, run.values, target, start, end)
                if rebuilt is not None:
                    error = numpy.abs(rebuilt.centre - run.truth[start : end + 1, target])
                    known = numpy.isfinite(rebuilt.half_width)
                    item |= {
                        "near_share": float(numpy.mean(error <= NEAR_SHARE * normal_range)),
                        "covered": float(numpy.mean(error[known] <= rebuilt.half_width[known]))
                        if known.any()
                        else None,
                    }
                else:
                    item["near_share"] = None
            events.append(item)

    def share(kinds: Sequence[str], key: str) -> dict[str, object]:
        chosen = [e for e in events if e["kind"] in kinds]
        return {"events": len(chosen), key: sum(bool(e[key]) for e in chosen)}

    liars = [e for e in events if e["kind"] in LIAR_KINDS]
    caught_liars = [e for e in liars if e["caught"]]
    summary = {
        "training": [r.name for r in normal],
        "liar_caught": share(LIAR_KINDS, "caught"),
        "liar_champion_caught": share(LIAR_KINDS, "champion_caught"),
        "liar_named_right": sum(e["named"] == ICSSIM_TARGET for e in caught_liars),
        "liar_named_wrong": sum(
            e["named"] is not None and e["named"] != ICSSIM_TARGET for e in caught_liars
        ),
        "true_reading_events": share(TRUE_READING_KINDS, "caught"),
        "true_reading_named_a_liar": sum(
            e["named"] is not None for e in events if e["kind"] in TRUE_READING_KINDS
        ),
        "true_reading_plant_changed": sum(
            bool(e["plant_changed"]) for e in events if e["kind"] in TRUE_READING_KINDS
        ),
        "map_links": list(detector.plant.describe()),
    }
    _write(
        "icssim",
        {"adr": "0123 §8, §9.7, §9.8, §9.9; ADR 0128", "summary": summary, "events": events},
    )
    return 0


#: ADR 0109: the liar's zero-magnitude control. Not one of ADR 0094's subtleties.
NULL_SUBTLETY: Final = 1.0


def _null_corpus(plant: str, seed: int, cache: Path) -> AttackCorpus:
    """The arena corpus's layout with every liar at the zero-magnitude control."""
    refuse_held_out(seed)
    config = liar_corpus_config(plant, seed)
    plans = tuple(
        plan.model_copy(update={"subtlety": NULL_SUBTLETY, "attack_id": plan.attack_id + "-null"})
        for plan in config.attacks
    )
    null = config.model_copy(
        update={"name": config.name + "-null", "attacks": plans, "note": config.note + " Null."}
    )
    directory = cache / null.name
    if not (directory / ".arena-complete").is_file():
        directory = generate_attack_dataset(null, cache, with_capture=False, allow_inert=True)[0]
        (directory / ".arena-complete").write_text("")
    return load_attack_corpus(directory)


def null(cache: Path) -> int:
    """How often ADR 0094's predicate passes with no lie at all, champion and challenger.

    The arena's corpora, laid out identically, every liar at subtlety 1.0, so each 3-hour window
    holds nothing to find. A pass here is a stray fact landing in the window by chance.
    """
    settings = BreakingConfig()
    rows: dict[str, dict[str, object]] = {}
    for label, plant_map in (("champion", None), ("challenger", DEFAULT_SETTINGS)):
        passes: dict[str, int] = {}
        runs = 0
        for plant in LIAR_PLANTS:
            normal = _normal(plant, cache)
            inlet = fit_inlet(normal, None, plant_map)
            calibrator = inlet_calibrator(
                inlet, [_liar(plant, s, cache) for s in SEEDS], settings.seed
            )
            count = 0
            for seed in ARENA_LIAR_SEEDS:
                for run in run_liar_corpus(
                    _null_corpus(plant, seed, cache), normal, inlet, calibrator, settings
                ):
                    runs += 1
                    count += int(run.passes)
            passes[plant] = count
        rows[label] = {"runs": runs, "passes": sum(passes.values()), "by_plant": passes}
    _write("liar-null", {"adr": "0109's control, chance diagnosis for 0123 §9.2", **rows})
    return 0


def _first_named(
    trusted: PlantMap, values: numpy.ndarray, records: Sequence[object], start: int, end: int
) -> tuple[bool, str | None]:
    """Whether the full challenger caught the window, and the trusted map's first name in it."""
    inside = [r for r in records if start <= r.onset <= end]  # type: ignore[attr-defined]
    for record in inside:
        if record.carried_by != "map":  # type: ignore[attr-defined]
            continue
        naming = name_instrument(
            trusted,
            values,
            row=record.onset,  # type: ignore[attr-defined]
            column=record.column,  # type: ignore[attr-defined]
            onset=record.first_onset,  # type: ignore[attr-defined]
            rules=trusted.settings.naming_rules,
        )
        if naming.verdict is Verdict.NAMED and naming.instrument is not None:
            return True, trusted.names[naming.instrument]
    return bool(inside), None


def _kept_against_declarations(plant: str, kept: set[tuple[str, str]]) -> dict[str, object]:
    direct, within_two = _declared_paths(plant)
    return {
        "kept": len(kept),
        "recovered_share": len(direct & kept) / len(direct) if direct else None,
        "on_a_declared_path_share": len(kept & within_two) / len(kept) if kept else None,
    }


def graded(data: Path, cache: Path) -> int:
    """ADR 0133: ADR 0130's falsifiers 3, 4 and 5 for the trusted map, on development data."""
    settings = _settings()
    synthetic: dict[str, object] = {}
    right = wrong = caught_total = 0
    for plant in LIAR_PLANTS:
        normal = _normal(plant, cache)
        inlet = fit_inlet(normal, None, settings)
        assert inlet.detector is not None
        full = inlet.detector.plant
        names = full.names
        description = description_for(plant)
        roles = plant_roles(description)
        declared = declared_pairs(
            roles, [(link.driver, link.driven) for link in declared_links(description)]
        )
        matrix = _matrix(normal.dataset, inlet.space)
        period = float(numpy.median(numpy.diff([t.timestamp() for t in matrix.timestamps])))
        train = [TrainFile(values=matrix.values, attack=numpy.zeros(matrix.values.shape[0], bool))]
        first, second = (fit_map(h, names, roles, period, settings) for h in split_halves(train))
        stable = stable_pairs(first, second)
        allowed = trusted_drivers(full, declared)
        trusted = trusted_map(train, names, roles, period, allowed, settings)
        runs: list[dict[str, object]] = []
        for seed in _seeds():
            corpus = _liar(plant, seed, cache)
            values = _matrix(corpus.dataset, inlet.space)
            records = promote_map(inlet, corpus.dataset, _Unit()).records
            for attack in corpus.manifest.attacks:
                if attack.type is not AttackType.LIAR:
                    continue
                (target,) = attack.target_signals
                start = _row_of(values.timestamps, attack.started_at)
                end = min(_row_of(values.timestamps, attack.ended_at), len(values.timestamps) - 1)
                caught, named = _first_named(trusted, values.values, records, start, end)
                runs.append(
                    {
                        "seed": seed,
                        "subtlety": attack.subtlety,
                        "caught": caught,
                        "named": named,
                        "target": target,
                    }
                )
        caught_runs = [r for r in runs if r["caught"]]
        hits = sum(r["named"] == r["target"] for r in caught_runs)
        misses = sum(r["named"] is not None and r["named"] != r["target"] for r in caught_runs)
        right, wrong = right + hits, wrong + misses
        caught_total += len(caught_runs)
        target = str(runs[0]["target"])
        synthetic[plant] = {
            "caught": len(caught_runs),
            "named_right": hits,
            "named_wrong": misses,
            "target": target,
            "target_placed": names.index(target) in trusted.targets,
            "trusted_drivers_of_target": sorted(allowed.get(target, frozenset())),
            "trusted_targets": len(trusted.targets),
            "full_links": len(learned_pairs(full)),
            "stable_links": len(stable),
            "stable": _kept_against_declarations(plant, set(stable)),
        }
    # HAI 20.07: falsifier 3's first half, D's share of the full map's links.
    directory = data / "hai-20.07"
    trains, _tests = HAI_20_07
    grids = [_read_hai(directory / name, ";") for name in trains]
    hai_roles = load_roles(directory / "roles.toml", grids[0].features)
    hai_train = [TrainFile(values=g.values, attack=numpy.asarray(g.attack, bool)) for g in grids]
    hai_full = fit_map(hai_train, grids[0].features, hai_roles, 1.0, settings)
    hai_halves = [fit_map([f], grids[0].features, hai_roles, 1.0, settings) for f in hai_train]
    hai_stable = stable_pairs(*hai_halves) & set(learned_pairs(hai_full))
    hai_trusted = trusted_drivers(hai_full, declared_pairs(hai_roles))
    # ICSSim: A from its loops, B from logged writes, C from traffic.
    icssim_dir = data / "phos-icssim-dev"
    normal_dirs = sorted(d for d in icssim_dir.iterdir() if d.name.startswith("normal-"))
    mixed_dirs = sorted(d for d in icssim_dir.iterdir() if d.name.startswith("mixed-"))
    normal_runs = [load_run(d) for d in normal_dirs]
    icssim_names = normal_runs[0].names
    icssim_roles = load_roles(icssim_dir / ROLES_FILE, icssim_names)
    icssim_train = [
        TrainFile(values=r.values, attack=numpy.zeros(r.time.size, bool)) for r in normal_runs
    ]
    detector = fit_detector(icssim_train, icssim_names, icssim_roles, 1.0, settings=settings)
    changes = [
        c
        for i, (d, r) in enumerate(zip(normal_dirs, normal_runs, strict=True))
        for c in load_interventions(d, r, i)
    ]
    b_pairs = intervened_pairs(
        intervened_links([r.values for r in normal_runs], icssim_names, changes, 1.0)
    )
    drives: dict[str, list[str]] = {}
    for d_name, t_name in learned_pairs(detector.plant):
        drives.setdefault(d_name, []).append(t_name)
    c_pairs = network_pairs(
        network_claims([e for d in normal_dirs for e in load_exchanges(d)], icssim_roles, drives)
    )
    icssim_allowed = trusted_drivers(detector.plant, declared_pairs(icssim_roles), b_pairs, c_pairs)
    icssim_trusted = trusted_map(
        icssim_train, icssim_names, icssim_roles, 1.0, icssim_allowed, settings
    )
    icssim_right = icssim_wrong = icssim_caught = 0
    for directory_run in mixed_dirs:
        run = load_run(directory_run)
        stamps = [datetime.fromtimestamp(t).astimezone() for t in run.time]
        entity = {name: EntityId(f"icssim/{name}") for name in icssim_names}
        records = promote_plant_map(
            detector, run.values, stamps, icssim_names, entity, _Unit(), (stamps[0], stamps[-1])
        ).records
        for event in run.events:
            if event.kind not in LIAR_KINDS:
                continue
            start, end = run.rows(event)
            caught, named = _first_named(icssim_trusted, run.values, records, start, end)
            icssim_caught += int(caught)
            icssim_right += int(caught and named == ICSSIM_TARGET)
            icssim_wrong += int(caught and named is not None and named != ICSSIM_TARGET)
    pooled = caught_total + icssim_caught
    _write(
        "graded-model",
        {
            "adr": "0133 (ADR 0130 falsifiers 3, 4, 5)",
            "synthetic": synthetic,
            "hai-20.07": {
                "full_links": len(learned_pairs(hai_full)),
                "stable_links": len(hai_stable),
                "stable_share": len(hai_stable) / len(learned_pairs(hai_full)),
                "trusted_targets": sorted(hai_trusted),
            },
            "icssim": {
                "a_pairs": sorted(f"{d} -> {t}" for d, t in declared_pairs(icssim_roles)),
                "b_pairs": sorted(f"{d} -> {t}" for d, t in b_pairs),
                "c_pairs": sorted(f"{d} -> {t}" for d, t in c_pairs),
                "trusted_targets": sorted(icssim_trusted.names[t] for t in icssim_trusted.targets),
                "target_placed": icssim_names.index(ICSSIM_TARGET) in icssim_trusted.targets,
                "caught": icssim_caught,
                "named_right": icssim_right,
                "named_wrong": icssim_wrong,
            },
            "naming_pooled": {
                "caught": pooled,
                "named_right": right + icssim_right,
                "named_wrong": wrong + icssim_wrong,
                "right_share": (right + icssim_right) / pooled if pooled else None,
                "wrong_share": (wrong + icssim_wrong) / pooled if pooled else None,
            },
        },
    )
    return 0


def intervened(data: Path) -> int:
    """ADR 0132 (ADR 0130 falsifier 2): grade-B links from ICSSim's logged writes."""
    corpus = data / "phos-icssim-dev"
    normal = sorted(d for d in corpus.iterdir() if d.name.startswith("normal-"))
    runs = [load_run(d) for d in normal]
    changes = [
        c
        for i, (d, r) in enumerate(zip(normal, runs, strict=True))
        for c in load_interventions(d, r, i)
    ]
    links = intervened_links([r.values for r in runs], runs[0].names, changes, 1.0)
    true = [link for link in links if link.driven in reachable(link.driver)]
    drivers = sorted({c.point for c in changes})
    pairs = [(t, s) for t in drivers for s in runs[0].names if s != t]
    base = [pair for pair in pairs if pair[1] in reachable(pair[0])]
    _write(
        "intervened-links-icssim",
        {
            "adr": "0132 (ADR 0130 falsifier 2, grade B)",
            "training": [d.name for d in normal],
            "changes": {t: sum(c.point == t for c in changes) for t in drivers},
            "links": len(links),
            "true": len(true),
            "precision": len(true) / len(links) if links else None,
            "chance_precision": len(base) / len(pairs) if pairs else None,
            "true_pairs_found": len(true),
            "true_pairs": len(base),
            "found": [
                {
                    "driver": link.driver,
                    "driven": link.driven,
                    "responses": link.responses,
                    "changes": link.changes,
                    "on_a_true_path": link.driven in reachable(link.driver),
                }
                for link in links
            ],
        },
    )
    return 0


def network(data: Path) -> int:
    """ADR 0130 falsifier 1: grade-C claims from ICSSim's traffic, against its declared loops."""
    corpus = data / "phos-icssim-dev"
    runs = sorted(d for d in corpus.iterdir() if (d / "manifest.json").is_file())
    normal = [d for d in runs if d.name.startswith("normal-")]
    mixed = [d for d in runs if d.name.startswith("mixed-")]
    loaded = [load_run(d) for d in normal]
    names = loaded[0].names
    roles = load_roles(corpus / ROLES_FILE, names)
    train = [
        TrainFile(values=r.values, attack=numpy.zeros(r.time.size, dtype=bool)) for r in loaded
    ]
    plant = fit_map(train, names, roles, 1.0, _settings())
    drives: dict[str, list[str]] = {}
    for target, model in plant.targets.items():
        for link in model.links:
            drives.setdefault(plant.names[link.driver], []).append(plant.names[target])
    exchanges = [e for d in normal for e in load_exchanges(d)]
    hosted = {e.point: e.server for e in exchanges}
    claims = network_claims(exchanges, roles, drives)
    per_run = {
        d.name: sorted(
            f"{c.controller}:{c.point}" for c in network_claims(load_exchanges(d), roles)
        )
        for d in (*normal, *mixed)
    }
    reference = per_run[normal[0].name]
    _write(
        "network-claims-icssim",
        {
            "adr": "0130 falsifier 1 (grade C)",
            "training": [d.name for d in normal],
            "score": score_claims(claims, roles, hosted),
            "claims": [
                {
                    "controller": c.controller,
                    "point": c.point,
                    "drives_one_of": list(c.actuators),
                    "narrowed_to": c.narrowed,
                    "reads": c.reads,
                }
                for c in claims
            ],
            "runs_with_the_same_claims": sum(v == reference for v in per_run.values()),
            "runs": len(per_run),
            "claims_by_run": per_run,
        },
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one measure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "measure",
        choices=(
            "liar",
            "map",
            "halves",
            "replace",
            "icssim",
            "null",
            "network",
            "intervened",
            "graded",
        ),
    )
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "phos-arena")
    parser.add_argument("--candidate", type=Path, help="an arena candidate file to measure instead")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="ADR 0135: measure liar and graded on CONFIRM_SEEDS instead of the arena's, once",
    )
    parser.add_argument("--confirm-set", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    if args.candidate is not None:
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        settings = map_settings_from(candidate)
        if settings is None:
            raise SystemExit("--candidate must be a detector candidate (ADR 0127)")
        _RUN.update(settings=settings, label=json.dumps(candidate), tag=args.candidate.stem)
    if args.confirm:
        seeds, suffix = (
            (CONFIRM_SEEDS, "confirm")
            if args.confirm_set == 1
            else (
                CONFIRM_SEEDS_2,
                "confirm-2",
            )
        )
        _RUN.update(seeds=seeds, tag=f"{_RUN.get('tag') or 'default'}-{suffix}")
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.measure == "liar":
        return liar(args.cache)
    if args.measure == "map":
        return mapping(args.cache)
    if args.measure == "halves":
        return halves(args.data)
    if args.measure == "icssim":
        return icssim(args.data)
    if args.measure == "null":
        return null(args.cache)
    if args.measure == "network":
        return network(args.data)
    if args.measure == "intervened":
        return intervened(args.data)
    if args.measure == "graded":
        return graded(args.data, args.cache)
    return replace_arm(args.data, args.cache)


if __name__ == "__main__":
    raise SystemExit(main())
