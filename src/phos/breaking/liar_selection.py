"""The water-liar task's declared rule for which arena attempts qualify, and which is chosen.

Written as code from the task's ``evaluation_plan`` (`experiments/arena/water-liar/task.json`,
ADR 0121), so the choice among candidates is mechanical. Kept out of the arena's scorer files on
purpose: it reads scorecards and never computes one, so changing it cannot change a score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["choose", "choose_detector", "qualifies", "qualifies_detector"]


def _passing(card: Mapping[str, object]) -> set[tuple[str, int, float]]:
    liar = card["liar"]
    assert isinstance(liar, dict)
    return {(str(p), int(s), float(t)) for p, s, t in liar["passing"]}


def _water(card: Mapping[str, object]) -> int:
    liar = card["liar"]
    assert isinstance(liar, dict)
    return int(liar["passes_by_plant"]["water-treatment"])


def _hai(card: Mapping[str, object]) -> int:
    hai = card["hai-20.07"]
    assert isinstance(hai, dict)
    return int(hai["caught"])


def qualifies(champion: Mapping[str, object], candidate: Mapping[str, object]) -> list[str]:
    """The water-liar task's declared rule. Returns every reason it fails; empty means it qualifies.

    More water-treatment passes than the champion; no run the champion passes is lost; HAI 20.07
    at least the champion's. Both arguments are scorecards as `scripts/arena.py` writes them.
    """
    reasons: list[str] = []
    if _water(candidate) <= _water(champion):
        reasons.append(f"water {_water(candidate)} is not above the champion's {_water(champion)}")
    lost = sorted(_passing(champion) - _passing(candidate))
    if lost:
        reasons.append(f"loses {len(lost)} run(s) the champion passes: {lost}")
    if _hai(candidate) < _hai(champion):
        reasons.append(f"HAI 20.07 {_hai(candidate)} is below the champion's {_hai(champion)}")
    return reasons


def choose(
    champion: Mapping[str, object], attempts: Sequence[Mapping[str, object]]
) -> Mapping[str, object] | None:
    """The declared choice among qualifying attempts, or ``None`` if none qualifies.

    Most water passes, then most passes in total, then fewest changed window fields, then the
    earliest attempt. Each attempt is a mapping with ``candidate`` and ``scorecard``.
    """
    eligible = [a for a in attempts if not qualifies(champion, _card(a))]
    if not eligible:
        return None

    def key(item: tuple[int, Mapping[str, object]]) -> tuple[int, int, int, int]:
        index, attempt = item
        card = _card(attempt)
        liar = card["liar"]
        assert isinstance(liar, dict)
        candidate = attempt["candidate"]
        assert isinstance(candidate, dict)
        return (-_water(card), -int(liar["passes"]), len(candidate), index)

    return min(enumerate(eligible), key=key)[1]


def _card(attempt: Mapping[str, object]) -> Mapping[str, object]:
    card = attempt["scorecard"]
    assert isinstance(card, dict)
    return card


def qualifies_detector(
    champion: Mapping[str, object], candidate: Mapping[str, object]
) -> list[str]:
    """The plant-map task's declared rule (ADR 0127). Every reason it fails; empty qualifies.

    At least 24 of 90 liar passes with water above 0 (ADR 0123 §9.2), no run the champion passes
    lost, and HAI 20.07 at least 37 (§9.4).
    """
    reasons: list[str] = []
    liar = candidate["liar"]
    assert isinstance(liar, dict)
    if int(liar["passes"]) < 24:
        reasons.append(f"{liar['passes']} liar passes, under 24")
    if _water(candidate) <= 0:
        reasons.append("no water-treatment pass")
    lost = sorted(_passing(champion) - _passing(candidate))
    if lost:
        reasons.append(f"loses {len(lost)} run(s) the champion passes: {lost}")
    if _hai(candidate) < 37:
        reasons.append(f"HAI 20.07 {_hai(candidate)} is under 37")
    return reasons


def choose_detector(
    champion: Mapping[str, object], attempts: Sequence[Mapping[str, object]]
) -> Mapping[str, object] | None:
    """ADR 0127's choice: most passes, then most water passes, then fewest overrides, earliest."""
    eligible = [a for a in attempts if not qualifies_detector(champion, _card(a))]
    if not eligible:
        return None

    def key(item: tuple[int, Mapping[str, object]]) -> tuple[int, int, int, int]:
        index, attempt = item
        card = _card(attempt)
        liar = card["liar"]
        assert isinstance(liar, dict)
        candidate = attempt["candidate"]
        assert isinstance(candidate, dict)
        overrides = candidate.get("map", {})
        assert isinstance(overrides, dict)
        return (-int(liar["passes"]), -_water(card), len(overrides), index)

    return min(enumerate(eligible), key=key)[1]
