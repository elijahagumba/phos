"""Measure the episode-level system against PART 6B's frozen per-day row, at one operator budget.

**The first thing this script does is try to fail.** Before it measures anything new it rebuilds
PART 6B's published operating point — 48 alerts, precision 0.104, window recall 0.5, sample recall
5/53 — from the trace cache, and compares it against the row in ``eval_runs/log.jsonl`` to twelve
decimal places. If the cache, the replay, the split, the fit or the scorer has drifted by so much
as a float, the run stops there. Nothing downstream of a broken gate is worth reading, and a
harness that only checks its own new numbers is a harness that cannot be wrong.

The frozen row is **never rewritten**. Everything this script logs carries a detector name prefixed
`EPISODE_DETECTOR_PREFIX`, on the pattern ``phos.atlas.queue`` already uses to keep a re-counted
queue from ever landing under a vertical's published name.

**The comparison.** At a fixed budget of items an analyst reads:

* *baseline* — the top N entity-days by PART 6B's own aggregate score. What 6B hands an operator.
* *episodes* — the top N episodes by the same score lifted to the episode unit.

Reported for both: items read, malicious entity-days covered, insiders covered, and — for episodes
— how many entity-days those items contain, because an episode costs more to read than a day and
a compression ratio that ignored that would be a conjuring trick.

Usage::

    python scripts/build_sentiel_trace_cache.py          # once, ~4 minutes
    python scripts/measure_sentiel_episodes.py --budget 48
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.eval.datasets import Dataset  # noqa: E402
from phos.eval.detectors import Detection  # noqa: E402
from phos.eval.harness import EvalConfig  # noqa: E402
from phos.eval.report import (  # noqa: E402
    EvaluationReport,
    LatencySummary,
    append_to_experiment_log,
    current_git_commit,
)
from phos.models.base import StaticRangeFittedModel  # noqa: E402
from phos.models.detector import uncalibrated_confidence  # noqa: E402
from phos.models.gaussian import GaussianBaseline  # noqa: E402
from phos.ontology import (  # noqa: E402  # noqa: E402
    Domain,
    Evidence,
    InMemoryEvidenceStore,
    Observation,
)
from phos.sentiel.compression import (  # noqa: E402
    COMPRESSION_CAVEATS,
    QueuedDay,
    build_episode_queue,
    compare_at_budget,
    rank_episodes,
)
from phos.sentiel.entities import EntityCatalogue, user_entity_id, user_id_of  # noqa: E402
from phos.sentiel.episode_reasoning import (  # noqa: E402
    explain_episode,
    path_evidence,
    sequence_evidence,
)
from phos.sentiel.episode_report import (  # noqa: E402
    EpisodeMeasurement,
    render_measurement_markdown,
    spearman,
)
from phos.sentiel.episodes import (  # noqa: E402
    EpisodePolicy,
    assemble_episodes,
    episode_sensitivity,
    floor_at_quantile,
)
from phos.sentiel.evaluation import evaluate_entity_aware  # noqa: E402
from phos.sentiel.featurise import FeatureSet, Featuriser  # noqa: E402
from phos.sentiel.graph import DeclaredGraph  # noqa: E402
from phos.sentiel.labels import EntityLabelledInterval, read_insiders  # noqa: E402
from phos.sentiel.paths import (  # noqa: E402
    VACUOUS_TOP_LEVEL_FINDING,
    DayDeviceIndex,
    device_index_for_day,
    path_findings,
)
from phos.sentiel.peers import PeerGroups, PeerPolicy  # noqa: E402
from phos.sentiel.scoring import (  # noqa: E402
    AggregationPolicy,
    PrecomputedDetector,
    ScoredWindow,
    WindowScorer,
    static_range_model,
)
from phos.sentiel.sequence_scoring import (  # noqa: E402
    SequencePolicy,
    SequenceScores,
    score_day,
    train_population,
    train_self,
)
from phos.sentiel.templates import family_of  # noqa: E402
from phos.sentiel.traces import EntityDayTrace, read_traces, replay_observations  # noqa: E402
from phos.sentiel.weak_signals import weak_signal_profile  # noqa: E402

logger = logging.getLogger("measure_sentiel_episodes")

DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
DEFAULT_CACHE: Final = DEFAULT_DATA_DIR / "cert-insider-threat" / "r3.1-entity-day-traces.jsonl.gz"
EPISODE_DETECTOR_PREFIX: Final = "sentiel-episode:"

FROZEN_SIX_B: Final = {
    "detector_name": "aggregate:gaussian:peer set (34 features)",
    "dataset_name": "cert-r3.1-user-day-peer-test",
    "alert_threshold": 13.700640148454447,
    "n_alerts": 48,
    "n_observations": 210814,
    "window_recall": 0.5,
    "precision": 0.10416666666666667,
    "recall_sample": 0.09433962264150944,
    "false_positives": 43,
    "seed": 7,
    "git_commit": "b71c40fd9dc7d6e647ea83de8352126094507baf",
}
"""PART 6B's published CERT operating point, copied from ``eval_runs/log.jsonl``.

