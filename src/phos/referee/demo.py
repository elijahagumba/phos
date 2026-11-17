"""Factory functions for ``phos-referee``'s own usage examples.

PART S6. The CLI takes a detector as a ``module:function`` factory string; this module exists so
``phos-referee run`` has something real to score. Nothing here is a PHOS detection model — the
threshold detector is a harness test fixture, and the atlas detector below is fitted on a
development plant's attack-free telemetry.
"""

from __future__ import annotations

import csv
import tempfile
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas

from phos.atlas import MahalanobisModel, load_topology
from phos.atlas.sequential_consistency import change_run
from phos.atlas.topology import Subsystem, SubsystemMap
from phos.eval import Dataset, Detector, ThresholdDetector
from phos.models.base import SplitPolicy, train_test_split
from phos.ontology import Domain, Observation
from phos.reasoning import FittedPlattCalibrator
from phos.referee.corpus import load_plant_dataset
from phos.referee.detectors import AtlasDetector, _reconstruct_values
from phos.synth.families import get_family
from phos.synth.outputs import TOPOLOGY_FILE, generate_plant

__all__ = [
    "atlas_detector",
    "batadal_detector",
    "hai_detector",
    "icssim_detector",
    "kelmarsh_detector",
    "swat_detector",
    "threshold_detector",
]

#: ICSSim signal names, read from roles.toml (ICSSim's own signal-role declaration).
ICSSIM_SIGNALS: tuple[str, ...] = (
    "tank_input_valve_status",
    "tank_input_valve_mode",
    "tank_level_value",
    "tank_level_min",
    "tank_level_max",
    "tank_output_valve_status",
    "tank_output_valve_mode",
    "tank_output_flow_value",
    "conveyor_belt_engine_status",
    "conveyor_belt_engine_mode",
    "bottle_level_value",
    "bottle_level_max",
    "bottle_distance_to_filler_value",
)

#: ICSSim subsystem grouping, read from roles.toml control loops.
ICSSIM_SUBSYSTEMS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "plc1_input_valve",
        "PLC1 input valve loop",
        (
            "tank_level_value",
            "tank_level_max",
            "tank_level_min",
            "tank_input_valve_status",
            "tank_input_valve_mode",
        ),
    ),
    (
        "plc1_output_valve",
        "PLC1 output valve loop",
        (
            "tank_output_valve_status",
            "tank_output_valve_mode",
            "tank_output_flow_value",
            "bottle_level_value",
            "bottle_level_max",
            "bottle_distance_to_filler_value",
        ),
    ),
    (
        "plc2_conveyor",
        "PLC2 conveyor loop",
        (
            "conveyor_belt_engine_status",
            "conveyor_belt_engine_mode",
        ),
    ),
)

#: Directory holding ICSSim dev corpora (normal-* for training, mixed-* for exams).
_ICSSIM_DEV_DIR: Path = Path("data/phos-icssim-dev")

#: Development seed used to grow the training plant the atlas detector is fitted on.
#: Kept fixed so the fitted model is reproducible across referee runs.
_ATLAS_TRAIN_SEED: int = 20261116
_ATLAS_TRAIN_FAMILY: str = "level_flow"


def _load_csv_dataset(path: Path, plant_id: str) -> Dataset:
    """Load a prepared CSV into a `Dataset`.

    Reads timestamp, label, and value columns. Every row becomes one Observation
    per value column. Timestamps are parsed as ISO-8601 with timezone.
    """
    df = pandas.read_csv(path)
    observations: list[Observation] = []
    ts_col = df.columns[0]
    for row_index, row in df.iterrows():
        ts = pandas.Timestamp(row[ts_col]).to_pydatetime()
        for column in df.columns:
            if column in (ts_col, "label"):
                continue
            observations.append(
                Observation(
                    id=f"obs_csv_{plant_id}_{row_index:08d}_{column}",
                    entity_ids=[f"csv:{plant_id}"],
                    feature=column,
                    value=float(row[column]),
                    timestamp=ts,
                    domain=Domain.ATLAS,
                )
            )
    return Dataset(
        name=f"csv:{plant_id}",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note=f"CSV telemetry from {path}",
    )


# ============================================================================
# level_flow — synthetic pumped tank chain (development seeds)
# ============================================================================


