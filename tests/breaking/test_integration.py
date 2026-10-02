"""End to end: a hand-built corpus pair driven through the whole harness.

Everything here is written to ``tmp_path`` rather than read from ``data/``. The generated corpora
are git-ignored, so a test that loaded one would pass only on a machine that had just run the
generators. The cost is that the plant is a toy; the benefit is that the orchestration — fold
splitting, fitting on a separate normal corpus, cross-fitting the calibrator, running the vertical,
scoring each attack against the true state, and pooling the false-positive load — is exercised
everywhere.
"""

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.breaking.conftest import signal

from phos.breaking.corpus import (
    CorpusNotFoundError,
    discover_attack_corpora,
    load_attack_corpus,
    load_normal_corpus,
)
from phos.breaking.harness import BreakingConfig, run_breaking
from phos.breaking.outcome import DetectionVerdict
from phos.breaking.robustness import run_robustness
from phos.synth import PlantDescription
from phos.synth.attacks import AttackFlavour, AttackGroundTruth, AttackType
from phos.synth.plant import Coupling, CouplingKind, PhysicalUnit, SignalKind

SAMPLES = 480
STEP = timedelta(minutes=3)
"""Twenty-four hours at three-minute sampling: two folds of twelve hours each."""

SIGNALS = ("inflow_m3ph", "level_m", "pump_pct")

BENIGN_SAMPLES = frozenset(range(120, 128)) | frozenset(range(300, 308))
"""Indices carrying a mild, *labelled-normal* operational bump — one in each fold.

D1's plants schedule genuine benign events (a filter backwash, a pump changeover) and Atlas's false
positives land on them. Without something like that in the fixture the model fits normal data
exactly, the calibration slice holds only attack-class candidates, and the cross-fit cannot be done
— which is a property of a toy corpus, not of the harness. These bumps are far smaller than an
attack's and fall outside every attack window.
"""


def run_start() -> datetime:
    """The first sample instant, in UTC."""
    return datetime(2026, 5, 1, tzinfo=UTC)


def toy_plant() -> PlantDescription:
    """A three-signal plant: one drifting sensor, one driftless sensor, one actuator."""
    return PlantDescription(
        plant_id="toy",
        label="Toy works",
        industry="testing",
        summary="Three signals on two units, enough for a joint model to have structure.",
        model_source="Hand-built for tests; models nothing real.",
        units=(
            PhysicalUnit(unit_id="intake", label="Intake"),
            PhysicalUnit(unit_id="storage", label="Storage"),
        ),
        signals=(
            signal("inflow_m3ph", SignalKind.SENSOR, noise=0.5, drift=0.4, unit_id="intake"),
            signal("level_m", SignalKind.SENSOR, noise=0.02, drift=0.0, unit_id="storage"),
            signal("pump_pct", SignalKind.ACTUATOR, noise=0.2, drift=0.0, unit_id="intake"),
        ),
        couplings=(
            Coupling(
                driven="level_m",
                drivers=("inflow_m3ph",),
                kind=CouplingKind.INTEGRATION,
                relation="level integrates inflow",
            ),
        ),
    )


def series(
    index: int,
    *,
    disturbed: bool = False,
    offset: float = 0.0,
    benign: bool = False,
    along_manifold: bool = False,
) -> dict[str, float]:
    """One sample of the toy plant: a daily sinusoid with per-signal deterministic wobbles.

    ``disturbed`` pushes the whole sample far outside the learned structure, which is what an attack
    window contains. ``offset`` shifts the wobble phases, so the normal corpus and the attacked one
    are *different runs* of the plant rather than the same numbers twice — which is what makes the
    fitted model imperfect on normal data, exactly as it is on a real pair of D1 corpora, and is
    what gives the calibration slice normal-class candidates to learn from.

    Deterministic — no randomness anywhere, so two runs agree (Constitution §3.7).
    """
    phase = 2.0 * math.pi * index / SAMPLES + offset
    along = along_manifold and disturbed
    # Each signal gets its own incommensurable wobble. A shared one would make the three perfectly
    # correlated, the covariance singular, and the joint model degenerate — which is a property of
    # the fixture rather than of Atlas, and would make this test measure the wrong thing.
    pump = 50.0 + 10.0 * math.sin(phase) + 0.30 * math.sin(7.0 * phase)
    inflow = 2.0 * pump + 0.90 * math.sin(13.0 * phase + 0.7)
    level = 3.0 + 0.5 * math.sin(phase) + 0.04 * math.sin(17.0 * phase + 1.9)
    if benign:
        # A real operational event: enough to leave the learned structure, nowhere near an attack.
        pump += 3.0
        inflow += 1.5
        level -= 0.25
    if disturbed:
        # Deliberately BREAKS the declared 2:1 inflow/pump relation: the pump runs hard while the
        # inflow barely moves. That is what a joint model is for. Moving both together — inflow to
        # exactly 2 x pump — would be an excursion *along* the learned correlation, which Atlas is
        # designed not to flag; `test_an_excursion_along_the_learned_correlations_is_not_flagged`
        # holds that case, because it is the engine's central claim rather than a bug.
        pump += 35.0
        inflow += 70.0 if along else 5.0
        level += 0.0 if along else 2.5
    return {"inflow_m3ph": inflow, "level_m": level, "pump_pct": pump}


