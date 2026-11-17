"""The referee: a locked exam, an adaptive attacker's target, and honest reporting.

PART S6. Import everything public from here — ``from phos.referee import make_exam``.

**This is a new package, not the referee module the brief suggested folding into an existing
one.** It is the only package in this programme that may import `phos.atlas`, through the public
surface a user of Atlas would use, and it may import `phos.synth`'s public surface too, to
generate the plants an exam runs on. Neither of those packages may import this one back —
`tests/referee/test_independence.py` is the check.

**What it owns, in one sentence each.**

- `phos.referee.seeds` — four pool files (dev, public, private, retired), a seed in at most one
  of them, and sealed families kept out of the open two.
- `phos.referee.exam` — a frozen, hashed list of plants to run. Its id *is* the hash, so there is
  no way to edit an exam without it becoming a different exam.
- `phos.referee.corpus` — a generated plant, read back as a labelled `phos.eval.Dataset`, and the
  label-free copy an isolated detector run is allowed to see.
- `phos.referee.detectors` — the Atlas adapter, the name for the baseline path
  `phos.models.ModelDetector` already covers, and a template for a third party's.
- `phos.referee.runner` — generate every plant an exam names, score one detector against each.
- `phos.referee.scoring` — per-plant metrics, aggregated with a mean, a spread and a bootstrap
  confidence interval, never a mean alone.
- `phos.referee.report` — the plain-language record: worst plants first, then the headline
  numbers, then what the exam cannot tell you.
- `phos.referee.integrity` — a detector cannot see labels or seeds by looking where it was given
  its input, and a private exam will not run from a dirty working tree.
- `phos.referee.query` — a counted, black-box way to ask Atlas about one plant (PART S7: the
  breaker reaches Atlas only through this).
- `phos.referee.real_data` — grading Atlas on real-world datasets, reported separately from
  simulated results (PART S9).
- `phos.referee.cli` — ``phos-referee make-exam|run|report|retire-seeds|round|replay-findings``.

**Nothing here is a detection claim.** Every number this package produces is about `phos.synth`'s
models of a plant, never about a real one (`docs/rules/data-tiers.md`).
"""

from phos.referee.detectors import AtlasDetector, ThirdPartyDetectorTemplate, baseline_detector
from phos.referee.exam import DEFAULT_EXAM_SIZE, Exam, ExamEntry, ExamError, exam_hash, make_exam
from phos.referee.integrity import (
    DirtyWorkingTreeError,
    IntegrityError,
    refuse_if_dirty_for_private_exam,
    run_detector_isolated,
)
from phos.referee.query import BudgetExceededError, QueryInterface, QueryResult
from phos.referee.real_data import (
    DatasetManifest,
    LicenceError,
    ManifestError,
    ManifestGate,
    RealDataExam,
    RealDataReport,
    run_real_data_exam,
)
from phos.referee.report import render_json, render_markdown, write_report
from phos.referee.runner import DEFAULT_EVENT_CATALOGUE, run_exam
from phos.referee.scoring import (
    DiscriminationHonesty,
    ExamScore,
    PlantScore,
    ScoringError,
    Summary,
    aggregate,
    score_plant,
    summarize,
)
from phos.referee.seeds import (
    SeedEntry,
    SeedPool,
    SeedVault,
    SeedVaultError,
    assert_no_sealed_in_open_pools,
)

__all__ = [
    "DEFAULT_EVENT_CATALOGUE",
    "DEFAULT_EXAM_SIZE",
    "AtlasDetector",
    "BudgetExceededError",
    "DatasetManifest",
    "DirtyWorkingTreeError",
    "DiscriminationHonesty",
    "Exam",
    "ExamEntry",
    "ExamError",
    "ExamScore",
    "IntegrityError",
    "LicenceError",
    "ManifestError",
    "ManifestGate",
    "PlantScore",
    "QueryInterface",
    "QueryResult",
    "RealDataExam",
    "RealDataReport",
    "ScoringError",
    "SeedEntry",
    "SeedPool",
    "SeedVault",
    "SeedVaultError",
    "Summary",
    "ThirdPartyDetectorTemplate",
    "aggregate",
    "assert_no_sealed_in_open_pools",
    "baseline_detector",
    "exam_hash",
    "make_exam",
    "refuse_if_dirty_for_private_exam",
    "render_json",
    "render_markdown",
    "run_detector_isolated",
    "run_exam",
    "run_real_data_exam",
    "score_plant",
    "summarize",
    "write_report",
]
