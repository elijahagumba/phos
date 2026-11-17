"""One breaker round: search against Atlas on development seeds (PART S7).

Runs the breaker against Atlas through the referee's ``QueryInterface`` on development seeds
only, records attempts, and writes a round report.

The breaker never sees public or private seeds, and never sees sealed generator families.
The breaker reaches Atlas *only* through ``phos.referee.query.QueryInterface`` — it never
imports ``phos.atlas`` or any referee module that exposes Atlas's rules, thresholds or model
parameters.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, TypedDict

import numpy
import pandas

from phos.breaker.genome import AttackGenome, AttackShape, AttackTechnique
from phos.breaker.objective import Objective
from phos.breaker.objective import score as objective_score
from phos.breaker.search import (
    RandomSearch,
    SearchResult,
    SearchStrategy,
)
from phos.eval import Detector
from phos.referee.findings import Finding, FindingRegistry
from phos.referee.query import QueryInterface
from phos.referee.seeds import SeedEntry, SeedPool, SeedVault, assert_no_sealed_in_open_pools
from phos.synth.families import get_family
from phos.synth.outputs import GeneratedPlant, generate_plant

PRIVATE_ENV_VAR: Final = "PHOS_SEEDS_PRIVATE"
PUBLIC_ENV_VAR: Final = "PHOS_SEEDS_PUBLIC"
DEV_ENV_VAR: Final = "PHOS_SEEDS_DEV"

_HELD_OUT_TECHNIQUES: Final[set[str]] = {
    # Techniques reserved for the referee's private exam — the breaker never trains on them.
    AttackTechnique.REPLAY_COMMAND.value,
}

#: A deviation larger than this fraction of a signal's pre-attack range counts as a physical
#: effect. A sensor-layer falsification moves readings but not the true state; an actuator- or
#: process-layer attack moves the plant. The breaker observes the modified telemetry after the
#    fact — this is measurement of harm, not use of labels to evade detection.
_PHYSICAL_EFFECT_FRACTION: Final[float] = 0.20


class _ProbeResult(TypedDict):
    """Result of probing one plant with one attack genome."""

    alerts_raised: int
    detected: bool
    physical_effect: bool
    queries_used: int


@dataclass
class Attempt:
    """One attack attempt, logged append-only."""

    seed: int
    plant_id: str
    genome: AttackGenome
    objective: Objective
    queries_used: int
    detected: bool
    physical_effect: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class RoundReport:
    """The report of one breaker round."""

    round_id: str
    detector_name: str
    n_dev_seeds: int
    n_attempts: int
    n_successes: int
    n_queries: int
    new_findings: list[dict[str, object]] = field(default_factory=list)
    newly_fixed: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    open_findings: int = 0

    def to_json(self) -> str:
        """Return this report as a JSON string."""
        import json as _json

        return _json.dumps(self, default=_serialize, indent=2) + "\n"


def _serialize(obj: object) -> object:
    if isinstance(obj, AttackGenome):
        return {
            "technique": obj.technique.value,
            "target_tags": list(obj.target_tags),
            "start_time": obj.start_time,
            "duration": obj.duration,
            "intensity": obj.intensity,
            "shape": obj.shape.value,
            "layer": obj.layer,
        }
    if isinstance(obj, Objective):
        return {"stealth": obj.stealth, "harm": obj.harm, "value": obj.value}
    raise TypeError(f"cannot serialise {type(obj)!r}")


def _dev_seed_entries(vault: SeedVault) -> list[SeedEntry]:
    """Return development seed entries, excluding any that also appear in public/private pools."""
    assert_no_sealed_in_open_pools(vault)
    entries = vault.load(SeedPool.DEV)
    public_keys = {e.key() for e in vault.load(SeedPool.PUBLIC)}
    private_keys = {e.key() for e in vault.load(SeedPool.PRIVATE)}
    return [e for e in entries if e.key() not in public_keys and e.key() not in private_keys]


def _refuses_held_out(techniques: set[AttackTechnique]) -> None:
    """Raise if any held-out technique is present — the breaker never sees them."""
    held_out = {t for t in techniques if t.value in _HELD_OUT_TECHNIQUES}
    if held_out:
        raise ValueError(
            f"breaker attempted to use held-out technique(s): {sorted(t.value for t in held_out)}; "
            "these are for the referee's private exam only"
        )


def run_round(
    detector: Detector,
    vault: SeedVault,
    *,
    budget_per_plant: int = 50,
    n_plants: int = 5,
    search_strategy: SearchStrategy | None = None,
    seed: int = 20261116,
    work_dir: Path | None = None,
    findings_dir: Path | None = None,
) -> RoundReport:
    """Run one breaker round against ``detector`` on development seeds.

    The detector is queried only through ``QueryInterface`` — the breaker never sees Atlas
    internals.
    """
    if work_dir is None:
        work_dir = Path(f"breaker-round-{seed}")
    work_dir.mkdir(parents=True, exist_ok=True)

    registry: FindingRegistry | None = None
    if findings_dir is not None:
        registry = FindingRegistry(findings_dir)

    rng = random.Random(seed)

    if search_strategy is None:
        tag_pool = tuple(_dev_tag_pool())
        allowed_techniques = tuple(
            t for t in AttackTechnique if t.value not in _HELD_OUT_TECHNIQUES
        )
        search_strategy = RandomSearch(
            rng=rng,
            tag_pool=tag_pool,
            techniques=allowed_techniques,
            hours=24.0,
        )

    _refuses_held_out(_techniques_of(search_strategy))

    entries = _dev_seed_entries(vault)
    chosen = entries[:n_plants]

    attempts: list[Attempt] = []
    total_queries = 0
    successes = 0

    for entry in chosen:
        family = get_family(entry.family)
        plant = generate_plant(
            family,
            entry.seed,
            work_dir / f"plant-{entry.seed}",
            hours=24.0,
            events=None,
            event_seed=entry.seed,
        )
        interface = QueryInterface(detector, budget=budget_per_plant)

        for _ in range(budget_per_plant):
            try:
                genome = search_strategy.next_genome()
            except Exception:
                break

            result = _probe_plant(interface, plant, genome)
            total_queries += result["queries_used"]

            objective = objective_score(
                alerts_raised=result["alerts_raised"],
                max_alerts=budget_per_plant,
                physical_effect=result["physical_effect"],
            )
            attempt = Attempt(
                seed=entry.seed,
                plant_id=plant.manifest.plant_id,
                genome=genome,
                objective=objective,
                queries_used=result["queries_used"],
                detected=result["detected"],
                physical_effect=result["physical_effect"],
            )
            attempts.append(attempt)

            search_strategy.record(
                SearchResult(genome=genome, objective=objective, queries=result["queries_used"])
            )

            if objective.value > 0.5 and not result["detected"] and result["physical_effect"]:
                successes += 1
                if registry is not None:
                    finding = Finding.create(
                        source=f"breaker-round-{seed}",
                        plant_spec_hash=plant.manifest.plant_id,
                        seed=entry.seed,
                        family=entry.family,
                        attack_genome=genome,
                        what_happened=(
                            f"{genome.technique.value} attack on {', '.join(genome.target_tags)} "
                            f"starting at t={genome.start_time:.0f}s, shape={genome.shape.value}, "
                            f"layer={genome.layer}, intensity={genome.intensity:.1f}"
                        ),
                        atlas_output="no alerts raised",
                        why_missed="unknown — Atlas raised no alert during the attack window",
                        physical_harm=True,
                        stealthy=True,
                    )
                    registry.add(finding)

    report = RoundReport(
        round_id=_round_hash(seed, attempts),
        detector_name=getattr(detector, "name", "unknown"),
        n_dev_seeds=len(chosen),
        n_attempts=len(attempts),
        n_successes=successes,
        n_queries=total_queries,
        open_findings=0,
    )

    _write_attempts(attempts, work_dir / "attempts.jsonl")
    return report


def _round_hash(seed: int, attempts: list[Attempt]) -> str:
    digest = hashlib.sha256()
    digest.update(str(seed).encode("utf-8"))
    for attempt in attempts:
        digest.update(attempt.genome.technique.value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _dev_tag_pool() -> list[str]:
    """Default tag pool for development searches."""
    return ["tank_level", "outlet_flow", "inlet_valve", "pump_status", "tank_temperature"]


def _techniques_of(strategy: SearchStrategy) -> set[AttackTechnique]:
    """Best-effort extraction of which techniques a strategy may draw from."""
    techniques: set[AttackTechnique] = set()
    for attr in ("techniques", "_techniques"):
        value = getattr(strategy, attr, None)
        if value is not None:
            techniques.update(value)
    return techniques


def _inject_attack(
    frame: pandas.DataFrame,
    mask: pandas.Series,
    genome: AttackGenome,
    valid_tags: list[str],
) -> None:
    """Modify ``frame`` in place, applying ``genome`` to ``valid_tags`` during ``mask``.

    The injection changes the reported signal values (telemetry) that Atlas would read. It does
    not change the label column or the schedule — the breaker never publishes ground truth.
    """
    for tag in valid_tags:
        baseline = frame.loc[~mask, tag]
        if baseline.empty:
            continue
        base_mean = float(baseline.mean())
        window_count = int(mask.sum())
        if window_count == 0:
            continue

        indices = frame.index[mask]
        if genome.shape is AttackShape.STEP:
            frame.loc[indices, tag] = base_mean + genome.intensity
        elif genome.shape is AttackShape.RAMP:
            ramp = numpy.linspace(0.0, genome.intensity, window_count)
            frame.loc[indices, tag] = base_mean + ramp
        elif genome.shape is AttackShape.PULSE:
            # Intensity in the middle third of the window.
            third = max(1, window_count // 3)
            pulse_idx = indices[third : 2 * third]
            frame.loc[pulse_idx, tag] = base_mean + genome.intensity
        elif genome.shape is AttackShape.REPLAY:
            # Repeat a segment from immediately before the window.
            pre = baseline.values
            if len(pre) >= window_count:
                replay = pre[-window_count:]
                frame.loc[indices, tag] = replay


def _assess_physical_effect(
    frame: pandas.DataFrame,
    mask: pandas.Series,
    genome: AttackGenome,
    valid_tags: list[str],
) -> bool:
    """Return whether the attack moved the plant's state, not just its reported readings.

    A sensor-layer falsification changes what instruments report but not true state; an
    actuator- or process-layer attack moves the plant. We observe this after the fact from the
    modified telemetry: if any target tag deviates from its pre-attack baseline by more than
    ``_PHYSICAL_EFFECT_FRACTION`` of its pre-attack range, the plant moved.
    """
    for tag in valid_tags:
        baseline = frame.loc[~mask, tag]
        if baseline.empty:
            continue
        pre_mean = float(baseline.mean())
        pre_min = float(baseline.min())
        pre_max = float(baseline.max())
        pre_range = pre_max - pre_min
        if pre_range <= 0:
            continue
        attacked = frame.loc[mask, tag]
        max_dev = float((attacked - pre_mean).abs().max())
        if max_dev > _PHYSICAL_EFFECT_FRACTION * pre_range:
            return True
    return False


def _probe_plant(
    interface: QueryInterface, plant: GeneratedPlant, genome: AttackGenome
) -> _ProbeResult:
    """Inject ``genome`` into the plant's telemetry and ask Atlas what it sees.

    The breaker copies the plant to a temporary directory, modifies ``telemetry.csv`` to apply
    the attack (step/ramp/pulse/replay on target tags during the attack window), and queries
    Atlas through the ``QueryInterface`` on the modified copy. The original plant on disk is
    never changed, so each query starts from a clean plant.

    Returns the number of alerts Atlas raised, whether it detected anything, whether the attack
    produced a physical effect, and how many queries were used.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="phos-break-probe-"))
    try:
        shutil.copytree(plant.directory, tmp_dir, dirs_exist_ok=True)

        telemetry_path = tmp_dir / "telemetry.csv"
        frame = pandas.read_csv(telemetry_path)
        time_col = "timestamp"
        times = pandas.to_datetime(frame[time_col], utc=True)
        value_cols = [c for c in frame.columns if c not in (time_col, "label")]

        # The plant ran for 24 hours starting at run_start. The genome's start_time and
        # duration are seconds into that run. Map them onto the actual timestamps.
        run_start = times.iloc[0]
        window_start = run_start + timedelta(seconds=genome.start_time)
        window_end = window_start + timedelta(seconds=genome.duration)
        mask = (times >= window_start) & (times < window_end)

        # Only target tags that exist in this plant's telemetry can be attacked.
        # The genome's tag names are generic (tank_level, outlet_flow, ...); each plant's
        # columns are its own (WTW-LT-1, WTW-FT-1, ...). Map by position so every genome
        # gets at least one real tag to attack.
        valid_tags = [tag for tag in genome.target_tags if tag in value_cols]
        if not valid_tags and value_cols:
            valid_tags = value_cols[: len(genome.target_tags)]

        if mask.sum() == 0 or not valid_tags:
            # No window in range, or no target tags exist in this plant — nothing to inject.
            result = interface.ask(plant)
            return {
                "alerts_raised": len(result.detections),
                "detected": len(result.detections) > 0,
                "physical_effect": False,
                "queries_used": result.queries_used,
            }

        # Apply the attack to reported telemetry.
        _inject_attack(frame, mask, genome, valid_tags)
        frame.to_csv(telemetry_path, index=False)

        # Assess physical effect from the modified telemetry — did the attack move the plant?
        physical_effect = _assess_physical_effect(frame, mask, genome, valid_tags)

        modified_plant = dataclasses.replace(plant, directory=tmp_dir)
        result = interface.ask(modified_plant)

        return {
            "alerts_raised": len(result.detections),
            "detected": len(result.detections) > 0,
            "physical_effect": physical_effect,
            "queries_used": result.queries_used,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _write_attempts(attempts: list[Attempt], path: Path) -> None:
    """Append attempts to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for attempt in attempts:
            handle.write(
                json.dumps(
                    {
                        "seed": attempt.seed,
                        "plant_id": attempt.plant_id,
                        "genome": attempt.genome,
                        "objective": attempt.objective,
                        "queries_used": attempt.queries_used,
                        "detected": attempt.detected,
                        "physical_effect": attempt.physical_effect,
                        "timestamp": attempt.timestamp,
                    },
                    default=_serialize,
                )
                + "\n"
            )


__all__ = [
    "DEV_ENV_VAR",
    "PRIVATE_ENV_VAR",
    "PUBLIC_ENV_VAR",
    "Attempt",
    "RoundReport",
    "run_round",
]
