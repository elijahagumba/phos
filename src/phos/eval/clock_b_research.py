"""Clock B research scoreboard behind the frozen Benchmark v1 ruler (ADR 0062).

This module cites public rows. It does not overwrite them. Fixture wins are not public
rows. Distillation phase inference stays refused. Sequences do not replace CERT 6B.
Command reconstruction completeness is not a lead rate. P1 stays a human conversation.
"""

from __future__ import annotations

from pathlib import Path

from phos.atlas.command_reconstruction import (
    IssuerKind,
    reconstruction_completeness,
    reconstructions_from_attack_config,
)
from phos.atlas.transitions import DeclaredPhaseTransitionModel, refuse_inferred_phase
from phos.eval.ablation import run_atlas_fixture_ladder
from phos.eval.benchmark import (
    BENCHMARK_SEED,
    CERT_SIX_B_PRECISION_AT_48,
    DISTILLATION_UNGATED_FP_PER_HOUR,
    HAI_GAUSSIAN_FP_PER_HOUR,
    HAI_MAHALANOBIS_FP_PER_HOUR,
    KNOWN_STATION_LED,
    KNOWN_STATION_N,
    UNKNOWN_MASTER_LED,
    UNKNOWN_MASTER_N,
)
from phos.eval.metrics import false_positives_per_day, precision_at_budget
from phos.reasoning.counterfactual import consequences_for
from phos.reasoning.fixtures import score_fixtures
from phos.sentiel.identity import score_identity_layers
from phos.sentiel.sequences import REPLACES_CERT_SIX_B, rare_path_beats_count_baseline

__all__ = ["assemble_clock_b_research"]

_D2_CONFIGS: tuple[str, ...] = (
    "01-water-treatment-graded.toml",
    "02-power-generation-graded.toml",
    "03-batch-reactor-graded.toml",
    "08-water-unknown-master.toml",
)


