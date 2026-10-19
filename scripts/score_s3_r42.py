#!/usr/bin/env python3
"""Score CERT r4.2 once, at 48 tickets a day (ADR 0202).

Writes ``eval_runs/build/v1/sentiel/s3-r42.json`` and refuses to run again if that
file already exists. Does not append ``eval_runs/log.jsonl``. Does not write the
frozen r3.1 6B row. Does not retune ``AggregationPolicy``, the 34 features, the
exclusive-host count, the rank key, or a threshold.

Usage::

    uv run python scripts/score_s3_r42.py --out eval_runs/build/v1/sentiel/s3-r42.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.models.gaussian import GaussianBaseline  # noqa: E402
from phos.sentiel.bet001 import DayScore  # noqa: E402
from phos.sentiel.daily_tickets import (  # noqa: E402
    alerts_per_day,
    draw_and_people,
    expected_distinct_insiders,
    s3_met,
    surfaced_user_ids,
)
from phos.sentiel.entities import EntityCatalogue, user_id_of  # noqa: E402
from phos.sentiel.exclusive_return import (  # noqa: E402
    HostDay,
    exclusive_return_scores,
    single_user_host_owners,
)
from phos.sentiel.featurise import FeatureSet, Featuriser  # noqa: E402
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.peers import PeerGroups, PeerPolicy  # noqa: E402
from phos.sentiel.r42_holdout import r42_may_be_scored  # noqa: E402
from phos.sentiel.scoring import (  # noqa: E402
    AggregationPolicy,
    ScoredWindow,
    WindowScorer,
    static_range_model,
)
from phos.sentiel.traces import read_traces, replay_observations  # noqa: E402

logger = logging.getLogger("score_s3_r42")

CHALLENGER_NAME: Final = "exclusive-host-return:cert-r4.2@48-per-day"
FROZEN_NAME: Final = "6b:cert-r4.2@48-per-day"
DETECTOR_NAME: Final = "aggregate:gaussian:peer set (34 features) (6B)"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "v1" / "sentiel" / "s3-r42.json"
DEFAULT_DATA: Final = REPO_ROOT / "data" / "cert-insider-threat"
BUDGET: Final = 48
MIN_SAMPLES: Final = 8


def _arm(
    name: str,
    days: list[DayScore],
    insider_ids: tuple[str, ...],
) -> dict[str, object]:
    """One scorer's per-day alerts and the distinct insiders those alerts surface."""
    alerts = alerts_per_day(days, BUDGET)
    surfaced = surfaced_user_ids(alerts)
    labelled = sum(1 for item in alerts if item.malicious)
    per_insider: dict[str, dict[str, object]] = {}
    for user in insider_ids:
        mine = [item for item in days if item.user_id == user and item.malicious]
        hit = sum(1 for item in alerts if item.user_id == user and item.malicious)
        per_insider[user] = {
            "malicious_person_days": len(mine),
            "malicious_days_alerted": hit,
            "surfaced": hit > 0,
        }
    return {
        "result_name": name,
        "distinct_labelled_insiders": len(surfaced),
        "surfaced_user_ids": list(surfaced),
        "alerts_raised": len(alerts),
        "labelled_days_among_alerts": labelled,
        "precision_over_alerts_raised": (labelled / len(alerts)) if alerts else None,
        "per_insider": per_insider,
    }


def _six_b(
    cache: Path, featuriser: Featuriser, first_attack: datetime
) -> dict[tuple[str, datetime], float]:
    """Fit AggregationPolicy() on the attack-free prefix and score the remainder."""
    policy = AggregationPolicy()
    train = [
        observation
        for observation in replay_observations(read_traces(cache), featuriser)
        if observation.timestamp < first_attack
    ]
    if not train:
        raise RuntimeError(
            f"no observation falls before the first labelled attack at {first_attack}"
        )
    fitted = static_range_model(GaussianBaseline(min_samples=MIN_SAMPLES).fit(train))
    logger.info("fitted gaussian on %d training observations", len(train))
    del train
    scorer = WindowScorer(fitted, policy, None)
    scores: dict[tuple[str, datetime], float] = {}

    def take(windows: list[ScoredWindow]) -> None:
        for window in windows:
            scores[(user_id_of(window.entity_id), window.timestamp)] = window.score

    for observation in replay_observations(read_traces(cache), featuriser):
        if observation.timestamp < first_attack:
            continue
        take(scorer.push(observation))
    take(scorer.close())
    return scores


