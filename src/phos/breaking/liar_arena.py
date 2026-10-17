"""The liar slice of the arena: a candidate window set scored on declared development seeds.

Stage S3 of `docs/learning-engine.md` (ADR 0120). A candidate is a `Windows` set in seconds,
converted by ADR 0112's rule (`scale_windows`) and fitted exactly as T1 fits the frozen inlet;
``None`` is the champion, `atlas-v1-consistency`'s own windows. Every run goes through
`phos.breaking.liar_diagnosis.diagnose_corpus`, so a scorecard carries pass counts *and* why each
failure failed.

**The seeds are development seeds, declared here before any arena run.** `ARENA_LIAR_SEEDS` score
candidates. `RED_TEAM_SEEDS` are kept back: no candidate is scored on them until one has been
chosen, so they can check it on runs its search never saw. Both are disjoint from T1's held-out
seeds and from the calibration seeds, which a test checks. All figures are synthetic (R4).
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from phos.atlas.consistency_windows import Windows
from phos.atlas.plant_map_detector import Arm
from phos.atlas.plant_map_model import MapSettings
from phos.breaking.corpus import AttackCorpus, NormalCorpus, load_attack_corpus, load_normal_corpus
from phos.breaking.harness import BreakingConfig
from phos.breaking.liar import fit_inlet, inlet_calibrator, liar_corpus_config
from phos.breaking.liar_diagnosis import LiarDiagnosis, diagnose_corpus, refuse_held_out
from phos.eval.liar_declaration import LIAR_PLANTS
from phos.library.ot import SEEDS, ot_trains
from phos.synth.attacks.generate import generate_attack_dataset
from phos.synth.generate import generate_dataset

__all__ = [
    "ARENA_LIAR_SEEDS",
    "CHURN_SHARE",
    "CONFIRM_SEEDS",
    "CONFIRM_SEEDS_2",
    "CONFIRM_SEEDS_3",
    "RED_TEAM_SEEDS",
    "LiarScorecard",
    "regressions",
    "score_windows",
    "within_churn",
]

#: Development seeds every candidate is scored on: ADR 0114's test seed and four new ones.
ARENA_LIAR_SEEDS: Final = (4242, 95001, 95002, 95003, 95004)
#: Development seeds kept back for the red team, scored only after a candidate is chosen.
RED_TEAM_SEEDS: Final = tuple(range(95101, 95111))
#: A second held-back set (ADR 0135), for a candidate declared after the first red team ran.
CONFIRM_SEEDS: Final = tuple(range(95201, 95211))
#: A third (ADR 0137), for the candidate declared after the second was spent.
CONFIRM_SEEDS_2: Final = tuple(range(95301, 95311))
#: A fourth (ADR 0139), judged by its forward rule, for attempt 6 unchanged.
CONFIRM_SEEDS_3: Final = tuple(range(95401, 95411))
#: ADR 0139: the champion's own churn when its corpora are regenerated (ADR 0134: 3 of its 52
#: red-team passes did not repeat). A challenger may lose at most this share of the champion's.
CHURN_SHARE: Final = (3, 52)

_DONE: Final = ".arena-complete"


@dataclass(frozen=True)
class LiarScorecard:
    """What one window set did on the liar slice.

    Attributes:
        seeds: The seeds scored.
        passing: ``(plant, seed, subtlety)`` for every run that met ADR 0094's predicate.
        mechanisms: How many runs each `LIAR_PRECEDENCE` clause decided.
        runs: Scored and unscored runs in total.
        seconds: Wall time.
        unmeasurable: Corpora the harness could not cross-fit, for every detector (ADR 0137).
    """

    seeds: tuple[int, ...]
    passing: frozenset[tuple[str, int, float]]
    mechanisms: dict[str, int]
    runs: int
    seconds: float
    unmeasurable: tuple[str, ...] = ()

    def passes_by_plant(self) -> dict[str, int]:
        """Passing runs per plant, every liar plant present."""
        counts = Counter(plant for plant, _seed, _subtlety in self.passing)
        return {plant: counts.get(plant, 0) for plant in LIAR_PLANTS}

    def as_dict(self) -> dict[str, object]:
        """A JSON-ready form for an attempt's scorecard."""
        return {
            "seeds": list(self.seeds),
            "runs": self.runs,
            "passes": len(self.passing),
            "passes_by_plant": self.passes_by_plant(),
            "passing": sorted([list(item) for item in self.passing]),
            "mechanisms": dict(sorted(self.mechanisms.items())),
            "seconds": round(self.seconds, 1),
            **({"unmeasurable": list(self.unmeasurable)} if self.unmeasurable else {}),
        }


