#!/usr/bin/env python3
"""Sentiel's real number, on a real CERT release, for either feature set.

This script builds no detection logic. It wires together what already exists — `phos.sentiel`'s
intake and featurisation, PART 3's `GaussianBaseline` and `ModelDetector`, PART 2's metric math via
the entity-aware evaluation — and writes the result to the shared experiment log.

**One script, two feature sets, so the comparison is like-for-like.** ``--feature-set starter``
reproduces the PART 6·D baseline exactly; ``--feature-set enriched`` (the default) measures PART
6A's baseline-relative, temporal and first-order relationship features through the same code path,
the same split, the same model and the same metrics. A difference in the numbers is therefore a
difference in the features and nothing else — which is the only way "did enrichment help?" can be
answered honestly.

**Honest outcomes include "no better".** The enriched features are still per-entity: a user is
judged against their own history and never against their team's. CERT's scenarios include an
insider whose activity is unremarkable for them and remarkable for their role, and nothing here can
see that. If the enrichment does not move precision, that is a real finding about what per-entity
modelling can reach, and it is the measured case for PART 6B.

**Why it reads the corpus twice.** An ontology `Observation` costs about 1.5 kB of process memory,
and the enriched set emits 26 of them per user-day across 340,171 user-days — about 13 GB if the
whole corpus were held at once, which no ordinary machine will do. So the training prefix is read,
fitted and dropped before the test half is read. Pass one stops at the first labelled attack rather
than running to the end, so the cost is roughly 1.3 reads, not 2. See ADR 0021.

**PART 6B adds a third feature set and a second scoring shape.** ``--feature-set peer`` emits the
26 enriched features plus a peer-relative companion for each of the 8 starter counts, judged against
the entity's declared peer group leave-one-out. ``--scoring aggregated`` replaces one alert per
feature per window with **one score per entity-window**, which is what makes a wide feature set
thresholdable to a budget a SOC could work — PART 6A's enriched set could not go below 1,668 alerts,
none of them true positives, at any threshold. ``per-feature`` remains the default so both earlier
baselines stay reproducible from this same code.

An aggregated peer run scores **two subsets of one stream against one fitted model**: all 34
features, and the 26 per-entity features alone. Without that control a change from PART 6A could be
the peer features or could be the scoring shape, and there would be no way to tell which.

Usage::

    python scripts/fetch_datasets.py cert-insider-threat --yes   # ~4.25 GB, once
    python scripts/evaluate_sentiel_baseline.py                  # enriched, the PART 6A number
    python scripts/evaluate_sentiel_baseline.py --feature-set starter   # the PART 6·D baseline
    python scripts/evaluate_sentiel_baseline.py --feature-set peer --scoring aggregated \
        --alert-budgets 48 200 723 1668                          # the PART 6B number

If ``phos`` is not importable, the repository's ``src`` is not on the path: prefix the command with
``PYTHONPATH=src``. ``pytest`` adds it from ``pyproject.toml`` and a bare interpreter does not.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import resource
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from phos.eval import (
    Dataset,
    Detection,
    EvalConfig,
    EvaluationReport,
    append_to_experiment_log,
    current_git_commit,
)
from phos.models import GaussianBaseline, ModelDetector
from phos.models.base import StaticRangeFittedModel
from phos.ontology import Domain, Observation
from phos.sentiel import (
    DEFAULT_GROUP_ATTRIBUTE,
    ENRICHED_CAVEATS,
    ENRICHED_FEATURES,
    PEER_CAVEATS,
    SENTIEL_CAVEATS,
    AggregationPolicy,
    CertReader,
    CertRelease,
    EntityLabelledInterval,
    FeatureSet,
    Featuriser,
    PeerGroups,
    PeerPolicy,
    PrecomputedDetector,
    ScoringSummary,
    WindowScorer,
    base_rate,
    enriched_source_note,
    evaluate_entity_aware,
    peer_source_note,
    precision_policy,
    read_insiders,
    sentiel_source_note,
    static_range_model,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
MANIFEST_NAME: Final = "sentiel-manifest.json"
_LOG_EVERY: Final = 500_000
_BYTES_PER_GB: Final = 1024.0**3

logger = logging.getLogger("phos.sentiel.baseline")


class BaselineError(RuntimeError):
    """Raised when the corpus or its manifest is not in a state this script can measure."""


class ReferenceRun(BaseModel):
    """A previously logged run, kept so a new number is never reported on its own.

    Attributes:
        part: Which build PART produced it.
        commit: The commit the numbers came from.
        dataset_name: The corpus and split it was measured on.
        n_features: How many features the featurisation emitted.
        precision: Fraction of its alerts that named the right user in the right window.
        malicious_windows: Malicious user-windows in its test half.
        total_windows: User-windows in its test half. With `malicious_windows` this gives the
            precision a detector would score by alerting on everything — the floor any real number
            has to be read against, and the one figure that makes a 0.4% precision interpretable.
        n_alerts: The alert budget the precision was measured at. Without it two runs cannot be
            compared at all: a fixed per-feature threshold gives a wider feature set proportionally
            more alerts, so the budget is the thing that has to be matched.
        alert_floor: The smallest alert count that run could reach at any threshold. This is the
            figure PART 6A's finding turns on — an enriched run cannot be quieter than 1,668
            alerts — and it is why a comparison at a SOC-sized budget has to state which runs could
            not reach it at all rather than quietly leaving them out.
        floor_true_positives: How many of those floor alerts named the right user in the right
            window. Zero, for both PART 6·D and PART 6A.
    """

    model_config = ConfigDict(frozen=True)

    part: str
    commit: str
    dataset_name: str
    n_features: int = Field(ge=1)
    precision: float = Field(ge=0.0, le=1.0)
    malicious_windows: int = Field(ge=1)
    total_windows: int = Field(ge=1)
    n_alerts: int = Field(default=0, ge=0)
    alert_floor: int = Field(default=0, ge=0)
    floor_true_positives: int = Field(default=0, ge=0)

    @property
    def trivial_precision(self) -> float:
        """Return the precision of a detector that alerts on every user-window."""
        return self.malicious_windows / self.total_windows

    @property
    def multiple_over_trivial(self) -> float:
        """Return how many times better than alerting on everything this run was."""
        return self.precision / self.trivial_precision


BASELINE_6D: Final = ReferenceRun(
    part="6·D",
    commit="ba41b99",
    dataset_name="cert-r3.1-user-day-test",
    n_features=8,
    precision=0.0040609137055837565,
    malicious_windows=53,
    total_windows=210_814,
)
"""The PART 6·D baseline this PART must be read against.

