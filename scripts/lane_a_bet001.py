#!/usr/bin/env python3
"""Bet 001's one labelled run on CERT r3.1 (ADR 0084, ADR 0093, ADR 0148).

The frozen 6B point is reproduced first and the run stops if it does not match. Then the three
declared formulas score every person-day from the same contributions. Each is ranked by
``(-score, user_id, timestamp)`` and cut at 48. All three are written, win or lose.

Nothing here appends ``eval_runs/log.jsonl`` or edits ``AggregationPolicy``.

Usage::

    uv run python scripts/lane_a_bet001.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT))

from scripts.measure_sentiel_episodes import (  # noqa: E402
    FROZEN_SIX_B,
    check_frozen_row,
)

from phos.eval.datasets import Dataset  # noqa: E402
from phos.eval.detectors import Detection  # noqa: E402
from phos.eval.harness import EvalConfig  # noqa: E402
from phos.models.detector import uncalibrated_confidence  # noqa: E402
from phos.models.gaussian import GaussianBaseline  # noqa: E402
from phos.ontology import Domain, Observation  # noqa: E402
from phos.sentiel.bet001 import (  # noqa: E402
    BUDGET,
    DayScore,
    chance_malicious_days,
    insiders_in_budget,
    rank_days,
)
from phos.sentiel.candidates import (  # noqa: E402
    DECLARED_CANDIDATES,
    FormulaTerm,
    score_candidate,
)
from phos.sentiel.entities import EntityCatalogue, user_entity_id, user_id_of  # noqa: E402
from phos.sentiel.evaluation import evaluate_entity_aware  # noqa: E402
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

logger = logging.getLogger("lane_a_bet001")

DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
DEFAULT_CACHE: Final = DEFAULT_DATA_DIR / "cert-insider-threat" / "r3.1-entity-day-traces.jsonl.gz"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "lane-a" / "bet-001.json"
SIX_B: Final = "6b-frozen"


def _summary(
    name: str,
    days: list[DayScore],
    insider_ids: tuple[str, ...],
    n_malicious: int,
) -> dict[str, object]:
    """One candidate's row: who is in the 48, best ranks, precision, and chance."""
    ranked = rank_days(days)
    rank_of = {(item.user_id, item.day): index + 1 for index, item in enumerate(ranked)}
    top = ranked[:BUDGET]
    found = insiders_in_budget(days, BUDGET)
    per_insider: dict[str, object] = {}
    for user in insider_ids:
        mine = [item for item in days if item.user_id == user and item.malicious]
        best = min((rank_of[(item.user_id, item.day)] for item in mine), default=None)
        per_insider[user] = {
            "malicious_days": len(mine),
            "in_top_48": sum(1 for item in top if item.user_id == user and item.malicious),
            "best_rank": best,
        }
    true_days = sum(1 for item in top if item.malicious)
    return {
        "candidate": name,
        "budget": BUDGET,
        "threshold_at_budget": top[-1].score if top else None,
        "found": sorted(found),
        "both_found": set(found) == set(insider_ids),
        "malicious_days_in_top_48": true_days,
        "precision_at_48": true_days / BUDGET,
        "chance_malicious_days_in_48": chance_malicious_days(len(days), n_malicious, BUDGET),
        "per_insider": per_insider,
        "n_days": len(days),
    }


