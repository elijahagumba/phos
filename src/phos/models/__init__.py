"""PHOS behavioural models: the shared detection machinery Atlas and Sentiel both build on.

Import everything public from here — ``from phos.models import GaussianBaseline`` — rather than
from the submodules, so internal layout can change without breaking callers.

The shape of this package, and why:

- **`fit` and `score` are different types.** `BehaviouralModel.fit` returns a `FittedModel`, and
  only a `FittedModel` can `score`. Scoring an unfitted model is not a mistake you can make.
- **The contract sits above the keying strategy.** `BehaviouralModel` is `fit` and nothing else.
  `PerKeyBehaviouralModel` adds the one-baseline-per-``(entity, feature)`` strategy the three
  baselines here share — and which `phos.atlas` deliberately does not, because a joint model of a
  plant cannot be expressed one signal at a time.
- **Models speak the ontology.** Fitting learns `ExpectedRange`s, scoring emits `Deviation`s.
  There is no private alert format anywhere in here (Constitution §3.1).
- **Baselines are per `(entity_id, feature)`**, with a feature-level aggregate as the fallback for
  a key that training never saw. A feature training never saw at all yields nothing: unknown is
  not the same as anomalous.
- **Splitting comes before fitting.** `train_test_split` carves off an attack-free training prefix
  so a model is never scored on data it learned from.
- **Any of them can be measured.** `ModelDetector` adapts a `FittedModel` to the PART 2 `Detector`
  protocol, so `phos.eval.evaluate(ModelDetector(fitted=...), test, config)` produces a real
  `EvaluationReport` (Constitution §3.5).

Three baselines ship here — Gaussian, EWMA and IQR — chosen because they fail differently:
Gaussian is sensitive but assumes a clean training window, EWMA follows drift, IQR shrugs off
contaminated training data. None of them is OT- or enterprise-specific; those features arrive with
the engines in PARTs 5-6.

The confidence `ModelDetector` reports is an **uncalibrated** squash of the anomaly score and must
not reach a user (Constitution §3.3). PART 4 fits the calibrator that replaces it.
"""

from phos.models.base import (
    FEATURE_LEVEL_ENTITY_ID,
    MAX_MAGNITUDE,
    BehaviouralModel,
    FittedModel,
    ModelKey,
    PerKeyBehaviouralModel,
    SplitPolicy,
    StaticRangeFittedModel,
    clamp_magnitude,
    model_key,
    train_test_split,
)
from phos.models.detector import ModelDetector, uncalibrated_confidence
from phos.models.ewma import EwmaBaseline, EwmaFittedModel, ewma_update
from phos.models.gaussian import GaussianBaseline, GaussianFittedModel
from phos.models.iqr import IqrBaseline, IqrFittedModel

__all__ = [
    "FEATURE_LEVEL_ENTITY_ID",
    "MAX_MAGNITUDE",
    "BehaviouralModel",
    "EwmaBaseline",
    "EwmaFittedModel",
    "FittedModel",
    "GaussianBaseline",
    "GaussianFittedModel",
    "IqrBaseline",
    "IqrFittedModel",
    "ModelDetector",
    "ModelKey",
    "PerKeyBehaviouralModel",
    "SplitPolicy",
    "StaticRangeFittedModel",
    "clamp_magnitude",
    "ewma_update",
    "model_key",
    "train_test_split",
    "uncalibrated_confidence",
]
