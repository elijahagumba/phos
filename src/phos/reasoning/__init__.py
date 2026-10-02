"""PHOS reasoning: where a measurement becomes something a conclusion can rest on.

Import everything public from here — ``from phos.reasoning import IsotonicCalibrator`` — rather
than from the submodules, so internal layout can change without breaking callers.

PART 4A built the floor that reasoning stands on; PART 4B built the reasoning.

**The evidence boundary** (`phos.reasoning.boundary`). PART 3's `Deviation` was ambiguous: with
``emit_k`` below ``band_k``, a model emits candidates for observations that never left their
expected range. Three terms now settle it — a *scored candidate* is any emitted `Deviation` and
exists only to feed the harness's threshold sweep; an *out-of-band deviation* is one whose value
actually fell outside its `ExpectedRange`; and `Evidence` is built **only** from the latter, by
`evidence_from_deviation`, which raises otherwise. The test is the value against the range, never
the magnitude, because a magnitude means something different in each of the three baselines. PART P3
adds `evidence_from_relationship_change` beside it, for structural facts that have no
`ExpectedRange` to be in or out of — it applies the same two refusals and reads a measured change of
zero as the non-event an in-band candidate is.

**Calibration** (`phos.reasoning.calibration`). A confidence is only allowed to reach a user if it
is a calibrated probability (Constitution §3.3). `PlattCalibrator` and `IsotonicCalibrator` learn
the score-to-probability mapping from labelled data; a fitted calibrator is a frozen model holding
plain floats, so it serialises and reproduces rather than needing to be re-fitted.

**The three-way split** (`phos.reasoning.splits`). A calibrator is itself fitted on labels, so two
slices are no longer enough: `train_calib_test_split` yields an attack-free training prefix, a
labelled calibration slice, and a labelled test slice. It refuses degenerate slices loudly, because
each one produces a number that looks like a result.

**The calibrated detector** (`phos.reasoning.detector`). `CalibratedModelDetector` is the PART 2
`Detector` with the uncalibrated squash replaced. It keeps ``score`` as the raw magnitude so
thresholds keep their meaning and the before/after comparison reads one alert set, not two.

Measured on real corpora, calibration roughly halves the expected calibration error on BATADAL and
collapses it on HAI — and Platt makes BATADAL *worse* than doing nothing, which is why
`scripts/calibrate_corpora.py` measures both rather than assuming either.

**Templates** (`phos.reasoning.templates`). Explanations are not inferred; they are written down.
A `HypothesisTemplate` declares a label, a prior, and the evidence patterns that argue for and
against it, and the `TemplateLibrary` is the registry the engine may draw from. 4B ships three
deliberately generic templates — `generic_library` — because authoring real OT and enterprise
explanations is PART 5's and PART 6's job, not this one's.

**Belief** (`phos.reasoning.belief`). `update_confidence` combines a hypothesis's current
confidence with a piece of evidence's calibrated weight in log-odds, so confidence stays in
``[0, 1]``, moves in the direction the evidence argues, is proportional to how much 4A trusts it,
and — because odds multiply but never reach infinity — never becomes certainty.
`reconstruct_confidence` replays a hypothesis's stored evidence to rebuild its confidence, which is
Constitution §3.2 made executable.

**The engine** (`phos.reasoning.engine`). `ReasoningEngine` takes evidence in and gives competing
hypotheses and `Narrative`s out. It keeps every plausible explanation, including the ones the
evidence argues against and the always-present "insufficient evidence" residual, because PHOS
reports what to investigate and why rather than returning a verdict.

**One honest limit.** Evidence *weights* are calibrated; the hypothesis confidences built from them
are not, because each template's prior and `EVIDENCE_STRENGTH` are unmeasured placeholders. Under
Constitution §3.3 that means a hypothesis confidence is not yet fit to surface to a user. PARTs 5
and 6 own measuring those two numbers for their domains; see `phos.reasoning.belief` for why the
corpora PHOS has cannot do it here.
"""

from phos.reasoning.belief import (
    CONFIDENCE_CEILING,
    EVIDENCE_STRENGTH,
    LEAD_TIE_EPSILON,
    evidence_fingerprint,
    normalise,
    prior_only_rivals,
    rank_hypotheses,
    reconstruct_confidence,
    tied_lead_ids,
    update_confidence,
)
from phos.reasoning.boundary import (
    evidence_from_deviation,
    evidence_from_relationship_change,
    is_out_of_band,
)
from phos.reasoning.calibration import (
    NORMAL_SCORE_WEIGHT_CAVEAT,
    Calibrator,
    FittedCalibrator,
    FittedIsotonicCalibrator,
    FittedNormalScoreCalibrator,
    FittedPlattCalibrator,
    IsotonicCalibrator,
    NormalScoreCalibrator,
    PlattCalibrator,
    calibrated_probabilities,
    normal_scores_from,
    scores_and_labels_from,
)
from phos.reasoning.detector import CalibratedModelDetector
from phos.reasoning.engine import ReasoningConfig, ReasoningEngine
from phos.reasoning.splits import (
    CalibrationSplitPolicy,
    DegenerateSplitError,
    attack_free_fit_calib_split,
    prefix_split,
    train_calib_test_split,
)
from phos.reasoning.templates import (
    GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
    GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    EvidencePattern,
    HypothesisTemplate,
    TemplateLibrary,
    TemplateMatch,
    generic_library,
    generic_templates,
    insufficient_evidence_template,
)

__all__ = [
    "CONFIDENCE_CEILING",
    "EVIDENCE_STRENGTH",
    "GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID",
    "GENERIC_BENIGN_CHANGE_TEMPLATE_ID",
    "INSUFFICIENT_EVIDENCE_TEMPLATE_ID",
    "LEAD_TIE_EPSILON",
    "NORMAL_SCORE_WEIGHT_CAVEAT",
    "CalibratedModelDetector",
    "CalibrationSplitPolicy",
    "Calibrator",
    "DegenerateSplitError",
    "EvidencePattern",
    "FittedCalibrator",
    "FittedIsotonicCalibrator",
    "FittedNormalScoreCalibrator",
    "FittedPlattCalibrator",
    "HypothesisTemplate",
    "IsotonicCalibrator",
    "NormalScoreCalibrator",
    "PlattCalibrator",
    "ReasoningConfig",
    "ReasoningEngine",
    "TemplateLibrary",
    "TemplateMatch",
    "attack_free_fit_calib_split",
    "calibrated_probabilities",
    "evidence_fingerprint",
    "evidence_from_deviation",
    "evidence_from_relationship_change",
    "generic_library",
    "generic_templates",
    "insufficient_evidence_template",
    "is_out_of_band",
    "normal_scores_from",
    "normalise",
    "prefix_split",
    "prior_only_rivals",
    "rank_hypotheses",
    "reconstruct_confidence",
    "scores_and_labels_from",
    "tied_lead_ids",
    "train_calib_test_split",
    "update_confidence",
]
