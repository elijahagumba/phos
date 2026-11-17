"""Evaluate BATADAL and HAI detectors: detection rate and false alarm rate on attack windows."""

from __future__ import annotations

from pathlib import Path

import pandas

from phos.referee.demo import _load_csv_dataset, batadal_detector, hai_detector


def attack_windows(df: pandas.DataFrame) -> list[tuple[int, int]]:
    """Return list of (start_row, end_row) for attack windows in test data."""
    windows: list[list[int]] = []
    in_attack = False
    for raw_i, row in df.iterrows():
        i = int(raw_i)  # type: ignore[call-overload]
        if row["label"] == 1 and not in_attack:
            windows.append([i, i])
            in_attack = True
        elif row["label"] == 0 and in_attack:
            windows[-1][1] = i - 1
            in_attack = False
    if in_attack:
        windows[-1][1] = len(df) - 1
    return [(start, end) for start, end in windows]


def overlaps_any(detection_row: int, windows: list[tuple[int, int]]) -> bool:
    """Check if a detection row index falls within any attack window."""
    return any(start <= detection_row <= end for start, end in windows)


def evaluate_batadal() -> None:
    """Run the BATADAL detector against its prepared test split and print the result."""
    print("=" * 60)
    print("BATADAL evaluation")
    print("=" * 60)

    detector = batadal_detector()
    print(f"Detector: {detector.name}")
    print()

    # Test data
    test_df = pandas.read_csv(Path("data/batadal/batadal-test-prepared.csv"))
    test_ds = _load_csv_dataset(Path("data/batadal/batadal-test-prepared.csv"), "batadal-test")
    detections = detector.run(test_ds)

    windows = attack_windows(test_df)
    total_attack_rows = sum(end - start + 1 for start, end in windows)

    det_in_attack = 0
    det_outside_attack = 0
    for det in detections:
        # Find row index for this detection timestamp
        det_ts = det.timestamp
        matching_rows = test_df.index[test_df["timestamp"] == det_ts].tolist()
        if matching_rows:
            row_idx = matching_rows[0]
            if overlaps_any(row_idx, windows):
                det_in_attack += 1
            else:
                det_outside_attack += 1

    attack_rows_with_detection = set()
    for det in detections:
        det_ts = det.timestamp
        matching_rows = test_df.index[test_df["timestamp"] == det_ts].tolist()
        for row_idx in matching_rows:
            if overlaps_any(row_idx, windows):
                attack_rows_with_detection.add(row_idx)

    print(f"Total test rows: {len(test_ds.observations)}")
    print(f"Attack rows: {total_attack_rows} (in {len(windows)} windows)")
    print(f"Total detections: {len(detections)}")
    print(f"  Detections inside attack windows: {det_in_attack}")
    print(f"  Detections outside attack windows: {det_outside_attack}")
    print(
        f"  Unique attack rows with detection: "
        f"{len(attack_rows_with_detection)}/{total_attack_rows}"
    )
    print(
        f"  Attack row coverage: {len(attack_rows_with_detection) / total_attack_rows * 100:.1f}%"
    )
    print(
        f"  False alarm rate: "
        f"{det_outside_attack / (len(test_df) - total_attack_rows) * 100:.4f}% of normal rows"
    )
    print()


def evaluate_hai() -> None:
    """Run the HAI detector against its prepared test split and print the result."""
    print("=" * 60)
    print("HAI evaluation")
    print("=" * 60)

    detector = hai_detector()
    print(f"Detector: {detector.name}")
    print()

    # Test data
    test_df = pandas.read_csv(Path("data/hai/hai-21.03-test-prepared.csv"))
    test_ds = _load_csv_dataset(Path("data/hai/hai-21.03-test-prepared.csv"), "hai-test")
    detections = detector.run(test_ds)

    windows = attack_windows(test_df)
    total_attack_rows = sum(end - start + 1 for start, end in windows)

    det_in_attack = 0
    det_outside_attack = 0
    for det in detections:
        det_ts = det.timestamp
        matching_rows = test_df.index[test_df["timestamp"] == det_ts].tolist()
        if matching_rows:
            row_idx = matching_rows[0]
            if overlaps_any(row_idx, windows):
                det_in_attack += 1
            else:
                det_outside_attack += 1

    attack_rows_with_detection = set()
    for det in detections:
        det_ts = det.timestamp
        matching_rows = test_df.index[test_df["timestamp"] == det_ts].tolist()
        for row_idx in matching_rows:
            if overlaps_any(row_idx, windows):
                attack_rows_with_detection.add(row_idx)

    print(f"Total test rows: {len(test_ds.observations)}")
    print(f"Attack rows: {total_attack_rows} (in {len(windows)} windows)")
    print(f"Total detections: {len(detections)}")
    print(f"  Detections inside attack windows: {det_in_attack}")
    print(f"  Detections outside attack windows: {det_outside_attack}")
    print(
        f"  Unique attack rows with detection: "
        f"{len(attack_rows_with_detection)}/{total_attack_rows}"
    )
    print(
        f"  Attack row coverage: {len(attack_rows_with_detection) / total_attack_rows * 100:.1f}%"
    )
    print(
        f"  False alarm rate: "
        f"{det_outside_attack / (len(test_df) - total_attack_rows) * 100:.4f}% of normal rows"
    )
    print()


def main() -> None:
    """Run both the BATADAL and HAI detectors and print each result."""
    evaluate_batadal()
    evaluate_hai()


if __name__ == "__main__":
    main()
