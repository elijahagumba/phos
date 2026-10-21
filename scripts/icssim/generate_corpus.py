"""Generate a declared PHOS ICSSim corpus: every run of one role, one directory per run (ADR 0122).

Usage, from the lab root, with any Python 3.11+ (this file uses only the standard library):

    python scripts/icssim/generate_corpus.py setup                # ICSSim at the pinned commit
    python scripts/icssim/generate_corpus.py development          # data/phos-icssim-dev/
    python scripts/icssim/generate_corpus.py held-out             # data/phos-icssim-heldout/

``setup`` clones ICSSim at `ICSSIM_COMMIT` into `ICSSIM_DIR` (under ``data/``, so git never sees
it) and makes a virtual environment there with ICSSim's two dependencies, at the versions the
harness was checked against. Each run is written once; an existing non-empty run
directory is skipped, so an interrupted batch resumes. **Nothing here reads a label.** The held-out
role may be generated at any time, and must not be opened until a declaration says so.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).resolve().parent / "phos_icssim.py"
ICSSIM_URL = "https://github.com/AlirezaDehlaghi/ICSSIM.git"
ICSSIM_COMMIT = "bcfd1844d3f063850c69f2643f6a052bac03d8ec"
ICSSIM_LICENSE_SHA256 = "e54f199223498684eba0a54368c4638b217edf8cb82f07427d8b756e7eb2d8a8"
ICSSIM_DIR = ROOT / "data" / "icssim-source"  # under data/, so git never sees it (ADR 0006)
VENV = ICSSIM_DIR / "venv"
DEPENDENCIES = ("pyModbusTCP==0.3.1", "python-memcached==1.62")

#: The declared runs (ADR 0122, extended by ADR 0285). Seeds are fixed here, before any run is
#: scored. The ``2`` roles are the corpus with the `creep_many` class; the originals are frozen as
#: the record lane 1's held-out score rests on (ADR 0276) and are never regenerated over.
RUNS: dict[str, dict[str, object]] = {
    "development": {
        "directory": "phos-icssim-dev",
        "runs": [("normal", seed) for seed in (96001, 96002, 96003)]
        + [("mixed", seed) for seed in range(96011, 96021)],
    },
    "held-out": {
        "directory": "phos-icssim-heldout",
        "runs": [("mixed", seed) for seed in range(96101, 96121)],
    },
    "development2": {
        "directory": "phos-icssim-dev2",
        "runs": [("normal", seed) for seed in (96201, 96202, 96203)]
        + [("mixed2", seed) for seed in range(96211, 96221)],
    },
    "held-out2": {
        "directory": "phos-icssim-heldout2",
        "runs": [("mixed2", seed) for seed in range(96301, 96321)],
    },
    # ADR 0295. `held-out3` may be generated and must not be opened until a declaration names
    # the score. Generating is not opening. This session does not generate it.
    "development3": {
        "directory": "phos-icssim-dev3",
        "runs": [("normal", seed) for seed in (96401, 96402, 96403)]
        + [("mixed3", seed) for seed in range(96411, 96415)],
    },
    "held-out3": {
        "directory": "phos-icssim-heldout3",
        "runs": [("mixed3", seed) for seed in range(96501, 96521)],
    },
}


def setup() -> None:
    """Clone ICSSim at the pinned commit and make its virtual environment."""
    import hashlib

    if not (ICSSIM_DIR / "repo").exists():
        ICSSIM_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", ICSSIM_URL, str(ICSSIM_DIR / "repo")], check=True)
    subprocess.run(
        ["git", "-C", str(ICSSIM_DIR / "repo"), "checkout", "-q", ICSSIM_COMMIT], check=True
    )
    licence = hashlib.sha256((ICSSIM_DIR / "repo" / "LICENSE").read_bytes()).hexdigest()
    if licence != ICSSIM_LICENSE_SHA256:
        raise SystemExit(f"ICSSim's LICENSE changed (sha256 {licence}); stop and read it")
    if not VENV.exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(VENV / "bin" / "pip"), "install", "-q", *DEPENDENCIES], check=True)
    print(f"ICSSim {ICSSIM_COMMIT[:7]} ready in {ICSSIM_DIR}")


def generate(role: str, time_scale: float) -> None:
    """Generate every declared run of ``role`` that does not exist yet."""
    spec = RUNS[role]
    base = ROOT / "data" / str(spec["directory"])
    base.mkdir(parents=True, exist_ok=True)
    python = VENV / "bin" / "python"
    if not python.exists():
        raise SystemExit("run `generate_corpus.py setup` first")
    for scenario, seed in spec["runs"]:  # type: ignore[attr-defined]
        out = base / f"{scenario}-{seed}"
        if out.exists() and (out / "manifest.json").exists():
            print(f"skip {out.name}: already generated")
            continue
        if out.exists():
            raise SystemExit(f"{out} exists without a manifest; an interrupted run. Remove it.")
        print(f"generating {out.name}")
        subprocess.run(
            [
                str(python),
                str(HARNESS),
                "--icssim",
                str(ICSSIM_DIR / "repo" / "src"),
                "--out",
                str(out),
                "--scenario",
                scenario,
                "--seed",
                str(seed),
                "--time-scale",
                str(time_scale),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )


def main() -> None:
    """Run ``setup`` or generate one role's declared runs."""
    parser = argparse.ArgumentParser(description="Generate the declared PHOS ICSSim corpus.")
    parser.add_argument("what", choices=["setup", *RUNS])
    parser.add_argument("--time-scale", type=float, default=20.0)
    args = parser.parse_args()
    if args.what == "setup":
        setup()
    else:
        generate(args.what, args.time_scale)


if __name__ == "__main__":
    main()