def threshold_detector() -> Detector:
    """Return `phos.eval.ThresholdDetector`'s own documented default.

    `ThresholdDetector` is the harness's test fixture, not a PHOS detection model — see its own
    docstring. It exists here only so a person trying `phos-referee run` for the first time has
    something that runs end to end before pointing the command at a real detector.
    """
    return ThresholdDetector()


def atlas_detector() -> Detector:
    """Build an `AtlasDetector` fitted on a development plant's attack-free telemetry.

    The detector is fitted once, at factory time, on a single level_flow plant grown with no
    injected events (normal operation only). It is then reused unchanged against every exam
    plant — which is exactly what a black-box breaker sees: a fixed detector it may query but
    never retune.

    Because `phos.atlas.engine.AtlasEngine` raises `TopologyError` for signals outside the
    subsystem map it was built against, every plant the breaker scores must share this plant's
    family (and therefore its signal names and topology). The dev seed pool for an atlas exam
    should therefore contain only ``level_flow`` seeds.

    Consistency evidence is fit per-plant inside `AtlasDetector.run` on this plant's own
    attack-free training prefix, because different plants from the same family have different
    signal sets.

    Returns:
        An `AtlasDetector` fitted on normal, attack-free telemetry.
    """
    output = Path(tempfile.mkdtemp(prefix="phos-atlas-train-"))
    family = get_family(_ATLAS_TRAIN_FAMILY)
    plant = generate_plant(
        family,
        _ATLAS_TRAIN_SEED,
        output,
        hours=24.0,
        events=None,
        event_seed=_ATLAS_TRAIN_SEED,
    )

    dataset = load_plant_dataset(plant)
    train, _test = train_test_split(dataset, SplitPolicy())

    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)
    topology = load_topology(
        plant.directory / TOPOLOGY_FILE,
        {observation.feature for observation in dataset.observations},
        corpus=plant.manifest.plant_id,
    )

    # Fit the sequential model on the separate training plant (not on exam data).
    # Discover setpoint tags dynamically from signal roles so this works with any tag
    # naming scheme, not just a hardcoded "tank_level_max".
    setpoint_keys = [
        tag for tag, role in plant.draw.spec.roles.items() if role.role == "level_setpoint"
    ]
    train_features, _train_timestamps, train_values, _train_entity_of = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model: dict[str, tuple[int, int]] = {}
    for tag in setpoint_keys:
        if tag not in col_map:
            continue
        col = col_map[tag]
        longest = 0
        observed = float(change_run(train_values[:, col]).max(initial=0.0))
        longest = max(longest, int(observed))
        sequential_model[tag] = (col, longest)

    return AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
    )


# ============================================================================
# ICSSim — synthetic water/filler process (MIT-licensed, Atlas's own domain)
# ============================================================================


def _load_icssim_csv(path: Path, plant_id: str) -> Dataset:
    """Load an ICSSim ``process.csv`` into a `Dataset`.

    Each row becomes one Observation per signal column. Timestamps are epoch
    seconds (float) as written by the ICSSim generator.
    """
    df = pandas.read_csv(path)
    observations: list[Observation] = []
    for row_index, row in df.iterrows():
        ts = datetime.fromtimestamp(float(row["timestamp"]), tz=UTC)
        for column in df.columns:
            if column == "timestamp":
                continue
            observations.append(
                Observation(
                    id=f"obs_icssim_{plant_id}_{row_index:08d}_{column}",
                    entity_ids=[f"icssim:{plant_id}"],
                    feature=column,
                    value=float(row[column]),
                    timestamp=ts,
                    domain=Domain.ATLAS,
                )
            )
    return Dataset(
        name=f"icssim:{plant_id}",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note=f"ICSSim telemetry from {path}",
    )


