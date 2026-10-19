"""ADR 0149 keep rule and stream combination."""

from datetime import UTC, datetime

from phos.sentiel.bet001 import DayScore
from phos.sentiel.day_facts import DayFacts
from phos.sentiel.dev_loop import FittedStreams, LoopSnapshot, decide_keep, snapshot
from phos.sentiel.traces import DeclaredToken


def _snap(found: tuple[str, ...], precision: float, cch_rank: int | None) -> LoopSnapshot:
    return LoopSnapshot(
        name="t",
        found=found,
        both_found=set(found) == {"CSF0929", "CCH0959"},
        precision_at_48=precision,
        chance_malicious_days_in_48=0.01,
        per_insider={
            "CSF0929": {
                "malicious_days": 11,
                "in_top_48": 1 if "CSF0929" in found else 0,
                "best_rank": 1 if "CSF0929" in found else 100,
            },
            "CCH0959": {
                "malicious_days": 42,
                "in_top_48": 1 if "CCH0959" in found else 0,
                "best_rank": cch_rank,
            },
        },
        n_days=100,
        n_malicious=5,
    )


def test_losing_the_first_insider_is_always_a_revert() -> None:
    current = _snap(("CSF0929",), 0.10, 900)
    candidate = _snap(("CCH0959",), 0.20, 10)
    assert decide_keep(current, candidate) == "revert"


def test_finding_the_second_insider_is_a_keep_even_if_precision_falls() -> None:
    current = _snap(("CSF0929",), 0.10, 900)
    candidate = _snap(("CCH0959", "CSF0929"), 0.04, 12)
    assert decide_keep(current, candidate) == "keep"


def test_a_better_missed_rank_is_kept_only_when_precision_holds() -> None:
    current = _snap(("CSF0929",), 0.10, 900)
    better = _snap(("CSF0929",), 0.10, 400)
    worse_precision = _snap(("CSF0929",), 0.08, 400)
    assert decide_keep(current, better) == "keep"
    assert decide_keep(current, worse_precision) == "revert"


def test_fitted_streams_sum_only_the_named_ones() -> None:
    train = [
        DayFacts(
            user_id="A",
            day=datetime(2010, 1, index + 1, tzinfo=UTC),
            role="Sales",
            logons=1,
            hosts=("shared.example",),
            sequence=(DeclaredToken.LOGON,),
        )
        for index in range(10)
    ]
    train.append(
        DayFacts(
            user_id="B",
            day=datetime(2010, 1, 1, tzinfo=UTC),
            role="Sales",
            hosts=("shared.example",),
        )
    )
    model = FittedStreams.fit(train)
    quiet = DayFacts(
        user_id="A",
        day=datetime(2010, 2, 1, tzinfo=UTC),
        role="Sales",
        logons=1,
        hosts=("shared.example",),
        sequence=(DeclaredToken.LOGON,),
    )
    assert model.score(quiet, ("depth",)) == 0.0
    loud = DayFacts(
        user_id="A",
        day=datetime(2010, 2, 2, tzinfo=UTC),
        role="Sales",
        logons=1,
        hosts=("rare.example",),
    )
    assert model.score(loud, ("peer_links",)) > 0.0
    assert model.score(loud, ("depth",)) == 0.0


def test_snapshot_uses_the_published_budget() -> None:
    days = [
        DayScore(
            user_id="CSF0929",
            day=datetime(2010, 7, 1, tzinfo=UTC),
            score=9.0,
            malicious=True,
        ),
        *[
            DayScore(user_id=f"N{index:03d}", day=datetime(2010, 7, 1, tzinfo=UTC), score=2.0)
            for index in range(50)
        ],
        DayScore(
            user_id="CCH0959",
            day=datetime(2010, 7, 1, tzinfo=UTC),
            score=1.0,
            malicious=True,
        ),
    ]
    row = snapshot("lane-a-dev:t", days, ("CCH0959", "CSF0929"))
    assert row.found == ("CSF0929",)
    assert row.both_found is False
    assert row.per_insider["CSF0929"]["best_rank"] == 1
