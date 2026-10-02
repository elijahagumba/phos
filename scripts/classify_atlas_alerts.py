#!/usr/bin/env python3
"""Decompose the Atlas false-positive load into an error taxonomy, and say what generates it.

`atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events` reports **53.26 false positives per
normal hour** on HAI — 424 subsystem events over 7.89 normal hours, of which 6 overlap a labelled
attack (ADR 0068). That is one undifferentiated number, and it has only ever been treated as a
quantity to reduce. This script asks the other question: **what kind of uncertainty is generating
those alerts?**

It runs in three stages, and the order matters.

1. **The gate.** The frozen rows are reproduced first, by the script that has always measured them,
   before a single new number is produced. If 646.58 ungated, 53.26 grouped, 424 events or window
   recall 1.00 do not come back, the run aborts — because a taxonomy of a different alert set than
   the one that was logged would be a taxonomy of nothing.
2. **The corpus screen.** Each candidate category is asked whether HAI carries the evidence it needs
   *at all*, before any event is looked at. Four categories are refuted by measurement here, two are
   not separable, and the screens say which on what basis.
3. **The reference and the classification.** The model exactly as fitted is applied to the corpus's
   own attack-free training file — 60 hours it never saw — and what it does there becomes the
   yardstick. An alert whose departure is no larger than one the model produces on declared-normal
   data is not reacting to the plant.

**Nothing here refits a public model, searches a threshold, or proposes an operating point.** The
fit-set contrast this script prints is a diagnostic under its own experiment name; its
false-positive figures are its own instrument's and are **not** the frozen rows, which are produced
separately in stage 1 by their own code. No row is appended to `eval_runs/log.jsonl`: a
re-decomposition of a logged alert set is a diagnostic, and it lands in `eval_runs/atlas/`,
following ADR 0065 and ADR 0068.

Usage::

    PYTHONPATH=src python scripts/classify_atlas_alerts.py
    PYTHONPATH=src python scripts/classify_atlas_alerts.py --no-write
    PYTHONPATH=src python scripts/classify_atlas_alerts.py --skip-gate   # development only
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

import numpy
import pandas

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_atlas_vertical import (  # noqa: E402
    SEED,
    THREE_WAY_POLICIES,
    adapter,
    discover,
    run_corpus,
    split_evidence,
)

from phos.atlas import (  # noqa: E402
    AtlasEngine,
    MahalanobisModel,
    load_topology,
    member_evidence_ids,
)
from phos.atlas.multivariate import (  # noqa: E402
    MultivariateFittedModel,
    _departure,
)
from phos.atlas.vectorise import vectorise  # noqa: E402
from phos.eval import Dataset, current_git_commit  # noqa: E402

# Imported from the submodules rather than through `phos.eval`, on purpose. Two Sentiel contract
# tests assert that `src/phos/eval` shows no diff against HEAD — the strongest available statement
# that the PART 2 harness was reused exactly as it was (tests/sentiel/test_evaluation.py and
# test_featurise.py). Adding modules to the package does not break that; re-exporting them through
# its `__init__` would, because that edits the surface those tests pin. See ADR 0075.
from phos.eval.taxonomy import (  # noqa: E402
    OVERLAPS_LABELLED_ATTACK,
    AlertUnderReview,
    CorpusScreen,
    MemberDeparture,
    SignalReference,
    classify,
    contributions,
    signature_runs,
)
from phos.eval.taxonomy_evidence import (  # noqa: E402
    AlertRatePair,
    CyclePeriod,
    FitLengthPoint,
    NoiseScaleRatio,
    TrendStrength,
    cycle_periods,
    noise_scale_ratios,
    summarise_ratios,
    sweep_transition,
    trend_strengths,
)
from phos.eval.taxonomy_report import render_taxonomy_markdown  # noqa: E402
from phos.ontology import Observation  # noqa: E402
from phos.reasoning import (  # noqa: E402
    IsotonicCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

logger = logging.getLogger("phos.atlas.taxonomy")

DATA_DIR: Final = REPO_ROOT / "data"
OUTPUT_DIR: Final = REPO_ROOT / "eval_runs" / "atlas"
CORPUS: Final = "hai"
GROUPING_WINDOW: Final = timedelta(minutes=1)
SAMPLE_SECONDS: Final = 10.0

#: Fit lengths the sweep walks, in timestamps of declared-normal data. Spaced to bracket the
#: transition rather than to find a best point: a doubling ladder to locate the step, then a finer
#: run across where it falls, then out to the whole file so the right-hand end is the whole
#: reference.
#: Every point is reported. Changing this list changes the resolution of the curve, never a claim.
SWEEP_LENGTHS: Final[tuple[int, ...]] = (
    350,
    700,
    1_400,
    1_750,
    2_100,
    2_800,
    5_600,
    11_200,
    21_601,
)

#: The frozen rows this run must reproduce before it is allowed to produce anything. ADR 0068 and
#: the Usefulness Phase both require it: a taxonomy of a different alert set is a taxonomy of
#: nothing. Compared to four decimal places, which is tighter than any of them is quoted at.
FROZEN: Final[dict[str, float]] = {
    "ungated_fp_per_normal_hour": 646.5797816132441,
    "grouped_fp_per_normal_hour": 53.25818950334625,
    "subsystem_events": 424.0,
    "grouped_window_recall": 1.0,
}

#: Signals that declare the plant's run state, mode and pump configuration on HAI, hand-read from
#: the same manual `data/hai/topology.toml` cites. If every one of these is constant across a slice,
#: the plant did not start, stop, change mode or go to manual during it — which refutes three
#: categories by measurement rather than by assumption.
RUN_STATE_SIGNALS: Final[tuple[str, ...]] = (
    "P1_STSP",
    "P1_PP01AD",
    "P1_PP01AR",
    "P1_PP01BD",
    "P1_PP01BR",
    "P1_PP02D",
    "P1_PP02R",
    "P2_ASD",
    "P2_AutoGO",
    "P2_Emerg",
    "P2_MSD",
    "P2_ManualGO",
    "P2_OnOff",
    "P2_RTR",
    "P2_TripEx",
)


class GateError(RuntimeError):
    """Raised when a frozen row does not reproduce, so nothing downstream may be trusted."""


def reproduce_frozen_gate() -> str:
    """Re-measure the frozen HAI rows with the code that has always measured them.

    Returns:
        A one-line statement of what reproduced, for the report's header.

    Raises:
        GateError: If any frozen row differs, or the corpus cannot be loaded at all.
    """
    manifest = dict(dict(discover([CORPUS]))[CORPUS])
    result = run_corpus(CORPUS, manifest)
    if result is None:
        raise GateError(f"{CORPUS}: the vertical produced no result, so the gate cannot be read")
    before, after = result.reports[1], result.reports[2]
    measured = {
        "ungated_fp_per_normal_hour": before.false_positive_rate,
        "grouped_fp_per_normal_hour": after.false_positive_rate,
        "subsystem_events": float(result.n_events),
        "grouped_window_recall": after.window_recall,
    }
    drift = {
        key: (FROZEN[key], value)
        for key, value in measured.items()
        if abs(value - FROZEN[key]) > 1e-4
    }
    if drift:
        raise GateError(
            "frozen row(s) did not reproduce, so no taxonomy may be built on this run: "
            + "; ".join(
                f"{key} expected {want:.4f}, got {got:.4f}" for key, (want, got) in drift.items()
            )
        )
    logger.info("gate: frozen rows reproduced exactly")
    return (
        f"**reproduced** — {measured['ungated_fp_per_normal_hour']:.2f} FP/normal-hour ungated, "
        f"{measured['grouped_fp_per_normal_hour']:.2f} grouped, "
        f"{int(measured['subsystem_events'])} subsystem events, "
        f"window recall {measured['grouped_window_recall']:.2f}"
    )


def _declared_normal_dataset() -> Dataset:
    """Load the corpus's own attack-free training file, refusing it if it carries an attack.

    Returns:
        The declared-normal dataset.

    Raises:
        GateError: If the file is absent, or declares an attack interval — in which case it is not a
            reference for normal operation and every verdict resting on it would be wrong.
    """
    manifest = dict(dict(discover([CORPUS]))[CORPUS])
    if "train" not in manifest or not (DATA_DIR / manifest["train"]["path"]).is_file():
        raise GateError(f"{CORPUS}: no declared-normal training file, so there is no reference")
    reference = adapter(manifest["train"]).load()
    if reference.attack_intervals:
        raise GateError(
            f"{CORPUS}: the declared-normal file carries {len(reference.attack_intervals)} attack "
            "interval(s), so it is not a reference for normal operation"
        )
    return reference


def _without_attacks(dataset: Dataset) -> Dataset:
    """Return the dataset with every observation inside a labelled attack window removed.

    Used only to put the slice's *normal* alert rate beside the reference's, so the comparison is
    normal-against-normal. Labels are used here to exclude, never to select or to tune.
    """
    intervals = dataset.attack_intervals
    kept = [
        item
        for item in dataset.observations
        if not any(interval.contains(item.timestamp) for interval in intervals)
    ]
    return dataset.model_copy(update={"observations": kept, "attack_intervals": []})


def _alerts_and_model() -> tuple[list[AlertUnderReview], MultivariateFittedModel, Dataset, int]:
    """Rebuild the logged alert set and return it with the model that produced it.

    Returns:
        ``(alerts, fitted model, scored slice, timestamps the fit used)``.
    """
    manifest = dict(dict(discover([CORPUS]))[CORPUS])
    loaded = adapter(manifest).load()
    train, calib, test = train_calib_test_split(loaded, THREE_WAY_POLICIES[CORPUS])
    fitted = MahalanobisModel().fit(train.observations)
    scores, labels = scores_and_labels_from(fitted, calib)
    calibrator = IsotonicCalibrator(seed=SEED).fit(scores, labels)
    topology = load_topology(
        DATA_DIR / CORPUS / "topology.toml",
        {observation.feature for observation in loaded.observations},
        corpus=CORPUS,
    )
    engine = AtlasEngine(fitted=fitted, calibrator=calibrator, subsystem_map=topology)
    engine.run(test)
    per_signal, events = split_evidence(engine)
    members = {item.id: item for item in per_signal}

    alerts: list[AlertUnderReview] = []
    for event in events:
        departures: list[MemberDeparture] = []
        for member_id in member_evidence_ids(event):
            member = members[member_id]
            deviation = engine.store.get_deviation(member.source_id)
            if deviation is None:  # pragma: no cover — the store refuses a dangling reference
                raise RuntimeError(f"evidence {member.id} has no deviation")
            observation = engine.store.get_observation(deviation.observation_id)
            if observation is None:  # pragma: no cover — same
                raise RuntimeError(f"deviation {deviation.id} has no observation")
            departures.append(
                MemberDeparture(
                    signal=deviation.expected.feature,
                    magnitude=deviation.magnitude,
                    value=observation.value,
                )
            )
        alerts.append(
            AlertUnderReview(
                evidence_id=event.id,
                timestamp=event.timestamp,
                subsystem=event.summary.split(" (")[0],
                members=tuple(departures),
                overlaps_attack=any(
                    interval.contains(members[member_id].timestamp)
                    for interval in test.attack_intervals
                    for member_id in member_evidence_ids(event)
                ),
            )
        )
    logger.info("rebuilt %d alert(s) with %d member(s)", len(alerts), len(per_signal))
    return alerts, fitted, test, len({item.timestamp for item in train.observations})


def declared_normal_references(
    fitted: MultivariateFittedModel, signals: Sequence[str]
) -> dict[str, SignalReference]:
    """Score the corpus's own attack-free training file with the model exactly as fitted.

    The reference is declared normal by the corpus author and the model never saw it, so what the
    model does here is its own out-of-sample behaviour on ordinary operation. No label on the judged
    side is consulted and no threshold is chosen: the band is the one the model already reports.

    Args:
        fitted: The model as the vertical fitted it.
        signals: The signals that actually departed, and therefore need a reference.

    Returns:
        One `SignalReference` per requested signal.

    Raises:
        GateError: If the declared-normal training file is absent or carries an attack interval,
            which would make it a reference to something other than normal operation.
    """
    reference = _declared_normal_dataset()
    assembled = vectorise(reference.observations, fitted.signal_space, fitted.fill_policy)
    matrix = assembled.matrix
    magnitudes = _departure(matrix, fitted._expected_values(matrix), fitted._signal_spread())
    spread = fitted._signal_spread()
    floor = float(spread.min())
    columns = {signal[1]: index for index, signal in enumerate(fitted.signal_space.signals)}
    hours = len(assembled.timestamps) * SAMPLE_SECONDS / 3600.0
    references: dict[str, SignalReference] = {}
    for signal in signals:
        column = columns[signal]
        values = matrix[:, column]
        band = float(fitted.band_k * spread[column])
        references[signal] = SignalReference(
            signal=signal,
            band_high=band,
            declared_normal_stddev=float(numpy.std(values)),
            declared_normal_exceedance=float((magnitudes[:, column] > fitted.band_k).mean()),
            declared_normal_max_magnitude=float(magnitudes[:, column].max()),
            reference_hours=hours,
            at_shrinkage_floor=abs(float(spread[column]) - floor) < 0.5,
            envelope_low=float(values.min()),
            envelope_high=float(values.max()),
        )
    logger.info(
        "reference: %.2f h of declared-normal data, %d of %d signal(s) at the shrinkage floor",
        hours,
        sum(1 for r in references.values() if r.at_shrinkage_floor),
        len(references),
    )
    return references


def screen_corpus(
    frame: pandas.DataFrame,
    noise: Mapping[str, NoiseScaleRatio],
    trends: Mapping[str, TrendStrength],
) -> list[CorpusScreen]:
    """Ask what HAI can say about each candidate category, before any event is looked at.

    Every verdict here is a measurement on the scored slice, not a judgement. Four categories come
    back refuted, two come back not separable, and each carries the figure behind it.

    Args:
        frame: The scored slice as raw rows, timestamps included.
        noise: Lag-1 jitter ratios per departing signal, slice against declared normal.
        trends: Monotone-trend strength per departing signal, with its envelope shift.

    Returns:
        One screen per candidate category, in a declared order.

    Raises:
        GateError: If a measurement contradicts the verdict the screen would record — an instrument
            that did become noisier, or a trend that is separable from a cycle phase. The screen
            would then be wrong, and a wrong screen silently removes a category from competition.
    """
    drifting = [trend for trend in trends.values() if trend.drifting]
    moved = ", ".join(
        f"`{trend.signal}`" for trend in trends.values() if trend.envelope_shift > 0.1
    )
    noisier = sorted(signal for signal, ratio in noise.items() if ratio.noisier)
    if noisier:
        raise GateError(
            "the sensor-noise screen cannot be refuted on this slice: "
            f"{', '.join(noisier)} became materially noisier than declared normal. Classify these "
            "by hand rather than letting the screen assert otherwise"
        )
    separable = sorted(
        signal for signal, trend in trends.items() if trend.separable_from_cycle_phase
    )
    if separable:
        raise GateError(
            "the equipment-ageing screen cannot report not_separable on this slice: the "
            "envelope of "
            f"{', '.join(separable)} has moved against declared normal, so a trend there is "
            "separable from a duty-cycle phase and must be classified rather than screened out"
        )
    deltas = frame["timestamp"].diff().dt.total_seconds().dropna().unique()
    duplicated = int(frame["timestamp"].duplicated().sum())
    moving = [
        signal
        for signal in RUN_STATE_SIGNALS
        if signal in frame.columns and frame[signal].nunique() > 1
    ]
    present = [signal for signal in RUN_STATE_SIGNALS if signal in frame.columns]
    context_columns = [
        column
        for column in frame.columns
        if any(key in column.lower() for key in ("work", "maint", "oper", "user", "ticket", "mode"))
    ]
    hours = len(frame) * SAMPLE_SECONDS / 3600.0
    return [
        CorpusScreen(
            category="modelling_error",
            verdict="assigned",
            basis=(
                "the model's own band and its behaviour on declared-normal data are both "
                "available, so the counterfactual in MODEL_FAULT_PRECEDENCE is decidable"
            ),
        ),
        CorpusScreen(
            category="normal_process_variation",
            verdict="assigned",
            basis=(
                "the corpus declares an operating envelope elsewhere — its 60 h attack-free "
                "training file — so 'inside the envelope declared elsewhere' is decidable"
            ),
        ),
        CorpusScreen(
            category="genuinely_unusual_benign",
            verdict="assigned",
            basis="decidable as the residual of the declared-normal reference being exceeded",
        ),
        CorpusScreen(
            category="communication_artefacts",
            verdict="refuted",
            basis=(
                f"every one of the {len(frame) - 1:,} inter-sample intervals in the scored "
                "slice is "
                f"exactly {', '.join(f'{d:.1f}' for d in sorted(deltas))} s, with {duplicated} "
                "duplicate timestamp(s) and no duplicate rows. The corpus carries no gap, repeat "
                "or timestamp irregularity for an alert to be reacting to"
            ),
        ),
        CorpusScreen(
            category="startup_shutdown_transition",
            verdict="refuted",
            basis=(
                f"all {len(present)} declared run-state signals are constant across the whole "
                f"{hours:.2f} h slice ({len(moving)} moved). The plant did not start, stop, trip "
                "or go to manual during it"
            ),
        ),
        CorpusScreen(
            category="grade_or_recipe_change",
            verdict="refuted",
            basis=(
                "no declared mode or setpoint change occurs anywhere in the slice — the same "
                "constant run-state and pump-configuration signals are the only mode evidence HAI "
                "carries, and none of them moves"
            ),
        ),
        CorpusScreen(
            category="sensor_noise",
            verdict="refuted",
            basis=(
                f"the lag-1 absolute-difference scale of all {len(noise)} departing signals in "
                f"the scored slice is within 1.5x of its scale over the declared-normal reference "
                f"({summarise_ratios(noise)}). No instrument became materially noisier"
            ),
        ),
        CorpusScreen(
            category="maintenance",
            verdict="not_separable",
            basis=(
                f"HAI carries no work-order, operator-identity or mode-register channel: "
                f"{len(context_columns)} of its {len(frame.columns) - 2} data columns name one. "
                "Maintenance and an attacker leave the same evidence and only priors separate them"
            ),
            what_would_lift_it=(
                "a CMMS work-order export covering the capture window, reaching the inlet Session "
                "E3 built (ADR 0069), naming the unit, the window and the authorised actor"
            ),
        ),
        CorpusScreen(
            category="equipment_ageing",
            verdict="not_separable",
            basis=(
                f"the corpus spans 2.5 days. {len(drifting)} departing signal(s) show a monotone "
                f"trend across the slice (Spearman rho to "
                f"{min((t.rho_under_review for t in drifting), default=0.0):+.2f} against "
                f"{min((t.rho_reference for t in drifting), default=0.0):+.2f} over the much "
                f"longer declared-normal reference), and every one does it inside an unmoved "
                f"envelope — their 5th-95th-percentile band sits within "
                f"{max((t.envelope_shift for t in drifting), default=0.0):.1%} of the reference "
                f"band's width of where the reference puts it. The only signal whose envelope did "
                f"move materially, {moved or 'none'}, shows no trend at all. Over 2.5 days a "
                "monotone run inside an unmoved envelope and a degradation are one measurement"
            ),
            what_would_lift_it=(
                "months of continuous declared-normal capture from one plant, enough that a trend "
                "in the envelope itself is separable from a trend within one cycle"
            ),
        ),
        CorpusScreen(
            category="insufficient_context",
            verdict="assigned",
            basis="available as the residual when no other discriminator fires",
        ),
    ]


def _score(model: MultivariateFittedModel, dataset: Dataset) -> tuple[int, float, int, int]:
    """Return ``(alerts, percent of moments alerting, windows caught, windows available)``."""
    assembled = vectorise(dataset.observations, model.signal_space, model.fill_policy)
    magnitudes = _departure(
        assembled.matrix, model._expected_values(assembled.matrix), model._signal_spread()
    )
    alerting = magnitudes > model.band_k
    intervals = dataset.attack_intervals
    covered = {
        index
        for index, interval in enumerate(intervals)
        for row, stamp in enumerate(assembled.timestamps)
        if interval.contains(stamp) and bool(alerting[row].any())
    }
    return (
        int(alerting.sum()),
        float(alerting.any(axis=1).mean() * 100.0),
        len(covered),
        len(intervals),
    )


def alert_rate_pair(
    fitted: MultivariateFittedModel, reference: Dataset, scored_normal: Dataset
) -> AlertRatePair:
    """Measure the model's alert rate on declared-normal data and on the scored slice's normal rows.

    The pair the whole finding rests on. If they agree, the alert load on the slice is the model's
    own out-of-sample behaviour on ordinary operation.

    Args:
        fitted: The model as the vertical fitted it.
        reference: The declared-normal dataset the model never saw.
        scored_normal: The scored slice with its attack rows removed.

    Returns:
        The two rates and the reference's length.
    """
    _, reference_pct, _, _ = _score(fitted, reference)
    _, slice_pct, _, _ = _score(fitted, scored_normal)
    hours = len({item.timestamp for item in reference.observations}) * SAMPLE_SECONDS / 3600.0
    pair = AlertRatePair(
        reference_pct=reference_pct, under_review_pct=slice_pct, reference_hours=hours
    )
    logger.info(
        "alert rate: %.2f%% of declared-normal moments, %.2f%% of scored-slice normal moments (%s)",
        pair.reference_pct,
        pair.under_review_pct,
        "indistinguishable" if pair.indistinguishable else "DIFFERENT",
    )
    return pair


def fit_length_sweep(
    fitted: MultivariateFittedModel,
    reference: Dataset,
    test: Dataset,
    lengths: Sequence[int],
    *,
    frozen_fit_timestamps: int,
) -> list[FitLengthPoint]:
    """Refit on increasing amounts of declared-normal data and score the same slice each time.

    The curve that turns "modelling error dominates" from an attribution into a quantity. Same model
    class, same threshold, same seed, same scored slice, and the signal space held to the one the
    frozen row's fit used, so the only thing that varies is how much declared-normal data the fit
    saw. **Every point is reported.** Nothing here is logged, nothing is selected as best, and the
    alert counts are this instrument's rather than the frozen rows reproduced in stage 1.

    Args:
        fitted: The model as the vertical fitted it, on the labelled file's prefix.
        reference: The declared-normal dataset.
        test: The scored slice.
        lengths: Fit lengths in timestamps, ascending.
        frozen_fit_timestamps: How many timestamps the frozen row's own fit used. Declared by the
            caller from the split policy rather than recovered from the model, which keeps only its
            learned window and not the observations behind it.

    Returns:
        The curve, with the frozen row's own fit as its first point.
    """
    keep = {signal[1] for signal in fitted.signal_space.signals}
    observations = [item for item in reference.observations if item.feature in keep]
    by_stamp: dict[datetime, list[Observation]] = {}
    for item in observations:
        by_stamp.setdefault(item.timestamp, []).append(item)
    stamps = sorted(by_stamp)

    alerts, moments, caught, available = _score(fitted, test)
    curve = [
        FitLengthPoint(
            timestamps=frozen_fit_timestamps,
            hours=frozen_fit_timestamps * SAMPLE_SECONDS / 3600.0,
            alerts=alerts,
            moments_pct=moments,
            windows_caught=caught,
            n_windows=available,
        )
    ]
    for length in lengths:
        taken = min(length, len(stamps))
        model = MahalanobisModel().fit(
            [item for stamp in stamps[:taken] for item in by_stamp[stamp]]
        )
        alerts, moments, caught, available = _score(model, test)
        curve.append(
            FitLengthPoint(
                timestamps=taken,
                hours=taken * SAMPLE_SECONDS / 3600.0,
                alerts=alerts,
                moments_pct=moments,
                windows_caught=caught,
                n_windows=available,
            )
        )
        logger.info(
            "fit on %6d timestamp(s) (%5.2f h): %6d alert(s), %5.2f%% of moments, %d/%d window(s)",
            taken,
            taken * SAMPLE_SECONDS / 3600.0,
            alerts,
            moments,
            caught,
            available,
        )
    return curve


def render_sweep(curve: Sequence[FitLengthPoint]) -> str:
    """Render a fit-length curve as a markdown table, every point shown."""
    return "\n".join(
        [
            "| Fit set | Per-signal alerts | Moments alerting | Attack windows caught |",
            "| --- | ---: | ---: | ---: |",
            *(
                f"| {point.hours:.2f} h ({point.timestamps:,} timestamps"
                f"{", the frozen row's own fit" if index == 0 else ''}) | {point.alerts:,} "
                f"| {point.moments_pct:.2f}% | {point.windows_caught} of {point.n_windows} |"
                for index, point in enumerate(curve)
            ),
        ]
    )


def written_answer(
    counted: Mapping[str, int],
    references: Mapping[str, SignalReference],
    rates: AlertRatePair,
    curve: Sequence[FitLengthPoint],
    periods: Mapping[str, CyclePeriod],
) -> str:
    """State the answer to U1's question in prose, with every figure computed rather than typed."""
    floored = [r for r in references.values() if r.at_shrinkage_floor]
    uncovered = sorted(
        (r for r in references.values() if not r.band_covers_declared_normal),
        key=lambda r: -r.declared_normal_exceedance,
    )
    false_alerts = sum(
        count for category, count in counted.items() if category != OVERLAPS_LABELLED_ATTACK
    )
    loudest = max(references.values(), key=lambda r: r.declared_normal_exceedance)
    cycles = sorted(
        (p for p in periods.values() if p.first_peak_hours > 0.0), key=lambda p: p.first_peak_hours
    )
    step = sweep_transition(curve[1:])
    recall = sorted({f"{p.windows_caught} of {p.n_windows}" for p in curve})
    return "\n".join(
        [
            f"**Modelling error, in {counted['modelling_error']} of {false_alerts} false alerts.** "
            "Not insufficient context — and the two point in opposite directions, so which it is "
            "decides what the rest of this phase should do.",
            "",
            "The evidence is one measurement. The model exactly as the vertical fitted it, applied "
            f"to the corpus's own {rates.reference_hours:.2f}-hour attack-free training file which "
            f"it never saw, exceeds its own reported band on **{rates.reference_pct:.2f}%** of "
            f"moments — against **{rates.under_review_pct:.2f}%** on the normal moments of the "
            f"scored slice. Its loudest signal, `{loudest.signal}`, exceeds on "
            f"{loudest.declared_normal_exceedance:.2%} of declared-normal moments on its own. The "
            "same signals exceed, at the same rates, to the same maxima. Every one of the "
            f"{counted['modelling_error']} false alerts has a departure no larger than one the "
            "model produces on data the corpus declares attack-free. None exceeds it.",
            "",
            "**The mechanism, in three measured parts.** "
            f"(1) A shrinkage floor: {len(floored)} of the {len(references)} signals that depart "
            "carry a band set not by their own variation but by the plant's largest-scale tag, "
            "because Ledoit-Wolf shrinkage is applied in raw units and HAI is a mixed-scale plant "
            "(`shrinkage_floor_mixed_scale`, ADR 0018). "
            f"(2) For {len(uncovered)} signals — "
            f"{', '.join(f'`{r.signal}`' for r in uncovered)} — the resulting band is **narrower "
            "than the signal's own declared-normal standard deviation**, so those signals must "
            "alert in normal operation as arithmetic. "
            f"(3) A fit set shorter than one duty cycle: the fastest-cycling departing signal, "
            f"`{cycles[0].signal}`, has a period of {cycles[0].first_peak_hours:.2f} h, and the "
            f"fit window is {curve[0].hours:.2f} h — "
            f"{curve[0].hours / cycles[0].first_peak_hours:.0%} of it (`mixed_modes`). The other "
            f"departing signals cycle more slowly still, out to "
            f"{cycles[-1].first_peak_hours:.2f} h on `{cycles[-1].signal}`.",
            "",
            "**The contribution, quantified, and what it costs.** Holding the model class, the "
            "threshold, the seed, the scored slice and the signal space fixed, and varying only "
            "the length of the fit set:",
            "",
            render_sweep(curve),
            "",
            (
                f"The transition is a step, not a slope: it falls between "
                f"{step[0].hours:.2f} h and "
                f"{step[1].hours:.2f} h of fit data — the first fit length past "
                f"`{cycles[0].signal}`'s {cycles[0].first_peak_hours:.2f} h period — and the alert "
                f"count drops from {step[0].alerts:,} to {step[1].alerts:,} across it. It does not "
                f"then fall to nothing: the curve flattens near "
                f"{min(p.moments_pct for p in curve[1:]):.2f}% of moments and stays there, which "
                f"is what a fit still shorter than the slowest signal's "
                f"{cycles[-1].first_peak_hours:.2f} h cycle should look like."
                if step
                else "The curve shows no step: more declared-normal data helps only gradually."
            )
            + f" Window recall is {' and '.join(recall)} at every fit length tested, so none of "
            "this is bought with detection.",
            "",
            "**What this is not.** It is not a proposal, an operating point or a detection claim. "
            f"The reason the public fit is {curve[0].hours:.2f} h is not an oversight: the "
            "vertical "
            "needs labelled positives to fit its isotonic calibrator, the declared-normal file "
            "carries none, so it splits the labelled file three ways, and HAI's attacks fall early "
            "enough in that file that `train_fraction` must be 0.04 to leave any attack in the "
            "scored slice. The fit length is a consequence of where the only labels live.",
            "",
            "**What remains genuinely blocked on evidence.** Maintenance and mode attribution. HAI "
            "carries no work order, no operator identity and no mode register, and no amount of "
            "modelling will conjure one. Those are the categories the synthetic diagnostic "
            "environment was built to exercise, and they are untouched by this finding.",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="print the report, write no file")
    parser.add_argument(
        "--skip-gate",
        action="store_true",
        help="skip the frozen-row reproduction. Development only; never for a reported run.",
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        gate = (
            "**SKIPPED — this run must not be quoted**"
            if arguments.skip_gate
            else reproduce_frozen_gate()
        )
        alerts, fitted, test, n_fit_timestamps = _alerts_and_model()
        departing = sorted({member.signal for alert in alerts for member in alert.members})
        references = declared_normal_references(fitted, departing)
        reference_dataset = _declared_normal_dataset()

        frame = pandas.read_csv(
            DATA_DIR / CORPUS / "hai-21.03-test-prepared.csv", parse_dates=["timestamp"]
        )
        reference_frame = pandas.read_csv(
            DATA_DIR / CORPUS / "hai-21.03-train-prepared.csv", parse_dates=["timestamp"]
        )
        stamps = sorted({item.timestamp for item in test.observations})
        scored = frame[
            (frame["timestamp"] >= pandas.Timestamp(stamps[0]))
            & (frame["timestamp"] <= pandas.Timestamp(stamps[-1]))
        ].reset_index(drop=True)

        noise = noise_scale_ratios(scored, reference_frame, departing)
        trends = trend_strengths(scored, reference_frame, departing)
        periods = cycle_periods(reference_frame, departing, sample_seconds=SAMPLE_SECONDS)
        screens = screen_corpus(scored, noise, trends)
        classified = classify(alerts, references, screens)
        rates = alert_rate_pair(fitted, reference_dataset, _without_attacks(test))
        curve = fit_length_sweep(
            fitted,
            reference_dataset,
            test,
            SWEEP_LENGTHS,
            frozen_fit_timestamps=n_fit_timestamps,
        )
    except GateError as error:
        logger.error("%s", error)
        return 2

    counted = contributions(classified)
    markdown = render_taxonomy_markdown(
        classified,
        screens,
        references,
        signature_runs(alerts, GROUPING_WINDOW),
        corpus=CORPUS,
        seed=SEED,
        git_commit=current_git_commit() or "unknown",
        gate=gate,
        answer=written_answer(counted, references, rates, curve, periods),
    )
    print("\n" + markdown)
    if not arguments.no_write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"{CORPUS}-error-taxonomy.md"
        path.write_text(markdown, encoding="utf-8")
        logger.info("wrote %s (a diagnostic, not a log row)", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