def icssim_detector() -> Detector:
    """Build an `AtlasDetector` fitted on ICSSim normal telemetry.

    Fits on the ICSSim dev normal plants (``data/phos-icssim-dev/normal-*``)
    and is then reused unchanged against ICSSim exam plants. The sequential
    consistency model is fit on ``tank_level_max`` from the normal training
    data, so setpoint walks on that register are detected.

    Returns:
        An `AtlasDetector` fitted on normal, attack-free ICSSim telemetry.
    """
    # Load normal ICSSim plants as training data. Use the first normal plant;
    # all ICSSim plants share the same epoch, so concatenating multiple would
    # break time-ordering. One plant (14401 samples) is sufficient for fitting.
    normal_dirs = sorted(_ICSSIM_DEV_DIR.glob("normal-*"))
    if not normal_dirs:
        raise FileNotFoundError(
            f"no ICSSim normal plants found in {_ICSSIM_DEV_DIR}; "
            "check that data/phos-icssim-dev/normal-* exists"
        )
    train_plant = normal_dirs[0]
    train_ds = _load_icssim_csv(train_plant / "process.csv", train_plant.name)

    # Split into train/test for fitting the Mahalanobis model.
    train, _test = train_test_split(train_ds, SplitPolicy())

    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    # Build SubsystemMap from ICSSim roles (read from roles.toml).
    subsystems = tuple(
        Subsystem(
            subsystem_id=sub_id,
            label=label,
            signals=frozenset(signals),
            source="ICSSim roles.toml",
        )
        for sub_id, label, signals in ICSSIM_SUBSYSTEMS
    )
    topology = SubsystemMap(subsystems, set(ICSSIM_SIGNALS))

    # Fit the sequential model on tank_level_max from normal training data.
    train_features, _train_timestamps, train_values, _train_entity_of = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model: dict[str, tuple[int, int]] = {}
    if "tank_level_max" in col_map:
        col = col_map["tank_level_max"]
        longest = int(change_run(train_values[:, col]).max(initial=0.0))
        sequential_model["tank_level_max"] = (col, longest)

    return AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
    )


# ============================================================================
# BATADAL — C-Town water distribution network (water sector, real data)
# ============================================================================

_BATADAL_TRAIN: Path = Path("data/batadal/batadal-train-prepared.csv")

_BATADAL_TANKS: tuple[str, ...] = tuple(f"L_T{i}" for i in range(1, 8))
_BATADAL_PUMPS: tuple[str, ...] = tuple(f"PU{i}" for i in range(1, 12))
_BATADAL_VALVES: tuple[str, ...] = ("V2",)
_BATADAL_JUNCTIONS: tuple[str, ...] = (
    "J14",
    "J256",
    "J269",
    "J280",
    "J289",
    "J300",
    "J302",
    "J306",
    "J307",
    "J317",
    "J415",
    "J422",
)


def _batadal_subsystems() -> tuple[Subsystem, ...]:
    """Build Subsystems for the BATADAL water network from signal roles.

    Tanks are level sensors; pumps have flow + status (setpoint); valves have
    flow + status; junctions are pressure sensors.
    """
    subsystems: list[Subsystem] = []

    for i in range(1, 8):
        subsystems.append(
            Subsystem(
                subsystem_id=f"tank_t{i}",
                label=f"Tank T{i}",
                signals=frozenset((f"L_T{i}",)),
                source="BATADAL dataset04 column roles",
            )
        )

    for pump in _BATADAL_PUMPS:
        subsystems.append(
            Subsystem(
                subsystem_id=f"pump_{pump}",
                label=f"Pump PU{pump}",
                signals=frozenset((f"F_{pump}", f"S_{pump}")),
                source="BATADAL dataset04 column roles",
            )
        )

    for valve in _BATADAL_VALVES:
        subsystems.append(
            Subsystem(
                subsystem_id=f"valve_{valve}",
                label=f"Valve {valve}",
                signals=frozenset((f"F_{valve}", f"S_{valve}")),
                source="BATADAL dataset04 column roles",
            )
        )

    for junction in _BATADAL_JUNCTIONS:
        subsystems.append(
            Subsystem(
                subsystem_id=f"junction_{junction}",
                label=f"Junction {junction}",
                signals=frozenset((f"P_{junction}",)),
                source="BATADAL dataset04 column roles",
            )
        )

    return tuple(subsystems)


_BATADAL_ALL_SIGNALS: frozenset[str] = frozenset(
    list(_BATADAL_TANKS)
    + [f"F_{p}" for p in _BATADAL_PUMPS]
    + [f"S_{p}" for p in _BATADAL_PUMPS]
    + ["F_V2", "S_V2"]
    + [f"P_{j}" for j in _BATADAL_JUNCTIONS]
)