Transcribed from the logged report at commit ``ba41b99`` (``eval_runs/log.jsonl``): 9,850 alerts of
which 9,810 were false, over 1,686,512 test observations of 8 features — 210,814 user-windows, 53
of them malicious. Window recall was 1.0 and is **not quoted**: the detector alerted on 966 of
about 1,000 users, so catching 2 of 2 insiders was close to automatic. Precision, and its multiple
over the alert-on-everything floor, are what carry the information.
"""

BASELINE_6D_BEST: Final = ReferenceRun(
    part="6·D best (starter, threshold 6.0)",
    commit="9ce7298",
    dataset_name="cert-r3.1-user-day-test",
    n_features=8,
    precision=0.027663,
    malicious_windows=53,
    total_windows=210_814,
    n_alerts=723,
    alert_floor=48,
)
"""The best figure Sentiel had produced before PART 6B, and the bar a usable budget must clear.

The eight-count starter set at threshold 6.0: 723 alerts — about 1.4 a day across a thousand people
— at 110x the alert-on-everything floor. It is the **only** thing that had ever reached a
SOC-sized budget, which is why the PART 6B question is not "is the wide set better?" but "can the
wide set reach this budget at all, and does it beat this when it does?". Window recall there was
0.5: one of the two insiders, which is not independently quotable.
"""

BASELINE_6A: Final = ReferenceRun(
    part="6A (enriched, threshold 4.5)",
    commit="9ce7298",
    dataset_name="cert-r3.1-user-day-enriched-test",
    n_features=26,
    precision=0.006373,
    malicious_windows=53,
    total_windows=210_814,
    n_alerts=10_984,
    alert_floor=1_668,
)
"""PART 6A's best matched-budget number, and the floor that is the whole point of the comparison.

At ~10,000 alerts the 26-feature enriched set scored 25.35x the floor against the starter set's
16.15x, so the features carry signal. But its **alert floor is 1,668, all of them false** —
detections clamped to `MAX_MAGNITUDE`, which no threshold below 1e6 can exclude — so it could not
be operated at a SOC-sized budget at all. That absence is not a gap in the record; it is the result
PART 6B exists to change, and every three-way comparison states it rather than omitting the row.
"""

_VERDICT_BAND: Final = 0.05
"""Relative change in the multiple-over-trivial below which a run is called "no change".

