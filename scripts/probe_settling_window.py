#!/usr/bin/env python3
"""Measure the blind window the settling allowance grants, by attacking inside it on purpose.

ADR 0019 accepts a bounded exposure: within `settling_window` of a phase change, a reading the
*phase being left* explains is not flagged. D2's shipped battery cannot test that claim — every one
of its twenty batch attacks runs 180 to 720 moments and **not one lies wholly inside a settling
window** — so an attack sized to hide in the transient is exactly what the map does not contain.

This is that attack, built here rather than added to D2. It is a measurement instrument, not a new
battery entry: nothing it produces enters the breaking-point map, and it changes no corpus on disk.

**The three probes, and what each is supposed to show.**

* ``hides`` — the exposure itself. The reagent feed is held at zero through the opening of the
  CHARGE phase: a blocked charge, which is a real attack on a batch process, and whose reading is
  *exactly* what the outgoing IDLE phase expects. If the allowance is what ADR 0019 says it is,
  this is invisible while the window lasts.
* ``outlives`` — the same attack held past the window. The exposure is supposed to be bounded in
  time, so this must be caught once the allowance expires. If it were not, the window would be a
  door rather than a delay.
* ``exceeds`` — a feed rate the plant never produces in *either* phase, injected at the same
  instant. The allowance forgives what the outgoing phase explains and nothing else, so this must
  be caught with the allowance on.

Every probe is run twice — allowance off (A-FIX-1's arrangement) and on — so each number is a
difference rather than an assertion.

Usage::

    python scripts/probe_settling_window.py
    python scripts/probe_settling_window.py --window 10
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas import PhaseConditionalModel  # noqa: E402
from phos.atlas.phased import phase_moments  # noqa: E402
from phos.breaking.corpus import CorpusNotFoundError, load_normal_corpus  # noqa: E402
from phos.ontology import Observation  # noqa: E402
from phos.reasoning import is_out_of_band  # noqa: E402

DATA_DIR: Final = REPO_ROOT / "data" / "synth"
TRAIN: Final = DATA_DIR / "synth-batch-reactor-train"
HOLDOUT: Final = DATA_DIR / "synth-batch-reactor-holdout"

PHASE_FEATURE: Final = "batch_phase"
FEED: Final = "reagent_feed_kgph"
IDLE: Final = 0
CHARGE: Final = 1

IDLE_FEED_KGPH: Final = 0.0
"""What the feed reads during IDLE, and therefore what the outgoing phase explains."""

IMPOSSIBLE_FEED_KGPH: Final = 50_000.0
"""A feed rate outside every phase's envelope: roughly nine times the plant's maximum."""

logger = logging.getLogger("phos.probe.settling")


@dataclass(frozen=True)
class Probe:
    """One injected attack and what it is meant to demonstrate.

    Attributes:
        name: Short label used in the report.
        hold: How long after the phase change the falsified value is held.
        value: The feed rate written over the plant's own reading.
        expectation: What ADR 0019 predicts, in words, for the allowance-on run.
    """

    name: str
    hold: timedelta
    value: float
    expectation: str


def falsify(
    observations: Sequence[Observation],
    starts: Sequence[datetime],
    hold: timedelta,
    value: float,
) -> tuple[list[Observation], set[str]]:
    """Overwrite the feed reading for ``hold`` after each phase start in ``starts``.

    Args:
        observations: The attack-free corpus to inject into.
        starts: The instants at which the targeted phase begins.
        hold: How long the falsified value is held after each start.
        value: The feed rate to write.

    Returns:
        ``(corpus, injected_ids)`` — the corpus with the injection applied, and the ids of every
        observation whose value was changed. Detection is judged against those ids alone, so an
        alert elsewhere in the corpus cannot be credited to the probe.
    """
    spans = [(start, start + hold) for start in starts]
    injected: set[str] = set()
    corpus: list[Observation] = []
    for observation in observations:
        hit = observation.feature == FEED and any(
            start <= observation.timestamp < end for start, end in spans
        )
        if hit and observation.value != value:
            corpus.append(observation.model_copy(update={"value": value}))
            injected.add(observation.id)
        else:
            corpus.append(observation)
    return corpus, injected


def caught(corpus: Sequence[Observation], injected: set[str], window: timedelta) -> int:
    """Return how many injected readings Atlas puts out of band with this settling window."""
    fitted = PhaseConditionalModel(phase_feature=PHASE_FEATURE, settling_window=window).fit(
        load_normal_corpus(TRAIN).dataset.observations
    )
    by_id = {observation.id: observation for observation in corpus}
    return sum(
        1
        for deviation in fitted.score(corpus)
        if deviation.observation_id in injected
        and is_out_of_band(deviation, by_id[deviation.observation_id])
    )


def charge_starts(observations: Sequence[Observation]) -> list[datetime]:
    """Every instant at which the CHARGE phase begins from IDLE."""
    moments = phase_moments(observations, PHASE_FEATURE)
    return sorted(
        timestamp
        for timestamp, moment in moments.items()
        if moment.phase == CHARGE and moment.previous == IDLE and moment.started_at == timestamp
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the three probes and print the comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window", type=float, default=10.0, help="settling window in minutes (default: 10)"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    window = timedelta(minutes=args.window)
    try:
        holdout = load_normal_corpus(HOLDOUT)
    except CorpusNotFoundError as error:
        logger.error("%s", error)
        return 1

    observations = holdout.dataset.observations
    starts = charge_starts(observations)
    if not starts:
        logger.error("no IDLE->CHARGE transition in %s; nothing to probe", holdout.name)
        return 1

    probes = (
        Probe(
            "hides",
            window,
            IDLE_FEED_KGPH,
            "invisible while the window lasts — this is the accepted exposure",
        ),
        Probe(
            "outlives",
            window * 3,
            IDLE_FEED_KGPH,
            "caught once the window expires — the exposure is a delay, not a door",
        ),
        Probe(
            "exceeds",
            window,
            IMPOSSIBLE_FEED_KGPH,
            "caught throughout — the allowance forgives only what IDLE explains",
        ),
    )

    print(f"\nprobing {holdout.name}: {len(starts)} IDLE->CHARGE transitions, window {window}\n")
    print(f"{'probe':<10} {'held':>8} {'feed':>9} {'injected':>9} {'off':>6} {'on':>6}  verdict")
    for probe in probes:
        corpus, injected = falsify(observations, starts, probe.hold, probe.value)
        if not injected:
            logger.warning("%s changed nothing; the plant already reads that value", probe.name)
            continue
        off = caught(corpus, injected, timedelta(0))
        on = caught(corpus, injected, window)
        verdict = "HIDDEN by the allowance" if on == 0 < off else f"seen ({on} reading(s))"
        print(
            f"{probe.name:<10} {probe.hold!s:>8} {probe.value:>9.0f} {len(injected):>9} "
            f"{off:>6} {on:>6}  {verdict}"
        )
        print(f"{'':<10} expected: {probe.expectation}")

    print(
        "\nRead this with ADR 0019. The `hides` row IS the blind window, measured rather than\n"
        "argued: inside it an attacker whose falsified reading is plausible for the phase just\n"
        "left is not flagged on that signal. The `outlives` and `exceeds` rows bound it.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