def batadal_detector() -> Detector:
    """Build an `AtlasDetector` fitted on BATADAL water network training data.

    Fits on ``data/batadal/batadal-train-prepared.csv`` (attack-free year of
    hourly SCADA from the C-Town water network) and is then reused unchanged
    against BATADAL exam plants. The sequential consistency model is fit on
    pump status signals (S_PU*), which are the network's commanded setpoints.

    Returns:
        An `AtlasDetector` fitted on normal, attack-free BATADAL telemetry.
    """
    ds = _load_csv_dataset(_BATADAL_TRAIN, "batadal-normal-train")
    train, _test = train_test_split(ds, SplitPolicy())

    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    topology = SubsystemMap(_batadal_subsystems(), set(_BATADAL_ALL_SIGNALS))

    # Fit the sequential model on pump status signals (pump setpoints).
    train_features, _train_timestamps, train_values, _train_entity_of = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model: dict[str, tuple[int, int]] = {}
    for pump in _BATADAL_PUMPS:
        tag = f"S_{pump}"
        if tag in col_map:
            col = col_map[tag]
            longest = int(change_run(train_values[:, col]).max(initial=0.0))
            sequential_model[tag] = (col, longest)
    if "S_V2" in col_map:
        col = col_map["S_V2"]
        longest = int(change_run(train_values[:, col]).max(initial=0.0))
        sequential_model["S_V2"] = (col, longest)

    return AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
    )


# ============================================================================
# HAI — HIL-based Augmented ICS Security Dataset (industrial ICS sector, real data)
# ============================================================================

_HAI_TRAIN: Path = Path("data/hai/hai-21.03-train-prepared.csv")

_HAI_PROCESSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "process_1",
        tuple(
            f"P1_{s}"
            for s in (
                "B2004",
                "B2016",
                "B3004",
                "B3005",
                "B4002",
                "B4005",
                "B400B",
                "B4022",
                "FCV01D",
                "FCV01Z",
                "FCV02D",
                "FCV02Z",
                "FCV03D",
                "FCV03Z",
                "FT01",
                "FT01Z",
                "FT02",
                "FT02Z",
                "FT03",
                "FT03Z",
                "LCV01D",
                "LCV01Z",
                "LIT01",
                "PCV01D",
                "PCV01Z",
                "PCV02D",
                "PCV02Z",
                "PIT01",
                "PIT02",
                "PP01AD",
                "PP01AR",
                "PP01BD",
                "PP01BR",
                "PP02D",
                "PP02R",
                "STSP",
                "TIT01",
                "TIT02",
            )
        ),
    ),
    (
        "process_2",
        tuple(
            f"P2_{s}"
            for s in (
                "24Vdc",
                "ASD",
                "AutoGO",
                "CO_rpm",
                "Emerg",
                "HILout",
                "MSD",
                "ManualGO",
                "OnOff",
                "RTR",
                "SIT01",
                "SIT02",
                "TripEx",
                "VT01",
                "VTR01",
                "VTR02",
                "VTR03",
                "VTR04",
                "VXT02",
                "VXT03",
                "VYT02",
                "VYT03",
            )
        ),
    ),
    (
        "process_3",
        tuple(f"P3_{s}" for s in ("FIT01", "LCP01D", "LCV01D", "LH", "LIT01", "LL", "PIT01")),
    ),
    (
        "process_4",
        tuple(
            f"P4_{s}"
            for s in (
                "HT_FD",
                "HT_LD",
                "HT_PO",
                "HT_PS",
                "LD",
                "ST_FD",
                "ST_GOV",
                "ST_LD",
                "ST_PO",
                "ST_PS",
                "ST_PT01",
                "ST_TT01",
            )
        ),
    ),
)


def _hai_subsystems() -> tuple[Subsystem, ...]:
    """Build Subsystems for the HAI ICS testbed from process groupings."""
    subsystems: list[Subsystem] = []
    for sub_id, signals in _HAI_PROCESSES:
        subsystems.append(
            Subsystem(
                subsystem_id=sub_id,
                label=f"HAI {sub_id.replace('_', ' ').title()}",
                signals=frozenset(signals),
                source="HAI 21.03 column roles",
            )
        )
    return tuple(subsystems)


_HAI_ALL_SIGNALS: frozenset[str] = frozenset(
    s for _sub_id, signals in _HAI_PROCESSES for s in signals
)


