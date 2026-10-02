"""The graded attack library: adversaries we design, label perfectly, and do not judge.

D1 built the plants and the two hooks. D2 walks through them. What it produces is attack-laden,
perfectly labelled data across a full difficulty range — and no evaluation of anything. Whether
Atlas sees any of it is D3's question, and this subpackage is careful not to answer it.

**The purpose is not to make attacks Atlas can catch.** It is to make attacks across a range that
runs from trivial to nearly invisible, including ones built to defeat Atlas's central claim
specifically, so that D3 can find where Atlas goes blind. A library that only produced easy
attacks would be a failure of this PART, not a success of the engine.

**Two flavours that may never blur.** A *detection* attack acts on the simulated plant and supports
the claim "Atlas detects plant attacks down to this level of subtlety". An *input-hostile* attack
acts on the data pipeline and supports the claim "Atlas handles hostile input safely" — which is
not, and must never be reported as, a claim that PHOS is secure against a real attacker. The
separation is structural: the flavour is derived from the type rather than assigned, the two plans
are different types, a corpus may hold one kind or the other but not both, and `HostileGroundTruth`
has no method that produces a `LabelledInterval`. See `phos.synth.attacks.spec`.

**Everything enters through D1's hook and is labelled against D1's true-state record.** An attack
acts on the plant through the same mechanisms a real attacker would — a final control element
moved, an instrument's report falsified — and its real danger is measured against what the plant
was *actually* doing, so a false-data-injection attack is labelled honestly even while the sensors
lie about it.

**Ground truth is measured, not intended.** Every corpus is two simulations of one seed: one clean,
one attacked. What each attack did is the difference between them, and an attack that turned out to
change nothing is refused rather than labelled — see `phos.synth.attacks.inject`.

**The standing caveat, carried in every corpus, manifest and report this package writes:** these
are attacks *we* designed. Atlas catching them shows that Atlas handles our imagination, not a real
adversary's. A detection rate measured here is an upper bound on this library and never a lower
bound on reality; and if Atlas ever scores suspiciously well, the first hypothesis is a leaked
fingerprint — some incidental tell in timing, formatting, ordering or numerical precision — and not
brilliance. `tests/synth/attacks/test_antifingerprint.py` is the standing defence of that claim and
the first thing to distrust. See `ATTACKS_ARE_OURS_CAVEAT`.

**What is not here, deliberately.** No evaluation of Atlas, no scoring, no breaking-point analysis
(D3). No claim about Atlas's performance or PHOS's security. No new plants (D1). No modification of
D1, of Atlas, or of any existing module.
"""

from phos.synth.attacks.battery import AttackDatasetConfig, load_batteries, load_battery
from phos.synth.attacks.generate import (
    CAPTURE_FILE,
    MANIFEST_FILE,
    TELEMETRY_FILE,
    TOPOLOGY_FILE,
    TRUTH_FILE,
    AttackGenerationError,
    AttackManifest,
    generate_attack_dataset,
    telemetry_lines,
    truth_lines,
)
from phos.synth.attacks.hostile import MALFORMED_KINDS, apply_hostile, is_finite_row
from phos.synth.attacks.inject import (
    ATTACK_LABEL_VALUE,
    NORMAL_LABEL_VALUE,
    AttackRun,
    attack_dataset,
    attack_source_note,
    inject,
    truth_rows,
)
from phos.synth.attacks.library import (
    NormalReference,
    ScheduledCommand,
    StagedAttack,
    stage_attack,
)
from phos.synth.attacks.manipulations import (
    ActuatorOffset,
    ActuatorRamp,
    ReadingBlend,
    ReadingTrack,
    pseudo_noise,
)
from phos.synth.attacks.spec import (
    ATTACK_LABEL,
    ATTACKS_ARE_OURS_CAVEAT,
    INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
    AttackFlavour,
    AttackGroundTruth,
    AttackPlan,
    AttackType,
    DifficultyLevel,
    HostileGroundTruth,
    HostilePlan,
    strength_of,
)

__all__ = [
    "ATTACKS_ARE_OURS_CAVEAT",
    "ATTACK_LABEL",
    "ATTACK_LABEL_VALUE",
    "CAPTURE_FILE",
    "INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT",
    "MALFORMED_KINDS",
    "MANIFEST_FILE",
    "NORMAL_LABEL_VALUE",
    "TELEMETRY_FILE",
    "TOPOLOGY_FILE",
    "TRUTH_FILE",
    "ActuatorOffset",
    "ActuatorRamp",
    "AttackDatasetConfig",
    "AttackFlavour",
    "AttackGenerationError",
    "AttackGroundTruth",
    "AttackManifest",
    "AttackPlan",
    "AttackRun",
    "AttackType",
    "DifficultyLevel",
    "HostileGroundTruth",
    "HostilePlan",
    "NormalReference",
    "ReadingBlend",
    "ReadingTrack",
    "ScheduledCommand",
    "StagedAttack",
    "apply_hostile",
    "attack_dataset",
    "attack_source_note",
    "generate_attack_dataset",
    "inject",
    "is_finite_row",
    "load_batteries",
    "load_battery",
    "pseudo_noise",
    "stage_attack",
    "strength_of",
    "telemetry_lines",
    "truth_lines",
    "truth_rows",
]
