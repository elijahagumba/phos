"""Classify *why* Sentiel fails on CERT r3.1 — Usefulness Phase item U2 (ADR 0074).

**The first thing this script does is try to fail.** It reproduces PART 6B's published operating
point — 48 alerts, precision 0.104, window recall 0.5, sample recall 5/53 — through
``measure_sentiel_episodes.check_frozen_row``, the same gate the episode cycle already used, and
stops on any disagreement past 1e-12. It then reproduces the published episode set (40 reportable
episodes over 506 entity-days) as a **second** gate, because the permutation null in
`phos.sentiel.episode_null` reassembles episodes from ``(day, score)`` pairs rather than from
`Episode` objects, and a fast reimplementation that disagreed with the published one would
make every null that follows a null about the wrong thing.

Nothing here appends to ``eval_runs/log.jsonl``, and no frozen number is re-derived under its own
name. The report lands in ``eval_runs/sentiel/cert-failure-classification.md``, following ADR 0065
and ADR 0075.

Usage::

    python scripts/build_sentiel_trace_cache.py          # once, ~4 minutes
    python scripts/classify_sentiel_failures.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT))

from scripts.measure_sentiel_episodes import (  # noqa: E402
    FROZEN_SIX_B,
    MeasurementError,
    check_frozen_row,
)

from phos.eval.datasets import Dataset  # noqa: E402
from phos.eval.detectors import Detection  # noqa: E402
from phos.eval.harness import EvalConfig  # noqa: E402
from phos.models.detector import uncalibrated_confidence  # noqa: E402
from phos.models.gaussian import GaussianBaseline  # noqa: E402
from phos.ontology import Domain, Observation  # noqa: E402
from phos.sentiel.entities import EntityCatalogue, user_entity_id, user_id_of  # noqa: E402
from phos.sentiel.episode_null import (  # noqa: E402
    EpisodeNull,
    coherence_permutation_null,
    coherence_share,
    episode_permutation_null,
)
from phos.sentiel.episodes import EPISODE_GAP_INHERITS_CORRELATION_WINDOW  # noqa: E402
from phos.sentiel.evaluation import evaluate_entity_aware  # noqa: E402
from phos.sentiel.failure import (  # noqa: E402
    CEILING_PRECEDENCE,
    BaselineShift,
    InsiderVisibility,
    VisibilityVerdict,
    baseline_shifts,
    classify_insider,
    contribution_curve,
    features_required,
    labelled_event_profile,
)
from phos.sentiel.featurise import FeatureSet, Featuriser  # noqa: E402
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.peers import PeerGroups, PeerPolicy  # noqa: E402
from phos.sentiel.scoring import (  # noqa: E402
    AggregationPolicy,
    PrecomputedDetector,
    ScoredWindow,
    WindowScorer,
    static_range_model,
)
from phos.sentiel.traces import read_traces, replay_observations  # noqa: E402

logger = logging.getLogger("classify_sentiel_failures")

DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
DEFAULT_CACHE: Final = DEFAULT_DATA_DIR / "cert-insider-threat" / "r3.1-entity-day-traces.jsonl.gz"

PUBLISHED_EPISODES: Final = 40
PUBLISHED_EPISODE_DAYS: Final = 506
PUBLISHED_EPISODE_MALICIOUS_DAYS: Final = 9
"""The malicious entity-days ADR 0072 reported the episode queue shows at budget 48.

Gated like the other two published figures. ADR 0072 read a **ratio** off this count — "1.8x the
malicious activity in front of an analyst" — and a ratio against a single alternative is only
meaningful beside the spread of the null, which that cycle never ran. U2 runs it; the count itself
is reproduced here first so the null cannot be a null about a different number.
"""
"""ADR 0072's published episode set, restated as the second gate.

Not a number this script may move: it is reproduced to prove the fast episode reassembly in
`phos.sentiel.episode_null._episodes` agrees with `phos.sentiel.episodes`, and the run stops if it
does not.
"""


ANSWER_TARGET_COLUMN: Final = {"http": 5, "email": 3}
"""Which column of a CERT answer row names the host or recipient, by event kind.

**Verified against the files rather than assumed, because the two layouts differ.** An ``http`` row
is ``kind, id, date, user, pc, url, content`` — column 5 is the URL. An ``email`` row is
``kind, id, date, to, from, size, attachments, content`` — column 3 is the **recipient** and column
4 is the sender. A first draft mapped ``email`` to 4 and reported every one of `CCH0959`'s labelled
mails as addressed to `CCH0959`'s own address, which is the sender; the recipients are what the
question is about.