Restated here so the gate is readable beside the code that checks it, and re-read from the log at
run time so the two cannot drift: `check_frozen_row` fails if this dict and the logged row
disagree, before it ever compares either against a fresh number.
"""

_TOLERANCE: Final = 1e-12


class MeasurementError(RuntimeError):
    """Raised when the run cannot honestly continue."""


class ScoredDay:
    """One entity-day, reduced to what the episode layer and the queue need."""

    __slots__ = ("day", "family_names", "leading_feature", "score", "user_id")

    def __init__(  # noqa: D107 - the class docstring covers this value's fields
        self,
        user_id: str,
        day: datetime,
        score: float,
        family_names: tuple[str, ...],
        leading_feature: str | None,
    ) -> None:
        self.user_id = user_id
        self.day = day
        self.score = score
        self.family_names = family_names
        self.leading_feature = leading_feature


def _families_in(window: ScoredWindow, band_k: float) -> tuple[str, ...]:
    """Return the distinct behaviour families that left their expected range, sorted.

    **Out-of-band contributions only**, not every contribution the scorer emitted. The scorer
    emits at ``emit_k`` (1.0), well below the ``band_k`` (3.0) that shapes the reported
    `ExpectedRange`, so nearly every active entity-day carries a contribution from all four
    families and a family count taken over all of them is a constant — which is exactly what a
    first run of this measurement found, and why it is taken over the out-of-band subset here.

    A symmetric range is ``mean ± band_k * stddev``, so "the value left its expected range" and
    "the magnitude exceeds band_k" are the same test — which is what lets this be computed from
    the contributions alone, without re-scoring every observation through
    `phos.reasoning.is_out_of_band`.
    """
    return tuple(
        sorted(
            {
                family.value
                for contribution in window.contributions
                if contribution.magnitude > band_k
                and (family := family_of(contribution.feature)) is not None
            }
        )
    )


def _band_k_of(fitted: StaticRangeFittedModel) -> float:
    """Recover the band multiplier the fitted ranges were built with, from a range itself.

    Read off the model rather than assumed, so a model fitted with a different ``band_k`` cannot
    silently change what "out of band" means here.
    """
    for expected in fitted.feature_ranges.values():
        if expected.stddev > 0.0:
            return (expected.high - expected.mean) / expected.stddev
    raise MeasurementError(
        "no feature-level range has any spread, so the band multiplier cannot be recovered"
    )


def build_stream(cache: Path, featuriser: Featuriser) -> Iterator[Observation]:
    """Return a fresh observation stream replayed from the trace cache."""
    return replay_observations(read_traces(cache), featuriser)


def fit_and_score(
    cache: Path,
    featuriser: Featuriser,
    first_attack: datetime,
    policy: AggregationPolicy,
    min_samples: int,
) -> tuple[list[ScoredDay], list[Observation], int, int]:
    """Fit on the attack-free prefix and score the remainder, exactly as PART 6B does.

    Two replays of the cache rather than one, mirroring ``evaluate_sentiel_baseline.py``: the
    training prefix is held, fitted, and dropped before the second pass begins, so the test half
    is never in memory beside it.

    Returns:
        ``(scored days, one observation per test window, training observations, test windows)``.
    """
    started = time.monotonic()
    train: list[Observation] = []
    for observation in build_stream(cache, featuriser):
        if observation.timestamp >= first_attack:
            break
        train.append(observation)
    if not train:
        raise MeasurementError(
            f"no observation falls before the first labelled attack at {first_attack}; there is "
            "no attack-free history to learn normal from"
        )
    n_train = len(train)
    fitted = static_range_model(GaussianBaseline(min_samples=min_samples).fit(train))
    logger.info(
        "fitted gaussian on %s training observations in %.0fs; dropping them",
        f"{n_train:,}",
        time.monotonic() - started,
    )
    train.clear()

    band_k = _band_k_of(fitted)
    logger.info("out-of-band cut for family breadth: magnitude > %.4f", band_k)
    scorer = WindowScorer(fitted, policy, None)
    days: list[ScoredDay] = []
    windows: list[Observation] = []
    seen: set[tuple[str, datetime]] = set()

    def take(scored: list[ScoredWindow]) -> None:
        for window in scored:
            days.append(
                ScoredDay(
                    user_id=user_id_of(window.entity_id),
                    day=window.timestamp,
                    score=window.score,
                    family_names=_families_in(window, band_k),
                    leading_feature=window.leading_feature,
                )
            )

    started = time.monotonic()
    for observation in build_stream(cache, featuriser):
        if observation.timestamp < first_attack:
            continue
        key = (observation.entity_ids[0], observation.timestamp)
        if key not in seen:
            seen.add(key)
            windows.append(observation)
        take(scorer.push(observation))
    take(scorer.close())
    logger.info(
        "scored %s test entity-day(s) in %.0fs; %s",
        f"{len(days):,}",
        time.monotonic() - started,
        scorer.summary().note(),
    )
    return days, windows, n_train, len(windows)


def logged_frozen_row(log_path: Path) -> dict[str, object]:
    """Return PART 6B's 48-alert row from the experiment log, or raise if it is not there."""
    wanted = FROZEN_SIX_B
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            row.get("detector_name") == wanted["detector_name"]
            and row.get("dataset_name") == wanted["dataset_name"]
            and row.get("n_alerts") == wanted["n_alerts"]
        ):
            return dict(row)
    raise MeasurementError(
        f"{log_path} holds no row for {wanted['detector_name']!r} on "
        f"{wanted['dataset_name']!r} at {wanted['n_alerts']} alerts. The frozen 6B operating "
        "point is the gate for this whole run and it cannot be checked against a log that does "
        "not contain it."
    )


