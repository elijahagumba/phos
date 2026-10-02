"""Session C4: joint vs univariate is a table, not a 10x stamp."""

from __future__ import annotations

from phos.eval.joint_table import PUBLIC_JOINT_VS_UNIVARIATE


def test_the_table_covers_water_batch_and_electrical_already_in_hand() -> None:
    kinds = {row.process_type for row in PUBLIC_JOINT_VS_UNIVARIATE}
    assert "industrial-water" in kinds
    assert "batch-chemical" in kinds
    assert "electrical-distribution" in kinds
    assert "water-distribution" in kinds


def test_every_row_forbids_the_ten_x_stamp() -> None:
    assert PUBLIC_JOINT_VS_UNIVARIATE
    for row in PUBLIC_JOINT_VS_UNIVARIATE:
        assert row.ten_x is False
        assert row.ratio != 10.0


def test_distillation_is_8_6_perturbation_recall_not_ten_x() -> None:
    row = next(item for item in PUBLIC_JOINT_VS_UNIVARIATE if item.corpus == "batch-distillation")
    assert row.joint_fp_per_hour == 18.72
    assert row.gaussian_fp_per_hour == 160.55
    assert row.ratio == 8.6
    assert row.recall_kind == "perturbation"


def test_data4cyber_is_6_6_and_the_fp_hour_ruler_is_refused() -> None:
    row = next(item for item in PUBLIC_JOINT_VS_UNIVARIATE if item.corpus.startswith("data4cyber"))
    assert row.ratio == 6.6
    assert row.joint_fp_per_hour == 9451.02
    assert row.gaussian_fp_per_hour == 62727.77
    assert row.fp_hour_ruler == "refused"
    assert row.recall_kind == "process_phase"


def test_hai_three_way_is_thirteen_x_attack_recall() -> None:
    row = next(item for item in PUBLIC_JOINT_VS_UNIVARIATE if item.corpus == "hai")
    assert row.ratio == 13.0
    assert row.gaussian_fp_per_hour == 8389.81
    assert row.joint_fp_per_hour == 646.58
    assert row.recall_kind == "attack"


def test_batadal_joint_is_not_a_false_positive_win() -> None:
    row = next(item for item in PUBLIC_JOINT_VS_UNIVARIATE if item.corpus == "batadal")
    assert row.joint_fp_per_hour > row.gaussian_fp_per_hour
    assert row.ratio < 1.0
    assert row.recall_kind == "attack_recall_win_fp_loss"


def test_no_swat_in_the_measured_table() -> None:
    names = {row.corpus.lower() for row in PUBLIC_JOINT_VS_UNIVARIATE}
    assert not any("swat" in name for name in names)


def test_three_w_is_an_unscored_fault_process_type_not_a_measured_row() -> None:
    from phos.eval.joint_table import THREE_W_OFFSHORE_WELLS

    names = {row.corpus.lower() for row in PUBLIC_JOINT_VS_UNIVARIATE}
    assert not any(name.startswith("3w") or "three-w" in name for name in names)
    assert THREE_W_OFFSHORE_WELLS.process_type == "offshore-wells"
    assert THREE_W_OFFSHORE_WELLS.cyber_claim is False
