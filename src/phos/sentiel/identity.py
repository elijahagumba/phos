"""Self / declared-role / organisation / temporal scores as separate numbers.

Peer-relative advantage stays retired on CERT (ADR 0022 / 0023). These layers are not pooled
into one "unusual" score. Hypothesis confidence stays uncalibrated and unsurfaced.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["IdentityLayerScores", "score_identity_layers"]


class IdentityLayerScores(BaseModel):
    """Four baselines for one person-window, plus an explicitly empty peer slot on CERT."""

    model_config = ConfigDict(frozen=True)

    self_score: float
    role_score: float
    org_score: float
    temporal_score: float
    peer_score: float | None = None
    pooled_unusual: None = None
    corpus: str = ""


def score_identity_layers(
    *,
    self_value: float,
    self_mean: float,
    self_std: float,
    role_value: float,
    role_mean: float,
    role_std: float,
    org_value: float,
    org_mean: float,
    org_std: float,
    temporal_value: float,
    temporal_mean: float,
    temporal_std: float,
    corpus: str,
) -> IdentityLayerScores:
    """Return per-layer z-magnitudes. Peer is ``None`` on CERT r3.1."""
    scores = IdentityLayerScores(
        self_score=_z_magnitude(self_value, self_mean, self_std),
        role_score=_z_magnitude(role_value, role_mean, role_std),
        org_score=_z_magnitude(org_value, org_mean, org_std),
        temporal_score=_z_magnitude(temporal_value, temporal_mean, temporal_std),
        peer_score=None,
        corpus=corpus,
    )
    return scores


def _z_magnitude(value: float, mean: float, std: float) -> float:
    scale = std if std > 1e-9 else 1.0
    return abs(value - mean) / scale
