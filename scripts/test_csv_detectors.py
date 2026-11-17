"""Test BATADAL detector on real water network telemetry."""

from __future__ import annotations

from pathlib import Path

import pandas

from phos.referee.demo import _load_csv_dataset, batadal_detector


def main() -> None:
    """Run the BATADAL detector on real training and test telemetry and print detections."""
    print("=" * 60)
    print("BATADAL water network detector")
    print("=" * 60)

    detector = batadal_detector()
    print(f"Detector: {detector.name}")
    print()

    # Normal (train) — false alarm check
    print("Loading training data...")
    train_ds = _load_csv_dataset(Path("data/batadal/batadal-train-prepared.csv"), "batadal-train")
    print(f"Loaded {len(train_ds.observations)} observations")
    print("Running detector on training data...")
    train_dets = detector.run(train_ds)
    print(
        f"Train (normal): {len(train_ds.observations)} observations, {len(train_dets)} detections"
    )
    print(f"  False alarms: {len(train_dets)}")
    print()

    # Test (has attacks)
    print("Loading test data...")
    test_ds = _load_csv_dataset(Path("data/batadal/batadal-test-prepared.csv"), "batadal-test")
    print(f"Loaded {len(test_ds.observations)} observations")
    print("Running detector on test data...")
    test_dets = detector.run(test_ds)

    df = pandas.read_csv(Path("data/batadal/batadal-test-prepared.csv"))
    attack_rows = int((df["label"] == 1).sum())
    print(f"Test: {len(test_ds.observations)} observations, {attack_rows} attack-labelled rows")
    print(f"Test detections: {len(test_dets)}")
    print()

    # Show detection timestamps
    print("First 15 detection timestamps:")
    for det in test_dets[:15]:
        print(
            f"  {det.timestamp} score={det.score:.3f} "
            f"confidence={det.confidence:.3f} feature={det.feature}"
        )


if __name__ == "__main__":
    main()