A **reporting convention, not a significance test**. With two labelled insiders no significance
test is available, and pretending otherwise would be the dishonesty this whole comparison exists to
avoid. Five per cent is simply narrow enough that a real improvement clears it and wide enough that
run-to-run noise in a deterministic pipeline — of which there is none — could not.
"""


def load_manifest(data_dir: Path) -> dict[str, object]:
    """Read the committed CERT manifest written by ``scripts/fetch_datasets.py``.

    Raises:
        BaselineError: If it is absent, with the command that creates it.
    """
    path = data_dir / "cert-insider-threat" / MANIFEST_NAME
    if not path.is_file():
        raise BaselineError(
            f"{path} not found. Fetch the corpus first:\n"
            "    python scripts/fetch_datasets.py cert-insider-threat --yes\n"
            "(~4.25 GB compressed, ~13 GB unpacked; it is git-ignored and never committed.)"
        )
    manifest: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


# ------------------------------------------------------------------------------------------------
# The two-pass split
# ------------------------------------------------------------------------------------------------


def training_prefix(
    observations: Iterator[Observation], first_attack: datetime
) -> list[Observation]:
    """Return the attack-free prefix, consuming only as much of the stream as it needs.

    This is PART 3's `train_test_split` rule — the longest time-ordered prefix ending strictly
    before the earliest labelled attack — expressed over a stream instead of a list, so the test
    half never has to be in memory at the same time. ``takewhile`` abandons the iterator at the
    first observation on or after the attack, so the reader stops there rather than reading the
    remaining months for nothing.

    Args:
        observations: A time-ordered observation stream.
        first_attack: Start of the earliest labelled malicious window.

    Returns:
        Every observation stamped strictly before ``first_attack``, in order.

    Note:
        The fraction ceiling is **not** applied here, because the corpus end is not known until the
        stream has been read to the end. `check_the_attack_bound_the_split` closes that gap after
        the second pass, and raises if the ceiling would have cut the prefix shorter.
    """
    prefix = list(itertools.takewhile(lambda item: item.timestamp < first_attack, observations))
    logger.info("pass 1: %d training observations before %s", len(prefix), first_attack)
    return prefix


def evaluation_remainder(
    observations: Iterator[Observation], first_attack: datetime
) -> list[Observation]:
    """Return everything from the earliest labelled attack onward, dropping the training prefix.

    Args:
        observations: A fresh, time-ordered observation stream over the same corpus.
        first_attack: Start of the earliest labelled malicious window.

    Returns:
        Every observation stamped at or after ``first_attack``, in order.
    """
    remainder: list[Observation] = []
    seen = 0
    for observation in observations:
        seen += 1
        if observation.timestamp >= first_attack:
            remainder.append(observation)
        if seen % _LOG_EVERY == 0:
            logger.info("pass 2: %d observations read, %d kept", seen, len(remainder))
    logger.info("pass 2: %d observations read, %d kept for the test half", seen, len(remainder))
    return remainder


def check_the_attack_bound_the_split(
    corpus_start: datetime, corpus_end: datetime, first_attack: datetime, train_fraction: float
) -> None:
    """Verify the streamed split is the one `train_test_split` would have made.

    `train_test_split` cuts at whichever comes first: the ``train_fraction`` ceiling, or the
    earliest attack. The streamed split above can only apply the second, so this asserts the first
    was not the binding one. Without it a corpus whose attacks start late would train on data the
    list-based split would have withheld, and nothing would say so.

    Raises:
        BaselineError: If the fraction ceiling falls before the first attack.
    """
    cutoff = corpus_start + (corpus_end - corpus_start) * train_fraction
    if cutoff < first_attack:
        raise BaselineError(
            f"--train-fraction {train_fraction} puts the split ceiling at {cutoff}, before the "
            f"first labelled attack at {first_attack}. The streamed split cuts at the attack, so "
            "it would train on observations the fraction excludes. Raise --train-fraction to at "
            "least "
            f"{(first_attack - corpus_start) / (corpus_end - corpus_start):.4f}."
        )
    logger.info(
        "split check: the first attack at %s binds the split; the %.2f fraction ceiling at %s is "
        "later, so this is exactly train_test_split's prefix",
        first_attack,
        train_fraction,
        cutoff,
    )


# ------------------------------------------------------------------------------------------------
# The comparison
# ------------------------------------------------------------------------------------------------


def side_by_side(
    report: EvaluationReport, counts: Mapping[str, int], n_features: int, reference: ReferenceRun
) -> str:
    """Return the one-line comparison stamped onto every logged run.

    A number on its own invites the reader to supply their own baseline, so this refuses to let
    one travel alone: it carries the reference run, this run, both multiples over the
    alert-on-everything floor, and a verdict.

    Args:
        report: The finished evaluation.
        counts: `phos.sentiel.base_rate`'s malicious and benign user-window counts for the test
            half, which give this run's own trivial floor.
        n_features: How many features this run's featurisation emitted.
        reference: The run to compare against.

    Returns:
        A single string, appended to the report's ``source_note``.
    """
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]
    trivial = counts["malicious_user_windows"] / total if total else 0.0
    multiple = report.precision / trivial if trivial > 0.0 else 0.0
    ratio = multiple / reference.multiple_over_trivial if reference.multiple_over_trivial else 0.0
    if ratio > 1.0 + _VERDICT_BAND:
        verdict = "BETTER"
    elif ratio < 1.0 - _VERDICT_BAND:
        verdict = "WORSE"
    else:
        verdict = "NO CHANGE"
    return (
        f"SIDE-BY-SIDE vs PART {reference.part} (commit {reference.commit}, "
        f"{reference.dataset_name}, {reference.n_features} features): precision "
        f"{reference.precision:.6f} = {reference.multiple_over_trivial:.2f}x the "
        f"alert-on-everything floor. THIS RUN ({n_features} features): precision "
        f"{report.precision:.6f} = {multiple:.2f}x that floor "
        f"({counts['malicious_user_windows']} malicious of {total} test user-windows). "
        f"VERDICT: {verdict} ({ratio:.2f}x the reference multiple). Window recall "
        f"{report.window_recall:.1f} is not quotable at 2 insiders."
    )


def multiple_over_trivial(report: EvaluationReport, counts: Mapping[str, int]) -> float:
    """Return how many times better than alerting on every user-window this run was."""
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]
    trivial = counts["malicious_user_windows"] / total if total else 0.0
    return report.precision / trivial if trivial > 0.0 else 0.0


def three_way(
    report: EvaluationReport, counts: Mapping[str, int], n_features: int, label: str
) -> str:
    """Return the three-way comparison PART 6B §4.4 requires, stamped onto every logged run.

    Three numbers at one alert budget, and the honest statement that one of the three could not
    reach it. Omitting PART 6A's row because it has no number at a SOC-sized budget would hide the
    finding; stating the row and saying *why* it is empty is the comparison's whole point.

    Args:
        report: The finished evaluation of this run at one threshold.
        counts: `phos.sentiel.base_rate`'s malicious and benign user-window counts for the test
            half, giving this run's own alert-on-everything floor.
        n_features: How many features this run's featurisation emitted.
        label: Which feature subset this report scored — the peer set or the enriched control.

    Returns:
        A single string, appended to the report's ``source_note``.
    """
    multiple = multiple_over_trivial(report, counts)
    ratio = multiple / BASELINE_6D_BEST.multiple_over_trivial
    if ratio > 1.0 + _VERDICT_BAND:
        verdict = "BETTER"
    elif ratio < 1.0 - _VERDICT_BAND:
        verdict = "WORSE"
    else:
        verdict = "NO CHANGE"
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]
    return (
        f"THREE-WAY AT A MATCHED ALERT BUDGET OF {report.n_alerts:,} ALERTS. "
        f"(1) PART {BASELINE_6D.part} starter, {BASELINE_6D.n_features} features, one alert per "
        f"feature per window (commit {BASELINE_6D.commit}): "
        f"{BASELINE_6D_BEST.multiple_over_trivial:.2f}x the alert-on-everything floor at "
        f"{BASELINE_6D_BEST.n_alerts:,} alerts, its quietest reachable point being "
        f"{BASELINE_6D_BEST.alert_floor} alerts. "
        f"(2) PART {BASELINE_6A.part}, {BASELINE_6A.n_features} features, one alert per feature "
        f"per window (commit {BASELINE_6A.commit}): {BASELINE_6A.multiple_over_trivial:.2f}x at "
        f"{BASELINE_6A.n_alerts:,} alerts, and it COULD NOT REACH THIS BUDGET AT ALL — its alert "
        f"floor was {BASELINE_6A.alert_floor:,} clamped alerts containing "
        f"{BASELINE_6A.floor_true_positives} true positives, which no threshold below 1e6 could "
        "remove. That absence is the comparison, not a gap in it. "
        f"(3) THIS RUN, PART 6B, {label} of {n_features} emitted, ONE ALERT PER ENTITY-WINDOW: "
        f"precision {report.precision:.6f} = {multiple:.2f}x that floor "
        f"({counts['malicious_user_windows']} malicious of {total:,} test user-windows). "
        f"VERDICT vs the only previously-reachable budget: {verdict} "
        f"({ratio:.2f}x PART 6·D's best multiple). Window recall {report.window_recall:.1f} is not "
        "quotable at 2 insiders."
    )


# ------------------------------------------------------------------------------------------------
# The run
# ------------------------------------------------------------------------------------------------


def build_featuriser(
    catalogue_domain: str, feature_set: FeatureSet, peer_groups: PeerGroups | None = None
) -> Featuriser:
    """Return the featuriser for a run, with "external" defined by the corpus's own directory."""
    return Featuriser(
        org_domains=frozenset({catalogue_domain}),
        feature_set=feature_set,
        peer_groups=peer_groups,
    )


