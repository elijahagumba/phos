"""D3 — the breaking harness: run Atlas against D2's adversary and report where it goes blind.

D1 built plants. D2 built a graded, honestly-labelled adversary and refused to judge anything with
it. This package is the point of both: it runs the **whole** Atlas vertical — score, promote,
group, reason — over each attacked corpus and reports, per attack type and per level of subtlety,
whether Atlas saw it. What comes out is a map of blind spots rather than an accuracy number,
because the blind spots are the specific, reproducible things a later PART can fix.

**It measures. It does not improve.** Nothing here modifies D1, D2, Atlas, or any existing module,
and no result is fed back into a detector. A separate top-level package rather than a corner of
`phos.synth` or `phos.atlas` precisely so that neither of those gains a dependency on the other:
the generator must not be able to see the detector it will be graded against, and the detector must
not be able to see the generator. This package sits above both and depends on both.

**Three honesty rules are structural here, not conventions someone must remember.**

1. *The flavours never blur.* A detection attack supports "Atlas detects plant attacks down to
   this subtlety"; an input-hostile case supports "Atlas survives hostile input" and **no claim
   whatever about security**. D2 made that unrepresentable per case and per corpus; D3 keeps it so
   with two unrelated result types — `AttackOutcome` and `RobustnessOutcome` — where the
   robustness type has no `detected` field and no route into a breaking-point map, exactly as
   `HostileGroundTruth` has no `interval()`. Nothing in this package combines them.
2. *The seam is distrusted.* D2 documented one statistical residual it could not remove.
   `phos.breaking.fingerprint` decides, from the plant's own declared drift and the manipulation
   D2 built, which results carry it. Caveated results are reported in their own column and are
   never folded into the clean headline.
3. *Ground truth judges, not the sensors.* For a liar attack the readings Atlas saw were
   fabricated, so being fooled cannot be judged from them. `phos.breaking.truth` reads D1's
   independently recorded true-state file, and an attack that drove the true state outside
   anything the plant did while unattacked, while Atlas stayed silent, is scored
   `MISSED_DANGEROUS` — the worst cell on the map, and one the harness must be able to reach.

**The boundary on everything this package prints.** These are attacks *we* designed against a
model of a plant. A blind spot found here is real and worth fixing. Atlas performing well here
shows it handles our adversary against our simulation — a necessary step toward handling a real
adversary against a real plant, and not evidence of it. `BREAKING_HARNESS_CAVEATS` carries that
into every report and every line of the experiment log.
"""

from phos.breaking.breakpoint import BreakingPoint, breaking_points
from phos.breaking.commands import (
    ATTACK_TEMPLATE_ID,
    CommandIssuerKind,
    CommandPath,
    CommandReasoningResult,
    ExplanationRanking,
    classify_command_issuer,
    command_attacks,
    rank_explanations,
    read_command_path,
)
from phos.breaking.corpus import (
    AttackCorpus,
    CorpusNotFoundError,
    NormalCorpus,
    discover_attack_corpora,
    load_attack_corpus,
    load_normal_corpus,
)
from phos.breaking.fingerprint import (
    FALSIFIED_READING_TYPES,
    FINGERPRINT_CAVEAT,
    FingerprintAssessment,
    FingerprintStatus,
    assess_fingerprint,
)
from phos.breaking.harness import BreakingConfig, CorpusBreakdown, run_breaking
from phos.breaking.outcome import (
    AttackOutcome,
    DetectionVerdict,
    RobustnessOutcome,
    RobustnessVerdict,
)
from phos.breaking.report import (
    ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT,
    BREAKING_HARNESS_CAVEATS,
    BreakingReport,
    assemble,
    render,
    summary_json,
    write_report,
)
from phos.breaking.robustness import CorpusRobustness, run_robustness
from phos.breaking.truth import (
    DEFAULT_DANGER_MARGIN,
    TrueStateRecord,
    TrueStateVerdict,
    judge_true_state,
    load_true_state,
)

__all__ = [
    "ATTACK_TEMPLATE_ID",
    "ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT",
    "BREAKING_HARNESS_CAVEATS",
    "DEFAULT_DANGER_MARGIN",
    "FALSIFIED_READING_TYPES",
    "FINGERPRINT_CAVEAT",
    "AttackCorpus",
    "AttackOutcome",
    "BreakingConfig",
    "BreakingPoint",
    "BreakingReport",
    "CommandIssuerKind",
    "CommandPath",
    "CommandReasoningResult",
    "CorpusBreakdown",
    "CorpusNotFoundError",
    "CorpusRobustness",
    "DetectionVerdict",
    "ExplanationRanking",
    "FingerprintAssessment",
    "FingerprintStatus",
    "NormalCorpus",
    "RobustnessOutcome",
    "RobustnessVerdict",
    "TrueStateRecord",
    "TrueStateVerdict",
    "assemble",
    "assess_fingerprint",
    "breaking_points",
    "classify_command_issuer",
    "command_attacks",
    "discover_attack_corpora",
    "judge_true_state",
    "load_attack_corpus",
    "load_normal_corpus",
    "load_true_state",
    "rank_explanations",
    "read_command_path",
    "render",
    "run_breaking",
    "run_robustness",
    "summary_json",
    "write_report",
]
