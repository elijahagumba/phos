<p align="center">
  <img src="../.github/assets/readme/record.svg" width="600" alt="The record: everything PHOS has measured, including what didn't work. Each number here can be rebuilt from this repository. Each limit says what would lift it.">
</p>

<br>

### What Atlas measured

Atlas was tested on HAI, a public dataset recorded from a hardware-in-the-loop industrial testbed.
Treating the plant as one connected machine, rather than watching each sensor alone, cut false alarms
from **8,390** to **647** an hour without missing an attack. Grouping alarms by physical unit cut what
an operator would have to read by a further **12 times**.

That still leaves about **53** false alarms an hour, far more than any control room would accept, and
the slice measured holds only **two** attack windows. A later calibration fitted only on ordinary
operation reads **3.55** an hour; it is
[recorded beside the original number](adr/0083-calibrator-without-labelled-positives.md), not in place
of it.

[Read the Atlas report →](atlas-report.md)

<br>

### What PHOS refuses to claim

Twenty-six things PHOS will not say, each with the evidence that rules it out and what would change
that. Atlas cannot tell maintenance from an attack without the work order for that hour. It cannot
rank its own alert queue: the loudest 96 alerts on HAI contained none of the real attacks.

[Read the refusal register →](refusal-register.md)

<br>

### How the simulated plants avoid fooling us

Three simulated plants (water treatment, power generation and a batch reactor) record their true
internal state separately from what their sensors report, so a miss is judged against what actually
happened. The attacks were written by people who could read the detector. Five rules stop the
simulator from quietly favouring Atlas, and each was tested by breaking it on purpose to make sure
the build fails. Of the three plants, one currently supports a detection claim.

[Read the method →](synthetic-harness-method.md)

<br>

### What Sentiel found, and the first open bet

Sentiel, the engine that watches people, finds one of the two labelled insiders in CERT r3.1, a
public insider-threat dataset, and cannot see the other. The reason is arithmetic: at least 14 of
its 34 signals must move at once before anyone can be flagged. The fix, its success test and our
own prediction that it won't be enough were all written down before any code.

[Read Bet 001: the second insider →](bets/001-the-second-insider.md)

The bar Atlas and Sentiel v1 must clear was fixed before any comparison was run.

[Read Bet 002: what v1 has to do →](bets/002-atlas-and-sentiel-v1.md)

<br>

### Why it is built this way

More than eighty design decisions, each with what was chosen, what was rejected and what it cost.
Several exist only to record a result that did not work. Five places to start:

- [The joint model, and the model that lost](adr/0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md)
- [A tie is a refusal, not an alphabetical winner](adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)
- [There is no labelled public command capture](adr/0040-no-labelled-public-command-corpus.md)
- [The operator queue cannot be ranked](adr/0068-the-atlas-operator-queue-cannot-be-ranked.md)
- [The false alarms were the model's, not the plant's](adr/0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md)

[Browse every decision →](adr/)

<br>

<p align="center">
  <sub>The documents behind these pages are the working record, written as the research happened. They are dense by design.</sub>
</p>