def check_frozen_row(fresh: dict[str, float], log_path: Path) -> list[str]:
    """Compare a freshly computed 48-alert point against the frozen one, and against the log.

    Args:
        fresh: The numbers this run produced.
        log_path: ``eval_runs/log.jsonl``.

    Returns:
        A list of human-readable disagreements. Empty means the gate passed.
    """
    problems: list[str] = []
    logged = logged_frozen_row(log_path)
    for field in ("alert_threshold", "window_recall", "precision", "recall_sample", "n_alerts"):
        if abs(float(logged[field]) - float(FROZEN_SIX_B[field])) > _TOLERANCE:  # type: ignore[arg-type]
            problems.append(
                f"the constant in this script disagrees with eval_runs/log.jsonl on {field}: "
                f"{FROZEN_SIX_B[field]!r} vs {logged[field]!r}"
            )
    for field, expected in (
        ("n_observations", FROZEN_SIX_B["n_observations"]),
        ("n_alerts", FROZEN_SIX_B["n_alerts"]),
        ("alert_threshold", FROZEN_SIX_B["alert_threshold"]),
        ("window_recall", FROZEN_SIX_B["window_recall"]),
        ("precision", FROZEN_SIX_B["precision"]),
        ("recall_sample", FROZEN_SIX_B["recall_sample"]),
        ("false_positives", FROZEN_SIX_B["false_positives"]),
    ):
        got = fresh.get(field)
        if got is None:
            problems.append(f"this run produced no {field}")
        elif abs(float(got) - float(expected)) > _TOLERANCE:  # type: ignore[arg-type]
            problems.append(f"{field}: frozen {expected!r}, reproduced {got!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run the gate and the measurement. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--release-dir", type=str, default="cert-insider-threat/r3.1")
    parser.add_argument("--answers-dir", type=str, default="cert-insider-threat/answers")
    parser.add_argument("--release", type=str, default="r3.1")
    parser.add_argument("--budget", type=int, default=48)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval_runs" / "sentiel")
    parser.add_argument(
        "--scores-cache",
        type=Path,
        default=None,
        help=(
            "reuse scored entity-days from this file when it exists, and write them when it does "
            "not. The frozen-row gate still runs against whatever is loaded, so a stale cache "
            "fails the gate rather than being trusted."
        ),
    )
    parser.add_argument("--gap-days", type=int, default=7)
    parser.add_argument("--floor-quantile", type=float, default=0.90)
    parser.add_argument("--ranking", type=str, default="peak")
    parser.add_argument("--ngram", type=int, default=3)
    parser.add_argument("--sequence-pct", type=float, default=99.0)
    parser.add_argument("--extra-budgets", type=int, nargs="*", default=[20, 100, 200])
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help="reproduce the frozen 6B row and stop, without measuring anything new",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    if not arguments.cache.is_file():
        logger.error(
            "no trace cache at %s. Build it first:\n"
            "    python scripts/build_sentiel_trace_cache.py",
            arguments.cache,
        )
        return 2

    release_dir = arguments.data_dir / arguments.release_dir
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    org_domain = catalogue.dominant_email_domain()
    labels = read_insiders(arguments.data_dir / arguments.answers_dir, arguments.release)
    first_attack = min(label.start for label in labels)
    groups = PeerGroups.from_catalogue(catalogue, PeerPolicy())
    featuriser = Featuriser(
        org_domains=frozenset({org_domain}),
        feature_set=FeatureSet.PEER,
        peer_groups=groups,
    )
    logger.info(
        "%d directory users | org domain %s | %d labelled insider(s) | first attack %s",
        len(catalogue.entities),
        org_domain,
        len(labels),
        first_attack,
    )

    policy = AggregationPolicy()
    cached = _load_scores(arguments.scores_cache)
    if cached is None:
        days, windows, n_train, n_windows = fit_and_score(
            arguments.cache, featuriser, first_attack, policy, arguments.min_samples
        )
        _save_scores(arguments.scores_cache, days, windows)
    else:
        days, windows = cached
        n_train = 0
        n_windows = len(windows)
        logger.info(
            "reused %s scored entity-day(s) from %s",
            f"{len(days):,}",
            arguments.scores_cache,
        )

    # -- the gate ---------------------------------------------------------------------------
    ranked = sorted((day.score for day in days), reverse=True)
    if arguments.budget > len(ranked):
        logger.error("budget %d exceeds %d scored entity-days", arguments.budget, len(ranked))
        return 2
    threshold = ranked[arguments.budget - 1]

    test = Dataset(
        name=f"cert-{arguments.release}-user-day-peer-test",
        domain=Domain.SENTIEL,
        observations=windows,
        attack_intervals=[],
        source_note="",
    )
    in_test = [
        label
        for label in labels
        if label.start <= windows[-1].timestamp and label.end >= windows[0].timestamp
    ]
    detections = [
        Detection(
            timestamp=day.day,
            score=day.score,
            confidence=uncalibrated_confidence(day.score, policy.score_scale),
            entity_ids=[user_entity_id(day.user_id)],
            feature=day.leading_feature,
        )
        for day in days
    ]
    report = evaluate_entity_aware(
        PrecomputedDetector(name=str(FROZEN_SIX_B["detector_name"]), detections=detections),
        test,
        in_test,
        EvalConfig(alert_threshold=threshold, seed=arguments.seed),
    )
    fresh = {
        "n_observations": report.n_observations,
        "n_alerts": report.n_alerts,
        "alert_threshold": report.alert_threshold,
        "window_recall": report.window_recall,
        "precision": report.precision,
        "recall_sample": report.recall_sample,
        "false_positives": report.false_positives,
    }
    logger.info("reproduced 48-alert point: %s", json.dumps(fresh, sort_keys=True))

    problems = check_frozen_row(fresh, REPO_ROOT / "eval_runs" / "log.jsonl")
    if problems:
        logger.error("FROZEN ROW GATE FAILED — refusing to report anything built on this run:")
        for problem in problems:
            logger.error("  %s", problem)
        return 3
    logger.info(
        "FROZEN ROW GATE PASSED: the trace cache reproduces PART 6B's 48-alert point exactly "
        "(threshold %.12f, precision %.12f, window recall %.1f, sample recall %.12f)",
        fresh["alert_threshold"],
        fresh["precision"],
        fresh["window_recall"],
        fresh["recall_sample"],
    )

    arguments.out.mkdir(parents=True, exist_ok=True)
    gate = {
        "gate": "frozen-6b-row",
        "passed": True,
        "frozen": FROZEN_SIX_B,
        "reproduced": fresh,
        "training_observations": n_train,
        "test_entity_days": n_windows,
        "cache": str(arguments.cache),
    }
    (arguments.out / "episode-gate.json").write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if arguments.gate_only:
        return 0

    return measure(arguments, days, labels, in_test, threshold, catalogue, featuriser)