def write_corpus(
    directory: Path,
    plant: PlantDescription,
    *,
    attacks: tuple[AttackGroundTruth, ...] = (),
    hostile: tuple[object, ...] = (),
    flavour: AttackFlavour = AttackFlavour.DETECTION,
    disturb: bool = True,
    offset: float = 0.0,
    along_manifold: bool = False,
) -> None:
    """Write a complete corpus — telemetry, truth, topology and manifest — to ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    windows = [truth.interval() for truth in attacks]

    telemetry = ["timestamp,label," + ",".join(SIGNALS)]
    truth_rows = ["timestamp," + ",".join(SIGNALS)]
    for index in range(SAMPLES):
        stamp = run_start() + index * STEP
        inside = any(window.contains(stamp) for window in windows)
        values = series(
            index,
            disturbed=inside and disturb,
            offset=offset,
            benign=disturb and index in BENIGN_SAMPLES,
            along_manifold=along_manifold,
        )
        cells = ",".join(f"{values[key]:.5f}" for key in SIGNALS)
        telemetry.append(f"{stamp.isoformat()},{int(inside)},{cells}")
        truth_rows.append(f"{stamp.isoformat()},{cells}")
    (directory / "telemetry.csv").write_text("\n".join(telemetry) + "\n", encoding="utf-8")
    (directory / "truth.csv").write_text("\n".join(truth_rows) + "\n", encoding="utf-8")

    (directory / "topology.toml").write_text(
        "schema_version = 1\n"
        f'corpus = "{plant.plant_id}"\n\n'
        "[[subsystems]]\n"
        'subsystem_id = "intake"\n'
        'label = "Intake"\n'
        'source = "Declared by the test fixture."\n'
        'signals = ["inflow_m3ph", "pump_pct"]\n\n'
        "[[subsystems]]\n"
        'subsystem_id = "storage"\n'
        'label = "Storage"\n'
        'source = "Declared by the test fixture."\n'
        'signals = ["level_m"]\n',
        encoding="utf-8",
    )

    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "name": directory.name,
                "plant_id": plant.plant_id,
                "flavour": flavour.value,
                "spec": {
                    "seed": 1,
                    "start": run_start().isoformat(),
                    "duration": "PT24H",
                    "sample_interval": "PT3M",
                },
                "samples": SAMPLES,
                "description": plant.model_dump(mode="json"),
                "attacks": [truth.model_dump(mode="json") for truth in attacks],
                "hostile": list(hostile),
            }
        ),
        encoding="utf-8",
    )


def write_normal(directory: Path, plant: PlantDescription) -> None:
    """Write an attack-free corpus of the same plant, as D1 would."""
    write_corpus(
        directory,
        plant,
        attacks=(),
        flavour=AttackFlavour.DETECTION,
        disturb=False,
        offset=0.35,
    )
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["attacks"] = []
    # D1's own manifests carry no flavour, so drop it: `load_normal_corpus` reads raw JSON.
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def attack(
    attack_id: str,
    attack_type: AttackType,
    *,
    subtlety: float,
    start_hours: float,
    targets: tuple[str, ...],
    duration_hours: float = 1.0,
    issuer: str = "",
) -> AttackGroundTruth:
    """Ground truth for one attack, as D2's manifest would record it."""
    started = run_start() + timedelta(hours=start_hours)
    return AttackGroundTruth(
        attack_id=attack_id,
        type=attack_type,
        subtlety=subtlety,
        started_at=started,
        ended_at=started + timedelta(hours=duration_hours),
        target_signals=targets,
        issuer=issuer,
        manipulation=f"{attack_type.value} on {', '.join(targets)}",
        physical_effect=True,
    )


@pytest.fixture
def corpora(tmp_path: Path) -> tuple[Path, Path]:
    """A battery with one attack in each fold, plus a separate normal corpus to fit on."""
    plant = toy_plant()
    attacked = tmp_path / "synth-attack-toy-graded"
    normal = tmp_path / "synth-toy-train"
    write_corpus(
        attacked,
        plant,
        attacks=(
            attack(
                "early-blatant",
                AttackType.BLATANT,
                subtlety=0.0,
                start_hours=3.0,
                targets=("pump_pct",),
            ),
            attack(
                "late-blatant",
                AttackType.BLATANT,
                subtlety=0.5,
                start_hours=18.0,
                targets=("pump_pct",),
            ),
        ),
    )
    write_normal(normal, plant)
    return attacked, normal


