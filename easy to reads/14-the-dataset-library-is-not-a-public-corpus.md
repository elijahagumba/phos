# The dataset library is not a public corpus

**What this is:** packing the plants and personas **we already control** into hundreds of labelled
windows, scoring Atlas and Sentiel on them, and **refusing** to read those scores as HAI,
distillation, or CERT.

**Why it exists:** the cycle contracts want cross-plant detection, command ranking, and a SOC
budget that does not accuse a backup team. Public ICS and CERT remain licence-gated or too thin
to host hundreds of distinct adversarial windows. Expanding [the crash-test dummies](08-plants-we-built-to-break-atlas.md)
is a legitimate next measurement. Pretending the expansion *is* a public plant is not.

## Crash tests, packed denser — still dummies

Car makers do not become regulators by crashing more dummies. They learn more about *their*
airbags.

The library is that move:

- **OT:** three simulated plants × three seeds × six points on the difficulty dial, process
  manipulations in one pack and command/mimic windows in another. **18 packs, 342 labelled
  windows.** Benign events (backwash, recipe change, dispatch) are still scheduled by the plant,
  so maintenance is interleaved rather than simulated twice. Command windows that land on a
  genuine operator write are **nudged later** so ground truth has one answer for who moved the
  setpoint.
- **IT:** **48 people, 2,400 person-days.** Sixteen ordinary staff, busy backup and admin
  personas, role-change and off-hours fixtures, and eight labelled users (multi-family insider,
  credential reuse, loud HTTP). Rows are ordinary `Observation` counts — logons, files, hosts,
  devices. They are not malware, not a live directory, and not CERT r3.1.

Catalogues (`dataset-library/OT/catalogue.json`, `IT/catalogue.json`) are **committed**. Payloads
are **regenerated** and git-ignored, same rule as every other corpus: never commit the data.
Every catalogue line and every `eval_runs/log.jsonl` row carries the standing caveats. See
[ADR 0029](../docs/adr/0029-synthetic-dataset-library-is-not-a-public-corpus.md).

## Two persistence levers, defaults off

[Quieter queues](13-quieter-queues-and-honest-ranking.md) already changed the **unit** of an Atlas
alert (the whole moment) and the **shape** of a Sentiel score (volume, peers, families). What was
still missing was **time**.

- **Dwell.** A control room does not page a one-sample flicker. Consecutive jointly-unusual
  moments must hold before the first alert of that run (four samples here: two minutes at 30 s).
  The counter **resets** when the plant returns inside the envelope. Default remains one sample
  so the distillation gated row stays comparable.
- **Chronic volume.** A backup that runs all week is one administrative pattern, not eight thefts.
  Repeated out-of-band file/host volume on consecutive person-days is decayed. Day one is
  unchanged. A first thumb-drive connect is **never** decayed. Default remains off so the CERT
  10% row stays comparable.

Neither lever is a named-attack signature. Both are [ADR 0030](../docs/adr/0030-moment-dwell-and-chronic-volume-decay.md).

## What the library run actually said

Protocol: fit a joint Mahalanobis envelope (0.995 training quantile) on 48 h of attack-free
traffic per plant; score a per-signal Gaussian, the joint-moment detector, and the same detector
with dwell-4. Sentiel: fit on the train half; score identity, `:precision`, and
`:precision-chronic` at threshold **1.25** (a library-only bar, not CERT). Seed 11. **57**
harness rows. Means below are over three seeds.

**Process packs** — false positives per day-equivalent = `false_positive_rate × 24`.

| Plant | Joint recall | Joint FP/day | Dwell-4 recall | Dwell-4 FP/day |
| --- | ---: | ---: | ---: | ---: |
| Water | 0.097 | 0.0 | 0.069 | 0.0 |
| Power | 0.306 | 34.0 | 0.125 | 6.6 |
| Batch | 0.431 | 15.3 | 0.111 | 0.0 |

The per-signal Gaussian still floods (~15,000–25,000 false positives per day-equivalent). Joint
gating is the quiet detector. Dwell then trades remaining flicker for missed short windows.

**A 2.2/day mean across those dwell rows is not the 2–3/day contract.** Power process dwell is
still **6.6/day at 12.5% recall**. Water and batch sit at 0/day because they also sit at about
7–11% recall. Stealth, liar, and high-subtlety windows mostly stay inside the envelope — the same
trade already published on [the distillation column](12-batch-distillation-todays-work.md).

**Command/mimic packs** were scored with the **telemetry** joint detector, which is the wrong
instrument for unknown-master writes. Dwell-4 zeros power and batch command packs: those
excursions did not last two minutes. Command ranking on the breaking harness (attacks we wrote,
issuer kinds apart): known-station unique lead **0/16**; unknown-master unique lead **1/4** (moved
4/4). The 1/4 is a D2 diagnostic, not ≥70%
([listening to commands](07-atlas-listening-to-commands.md),
[who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md)). A ceiling tie is
a refusal, not an alphabetical unique winner
([ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)). Payloads for
the *library* packs were generated without packet capture.

**Sentiel fixture** (8 labelled users, 15 test days, 48 people). Alerts/day = alerts / 15 calendar
days for the whole population.

| Policy | Recall | Precision | Alerts/day | False positives |
| --- | ---: | ---: | ---: | ---: |
| Identity (PART 6B shape) | 8/8 | 0.222 | 36.0 | 420 |
| `:precision` | 8/8 | 0.298 | 22.8 | 240 |
| `:precision-chronic` | 8/8 | 0.298 | 22.8 | 240 |

The precision policy cuts the backup/admin queue. Chronic volume decay is unit-tested and **did
not move** this operating point: decayed backup days still clear 1.25. Precision 0.298 is not the
CERT wall. 22.8 alerts/day is this fixture, not CERT r3.1.

## What this number does not license

- Not HAI, BATADAL, distillation, or CERT recall. Distillation perturbation recall is a different
  ruler (~49 moment-alerts/day at 0.29 perturbation recall) and was **not** re-run here.
- Not ≤2–3 Atlas alerts/day on a public plant with high recall. Not 10× false-alarm reduction on
  every dataset.
- Not ≥70% command-window ranking. Not a SOC-ready Sentiel precision.
- Not a rewritten covariance, not fitted feature weights, not calibrated hypothesis confidence.
- Not a live plant or a live company.

## What you can assume exists now

- Layout and caveats: `dataset-library/README.md`
- Generators and scoring: `src/phos/library/`; `scripts/generate_dataset_library.py`,
  `scripts/evaluate_dataset_library.py`
- Compact table of the 57 rows: `eval_runs/dataset-library-summary.json` (the log still wins)
- Decisions: [ADR 0029](../docs/adr/0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0030](../docs/adr/0030-moment-dwell-and-chronic-volume-decay.md)
- Engineering log: `PROGRESS.md` cycle section “synthetic dataset library and persistence levers”
