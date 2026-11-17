"""Test HAI detector on real ICS telemetry using subset of training data."""

from __future__ import annotations

from pathlib import Path

import pandas

from phos.atlas import MahalanobisModel
from phos.atlas.sequential_consistency import change_run
from phos.atlas.topology import SubsystemMap
from phos.eval import Dataset
from phos.models.base import SplitPolicy, train_test_split
from phos.ontology import Domain, Observation
from phos.reasoning import FittedPlattCalibrator
from phos.referee.demo import _HAI_ALL_SIGNALS, _hai_subsystems
from phos.referee.detectors import AtlasDetector, _reconstruct_values


def main() -> None:
    """Fit Atlas on a subset of HAI training data and run it on the full test split."""
    print("=" * 60)
    print("HAI 21.03 industrial ICS detector (subset training)")
    print("=" * 60)

    # Load training data
    print("Loading HAI training data...")
    df = pandas.read_csv(Path("data/hai/hai-21.03-train-prepared.csv"))
    print(f"Loaded {len(df)} rows, {len(df.columns) - 2} signals")

    # Use first 8000 timestamps for fitting (speed)
    unique_ts = sorted(df["timestamp"].unique())[:8000]
    subset_df = df[df["timestamp"].isin(unique_ts)]
    print(f"Using {len(unique_ts)} timestamps, {len(subset_df)} observations for training")

    # Build observations
    observations = []
    for row_index, row in subset_df.iterrows():
        ts = pandas.Timestamp(row["timestamp"]).to_pydatetime()
        for column in df.columns:
            if column in ("timestamp", "label"):
                continue
            observations.append(
                Observation(
                    id=f"obs_hai_train_{row_index:08d}_{column}",
                    entity_ids=["hai:train"],
                    feature=column,
                    value=float(row[column]),
                    timestamp=ts,
                    domain=Domain.ATLAS,
                )
            )

    train_ds = Dataset(
        name="hai-train-subset",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note="HAI 21.03 train subset (first 8000 timestamps)",
    )

    train, _test = train_test_split(train_ds, SplitPolicy())

    # Fit model
    print("Fitting Mahalanobis model...")
    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    consistency_calibrator = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    # Build topology
    subsystems = _hai_subsystems()
    topology = SubsystemMap(subsystems, set(_HAI_ALL_SIGNALS))

    # Sequential model on P1_STSP
    train_features, _tt, train_values, _teo = _reconstruct_values(train)
    col_map = {f: i for i, f in enumerate(train_features)}
    sequential_model = {}
    if "P1_STSP" in col_map:
        col = col_map["P1_STSP"]
        longest = int(change_run(train_values[:, col]).max(initial=0.0))
        sequential_model["P1_STSP"] = (col, longest)
    print(f"Sequential model: {sequential_model}")

    det = AtlasDetector(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=topology,
        consistency_calibrator=consistency_calibrator,
        sequential_model=sequential_model or None,
    )
    print(f"Detector: {det.name}")
    print()

    # Test on full test set
    print("Loading test data...")
    test_df = pandas.read_csv(Path("data/hai/hai-21.03-test-prepared.csv"))
    print(f"Test: {len(test_df)} rows")

    test_observations = []
    for row_index, row in test_df.iterrows():
        ts = pandas.Timestamp(row["timestamp"]).to_pydatetime()
        for column in test_df.columns:
            if column in ("timestamp", "label"):
                continue
            test_observations.append(
                Observation(
                    id=f"obs_hai_test_{row_index:08d}_{column}",
                    entity_ids=["hai:test"],
                    feature=column,
                    value=float(row[column]),
                    timestamp=ts,
                    domain=Domain.ATLAS,
                )
            )

    test_ds = Dataset(
        name="hai-test",
        domain=Domain.ATLAS,
        observations=test_observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note="HAI 21.03 test",
    )
    print(f"Loaded {len(test_ds.observations)} test observations")
    print("Running detector...")
    test_dets = det.run(test_ds)

    attack_rows = int((test_df["label"] == 1).sum())
    print(f"\nTest: {len(test_ds.observations)} observations, {attack_rows} attack-labelled rows")
    print(f"Test detections: {len(test_dets)}")
    print()

    print("First 15 detection timestamps:")
    for det_item in test_dets[:15]:
        print(
            f"  {det_item.timestamp} score={det_item.score:.3f} "
            f"confidence={det_item.confidence:.3f} feature={det_item.feature}"
        )


if __name__ == "__main__":
    main()