def run(
    stream_factory: Callable[[], Iterator[Observation]],
    labels: Sequence[EntityLabelledInterval],
    featuriser: Featuriser,
    dataset_name: str,
    provenance: str,
    train_fraction: float,
    min_samples: int,
    config: EvalConfig,
    extra_thresholds: Sequence[float] = (),
) -> tuple[list[EvaluationReport], list[EntityLabelledInterval]]:
    """Fit on the attack-free prefix, score the remainder, and return the finished report(s).

    Args:
        stream_factory: Produces a fresh, time-ordered observation stream over the corpus. Called
            twice — see this module's docstring for why.
        labels: Entity-scoped ground truth for the whole corpus.
        featuriser: The featuriser the streams came from, read for its feature list.
        dataset_name: Name the corpus is logged under.
        provenance: Where the corpus came from, opening the report's ``source_note``.
        train_fraction: Ceiling on the training prefix, checked against the attack-bound split.
        min_samples: Fewest training points a baseline needs.
        config: PART 2's evaluation config, unchanged. Its ``alert_threshold`` is the headline.
        extra_thresholds: Further alert thresholds to evaluate the **same** fitted model and the
            **same** test corpus at, each producing its own report. This exists for one reason: a
            fixed per-feature threshold gives a wider feature set proportionally more alerts, so
            comparing two feature sets at one threshold confounds "are these features better?"
            with "are there more of them?". Comparing at a matched alert budget separates the two,
            and an analyst's budget is the constraint that is actually fixed in practice. Each
            re-evaluation rescores the test half, which is cheap beside reading the corpus.

    Returns:
        ``(reports, labels falling in the test half)``, the headline report first.

    Raises:
        BaselineError: If the corpus is empty, has no attack-free prefix, or leaves no labelled
            insider in the test half.
    """
    first_attack = min(label.start for label in labels)

    train = training_prefix(stream_factory(), first_attack)
    if not train:
        raise BaselineError(
            f"the training half is empty: the earliest labelled attack is at {first_attack}, at or "
            "before the corpus's first observation, so there is no attack-free history to learn "
            "normal from"
        )
    corpus_start = train[0].timestamp

    model = GaussianBaseline(min_samples=min_samples)
    fitted = model.fit(train)
    logger.info(
        "fitted %s on %d training observations to %s; dropping them before the second pass",
        model.name,
        len(train),
        train[-1].timestamp.date(),
    )
    train.clear()

    remainder = evaluation_remainder(stream_factory(), first_attack)
    if not remainder:
        raise BaselineError("the test half is empty; lower --train-fraction or check the labels")
    check_the_attack_bound_the_split(
        corpus_start, remainder[-1].timestamp, first_attack, train_fraction
    )

    in_test = [
        label
        for label in labels
        if label.start <= remainder[-1].timestamp and label.end >= remainder[0].timestamp
    ]
    if not in_test:
        raise BaselineError(
            "no labelled insider falls in the test half, so recall would be vacuous; lower "
            "--train-fraction"
        )

    test = Dataset(
        name=f"{dataset_name}-test",
        domain=Domain.SENTIEL,
        observations=remainder,
        attack_intervals=[],  # Sentiel truth is entity-scoped; it travels in `labels`.
        source_note="",
    )
    counts = base_rate(test, in_test)
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]
    logger.info(
        "test half: %d observations over %d user-windows, %d of them malicious (%.4f%%); "
        "%d of %d insider(s) fall inside it",
        len(remainder),
        total,
        counts["malicious_user_windows"],
        100.0 * counts["malicious_user_windows"] / max(total, 1),
        len(in_test),
        len(labels),
    )

    write_note = (
        enriched_source_note
        if featuriser.feature_set is FeatureSet.ENRICHED
        else sentiel_source_note
    )
    note = write_note(
        f"{provenance} | {len(remainder)} test observations x "
        f"{len(featuriser.feature_names)} features ({featuriser.feature_set.value}), one-day "
        f"windows | {len(in_test)} labelled insider(s) in the test half: "
        + ", ".join(f"{label.user_id}/scenario-{label.scenario}" for label in in_test)
        + f" | test half of a train_fraction={train_fraction} attack-free-prefix split",
        f"base rate {counts['malicious_user_windows']} malicious of {total} user-windows",
    )
    test = test.model_copy(update={"source_note": note})

    detector = ModelDetector(fitted=fitted)
    commit = current_git_commit(REPO_ROOT)
    reports: list[EvaluationReport] = []
    for threshold in (config.alert_threshold, *extra_thresholds):
        at = config.model_copy(update={"alert_threshold": threshold})
        report = evaluate_entity_aware(detector, test, in_test, at)
        comparison = side_by_side(report, counts, len(featuriser.feature_names), BASELINE_6D)
        reports.append(
            report.model_copy(
                update={
                    "git_commit": commit,
                    "source_note": f"{report.source_note} | {comparison}",
                }
            )
        )
    return reports, in_test