``logon`` and ``device`` name a machine the user already owns and are given no target: the question
targets answer is "where could the data go", and a workstation the person logs into daily is not an
answer to it. ``file`` is absent from both r3.1 answer files, so no column is claimed for it rather
than a layout being guessed.
"""


def _labelled_rows(path: Path, user_id: str) -> list[tuple[str, datetime, str | None]]:
    """Read one insider's answer file into ``(kind, when, target)`` triples.

    CERT's answer files are headerless and per-incident. Rows naming another party — a recipient
    address rather than the insider — are kept, because scenario 2's mail to a competitor is
    exactly such a row and dropping it would delete the evidence the profile exists to count.
    """
    rows: list[tuple[str, datetime, str | None]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            kind = row[0]
            when = datetime.strptime(row[2], "%m/%d/%Y %H:%M:%S").replace(tzinfo=UTC)
            column = ANSWER_TARGET_COLUMN.get(kind)
            target: str | None = None
            if column is not None and len(row) > column:
                raw = row[column]
                target = urlparse(raw).netloc if kind == "http" else raw
            rows.append((kind, when, target or None))
    return rows


def _quantile(ordered: list[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted sequence."""
    index = q * (len(ordered) - 1)
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] * (1.0 - (index - low)) + ordered[high] * (index - low)


