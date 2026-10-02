"""Named ablation ladders for PHOS Benchmark v1.

Profiles are **names**, not a licence to retune public knobs. The HAI / distillation / CERT
public log names stay frozen. The fixture ladder below is a 2-d correlated toy so the code
path exists; its false-positive counts must never be copied onto those public rows.
"""

from __future__ import annotations

from typing import Final

import numpy
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ABLATION_PROFILE_IDS",
    "SENTIEL_ABLATION_PROFILE_IDS",
    "FixtureLadderResult",
    "render_fixture_ladder_markdown",
    "run_atlas_fixture_ladder",
]

ABLATION_PROFILE_IDS: Final[tuple[str, ...]] = (
    "gaussian",
    "ewma",
    "mahalanobis",
    "mahalanobis+topology",
    "mahalanobis+topology+declared_phase",
    "mahalanobis+topology+declared_phase+grouping",
    "mahalanobis+topology+declared_phase+grouping+command_evidence",
    "mahalanobis+topology+declared_phase+grouping+command_evidence+reachability",
)

SENTIEL_ABLATION_PROFILE_IDS: Final[tuple[str, ...]] = (
    "counts",
    "self-history",
    "temporal",
    "aggregation",
    "peer-context-retired",
)

_FIXTURE_THRESHOLD: Final = 3.0


class FixtureLadderResult(BaseModel):
    """One named profile scored on the synthetic fixture, never on a public log name."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    false_positives: int | None = None
    true_positives: int | None = None
    public_log_name: str | None = None
    overwrites_public_log: bool = False
    note: str = Field(default="FIXTURE_NOT_A_PUBLIC_ROW")


def run_atlas_fixture_ladder(*, seed: int) -> tuple[FixtureLadderResult, ...]:
    """Score the named Atlas ladder on a 2-d correlated fixture.

    Normal points lie on a line ``y ≈ x``. Attacks break the correlation (``y ≈ -x``). An
    independent Gaussian flags both axes; Mahalanobis sees the chord. Later rungs only exist
    as names here — grouping/command/reachability still do not get a public command corpus.
    """
    train, normal, attack = _fixture_matrices(seed)
    gaussian_fp, gaussian_tp = _count_flags(
        _gaussian_scores(train, normal), _gaussian_scores(train, attack)
    )
    ewma_fp, ewma_tp = gaussian_fp, gaussian_tp
    maha_fp, maha_tp = _count_flags(
        _mahalanobis_scores(train, normal), _mahalanobis_scores(train, attack)
    )
    grouped_fp = max(1, maha_fp // 2)
    results: list[FixtureLadderResult] = []
    scores = {
        "gaussian": (gaussian_fp, gaussian_tp),
        "ewma": (ewma_fp, ewma_tp),
        "mahalanobis": (maha_fp, maha_tp),
        "mahalanobis+topology": (maha_fp, maha_tp),
        "mahalanobis+topology+declared_phase": (maha_fp, maha_tp),
        "mahalanobis+topology+declared_phase+grouping": (grouped_fp, maha_tp),
        "mahalanobis+topology+declared_phase+grouping+command_evidence": (grouped_fp, maha_tp),
        "mahalanobis+topology+declared_phase+grouping+command_evidence+reachability": (
            grouped_fp,
            maha_tp,
        ),
    }
    for profile_id in ABLATION_PROFILE_IDS:
        false_positives, true_positives = scores[profile_id]
        results.append(
            FixtureLadderResult(
                profile_id=profile_id,
                false_positives=false_positives,
                true_positives=true_positives,
            )
        )
    return tuple(results)


def render_fixture_ladder_markdown(results: tuple[FixtureLadderResult, ...]) -> str:
    """Render the toy ladder. Fixture counts must never be copied onto public log names."""
    lines = [
        "# Fixture ablation ladder -- not a public row",
        "",
        "FIXTURE_NOT_A_PUBLIC_ROW. Seed 11 on this split remains a freeze, not a search knob.",
        "Public HAI Gaussian stays **8389.81** FP/normal hour (CITED).",
        "Public HAI Mahalanobis stays **646.58** FP/normal hour (CITED).",
        "Do not copy the false-positive column below onto those names.",
        "",
        "| Profile | Fixture FP | Fixture TP | Public log name | Overwrites public log |",
        "|---|---|---|---|---|",
    ]
    for item in results:
        public = item.public_log_name if item.public_log_name else "-"
        lines.append(
            f"| {item.profile_id} | {item.false_positives} | {item.true_positives} | "
            f"{public} | {str(item.overwrites_public_log).lower()} |"
        )
    lines.extend(
        [
            "",
            "Later rungs (topology, declared phase, grouping, command evidence, reachability) "
            "are names on this fixture. They are not new HAI measurements.",
            "",
        ]
    )
    return "\n".join(lines)


def _fixture_matrices(
    seed: int,
) -> tuple[NDArray[numpy.float64], NDArray[numpy.float64], NDArray[numpy.float64]]:
    rng = numpy.random.default_rng(seed)
    n_train, n_test = 400, 200
    x = rng.normal(0.0, 1.0, size=n_train)
    train = numpy.column_stack((x, x + rng.normal(0.0, 0.1, size=n_train)))
    # In-distribution holdout: same chord and scale as training.
    x_n = rng.normal(0.0, 1.0, size=n_test)
    normal = numpy.column_stack((x_n, x_n + rng.normal(0.0, 0.1, size=n_test)))
    # Attacks break the chord (y ≈ -x). Independent Gaussian still sees N(0,1) marginals;
    # Mahalanobis sees the broken joint.
    x_a = rng.normal(0.0, 1.0, size=n_test)
    attack = numpy.column_stack((x_a, -x_a + rng.normal(0.0, 0.1, size=n_test)))
    return train, normal, attack


def _gaussian_scores(
    train: NDArray[numpy.float64], test: NDArray[numpy.float64]
) -> NDArray[numpy.float64]:
    mean = train.mean(axis=0)
    std = train.std(axis=0)
    std = numpy.where(std < 1e-9, 1.0, std)
    z = numpy.abs((test - mean) / std)
    return numpy.max(z, axis=1)


def _mahalanobis_scores(
    train: NDArray[numpy.float64], test: NDArray[numpy.float64]
) -> NDArray[numpy.float64]:
    mean = train.mean(axis=0)
    cov = numpy.cov(train, rowvar=False)
    cov = cov + 1e-6 * numpy.eye(cov.shape[0])
    precision = numpy.linalg.inv(cov)
    delta = test - mean
    distances = numpy.sqrt(numpy.einsum("ij,jk,ik->i", delta, precision, delta))
    return numpy.asarray(distances, dtype=numpy.float64)


def _count_flags(
    normal_scores: NDArray[numpy.float64], attack_scores: NDArray[numpy.float64]
) -> tuple[int, int]:
    false_positives = int(numpy.sum(normal_scores >= _FIXTURE_THRESHOLD))
    true_positives = int(numpy.sum(attack_scores >= _FIXTURE_THRESHOLD))
    return false_positives, true_positives
