# ADR 0090 — The authors' HAI pipeline matches our detectors, not the paper

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap week 1, reproduction check
- **Depends on:** [ADR 0089](0089-three-published-hai-detectors.md)

## Context

Roadmap §2 is frozen at `93156a51d4cd2e2be5684ca817306d2db07c0be7`. This record does not
edit §2. §2.0 says a published method is **checked** when one of three things is true: it is
run with the authors' own public code; its alerts agree with that code on the same input; or
its numbers match the paper's own table on the paper's own corpus. A method that fails all
three is unchecked and is never an opponent. The parenthetical in that sentence names ADR
0089's three detectors as unchecked as of 4 October, which was the state before this run.

ADR 0089 reproduced MinMax, Steadytime and Histogram from the public sources and scored them
on HAI 20.07. The window rate for MinMax sat next to the paper's 86% and was not that claim.
The point scores were not the paper's. The authors' pipeline itself had not been executed.

The paper's HAI MinMax row is 86.0% of attacks detected, 73 alert-runs overlapping an attack
(TPA), 7 that do not (FPA), penalty 496, accuracy 0.98, precision 0.87, recall 0.38, F1 0.53.
Steadytime and Histogram share a row: 28.0%, TPA 15, FPA 0, penalty 161, precision 0.86,
recall 0.11, F1 0.19.

## Decision

**The authors' own MinMax, Steadytime and Histogram were run on hai-20.07. They do not
reproduce the paper. They reproduce ADR 0089, alert for alert.** No threshold was moved, no
sensor was dropped, and no detector in `phos.eval.simple_iids` was changed. Atlas was not
compared.

Packages, shallow clones, not committed:

| Package | Version | Commit |
|---|---|---|
| `ipal-iids` (`ipal_ids_framework`) | 1.5.4 | `0d71866b777deb13bd2ee038d5058c2425ec4568` |
| `ipal-evaluate` (`ipal_evaluate`) | 1.3.2 | `fd247acb4ea12892f4a849c00070b2ceacc29415` |
| `ipal-transcriber` (`ipal_transcriber`) | 1.4.4 | `18fe5fba589d33c7c61fcc0b0fe11a33ff32bd52` |
| `ipal_datasets` | — | `2fae8546757f82b4840a492cf6351d28f3727e60` |

`ipal-transcriber` is the packet path. Importing it needs `pyshark`. HAI is state data, and
that binary is not on the HAI path. The HAI converter is `ipal_datasets` `HAI/transcribe.py`.
That file splits on commas and lists `test1`–`test5` and `train1`–`train3`, which is the
hai-21.03 layout, and it carries a 50-entry attack-point catalogue used as metadata. hai-20.07
on disk is semicolon-separated and has four files. The run kept their gap-fill and their state
columns (`columns[1:-4]`), and changed only what the files forced: semicolon, and the four
files that exist, in order `test1`, `test2`, `train1`, `train2`. Attack windows came from the
`attack` column. Timestamps were naive `strptime` in the machine zone (BST, UTC+1). There is
no gap longer than one second, so the gap-fill never fired. The test score used 38 windows.
`train2` contains two further attack windows (durations 386 s and 388 s); they were not in
the test score. Their 21.03 attack-point names were not quoted as 20.07 labels.

Each IDS was `ipal-iids` with every one of the 59 state features, threshold 1.0, discrete
cutoff 10, empty preprocessors, `trainon` 1.0, and the default Any combiner.
`--retrain` was used on `test1` only. `test2` loaded the saved model. Steadytime had
`adjust` true. Histogram had window 100. The training file is the concatenation of both
training files, including `train2`'s 776 attack rows. The IDS warned that it expects benign
data only, and trained on those rows anyway.