def assemble_clock_b_research(repo_root: Path) -> str:
    """Render the Wave 3 scoreboard. Public log names stay cited, not rewritten."""
    ladder = {item.profile_id: item for item in run_atlas_fixture_ladder(seed=BENCHMARK_SEED)}
    gaussian = ladder["gaussian"]
    mahalanobis = ladder["mahalanobis"]
    fixture_mahalanobis_wins = (
        mahalanobis.true_positives is not None
        and gaussian.true_positives is not None
        and mahalanobis.true_positives > gaussian.true_positives
    )
    distillation_day = false_positives_per_day(DISTILLATION_UNGATED_FP_PER_HOUR)
    cert_budget = precision_at_budget((True,) * 5 + (False,) * 43, 48)
    scorecard = score_fixtures()
    phase_refusal = refuse_inferred_phase("batch-distillation")
    phase_model = DeclaredPhaseTransitionModel.fit((0, 1, 2, 0, 1, 2))
    illegal = phase_model.unexpected_indices((0, 1, 2, 0, 2))
    known, unknown, completeness = _d2_reconstruction(repo_root)
    identity = score_identity_layers(
        self_value=3.0,
        self_mean=0.0,
        self_std=1.0,
        role_value=0.2,
        role_mean=0.0,
        role_std=1.0,
        org_value=0.1,
        org_mean=0.0,
        org_std=1.0,
        temporal_value=0.4,
        temporal_mean=0.0,
        temporal_std=1.0,
        corpus="cert-r3.1",
    )
    lines = [
        "# Clock B research scoreboard",
        "",
        "Behind PHOS Benchmark v1 (ADR 0062). Cited public rows are not retuned.",
        "Fixture results are not public rows. P1 remains a blocked human conversation.",
        "",
        "## Public ruler (cited, not overwritten)",
        "",
        f"- HAI Gaussian: **{HAI_GAUSSIAN_FP_PER_HOUR}** FP/normal hour",
        f"- HAI Mahalanobis: **{HAI_MAHALANOBIS_FP_PER_HOUR}** FP/normal hour "
        "(still quieter than Gaussian on the public row)",
        f"- Distillation ungated Mahalanobis: **{DISTILLATION_UNGATED_FP_PER_HOUR}** "
        f"FP/hour = **{distillation_day}** FP/day. 2-3/day stays refused.",
        f"- CERT 6B at 48: precision **{CERT_SIX_B_PRECISION_AT_48}** "
        f"(5/48 = {cert_budget:.3f} on the frozen TP/FP counts)",
        f"- Known-station unique lead **{KNOWN_STATION_LED}/{KNOWN_STATION_N}**; "
        f"unknown-master unique lead **{UNKNOWN_MASTER_LED}/{UNKNOWN_MASTER_N}**; unpooled.",
        "",
        "## Fixture ablation (not a public row)",
        "",
        f"- Toy Mahalanobis true positives exceed Gaussian: **{fixture_mahalanobis_wins}**.",
        "- That does not overwrite HAI 646.58. If Mahalanobis still wins on HAI, it wins.",
        "",
        "## Declared-phase transitions",
        "",
        f"- Distillation inferred phase: {phase_refusal}",
        f"- Declared-phase fixture flags illegal arrival at index {illegal}.",
        "",
        "## Sequences versus counts",
        "",
        f"- Rare ordered path more surprising than the common trained path: "
        f"**{rare_path_beats_count_baseline()}**.",
        f"- Replaces CERT 6B: **{REPLACES_CERT_SIX_B}**.",
        "",
        "## Reasoning fixtures (library, not CERT)",
        "",
        f"- n={scorecard.n} top-1={scorecard.top_1} top-2={scorecard.top_2} "
        f"abstention-when-correct={scorecard.abstention_when_correct} miss={scorecard.miss}",
        f"- is_cert_row: **{scorecard.is_cert_row}**",
        f"- Maintenance consequences authored: {len(consequences_for('engineering_maintenance'))}",
        f"- Unauthorised consequences authored: "
        f"{len(consequences_for('unauthorised_control_activity'))}",
        "",
        "## D2 reconstruction completeness (not a lead rate)",
        "",
        f"- Known-station command records: {known}",
        f"- Unknown-master command records: {unknown}",
        f"- Mean completeness: {completeness:.3f} (path/state/aftermath usually empty)",
        "- Every record has lead_rate None. 0/16 and 1/4 stay the ranking freeze.",
        "",
        "## Identity layers (not a CERT row)",
        "",
        f"- Self/role/org/time scored separately on a fixture. "
        f"Peer slot: **{identity.peer_score}**. "
        f"Pooled unusual: **{identity.pooled_unusual}**. Peer advantage stays retired.",
        "- This is not a CERT 6B replacement and not a public log name.",
        "",
        "## Hunt tickets",
        "",
        "- TEP: read-once per dump (faults, not attacks). Dumps do not confirm each other. "
        "Not acquired.",
        "- Electra ICS: host timed out; dataset licence unverified; name collisions. Not acquired.",
        "- HVAC/BACnet: campus traces have no SPDX and truncated payloads; Kaggle unread. "
        "Not acquired.",
        "- Further Modbus pcaps: unlabelled or attack-type, not command-action windows. "
        "Not acquired. None fills ADR 0040.",
        "",
        "## Still forbidden",
        "",
        "- Intelligence, API, UI, TAP in src/phos.",
        "- Threshold search on seed 11.",
        "- Pooling command issuers. Claiming >=70%, 10x, or 2-3/day on public ZIPs.",
        "",
    ]
    return "\n".join(lines)


def _d2_reconstruction(repo_root: Path) -> tuple[int, int, float]:
    """Score reconstruction completeness on D2 command-typed attacks. Not a lead rate."""
    directory = repo_root / "configs" / "attacks"
    known = 0
    unknown = 0
    scores: list[float] = []
    for name in _D2_CONFIGS:
        path = directory / name
        for record in reconstructions_from_attack_config(path):
            assert record.lead_rate is None
            scores.append(reconstruction_completeness(record))
            if record.issuer_kind is IssuerKind.KNOWN_STATION:
                known += 1
            elif record.issuer_kind is IssuerKind.UNKNOWN_MASTER:
                unknown += 1
    mean = sum(scores) / float(len(scores)) if scores else 0.0
    return known, unknown, mean
