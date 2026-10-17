"""The October 2026 build, declared before any new file is opened (ADR 0144).

Development seeds and a held-back batch for the synthetic plants, the file split
for each newly registered corpus, the GRFICSv3 runs, and the scorecard the
lanes report against. This module does not generate a plant, does not download
a file, and does not write ``eval_runs/log.jsonl``.
"""

from __future__ import annotations

from typing import Final, NamedTuple

__all__ = [
    "BUILD_DEVELOPMENT_SEEDS",
    "BUILD_HELD_BACK_SEEDS",
    "DECLARED_HELD_OUT",
    "FOUR_SICS_DEVELOPMENT_FILES",
    "FOUR_SICS_HELD_BACK_FILES",
    "GRFICS_COMMIT",
    "GRFICS_DEVELOPMENT_RUNS",
    "GRFICS_HELD_BACK_RUNS",
    "GRFICS_LICENSE_SHA256",
    "KELMARSH_DEVELOPMENT_FILES",
    "KELMARSH_HELD_BACK_FILES",
    "KELMARSH_RECORD",
    "PENMANSHIEL_DEVELOPMENT_FILES",
    "PENMANSHIEL_HELD_BACK_FILES",
    "PENMANSHIEL_RECORD",
    "SCORECARD",
    "GrficsRun",
    "build_seed_blocks",
    "registry_file_halves",
]

#: Synthetic-plant seeds the October build may iterate on. Disjoint from every
#: used set, including T1's 94001-94020.
BUILD_DEVELOPMENT_SEEDS: Final[tuple[int, ...]] = tuple(range(97001, 97021))
#: Synthetic-plant seeds scored once, after a committed declaration, and not before.
BUILD_HELD_BACK_SEEDS: Final[tuple[int, ...]] = tuple(range(97101, 97121))

#: What a lane's report has to carry. Names only: no number is filled in here.
SCORECARD: Final[tuple[str, ...]] = (
    "catches_within_budget",
    "margin_over_best_simple_rival",
    "margin_over_chance",
    "falsified_sensor_passes",
    "naming_right",
    "naming_wrong",
    "reconstruction_error",
    "maintenance_closures",
    "calibration",
    "false_alerts_per_shift",
    "runtime",
)

#: Zenodo record 16807551, version DOI 10.5281/zenodo.16807551, not the concept DOI.
KELMARSH_RECORD: Final = "16807551"
#: Zenodo record 16807304, version DOI 10.5281/zenodo.16807304, not the concept DOI.
PENMANSHIEL_RECORD: Final = "16807304"

#: Year files 2016-2022, plus the static sheet, the signal map and the site kmz.
#: Each SCADA zip mixes all six turbines, so the holdout is the later years.
KELMARSH_DEVELOPMENT_FILES: Final[tuple[str, ...]] = (
    "Kelmarsh_SCADA_2016_3082.zip",
    "Kelmarsh_SCADA_2017_3083.zip",
    "Kelmarsh_SCADA_2018_3084.zip",
    "Kelmarsh_SCADA_2019_3085.zip",
    "Kelmarsh_SCADA_2020_3086.zip",
    "Kelmarsh_SCADA_2021_4456.zip",
    "Kelmarsh_SCADA_2022_4457.zip",
    "Kelmarsh_WT_static.csv",
    "Kelmarsh_WT_dataSignalMapping.csv",
    "Kelmarsh_12.3MW_6xSenvion_MM92.kmz",
)
#: 2023-2024 SCADA, and the meter archives whose names do not separate those years.
KELMARSH_HELD_BACK_FILES: Final[tuple[str, ...]] = (
    "Kelmarsh_SCADA_2023_5961.zip",
    "Kelmarsh_SCADA_2024_5962.zip",
    "Kelmarsh_PMU_4459.zip",
    "Kelmarsh_PMU_2023_2024_5968.zip",
    "Kelmarsh_Grid_Meter_4458.zip",
)

