#!/usr/bin/env python3
"""Measure what grouping is worth to an operator, honestly, and log the answer with its caveats.

This is the reproducible proof behind PART 5C. It runs the whole Atlas vertical — joint model,
evidence boundary, calibrator, subsystem grouping, OT templates, reasoning — on each corpus that
has a declared topology, and reports the same alert set counted two ways:

* **per-signal evidence** — one alert per out-of-band, calibrated departure. This is what Atlas
  hands an operator without grouping.
* **subsystem events** — the same departures, collapsed by physical unit and time window.

Both rows come from one run over one test slice, so the difference between them is the counting and
nothing else. A row for PART 5A's own protocol is printed alongside, and for Atlas's joint models
it is the *same* alert set: a magnitude is a departure measured in band widths, so
``magnitude >= band_k`` and "outside the reported band" pick out the same alerts whenever the
harness threshold equals ``band_k``, which at 3.0 it does. The before row is therefore literally
5A's logged number rather than a near neighbour of it.

**Three things this script refuses to let a reader assume.** Recall is measured at the grouped
level rather than carried over, and measured by *overlap* — a subsystem event covers an attack
window when any of its members fell inside it — because a group stamped at its earliest member
would otherwise look like it had missed an incident it plainly caught. The reduction is reported as
a counting change and never as a detection improvement. And every caveat in
`phos.atlas.ATLAS_VERTICAL_CAVEATS` is printed beside the numbers and written into the logged
report, so a reader of ``eval_runs/log.jsonl`` gets them too.

Nothing here lets a model or a calibrator score data it was fitted on.

Usage::

    python scripts/evaluate_atlas_vertical.py
    python scripts/evaluate_atlas_vertical.py hai
    python scripts/evaluate_atlas_vertical.py --no-log      # print the tables, write nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas import (  # noqa: E402
    ATLAS_VERTICAL_CAVEATS,
    AtlasEngine,
    MahalanobisModel,
    annotate_with_caveats,
    is_subsystem_event,
    load_topology,
    member_evidence_ids,
)
from phos.eval import (  # noqa: E402
    Dataset,
    Detection,
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    LabelledInterval,
    append_to_experiment_log,
    evaluate,
)
from phos.models import ModelDetector  # noqa: E402
from phos.ontology import Domain, Evidence  # noqa: E402
from phos.reasoning import (  # noqa: E402
    CalibrationSplitPolicy,
    DegenerateSplitError,
    IsotonicCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

DATA_DIR: Final = REPO_ROOT / "data"

#: Matches `scripts/evaluate_atlas.py` exactly, so the 5A context row is the number 5A logged.
ALERT_THRESHOLD: Final = 3.0
SEED: Final = 11
DEFAULT_THREE_WAY: Final = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)

#: HAI's attacks all fall in the first half of its test file, so the default fractions leave a test
#: slice with nothing to be right about. Copied from `scripts/calibrate_corpora.py`.
THREE_WAY_POLICIES: Final[dict[str, CalibrationSplitPolicy]] = {
    "hai": CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30),
}

logger = logging.getLogger("phos.atlas.vertical")


class PrecomputedDetector(BaseModel):
    """Adapts an already-computed alert set to the PART 2 `Detector` protocol.

    A measurement adapter, not a detector: the vertical produced these alerts already, and this
    exists only so the same harness scores them as it scores everything else. Reusing `evaluate`
    is the point — a false-positive rate computed here means exactly what it means everywhere.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    detections: tuple[Detection, ...]

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return the precomputed detections, ignoring ``dataset``."""
        logger.debug(
            "%s replaying %d detection(s) for %s", self.name, len(self.detections), dataset.name
        )
        return list(self.detections)


def adapter(config: Mapping[str, Any]) -> LabelledCsvAdapter:
    """Build an adapter from a manifest block, resolving its path against ``data/``."""
    fields = {
        key: value
        for key, value in config.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    return LabelledCsvAdapter.model_validate({**fields, "path": str(DATA_DIR / config["path"])})


def discover(names: Sequence[str]) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(dataset_name, manifest)`` for every corpus that has both a CSV and a topology.

    A corpus without a declared topology is skipped rather than grouped by some other rule: 5B's
    standing policy is that membership is declared, never inferred, and inventing one here would
    be exactly the circularity that policy exists to prevent.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for manifest_path in sorted(DATA_DIR.glob("*/manifest.json")):
        name = manifest_path.parent.name
        if names and name not in names:
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not (DATA_DIR / manifest["path"]).is_file():
            logger.warning("%s: manifest present but %s is not", name, manifest["path"])
            continue
        if not (manifest_path.parent / "topology.toml").is_file():
            logger.warning("%s: no topology.toml, so there is no declared map to group by", name)
            continue
        found.append((name, manifest))
    return found


def detections_from(
    events: Sequence[Evidence],
    magnitudes: Mapping[str, float],
    signals: Mapping[str, Sequence[str]],
) -> tuple[Detection, ...]:
    """Turn evidence into harness detections, scored by the raw magnitude behind them.

    ``score`` stays the model's own magnitude so the numbers are in the same units PART 5A reported
    and the threshold sweep still means something; ``confidence`` is the calibrated weight.
    """
    return tuple(
        Detection(
            timestamp=event.timestamp,
            score=magnitudes[event.id],
            confidence=event.weight,
            entity_ids=list(event.entity_ids),
            feature=", ".join(signals[event.id]),
        )
        for event in events
    )


def windows_covered(
    evidence: Sequence[Evidence],
    members: Mapping[str, Evidence],
    intervals: Sequence[LabelledInterval],
) -> set[int]:
    """Return the indices of the attack windows a set of evidence overlaps.

    Overlap rather than the alert's own timestamp, because a subsystem event stands for the span
    from its earliest member to its latest and is stamped at the earliest — so an event that began
    in normal time and continued into an attack has plainly caught that attack, and counting only
    its stamp would report a miss that did not happen. Per-signal evidence covers one instant, so
    for it the two readings coincide; running both sides through the same function is what makes
    the before/after comparable.
    """
    covered: set[int] = set()
    for item in evidence:
        stamps = (
            [members[member].timestamp for member in member_evidence_ids(item)]
            if is_subsystem_event(item)
            else [item.timestamp]
        )
        for index, interval in enumerate(intervals):
            if any(interval.contains(stamp) for stamp in stamps):
                covered.add(index)
    return covered


def split_evidence(engine: AtlasEngine) -> tuple[list[Evidence], list[Evidence]]:
    """Return ``(per-signal evidence, subsystem events)`` from a completed run, in stored order."""
    stored = engine.store.evidence(Domain.ATLAS)
    return (
        [item for item in stored if not is_subsystem_event(item)],
        [item for item in stored if is_subsystem_event(item)],
    )


def magnitudes_of(
    engine: AtlasEngine, per_signal: Sequence[Evidence], events: Sequence[Evidence]
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Return each piece of evidence's raw magnitude and the signals it concerns.

    Both are recovered by walking the traceability path rather than being carried alongside it, so
    the numbers in this report and the drill-down an operator would perform read the same objects.
    """
    magnitude: dict[str, float] = {}
    signals: dict[str, list[str]] = {}
    for item in per_signal:
        deviation = engine.store.get_deviation(item.source_id)
        if deviation is None:  # pragma: no cover — the store refuses a dangling reference on write
            raise RuntimeError(f"evidence {item.id} has no deviation in the store")
        magnitude[item.id] = deviation.magnitude
        signals[item.id] = [deviation.expected.feature]
    for event in events:
        members = member_evidence_ids(event)
        magnitude[event.id] = max(magnitude[member] for member in members)
        signals[event.id] = list(event.entity_ids)
    return magnitude, signals


