#!/usr/bin/env python3
"""Score declared-new-destination once on CERT r4.2, at 48 tickets a day (ADR 0271).

Writes the declared output and refuses to run again if that file already exists.
Refuses before reading a trace if ``src/phos/sentiel/declared_destination.py`` is
not the frozen sha256. Does not append ``eval_runs/log.jsonl``. Does not write
the frozen r3.1 6B row. Does not retune ``AggregationPolicy``, the 34 features,
the new-destination count, the rank key, or a threshold.

The declared command passes no ``--data-dir``. The default path keeps the
register-hash check live. Passing ``--data-dir`` elsewhere skips that check,
which is why the shot does not. The exact command is ``DECLARED_COMMAND``.
"""

from __future__ import annotations

import argparse
import hashlib
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
from phos.sentiel.declared_destination import (  # noqa: E402
    SCORER_NAME,
    score_declared_new_destinations,
    single_user_destination_owners,
    users_with_new_destination,
)
from phos.sentiel.entities import EntityCatalogue, user_id_of  # noqa: E402
from phos.sentiel.featurise import FeatureSet, Featuriser  # noqa: E402
from phos.sentiel.identity_score import directory_destination_register  # noqa: E402
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.named_counterparties import register_sha256  # noqa: E402
from phos.sentiel.peers import PeerGroups, PeerPolicy  # noqa: E402
from phos.sentiel.r42_holdout import r42_may_be_scored  # noqa: E402
from phos.sentiel.scoring import (  # noqa: E402
    AggregationPolicy,
    ScoredWindow,
    WindowScorer,
    static_range_model,
)
from phos.sentiel.traces import read_traces, replay_observations  # noqa: E402

logger = logging.getLogger("score_s3_destinations")

CHALLENGER_NAME: Final = "declared-new-destination:cert-r4.2@48-per-day"
FROZEN_NAME: Final = "6b:cert-r4.2@48-per-day"
DETECTOR_NAME: Final = "aggregate:gaussian:peer set (34 features) (6B)"
# Raw bytes of the scorer file. The path is not mixed in. ADR 0270.
FROZEN_SHA256: Final = "ee061bc7d86c8e24df55469a5867a8358a617f1fc1b99013bd54de0a52d5a6a3"
# ADR 0261, the r4.2 directory register, computed before that score read labels.
R42_DIRECTORY_SHA256: Final = "6b0597ae973edb27f2ff995ab1727e7bf12ae6af6aae57ba17c54169d294aac0"
DEFAULT_OUT: Final = (
    REPO_ROOT / "eval_runs" / "build" / "v1" / "sentiel" / "s3-declared-new-destination-r42.json"
)
DEFAULT_DATA: Final = REPO_ROOT / "data" / "cert-insider-threat"
SCORER_PATH: Final = REPO_ROOT / "src" / "phos" / "sentiel" / "declared_destination.py"
DECLARED_COMMAND: Final = (
    "uv run python scripts/score_s3_destinations.py "
    "--out eval_runs/build/v1/sentiel/s3-declared-new-destination-r42.json"
)
BUDGET: Final = 48
MIN_SAMPLES: Final = 8


def scorer_sha256() -> str:
    """Return the sha256 of the frozen scorer file's raw bytes."""
    return hashlib.sha256(SCORER_PATH.read_bytes()).hexdigest()


