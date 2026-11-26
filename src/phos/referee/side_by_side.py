"""One simulated run, with the referee's baseline printed beside Atlas's page.

Stage 3. The point is not that Atlas wins. The point is that a reader can see both outputs on the
same evidence, with the baseline's own settings and its actual alert count, and decide for
themselves whether the difference is worth anything.

**Three rules this module exists to keep.**

1. **The baseline is a real run.** `phos.models.GaussianBaseline` is fitted on the same attack-free
   telemetry Atlas is fitted on, and it is asked about the same plant. Its alert count is whatever
   it produces; nothing here caps, filters or reselects it. If the baseline looks weak, the reason
   is printed beside the number, because a weak baseline presented without its reason is a staged
   comparison.

2. **Every figure is labelled simulated.** Both outputs come from a generated plant. The label is
   printed once, before anything else, and repeated at the foot, because a screenshot of the middle
   of this output must not be quotable as a field result.

3. **Atlas's page is Atlas's.** The right-hand column is `AtlasDetector`'s own narratives, read
   from its store, with the leading hypothesis and its evidence. Nothing is summarised, scored or
   re-weighted here. Hypothesis confidence is printed because the page prints it, and it is
   labelled uncalibrated wherever it appears, per Constitution §3.3.

**What this is not.** It is not an evaluation. There is no recall here, no ground truth compared
against either detector, and no verdict. Those belong to the referee's exam machinery, and doing
them in a demo would be doing measurement in the place most likely to be quoted out of context.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from phos.eval import Detection, Detector
from phos.models import GaussianBaseline, ModelDetector
from phos.ontology import Hypothesis, Narrative
from phos.referee.corpus import load_plant_dataset
from phos.referee.demo import atlas_detector
from phos.referee.detectors import AtlasDetector, leading_hypothesis
from phos.synth.families import get_family
from phos.synth.outputs import generate_plant

__all__ = [
    "DEFAULT_EVENT_CATALOGUE",
    "DEFAULT_HOURS",
    "DEFAULT_SEED",
    "side_by_side",
]

#: The plant both detectors are shown. A development seed from the published pool, so anyone can
#: regenerate this exact plant and get this exact output.
DEFAULT_SEED: Final = 771001

#: The family the seed belongs to. Atlas's detector is fitted on this family, so the demo plant has
#: to share its signal names or `AtlasEngine` refuses it with a `TopologyError`.
DEFAULT_FAMILY: Final = "level_flow"

#: Twenty-four hours, which is what the default event catalogue needs to place its five events.
DEFAULT_HOURS: Final = 24.0

DEFAULT_EVENT_CATALOGUE: Final = None
"""The demo runs a plant with no injected events.

