# Writing your own detector and running it on the development pool

This page is for someone outside PHOS who wants to run their own detector against the referee
without asking anyone here a question. It has been written to be followed end to end. If a step
does not work, that is a fault in this page rather than in you, and it is worth reporting.

Nothing here requires access to PHOS's private repositories, its private seed pools, or its sealed
corpora. Everything it uses is in the public checkout.

## What you are running against

A published pool of simulated plants. Each plant is generated from a seed written down in
`data/development-pool.json`, in the five process families the generator offers. The plants are
models written from public descriptions of how such processes behave. **None of them is a capture
of a real plant, and a result on them is not a claim about catching a real attacker.**

Because the seeds are published, you can regenerate any plant and look at it as closely as you
like. That is the point: it is what makes the pool usable for building. It is also why a result
here says nothing about unseen attacks. A number from this pool describes how your detector
behaves; it is not evidence that it would catch something new.

## 1. Install

```bash
git clone <the public repository>
cd phos
uv sync
```

Python 3.12 is required and `uv` manages it. If `uv run python -c "import phos"` prints nothing,
the install worked.

## 2. Write a detector

A detector is any object with a `name` and a `run(dataset)` method. There is no base class to
subclass, nothing to register, and no import of anything PHOS-internal. The shape is:

```python
from datetime import datetime

from phos.eval import Dataset, Detection


class MyDetector:
    @property
    def name(self) -> str:
        return "my-detector"

    def run(self, dataset: Dataset) -> list[Detection]:
        # dataset.observations is every reading, with a timestamp, a feature name and a value.
        # dataset.attack_intervals is EMPTY here: the referee never hands a detector labels.
        return [
            Detection(
                timestamp=observation.timestamp,
                entity_ids=list(observation.entity_ids),
                score=0.0,          # your own anomaly score, any scale
                confidence=0.5,     # in [0, 1]; do not present it as calibrated unless it is
            )
            for observation in dataset.observations
            if <your rule>
        ]
```

Two things about the input that are easy to get wrong, and that the referee enforces rather than
merely advising:

- **You will not receive labels.** `dataset.attack_intervals` is empty and there is no unscored
  interval either. If you need ground truth to check yourself, generate a plant from a published
  seed yourself and read its `labels.json` in your own code, outside the exam.
- **The plant you are given is not named.** Its dataset name is an opaque token like
  `plant-3f2a91c4d0b17e55`, not `level-flow-771001`. The real name would carry the family and the
  seed, and handing that over would let a detector recover the plant without looking at any label
  file. Do not try to work around this; a detector that needs the seed is measuring the seed.

Then give it a factory, a function taking no arguments and returning your detector:

```python
def make() -> MyDetector:
    return MyDetector()
```

Put this in an importable module. The isolated run happens in a subprocess with `-I`, so the
module must be importable from the installed environment rather than by relative path.

## 3. Build the development exam

```python
from pathlib import Path

from phos.referee.development import development_exam, load

pool = load(Path("."))
exam = development_exam(pool, scorer_version="my-scorer-1", code_version=None, size=3, hours=4.0)
Path("exam.json").write_text(exam.to_json(), encoding="utf-8")
```

`size=3` keeps a first run quick. **Leave `hours` at its default of 24.** The default event
catalogue places five events of twenty to sixty minutes, and the generator refuses a run that
cannot hold them or would be more than a quarter event time. At 8 hours it refuses with "5 events
would leave only 64.35% of the run normal, below the 75.00% a corpus must keep", and below about
6 hours it refuses for want of room. If you want a faster first run, lower `size` and leave
`hours` alone.

## 4. Run it

```python
from pathlib import Path

from phos.referee.runner import run_exam

scores = run_exam(exam, my_detector, Path("work"))
```

`run_exam` generates every plant the exam names and scores your detector against each. Two things
it does for you that are worth knowing about:

- **Your detector is not given labels.** `score_plant` wraps it in `sealed_detector`, which strips
  the attack and unscored intervals from the corpus before passing it on. If you want to check
  yourself against ground truth, generate a plant from a published seed in your own code and read
  its `labels.json` there, outside the exam.
- **The plant's name is opaque.** A generated plant's real id is `level-flow-771001`, which carries
  the family and the seed. Your detector receives `plant-<16 hex characters>` instead. That is
  deliberate: a detector that can read the seed out of its input can regenerate the plant, and is
  then measuring the seed rather than the plant. Do not try to work around it.

If you want the isolation to be enforced by a process boundary as well as by the wrapper, use
`run_detector_isolated` instead. It runs a factory in a subprocess with only the telemetry
directory visible, and is what the integrity tests exercise. `run_exam` scores in-process with the
wrapper, which is faster and sufficient for the development pool.

## 5. Score and report

```python
from phos.referee.report import render_markdown, write_report
from phos.referee.scoring import aggregate

# Build one PlantScore per plant from phos.eval.evaluate, then:
score = aggregate("my-detector", plant_scores)
print(render_markdown(exam, score))
```

The report lists the worst plants first, gives each headline metric with a spread and a 95 percent
bootstrap interval, and ends with what the exam cannot tell you. Read that last section before
quoting any number from it.

## What the development pool cannot tell you

- Whether your detector would catch an attack it has never seen. Every seed here is published.
- Anything about a real plant. These are models.
- Anything about a real attacker. The attacks are scripted by the generator.
- How your detector compares with Atlas on unseen plants. That needs the private pool, which is
  not available, and a sealed scoring run, which is a separate thing with its own declaration.

## Where to look when something goes wrong

- **`IntegrityError` mentioning a non-zero exit.** Your factory raised. The subprocess's stderr is
  in the message; run the factory by hand to see it.
- **`ExamError` about pool size.** You asked for more plants than the pool holds.
- **An empty `attack_intervals` in your scoring.** You are looking at the detector's copy, not
  yours. Call `load_plant_dataset` in your own process.
- **`DevelopmentPoolError` about a missing file.** You are not in the checkout root.
