"""Clock B research scoreboard cites public rows and does not overwrite them."""

from __future__ import annotations

from pathlib import Path

from phos.eval.ablation import render_fixture_ladder_markdown, run_atlas_fixture_ladder
from phos.eval.adversary import render_adversary_markdown
from phos.eval.benchmark import BENCHMARK_SEED, HAI_MAHALANOBIS_FP_PER_HOUR
from phos.eval.clock_b_research import assemble_clock_b_research
from phos.reasoning.counterfactual import consequences_for
from phos.sentiel.sequences import REPLACES_CERT_SIX_B, rare_path_beats_count_baseline

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_research_scoreboard_cites_frozen_rows_and_keeps_refusals() -> None:
    text = assemble_clock_b_research(REPO_ROOT)
    assert "646.58" in text
    assert "18.72" in text
    assert "0.104" in text
    assert "0/16" in text
    assert "1/4" in text
    assert "REFUSED" in text
    assert "REPLACES_CERT_SIX_B" not in text or "False" in text
    lowered = text.lower()
    assert "not acquired" in lowered or "not dual-surface" in lowered
    assert "threshold search" in text.lower()
    assert "src/phos" in text
    assert "Peer slot" in text or "peer" in text.lower()
    assert "None" in text


def test_fixture_ladder_markdown_forbids_copying_onto_hai() -> None:
    markdown = render_fixture_ladder_markdown(run_atlas_fixture_ladder(seed=BENCHMARK_SEED))
    assert "FIXTURE_NOT_A_PUBLIC_ROW" in markdown or "not a public row" in markdown.lower()
    assert "646.58" in markdown
    assert "8389.81" in markdown
    assert str(HAI_MAHALANOBIS_FP_PER_HOUR) in markdown


def test_adversary_markdown_is_not_a_detection_claim() -> None:
    markdown = render_adversary_markdown()
    assert "specification" in markdown.lower()
    assert "false" in markdown
    assert "gradual-drift" in markdown


def test_extra_templates_have_consequences_and_sequences_do_not_replace_six_b() -> None:
    assert consequences_for("sensor_or_device_fault")
    assert consequences_for("process_disturbance")
    assert consequences_for("compromised_account")
    assert consequences_for("benign_role_change")
    assert rare_path_beats_count_baseline() is True
    assert REPLACES_CERT_SIX_B is False
