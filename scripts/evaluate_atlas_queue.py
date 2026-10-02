#!/usr/bin/env python3
"""Rank the Atlas subsystem-event queue and score it at an operator's alert budget.

The vertical already answers "how many false positives per normal hour". On HAI that is 53.26,
and it describes an experience nobody has measured: the same run leaves **424 subsystem events
covering 7.89 normal hours, of which 4 are true**. That is one shift's queue, in time order, and
an operator working it front to back reads 424 things to find 4.

This script asks the question the rate cannot. It re-runs the vertical on the same split with the
same seed, so the queue is the *same* alert set the frozen row was measured on, then ranks it and
reports recall and precision at a budget an operator could actually work. It is the Atlas twin of
Session S4's CERT curve.

**It never appends to `eval_runs/log.jsonl`.** `atlas-vertical:...` rows are frozen public names;
a ranked re-count of that alert set is a diagnostic, and it lands in `eval_runs/atlas/` under
`atlas-queue:<key>` instead. Nothing here refits a model, searches a threshold, or touches
``_shrink``, ``joint_k``, ``dwell_samples`` or ``templates.py``.

**Three keys are scored because the honest answer may be that none of them rank.** A calibrated
weight tops out at 0.034 across four isotonic knots; a breadth on a coarse map is a small integer.
Both are expected to tie, and a cut that falls inside a tie block is struck rather than quoted.

Usage::

    PYTHONPATH=src python scripts/evaluate_atlas_queue.py
    PYTHONPATH=src python scripts/evaluate_atlas_queue.py hai --no-write
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_atlas_vertical import (  # noqa: E402
    SEED,
    adapter,
    discover,
    magnitudes_of,
    split_evidence,
)

from phos.atlas import (  # noqa: E402
    RANKING_KEYS,
    AtlasEngine,
    MahalanobisModel,
    QueuedAlert,
    load_topology,
    member_evidence_ids,
    queue_curve,
    render_queue_markdown,
    windows_overlapped,
)
from phos.eval.report import current_git_commit  # noqa: E402
from phos.reasoning import (  # noqa: E402
    CalibrationSplitPolicy,
    DegenerateSplitError,
    IsotonicCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

logger = logging.getLogger("phos.atlas.queue")

DATA_DIR: Final = REPO_ROOT / "data"
OUTPUT_DIR: Final = REPO_ROOT / "eval_runs" / "atlas"

#: Copied from `scripts/evaluate_atlas_vertical.py` so the queue is the same alert set the frozen
#: 53.26 row was measured on. If these drift, the two reports stop describing one run.
DEFAULT_THREE_WAY: Final = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)
THREE_WAY_POLICIES: Final[dict[str, CalibrationSplitPolicy]] = {
    "hai": CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30),
}

#: Budgets an operator might plausibly work over a shift-length slice, plus the full queue so the
#: curve's right-hand end is the number the vertical already reports. 48 is deliberately CERT 6B's
#: budget, so the two engines can be read on one axis.
DEFAULT_BUDGETS: Final[tuple[int, ...]] = (6, 12, 24, 48, 96, 192)


def queue_for(name: str) -> tuple[list[QueuedAlert], int] | None:
    """Run the vertical on one corpus and return its queue plus the attack-window count.

    Returns:
        ``(alerts, n_windows)``, or ``None`` when the corpus cannot be split or calibrated —
        the same refusals the vertical makes, for the same reasons.
    """
    manifest = dict(dict(discover([name]))[name])
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
    engine.run(test)

    per_signal, events = split_evidence(engine)
    magnitude, _ = magnitudes_of(engine, per_signal, events)
    members = {item.id: item for item in per_signal}

    alerts = [
        QueuedAlert(
            evidence_id=event.id,
            timestamp=event.timestamp,
            magnitude=magnitude[event.id],
            weight=event.weight,
            breadth=len(event.entity_ids),
            covers_windows=windows_overlapped(
                [members[member].timestamp for member in member_evidence_ids(event)],
                test.attack_intervals,
            ),
        )
        for event in events
    ]
    logger.info(
        "%s: %d subsystem event(s), %d true, over %d attack window(s)",
        name,
        len(alerts),
        sum(1 for alert in alerts if alert.is_true_positive),
        len(test.attack_intervals),
    )
    return alerts, len(test.attack_intervals)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="dataset names; default is every one found")
    parser.add_argument(
        "--budget",
        type=int,
        action="append",
        dest="budgets",
        help="an operator alert budget; repeatable. Defaults to a shift-shaped sweep.",
    )
    parser.add_argument(
        "--no-write", action="store_true", help="print the report and write no file"
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpora = discover(arguments.names)
    if not corpora:
        logger.error("no corpus with both data and a declared topology")
        return 2

    written = 0
    for name, _ in corpora:
        built = queue_for(name)
        if built is None:
            continue
        alerts, n_windows = built
        budgets = tuple(arguments.budgets or DEFAULT_BUDGETS)
        # The full queue is always the right-hand end, so the curve reaches the number the
        # vertical already logged rather than stopping somewhere flattering.
        budgets = tuple(sorted({*budgets, len(alerts)}))
        curves = [queue_curve(alerts, budgets, key, n_windows) for key in RANKING_KEYS]
        markdown = render_queue_markdown(
            curves, corpus=name, seed=SEED, git_commit=current_git_commit()
        )
        print("\n" + markdown)
        if not arguments.no_write:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            path = OUTPUT_DIR / f"{name}-operator-queue.md"
            path.write_text(markdown, encoding="utf-8")
            logger.info("wrote %s (a diagnostic, not a log row)", path)
        written += 1

    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
