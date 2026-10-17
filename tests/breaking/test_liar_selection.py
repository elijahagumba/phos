"""The water-liar task's qualify-and-choose rule (ADR 0121)."""

from __future__ import annotations

from phos.breaking.liar_selection import choose, qualifies

POWER = ["power-generation", 4242, 0.0]


def a_card(water: int, total: int, passing: list[list[object]], hai: int = 37) -> dict[str, object]:
    by_plant = {"water-treatment": water, "power-generation": 0, "batch-reactor": 0}
    return {
        "liar": {"passes": total, "passes_by_plant": by_plant, "passing": passing},
        "hai-20.07": {"caught": hai, "attacks": 38},
    }


CHAMPION = a_card(0, 1, [POWER])


def an_attempt(candidate: dict[str, object], card: dict[str, object]) -> dict[str, object]:
    return {"candidate": candidate, "scorecard": card}


def test_more_water_no_loss_and_hai_held_qualifies() -> None:
    assert qualifies(CHAMPION, a_card(3, 4, [POWER])) == []


def test_no_more_water_does_not_qualify() -> None:
    assert "not above" in qualifies(CHAMPION, a_card(0, 1, [POWER]))[0]


def test_a_lost_champion_pass_does_not_qualify() -> None:
    assert "loses 1 run" in qualifies(CHAMPION, a_card(3, 3, []))[0]


def test_lower_hai_does_not_qualify() -> None:
    assert "HAI 20.07 36" in qualifies(CHAMPION, a_card(3, 4, [POWER], hai=36))[0]


def test_nothing_qualifying_chooses_nothing() -> None:
    assert choose(CHAMPION, [an_attempt({"lags": [0]}, a_card(0, 1, [POWER]))]) is None


def test_most_water_wins_then_total_then_fewest_fields_then_earliest() -> None:
    few = an_attempt({"lags": [0, 300]}, a_card(5, 9, [POWER]))
    many = an_attempt({"lags": [0, 300], "detrend_window": 7200}, a_card(5, 9, [POWER]))
    more_total = an_attempt({"lags": [0, 600]}, a_card(5, 10, [POWER]))
    most_water = an_attempt({"lags": [0, 900]}, a_card(6, 7, [POWER]))
    assert choose(CHAMPION, [few, many, more_total, most_water]) is most_water
    assert choose(CHAMPION, [few, many, more_total]) is more_total
    assert choose(CHAMPION, [many, few]) is few
    twin = an_attempt({"lags": [0, 120]}, a_card(5, 9, [POWER]))
    assert choose(CHAMPION, [few, twin]) is few


def test_the_plant_map_task_chooses_by_passes_then_water_then_fewest_overrides() -> None:
    from phos.breaking.liar_selection import choose_detector, qualifies_detector

    champion = a_card(0, 24, [POWER])
    plain = an_attempt({"detector": "atlas-plant-map-v1"}, a_card(22, 55, [POWER]))
    tuned = an_attempt(
        {"detector": "atlas-plant-map-v1", "map": {"min_gain": 0.03}}, a_card(25, 55, [POWER])
    )
    weak = an_attempt({"detector": "atlas-plant-map-v1"}, a_card(0, 29, [POWER]))
    lossy = an_attempt({"detector": "atlas-plant-map-v1"}, a_card(30, 70, []))
    low_hai = an_attempt({"detector": "atlas-plant-map-v1"}, a_card(30, 70, [POWER], hai=36))
    assert qualifies_detector(champion, plain["scorecard"]) == []  # type: ignore[arg-type]
    assert qualifies_detector(champion, weak["scorecard"])  # type: ignore[arg-type]
    assert qualifies_detector(champion, lossy["scorecard"])  # type: ignore[arg-type]
    assert qualifies_detector(champion, low_hai["scorecard"])  # type: ignore[arg-type]
    assert choose_detector(champion, [plain, tuned, weak, lossy, low_hai]) is tuned
    assert choose_detector(champion, [weak, lossy]) is None