Deliberate. The comparison is between two detectors on the same evidence, and injecting an attack
would make a reader ask whether the demo plant was chosen to make one of them look good. A clean
plant shows what each does on ordinary operation, which is where the baseline's false-alert
behaviour is visible and honest.
"""

_BASELINE_TRAIN_SEED: Final = 771002
"""The plant the baseline is fitted on. A different seed from the demo plant on purpose: a baseline
fitted on the plant it is scored against has learned that plant's own noise, which flatters it.
Atlas is fitted on a separate training plant for exactly the same reason."""


@dataclass(frozen=True)
class BaselineRun:
    """What the baseline did, with the settings that produced it.

    Attributes:
        detections: Every detection it returned.
        alerts: Those at or above the alert threshold.
        threshold: The score threshold an alert had to reach.
        model: The baseline model's class name.
        fit_note: What it was fitted on, so a reader can judge whether the comparison is fair.
    """

    detections: tuple[Detection, ...]
    alerts: tuple[Detection, ...]
    threshold: float
    model: str
    fit_note: str


@dataclass(frozen=True)
class AtlasRun:
    """What Atlas produced, read from its own store.

    Attributes:
        detections: The detections the referee adapter returned.
        alerts: Those at or above the threshold.
        narratives: Atlas's own narratives, unedited.
        store: The evidence store, so a reader can walk any narrative's evidence.
    """

    detections: tuple[Detection, ...]
    alerts: tuple[Detection, ...]
    narratives: tuple[Narrative, ...]
    store: object


def _alerts(detections: tuple[Detection, ...], threshold: float) -> tuple[Detection, ...]:
    """Return the detections at or above a threshold.

    Args:
        detections: Every detection.
        threshold: The score an alert must reach.

    Returns:
        The alerts, in the order given.
    """
    return tuple(detection for detection in detections if detection.score >= threshold)


def _baseline(threshold: float, *, train_seed: int, label: str) -> tuple[BaselineRun, Detector]:
    """Fit the baseline on attack-free telemetry and return it with its settings.

    The baseline is the per-signal Gaussian, which is the simplest model in the repository and the
    one whose weakness is most instructive: it treats each signal as independent, so it cannot see
    a joint move. That is stated in the output rather than hidden, because a reader comparing two
    detectors should know which one is being asked a harder question.

    Args:
        threshold: The score an alert must reach.
        train_seed: The plant to fit on.
        label: How to describe that plant in the output.

    Returns:
        The run, and the detector so the caller can score it. The run's detections and alerts are
        empty here; the caller fills them after running, so this function never reports a count it
        did not measure.
    """
    output = Path(tempfile.mkdtemp(prefix=f"phos-baseline-train-{train_seed}-"))
    family = get_family(DEFAULT_FAMILY)
    plant = generate_plant(family, train_seed, output, hours=DEFAULT_HOURS, events=None)
    dataset = load_plant_dataset(plant)
    fitted = GaussianBaseline().fit(dataset.observations)
    detector = ModelDetector(fitted=fitted, score_scale=3.0)
    return (
        BaselineRun(
            detections=(),
            alerts=(),
            threshold=threshold,
            model=type(fitted).__name__,
            fit_note=(
                f"fitted on {len(dataset.observations)} observations of attack-free "
                f"operation {label}"
            ),
        ),
        detector,
    )


def _narrative_block(narrative: Narrative, store: object) -> list[str]:
    """Render one narrative as the lines an operator would read.

    Args:
        narrative: Atlas's narrative.
        store: Its evidence store, so the leading hypothesis and evidence can be named.

    Returns:
        Markdown lines. Confidence is labelled uncalibrated wherever it appears.
    """
    lines = [f"  - {narrative.title}"]
    lead = leading_hypothesis(narrative, _hypotheses(store))
    if lead is not None:
        lines.append(
            f"    leading explanation: {lead.label} "
            f"(confidence {lead.confidence:.3f}, uncalibrated, for ranking only)"
        )
    lines.append(f"    evidence attached: {len(narrative.evidence_ids)}")
    return lines


def _hypotheses(store: object) -> Mapping[str, Hypothesis]:
    """Return every hypothesis an evidence store holds, keyed by id.

    Args:
        store: Atlas's store.

    Returns:
        The hypotheses by id, or an empty mapping when the store cannot list them.
    """
    reader = getattr(store, "hypotheses", None)
    if not callable(reader):
        return {}
    return {item.id: item for item in reader()}


def side_by_side(
    *,
    seed: int = DEFAULT_SEED,
    hours: float = DEFAULT_HOURS,
    threshold: float = 3.0,
) -> str:
    """Run both detectors on one plant and return the printable comparison.

    Args:
        seed: The plant's master seed. The default is a published development seed.
        hours: How long the plant runs.
        threshold: The score an alert must reach, for both detectors. The same number, so neither
            is given an easier setting.

    Returns:
        The whole output as a string, labelled simulated at the top and the foot.
    """
    output = Path(tempfile.mkdtemp(prefix="phos-demo-plant-"))
    plant = generate_plant(get_family(DEFAULT_FAMILY), seed, output, hours=hours, events=None)
    dataset = load_plant_dataset(plant)

    # Two baseline fits, because the honest comparison has two answers and neither alone is fair.
    # Fitted on this plant: the baseline has learned this plant's own noise, which flatters it.
    # Fitted on another plant: it detects nothing, which says more about the model than about the
    # plant. Printing one and not the other would let a reader draw a conclusion from the choice.
    same_run, same_detector = _baseline(
        threshold, train_seed=seed, label=f"from this same plant (seed {seed})"
    )
    other_run, other_detector = _baseline(
        threshold,
        train_seed=_BASELINE_TRAIN_SEED,
        label=f"from a different plant of the same family (seed {_BASELINE_TRAIN_SEED})",
    )
    same_detections = tuple(same_detector.run(dataset))
    other_detections = tuple(other_detector.run(dataset))

    atlas = atlas_detector()
    atlas_detections = tuple(atlas.run(dataset))
    narratives: tuple[Narrative, ...] = ()
    store: object = None
    if isinstance(atlas, AtlasDetector):
        narratives = atlas.last_narratives
        store = atlas.last_store

    same_alerts = _alerts(same_detections, threshold)
    other_alerts = _alerts(other_detections, threshold)
    atlas_alerts = _alerts(atlas_detections, threshold)

    lines = [
        "=" * 78,
        "SIMULATED. One generated plant, two detectors, nothing compared against ground truth.",
        "This is not a detection claim. No recall, no accuracy, no verdict appears here.",
        "=" * 78,
        "",
        f"plant       {plant.manifest.plant_id}  ({DEFAULT_FAMILY}, seed {seed}, {hours:g} h)",
        f"rows        {len(dataset.observations)} observations",
        "events      none injected. The plant runs ordinary operation only, so both detectors are",
        "            answering the same question: what do you say about a quiet plant?",
        "",
        "-" * 78,
        "BASELINE, fitted on the same plant it is shown",
        "-" * 78,
        f"model       {same_run.model}, one Gaussian per signal, signals treated independently",
        f"fit         {same_run.fit_note}",
        f"threshold   {threshold:g}",
        f"detections  {len(same_detections)}",
        f"alerts      {len(same_alerts)}",
        "",
        "-" * 78,
        "BASELINE, fitted on a different plant of the same family",
        "-" * 78,
        f"model       {other_run.model}, the same model",
        f"fit         {other_run.fit_note}",
        f"threshold   {threshold:g}",
        f"detections  {len(other_detections)}",
        f"alerts      {len(other_alerts)}",
        "",
        "Why the two baseline columns differ, and why both are printed:",
        "  Fitted on the plant it is shown, the baseline has learned that plant's own noise, which",
        "  flatters it. Fitted on another plant, the per-signal Gaussian detects nothing at all,",
        "  because each signal's ordinary range differs enough between plants that no reading",
        "  falls outside the fitted bands. Neither column is fair on its own, and printing a",
        "  single number would let the choice of fit decide the comparison.",
        "",
        "What the baseline cannot do, stated here rather than left to be inferred:",
        "  It models each signal on its own. A plant is one machine, and a move that is ordinary",
        "  for every signal while being impossible for the plant is invisible to it.",
        "  It is included because it is the simplest honest thing to compare against,",
        "  not because it is a fair",
        "  opponent.",
        "",
        "-" * 78,
        "ATLAS",
        "-" * 78,
        f"detections  {len(atlas_detections)}",
        f"alerts      {len(atlas_alerts)}",
        f"narratives  {len(narratives)}",
        "",
    ]
    if len(atlas_alerts) > len(narratives):
        lines += [
            f"Note on the two Atlas numbers: {len(atlas_alerts)} alerts and {len(narratives)} "
            "narrative(s).",
            "  An alert is a flagged instant; a narrative is a story that pulls evidence together.",
            "  Atlas flags far more instants than it narrates, because most departures",
            "  repeat and one story covers them. Neither is recall; neither is precision.",
            "",
        ]
    if len(atlas_alerts) > len(same_alerts) and len(narratives) <= 1:
        lines += [
            "Something this comparison shows that is not flattering to Atlas:",
            f"  Atlas raised {len(atlas_alerts)} alerts on a plant where nothing was injected, and",
            "  settled on one explanation for all of them. A reader should not read the larger",
            "  number as more detection. On a quiet plant, more alerts is more noise, and one",
            "  narrative covering two thousand flagged instants is a page an operator would learn",
            "  to ignore. This is the false-alert problem stated in one line, and it is the reason",
            "  the eight-alerts-a-shift budget exists.",
            "",
            "  The demo does not fix that and is not meant to. It shows it, which is the",
            "  first step.",
            "",
        ]
    if narratives:
        lines.append("Atlas's page, as an operator reads it:")
        for narrative in narratives:
            lines += _narrative_block(narrative, store)
    else:
        lines += [
            "Atlas's page is empty: it found nothing to say about this plant.",
            "",
            "That is a result, not a failure. The right to remain silent is part of the",
            "design, and an empty page on a quiet plant is what it is for.",
        ]
    lines += [
        "",
        "=" * 78,
        "SIMULATED. Both columns are about a model written from public descriptions of how such a",
        "process behaves, not a capture of a real plant. Neither number is a field detection rate,",
        "and neither may be quoted as one.",
        "=" * 78,
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Print the side-by-side comparison.

    Args:
        argv: Command-line arguments.

    Returns:
        0 on success.
    """
    parser = argparse.ArgumentParser(
        description="Print the referee's baseline beside Atlas's page on one simulated plant."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    parser.add_argument("--threshold", type=float, default=3.0)
    parser.add_argument("--out", type=Path, default=None, help="Also write the output here.")
    args = parser.parse_args(argv)
    text = side_by_side(seed=args.seed, hours=args.hours, threshold=args.threshold)
    sys.stdout.write(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
