"""The Atlas eval script can score atlas-var1 without re-logging frozen Mahalanobis.

HAI three-way (seed 11, threshold 3.0) is the measurement. These tests pin the wiring:
`--var` emits LinearDynamicsModel only. Default contenders stay the public trio.
"""

from __future__ import annotations

import pytest
from scripts.evaluate_atlas import correlation_contenders, selected_contenders, var_contenders

from phos.atlas import LinearDynamicsModel, MahalanobisModel, ShrinkageTarget


def test_pooled_contenders_do_not_include_var() -> None:
    names = [model.name for model in selected_contenders(gated=False)]
    assert names == ["gaussian", "atlas-pca", "atlas-mahalanobis"]
    assert "atlas-var1" not in names


def test_var_contenders_are_atlas_var1_only() -> None:
    models = var_contenders()
    assert len(models) == 1
    assert isinstance(models[0], LinearDynamicsModel)
    assert models[0].name == "atlas-var1"
    assert models[0].lag == 1


def test_var_flag_rejects_gated(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.evaluate_atlas import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--var", "--gated"])
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "--var" in err


def test_correlation_contenders_are_named_apart_from_public_mahalanobis() -> None:
    models = correlation_contenders()
    assert len(models) == 1
    model = models[0]
    assert isinstance(model, MahalanobisModel)
    assert model.name == "atlas-mahalanobis-correlation"
    assert model.shrinkage_target == ShrinkageTarget.CORRELATION
    pooled = [item.name for item in selected_contenders(gated=False)]
    assert "atlas-mahalanobis-correlation" not in pooled


def test_singular_covariance_is_a_refuse_not_a_retune() -> None:
    from scripts.evaluate_atlas import is_singular_covariance_refuse

    refuse = ValueError(
        "atlas-mahalanobis-correlation: the training covariance of these 52 signals is "
        "singular at shrinkage=0.05 (condition number 3.85e+25)"
    )
    assert is_singular_covariance_refuse(refuse)
    assert not is_singular_covariance_refuse(ValueError("could not fit a calibrator"))