def fit_on_prefix(
    stream_factory: Callable[[], Iterator[Observation]],
    first_attack: datetime,
    min_samples: int,
) -> tuple[StaticRangeFittedModel, datetime, int]:
    """Read the attack-free prefix, fit, and drop it before the second pass begins.

    Args:
        stream_factory: Produces a fresh, time-ordered observation stream over the corpus.
        first_attack: Start of the earliest labelled malicious window.
        min_samples: Fewest training points a baseline needs.

    Returns:
        ``(fitted model, corpus start, training observations)``.

    Raises:
        BaselineError: If there is no attack-free history to learn normal from.
    """
    train = training_prefix(stream_factory(), first_attack)
    if not train:
        raise BaselineError(
            f"the training half is empty: the earliest labelled attack is at {first_attack}, at or "
            "before the corpus's first observation, so there is no attack-free history to learn "
            "normal from"
        )
    corpus_start = train[0].timestamp
    n_train = len(train)
    fitted = static_range_model(GaussianBaseline(min_samples=min_samples).fit(train))
    logger.info(
        "fitted gaussian on %d training observations to %s; dropping them before the second pass",
        n_train,
        train[-1].timestamp.date(),
    )
    train.clear()
    assert isinstance(fitted, StaticRangeFittedModel)
    return fitted, corpus_start, n_train


def score_streaming(
    stream_factory: Callable[[], Iterator[Observation]],
    first_attack: datetime,
    fitted: StaticRangeFittedModel,
    policy: AggregationPolicy,
    subsets: Mapping[str, frozenset[str] | None],
) -> tuple[dict[str, list[Detection]], dict[str, ScoringSummary], list[Observation]]:
    """Second pass: aggregate the test half into one score per user-window **as it streams**.

    This is the pass PART 6A could not afford. At 34 features the test half is about 7.2 million
    `Observation` objects — roughly 11 GB of process memory, which this machine does not have — so
    the corpus is never held. Each observation is scored and dropped, and what survives is one
    representative observation per user-window plus one `Detection` per user-window per subset.

    The consequence is stated rather than buried: the `Dataset` handed to the evaluation carries
    **one row per user-window rather than one per feature**, so `EvaluationReport.n_observations`
    counts user-windows for an aggregated run. Nothing else in the evaluation changes — the
    normal-hours denominator comes from each user's first and last window, the base rate already
    de-duplicates to user-windows, and every matching decision is about detections and intervals —
    and a test asserts the two datasets give the same precision, recall and false-positive count.

    Args:
        stream_factory: Produces a fresh, time-ordered observation stream over the corpus.
        first_attack: Everything from here on is the test half.
        fitted: The model fitted on the prefix.
        policy: How per-feature contributions combine.
        subsets: ``label -> features to score``, or ``None`` for every feature. Two subsets over
            one stream is how "did the peer features add anything?" is asked without also changing
            the model, the split, or the corpus read.

    Returns:
        ``(detections by subset, scoring summary by subset, one observation per user-window)``.
    """
    scorers = {label: WindowScorer(fitted, policy, features) for label, features in subsets.items()}
    detections: dict[str, list[Detection]] = {label: [] for label in subsets}
    windows: list[Observation] = []
    seen: set[tuple[str, datetime]] = set()
    read = 0

    for observation in stream_factory():
        read += 1
        if read % _LOG_EVERY == 0:
            logger.info("pass 2: %d observations scored, %d user-windows kept", read, len(windows))
        if observation.timestamp < first_attack:
            continue
        key = (observation.entity_ids[0], observation.timestamp)
        if key not in seen:
            seen.add(key)
            windows.append(observation)
        for label, scorer in scorers.items():
            detections[label] += [
                window.as_detection(policy.score_scale) for window in scorer.push(observation)
            ]

    summaries: dict[str, ScoringSummary] = {}
    for label, scorer in scorers.items():
        detections[label] += [window.as_detection(policy.score_scale) for window in scorer.close()]
        summaries[label] = scorer.summary()
        logger.info("%s: %s", label, summaries[label].note())
    logger.info("pass 2: %d observations scored into %d user-windows", read, len(windows))
    return detections, summaries, windows


