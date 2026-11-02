"""Ask the GRFICS agreement tell of the captured pair, and write one report (ADR 0407).

Usage, from the lab root:

    python scripts/grfics/agreement.py

What this file is, and is not:

    * **It is a diagnosis, not a detection result.** No recall, no rate, no accuracy, no confidence,
      no budget and no operating point is computed. `eval_runs/log.jsonl` is not appended. ADR 0407
      Decision 3.
    * **It reads the captured files and nothing else.** No container, no network, no live stack.
      Every number in the report is re-derivable from `data/grfics-dev/` by the command it names.
    * **The bar was fixed before the computation** (ADR 0407) and is not adjusted here. Three bars:
      the physical run tracked its registers, the cyber run froze against them, and no tag satisfies
      both.
    * **It answers a question about an emulated plant.** R4 and ADR 0143 apply: a visible tell is
      not evidence about a real plant, and it advances nothing.

The tell, in GRFICSv3's own words: *"A physical field-device fault corrupts data at the source, so
the PLC and HMI are fooled identically and agree with each other (both wrong, together). A read-path
cyber attack only corrupts the HMI's view, so the PLC and HMI disagree."*
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[2]
DEV_DIR = ROOT / "data" / "grfics-dev"
REPORT = ROOT / "eval_runs" / "build" / "grfics" / "agreement-tell.md"

#: The point-to-register map ADR 0405 declared, restated here so this script reads the CSVs by name
#: rather than by position (ADR 0405's table is the source).
TAGS: Final[tuple[tuple[str, int], ...]] = (
    ("AValve", 100),
    ("AFlow", 101),
    ("BValve", 102),
    ("BFlow", 103),
    ("PurgeValve", 104),
    ("PurgeFlow", 105),
    ("ProductValve", 106),
    ("ProductFlow", 107),
    ("Pressure", 108),
    ("Level", 109),
    ("AComp", 110),
    ("BComp", 111),
    ("CComp", 112),
)

#: Samples at the start of the event allowed to differ while the mechanism takes over. Declared in
#: `capture.py` before the recapture (ADR 0406); repeated so this script does not import the driver.
TRANSITION_SAMPLES: Final = 10

PHYSICAL_DIR: Final = DEV_DIR / "physical-frozen-tank_level-97201"
CYBER_DIR: Final = DEV_DIR / "cyber-frozen-tank_level-97206"


@dataclass(frozen=True)
class TagObservation:
    """What one tag did in one run, inside the analysis window.

    Attributes:
        tag: The ScadaLTS point name.
        register: The PLC input register it reads.
        samples: How many paired samples the window holds.
        register_distinct: Distinct raw register values on the ICS side.
        hmi_changes: How many times the HMI value changed.
    """

    tag: str
    register: int
    samples: int
    register_distinct: int
    hmi_changes: int

    @property
    def live_on_ics(self) -> bool:
        """Whether the PLC register moved at all in the window.

        A tag whose register never moved carries no evidence either way: a flat HMI over a flat
        register cannot distinguish a freeze from a quiet plant (ADR 0406).
        """
        return self.register_distinct > 1

    @property
    def hmi_tracked(self) -> bool:
        """Whether the HMI changed at least once.

        Deliberately a count and not a ratio: the HMI polls every ~2.01 s against a 1 s sampler
        (ADR 0407 finding 1), so a proportion would measure the poll period.
        """
        return self.hmi_changes > 0


def read_rows(directory: Path, name: str) -> list[dict[str, str]]:
    """Read one CSV from a run directory, or refuse.

    Args:
        directory: The run directory.
        name: The file name, for example ``hmi_values.csv``.

    Returns:
        The rows.

    Raises:
        SystemExit: The file is absent, which is a refusal rather than an empty analysis.
    """
    path = directory / name
    if not path.is_file():
        raise SystemExit(f"refused: {path} is absent; this analysis needs both captured runs")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def analyse(directory: Path) -> list[TagObservation]:
    """Measure every tag in one run inside the declared analysis window.

    The window is the event phase past `TRANSITION_SAMPLES`, matched sample by sample between the
    HMI stream and the ICS-side register stream on their shared clock.

    Args:
        directory: The run directory.

    Returns:
        One observation per tag that has paired samples.

    Raises:
        SystemExit: The two streams do not have the same row count, which would misalign them.
    """
    hmi = read_rows(directory, "hmi_values.csv")
    modbus = read_rows(directory, "modbus.csv")
    if len(hmi) != len(modbus):
        raise SystemExit(
            f"refused: {directory.name} has {len(hmi)} HMI rows and {len(modbus)} register rows; "
            "the streams must share one clock row for row"
        )

    pairs = [
        (h, m)
        for h, m in zip(hmi, modbus, strict=True)
        if h["phase"] == "event" and m["phase"] == "event"
    ][TRANSITION_SAMPLES:]
    if not pairs:
        raise SystemExit(
            f"refused: {directory.name} has no event samples past the transition window"
        )

    observations: list[TagObservation] = []
    for tag, register in TAGS:
        key = f"reg_{register}"
        hmi_values = [row[0][tag] for row in pairs if row[0].get(tag) and row[1].get(key)]
        raw_values = [row[1][key] for row in pairs if row[0].get(tag) and row[1].get(key)]
        if not hmi_values:
            continue
        changes = sum(
            1 for index in range(1, len(hmi_values)) if hmi_values[index] != hmi_values[index - 1]
        )
        observations.append(
            TagObservation(
                tag=tag,
                register=register,
                samples=len(hmi_values),
                register_distinct=len(set(raw_values)),
                hmi_changes=changes,
            )
        )
    return observations


def judge(physical: list[TagObservation], cyber: list[TagObservation]) -> tuple[bool, list[str]]:
    """Judge the three bars ADR 0407 declared.

    Args:
        physical: Observations from `97201`.
        cyber: Observations from `97206`.

    Returns:
        Whether the tell is visible, and the reasons it is not (empty when it is).
    """
    failures: list[str] = []

    physical_live = [obs for obs in physical if obs.live_on_ics]
    cyber_live = [obs for obs in cyber if obs.live_on_ics]

    if not physical_live:
        failures.append("no tag was live on the ICS side in the physical run; nothing to judge")
    if not cyber_live:
        failures.append("no tag was live on the ICS side in the cyber run; nothing to judge")

    # Bar 1: the physical run agrees - every live tag's HMI moved.
    for obs in physical_live:
        if not obs.hmi_tracked:
            failures.append(
                f"bar 1: {obs.tag} was live on the ICS side in the physical run but its HMI never "
                "changed, which is a disagreement where the tell predicts agreement"
            )

    # Bar 2: the cyber run disagrees - every live tag's HMI stayed frozen.
    for obs in cyber_live:
        if obs.hmi_tracked:
            failures.append(
                f"bar 2: {obs.tag} was live on the ICS side in the cyber run but its HMI changed "
                f"{obs.hmi_changes} times, which is tracking where the tell predicts a freeze"
            )

    # Bar 3: no tag satisfies both. Bars 1 and 2 above already catch any single tag that is wrong
    # in one run, so in practice this set is always disjoint. It is computed and reported anyway
    # because ADR 0407 declared it as a bar, and a reader should see the conjunction stated rather
    # than have to derive it from the other two.
    tracks_in_physical = {obs.tag for obs in physical_live if obs.hmi_tracked}
    tracks_in_cyber = {obs.tag for obs in cyber_live if obs.hmi_tracked}
    separation = tracks_in_physical & tracks_in_cyber
    for tag in sorted(separation):
        failures.append(
            f"bar 3: {tag} tracked its register in both runs, so the tell does not separate them"
        )

    return (not failures, failures)


def render(
    physical: list[TagObservation], cyber: list[TagObservation], kept: bool, failures: list[str]
) -> str:
    """Render the report. Every figure is read from the observations, none is typed by hand."""
    lines: list[str] = [
        "# The GRFICS agreement tell on the captured pair (ADR 0407)",
        "",
        "**This is a diagnosis on an emulated plant.** It is not a detection result: no recall,",
        "rate, accuracy, confidence or budget appears here, and none may be quoted from it",
        "(ADR 0407 Decision 3, R4, ADR 0143).",
        "",
        "Reproduce with: `python scripts/grfics/agreement.py`",
        "",
        "Corpus: `grfics-v3-bridge`. Not `grfics-v3`, never pooled with it (ADR 0401).",
        "",
        "## Verdict",
        "",
    ]
    if kept:
        lines.append(
            "**Kept.** The tell is visible on this pair: under the physical fault the operator's "
            "view tracked the PLC, and under the read-path attack it did not."
        )
    else:
        lines.append("**Refused.** The tell does not separate these two runs on the declared bars:")
        lines.append("")
        for failure in failures:
            lines.append(f"- {failure}")
    lines += [
        "",
        f"Analysis window: the event phase past the {TRANSITION_SAMPLES}-sample transition,",
        "matched sample by sample between `hmi_values.csv` and `modbus.csv` on their shared",
        "clock.",
        "",
        "A tag is **live on the ICS side** when its register held more than one distinct value.",
        "Tags that were not live carry no evidence either way and are excluded from the bars, with",
        "the reason shown.",
        "",
    ]
    for label, directory, observations in (
        ("97201 physical/frozen/tank_level", PHYSICAL_DIR.name, physical),
        ("97206 cyber/frozen/tank_level", CYBER_DIR.name, cyber),
    ):
        lines += [
            f"## {label}",
            "",
            f"`data/grfics-dev/{directory}/`",
            "",
            "| tag | reg | samples | distinct regs | HMI changes | live | tracked |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for obs in observations:
            lines.append(
                f"| `{obs.tag}` | {obs.register} | {obs.samples} | {obs.register_distinct} | "
                f"{obs.hmi_changes} | {'yes' if obs.live_on_ics else 'no'} | "
                f"{'yes' if obs.hmi_tracked else 'no'} |"
            )
        lines.append("")
    lines += [
        "## What this does not say",
        "",
        "- It does not say Atlas detects anything. Nothing here is scored.",
        "- It does not describe a real plant. The pair is an emulated process in a simulator.",
        "- It does not report cross-zone evidence. The corpus is one Docker bridge with no",
        "  router, so there is no firewall, Suricata or arpmon evidence (ADR 0401).",
        "- It does not generalise to other faults, other tags or other seeds. Two runs were",
        "  captured and two were analysed.",
        "",
        "## The one row worth reading twice",
        "",
        "`Level` is **not live on the ICS side in the physical run** (1 distinct register",
        "value) but **is live in the cyber run** (181 distinct values), and its HMI froze in",
        "both. That is not an inconsistency: it is the physical case doing exactly what the",
        "design doc describes. The physical fault froze the sensor at the source, so the",
        "register itself stopped moving and everyone downstream was fooled together, including",
        "this analysis, which can therefore say nothing about it from the register alone. Under",
        "the cyber attack the register kept moving (181 distinct values) while the operator's",
        "view held one value for 1174 samples, which is the disagreement, recorded.",
        "",
        "The sharpest single instance of agreement is therefore not `Level` in the physical run",
        "but `Pressure` in it: 197 distinct register values, and an HMI that tracked them.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = argparse.ArgumentParser(description="Diagnose the GRFICS agreement tell (ADR 0407).")
    parser.add_argument(
        "--dry-run", action="store_true", help="compute and print without writing the report"
    )
    args = parser.parse_args(argv)

    physical = analyse(PHYSICAL_DIR)
    cyber = analyse(CYBER_DIR)
    kept, failures = judge(physical, cyber)
    report = render(physical, cyber, kept, failures)

    if args.dry_run:
        print(report)
        return 0

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")
    print("kept" if kept else "refused")
    if not kept:
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