def test_the_whole_harness_runs_and_scores_every_attack(corpora: tuple[Path, Path]) -> None:
    """The orchestration end to end: two folds, two attacks, each scored exactly once."""
    attacked, normal = corpora
    breakdown = run_breaking(
        load_attack_corpus(attacked),
        load_normal_corpus(normal),
        BreakingConfig(measure_commands=False),
    )
    assert breakdown.corpus == "synth-attack-toy-graded"
    assert breakdown.plant_id == "toy"
    assert breakdown.fit_corpus == "synth-toy-train"
    assert {o.attack_id for o in breakdown.outcomes} == {"early-blatant", "late-blatant"}
    assert breakdown.unscored == ()
    # One attack per fold, so both were scored out of their own calibration slice.
    assert breakdown.report.n_attack_intervals == 2


def test_a_blatant_attack_on_a_well_fitted_baseline_is_caught(
    corpora: tuple[Path, Path],
) -> None:
    """Not a claim about Atlas in general — a check that the pipeline can reach CAUGHT at all."""
    attacked, normal = corpora
    breakdown = run_breaking(
        load_attack_corpus(attacked),
        load_normal_corpus(normal),
        BreakingConfig(measure_commands=False),
    )
    verdicts = {o.attack_id: o.verdict for o in breakdown.outcomes}
    assert DetectionVerdict.CAUGHT in verdicts.values()


def test_the_run_is_deterministic(corpora: tuple[Path, Path]) -> None:
    """Same corpora, same config, same map (Constitution §3.7)."""
    attacked, normal = corpora
    config = BreakingConfig(measure_commands=False)
    first = run_breaking(load_attack_corpus(attacked), load_normal_corpus(normal), config)
    second = run_breaking(load_attack_corpus(attacked), load_normal_corpus(normal), config)
    assert [(o.attack_id, o.verdict, o.n_alerts) for o in first.outcomes] == [
        (o.attack_id, o.verdict, o.n_alerts) for o in second.outcomes
    ]
    assert first.report.false_positive_rate == second.report.false_positive_rate


def test_the_false_positive_load_comes_from_the_harness(corpora: tuple[Path, Path]) -> None:
    """Reuse, not reimplementation: the rate is `phos.eval`'s, over hours of normal operation."""
    attacked, normal = corpora
    breakdown = run_breaking(
        load_attack_corpus(attacked),
        load_normal_corpus(normal),
        BreakingConfig(measure_commands=False),
    )
    assert breakdown.report.normal_hours > 0.0
    assert breakdown.report.false_positive_rate >= 0.0
    assert breakdown.report.detector_name.startswith("atlas-vertical:")


def test_fitting_on_another_plant_is_refused(corpora: tuple[Path, Path], tmp_path: Path) -> None:
    """A baseline from a different machine describes different signals."""
    attacked, _ = corpora
    other = tmp_path / "synth-elsewhere-train"
    plant = toy_plant().model_copy(update={"plant_id": "elsewhere"})
    write_normal(other, plant)
    with pytest.raises(ValueError, match="another machine"):
        run_breaking(load_attack_corpus(attacked), load_normal_corpus(other), BreakingConfig())


def test_an_input_hostile_corpus_is_refused_for_detection(tmp_path: Path) -> None:
    """Scoring one for recall would compute a rate over nothing.

    The type split is not enough here, because the corpus object is the same type either way — so
    the runner refuses it explicitly.
    """
    plant = toy_plant()
    directory = tmp_path / "synth-hostile-toy"
    write_corpus(directory, plant, attacks=(), flavour=AttackFlavour.INPUT_HOSTILE)
    normal = tmp_path / "synth-toy-train"
    write_normal(normal, plant)
    with pytest.raises(ValueError, match="input-hostile corpus is measured for robustness"):
        run_breaking(load_attack_corpus(directory), load_normal_corpus(normal), BreakingConfig())


def test_a_corpus_attacked_end_to_end_cannot_be_cross_fitted(tmp_path: Path) -> None:
    """No gap near the midpoint means no calibration slice can be held out. Refused, not fudged."""
    plant = toy_plant()
    directory = tmp_path / "synth-attack-toy-saturated"
    write_corpus(
        directory,
        plant,
        attacks=(
            attack(
                "everything",
                AttackType.BLATANT,
                subtlety=0.0,
                start_hours=0.0,
                targets=("pump_pct",),
                duration_hours=24.0,
            ),
        ),
    )
    normal = tmp_path / "synth-toy-train"
    write_normal(normal, plant)
    with pytest.raises(ValueError, match="cannot be split into two folds"):
        run_breaking(load_attack_corpus(directory), load_normal_corpus(normal), BreakingConfig())


