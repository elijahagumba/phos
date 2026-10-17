#!/usr/bin/env python3
"""Diagnose every T1 liar run on one development seed, and record each in a learning ledger.

Learning engine S2 (ADR 0119). The first thing this script does is try to fail: on seed 4242 it
checks that the runner reproduces ADR 0114's passes (water none, power 0.0 and 0.2, batch 0.0 and
0.4) before writing anything. Held-out seeds are refused. Corpora are generated into a temporary
directory and never committed.

Usage::

    uv run python scripts/diagnose_liar_runs.py                # seed 4242
    uv run python scripts/diagnose_liar_runs.py --seed 4242 --out eval_runs/learning
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.breaking.corpus import load_attack_corpus, load_normal_corpus  # noqa: E402
from phos.breaking.harness import BreakingConfig  # noqa: E402
from phos.breaking.liar import fit_inlet, inlet_calibrator, liar_corpus_config  # noqa: E402
from phos.breaking.liar_diagnosis import (  # noqa: E402
    LiarDiagnosis,
    diagnose_corpus,
    learning_records,
    refuse_held_out,
    write_report,
)
from phos.eval.learning_records import LearningLedger  # noqa: E402
from phos.eval.liar_declaration import LIAR_PLANTS  # noqa: E402
from phos.eval.report import current_git_commit  # noqa: E402
from phos.library.ot import SEEDS, ot_trains  # noqa: E402
from phos.synth.attacks.generate import generate_attack_dataset  # noqa: E402
from phos.synth.generate import generate_dataset  # noqa: E402

logger = logging.getLogger("phos.diagnose_liar")

#: ADR 0114 §2: on development seed 4242, the subtleties that pass, per plant.
ADR_0114_PASSES: Final = {
    "water-treatment": (),
    "power-generation": (0.0, 0.2),
    "batch-reactor": (0.0, 0.4),
}


def reproduces_adr_0114(diagnoses: Sequence[LiarDiagnosis]) -> bool:
    """Return whether seed 4242's passes equal ADR 0114's table, plant by plant."""
    found = {
        plant: tuple(
            sorted(d.run.subtlety for d in diagnoses if d.run.plant_id == plant and d.run.passes)
        )
        for plant in ADR_0114_PASSES
    }
    return found == ADR_0114_PASSES


def diagnose_seed(seed: int, workdir: Path, ledger: LearningLedger) -> list[LiarDiagnosis]:
    """Generate, run and diagnose every liar plant's corpus on ``seed``.

    Raises:
        ValueError: If ``seed`` is held out.
    """
    refuse_held_out(seed)
    settings = BreakingConfig()
    commit = current_git_commit(REPO_ROOT)
    trains = {config.plant_id: config for config in ot_trains()}
    out: list[LiarDiagnosis] = []
    for plant in LIAR_PLANTS:
        normal = load_normal_corpus(generate_dataset(trains[plant], workdir, with_capture=False)[0])
        inlet = fit_inlet(normal)
        development = [
            load_attack_corpus(
                generate_attack_dataset(liar_corpus_config(plant, s), workdir, with_capture=False)[
                    0
                ]
            )
            for s in SEEDS
        ]
        calibrator = inlet_calibrator(inlet, development, seed=settings.seed)
        corpus = load_attack_corpus(
            generate_attack_dataset(liar_corpus_config(plant, seed), workdir, with_capture=False)[0]
        )
        out.extend(diagnose_corpus(corpus, normal, inlet, calibrator, settings, ledger, commit))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Run the diagnosis and write the report and ledger."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval_runs" / "learning")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ledger_path = args.out / f"liar-dev-s{args.seed}.ledger.jsonl"
    if ledger_path.exists():
        print(f"{ledger_path} exists; a ledger is never overwritten", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        scratch = LearningLedger(Path(tmp) / "ledger.jsonl")
        diagnoses = diagnose_seed(args.seed, Path(tmp), scratch)
        if args.seed == 4242 and not reproduces_adr_0114(diagnoses):
            print(
                "seed 4242 does not reproduce ADR 0114's passes; nothing written", file=sys.stderr
            )
            return 1
        args.out.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes((Path(tmp) / "ledger.jsonl").read_bytes())
    ledger = LearningLedger(ledger_path)  # verifies the copy
    write_report(diagnoses, args.out / f"liar-dev-s{args.seed}.diagnosis.json", args.seed)
    records = learning_records(diagnoses, ledger)
    (args.out / f"liar-dev-s{args.seed}.learning.jsonl").write_text(
        "".join(record.model_dump_json() + "\n" for record in records), encoding="utf-8"
    )
    for d in sorted(diagnoses, key=lambda d: (d.run.plant_id, d.run.subtlety)):
        peak = "-" if d.peak_loop is None else f"{d.peak_loop:.3f}"
        print(f"{d.run.plant_id:17} {d.run.subtlety:.1f}  {d.mechanism:26} peak={peak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
