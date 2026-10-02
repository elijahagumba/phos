"""Which results D3 may report as clean, and which carry D2's documented statistical residual.

A detection is only evidence about Atlas if Atlas found *the attack*. If the injection left an
incidental statistical tell, a detector can find the tell instead and the number measures the
generator rather than the engine. D2 spent a whole discipline on removing those tells and then —
this is the part that matters here — **wrote down the one it could not remove**.

The residual, in D2's own words (`phos.synth.attacks.manipulations`, and ADR 0016): a falsified
reading carries pseudo-noise so that a suddenly-smooth signal does not announce itself, but
"pseudo-noise reproduces the instrument's noise and not its slow calibration drift, whose phase is
drawn from the plant's setup generator and cannot be reconstructed from outside. At full strength
a falsified signal is therefore drift-free."

So the rule this module applies is **mechanical, not a list of type names**:

    An attack is fingerprint-caveated exactly when it falsifies the reading of a signal that
    carries calibration drift.

Both halves are read off D2's own declarations rather than assumed here. Whether a type falsifies
a reading is a property of the manipulation `phos.synth.attacks.library` builds for it; whether a
signal drifts is `SignalSpec.drift_amplitude`, declared by D1's plant. That is why the classifier
takes a `PlantDescription` — the same attack type is caveated on one target and clean on another,
and only the plant knows which.

**What this yields on the shipped battery, and why it is not what the PART assumed.** The PART
naming this work expected `STEALTH_DRIFT` to be the fingerprinted case. It is not, and the
difference is worth stating plainly because it changes which numbers a reader should distrust:

* `BLATANT` and `STEALTH_DRIFT` move an **actuator**. The plant then produces the reading through
  its ordinary `_sense` path, drift and all, so there is no falsified reading and no residual.
  A stealth drift is *hard to see*, which is a different property from *leaving a tell*.
* `MIMIC`, `ROGUE_COMMAND` and `MIMIC_COMMAND` hold a **setpoint**. A setpoint declares
  ``noise_stddev = 0`` and ``drift_amplitude = 0``, so a held setpoint is exactly constant —
  which, as D2 notes, is exactly what a real setpoint does. No residual.
* `CORRELATION_BREAK` and `LIAR` falsify a **sensor** reading, and every sensor in the three
  shipped plants declares a non-zero drift. These are the caveated ones.

**The residual is strongest where the attack is most obvious.** `artefact_strength` is
``1 - subtlety``: the blend keeps that share of the falsified value and the rest of the genuine
signal, drift included. At the blatant end the signal is fully synthetic and fully drift-free; at
the near-invisible end it is almost entirely the real reading and the tell all but vanishes. This
matters for reading the map: a *caught* result at low subtlety is the one most likely to be the
artefact, while the breaking point itself — which lives at high subtlety — is the least
contaminated part of the sweep. It is not a reason to trust the boundary, only a reason not to
treat the whole row as worthless.

Nothing here judges Atlas. It decides which column of the report a result is allowed to appear in.
"""

from enum import Enum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.synth import PlantDescription
from phos.synth.attacks import AttackGroundTruth, AttackType, strength_of

__all__ = [
    "FALSIFIED_READING_TYPES",
    "FINGERPRINT_CAVEAT",
    "FingerprintAssessment",
    "FingerprintStatus",
    "assess_fingerprint",
]


class FingerprintStatus(str, Enum):
    """Whether a result may be reported as clean evidence of detection.

    Attributes:
        CLEAN: D2's anti-fingerprint discipline covers this attack's mechanism. The manipulation
            falsifies no reading, or falsifies one that carries no drift to be missing, so a
            detection is evidence about Atlas.
        CAVEATED: The manipulation falsifies a drifting instrument's reading, so the injected
            signal is short of the slow wander a real one has. A detection here **may** be Atlas
            seeing the injection artefact rather than the danger, and is not clean evidence of
            genuine detection.
    """

    CLEAN = "CLEAN"
    CAVEATED = "CAVEATED"


FINGERPRINT_CAVEAT: Final = (
    "This attack falsifies the reading of an instrument that carries calibration drift. D2's "
    "pseudo-noise reproduces the instrument's measurement noise but NOT its slow drift, whose "
    "phase is drawn from the plant's setup generator and cannot be reconstructed from outside, so "
    "the injected signal is drift-free where a genuine one wanders. A detection here may be Atlas "
    "seeing that artefact rather than the danger, and must not be read as clean evidence of "
    "genuine detection. The artefact is strongest at low subtlety, where the reading is fully "
    "synthetic, and fades toward the near-invisible end, where most of the genuine signal — drift "
    "included — is still present."
)
"""Travels with every caveated row of the breaking-point map, and into the experiment log."""

