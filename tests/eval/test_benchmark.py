"""PHOS Benchmark v1: freeze-before-optimise (ADR 0062).

These tests pin the protocol, the cited public rows, and the cells that must stay REFUSED.
They do not remeasure HAI, distillation, or CERT. They do not retune Atlas templates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.eval.ablation import (
    ABLATION_PROFILE_IDS,
    SENTIEL_ABLATION_PROFILE_IDS,
    run_atlas_fixture_ladder,
)
from phos.eval.adversary import DETECTION_ADVERSARY_SCENARIOS, adversary_catalogue
from phos.eval.benchmark import (
    BENCHMARK_PROTOCOL_ID,
    BENCHMARK_SEED,
    CERT_PRECISION_POLICY_AT_48,
    CERT_SIX_B_PRECISION_AT_48,
    CERT_SIX_B_RECALL,
    DISTILLATION_REDUCTION_VS_GAUSSIAN,
    DISTILLATION_UNGATED_FP_PER_HOUR,
    HAI_GAUSSIAN_FP_PER_HOUR,
    HAI_GROUPED_FP_PER_HOUR,
    HAI_MAHALANOBIS_FP_PER_HOUR,
    HAI_MAHALANOBIS_PRECISION,
    HAI_WINDOW_RECALL,
    KNOWN_STATION_LED,
    KNOWN_STATION_N,
    PUBLIC_COMMAND_CORPUS_PRESENT,
    UNKNOWN_MASTER_LED,
    UNKNOWN_MASTER_N,
    CellStatus,
    RowFamily,
    assemble_v1_table,
    render_v1_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_TABLE = REPO_ROOT / "eval_runs" / "benchmark" / "phos-benchmark-v1.md"
COMMITTED_JSON = REPO_ROOT / "eval_runs" / "benchmark" / "phos-benchmark-v1.json"


def test_protocol_identity_is_frozen() -> None:
    assert BENCHMARK_PROTOCOL_ID == "phos-benchmark-v1"
    assert BENCHMARK_SEED == 11


def test_hai_citations_match_encyclopedia_eleven() -> None:
    assert HAI_GAUSSIAN_FP_PER_HOUR == 8389.81
    assert HAI_MAHALANOBIS_FP_PER_HOUR == 646.58
    assert HAI_GROUPED_FP_PER_HOUR == 53.26
    assert HAI_WINDOW_RECALL == 1.0
    assert HAI_MAHALANOBIS_PRECISION == 0.0047


def test_distillation_and_cert_citations_stay_frozen() -> None:
    assert DISTILLATION_UNGATED_FP_PER_HOUR == 18.72
    assert DISTILLATION_REDUCTION_VS_GAUSSIAN == 8.6
    assert CERT_SIX_B_PRECISION_AT_48 == 0.104
    assert CERT_SIX_B_RECALL == 0.5
    assert CERT_PRECISION_POLICY_AT_48 == 0.083


def test_command_lead_citations_stay_split() -> None:
    assert KNOWN_STATION_LED == 0
    assert KNOWN_STATION_N == 16
    assert UNKNOWN_MASTER_LED == 1
    assert UNKNOWN_MASTER_N == 4
    assert PUBLIC_COMMAND_CORPUS_PRESENT is False


def test_v1_table_cites_hai_mahalanobis_and_refuses_to_overwrite_it() -> None:
    table = assemble_v1_table()
    hai = table.row("atlas-process-cyber", "hai", "atlas-mahalanobis")
    assert hai.status is CellStatus.CITED
    assert hai.fp_per_normal_hour == 646.58
    assert hai.window_recall == 1.0
    assert hai.overwrites_public_log is False
    gaussian = table.row("atlas-process-cyber", "hai", "model:gaussian")
    assert hai.fp_per_normal_hour is not None
    assert gaussian.fp_per_normal_hour is not None
    assert hai.fp_per_normal_hour < gaussian.fp_per_normal_hour


def test_v1_table_refuses_public_command_lead() -> None:
    command = assemble_v1_table().row("atlas-command-public", "none", "command-lead")
    assert command.status is CellStatus.REFUSED
    assert command.fp_per_normal_hour is None
    assert "ADR 0040" in (command.refusal_reason or "")


def test_v1_table_refuses_hai_to_batadal_transfer() -> None:
    transfer = assemble_v1_table().row("transfer", "hai→batadal", "shared-schema")
    assert transfer.status is CellStatus.REFUSED
    assert transfer.family is RowFamily.TRANSFER


def test_v1_table_refuses_distillation_two_to_three_per_day() -> None:
    table = assemble_v1_table()
    budget = table.row("atlas-process-perturbation", "batch-distillation", "2-3-per-day")
    assert budget.status is CellStatus.REFUSED
    ungated = table.row("atlas-process-perturbation", "batch-distillation", "atlas-mahalanobis")
    assert ungated.status is CellStatus.CITED
    assert ungated.fp_per_normal_hour == 18.72
    assert ungated.caveat == "PERTURBATION_RECALL_IS_NOT_ATTACK_RECALL"


def test_v1_table_keeps_cert_six_b_and_refuses_peer_advantage() -> None:
    table = assemble_v1_table()
    six_b = table.row("sentiel", "cert-r3.1", "aggregate:gaussian:peer-set-6B")
    assert six_b.status is CellStatus.CITED
    assert six_b.precision_at_budget == 0.104
    peer = table.row("sentiel", "cert-r3.1", "peer-advantage")
    assert peer.status is CellStatus.REFUSED
    precision_policy = table.row("sentiel", "cert-r3.1", ":precision")
    assert precision_policy.status is CellStatus.CITED
    assert precision_policy.precision_at_budget == 0.083
    assert precision_policy.caveat == "MEASURED_LOSS_VS_6B"
    detectors = {item.detector for item in table.rows if item.family is RowFamily.SENTIEL}
    assert not any("sequence" in name for name in detectors)


def test_v1_table_does_not_pool_command_issuers() -> None:
    markdown = render_v1_markdown(assemble_v1_table())
    assert "0/16" in markdown
    assert "1/4" in markdown
    lowered = markdown.lower()
    assert "must not pool" in lowered
    assert "unearned" in lowered


def test_committed_markdown_matches_assembler() -> None:
    expected = render_v1_markdown(assemble_v1_table())
    assert COMMITTED_TABLE.is_file()
    assert COMMITTED_TABLE.read_text(encoding="utf-8") == expected


def test_committed_json_does_not_claim_public_command_or_seventy_percent() -> None:
    payload = json.loads(COMMITTED_JSON.read_text(encoding="utf-8"))
    assert payload["protocol"] == BENCHMARK_PROTOCOL_ID
    assert payload["seed"] == BENCHMARK_SEED
    assert "pooled_lead_rate" not in json.dumps(payload)
    assert payload["threshold_search"] is False
    assert PUBLIC_COMMAND_CORPUS_PRESENT is False


def test_ablation_profile_order_is_the_named_ladder() -> None:
    assert ABLATION_PROFILE_IDS == (
        "gaussian",
        "ewma",
        "mahalanobis",
        "mahalanobis+topology",
        "mahalanobis+topology+declared_phase",
        "mahalanobis+topology+declared_phase+grouping",
        "mahalanobis+topology+declared_phase+grouping+command_evidence",
        "mahalanobis+topology+declared_phase+grouping+command_evidence+reachability",
    )
    assert SENTIEL_ABLATION_PROFILE_IDS == (
        "counts",
        "self-history",
        "temporal",
        "aggregation",
        "peer-context-retired",
    )


def test_atlas_fixture_ladder_does_not_overwrite_public_log_names() -> None:
    results = run_atlas_fixture_ladder(seed=BENCHMARK_SEED)
    names = {item.profile_id for item in results}
    assert "gaussian" in names and "mahalanobis" in names
    for item in results:
        assert item.public_log_name is None
        assert item.overwrites_public_log is False


def test_fixture_mahalanobis_catches_broken_chords_gaussian_misses() -> None:
    results = {item.profile_id: item for item in run_atlas_fixture_ladder(seed=BENCHMARK_SEED)}
    assert results["gaussian"].true_positives is not None
    assert results["mahalanobis"].true_positives is not None
    assert results["mahalanobis"].true_positives > results["gaussian"].true_positives
    assert results["mahalanobis"].overwrites_public_log is False


def test_adversary_catalogue_is_spec_not_detection() -> None:
    catalogue = adversary_catalogue()
    ids = {item.scenario_id for item in catalogue}
    assert "gradual-drift" in ids
    assert "maintenance-mimicry" in ids
    assert "low-and-slow-identity" in ids
    for item in catalogue:
        assert item.is_detection_claim is False
        assert item.report_kind == "spec"
    assert len(DETECTION_ADVERSARY_SCENARIOS) >= 8


def test_assembler_refuses_to_invent_a_shared_plant_schema() -> None:
    with pytest.raises(KeyError):
        assemble_v1_table().row("transfer", "hai→batadal", "trained-joint")
