"""The realism.json sidecar: SYNTHETIC-DERIVED ground truth Atlas must never read.

A quiet profile writes no sidecar, so every corpus generated before this file existed stays
byte-identical. A non-quiet run writes the profile and every planned phenomenon, serialised in
sorted order, labelled SYNTHETIC-DERIVED, and listed in the manifest's ``files`` with a digest.

The sidecar is ground truth for a human reading a diagnostic. It is not an input to Atlas.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Final

from phos.synth.manifest import GeneratedFile, digest_of
from phos.synth.plant import SYNTHETIC_DERIVED, SYNTHETIC_DERIVED_BANNER
from phos.synth.realism import BenignPhenomenon, RealismPlan, RealismProfile

__all__ = ["REALISM_FILE", "REALISM_KIND", "write_realism_sidecar"]

REALISM_FILE: Final = "realism.json"
REALISM_KIND: Final = "realism-sidecar"


def _instant(clock: datetime) -> str:
    """Return an ISO-8601 UTC timestamp with a trailing Z."""
    return (
        clock.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if clock.microsecond
        else clock.strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _phenomenon(item: BenignPhenomenon) -> dict[str, object]:
    """Return one phenomenon as a JSON-ready mapping, keys and signals sorted."""
    return {
        "detail": item.detail,
        "ended_at": _instant(item.ended_at),
        "kind": item.kind.value,
        "resembles_attack": item.resembles_attack,
        "signals": list(item.signals),
        "started_at": _instant(item.started_at),
    }


def realism_document(profile: RealismProfile, plan: RealismPlan) -> dict[str, object]:
    """Return the sidecar document. Deterministic: sorted keys, sorted ageing signals."""
    dumped = profile.model_dump(mode="json")
    dumped["ambient_signals"] = list(dumped["ambient_signals"])
    dumped["ageing_signals"] = list(dumped["ageing_signals"])
    dumped["dropout_duration"] = profile.dropout_duration.total_seconds()
    return {
        "banner": SYNTHETIC_DERIVED_BANNER,
        "label": SYNTHETIC_DERIVED,
        "phenomena": [_phenomenon(item) for item in plan.phenomena],
        "plan": {
            "ageing": {key: plan.ageing[key] for key in sorted(plan.ageing)},
            "dropouts": [
                {
                    "ended_at": _instant(item.ended_at),
                    "node_id": item.node_id,
                    "retransmits": item.retransmits,
                    "started_at": _instant(item.started_at),
                }
                for item in plan.dropouts
            ],
            "n_drifts": len(plan.drifts),
            "n_faults": len(plan.faults),
        },
        "profile": {key: dumped[key] for key in sorted(dumped)},
    }


def write_realism_sidecar(
    profile: RealismProfile, plan: RealismPlan, directory: Path
) -> GeneratedFile:
    """Write ``realism.json`` and describe it for the manifest.

    Raises:
        ValueError: If the profile is quiet. Quiet runs write no sidecar.
    """
    if profile.is_quiet():
        raise ValueError("a quiet profile writes no realism sidecar")
    path = directory / REALISM_FILE
    document = realism_document(profile, plan)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=REALISM_FILE,
        kind=REALISM_KIND,
        records=len(plan.phenomena),
        sha256=sha256,
        size_bytes=size,
    )
