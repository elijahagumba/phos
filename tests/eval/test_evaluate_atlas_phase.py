"""The Atlas eval script scores a declared recipe_step with PhaseConditionalModel.

Pooled comparison models must not see that column, or the frozen ungated Mahalanobis row
would quietly change meaning.
"""

from datetime import timedelta

from scripts.evaluate_atlas import selected_contenders

from phos.atlas import PhaseConditionalModel


def test_selected_contenders_stay_pooled_until_a_phase_feature_is_declared() -> None:
    names = [model.name for model in selected_contenders(gated=False)]
    assert names == ["gaussian", "atlas-pca", "atlas-mahalanobis"]


def test_a_declared_phase_feature_adds_phase_conditional_mahalanobis_without_settling() -> None:
    models = selected_contenders(gated=False, phase_feature="recipe_step")
    phase = models[-1]
    assert isinstance(phase, PhaseConditionalModel)
    assert phase.phase_feature == "recipe_step"
    assert phase.settling_window == timedelta(0)
    assert phase.inner.name == "atlas-mahalanobis"