def hai_detector() -> Detector:
    """Build an `AtlasDetector` fitted on HAI 21.03 training data.

    Fits on ``data/hai/hai-21.03-train-prepared.csv`` (attack-free 60 hours of
    HIL-based ICS telemetry) and is then reused unchanged against HAI exam
    plants. The sequential consistency model is fit on P1_STSP (process 1
    setpoint), which is the plant's commanded setpoint register.

    Returns:
        An `AtlasDetector` fitted on normal, attack-free HAI telemetry.
    """
    ds = _load_csv_dataset(_HAI_TRAIN, "hai-normal-train")
    train, _test = train_test_split(ds, SplitPolicy())

    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    topology = SubsystemMap(_hai_subsystems(), set(_HAI_ALL_SIGNALS))

    # Fit the sequential model on P1_STSP (process 1 setpoint).
    train_features, _train_timestamps, train_values, _train_entity_of = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model: dict[str, tuple[int, int]] = {}
    if "P1_STSP" in col_map:
        col = col_map["P1_STSP"]
        longest = int(change_run(train_values[:, col]).max(initial=0.0))
        sequential_model["P1_STSP"] = (col, longest)

    # Pre-compute HAI code-law baselines from the FULL training file (not split),
    # so baselines reflect pure attack-free operation. These are used by
    # _build_hai_code_law_detections to detect deviations on exam plants.
    hai_baselines: dict[str, tuple[int, float]] = {}
    for tag in _HAI_ALL_SIGNALS:
        if tag in col_map:
            col = col_map[tag]
            mean = float(train_values[:, col].mean())
            hai_baselines[tag] = (col, mean)

    return AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
        hai_baselines=hai_baselines,
    )


# ============================================================================
# Kelmarsh — UK wind farm SCADA (power sector, UK, real data)
# ============================================================================

_KELMARSH_ZIP: Path = Path("data/kelmarsh/Kelmarsh_SCADA_2018_3084.zip")

# Key turbine signals for detection (subset of all Greenbyte signals).
# These cover wind, power, drive train, electrical, temperature and availability.
_KELMARSH_SIGNALS: tuple[str, ...] = (
    "Wind speed (m/s)",
    "Wind direction (°)",
    "Nacelle position (°)",
    "Power (kW)",
    "Turbine Power setpoint (kW)",
    "Rotor speed (RPM)",
    "Generator RPM (RPM)",
    "Gearbox speed (RPM)",
    "Grid frequency (Hz)",
    "Grid voltage (V)",
    "Grid current (A)",
    "Blade angle (pitch position) A (°)",
    "Blade angle (pitch position) B (°)",
    "Blade angle (pitch position) C (°)",
    "Front bearing temperature (°C)",
    "Rear bearing temperature (°C)",
    "Gear oil temperature (°C)",
    "Generator bearing front temperature (°C)",
    "Generator bearing rear temperature (°C)",
    "Ambient temperature (converter) (°C)",
    "Hub temperature (°C)",
    "Nacelle temperature (°C)",
    "Apparent power (kVA)",
    "Reactive power (kvar)",
    "Capacity factor",
    "Data Availability",
)


def _kelmarsh_column_names(zip_path: Path) -> list[str]:
    """Read column names from a Kelmarsh Turbine_Data CSV header line.

    Greenbyte exports the header as a comment line starting with ``# ``.
    """
    with zipfile.ZipFile(zip_path) as zf:
        turbine_files = [n for n in zf.namelist() if n.startswith("Turbine_Data_Kelmarsh_1_")]
        if not turbine_files:
            raise FileNotFoundError(f"No Turbine_Data for Kelmarsh 1 in {zip_path}")
        content = zf.read(turbine_files[0]).decode("utf-8", errors="replace")

    for line in content.splitlines():
        if line.startswith("# Date and time"):
            reader = csv.reader([line[2:]])
            return next(reader)
    raise ValueError(f"No header line found in {zip_path}")