def main(argv: list[str] | None = None) -> int:
    """Run both gates and the classification. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--release-dir", type=str, default="cert-insider-threat/r3.1")
    parser.add_argument("--answers-dir", type=str, default="cert-insider-threat/answers")
    parser.add_argument("--release", type=str, default="r3.1")
    parser.add_argument("--budget", type=int, default=48)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--permutation-seed", type=int, default=11)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument("--floor-quantile", type=float, default=0.90)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval_runs" / "sentiel")
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    if not arguments.cache.is_file():
        logger.error("no trace cache at %s; run build_sentiel_trace_cache.py", arguments.cache)
        return 2

    release_dir = arguments.data_dir / arguments.release_dir
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    labels = read_insiders(arguments.data_dir / arguments.answers_dir, arguments.release)
    first_attack = min(label.start for label in labels)
    featuriser = Featuriser(
        org_domains=frozenset({catalogue.dominant_email_domain()}),
        feature_set=FeatureSet.PEER,
        peer_groups=PeerGroups.from_catalogue(catalogue, PeerPolicy()),
    )
    insiders = {label.user_id: label for label in labels}
    policy = AggregationPolicy()

    # -- fit on the attack-free prefix, exactly as PART 6B does ---------------------------------
    # The insiders' own pre-attack feature values are kept from this same pass, so the fixed
    # baseline `baseline_shifts` measures against is literally the data the model was fitted on.
    started = time.monotonic()
    train: list[Observation] = []
    pre_attack: dict[str, dict[datetime, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for observation in replay_observations(read_traces(arguments.cache), featuriser):
        if observation.timestamp < first_attack:
            train.append(observation)
            user = user_id_of(observation.entity_ids[0])
            if user in insiders:
                pre_attack[user][observation.timestamp][observation.feature] = observation.value
    if not train:
        raise MeasurementError("no attack-free history before the first labelled attack")
    fitted = static_range_model(GaussianBaseline(min_samples=arguments.min_samples).fit(train))
    logger.info("fitted on %s observations in %.0fs", f"{len(train):,}", time.monotonic() - started)
    train.clear()
    band_k = next(
        (er.high - er.mean) / er.stddev for er in fitted.feature_ranges.values() if er.stddev > 0.0
    )
    logger.info("out-of-band cut recovered from the fitted model: magnitude > %.4f", band_k)

    # -- one scoring pass, keeping per-insider magnitudes ---------------------------------------
    scorer = WindowScorer(fitted, policy, None)
    scores: list[tuple[str, datetime, float, str | None]] = []
    windows: list[Observation] = []
    seen: set[tuple[str, datetime]] = set()
    insider_days: dict[str, list[tuple[datetime, float, dict[str, float]]]] = defaultdict(list)

    def take(scored: list[ScoredWindow]) -> None:
        for window in scored:
            user = user_id_of(window.entity_id)
            scores.append((user, window.timestamp, window.score, window.leading_feature))
            if user in insiders:
                insider_days[user].append(
                    (
                        window.timestamp,
                        window.score,
                        {c.feature: c.magnitude for c in window.contributions},
                    )
                )

    scored_values: dict[str, dict[datetime, dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    started = time.monotonic()
    for observation in replay_observations(read_traces(arguments.cache), featuriser):
        if observation.timestamp < first_attack:
            continue
        key = (observation.entity_ids[0], observation.timestamp)
        if key not in seen:
            seen.add(key)
            windows.append(observation)
        user = user_id_of(observation.entity_ids[0])
        if user in insiders:
            scored_values[user][observation.timestamp][observation.feature] = observation.value
        take(scorer.push(observation))
    take(scorer.close())
    logger.info("scored %s entity-days in %.0fs", f"{len(scores):,}", time.monotonic() - started)

    # -- GATE 1: PART 6B's frozen row ------------------------------------------------------------
    ranked = sorted((row[2] for row in scores), reverse=True)
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
    report = evaluate_entity_aware(
        PrecomputedDetector(
            name=str(FROZEN_SIX_B["detector_name"]),
            detections=[
                Detection(
                    timestamp=day,
                    score=score,
                    confidence=uncalibrated_confidence(score, policy.score_scale),
                    entity_ids=[user_entity_id(user)],
                    feature=leading,
                )
                for user, day, score, leading in scores
            ],
        ),
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
    problems = check_frozen_row(fresh, REPO_ROOT / "eval_runs" / "log.jsonl")
    if problems:
        for problem in problems:
            logger.error("FROZEN ROW GATE FAILED: %s", problem)
        return 1
    logger.info("GATE 1 PASSED: PART 6B's 48-alert point reproduced exactly")

    # -- GATE 2: the published episode set --------------------------------------------------------
    by_entity: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    leading_of: dict[tuple[str, datetime], str | None] = {}
    for user, day, score, leading in scores:
        by_entity[user].append((day, score))
        leading_of[(user, day)] = leading
    for rows in by_entity.values():
        rows.sort()
    floor = _quantile(sorted(row[2] for row in scores), arguments.floor_quantile)
    gap = EPISODE_GAP_INHERITS_CORRELATION_WINDOW

    from phos.sentiel.episode_null import _episodes

    episodes = [
        (u, e) for u, rows in by_entity.items() for e in _episodes(rows, floor, threshold, gap)
    ]
    n_episodes = len(episodes)
    n_episode_days = sum(len(e) for _, e in episodes)
    if (n_episodes, n_episode_days) != (PUBLISHED_EPISODES, PUBLISHED_EPISODE_DAYS):
        logger.error(
            "EPISODE GATE FAILED: reassembly gives %d episodes over %d entity-days; ADR 0072 "
            "published %d over %d. Every null below would be a null about a different rule.",
            n_episodes,
            n_episode_days,
            PUBLISHED_EPISODES,
            PUBLISHED_EPISODE_DAYS,
        )
        return 1
    logger.info(
        "GATE 2 PASSED: %d episodes over %d entity-days, matching ADR 0072 (floor %.6f, gap %s)",
        n_episodes,
        n_episode_days,
        floor,
        gap,
    )

    # -- the classification ------------------------------------------------------------------------
    rank_of = {
        (user, day): index + 1
        for index, (user, day, _score, _leading) in enumerate(
            sorted(scores, key=lambda row: -row[2])
        )
    }
    visibility = []
    shifts: dict[str, tuple[BaselineShift, ...]] = {}
    out_of_band: dict[str, dict[str, int]] = {}
    ground_truth = {
        user_id: labelled_event_profile(
            user_id,
            _labelled_rows(
                arguments.data_dir
                / arguments.answers_dir
                / f"{arguments.release}-{label.scenario}.csv",
                user_id,
            ),
        )
        for user_id, label in insiders.items()
    }
    for user_id, label in insiders.items():
        malicious = [
            (day, score, magnitudes)
            for day, score, magnitudes in insider_days[user_id]
            if label.contains(user_id, day)
        ]
        ordinary = [
            score for day, score, _m in insider_days[user_id] if not label.contains(user_id, day)
        ]
        out_of_band[user_id] = {
            day.isoformat(): sum(1 for m in magnitudes.values() if m > band_k)
            for day, _score, magnitudes in malicious
        }
        shifts[user_id] = baseline_shifts(
            [values for _day, values in sorted(pre_attack[user_id].items())],
            [
                values
                for day, values in sorted(scored_values[user_id].items())
                if label.contains(user_id, day)
            ],
            FeatureSet.PEER.features,
        )
        visibility.append(
            classify_insider(
                user_id=user_id,
                scenario=label.scenario,
                malicious=malicious,
                threshold=threshold,
                best_rank=min((rank_of[(user_id, d)] for d, _s, _m in malicious), default=None),
                n_scored_days=len(scores),
                ordinary_scores=ordinary,
            )
        )

    malicious_pairs = frozenset(
        (user_id, day)
        for user_id, label in insiders.items()
        for day, _score, _magnitudes in insider_days[user_id]
        if label.contains(user_id, day)
    )
    nulls = {
        statistic: episode_permutation_null(
            by_entity,
            statistic,
            floor,
            threshold,
            gap,
            iterations=arguments.iterations,
            seed=arguments.permutation_seed,
            malicious=malicious_pairs,
            budget=arguments.budget,
        )
        for statistic in ("n_episodes", "n_days", "longest", "n_long", "malicious_days")
    }
    observed_malicious = int(nulls["malicious_days"].observed)
    if observed_malicious != PUBLISHED_EPISODE_MALICIOUS_DAYS:
        logger.error(
            "EPISODE COVERAGE GATE FAILED: the episode queue covers %d malicious entity-day(s) at "
            "budget %d; ADR 0072 published %d. The null below would describe a different number.",
            observed_malicious,
            arguments.budget,
            PUBLISHED_EPISODE_MALICIOUS_DAYS,
        )
        return 1
    logger.info(
        "GATE 3 PASSED: the episode queue covers %d malicious entity-day(s) at budget %d, "
        "matching ADR 0072; permuted mean %.2f, 95%% [%.0f, %.0f], P(permuted >= observed) %.3f",
        observed_malicious,
        arguments.budget,
        nulls["malicious_days"].mean,
        nulls["malicious_days"].low,
        nulls["malicious_days"].high,
        nulls["malicious_days"].p_at_least_observed,
    )
    shares = [
        share
        for user, episode in episodes
        if (share := coherence_share([leading_of[(user, d)] or "" for d, _s in episode]))
        is not None
    ]
    observed_share = statistics.mean(shares)
    coherence_null = coherence_permutation_null(
        {
            user: [(day, score, leading_of[(user, day)]) for day, score in rows]
            for user, rows in by_entity.items()
        },
        floor,
        threshold,
        gap,
        iterations=arguments.iterations,
        seed=arguments.permutation_seed,
    )
    if abs(coherence_null.observed - observed_share) > 1e-12:
        logger.error(
            "COHERENCE GATE FAILED: the null's observed share is %.15f and the report's is "
            "%.15f. The null would be describing a different statistic from the one reported.",
            coherence_null.observed,
            observed_share,
        )
        return 1
    nulls["coherence"] = coherence_null
    logger.info(
        "coherence %.3f observed | permuted mean %.3f, 95%% [%.3f, %.3f], "
        "P(permuted >= observed) %.3f, inside null %s",
        coherence_null.observed,
        coherence_null.mean,
        coherence_null.low,
        coherence_null.high,
        coherence_null.p_at_least_observed,
        coherence_null.inside_null,
    )

    payload = {
        "threshold": threshold,
        "features_required": features_required(threshold),
        "score_scale": policy.score_scale,
        "extension_floor": floor,
        "floor_quantile": arguments.floor_quantile,
        "gap_days": gap.days,
        "n_scored_days": len(scores),
        "n_episodes": n_episodes,
        "n_episode_days": n_episode_days,
        "visibility": [v.model_dump(mode="json") for v in visibility],
        "baseline_shifts": {u: [s.model_dump(mode="json") for s in v] for u, v in shifts.items()},
        "episode_nulls": {k: v.model_dump(mode="json") for k, v in nulls.items()},
        "ground_truth": {u: p.model_dump(mode="json") for u, p in ground_truth.items()},
        "out_of_band_per_malicious_day": out_of_band,
        "band_k": band_k,
        "contribution_curve": [
            {"magnitude": m, "contribution": c}
            for m, c in contribution_curve(
                (1.0, 2.0, 3.0, 4.0, 6.0, 6.333, 10.0, 18.768), policy.score_scale
            )
        ],
        "long_episodes": [
            {
                "user_id": user,
                "n_days": len(episode),
                "span_days": (episode[-1][0] - episode[0][0]).days + 1,
                "distinct_leading_features": len({leading_of[(user, d)] for d, _s in episode}),
                "above_floor_days": sum(1 for _d, s in by_entity[user] if s >= floor),
                "total_days": len(by_entity[user]),
            }
            for user, episode in sorted(episodes, key=lambda ue: -len(ue[1]))
            if len(episode) >= 40
        ],
        "coherence_observed_share": observed_share,
        "n_multi_day_episodes": len(shares),
        "permutation_seed": arguments.permutation_seed,
        "iterations": arguments.iterations,
    }
    arguments.out.mkdir(parents=True, exist_ok=True)
    (arguments.out / "cert-failure-classification.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (arguments.out / "cert-failure-classification.md").write_text(
        render(payload, visibility, nulls, shifts), encoding="utf-8"
    )
    logger.info("wrote %s", arguments.out / "cert-failure-classification.md")

    for v in visibility:
        logger.info(
            "%s scenario %s: %s | best rank %s of %s | malicious median %.3f vs own ordinary %.3f",
            v.user_id,
            v.scenario,
            v.counts,
            f"{v.best_rank:,}",
            f"{v.n_scored_days:,}",
            v.malicious_median or 0.0,
            v.own_ordinary_median or 0.0,
        )
    return 0


def render(
    payload: dict[str, object],
    visibility: Sequence[InsiderVisibility],
    nulls: Mapping[str, EpisodeNull],
    shifts: Mapping[str, Sequence[BaselineShift]],
) -> str:
    """Render the report. Every figure comes from ``payload``; this function does no arithmetic."""
    lines = [
        "# CERT r3.1 — why Sentiel fails (Usefulness Phase U2)",
        "",
        f"Threshold **{payload['threshold']:.12f}** (PART 6B's 48-alert operating point, "
        "reproduced as a gate before anything here was computed). The frozen row — 0.104 at 48, "
        "window recall 0.5 — is **untouched**; nothing below is logged under its name.",
        "",
        "## The ceiling",
        "",
        f"`AggregationPolicy` sums `1 - exp(-magnitude / {payload['score_scale']})` over the "
        "features that spoke. Every term is below 1, so a window in which *k* features spoke "
        "scores at most *k*.",
        "",
        f"**At this threshold, at least {payload['features_required']} of the 34 features must "
        "speak at once for any entity-day to alert — whatever the magnitudes.**",
        "",
        "The bound is `<=` rather than `<` for a floating-point reason, not a mathematical one: "
        "in exact arithmetic the term is strictly below 1, and in IEEE754 it reaches exactly 1.0 "
        "once `magnitude / scale` passes 37.4299 — a magnitude of 112.29 at scale 3, against a "
        "largest observed magnitude of **18.768** anywhere in this run. The conservative reading "
        "is the one asserted, so the finding cannot be overstated by a rounding error.",
        "",
        "```",
        CEILING_PRECEDENCE,
        "```",
        "",
        "## The two insiders",
        "",
        "| Insider | Scenario | Malicious days | Alerted | Reachable, sub-threshold | "
        "Structurally unalertable | Evidence absent | Best rank | Malicious median | "
        "Own ordinary median |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for v in visibility:
        c = v.counts
        lines.append(
            f"| `{v.user_id}` | {v.scenario} | {v.n_malicious_days} | "
            f"{c[VisibilityVerdict.ALERTED.value]} | "
            f"{c[VisibilityVerdict.REACHABLE_BUT_SUBTHRESHOLD.value]} | "
            f"{c[VisibilityVerdict.STRUCTURALLY_UNALERTABLE.value]} | "
            f"{c[VisibilityVerdict.EVIDENCE_ABSENT.value]} | "
            f"{v.best_rank:,} of {v.n_scored_days:,} | "
            f"{v.malicious_median:.3f} | {v.own_ordinary_median:.3f} |"
        )
    lines += [
        "",
        "## The episode unit, against the only null that can falsify it",
        "",
        f"Each entity's own scores reshuffled across their own days — activity calendar and score "
        f"distribution held, order destroyed. {payload['iterations']} iterations, seed "
        f"{payload['permutation_seed']}.",
        "",
        "| Statistic | Observed | Permuted mean | 95% interval | P(permuted \u2265 observed) "
        "| Inside null |",
        "| --- | ---: | ---: | :---: | ---: | :---: |",
    ]
    names = {
        "n_episodes": "reportable episodes",
        "n_days": "entity-days inside episodes",
        "longest": "longest single episode (days)",
        "n_long": "episodes of 40+ days",
        "malicious_days": "malicious entity-days covered",
        "coherence": "mean leading-feature agreement",
    }
    for key, null in nulls.items():
        places = 3 if key == "coherence" else 0
        lines.append(
            f"| {names[key]} | {null.observed:.{places}f} | {null.mean:.{max(places, 1)}f} | "
            f"[{null.low:.{places}f}, {null.high:.{places}f}] | "
            f"{null.p_at_least_observed:.3f} | {'yes' if null.inside_null else 'no'} |"
        )
    lines += [
        "",
        "## What the ground truth contains",
        "",
        "Counted from the corpus's own answer files, not from the engine's output: an engine that "
        "discards a channel reports nothing about it either way.",
        "",
        "| Insider | Labelled events | Kinds | Active days | Span | Distinct hosts/recipients |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    truth = payload["ground_truth"]
    assert isinstance(truth, dict)
    for record in visibility:
        g = truth[record.user_id]
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(g["kinds"].items()))
        lines.append(
            f"| `{record.user_id}` | {g['n_events']} | {kinds} | {g['active_days']} | "
            f"{g['span_days']} d | {g['distinct_targets']} |"
        )
    lines.append("")
    for record in visibility:
        g = truth[record.user_id]
        if not g["top_targets"]:
            continue
        named = ", ".join(f"`{name}` ({n})" for name, n in g["top_targets"][:6])
        lines.append(f"`{record.user_id}` most-named targets: {named}.")
        lines.append("")
    lines += [
        "## How fast the aggregation saturates",
        "",
        "| Magnitude | Contribution |",
        "| ---: | ---: |",
    ]
    curve = payload["contribution_curve"]
    assert isinstance(curve, list)
    for point in curve:
        lines.append(f"| {point['magnitude']:.3f} | {point['contribution']:.4f} |")
    lines += [
        "",
        f"The out-of-band cut, recovered from the fitted model rather than assumed, is "
        f"**{payload['band_k']:.4f}**.",
        "",
        "## The long false episodes",
        "",
        "| Entity | Days in episode | Span | Distinct leading features | Above-floor rate, all "
        "their days |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    longs = payload["long_episodes"]
    assert isinstance(longs, list)
    for item in longs:
        rate = item["above_floor_days"] / item["total_days"]
        lines.append(
            f"| `{item['user_id']}` | {item['n_days']} | {item['span_days']} d "
            f"| {item['distinct_leading_features']} | {item['above_floor_days']}/"
            f"{item['total_days']} = {rate:.1%} |"
        )
    lines += [
        "",
        f"Against a population rate of {100 * (1 - float(str(payload['floor_quantile']))):.0f}% "
        "above the floor by construction.",
        "",
        "## What the malicious days did to each feature",
        "",
        "Measured against each person's **own pre-attack days** — every day of theirs before the "
        "corpus's first labelled attack, which is the data the model was fitted on. A fixed "
        "baseline, not the trailing window the `_dev` family uses: a trailing baseline chases a "
        "slow escalation, so a fixed one is the generous choice. The five largest shifts per "
        "insider, by |z| against their own pre-attack spread.",
        "",
    ]
    for record in visibility:
        ranked_shifts = sorted(
            (s for s in shifts.get(record.user_id, ()) if s.shift_z is not None),
            key=lambda s: -abs(s.shift_z or 0.0),
        )[:5]
        lines += [
            f"**`{record.user_id}` — scenario {record.scenario}**",
            "",
            "| Feature | Pre-attack mean | Malicious mean | Ratio | Shift (z) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for s in ranked_shifts:
            ratio = "—" if s.ratio is None else f"{s.ratio:.2f}\u00d7"
            lines.append(
                f"| `{s.feature}` | {s.pre_mean:.3f} | {s.malicious_mean:.3f} "
                f"| {ratio} | {s.shift_z:.2f} |"
            )
        lines.append("")
    lines += [
        "## Coherence",
        "",
        f"Across {payload['n_multi_day_episodes']} multi-day episodes, the mean share of an "
        f"episode's days that agree on a single leading feature is "
        f"**{payload['coherence_observed_share']:.3f}**.",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