def main(argv: list[str] | None = None) -> int:
    """Gate, score three candidates once, and write the result. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-samples", type=int, default=8)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)

    started_all = time.monotonic()
    release_dir = arguments.data_dir / "cert-insider-threat" / "r3.1"
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    labels = read_insiders(arguments.data_dir / "cert-insider-threat" / "answers", "r3.1")
    first_attack = min(label.start for label in labels)
    featuriser = Featuriser(
        org_domains=frozenset({catalogue.dominant_email_domain()}),
        feature_set=FeatureSet.PEER,
        peer_groups=PeerGroups.from_catalogue(catalogue, PeerPolicy()),
    )
    policy = AggregationPolicy()

    train: list[Observation] = []
    for observation in replay_observations(read_traces(arguments.cache), featuriser):
        if observation.timestamp < first_attack:
            train.append(observation)
    fitted = static_range_model(GaussianBaseline(min_samples=arguments.min_samples).fit(train))
    train.clear()
    logger.info("fitted on the attack-free prefix")

    scorer = WindowScorer(fitted, policy, None)
    rows: list[tuple[str, datetime, float, str | None, tuple[float, float, float]]] = []
    windows: list[Observation] = []
    seen: set[tuple[str, datetime]] = set()
    candidate_ids = tuple(item.candidate_id for item in DECLARED_CANDIDATES)

    def take(scored: list[ScoredWindow]) -> None:
        for window in scored:
            terms = tuple(
                FormulaTerm(
                    feature=item.feature,
                    magnitude=item.magnitude,
                    unquantified=item.unquantified,
                )
                for item in window.contributions
            )
            values = tuple(score_candidate(cid, terms).score for cid in candidate_ids)
            rows.append(
                (
                    user_id_of(window.entity_id),
                    window.timestamp,
                    window.score,
                    window.leading_feature,
                    (values[0], values[1], values[2]),
                )
            )

    for observation in replay_observations(read_traces(arguments.cache), featuriser):
        if observation.timestamp < first_attack:
            continue
        key = (observation.entity_ids[0], observation.timestamp)
        if key not in seen:
            seen.add(key)
            windows.append(observation)
        take(scorer.push(observation))
    take(scorer.close())
    logger.info("scored %d person-days", len(rows))

    ranked_six_b = sorted((row[2] for row in rows), reverse=True)
    threshold = ranked_six_b[BUDGET - 1]
    test = Dataset(
        name="cert-r3.1-user-day-peer-test",
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
                for user, day, score, leading, _values in rows
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
            logger.error("FROZEN 6B GATE FAILED: %s", problem)
        return 1
    logger.info("gate passed: 6B at 48 reproduced (precision %.6f)", report.precision)

    insiders = {label.user_id: label for label in labels}
    insider_ids = tuple(sorted(insiders))

    def malicious(user: str, day: datetime) -> bool:
        label = insiders.get(user)
        return label is not None and label.contains(user, day)

    flags = [malicious(user, day) for user, day, _s, _l, _v in rows]
    n_malicious = sum(flags)
    results: list[dict[str, object]] = []
    six_b_days = [
        DayScore(user_id=user, day=day, score=score, malicious=flag)
        for (user, day, score, _l, _v), flag in zip(rows, flags, strict=True)
    ]
    results.append(_summary(SIX_B, six_b_days, insider_ids, n_malicious))
    for index, cid in enumerate(candidate_ids):
        days = [
            DayScore(user_id=user, day=day, score=values[index], malicious=flag)
            for (user, day, _score, _l, values), flag in zip(rows, flags, strict=True)
        ]
        results.append(_summary(cid, days, insider_ids, n_malicious))

    success = [
        row["candidate"] for row in results if row["candidate"] != SIX_B and bool(row["both_found"])
    ]
    body = {
        "result_name": "lane-a-bet-001",
        "corpus": "cert-insider-threat r3.1",
        "contract": "ADR 0084, ADR 0093, ADR 0148",
        "gate": {"frozen_6b_reproduced": True, **fresh},
        "insiders": list(insider_ids),
        "n_malicious_days": n_malicious,
        "candidates": results,
        "bet_won_by": success,
        "bet_won": bool(success),
        "runtime_seconds": time.monotonic() - started_all,
        "note": (
            "One labelled run. All three declared formulas are reported. The frozen 6B row is "
            "reproduced, not overwritten. Nothing was appended to eval_runs/log.jsonl."
        ),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n")
    for row in results:
        logger.info(
            "%-14s found=%s precision@48=%.3f per_insider=%s",
            row["candidate"],
            row["found"],
            row["precision_at_48"],
            row["per_insider"],
        )
    logger.info("bet won: %s %s", bool(success), success)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