def main(argv: list[str] | None = None) -> int:
    """Score both arms once. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)

    if arguments.out.exists():
        logger.error("%s already exists; this shot is not run twice", arguments.out)
        return 2
    if not r42_may_be_scored():
        logger.error("r42_may_be_scored() is false; the holdout is not lifted")
        return 2

    started = time.monotonic()
    cache = arguments.cache or (arguments.data_dir / "r4.2-entity-day-traces.jsonl.gz")
    release_dir = arguments.data_dir / "r4.2"
    labels = read_insiders(arguments.data_dir / "answers", "r4.2")
    insider_ids = tuple(dict.fromkeys(label.user_id for label in labels))
    first_attack = min(label.start for label in labels)
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    featuriser = Featuriser(
        org_domains=frozenset({catalogue.dominant_email_domain()}),
        feature_set=FeatureSet.PEER,
        peer_groups=PeerGroups.from_catalogue(catalogue, PeerPolicy()),
    )

    host_days: list[HostDay] = []
    for trace in read_traces(cache):
        host_days.append(HostDay(trace.user_id, trace.day, trace.hosts))
    exclusive = exclusive_return_scores(host_days)
    six_b = _six_b(cache, featuriser, first_attack)

    challenger_rows: list[DayScore] = []
    frozen_rows: list[DayScore] = []
    for item, score in zip(host_days, exclusive, strict=True):
        if item.day < first_attack:
            continue
        key = (item.user_id, item.day)
        if key not in six_b:
            logger.error("6B did not score %s", key)
            return 1
        malicious = any(label.contains(item.user_id, item.day) for label in labels)
        challenger_rows.append(
            DayScore(user_id=item.user_id, day=item.day, score=float(score), malicious=malicious)
        )
        frozen_rows.append(
            DayScore(user_id=item.user_id, day=item.day, score=six_b.pop(key), malicious=malicious)
        )
    if six_b:
        logger.error("6B scored %d person-days the queue does not have", len(six_b))
        return 1

    n_draw, n_people = draw_and_people(challenger_rows, BUDGET)
    malicious_days: dict[str, list[date]] = {user: [] for user in insider_ids}
    for row in challenger_rows:
        if row.malicious:
            stamp = row.day if row.day.tzinfo is not None else row.day.replace(tzinfo=UTC)
            malicious_days[row.user_id].append(stamp.astimezone(UTC).date())
    try:
        chance = expected_distinct_insiders(malicious_days, n_draw, n_people)
    except ValueError as error:
        logger.error("chance null refused: %s", error)
        return 1

    challenger = _arm(CHALLENGER_NAME, challenger_rows, insider_ids)
    frozen = _arm(FROZEN_NAME, frozen_rows, insider_ids)
    challenger_found = int(str(challenger["distinct_labelled_insiders"]))
    frozen_found = int(str(frozen["distinct_labelled_insiders"]))
    owners = single_user_host_owners(host_days)
    present = {item.user_id for item in host_days}
    innocent = present - set(insider_ids)
    innocent_with = sum(1 for user in innocent if owners.get(user, 0) > 0)
    met = s3_met(challenger_found, frozen_found)
    payload: dict[str, object] = {
        "command": (
            "uv run python scripts/score_s3_r42.py --out eval_runs/build/v1/sentiel/s3-r42.json"
        ),
        "release": "r4.2",
        "budget_per_day": BUDGET,
        "rank_key": "(-score, user_id, timestamp)",
        "alerting": "phos.sentiel.exclusive_return.alerting",
        "n_labelled_insiders": len(insider_ids),
        "n_person_days": len(challenger_rows),
        "n_calendar_days": len(n_draw),
        "challenger": {
            **challenger,
            "code": "phos.sentiel.exclusive_return.exclusive_return_scores",
        },
        "frozen_6b": {
            **frozen,
            "detector_name": DETECTOR_NAME,
            "policy": "AggregationPolicy()",
        },
        "chance_null_expected_distinct_insiders": chance,
        "s3_met": met,
        "s3_rule": (
            "met only if the challenger surfaces more distinct labelled insiders than frozen 6B"
        ),
        "realism": {
            "source": "phos.sentiel.exclusive_return.single_user_host_owners",
            "scope": "whole release",
            "innocent_users": len(innocent),
            "innocent_users_with_single_user_host": innocent_with,
            "share_of_innocent_users": (innocent_with / len(innocent)) if innocent else None,
        },
        "frozen_r31_row_written": False,
        "log_jsonl_appended": False,
        "seconds": round(time.monotonic() - started, 1),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.out.with_suffix(arguments.out.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(arguments.out)
    logger.info(
        "challenger %s 6B %s chance %.4f s3_met %s realism %d/%d",
        challenger["distinct_labelled_insiders"],
        frozen["distinct_labelled_insiders"],
        chance,
        met,
        innocent_with,
        len(innocent),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