`ipal-evaluate` was invoked on the MinMax output and exited 1 with `Please install eTaPR`
before writing a report (`metrics/tapr.py` calls `sys.exit`, which the evaluator does not
catch). The numbers below are that same package's point and alarm metric classes on the
`ipal-iids` output, with `timed_dataset` set: confusion, precision, recall, F1, TPA, FPA,
penalty, and detected scenarios. That is the paper's row. It is not an eTaPR score. None of
the four output files contains an `adjust` field, so `ipal-extend-alarms` would rewrite
nothing. Alarm extension is not the gap.

Authors' MinMax, both test files concatenated, 38 attacks, 444,600 rows:

| | authors' code | paper |
|---|---|---|
| Detected | 33/38 = 0.868421052631579 | 86.0% |
| TPA | 255 | 73 |
| FPA | 811 | 7 |
| Penalty | 159460 | 496 |
| Precision | 0.06824781904978935 | 0.87 |
| Recall | 0.6664004107947737 | 0.38 |
| F1 | 0.12381537939661202 | 0.53 |
| Accuracy | 0.628187134502924 | 0.98 |

171,141 rows alert. Per file: `test1` TPA 242, FPA 811, 23/28 detected; `test2` TPA 13,
FPA 0, 10/10 detected. The concatenation equals the sum, so the file boundary did not merge
a run. `P1_PCV02Z` in the fitted model is min 11.9797, max 12.2391, delta 0.1297. It was
not dropped. Ten features have delta 0.

Those alert timestamps are identical to `simple-minmax` (0 rows only on one side). Fitting
on every training row and fitting on `attack == 0` only produce the same MinMax alerts.
The 776 attack rows do not move one of them.

Authors' Steadytime and Histogram are identical to each other: 36,656 alerting rows
(`test1` 22,068, `test2` 14,588). Concatenated metrics, the same for both:

| | authors' code | paper |
|---|---|---|
| Detected | 7/38 = 0.18421052631578946 | 28.0% |
| TPA | 9 | 15 |
| FPA | 5 | 0 |
| Penalty | 35999 | 161 |
| Precision | 0.017923395896988215 | 0.86 |
| Recall | 0.03748502310720603 | 0.11 |
| F1 | 0.024251148884336417 | 0.19 |

Per file: `test1` TPA 6, FPA 3, 4/28 detected; `test2` TPA 3, FPA 2, 3/10 detected. Those
alert timestamps are identical to `simple-steadytime` and to `simple-histogram`, again both
when the 776 attack rows are in the fit and when they are not. Ten features produced a model.

**Checked, under the frozen rule, beside the sentence that named them unchecked:**

| Detector | Authors' code run | Alerts agree | Paper table | Mark |
|---|---|---|---|---|
| `simple-minmax` | yes | yes, every row | no (255/811, not 73/7) | checked |
| `simple-steadytime` | yes | yes, every row | no (9/5, not 15/0) | checked |
| `simple-histogram` | yes | yes, every row | no (same alarms as Steadytime) | checked |
| Gradient | no IDS in the tree | — | not run | unchecked, not an opponent |

Checked here means the public code, not the printed table. The printed table remains
unreproduced, including by the code the authors publish. These three may later be opponents
in A2. This record does not score Atlas, does not append `eval_runs/log.jsonl`, and does not
move a frozen row.

## Consequences

The reproduction gap in ADR 0089 is not in our parsing, our alarm extension, or our scoring.
On hai-20.07 the authors' pipeline and `simple-minmax` / `simple-steadytime` /
`simple-histogram` are the same alarms. Whatever produced 73 and 7 is not this public code
on this release, at threshold 1.0, on all 59 sensors.

Their current HAI converter is built for hai-21.03. 43 of 50 is exactly 86.0%, and 33 of 38
is 86.84%. That arithmetic is not a measurement of hai-21.03. This run did not fetch that
release. The paper cites HAI 1.0.

`ipal-evaluate` cannot emit its report unless eTaPR imports. Full eTaPR on a few hundred
thousand points is a different score from the TPA/FPA row, and it was not run. A later
comparison that wants the evaluator's JSON has to install that package and wait; it must
not treat a missing eTaPR import as a different detector.