#: The publisher's WT01-10 group, including the 2023 files of that group, plus schema.
PENMANSHIEL_DEVELOPMENT_FILES: Final[tuple[str, ...]] = (
    "Penmanshiel_SCADA_2016_WT01-10_3107.zip",
    "Penmanshiel_SCADA_2017_WT01-10_3114.zip",
    "Penmanshiel_SCADA_2018_WT01-10_3113.zip",
    "Penmanshiel_SCADA_2019_WT01-10_3112.zip",
    "Penmanshiel_SCADA_2020_WT01-10_3109.zip",
    "Penmanshiel_SCADA_2021_WT01-10_4460.zip",
    "Penmanshiel_SCADA_2022_WT01-10_4462.zip",
    "Penmanshiel_SCADA_2023_02_WT_01-10_5981.zip",
    "Penmanshiel_SCADA_2023_03_WT_01-10_5982.zip",
    "Penmanshiel_SCADA_2023_Q2_WT_01-10_5977.zip",
    "Penmanshiel_SCADA_2023_Q3 Q4_WT_01-10_5973.zip",
    "Penmanshiel_WT_static.csv",
    "Penmanshiel_WT_dataSignalMapping.xlsx",
    "Penmanshiel_28.7MW_14xSenvion_MM82.kmz",
)
#: WT11-15, and the site meters, which are not split by turbine in the file names.
PENMANSHIEL_HELD_BACK_FILES: Final[tuple[str, ...]] = (
    "Penmanshiel_SCADA_2016_WT11-15_3107.zip",
    "Penmanshiel_SCADA_2017_WT11-15_3115.zip",
    "Penmanshiel_SCADA_2018_WT11-15_3116.zip",
    "Penmanshiel_SCADA_2019_WT11-15_3117.zip",
    "Penmanshiel_SCADA_2020_WT11-15_3118.zip",
    "Penmanshiel_SCADA_2021_WT11-15_4461.zip",
    "Penmanshiel_SCADA_2022_WT11-15_4463.zip",
    "Penmanshiel_SCADA_2023_WT_11-15_5964.zip",
    "Penmanshiel_SCADA_2024_WT_11-15_5966.zip",
    "Penmanshiel_PMU_4465.zip",
    "Penmanshiel_PMU_2023_2024_5969.zip",
    "Penmanshiel_Grid_4464.zip",
)

#: The first two published Geek Lounge days. The third day is held back.
FOUR_SICS_DEVELOPMENT_FILES: Final[tuple[str, ...]] = (
    "4SICS-GeekLounge-151020.pcap",
    "4SICS-GeekLounge-151021.pcap",
)
FOUR_SICS_HELD_BACK_FILES: Final[tuple[str, ...]] = ("4SICS-GeekLounge-151022.pcap",)

#: Fortiphyd/GRFICSv3 ``main`` on 14 October 2026. The tree is not copied here.
GRFICS_COMMIT: Final = "37bdf101f3ad0706a7595bd01d696ce7b84db436"
#: sha256 of that commit's LICENSE file (GPL-3.0). Recorded without storing the file.
GRFICS_LICENSE_SHA256: Final = "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad"


class GrficsRun(NamedTuple):
    """One GRFICSv3 run, named before the testbed is started.

    ``flow_1`` to ``flow_4`` and ``analyzer_a`` to ``analyzer_c`` mean the four
    flows and the three analysers in the order the pinned engine lists them.
    A generator that cannot find that order stops. It does not invent tags.

    Attributes:
        seed: The run's seed. Development and held-back do not share one.
        cause: ``physical`` (engine true/measured fault), ``cyber`` (HMI or
            command path), or ``quiet``.
        mode: ``frozen``, ``drift``, ``noise``, ``dropout``, ``stuck``, or ``none``.
        target: The sensor or valve the design note names, or ``none`` when quiet.
    """

    seed: int
    cause: str
    mode: str
    target: str