class VerticalResult(BaseModel):
    """One corpus's before/after, and the recall check that keeps it honest."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    corpus: str
    reports: tuple[EvaluationReport, ...]
    n_per_signal: int
    n_events: int
    n_narratives: int
    windows_before: int
    windows_after: int
    n_windows: int


def run_corpus(name: str, manifest: Mapping[str, Any]) -> VerticalResult | None:
    """Fit, calibrate and run the vertical on one corpus; return its measured before/after."""
    loaded = adapter(manifest).load()
    policy = THREE_WAY_POLICIES.get(name, DEFAULT_THREE_WAY)
    try:
        train, calib, test = train_calib_test_split(loaded, policy)
    except DegenerateSplitError as error:
        logger.warning("%s: %s", name, error)
        return None

    fitted = MahalanobisModel().fit(train.observations)
    scores, labels = scores_and_labels_from(fitted, calib)
    try:
        calibrator = IsotonicCalibrator(seed=SEED).fit(scores, labels)
    except ValueError as error:
        logger.warning("%s: could not fit a calibrator: %s", name, error)
        return None

    topology = load_topology(
        DATA_DIR / name / "topology.toml",
        {observation.feature for observation in loaded.observations},
        corpus=name,
    )
    engine = AtlasEngine(fitted=fitted, calibrator=calibrator, subsystem_map=topology)
    narratives = engine.run(test)

    per_signal, events = split_evidence(engine)
    magnitude, signals = magnitudes_of(engine, per_signal, events)
    members = {item.id: item for item in per_signal}

    config = EvalConfig(alert_threshold=0.0, seed=SEED)
    reports = (
        _named(
            evaluate(
                ModelDetector(fitted=fitted),
                test,
                EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED),
            ),
            f"{name}[5A context]",
        ),
        _named(
            evaluate(
                PrecomputedDetector(
                    name=f"{engine.name}/per-signal-evidence",
                    detections=detections_from(per_signal, magnitude, signals),
                ),
                test,
                config,
            ),
            f"{name}[before]",
        ),
        _named(
            evaluate(
                PrecomputedDetector(
                    name=f"{engine.name}/subsystem-events",
                    detections=detections_from(events, magnitude, signals),
                ),
                test,
                config,
            ),
            f"{name}[after]",
        ),
    )
    return VerticalResult(
        corpus=name,
        reports=tuple(annotate_with_caveats(report) for report in reports),
        n_per_signal=len(per_signal),
        n_events=len(events),
        n_narratives=len(narratives),
        windows_before=len(windows_covered(per_signal, members, test.attack_intervals)),
        windows_after=len(windows_covered(events, members, test.attack_intervals)),
        n_windows=len(test.attack_intervals),
    )


def _named(report: EvaluationReport, label: str) -> EvaluationReport:
    """Stamp which corpus and which counting unit a report describes."""
    return report.model_copy(update={"dataset_name": label})


def render(results: Sequence[VerticalResult]) -> str:
    """Render every report as a markdown table, in the shape PROGRESS.md uses."""
    header = (
        "| Corpus | Counted as | Alerts | Recall | FPs | FP/normal-hr | Precision | ECE |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = [
        f"| `{report.dataset_name}` | `{report.detector_name}` | {report.n_alerts:,} "
        f"| {report.window_recall:.2f} | {report.false_positives:,} "
        f"| {report.false_positive_rate:.2f} | {report.precision:.4f} "
        f"| {report.expected_calibration_error:.4f} |"
        for result in results
        for report in result.reports
    ]
    return "\n".join([header, *rows])


def summarise(results: Sequence[VerticalResult]) -> str:
    """State the before/after per corpus as a counting change, with the recall check beside it."""
    lines: list[str] = []
    for result in results:
        before, after = result.reports[1], result.reports[2]
        factor = result.n_per_signal / result.n_events if result.n_events else float("inf")
        lines.append(
            f"{result.corpus}: {result.n_per_signal:,} per-signal alerts -> {result.n_events:,} "
            f"subsystem events ({factor:.1f}x fewer things to investigate), "
            f"{result.n_narratives:,} narrative(s)"
        )
        lines.append(
            f"  counting only: FP/normal-hr {before.false_positive_rate:.2f} -> "
            f"{after.false_positive_rate:.2f}. The detector did not change — the same departures "
            f"are being counted per unit instead of per signal."
        )
        lines.append(
            f"  attack windows covered: {result.windows_before}/{result.n_windows} before "
            f"grouping, {result.windows_after}/{result.n_windows} after (overlap-aware); "
            f"harness window recall {before.window_recall:.2f} -> {after.window_recall:.2f}"
        )
    return "\n".join(lines) or "nothing to compare"


def caveats() -> str:
    """Render the caveats that must be read with every number above."""
    return "\n".join(
        ["Read every number above with these:", *(f"  - {c}" for c in ATLAS_VERTICAL_CAVEATS)]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="dataset names; default is every one found")
    parser.add_argument("--no-log", action="store_true", help="do not append to the experiment log")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpora = discover(arguments.names)
    if not corpora:
        logger.error(
            "no corpus with both data and a declared topology; run scripts/fetch_datasets.py --all"
        )
        return 2

    results: list[VerticalResult] = []
    for name, manifest in corpora:
        result = run_corpus(name, manifest)
        if result is None:
            continue
        results.append(result)
        if not arguments.no_log:
            for report in result.reports:
                append_to_experiment_log(report)

    if not results:
        logger.error("no corpus yielded a usable split")
        return 1

    print("\n" + render(results))
    print("\n" + summarise(results))
    print("\n" + caveats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