def thresholds_for_budgets(
    detections: Sequence[Detection], budgets: Sequence[int]
) -> dict[int, float]:
    """Return the score threshold that yields about each target alert count.

    An operating point chosen by **budget** rather than by threshold, because a threshold means a
    different thing for every feature-set width and an analyst's constraint is the number of alerts
    they can work. No label is consulted: this reads the score distribution and nothing else, which
    is what keeps it a choice of operating point rather than a fit to the answer.

    Args:
        detections: Every detection the run produced.
        budgets: Target alert counts.

    Returns:
        ``budget -> threshold``. A budget larger than the detection count is dropped, and ties mean
        the realised count can exceed the target — which the report states rather than rounds away.
    """
    ranked = sorted((detection.score for detection in detections), reverse=True)
    return {budget: ranked[budget - 1] for budget in budgets if 0 < budget <= len(ranked)}


PEER_SUBSET: Final = "peer set (34 features)"
ENRICHED_SUBSET: Final = "enriched control (26 features)"
"""The two subsets a peer run scores, from one corpus read and one fitted model.

The control is not decoration. Without it, a change in the numbers between PART 6A and PART 6B
could be the peer features or could be the scoring shape, and there would be no way to tell which.
Scoring the 26 per-entity features of the same emitted stream, through the same model and the same
aggregation, isolates the peer family as the only difference.
"""


def run_aggregated(
    stream_factory: Callable[[], Iterator[Observation]],
    labels: Sequence[EntityLabelledInterval],
    featuriser: Featuriser,
    dataset_name: str,
    provenance: str,
    train_fraction: float,
    min_samples: int,
    config: EvalConfig,
    grouping: str,
    budgets: Sequence[int],
    policy: AggregationPolicy,
) -> tuple[list[EvaluationReport], list[EntityLabelledInterval], dict[str, ScoringSummary]]:
    """Fit on the attack-free prefix, then score the remainder one alert per **entity-window**.

    Args:
        stream_factory: Produces a fresh, time-ordered observation stream. Called twice.
        labels: Entity-scoped ground truth for the whole corpus.
        featuriser: The featuriser the streams came from, read for its feature list.
        dataset_name: Name the corpus is logged under.
        provenance: Where the corpus came from, opening the report's ``source_note``.
        train_fraction: Ceiling on the training prefix, checked against the attack-bound split.
        min_samples: Fewest training points a baseline needs.
        config: PART 2's evaluation config, unchanged.
        grouping: `phos.sentiel.PeerGroups.summary`, carried onto every report.
        budgets: Target alert counts to evaluate each subset at, so the comparison is made where
            an analyst actually works rather than at whatever threshold happens to be the default.
        policy: How per-feature contributions combine into a window score.

    Returns:
        ``(reports, labels falling in the test half, scoring summary per subset)``.

    Raises:
        BaselineError: If the corpus is empty, has no attack-free prefix, or leaves no labelled
            insider in the test half.
    """
    first_attack = min(label.start for label in labels)
    fitted, corpus_start, _ = fit_on_prefix(stream_factory, first_attack, min_samples)

    subsets: dict[str, frozenset[str] | None] = {PEER_SUBSET: None}
    if featuriser.feature_set is FeatureSet.PEER:
        subsets[ENRICHED_SUBSET] = frozenset(ENRICHED_FEATURES)
    detections, summaries, windows = score_streaming(
        stream_factory, first_attack, fitted, policy, subsets
    )
    if not windows:
        raise BaselineError("the test half is empty; lower --train-fraction or check the labels")
    check_the_attack_bound_the_split(
        corpus_start, windows[-1].timestamp, first_attack, train_fraction
    )

    in_test = [
        label
        for label in labels
        if label.start <= windows[-1].timestamp and label.end >= windows[0].timestamp
    ]
    if not in_test:
        raise BaselineError(
            "no labelled insider falls in the test half, so recall would be vacuous; lower "
            "--train-fraction"
        )

    test = Dataset(
        name=f"{dataset_name}-test",
        domain=Domain.SENTIEL,
        observations=windows,
        attack_intervals=[],  # Sentiel truth is entity-scoped; it travels in `labels`.
        source_note="",
    )
    counts = base_rate(test, in_test)
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]
    logger.info(
        "test half: %d user-windows, %d of them malicious (%.4f%%); %d of %d insider(s) inside it",
        total,
        counts["malicious_user_windows"],
        100.0 * counts["malicious_user_windows"] / max(total, 1),
        len(in_test),
        len(labels),
    )

    commit = current_git_commit(REPO_ROOT)
    reports: list[EvaluationReport] = []
    for label, alerts in detections.items():
        scored_features = subsets[label]
        note = peer_source_note(
            f"{provenance} | {total:,} test user-windows x "
            f"{len(featuriser.feature_names)} emitted features ({featuriser.feature_set.value}), "
            f"one-day windows | SCORED SUBSET: {label} — "
            f"{len(scored_features) if scored_features else len(featuriser.feature_names)} of "
            f"{len(featuriser.feature_names)} emitted features, aggregated to one score per "
            f"entity-window | n_observations on this report counts USER-WINDOWS, not feature "
            f"observations, because the alert unit is a window; the underlying feature stream was "
            f"{total * len(featuriser.feature_names):,} observations | "
            f"{summaries[label].note()} | {len(in_test)} labelled insider(s) in the test half: "
            + ", ".join(f"{item.user_id}/scenario-{item.scenario}" for item in in_test)
            + f" | test half of a train_fraction={train_fraction} attack-free-prefix split",
            f"base rate {counts['malicious_user_windows']} malicious of {total} user-windows",
            grouping,
        )
        detector = PrecomputedDetector(
            name=f"aggregate:gaussian:{label}{policy.log_suffix}", detections=alerts
        )
        thresholds = [config.alert_threshold, *thresholds_for_budgets(alerts, budgets).values()]
        for threshold in thresholds:
            at = config.model_copy(update={"alert_threshold": threshold})
            report = evaluate_entity_aware(
                detector, test.model_copy(update={"source_note": note}), in_test, at
            )
            comparison = three_way(report, counts, len(featuriser.feature_names), label)
            reports.append(
                report.model_copy(
                    update={
                        "git_commit": commit,
                        "source_note": f"{report.source_note} | {comparison}",
                    }
                )
            )
    return reports, in_test, summaries