def within_churn(champion: LiarScorecard, candidate: LiarScorecard) -> bool:
    """ADR 0139's forward rule: losses within the champion's own churn, and gains beyond it.

    The candidate may lose at most ``floor(3/52 x champion passes)`` of the champion's
    passes, and must pass more than the champion by more than that allowance.
    """
    lost_part, of = CHURN_SHARE
    allowed = lost_part * len(champion.passing) // of
    lost = len(regressions(champion, candidate))
    return lost <= allowed and len(candidate.passing) > len(champion.passing) + allowed


def regressions(champion: LiarScorecard, candidate: LiarScorecard) -> list[tuple[str, int, float]]:
    """Runs the champion passes and the candidate does not, on seeds both scored."""
    shared = set(champion.seeds) & set(candidate.seeds)
    lost = {item for item in champion.passing if item[1] in shared} - candidate.passing
    return sorted(lost)


def _normal(plant: str, cache: Path) -> NormalCorpus:
    config = next(c for c in ot_trains() if c.plant_id == plant)
    directory = cache / config.name
    if not (directory / _DONE).is_file():
        directory = generate_dataset(config, cache, with_capture=False)[0]
        (directory / _DONE).write_text("")
    return load_normal_corpus(directory)


def _liar(plant: str, seed: int, cache: Path) -> AttackCorpus:
    refuse_held_out(seed)
    config = liar_corpus_config(plant, seed)
    directory = cache / config.name
    if not (directory / _DONE).is_file():
        directory = generate_attack_dataset(config, cache, with_capture=False)[0]
        (directory / _DONE).write_text("")
    return load_attack_corpus(directory)


def score_windows(
    base: Windows | None,
    seeds: Iterable[int],
    cache: Path,
    plants: Sequence[str] = LIAR_PLANTS,
    plant_map: MapSettings | None = None,
    arm: Arm = Arm.EXTEND,
) -> tuple[LiarScorecard, list[LiarDiagnosis]]:
    """Score one window set on the liar slice and diagnose every run.

    Args:
        base: A window set in seconds, or ``None`` for the champion's.
        seeds: Development seeds to score. A held-out seed raises before anything is generated.
        cache: Where generated corpora are kept between attempts. Never committed.
        plants: The liar plants to score.
        plant_map: Score `atlas-plant-map-v1` with these settings instead (ADR 0127).
        arm: The challenger's arm; the replace arm is diagnosis only.

    Raises:
        ValueError: If a seed is held out.
    """
    chosen = tuple(seeds)
    for seed in chosen:
        refuse_held_out(seed)
    started = time.monotonic()
    settings = BreakingConfig()
    diagnoses: list[LiarDiagnosis] = []
    unmeasurable: list[str] = []
    for plant in plants:
        normal = _normal(plant, cache)
        inlet = fit_inlet(normal, base, plant_map, arm)
        calibrator = inlet_calibrator(inlet, [_liar(plant, s, cache) for s in SEEDS], settings.seed)
        for seed in chosen:
            corpus = _liar(plant, seed, cache)
            try:
                diagnoses.extend(diagnose_corpus(corpus, normal, inlet, calibrator, settings))
            except ValueError as error:
                # ADR 0137: a corpus the harness cannot cross-fit is unmeasurable for every
                # detector alike, because the fold calibrator never sees the inlet. Reported.
                if "cannot cross-fit" not in str(error):
                    raise
                unmeasurable.append(corpus.name)
    passing = frozenset(
        (d.run.plant_id, d.run.seed, d.run.subtlety) for d in diagnoses if d.run.passes
    )
    card = LiarScorecard(
        seeds=chosen,
        passing=passing,
        mechanisms=dict(Counter(d.mechanism for d in diagnoses)),
        runs=len(diagnoses),
        seconds=time.monotonic() - started,
        unmeasurable=tuple(unmeasurable),
    )
    return card, diagnoses
