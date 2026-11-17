"""The objective function: stealth subject to harm (PART S7).

The breaker maximises ``stealth * harm`` where stealth is how well the attack evaded Atlas
and harm is whether it produced a real physical effect. Both sides are documented and
versioned so an objective change is visible in the record.
"""

from __future__ import annotations

from dataclasses import dataclass

OBJECTIVE_VERSION: str = "s7-objective-v1"
"""The version of the objective function. Changes here are recorded in every attempt log."""


@dataclass(frozen=True)
class Objective:
    """Score one attack outcome: how stealthy, how harmful, and the combined objective.

    Attributes:
        stealth: 0.0 = Atlas alerted loudly, 1.0 = Atlas saw nothing.
        harm: 0.0 = no physical effect, 1.0 = a documented limit was exceeded.
        value: ``stealth * harm`` — the number the search maximises. An attack that is
            perfectly stealthy but harmless scores 0; one that causes harm but is caught
            every time also scores 0.
    """

    stealth: float
    harm: float
    value: float

    def __post_init__(self) -> None:
        """Validate that all scores are in [0, 1]."""
        for name, value in (("stealth", self.stealth), ("harm", self.harm), ("value", self.value)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")


def score(alerts_raised: int, max_alerts: int, physical_effect: bool) -> Objective:
    """Compute the objective from an outcome.

    Args:
        alerts_raised: How many alerts Atlas raised during the attack window.
        max_alerts: The maximum alerts Atlas could have raised (the alert budget for the
            window), used to normalise stealth.
        physical_effect: Whether the attack produced a real physical effect in the
            simulation (a level or temperature excursion beyond a documented limit, or a
            product-quality proxy).

    Returns:
        An ``Objective`` with stealth, harm and the combined value.
    """
    if max_alerts <= 0:
        stealth = 1.0 if alerts_raised == 0 else 0.0
    else:
        stealth = max(0.0, 1.0 - (alerts_raised / max_alerts))
    harm = 1.0 if physical_effect else 0.0
    return Objective(stealth=stealth, harm=harm, value=stealth * harm)


def objective_version() -> str:
    """Return the objective function's version string."""
    return OBJECTIVE_VERSION


__all__ = ["OBJECTIVE_VERSION", "Objective", "objective_version", "score"]