#: Ten development runs. They may be generated later and read any number of times.
GRFICS_DEVELOPMENT_RUNS: Final[tuple[GrficsRun, ...]] = (
    GrficsRun(97201, "physical", "frozen", "tank_level"),
    GrficsRun(97202, "physical", "frozen", "tank_pressure"),
    GrficsRun(97203, "physical", "drift", "flow_1"),
    GrficsRun(97204, "physical", "noise", "analyzer_a"),
    GrficsRun(97205, "physical", "dropout", "flow_2"),
    GrficsRun(97206, "cyber", "frozen", "tank_level"),
    GrficsRun(97207, "cyber", "noise", "tank_pressure"),
    GrficsRun(97208, "cyber", "stuck", "product"),
    GrficsRun(97209, "quiet", "none", "none"),
    GrficsRun(97210, "physical", "frozen", "analyzer_b"),
)
#: Ten held-back runs. Not generated, and not opened, until a score declaration.
GRFICS_HELD_BACK_RUNS: Final[tuple[GrficsRun, ...]] = (
    GrficsRun(97301, "physical", "frozen", "flow_3"),
    GrficsRun(97302, "physical", "drift", "analyzer_c"),
    GrficsRun(97303, "physical", "noise", "flow_4"),
    GrficsRun(97304, "physical", "dropout", "tank_level"),
    GrficsRun(97305, "cyber", "frozen", "flow_1"),
    GrficsRun(97306, "cyber", "dropout", "analyzer_a"),
    GrficsRun(97307, "cyber", "drift", "tank_level"),
    GrficsRun(97308, "cyber", "stuck", "f1"),
    GrficsRun(97309, "quiet", "none", "none"),
    GrficsRun(97310, "physical", "frozen", "flow_4"),
)

#: Atlas corpora with role ``held-out``. Order is registry order.
DECLARED_HELD_OUT: Final[tuple[str, ...]] = (
    "phos-icssim-heldout",
    "kelmarsh-heldback",
    "penmanshiel-heldback",
    "netresec-4sics-heldout",
    "grfics-v3-heldout",
    "tu-wien-pilot-factory-heldout",
)

_CAUSES: Final = frozenset({"physical", "cyber", "quiet"})
_MODES: Final = frozenset({"frozen", "drift", "noise", "dropout", "stuck", "none"})


def build_seed_blocks() -> dict[str, frozenset[int]]:
    """Return the four seed blocks this declaration adds.

    The blocks are the synthetic development batch, the synthetic held-back
    batch, and the two GRFICS batches. A test checks them against the sets
    that were already used.
    """
    return {
        "build-development": frozenset(BUILD_DEVELOPMENT_SEEDS),
        "build-held-back": frozenset(BUILD_HELD_BACK_SEEDS),
        "grfics-development": frozenset(run.seed for run in GRFICS_DEVELOPMENT_RUNS),
        "grfics-held-back": frozenset(run.seed for run in GRFICS_HELD_BACK_RUNS),
    }


def registry_file_halves() -> dict[str, frozenset[str]]:
    """Return the registry name of each half and the files that belong in it.

    Schema files sit on the development entry. Held-back entries are the
    files nobody opens until a declaration.
    """
    return {
        "kelmarsh": frozenset(KELMARSH_DEVELOPMENT_FILES),
        "kelmarsh-heldback": frozenset(KELMARSH_HELD_BACK_FILES),
        "penmanshiel": frozenset(PENMANSHIEL_DEVELOPMENT_FILES),
        "penmanshiel-heldback": frozenset(PENMANSHIEL_HELD_BACK_FILES),
        "netresec-4sics-ics-pcap": frozenset(FOUR_SICS_DEVELOPMENT_FILES),
        "netresec-4sics-heldout": frozenset(FOUR_SICS_HELD_BACK_FILES),
    }


def grfics_run_ok(run: GrficsRun) -> bool:
    """Return whether one declared run uses only the named causes and modes.

    A quiet run has mode ``none`` and target ``none``. Any other run names a
    target. This checks the declaration, not a generated file.
    """
    if run.cause not in _CAUSES or run.mode not in _MODES:
        return False
    if run.cause == "quiet":
        return run.mode == "none" and run.target == "none"
    return run.mode != "none" and run.target != "none"
