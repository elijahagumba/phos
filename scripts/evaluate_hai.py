"""Evaluate HAI detector quickly: detection count and attack overlap."""

from __future__ import annotations

from pathlib import Path

import pandas

from phos.referee.demo import _load_csv_dataset, hai_detector


def main() -> None:
    """Run the HAI detector against its prepared test split and print detection detail."""
    print("=" * 60)
    print("HAI evaluation")
    print("=" * 60)

    detector = hai_detector()
    print(f"Detector: {detector.name}")
    print()

    # Test data
    test_df = pandas.read_csv(Path("data/hai/hai-21.03-test-prepared.csv"))
    test_ds = _load_csv_dataset(Path("data/hai/hai-21.03-test-prepared.csv"), "hai-test")
    print(f"Loaded {len(test_ds.observations)} observations, running detector...")
    detections = detector.run(test_ds)
    print(f"Detector returned {len(detections)} detections")
    print()

    # Attack windows
    attack_rows = test_df[test_df["label"] == 1]
    total_attack_rows = len(attack_rows)
    print(f"Total test rows: {len(test_df)}")
    print(f"Attack rows: {total_attack_rows}")
    print(f"Normal rows: {len(test_df) - total_attack_rows}")
    print(f"Total detections: {len(detections)}")
    print()

    # Check detection features
    from collections import Counter

    features = Counter(d.feature for d in detections)
    print("Detection features:")
    for feat, count in features.most_common(20):
        print(f"  {feat}: {count}")
    print()

    # Check timestamps - convert detection timestamps to string format
    det_timestamps = set()
    for det in detections:
        det_timestamps.add(det.timestamp.strftime("%Y-%m-%dT%H:%M:%S+0000"))

    # Count detections that match attack timestamps
    attack_timestamps = set(attack_rows["timestamp"].tolist())
    normal_timestamps = set(test_df[test_df["label"] == 0]["timestamp"].tolist())

    det_in_attack = sum(1 for ts in det_timestamps if ts in attack_timestamps)
    det_outside_attack = sum(1 for ts in det_timestamps if ts in normal_timestamps)
    det_unknown = len(det_timestamps) - det_in_attack - det_outside_attack

    print(f"Unique detection timestamps: {len(det_timestamps)}")
    print(f"  Timestamps in attack windows: {det_in_attack}")
    print(f"  Timestamps in normal data: {det_outside_attack}")
    print(f"  Timestamps not found: {det_unknown}")
    print()

    # Count attack timestamps with at least one detection
    attack_ts_with_detection = det_timestamps & attack_timestamps
    print(
        f"Attack timestamps with detection: "
        f"{len(attack_ts_with_detection)}/{len(attack_timestamps)}"
    )
    print(
        f"Attack timestamp coverage: "
        f"{len(attack_ts_with_detection) / len(attack_timestamps) * 100:.1f}%"
    )
    print()

    # False alarm rate on normal timestamps
    normal_ts_with_detection = det_timestamps & normal_timestamps
    print(
        f"Normal timestamps with detection: "
        f"{len(normal_ts_with_detection)}/{len(normal_timestamps)}"
    )
    print(
        f"False alarm rate: "
        f"{len(normal_ts_with_detection) / len(normal_timestamps) * 100:.4f}% of normal timestamps"
    )


if __name__ == "__main__":
    main()
