# Plants we built to break Atlas

**What this is:** a synthetic industrial world — plants whose **true internal state** is recorded
separately from what the sensors claim — plus a graded attack library and a harness whose job is
to find blind spots.

**Why it exists:** published datasets are rare, labelled oddly, and never designed to embarrass
*this* detector. If you only test on them, you will not know what Atlas cannot see.

## Crash-test dummies, not a victory lap

Car makers do not wait for motorway pile-ups to learn whether airbags work. They build dummies and
crash them **on purpose**.

PHOS built three plants (water treatment, a batch reactor, power generation). Each has:

- a physics-ish process that can be run unattacked for days
- sensors that can drift or lie
- a **truth record**: what the plant was *really* doing, even if a sensor was falsified

Attacks are **graded** (how blatant, what they touch) and kept from “fingerprinting” the detector:
the generator is not allowed to import Atlas. The breaking harness sits **above** both so neither
side gets a secret edge.

## Saturation and silence — two ways to fail

The harness marks a plant **saturated** if false positives exceed **1.0 per normal hour**. Above
that, it **refuses to quote a detection rate**. A perfect recall on a screaming board is not a
result.

After the first full battery:

| Plant | FP per normal hour | Status |
| --- | --- | --- |
| Water treatment | 0.39 | Detection claims may stand |
| Batch reactor | 3.59 (later 2.45 after settling work) | Saturated — claims struck |
| Power generation | 134.49 | Saturated — claims struck |

Of three plants, **one** supported a detection claim. The batch reactor was **wholly blind** until
a phase-aware fix; then it became **loud** rather than “working.” That move from silent to
saturated is progress you can measure, and still not a product claim.

Some attacks drove the plant into **danger** (true state outside anything seen in clean operation)
while Atlas reported all-clear. Those misses are judged against **truth**, not against a label we
might have written wrongly.

## These attacks are ours

People who could read the detector designed the library. A rate measured here is an **upper bound
on this library**, never a lower bound on reality. That caveat is load-bearing.

The same plants were later packed into hundreds of labelled windows under `dataset-library/`.
That is more dummies, not a public plant. The numbers, and the refusal to quote them as HAI or
distillation recall, are
[the dataset library note](14-the-dataset-library-is-not-a-public-corpus.md).

Four extra corpora (`04`–`07`) do not attack the plant at all. They attack **the file**: a
poisoned fitting window, a malformed row, out-of-range values, a truncated tail. Those were
measured as **software-survival** on a separate report
(`eval_runs/breaking/input-hostile-robustness.md`). Malformed input was **refused** loudly;
the others **completed**; none **crashed**. Surviving rubbish we wrote is not “Atlas is
secure,” not a detection rate, and not licence to merge those rows into the detection map
([ADR 0041](../docs/adr/0041-input-hostile-report-must-not-overwrite-detection.md)).

## What this is not

- Not a substitute for public corpora. Cross-plant generalisation still has to be earned on
  independent published plants ([the distillation column](12-batch-distillation-todays-work.md)).
  Packing our own attacks denser does not change that.
- Not malware, exploits, or live attack tooling. The constitution forbids that; this is an
  offline simulator with recorded truth.

## Where to read more

- Decisions: [ADR 0015](../docs/adr/0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0016](../docs/adr/0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0017](../docs/adr/0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
  [ADR 0029](../docs/adr/0029-synthetic-dataset-library-is-not-a-public-corpus.md)
- Packed expansion: [the dataset library](14-the-dataset-library-is-not-a-public-corpus.md)
- Map: `eval_runs/breaking/breaking-report.md`
- Software-survival (separate file): `eval_runs/breaking/input-hostile-robustness.md`
