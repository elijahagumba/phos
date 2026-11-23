"""Sequential consistency detection against ICSSim dev data (real plant telemetry).

Tests the change_run + margin sequential walk detector on real ICSSim process data:
- Fit longest_run on normal-* process.csv (attack-free training)
- Score on mixed-* process.csv (with attacks)
- Use events.json to label attack windows
- Count detections inside vs outside attack windows

Honest scope: one evidence stream (sequential consistency) on real ICSSim data,
not the full fused atlas_detector() (which requires level_flow topology and can't
score ICSSim signals).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy

from phos.atlas.sequential_consistency import change_run

DATA = Path("data/phos-icssim-dev")
NORMAL_DIRS = sorted(DATA.glob("normal-*"))
MIXED_DIRS = sorted(DATA.glob("mixed-*"))


def load_process_csv(path: Path) -> dict[str, list[float]]:
    """Return {column: [values]} from process.csv."""
    lines = path.read_text().strip().splitlines()
    header = lines[0].split(",")
    col_idx = {name: i for i, name in enumerate(header)}
    values: dict[str, list[float]] = {name: [] for name in header}
    for line in lines[1:]:
        fields = line.split(",")
        for name, i in col_idx.items():
            try:
                values[name].append(float(fields[i]))
            except ValueError:
                values[name].append(0.0)
    return values


def load_events(path: Path) -> list[dict]:
    """Return events from events.json."""
    return json.loads(path.read_text())


def main() -> None:
    # --- Fit on normal data ---
    normal_series: list[numpy.ndarray] = []
    for d in NORMAL_DIRS:
        proc = load_process_csv(d / "process.csv")
        normal_series.append(numpy.array(proc["tank_level_max"], dtype=numpy.float64))
        print(f"Normal {d.name}: {len(normal_series[-1])} samples")

    # Longest run across all normal training data
    longest_run = 0
    for s in normal_series:
        runs = change_run(s)
        longest_run = max(longest_run, int(runs.max(initial=0.0)))
    margin = 1
    threshold = float(longest_run) + margin
    print(f"\nFitted on {len(NORMAL_DIRS)} normal plants")
    print(f"Longest attack-free run: {longest_run} samples")
    print(f"Detection threshold: > {threshold} samples (margin={margin})")

    # --- Score on mixed data ---
    total_hits = 0
    total_inside_attack = 0
    total_outside_attack = 0

    for d in MIXED_DIRS:
        proc = load_process_csv(d / "process.csv")
        series = numpy.array(proc["tank_level_max"], dtype=numpy.float64)
        runs = change_run(series)

        # Load attack windows from events.json
        events = load_events(d / "events.json")
        attack_windows = [
            (float(e["start"]), float(e["end"]))
            for e in events
            if e.get("label") == "attack"
        ]

        # Timestamp column is epoch seconds, 1 sample per second
        timestamps = numpy.array(proc["timestamp"], dtype=numpy.float64)
        epoch = timestamps[0]

        hits = 0
        inside = 0
        outside = 0
        for i in range(len(runs)):
            if runs[i] > threshold:
                hits += 1
                t = timestamps[i] - epoch  # seconds into run
                in_attack = any(s <= t <= e for s, e in attack_windows)
                if in_attack:
                    inside += 1
                else:
                    outside += 1

        total_hits += hits
        total_inside_attack += inside
        total_outside_attack += outside

        # Summarise attack types
        attack_types = [
            (e["kind"], e["start"], e["end"])
            for e in events
            if e.get("label") == "attack"
        ]
        print(
            f"\n{d.name}: {hits} hits ({inside} inside attack, {outside} outside)"
        )
        for kind, s, e in attack_types:
            hits_in = sum(
                1
                for i in range(len(runs))
                if runs[i] > threshold and s <= (timestamps[i] - epoch) <= e
            )
            if hits_in > 0:
                print(f"  {kind} [{s:.1f}-{e:.1f}s]: {hits_in} hits")

    print(f"\n=== SUMMARY ===")
    print(f"Mixed plants scored: {len(MIXED_DIRS)}")
    print(f"Total sequential hits above threshold: {total_hits}")
    print(f"Hits inside attack windows: {total_inside_attack}")
    print(f"Hits outside attack windows (false alarms): {total_outside_attack}")


if __name__ == "__main__":
    main()