class OpenedCorpus(NamedTuple):
    """Everything a run needs to read one release twice."""

    stream_factory: Callable[[], Iterator[Observation]]
    labels: list[EntityLabelledInterval]
    featuriser: Featuriser
    dataset_name: str
    provenance: str
    peer_groups: PeerGroups | None


def build_corpus(
    data_dir: Path,
    manifest: dict[str, object],
    feature_set: FeatureSet,
    peer_policy: PeerPolicy | None = None,
) -> OpenedCorpus:
    """Open the release and return everything a run needs to read it twice.

    Args:
        data_dir: Where the corpus was fetched to.
        manifest: The committed CERT manifest.
        feature_set: Which features to emit.
        peer_policy: Which declared attribute makes a peer group, and how small a group may be.
            Read only when ``feature_set`` is `FeatureSet.PEER`, and applied to the release's own
            LDAP directory rather than to anything derived from behaviour.

    Raises:
        BaselineError: If the directory carries no email addresses to define "external" from, or
            carries no value for the grouping attribute a peer run needs.
    """
    release_dir = data_dir / str(manifest["release_dir"])
    answers_dir = data_dir / str(manifest["answers_dir"])
    release_name = str(manifest["release"])

    reader = CertReader.for_release(CertRelease.discover(release_dir))
    catalogue = reader.catalogue()
    org_domain = catalogue.dominant_email_domain()
    if not org_domain:
        raise BaselineError(
            f"the LDAP directory under {release_dir} carries no email addresses, so 'external "
            "email' cannot be defined from the corpus rather than guessed at"
        )
    logger.info(
        "directory: %d users as of %s; organisation mail domain %s",
        len(catalogue.entities),
        catalogue.directory_as_of.date(),
        org_domain,
    )

    labels = read_insiders(answers_dir, release_name)
    if not labels:
        raise BaselineError(f"{answers_dir} names no insider for release {release_name}")

    groups: PeerGroups | None = None
    if feature_set.needs_peers:
        try:
            groups = PeerGroups.from_catalogue(catalogue, peer_policy or PeerPolicy())
        except ValueError as error:
            raise BaselineError(str(error)) from error
        logger.info("%s", groups.summary())

    featuriser = build_featuriser(org_domain, feature_set, groups)
    suffix = {FeatureSet.STARTER: "", FeatureSet.ENRICHED: "-enriched", FeatureSet.PEER: "-peer"}[
        feature_set
    ]
    provenance = (
        f"CERT Insider Threat {release_name} (CMU/SEI, doi:10.1184/R1/12841247.v1) | "
        f"{len(catalogue.entities)} directory users"
    )
    return OpenedCorpus(
        stream_factory=lambda: featuriser.stream(reader.events()),
        labels=labels,
        featuriser=featuriser,
        dataset_name=f"cert-{release_name}-user-day{suffix}",
        provenance=provenance,
        peer_groups=groups,
    )


_CAVEATS_BY_SET: Final[dict[FeatureSet, tuple[str, ...]]] = {
    FeatureSet.STARTER: SENTIEL_CAVEATS,
    FeatureSet.ENRICHED: ENRICHED_CAVEATS,
    FeatureSet.PEER: PEER_CAVEATS,
}


def report_lines(
    report: EvaluationReport,
    labels: Sequence[EntityLabelledInterval],
    featuriser: Featuriser,
    scoring: ScoringSummary | None = None,
) -> list[str]:
    """Render the honest summary printed at the end of a run."""
    caught = f"{report.window_recall * len(labels):.0f}/{len(labels)}"
    marker = "THREE-WAY" if scoring is not None else "SIDE-BY-SIDE"
    comparison = report.source_note.rpartition(marker)[2]
    caveats = _CAVEATS_BY_SET[featuriser.feature_set]
    return [
        "",
        "=" * 96,
        f"SENTIEL BASELINE — {report.detector_name} on {report.dataset_name}",
        f"  feature set            {featuriser.feature_set.value} "
        f"({len(featuriser.feature_names)} features)",
        "=" * 96,
        f"  commit                 {report.git_commit or '(unknown)'}",
        f"  seed                   {report.seed}",
        f"  alert threshold        {report.alert_threshold:.4f}",
        f"  {'user-windows (test)  ' if scoring is not None else 'observations (test)  '}  "
        f"{report.n_observations:,}",
        f"  alerts                 {report.n_alerts:,}",
        "",
        f"  window recall          {report.window_recall:.4f}   ({caught} insiders caught — "
        "NOT QUOTABLE at 2 insiders)",
        f"  precision              {report.precision:.6f}",
        f"  false positives        {report.false_positives:,}",
        f"  FP per normal USER-hr  {report.false_positive_rate:.4f}",
        f"  sample recall          {report.recall_sample:.4f}",
        f"  F1                     {report.f1:.6f}",
        f"  ECE                    {report.expected_calibration_error:.4f}",
        f"  Brier                  {report.brier_score:.4f}",
        "  median latency         "
        + (
            f"{report.latency.median_seconds / 3600.0:.1f} h"
            if report.latency.median_seconds is not None
            else "(nothing caught)"
        ),
        "",
        *([f"  scoring                {scoring.note()}", ""] if scoring is not None else []),
        f"  {marker}{comparison}",
        "",
        "  CAVEATS (stamped into source_note on the logged report, so they cannot be read apart",
        "  from the numbers above):",
        *[f"    - {caveat}" for caveat in caveats],
        f"  peak memory            {_peak_memory_gb():.2f} GB",
        "=" * 96,
    ]