FALSIFIED_READING_TYPES: Final = frozenset(
    {
        AttackType.CORRELATION_BREAK,
        AttackType.LIAR,
        AttackType.MIMIC,
        AttackType.ROGUE_COMMAND,
        AttackType.MIMIC_COMMAND,
    }
)
"""The types whose manipulation overrides what a signal *reports*, rather than what it *is*.

Read off `phos.synth.attacks.library`: `CORRELATION_BREAK` builds a `ReadingBlend`, `LIAR` a
`ReadingTrack`, and the three setpoint-holding kinds a `ReadingBlend` on the setpoint. `BLATANT`
and `STEALTH_DRIFT` build actuator manipulations and are therefore absent — the plant senses their
consequence honestly. Membership here is necessary for a residual and not sufficient: the signal
must also drift.
"""


class FingerprintAssessment(BaseModel):
    """Why one attack's result may or may not be reported as clean.

    Attributes:
        attack_id: The attack this judges.
        status: Which column of the report the result belongs in.
        falsifies_reading: Whether the manipulation overrode what a signal reported.
        drifting_targets: The falsified signals that carry calibration drift, with their declared
            drift amplitudes. Empty for a clean assessment, and the reason for a caveated one.
        artefact_strength: Share of the reported signal that was synthetic, ``1 - subtlety``. The
            residual scales with this, so it says *how much* to distrust rather than only whether.
        reason: The judgement in a sentence a reviewer can check against the plant's declaration.

    Invariants:
        ``status`` is `CAVEATED` exactly when ``drifting_targets`` is non-empty, so the flag and
        its evidence cannot disagree.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    status: FingerprintStatus
    falsifies_reading: bool
    drifting_targets: dict[str, float] = Field(default_factory=dict)
    artefact_strength: float = Field(ge=0.0, le=1.0)
    reason: str = ""

    @model_validator(mode="after")
    def _check_agreement(self) -> Self:
        caveated = self.status is FingerprintStatus.CAVEATED
        if caveated != bool(self.drifting_targets):
            raise ValueError(
                f"assessment for {self.attack_id!r} is incoherent: status is {self.status.value} "
                f"but it names {len(self.drifting_targets)} drifting target(s). A caveat must "
                "name the drift that justifies it, and a clean result must name none"
            )
        return self

    @property
    def is_clean(self) -> bool:
        """Whether this result may appear in the headline map."""
        return self.status is FingerprintStatus.CLEAN


def assess_fingerprint(
    truth: AttackGroundTruth, description: PlantDescription
) -> FingerprintAssessment:
    """Decide whether one attack's result is clean evidence or carries D2's documented residual.

    Args:
        truth: Measured ground truth for the attack, from D2's manifest. Supplies the type, the
            signals the manipulation acted on, and where on the dial it ran.
        description: The plant's own declaration, supplying each signal's ``drift_amplitude``.
            Passed rather than assumed because the same attack type is caveated on a drifting
            sensor and clean on a driftless setpoint.

    Returns:
        The assessment, naming the drift that justifies a caveat.

    Raises:
        KeyError: Propagated from `PlantDescription.signal` if the attack names a target the plant
            does not declare. That is a corrupt manifest rather than a clean result, and guessing
            would put a `CLEAN` stamp on an attack nobody could classify.
    """
    falsifies = truth.type in FALSIFIED_READING_TYPES
    drifting: dict[str, float] = {}
    if falsifies:
        for key in truth.target_signals:
            amplitude = description.signal(key).drift_amplitude
            if amplitude > 0.0:
                drifting[key] = amplitude

    if drifting:
        named = ", ".join(f"{key} (drift {value:g})" for key, value in sorted(drifting.items()))
        return FingerprintAssessment(
            attack_id=truth.attack_id,
            status=FingerprintStatus.CAVEATED,
            falsifies_reading=True,
            drifting_targets=drifting,
            artefact_strength=strength_of(truth.subtlety),
            reason=(
                f"{truth.type.value} falsifies the reading of {named}, and D2's pseudo-noise "
                "carries no calibration drift"
            ),
        )

    if falsifies:
        return FingerprintAssessment(
            attack_id=truth.attack_id,
            status=FingerprintStatus.CLEAN,
            falsifies_reading=True,
            artefact_strength=strength_of(truth.subtlety),
            reason=(
                f"{truth.type.value} falsifies a reading, but no target declares calibration "
                "drift, so there is no drift for the injected signal to be missing"
            ),
        )

    return FingerprintAssessment(
        attack_id=truth.attack_id,
        status=FingerprintStatus.CLEAN,
        falsifies_reading=False,
        artefact_strength=strength_of(truth.subtlety),
        reason=(
            f"{truth.type.value} acts on the plant rather than on what a signal reports, so the "
            "reading is produced by the plant's own sensing path, drift included"
        ),
    )
