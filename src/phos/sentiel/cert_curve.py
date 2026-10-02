"""CERT r3.1 recall at a ticket budget, as a frozen curve (Session S4).

The 48-alert point stays precision **0.104** / recall **0.5** (6B). ``:precision`` at the
same budget is **0.083** and is a measured loss (ADR 0032). Do not headline it. 30-50
tickets/day is not earned on CERT. r4.2 events are not a substitute ruler.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CERT_R31_BUDGET_CURVE",
    "CERT_R31_HEADLINE_ALERTS",
    "BudgetPoint",
]

CERT_R31_HEADLINE_ALERTS: Final = 48


class BudgetPoint(BaseModel):
    """One operating point on the public CERT curve.

    Attributes:
        alerts: Ticket count at this point.
        precision: Positive predictive value.
        recall: Window recall.
        name: Detector / policy name.
        headline: Whether this point is the public ruler.
    """

    model_config = ConfigDict(frozen=True)

    alerts: int = Field(ge=1)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    name: str
    headline: bool = False
    kind: Literal["identity_6b", "precision_policy"]


CERT_R31_BUDGET_CURVE: Final[tuple[BudgetPoint, ...]] = (
    BudgetPoint(
        alerts=CERT_R31_HEADLINE_ALERTS,
        precision=0.104,
        recall=0.5,
        name="aggregate:gaussian:peer set (34 features) (6B)",
        headline=True,
        kind="identity_6b",
    ),
    BudgetPoint(
        alerts=CERT_R31_HEADLINE_ALERTS,
        precision=0.083,
        recall=0.5,
        name=":precision",
        headline=False,
        kind="precision_policy",
    ),
)