def _load_scores(path: Path | None) -> tuple[list[ScoredDay], list[Observation]] | None:
    """Return cached scored days and window representatives, or ``None`` to compute them.

    The cache holds only what the episode layer needs plus one `Observation` per window, which is
    all `evaluate_entity_aware` reads. It is never trusted blindly: the frozen-row gate runs
    against whatever is loaded, so a cache built from different code fails the gate.
    """
    if path is None or not path.is_file():
        return None
    import gzip

    days: list[ScoredDay] = []
    windows: list[Observation] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            day = datetime.fromisoformat(row["d"])
            days.append(
                ScoredDay(
                    user_id=row["u"],
                    day=day,
                    score=row["s"],
                    family_names=tuple(row["f"]),
                    leading_feature=row["l"],
                )
            )
            windows.append(
                Observation(
                    id=row["o"],
                    entity_ids=[user_entity_id(row["u"])],
                    feature=row["w"],
                    value=0.0,
                    timestamp=day,
                    domain=Domain.SENTIEL,
                )
            )
    return days, windows


def _save_scores(path: Path | None, days: list[ScoredDay], windows: list[Observation]) -> None:
    """Write the scored days so a later run can skip the fit and the scoring pass."""
    if path is None:
        return
    import gzip

    by_key = {(user_id_of(w.entity_ids[0]), w.timestamp): w for w in windows}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as handle:
        for day in days:
            window = by_key[(day.user_id, day.day)]
            handle.write(
                json.dumps(
                    {
                        "u": day.user_id,
                        "d": day.day.isoformat(),
                        "s": day.score,
                        "f": list(day.family_names),
                        "l": day.leading_feature,
                        "o": window.id,
                        "w": window.feature,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
    logger.info("wrote %s scored entity-day(s) to %s", f"{len(days):,}", path)


# ------------------------------------------------------------------------------------------------
# The measurement, once the gate has passed
# ------------------------------------------------------------------------------------------------


def _is_malicious(user_id: str, day: datetime, labels: Sequence[EntityLabelledInterval]) -> bool:
    """Return whether ground truth calls this entity-day malicious.

    The ontology's own rule (`EntityLabelledInterval.contains`), applied to the window's start —
    the same test `phos.sentiel.evaluation` applies, so a covered day here and a true positive
    there mean the same thing.
    """
    return any(label.contains(user_id, day) for label in labels)


def _day_traces(cache: Path) -> Iterator[list[EntityDayTrace]]:
    """Yield each day's traces together, so co-presence on a machine stays a fact about one day."""
    batch: list[EntityDayTrace] = []
    open_day: datetime | None = None
    for trace in read_traces(cache):
        if open_day is not None and trace.day != open_day:
            yield batch
            batch = []
        open_day = trace.day
        batch.append(trace)
    if batch:
        yield batch


def measure(
    arguments: argparse.Namespace,
    days: list[ScoredDay],
    labels: Sequence[EntityLabelledInterval],
    in_test: Sequence[EntityLabelledInterval],
    threshold: float,
    catalogue: EntityCatalogue,
    featuriser: Featuriser,
) -> int:
    """Assemble episodes, ask the graph and sequence layers, and write the report."""
    del labels
    budget = arguments.budget
    scores = [day.score for day in days]
    floor = min(floor_at_quantile(scores, arguments.floor_quantile), threshold)
    policy = EpisodePolicy(
        anchor_threshold=threshold,
        extension_floor=floor,
        gap=timedelta(days=arguments.gap_days),
    )
    candidates = [
        (user_entity_id(day.user_id), day.day, day.score, day.family_names, day.leading_feature)
        for day in days
    ]
    episodes = assemble_episodes(candidates, policy)

    malicious_days = [day for day in days if _is_malicious(day.user_id, day.day, in_test)]
    n_malicious = len(malicious_days)
    logger.info(
        "test half: %s entity-day(s), %d malicious across %d insider(s); %s episode(s) at "
        "floor %.4f / anchor %.4f / gap %dd",
        f"{len(days):,}",
        n_malicious,
        len(in_test),
        f"{len(episodes):,}",
        floor,
        threshold,
        arguments.gap_days,
    )

    queued_days = [
        QueuedDay(
            user_id=day.user_id,
            day=day.day,
            score=day.score,
            malicious=_is_malicious(day.user_id, day.day, in_test),
        )
        for day in days
    ]
    alerts = build_episode_queue(episodes, in_test)
    comparison = compare_at_budget(
        queued_days, alerts, budget, n_malicious, len(in_test), arguments.ranking
    )
    extra = tuple(
        compare_at_budget(queued_days, alerts, other, n_malicious, len(in_test), arguments.ranking)
        for other in arguments.extra_budgets
        if other != budget
    )

    ranked = rank_episodes(alerts, arguments.ranking)
    top = tuple(ranked[:budget])
    by_key = {
        (episode.entity_id.removeprefix("ent_"), episode.start): episode for episode in episodes
    }
    profiles = tuple(
        weak_signal_profile(by_key[(alert.user_id, alert.start)])
        for alert in top
        if (alert.user_id, alert.start) in by_key
    )

    # -- the declared graph, and what the corpus lets it be asked ----------------------------
    graph = DeclaredGraph.from_catalogue(catalogue)
    first_attack = min(label.start for label in in_test)
    path_firing: dict[str, int] = defaultdict(int)
    path_on_malicious: dict[str, int] = defaultdict(int)
    verdicts: dict[str, int] = defaultdict(int)
    training_traces: list[EntityDayTrace] = []
    test_traces: list[EntityDayTrace] = []
    started = time.monotonic()
    for batch in _day_traces(arguments.cache):
        if batch[0].day < first_attack:
            training_traces.extend(batch)
            continue
        test_traces.extend(batch)
        index = device_index_for_day(batch)
        for trace in batch:
            findings = path_findings(trace, graph, index)
            malicious = _is_malicious(trace.user_id, trace.day, in_test)
            for name, value in findings.values().items():
                if value > 0:
                    path_firing[name] += 1
                    if malicious:
                        path_on_malicious[name] += 1
            for verdict, count in findings.interaction_verdicts.items():
                verdicts[verdict] += count
    logger.info(
        "path findings over %s test entity-day(s) in %.0fs (%s training day(s) held back)",
        f"{len(test_traces):,}",
        time.monotonic() - started,
        f"{len(training_traces):,}",
    )

    # -- sequences, trained on the attack-free prefix only ------------------------------------
    sequence_policy = SequencePolicy(n=arguments.ngram, alert_percentile=arguments.sequence_pct)
    population = train_population(training_traces, sequence_policy)
    self_baselines = train_self(training_traces, sequence_policy)
    sequence_alerts = 0
    sequence_alerts_malicious = 0
    ordered_scores: list[float] = []
    blind_scores: list[float] = []
    sequence_by_key: dict[tuple[str, datetime], SequenceScores] = {}
    for trace in test_traces:
        scored = score_day(trace, population, self_baselines)
        sequence_by_key[(trace.user_id, trace.day)] = scored
        ordered_scores.append(scored.population)
        blind_scores.append(scored.count_baseline)
        if scored.alerts:
            sequence_alerts += 1
            if _is_malicious(trace.user_id, trace.day, in_test):
                sequence_alerts_malicious += 1
    agreement = spearman(ordered_scores, blind_scores)
    chance = (n_malicious / len(days)) if days else 0.0
    path_chance = {name: count * chance for name, count in path_firing.items()}
    logger.info(
        "sequence: %s of %s test entity-day(s) cleared the p%.1f cut of %.4f; %d malicious; "
        "rank agreement with the order-blind baseline %.3f",
        f"{sequence_alerts:,}",
        f"{len(test_traces):,}",
        sequence_policy.alert_percentile,
        population.alert_cut,
        sequence_alerts_malicious,
        agreement,
    )

    # -- reasoning over the episodes an analyst reads ------------------------------------------
    store = InMemoryEvidenceStore()
    narratives = 0
    sequence_evidence_made = 0
    path_evidence_made = 0
    trace_by_key = {(trace.user_id, trace.day): trace for trace in test_traces}
    # Grouped once. Scanning `test_traces` per episode-day would be quadratic over 210,000 rows.
    traces_by_day: dict[datetime, list[EntityDayTrace]] = defaultdict(list)
    for trace in test_traces:
        traces_by_day[trace.day].append(trace)
    day_index: dict[datetime, DayDeviceIndex] = {}
    for alert in top:
        episode = by_key.get((alert.user_id, alert.start))
        if episode is None:
            continue
        evidence: list[Evidence] = []
        for member in episode.days:
            key = (alert.user_id, member.day)
            member_scores = sequence_by_key.get(key)
            if member_scores is not None:
                made = sequence_evidence(
                    episode.entity_id, member.day, member_scores, population.alert_cut, 0.5
                )
                if made is not None:
                    store.add_evidence(made)
                    evidence.append(made)
                    sequence_evidence_made += 1
            member_trace = trace_by_key.get(key)
            if member_trace is not None:
                member_index = day_index.get(member.day)
                if member_index is None:
                    member_index = device_index_for_day(traces_by_day.get(member.day, []))
                    day_index[member.day] = member_index
                made_path = path_evidence(
                    episode.entity_id,
                    member.day,
                    path_findings(member_trace, graph, member_index),
                    0.5,
                )
                if made_path is not None:
                    store.add_evidence(made_path)
                    evidence.append(made_path)
                    path_evidence_made += 1
        if evidence:
            narratives += len(explain_episode(episode, evidence, store))
    logger.info(
        "reasoned over the top %d episode(s): %d sequence and %d path evidence, %d narrative(s)",
        len(top),
        sequence_evidence_made,
        path_evidence_made,
        narratives,
    )

    notes = [
        VACUOUS_TOP_LEVEL_FINDING,
        f"The declared interaction policy was asked about {sum(verdicts.values()):,} internal "
        f"recipient pair(s) and returned INSUFFICIENT for every one: CERT r3.1 ships no policy "
        f"about which roles may talk to which. This is phos.sentiel.interaction refusing "
        f"correctly, wired end to end for the first time.",
        f"EvidenceKind.SEQUENCE_ANOMALY was emitted {sequence_evidence_made} time(s) — the first "
        f"any PHOS engine has produced. EvidenceKind.RELATIONSHIP_CHANGE carried "
        f"{path_evidence_made} declared-path finding(s).",
    ]

    measurement = EpisodeMeasurement(
        budget=budget,
        comparison=comparison,
        extra_budgets=extra,
        sensitivity=tuple(episode_sensitivity(candidates, threshold)),
        top_episodes=top,
        profiles=profiles,
        graph=graph.summary,
        path_firing=dict(path_firing),
        path_on_malicious=dict(path_on_malicious),
        path_expected_by_chance=path_chance,
        interaction_verdicts=dict(verdicts),
        sequence_alerts=sequence_alerts,
        sequence_alerts_malicious=sequence_alerts_malicious,
        sequence_expected_by_chance=sequence_alerts * chance,
        sequence_cut=population.alert_cut,
        sequence_rank_agreement=agreement,
        n_malicious_days=n_malicious,
        n_scored_days=len(days),
        n_episodes=len(episodes),
        notes=tuple(notes),
    )
    commit = current_git_commit()
    markdown = render_measurement_markdown(
        measurement,
        corpus=f"CERT {arguments.release}",
        seed=arguments.seed,
        git_commit=commit,
        frozen=FROZEN_SIX_B,
    )
    (arguments.out / "episode-measurement.md").write_text(markdown, encoding="utf-8")
    (arguments.out / "episode-measurement.json").write_text(
        measurement.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    logger.info("wrote %s", arguments.out / "episode-measurement.md")

    if not arguments.no_log:
        _log_episode_row(measurement, arguments, commit, featuriser)
    return 0


def _log_episode_row(
    measurement: EpisodeMeasurement,
    arguments: argparse.Namespace,
    commit: str | None,
    featuriser: Featuriser,
) -> None:
    """Append the episode queue's operating point under a NEW name, beside the frozen row.

    The log is append-only and the detector name carries `EPISODE_DETECTOR_PREFIX`, so this cannot
    reach PART 6B's row — which is reproduced as a gate earlier in this run and left alone.
    """
    comparison = measurement.comparison
    taken = min(comparison.budget, comparison.n_episodes_available)
    report = EvaluationReport(
        detector_name=f"{EPISODE_DETECTOR_PREFIX}{comparison.ranking}",
        dataset_name=f"cert-{arguments.release}-entity-day-episodes",
        domain=Domain.SENTIEL,
        git_commit=commit,
        seed=arguments.seed,
        source_note=" | ".join(
            [
                f"CERT {arguments.release} episode queue over "
                f"{measurement.n_scored_days:,} scored entity-days "
                f"({len(featuriser.feature_names)} features), "
                f"{measurement.n_episodes:,} episodes",
                *COMPRESSION_CAVEATS,
            ]
        ),
        alert_threshold=comparison.cut_score or 0.0,
        match_tolerance_seconds=0.0,
        calibration_bins=10,
        n_observations=measurement.n_scored_days,
        n_detections=comparison.n_episodes_available,
        n_alerts=taken,
        n_attack_intervals=comparison.n_insiders,
        normal_hours=0.0,
        window_recall=(
            comparison.episode_insiders / comparison.n_insiders if comparison.n_insiders else 0.0
        ),
        false_positives=taken - comparison.episode_true_items,
        false_positive_rate=0.0,
        precision=comparison.episode_true_items / taken if taken else 0.0,
        recall_sample=comparison.episode_coverage,
        f1=0.0,
        latency=LatencySummary(count=0),
        expected_calibration_error=0.0,
        brier_score=0.0,
    )
    append_to_experiment_log(report)


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