def _load_kelmarsh_dataset(zip_path: Path, column_names: list[str]) -> Dataset:
    """Load Kelmarsh turbine SCADA data from a zip file into a `Dataset`."""
    with zipfile.ZipFile(zip_path) as zf:
        turbine_files = [n for n in zf.namelist() if n.startswith("Turbine_Data_Kelmarsh_1_")]
        if not turbine_files:
            raise FileNotFoundError(f"No Turbine_Data for Kelmarsh 1 in {zip_path}")
        content = zf.read(turbine_files[0]).decode("utf-8", errors="replace")

    lines = content.strip().split("\n")

    # Find data start (line after the header comment)
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("# Date and time"):
            data_start = i + 1
            break

    # Column indices for signals of interest
    col_indices = {name: i for i, name in enumerate(column_names) if name in _KELMARSH_SIGNALS}

    observations: list[Observation] = []
    for row_count, line in enumerate(lines[data_start:]):
        row = next(csv.reader([line]))
        if len(row) <= 1:
            continue
        try:
            ts = pandas.Timestamp(row[0]).tz_localize("UTC").to_pydatetime()
        except (ValueError, IndexError):
            continue
        for col_name, col_idx in col_indices.items():
            if col_idx >= len(row):
                continue
            try:
                value = float(row[col_idx])
            except (ValueError, IndexError):
                continue
            safe_name = (
                col_name.replace(" ", "_").replace("(", "").replace(")", "").replace("°", "deg")
            )
            observations.append(
                Observation(
                    id=f"obs_kelmarsh_{row_count:08d}_{safe_name}",
                    entity_ids=["kelmarsh:turbine1"],
                    feature=col_name,
                    value=value,
                    timestamp=ts,
                    domain=Domain.ATLAS,
                )
            )

    return Dataset(
        name="kelmarsh-turbine1",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note=f"Kelmarsh wind farm SCADA from {zip_path}",
    )


def kelmarsh_detector() -> Detector:
    """Build an `AtlasDetector` fitted on Kelmarsh UK wind farm SCADA data.

    Fits on ``data/kelmarsh/Kelmarsh_SCADA_2018_3084.zip`` (attack-free year of
    10-minute SCADA from Kelmarsh wind farm, UK) and is then reused unchanged
    against Kelmarsh exam plants. The sequential consistency model is fit on
    ``Turbine Power setpoint (kW)``, which is the turbine's commanded setpoint.

    Because Kelmarsh data carries no attack labels, this detector can be used
    for false-alarm rate measurement on real UK wind farm telemetry, but not
    for attack detection measurement.

    Returns:
        An `AtlasDetector` fitted on normal, attack-free Kelmarsh telemetry.
    """
    column_names = _kelmarsh_column_names(_KELMARSH_ZIP)
    ds = _load_kelmarsh_dataset(_KELMARSH_ZIP, column_names)

    train, _test = train_test_split(ds, SplitPolicy())

    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    # Build SubsystemMap from Kelmarsh signal groups (each signal in exactly one subsystem).
    remaining: set[str] = set(_KELMARSH_SIGNALS)
    subsystems: list[Subsystem] = []

    def _add(sub_id: str, label: str, predicate: Callable[[str], bool]) -> None:
        nonlocal remaining
        matched = frozenset(s for s in remaining if predicate(s))
        if matched:
            subsystems.append(
                Subsystem(
                    subsystem_id=sub_id,
                    label=label,
                    signals=matched,
                    source="Kelmarsh SCADA signal roles",
                )
            )
            remaining = remaining - matched

    _add("wind", "Wind measurement", lambda s: "Wind" in s or "wind" in s)
    _add("power", "Power generation", lambda s: "Power" in s or "power" in s)
    _add("temperature", "Temperature", lambda s: "temperature" in s.lower())
    _add(
        "electrical",
        "Electrical",
        lambda s: ("Voltage" in s or "Current" in s or "frequency" in s.lower()),
    )
    _add(
        "mechanical",
        "Mechanical drive train",
        lambda s: ("RPM" in s or "Blade" in s or "pitch" in s.lower() or "Yaw" in s or "yaw" in s),
    )
    _add("availability", "Availability", lambda s: "Availability" in s or "factor" in s.lower())

    # Any unmatched signals go to an "other" subsystem.
    if remaining:
        subsystems.append(
            Subsystem(
                subsystem_id="other",
                label="Other measurements",
                signals=frozenset(remaining),
                source="Kelmarsh SCADA signal roles",
            )
        )

    topology = SubsystemMap(subsystems, frozenset(_KELMARSH_SIGNALS))

    # Fit sequential model on Turbine Power setpoint.
    train_features, _train_timestamps, train_values, _train_entity_of = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model: dict[str, tuple[int, int]] = {}
    setpoint_tag = "Turbine Power setpoint (kW)"
    if setpoint_tag in col_map:
        col = col_map[setpoint_tag]
        longest = int(change_run(train_values[:, col]).max(initial=0.0))
        sequential_model[setpoint_tag] = (col, longest)

    return AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
    )


