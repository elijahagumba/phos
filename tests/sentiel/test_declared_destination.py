"""New declared destinations. The fixture is not CERT, and it does not read r4.2."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.sentiel.bet001 import DayScore
from phos.sentiel.daily_tickets import alerts_per_day, surfaced_user_ids
from phos.sentiel.declared_destination import (
    SCORER_NAME,
    score_declared_new_destinations,
    single_user_destination_owners,
    users_with_new_destination,
)
from phos.sentiel.named_counterparties import DeclaredIdentities
from phos.sentiel.traces import EntityDayTrace

_REGISTER = DeclaredIdentities(destinations=frozenset({"a@corp.example", "b@corp.example"}))


def _trace(user: str, day: int, recipients: tuple[str, ...] = ()) -> EntityDayTrace:
    return EntityDayTrace(
        user_id=user,
        day=datetime(2010, 1, day, tzinfo=UTC),
        recipients=recipients,
    )


def test_scorer_name_is_not_the_frozen_row_or_the_host_challenger() -> None:
    assert SCORER_NAME == "declared-new-destination"
    assert "6B" not in SCORER_NAME
    assert "aggregate" not in SCORER_NAME
    assert "exclusive-host" not in SCORER_NAME


def test_cold_start_scores_zero_and_a_later_new_address_scores_one() -> None:
    quiet = tuple(_trace("A", day) for day in range(1, 9))
    first = _trace("A", 9, ("a@corp.example", "outsider@example.com"))
    repeat = _trace("A", 10, ("a@corp.example",))
    added = _trace("A", 11, ("a@corp.example", "b@corp.example"))
    scores = score_declared_new_destinations((*quiet, first, repeat, added), _REGISTER)
    assert [row.new_destinations for row in scores] == [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1]
    assert scores[8].destinations == ("a@corp.example",)
    assert scores[10].destinations == ("a@corp.example", "b@corp.example")


def test_another_users_mail_does_not_spend_this_users_destination() -> None:
    days: list[EntityDayTrace] = []
    for day in range(1, 9):
        days.append(_trace("A", day))
        days.append(_trace("B", day, ("a@corp.example",)))
    days.append(_trace("B", 9, ("a@corp.example",)))
    days.append(_trace("A", 9, ("a@corp.example",)))
    scores = score_declared_new_destinations(days, _REGISTER)
    by_user = {(row.user_id, row.day.day): row.new_destinations for row in scores}
    assert by_user[("A", 9)] == 1
    assert by_user[("B", 9)] == 0
    assert [row.user_id for row in scores[-2:]] == ["B", "A"]


def test_an_empty_register_scores_zero() -> None:
    days = tuple(_trace("A", day, ("a@corp.example",)) for day in range(1, 11))
    scores = score_declared_new_destinations(days, DeclaredIdentities())
    assert [row.new_destinations for row in scores] == [0] * 10
    assert users_with_new_destination(scores) == frozenset()


def test_days_out_of_order_are_refused() -> None:
    with pytest.raises(ValueError, match="time-ordered"):
        score_declared_new_destinations((_trace("A", 2), _trace("A", 1)), _REGISTER)


def test_a_zero_new_destination_count_is_not_an_alert() -> None:
    scored = score_declared_new_destinations(
        (
            *(_trace("A", day) for day in range(1, 10)),
            _trace("A", 10, ("a@corp.example",)),
            _trace("B", 10),
        ),
        _REGISTER,
    )
    last = scored[-2:]
    alerts = alerts_per_day(
        tuple(
            DayScore(
                user_id=row.user_id,
                day=row.day,
                score=float(row.new_destinations),
                malicious=row.user_id == "A",
            )
            for row in last
        ),
        budget=48,
    )
    assert [item.user_id for item in alerts] == ["A"]
    assert surfaced_user_ids(alerts) == ("A",)
    assert users_with_new_destination(scored) == frozenset({"A"})


def test_single_user_destinations_ignore_addresses_outside_the_register() -> None:
    days = score_declared_new_destinations(
        (
            _trace("ann", 1, ("a@corp.example", "outsider@example.com")),
            _trace("bob", 1, ("a@corp.example",)),
            _trace("bob", 2, ("b@corp.example",)),
        ),
        _REGISTER,
    )
    assert single_user_destination_owners(days) == {"bob": 1}


def test_an_existing_output_is_refused_before_any_corpus_read(tmp_path: Path) -> None:
    from scripts.score_s3_destinations import main

    out = tmp_path / "s3-declared-new-destination-r42.json"
    out.write_text("{}\n", encoding="utf-8")
    assert main(["--out", str(out), "--data-dir", str(tmp_path / "absent")]) == 2
    assert out.read_text(encoding="utf-8") == "{}\n"
    assert not (tmp_path / "absent").exists()


def test_the_frozen_digest_is_the_scorer_file(tmp_path: Path) -> None:
    from scripts.score_identity_features import DECLARED_DIRECTORY_SHA256
    from scripts.score_s3_destinations import (
        FROZEN_SHA256,
        R42_DIRECTORY_SHA256,
        scorer_sha256,
        shot_refused,
    )

    assert FROZEN_SHA256 == "ee061bc7d86c8e24df55469a5867a8358a617f1fc1b99013bd54de0a52d5a6a3"
    assert scorer_sha256() == FROZEN_SHA256
    assert R42_DIRECTORY_SHA256 == DECLARED_DIRECTORY_SHA256["r4.2"]
    missing = tmp_path / "not-written.json"
    assert shot_refused(missing, "abc", FROZEN_SHA256) == (
        f"scorer sha256 abc is not the frozen {FROZEN_SHA256}"
    )
