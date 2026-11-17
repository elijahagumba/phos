"""Score ICSSim dev4-walk real plant data with the ICSSim AtlasDetector.

Tests the fused Atlas detector (Mahalanobis + consistency + sequential + walk + code law)
against real ICSSim telemetry from data/phos-icssim-dev4-walk/.

- Normal plants (normal-96801/2/3): should have zero or very few detections (false alarms)
- Subfloor plants (subfloor-96811..96818): each has a subfloor_walk attack on tank_level_max
  (setpoint walks from 6.5 to 7.5 over 720 seconds). Should be detected during the attack window.

Honest scope: real ICSSim telemetry, MIT-licensed, Atlas's own domain.
"""

from __future__ import annotations

import json
from pathlib import Path

from phos.referee.demo import _load_icssim_csv, icssim_detector

DATA = Path("data/phos-icssim-dev4-walk")


def main() -> None:
    """Score the ICSSim detector on real dev4-walk telemetry and print detection detail."""
    print("Building ICSSim AtlasDetector (fitted on data/phos-icssim-dev/normal-*)")
    detector = icssim_detector()
    print(f"Detector: {detector.name}")
    print()

    # --- Score normal plants (false alarm check) ---
    print("=== NORMAL PLANTS (false alarm check) ===")
    normal_dirs = sorted(DATA.glob("normal-*"))
    total_normal_detections = 0
    for d in normal_dirs:
        ds = _load_icssim_csv(d / "process.csv", d.name)
        detections = detector.run(ds)
        total_normal_detections += len(detections)
        print(f"  {d.name}: {len(detections)} detections")
    print(f"  Total normal detections: {total_normal_detections}")
    print()

    # --- Score subfloor plants (detection check) ---
    print("=== SUBFLOOR PLANTS (subfloor_walk detection) ===")
    subfloor_dirs = sorted(DATA.glob("subfloor-*"))
    total_subfloor_detections = 0
    total_inside_attack = 0
    detected_plants = 0

    for d in subfloor_dirs:
        ds = _load_icssim_csv(d / "process.csv", d.name)
        detections = detector.run(ds)
        total_subfloor_detections += len(detections)

        # Load attack windows from events.json
        events = json.loads((d / "events.json").read_text())
        attack_windows = [
            (float(e["start"]), float(e["end"]))
            for e in events
            if e.get("label") == "attack" and e.get("kind") == "subfloor_walk"
        ]

        # Convert detection timestamps to seconds since epoch
        # ICSSim epoch is 1767225600.0 (from manifest); attack windows in events.json
        # are relative to that epoch.
        epoch = 1767225600.0
        inside_attack = 0
        outside_attack = 0
        for det in detections:
            det_ts = det.timestamp.timestamp() - epoch
            in_attack = any(s <= det_ts <= e for s, e in attack_windows)
            if in_attack:
                inside_attack += 1
            else:
                outside_attack += 1

        total_inside_attack += inside_attack
        if detections:
            detected_plants += 1

        print(
            f"  {d.name}: {len(detections)} detections "
            f"({inside_attack} inside subfloor_walk window, {outside_attack} outside)"
        )
        if attack_windows:
            print(
                f"    subfloor_walk window: "
                f"{attack_windows[0][0]:.1f}s - {attack_windows[0][1]:.1f}s"
            )

    print()
    print("=== SUMMARY ===")
    print(f"Normal plants: {len(normal_dirs)}, total detections: {total_normal_detections}")
    print(f"Subfloor plants: {len(subfloor_dirs)}, total detections: {total_subfloor_detections}")
    print(f"  Detections inside subfloor_walk windows: {total_inside_attack}")
    print(f"  Plants with at least one detection: {detected_plants}/{len(subfloor_dirs)}")


if __name__ == "__main__":
    main()