def shot_refused(out: Path, digest: str, expected: str) -> str | None:
    """Return why this shot must not start, before any corpus file is opened.

    An existing output is a second look. A digest mismatch means the challenger
    moved after it was frozen.
    """
    if out.exists():
        return f"{out} already exists; this shot is not run twice"
    if digest != expected:
        return f"scorer sha256 {digest} is not the frozen {expected}"
    return None


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
    """Fit AggregationPolicy() on the attack-free prefix and score the remainder.

    This is the PART 6B procedure ADR 0202 item 4 names. No threshold is chosen
    from the release being scored.
    """
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

    refused = shot_refused(arguments.out, scorer_sha256(), FROZEN_SHA256)
    if refused is not None:
        logger.error("%s", refused)
        return 2
    if not r42_may_be_scored():
        logger.error("r42_may_be_scored() is false; the holdout is not lifted")
        return 2

    started = time.monotonic()
    cache = arguments.cache or (arguments.data_dir / "r4.2-entity-day-traces.jsonl.gz")
    release_dir = arguments.data_dir / "r4.2"
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    register = directory_destination_register(catalogue)
    fingerprint = register_sha256(register)
    default_data = arguments.data_dir.resolve() == DEFAULT_DATA.resolve()
    if default_data and fingerprint != R42_DIRECTORY_SHA256:
        logger.error(
            "directory register hash %s is not the hash declared for r4.2",
            fingerprint,
        )
        return 1
    scored = score_declared_new_destinations(tuple(read_traces(cache)), register)
    labels = read_insiders(arguments.data_dir / "answers", "r4.2")
    insider_ids = tuple(dict.fromkeys(label.user_id for label in labels))
    first_attack = min(label.start for label in labels)
    featuriser = Featuriser(
        org_domains=frozenset({catalogue.dominant_email_domain()}),
        feature_set=FeatureSet.PEER,
        peer_groups=PeerGroups.from_catalogue(catalogue, PeerPolicy()),
    )
    six_b = _six_b(cache, featuriser, first_attack)

    challenger_rows: list[DayScore] = []
    frozen_rows: list[DayScore] = []
    for item in scored:
        if item.day < first_attack:
            continue
        key = (item.user_id, item.day)
        if key not in six_b:
            logger.error("6B did not score %s", key)
            return 1
        malicious = any(label.contains(item.user_id, item.day) for label in labels)
        challenger_rows.append(
            DayScore(
                user_id=item.user_id,
                day=item.day,
                score=float(item.new_destinations),
                malicious=malicious,
            )
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
    present = {item.user_id for item in scored}
    innocent = present - set(insider_ids)
    with_new = users_with_new_destination(scored)
    owners = single_user_destination_owners(scored)
    innocent_new = sum(1 for user in innocent if user in with_new)
    innocent_exclusive = sum(1 for user in innocent if owners.get(user, 0) > 0)
    met = s3_met(challenger_found, frozen_found)
    payload: dict[str, object] = {
        "command": DECLARED_COMMAND,
        "release": "r4.2",
        "scorer": SCORER_NAME,
        "scorer_sha256": FROZEN_SHA256,
        "register_source": "ldap-email",
        "register_sha256": fingerprint,
        "register_note": (
            "Destinations are every email address in this release's LDAP snapshots. "
            "The address list is not written here. insiders.csv was not read to choose the names."
        ),
        "budget_per_day": BUDGET,
        "rank_key": "(-score, user_id, timestamp)",
        "alerting": "phos.sentiel.exclusive_return.alerting",
        "n_labelled_insiders": len(insider_ids),
        "n_person_days": len(challenger_rows),
        "n_calendar_days": len(n_draw),
        "challenger": {
            **challenger,
            "code": "phos.sentiel.declared_destination.score_declared_new_destinations",
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
            "source": "phos.sentiel.declared_destination.users_with_new_destination",
            "scope": "whole release",
            "innocent_users": len(innocent),
            "innocent_users_with_new_declared_destination": innocent_new,
            "share_of_innocent_users": (innocent_new / len(innocent)) if innocent else None,
            "exclusive_destinations_not_the_score": {
                "source": "phos.sentiel.declared_destination.single_user_destination_owners",
                "innocent_users_with_single_user_destination": innocent_exclusive,
                "share_of_innocent_users": (
                    (innocent_exclusive / len(innocent)) if innocent else None
                ),
            },
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
        "challenger %s 6B %s chance %.4f s3_met %s realism %d/%d exclusive %d/%d",
        challenger["distinct_labelled_insiders"],
        frozen["distinct_labelled_insiders"],
        chance,
        met,
        innocent_new,
        len(innocent),
        innocent_exclusive,
        len(innocent),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
