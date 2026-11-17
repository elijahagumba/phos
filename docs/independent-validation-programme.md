# PHOS Independent Validation Programme

**Criticise the simulator. Don't validate it.**

The PHOS simulation engine (`src/phos/synth/`) generates industrial control system data with perfect
ground truth. It is a model of reality, not reality. Its realism is a claim to be defended — not a
property to be assumed.

PHOS does not invite researchers to *validate* the simulator. Validation implies endorsement, and PHOS
has not earned the right to endorse. PHOS invites researchers to *criticise* it — to publish where it is
wrong, where its assumptions are simplified, which attack scenarios it represents and which it fails to
represent, whether its randomisation genuinely produces meaningful diversity, and whether Atlas performs
differently across independently generated environments.

## What researchers may publish

A researcher's independent publication may state:

| Publication target | What it means |
|---|---|
| Where the simulator accurately represents industrial behaviour | Which physical behaviours, control loops, and process dynamics the simulator gets right, with evidence |
| Where its assumptions are simplified | Which physics, noise, control-network, or operator behaviours the simulator leaves out or models too cleanly |
| Which attack scenarios it represents | Which of the graded attack library's scenarios (blatant, stealth drift, correlation break, liar, mimic, rogue command, mimic command, input-hostile) map to real attack patterns |
| Which scenarios it fails to represent | Attack types, adversary behaviours, or physical phenomena the simulator cannot produce |
| Whether its randomisation genuinely produces meaningful diversity | Whether seed-drawn plant variation (tank sizes, controller tunings, instrument noise, tag naming) creates environments that test different detector behaviours, or whether all seeds look the same to Atlas |
| Whether Atlas performs differently across independently generated environments | Whether recall, false-positive rate, and grouping behaviour vary across seeds, plant families, and difficulty levels — or whether Atlas memorises one plant shape |

## What researchers must attach

Every number published about Atlas's performance on synthetic corpora must carry:

1. **`SYNTHETIC-DERIVED`** — the result measures Atlas against a model of a plant, not against reality
2. **`MODEL_NOT_REALITY_CAVEAT`** — this is a model of a plant, not reality
3. **`ATTACKS_ARE_OURS_CAVEAT`** — these are attacks PHOS designed; a detection rate is an upper bound on this library, never a lower bound on reality
4. **`SYNTHETIC_TOPOLOGY_CAVEAT`** — the topology is declared by PHOS, not derived from plant documentation
5. **`INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT`** — input-hostile survival is software robustness, not security

A result read without these caveats is misread.

## What PHOS will not do

PHOS will not:
- Endorse any researcher's validation of the simulator
- Quote any researcher's results as PHOS detection claims
- Compare synthetic results against frozen public rows (HAI 646.58, grouped 53.26, distillation 18.72, CERT 6B 0.104)
- Allow synthetic recall/FP/precision to be quoted as field detection rates
- Allow claims of ≥70%, 10×, or 2–3 alerts/day from synthetic data
- Print hypothesis confidence as a user-facing number

## How to use the simulator

Generate plants:

```bash
uv run python scripts/generate_plants.py list-families
uv run python scripts/generate_plants.py generate level_flow 2026001
uv run python scripts/generate_plants.py verify data/plants/level-flow-2026001
```

Generate attack corpora:

```bash
uv run python scripts/generate_attacks.py --all
uv run python scripts/generate_attacks.py --dataset synth-attack-water-treatment-graded
```

Run Atlas against synthetic corpora (D3):

```bash
uv run python scripts/evaluate_atlas_synthetic.py
uv run python scripts/evaluate_atlas_synthetic.py --no-log
```

Every D3 report is written to `eval_runs/synth/` — never to `eval_runs/log.jsonl` — and carries
`SYNTHETIC-DERIVED` plus the standing caveats.

## Licence

Released under the [PolyForm Noncommercial License 1.0.0](../LICENSE). Noncommercial use,
research, education, and personal experimentation are permitted purposes. Commercial use requires a
separate licence.

## Standing caveats (carried in every corpus)

> **MODEL_NOT_REALITY_CAVEAT:** this is a model of a plant, not reality. Good scores here mean Atlas
> handles our model of a plant, not evidence of handling a real one.
>
> **ATTACKS_ARE_OURS_CAVEAT:** these are attacks we designed. A detection rate measured here is an
> upper bound on this library, never a lower bound on reality. A suspiciously good score is a leaked
> fingerprint until proven otherwise.
>
> **SYNTHETIC_TOPOLOGY_CAVEAT:** the topology is declared by us, not derived from plant documentation.
>
> **INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT:** input-hostile survival is not detection.

## Anti-bias construction (enforced in the generator)

1. The generator may not reference the detector
2. Attacks are specified by intent, never by signature
3. Every scenario carries real-world provenance
4. A mandatory band of cases the detector should miss
5. The method is published, including its failures