# ============================================================================
# SWaT — Secure Water Treatment (iTrust, SUTD) — ready when access is granted
# ============================================================================
# SWaT is form-gated at iTrust (ADR 0067). This factory is committed ready to run
# the moment the form is returned and the files are on disk. It does not fetch,
# scrape, or assume the files exist.
#
# SWaT uses published tag naming: FIT=flow, PIT=pressure, P=pump_state,
# MV=valve, LIT=level, AIT=analyzer, UV=UV lamp. ADR 0063 declares three
# shared physical roles (flow, pressure, pump_state); tank levels and analyser
# channels stay plant-private for the zero-shot protocol but are available to
# this detector factory when SWaT is scored in-plant.


def _swat_subsystems(signal_names: list[str]) -> tuple[Subsystem, ...]:
    """Build Subsystems for SWaT from signal names, grouped by declared physical role.

    Uses ADR 0063's three declared roles: flow, pressure, pump_state. Tank levels,
    analyser channels, and setpoints are plant-private for zero-shot but included
    here as their own subsystems for in-plant scoring.
    """
    subsystems: list[Subsystem] = []
    signal_set = set(signal_names)

    flow = frozenset(s for s in signal_set if s.startswith("FIT"))
    pressure = frozenset(s for s in signal_set if s.startswith("PIT"))
    pump_state = frozenset(s for s in signal_set if s.startswith("P") and not s.startswith("PIT"))
    level = frozenset(s for s in signal_set if s.startswith("LIT"))
    analyzer = frozenset(s for s in signal_set if s.startswith("AIT"))
    valve = frozenset(s for s in signal_set if s.startswith("MV"))
    uv = frozenset(s for s in signal_set if s.startswith("UV"))

    for sub_id, label, signals in (
        ("flow", "Flow meters", flow),
        ("pressure", "Pressure sensors", pressure),
        ("pump_state", "Pump states", pump_state),
        ("level", "Tank levels", level),
        ("analyzer", "Analyser channels", analyzer),
        ("valve", "Valves", valve),
        ("uv", "UV lamps", uv),
    ):
        if signals:
            subsystems.append(
                Subsystem(
                    subsystem_id=sub_id,
                    label=label,
                    signals=signals,
                    source="SWaT published tag naming (FIT/PIT/P/LIT/AIT/MV/UV)",
                )
            )

    return tuple(subsystems)


def _swat_all_signals(signal_names: list[str]) -> frozenset[str]:
    """Return the subset of known SWaT signals present in the CSV."""
    known_prefixes = ("FIT", "PIT", "LIT", "AIT", "MV", "UV", "P")
    return frozenset(s for s in signal_names if any(s.startswith(p) for p in known_prefixes))


def swat_detector(train_csv: Path) -> Detector:
    """Build an `AtlasDetector` fitted on SWaT training data.

    SWaT is form-gated at iTrust (ADR 0067). This factory is committed ready to
    run the moment the form is returned and the training CSV is on disk. Pass the
    path to the SWaT training CSV; the factory discovers signals from the header
    and groups them by ADR 0063's declared physical roles.

    Because SWaT data is not on disk, this factory is untested against real
    SWaT telemetry. It is a structural readiness, not a measured result.

    Args:
        train_csv: Path to the SWaT training CSV (from iTrust form return).

    Returns:
        An `AtlasDetector` fitted on normal, attack-free SWaT telemetry.

    Raises:
        FileNotFoundError: If ``train_csv`` does not exist.
    """
    if not train_csv.exists():
        raise FileNotFoundError(
            f"SWaT training CSV not found at {train_csv}. "
            "SWaT is form-gated at iTrust (ADR 0067); this factory waits for "
            "the form to be returned, it does not fetch."
        )

    ds = _load_csv_dataset(train_csv, "swat-train")
    train, _test = train_test_split(ds, SplitPolicy())

    signal_names = sorted({o.feature for o in train.observations})
    topology = SubsystemMap(_swat_subsystems(signal_names), _swat_all_signals(signal_names))

    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    # Fit the sequential model on pump state signals (pump setpoints).
    train_features, _train_timestamps, train_values, _train_entity_of = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model: dict[str, tuple[int, int]] = {}
    for tag in train_features:
        if tag.startswith("P") and not tag.startswith("PIT"):
            col = col_map[tag]
            longest = int(change_run(train_values[:, col]).max(initial=0.0))
            sequential_model[tag] = (col, longest)

    return AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
    )
