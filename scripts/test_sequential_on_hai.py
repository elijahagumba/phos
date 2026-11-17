"""Sequential consistency detection against HAI 21.03 real plant data.

This tests the sequential walk-detection statistic (change_run) directly on
real HAI telemetry, not simulated dev seeds. HAI signals use different names
than level_flow (P1_STSP instead of tank_level_max), so atlas_detector()
cannot score HAI — AtlasEngine raises TopologyError. Instead we apply the
same change_run + margin logic to HAI's setpoint signals directly.

This is honest scope: one evidence stream on real data, not the full fused
detector. Results are labelled as such.
"""

from __future__ import annotations

from pathlib import Path

import numpy

from phos.atlas.sequential_consistency import change_run

DATA = Path("data/hai")
TRAIN = DATA / "hai-21.03-train-prepared.csv"
TEST = DATA / "hai-21.03-test-prepared.csv"


def load_csv(path: Path) -> tuple[list[str], list[str], dict[str, list[float]]]:
    """Return (columns, timestamps, {column: [values]})."""
    lines = path.read_text().strip().splitlines()
    header = lines[0].split(",")
    ts_col = header.index("timestamp")
    label_col = header.index("label")
    value_cols = [i for i in range(len(header)) if i not in (ts_col, label_col)]
    col_names = [header[i] for i in value_cols]

    timestamps: list[str] = []
    values: dict[str, list[float]] = {name: [] for name in col_names}
    for line in lines[1:]:
        fields = line.split(",")
        timestamps.append(fields[ts_col])
        for i, name in zip(value_cols, col_names, strict=True):
            try:
                values[name].append(float(fields[i]))
            except ValueError:
                values[name].append(0.0)
    return col_names, timestamps, values


def main() -> None:
    """Score HAI's setpoint columns directly with the sequential change-run statistic."""
    train_cols, _train_ts, train_vals = load_csv(TRAIN)
    test_cols, test_ts, test_vals = load_csv(TEST)

    # Find setpoint-like columns in HAI (anything ending in STSP).
    train_setpoints = [c for c in train_cols if c.upper().endswith("STSP")]
    test_setpoints = [c for c in test_cols if c.upper().endswith("STSP")]
    print(f"Train setpoint columns: {train_setpoints}")
    print(f"Test setpoint columns: {test_setpoints}")
    print(f"Train rows: {len(_train_ts)}, Test rows: {len(test_ts)}")

    # Fit sequential model on train: longest run per setpoint column.
    models: dict[str, tuple[int, int]] = {}  # tag -> (column, longest_run)
    for tag in train_setpoints:
        col = train_cols.index(tag)
        series = numpy.array(train_vals[tag], dtype=numpy.float64)
        runs = change_run(series)
        longest = int(runs.max(initial=0.0))
        models[tag] = (col, longest)
        print(f"  {tag}: col={col}, longest attack-free run={longest} samples")

    # Score test: count changes per setpoint column above threshold.
    margin = 1
    detections = 0
    detections_by_tag: dict[str, int] = {}
    for tag, (_col, longest_run) in models.items():
        series = numpy.array(test_vals[tag], dtype=numpy.float64)
        runs = change_run(series)
        threshold = float(longest_run) + margin
        hits = int((runs > threshold).sum())
        detections += hits
        detections_by_tag[tag] = hits
        print(f"\n{tag}: threshold={threshold}, hits={hits}/{len(runs)}")

    # Count attack-labelled rows in test.
    attack_rows = 0
    with open(TEST) as f:
        header = f.readline().strip().split(",")
        label_idx = header.index("label")
        for line in f:
            fields = line.strip().split(",")
            if int(fields[label_idx]) == 1:
                attack_rows += 1
    print(f"\nAttack-labelled rows in test: {attack_rows} / {len(test_ts)}")
    print(f"Total sequential hits above threshold: {detections}")

    # Show where hits fall vs attack windows.
    attack_starts: list[int] = []
    attack_ends: list[int] = []
    in_attack = False
    with open(TEST) as f:
        header = f.readline().strip().split(",")
        label_idx = header.index("label")
        for row_i, line in enumerate(f):
            fields = line.strip().split(",")
            is_attack = int(fields[label_idx]) == 1
            if is_attack and not in_attack:
                attack_starts.append(row_i)
                in_attack = True
            elif not is_attack and in_attack:
                attack_ends.append(row_i - 1)
                in_attack = False
    if in_attack:
        attack_ends.append(len(test_ts) - 1)
    print(f"Attack windows: {list(zip(attack_starts, attack_ends, strict=True))}")

    # For each tag, count hits inside attack windows.
    for tag, (_col, longest_run) in models.items():
        series = numpy.array(test_vals[tag], dtype=numpy.float64)
        runs = change_run(series)
        threshold = float(longest_run) + margin
        hit_indices = [i for i in range(len(runs)) if runs[i] > threshold]
        inside_attack = sum(
            1
            for i in hit_indices
            if any(s <= i <= e for s, e in zip(attack_starts, attack_ends, strict=True))
        )
        print(f"  {tag}: {len(hit_indices)} hits, {inside_attack} inside attack windows")


if __name__ == "__main__":
    main()