def _peak_memory_gb() -> float:
    """Return this process's peak resident set size in GB, for the record."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes. Anything under a megabyte cannot be a real
    # peak for this script, so the small number is the kilobyte one.
    return (usage if usage > 1_000_000 else usage * 1024) / _BYTES_PER_GB


def _aggregation_policy(arguments: argparse.Namespace) -> AggregationPolicy:
    """Return the scorer policy for this invocation, identity unless ``--precision-policy``."""
    borrowed = not arguments.no_borrowed_scale
    if arguments.precision_policy:
        return precision_policy().model_copy(
            update={
                "score_scale": arguments.score_scale,
                "borrow_population_scale": borrowed,
            }
        )
    return AggregationPolicy(
        score_scale=arguments.score_scale,
        borrow_population_scale=borrowed,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--feature-set",
        choices=[member.name.lower() for member in FeatureSet],
        default=FeatureSet.ENRICHED.name.lower(),
        help=(
            "starter reproduces the PART 6·D baseline; enriched measures PART 6A; peer adds PART "
            "6B's peer-relative companions and needs --scoring aggregated to be usable"
        ),
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--train-fraction", type=float, default=0.5)
    parser.add_argument("--alert-threshold", type=float, default=3.0)
    parser.add_argument(
        "--extra-thresholds",
        type=float,
        nargs="*",
        default=[],
        help=(
            "further alert thresholds to score the same fitted model at, so two feature sets can "
            "be compared at a matched alert budget rather than at a matched per-feature threshold"
        ),
    )
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument(
        "--scoring",
        choices=["per-feature", "aggregated"],
        default="per-feature",
        help=(
            "per-feature is PART 6·D's and 6A's shape, one alert per feature per window, and is "
            "the default so both stay reproducible from this code; aggregated is PART 6B's, one "
            "alert per entity-window"
        ),
    )
    parser.add_argument(
        "--group-attribute",
        default=DEFAULT_GROUP_ATTRIBUTE,
        help="the LDAP attribute a peer group is cut from (peer feature set only)",
    )
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=PeerPolicy().min_group_size,
        help="fewest declared members a peer group needs before its members get peer features",
    )
    parser.add_argument(
        "--alert-budgets",
        type=int,
        nargs="*",
        default=[200, 500, 1_000, 5_000],
        help=(
            "target alert counts to evaluate an aggregated run at. An operating point chosen by "
            "the constraint an analyst actually has, rather than by a threshold whose meaning "
            "changes with the width of the feature set. No label is consulted to pick it"
        ),
    )
    parser.add_argument("--score-scale", type=float, default=AggregationPolicy().score_scale)
    parser.add_argument(
        "--precision-policy",
        action="store_true",
        help=(
            "apply the opt-in aggregation that discounts volume features, off-hours, "
            "self-relative-only departures, and single-family windows. Default AggregationPolicy "
            "is unchanged so PART 6B rows stay reproducible. The detector name gains :precision"
        ),
    )
    parser.add_argument(
        "--no-borrowed-scale",
        action="store_true",
        help=(
            "score a feature whose own baseline has no spread at the clamped maximum, as PART 6A "
            "did, instead of against the population's spread. Reproduces the alert floor"
        ),
    )
    parser.add_argument(
        "--no-log", action="store_true", help="compute but do not append to the experiment log"
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    feature_set = FeatureSet[arguments.feature_set.upper()]
    config = EvalConfig(
        alert_threshold=arguments.alert_threshold,
        match_tolerance=timedelta(0),
        seed=arguments.seed,
    )

    summaries: dict[str, ScoringSummary] = {}
    try:
        manifest = load_manifest(arguments.data_dir)
        corpus = build_corpus(
            arguments.data_dir,
            manifest,
            feature_set,
            PeerPolicy(
                group_attribute=arguments.group_attribute,
                min_group_size=arguments.min_group_size,
            ),
        )
        if arguments.scoring == "aggregated":
            reports, test_labels, summaries = run_aggregated(
                stream_factory=corpus.stream_factory,
                labels=corpus.labels,
                featuriser=corpus.featuriser,
                dataset_name=corpus.dataset_name,
                provenance=corpus.provenance,
                train_fraction=arguments.train_fraction,
                min_samples=arguments.min_samples,
                config=config,
                grouping=corpus.peer_groups.summary() if corpus.peer_groups else "",
                budgets=arguments.alert_budgets,
                policy=_aggregation_policy(arguments),
            )
        else:
            reports, test_labels = run(
                stream_factory=corpus.stream_factory,
                labels=corpus.labels,
                featuriser=corpus.featuriser,
                dataset_name=corpus.dataset_name,
                provenance=corpus.provenance,
                train_fraction=arguments.train_fraction,
                min_samples=arguments.min_samples,
                config=config,
                extra_thresholds=arguments.extra_thresholds,
            )
    except BaselineError as error:
        logger.error("%s", error)
        return 2

    for report in reports:
        subset = report.detector_name.partition("aggregate:gaussian:")[2]
        for line in report_lines(report, test_labels, corpus.featuriser, summaries.get(subset)):
            print(line)
        if not arguments.no_log:
            append_to_experiment_log(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
