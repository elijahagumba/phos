"""Published joint-vs-univariate rows for corpora already scored (Session C4).

This is a table, not a 10x stamp (ADR 0049 / 0053). Numbers are copied from ADRs and
the atlas-report. Do not average them into a pooled reduction. Do not fetch a new
corpus to chase 10x. Distillation recall is perturbation recall. Data4Cyber FP/hour
is refused as a control-room ruler.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PUBLIC_JOINT_VS_UNIVARIATE",
    "THREE_W_OFFSHORE_WELLS",
    "JointVsUnivariateRow",
    "RecallKind",
    "UnscoredProcessType",
]

RecallKind = Literal[
    "attack",
    "perturbation",
    "process_phase",
    "attack_recall_win_fp_loss",
]


class JointVsUnivariateRow(BaseModel):
    """One public comparison of per-signal Gaussian against ungated Mahalanobis.

    Attributes:
        corpus: Registry / report name.
        process_type: Honest plant class (water, batch, electrical, water-distribution).
        gaussian_fp_per_hour: Per-signal Gaussian false positives per normal hour.
        joint_fp_per_hour: Ungated Mahalanobis false positives per normal hour.
        ratio: ``gaussian / joint`` when both are finite and joint > 0. May be below 10.
        recall_kind: What the recall number on that row actually is.
        ten_x: Always false here. The stamp is forbidden.
        fp_hour_ruler: Whether this FP/hour may be quoted as a control-room budget.
        source: ADR or atlas-report section the numbers come from.
    """

    model_config = ConfigDict(frozen=True)

    corpus: str
    process_type: str
    gaussian_fp_per_hour: float = Field(ge=0.0)
    joint_fp_per_hour: float = Field(ge=0.0)
    ratio: float = Field(gt=0.0)
    recall_kind: RecallKind
    ten_x: Literal[False] = False
    fp_hour_ruler: Literal["quoted", "refused"]
    source: str


PUBLIC_JOINT_VS_UNIVARIATE: Final[tuple[JointVsUnivariateRow, ...]] = (
    JointVsUnivariateRow(
        corpus="hai",
        process_type="industrial-water",
        gaussian_fp_per_hour=8389.81,
        joint_fp_per_hour=646.58,
        ratio=13.0,
        recall_kind="attack",
        fp_hour_ruler="quoted",
        source="docs/atlas-report.md three-way seed 11 threshold 3.0; ADR 0009",
    ),
    JointVsUnivariateRow(
        corpus="batch-distillation",
        process_type="batch-chemical",
        gaussian_fp_per_hour=160.55,
        joint_fp_per_hour=18.72,
        ratio=8.6,
        recall_kind="perturbation",
        fp_hour_ruler="quoted",
        source="ADR 0025/0031/0048 designed protocol",
    ),
    JointVsUnivariateRow(
        corpus="data4cyber[designed]",
        process_type="electrical-distribution",
        gaussian_fp_per_hour=62727.77,
        joint_fp_per_hour=9451.02,
        ratio=6.6,
        recall_kind="process_phase",
        fp_hour_ruler="refused",
        source="ADR 0046 Track A S0/S1 seed 11",
    ),
    JointVsUnivariateRow(
        corpus="batadal",
        process_type="water-distribution",
        gaussian_fp_per_hour=0.06,
        joint_fp_per_hour=0.11,
        ratio=0.55,
        recall_kind="attack_recall_win_fp_loss",
        fp_hour_ruler="quoted",
        source="docs/atlas-report.md §3.1; Gaussian already quiet, joint wins recall 0.50→1.00",
    ),
)
"""Three process types already in hand, plus BATADAL as the water-distribution row.

Ratios: 13.0, 8.6, 6.6, 0.55. None of these is a 10x stamp.
"""


class UnscoredProcessType(BaseModel):
    """A process type named on the joint table without invented FP/hour (Session C9).

    3W payloads are ``files: []``. Classes 1-9 are faults. Do not put zeros in the
    measured table and call them a measurement.
    """

    model_config = ConfigDict(frozen=True)

    corpus: str
    process_type: str
    recall_kind: Literal["fault"]
    files_present: Literal[False] = False
    command_corpus: Literal[False] = False
    cyber_claim: Literal[False] = False
    reason: str


THREE_W_OFFSHORE_WELLS: Final = UnscoredProcessType(
    corpus="3w-petrobras",
    process_type="offshore-wells",
    recall_kind="fault",
    reason=(
        "Licence confirmed (ADR 0033). files=[] so there is no FP/hour to quote. "
        "Classes 1-9 are faults, not cyber-attacks. Detection of faults is not a cyber claim. "
        "Not a command corpus (ADR 0040). Do not collapse through default_attack_when."
    ),
)