# --- loading -------------------------------------------------------------


def test_discovery_finds_corpora_and_respects_a_name_filter(tmp_path: Path) -> None:
    plant = toy_plant()
    for name in ("synth-attack-toy-a", "synth-attack-toy-b"):
        write_corpus(
            tmp_path / name,
            plant,
            attacks=(
                attack(
                    "a", AttackType.BLATANT, subtlety=0.0, start_hours=3.0, targets=("pump_pct",)
                ),
            ),
        )
    assert len(discover_attack_corpora(tmp_path)) == 2
    found = discover_attack_corpora(tmp_path, ("synth-attack-toy-b",))
    assert [path.name for path in found] == ["synth-attack-toy-b"]
    assert discover_attack_corpora(tmp_path, ("nope",)) == ()


def test_a_missing_corpus_names_the_generator_that_would_produce_it(tmp_path: Path) -> None:
    with pytest.raises(CorpusNotFoundError, match=r"generate_attacks\.py"):
        load_attack_corpus(tmp_path / "not-there")
    with pytest.raises(CorpusNotFoundError, match=r"generate_synth\.py"):
        load_normal_corpus(tmp_path / "not-there-either")


def test_the_subsystem_map_loads_against_the_plant_id(corpora: tuple[Path, Path]) -> None:
    """D1 writes one topology per plant, shared by every corpus of it."""
    attacked, _ = corpora
    corpus = load_attack_corpus(attacked)
    subsystem_map = corpus.subsystem_map()
    assert {s.subsystem_id for s in subsystem_map.subsystems} == {"intake", "storage"}


def test_a_loaded_corpus_reports_its_flavour(corpora: tuple[Path, Path]) -> None:
    attacked, _ = corpora
    assert load_attack_corpus(attacked).flavour is AttackFlavour.DETECTION


# --- robustness over a real corpus ---------------------------------------


def test_a_readable_hostile_corpus_completes_and_is_measured_per_case(tmp_path: Path) -> None:
    plant = toy_plant()
    directory = tmp_path / "synth-hostile-toy"
    write_corpus(
        directory,
        plant,
        flavour=AttackFlavour.INPUT_HOSTILE,
        hostile=(
            {
                "attack_id": "poison",
                "type": "POISONED_BASELINE",
                "target": "level_m",
                "description": "fitting window contaminated",
                "rows_affected": 40,
            },
        ),
    )
    normal = tmp_path / "synth-toy-train"
    holdout = tmp_path / "synth-toy-holdout"
    write_normal(normal, plant)
    write_normal(holdout, plant)

    result = run_robustness(directory, load_normal_corpus(normal), load_normal_corpus(holdout))
    assert result.loaded
    assert result.all_safe
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.attack_type is AttackType.POISONED_BASELINE
    # The one number that separates "survived" from "silently went wrong".
    assert outcome.baseline_shift is not None
    assert 0.0 <= outcome.baseline_shift <= 1.0


def test_an_excursion_along_the_learned_correlations_is_not_flagged(tmp_path: Path) -> None:
    """Atlas's central claim, exercised through the harness rather than asserted about it.

    Here the pump runs hard AND the inflow follows it at exactly the learned 2:1 ratio. Every signal
    is far from its own usual value, and the plant is still the machine Atlas learned — so a joint
    model reconstructs the reading and does not alert, where a per-signal threshold would have fired
    on all three. The harness scores that as a miss, which is the honest answer: the attack was in
    the corpus and Atlas did not report it. What the row means is that this attack did not break the
    structure Atlas watches, and a reader of the map needs that distinction.
    """
    plant = toy_plant()
    attacked = tmp_path / "synth-attack-toy-alongmanifold"
    normal = tmp_path / "synth-toy-train"
    write_corpus(
        attacked,
        plant,
        attacks=(
            attack(
                "along-manifold",
                AttackType.BLATANT,
                subtlety=0.0,
                start_hours=3.0,
                targets=("pump_pct",),
            ),
            attack(
                "along-manifold-late",
                AttackType.BLATANT,
                subtlety=0.5,
                start_hours=18.0,
                targets=("pump_pct",),
            ),
        ),
        along_manifold=True,
    )
    write_normal(normal, plant)

    breakdown = run_breaking(
        load_attack_corpus(attacked),
        load_normal_corpus(normal),
        BreakingConfig(measure_commands=False),
    )
    assert all(not outcome.detected for outcome in breakdown.outcomes)
    assert all(outcome.is_miss for outcome in breakdown.outcomes)
