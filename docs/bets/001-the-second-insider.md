# Bet 001 — The second insider

**Status: lost (18 October 2026).** The success test was fixed on 27 September 2026. The three
formulas were fixed on 4 October 2026. The ranking was fixed by commit before the one run
(ADR 0148). All three formulas were run once. None of them put a day of the second insider in
the top 48. One of them lost the first insider too.

## The problem

Sentiel watches people rather than machines. It is tested on CERT r3.1, a public, synthetic
insider-threat dataset from Carnegie Mellon's CERT. The dataset contains two labelled insiders.
At a budget of 48 alerts, Sentiel finds one of them and misses the other completely.

The reason is arithmetic, not missing data. Sentiel scores each person-day by adding up one capped
term per signal that moved, and no single term can exceed 1. The 48-alert threshold is 13.7, so at
least **14 of its 34 signals** must move on the same day before anyone can be flagged, however
extreme any one of them is. **31 of the second insider's 42 malicious days** could never have
raised an alert at any magnitude. Their best day ranked 957th of 210,814.

[How this was found: ADR 0076](../adr/0076-sentiel-fails-on-an-aggregation-ceiling-not-a-missing-corpus.md)

## The bet

Replace the capped sum with a way of combining signals that lets **depth** count, not only
**breadth**: a day where a few signals move a long way should be able to reach the threshold.

**Success, fixed before running:** at the same 48-alert budget, at least one of the second
insider's malicious days is in the top 48 **and** the first insider is still there. Finding the
second by losing the first counts as a failure. So does a precision gain that only finds more days
of the insider already found.

**The rules, so the result cannot be tuned into a win:**

- At most three candidate formulas, each written down and committed **before** any of them is
  scored against the labels. All three are reported, win or lose.
- No adjusting thresholds, budgets or weights after seeing results. Every signal is treated the
  same; no signal may be favoured because it is known to matter for this insider.
- The existing published number (precision 0.104 at 48 alerts) is reproduced exactly first, and is
  never overwritten.
- Every result is shown beside what chance alone would produce.

[The full contract: ADR 0084](../adr/0084-non-saturating-aggregation-for-sentiel.md)

## Our prediction

**It probably won't be enough.** We wrote down why before running anything:

- The second insider's malicious days score *below* their own ordinary days (4.50 against 4.59 at
  the median). Their behaviour barely changed.
- Measured against their own history, no signal moved by more than 1.27 standard deviations.
- Their strongest single signal reached 6.33, while other people's days reach 18.8. A
  formula that rewards depth will reward those days first.

If the bet fails, that is still a result: it moves the problem from how Sentiel adds up evidence to
what evidence it collects. Its signals count *how many* hosts and recipients a person touches,
never *which ones*, and this insider's activity was about which.

## The three formulas

Written down before any of them is scored. All three will be reported. None is selected yet,
because none has been run. A fourth formula is a new bet.

1. **Depth above the bar.** Add up, for each measured signal, how far it sits above 1.0. That
   1.0 is the bar the scorer already uses to decide a signal spoke. A signal the model could
   not measure adds nothing.
2. **How rare, under a bell curve.** Add up, for each measured signal, the negative log of the
   chance a standard bell curve gives to a departure at least that large. A signal the model
   could not measure adds nothing.
3. **One voice per kind of behaviour.** Inside each kind of behaviour Sentiel already groups
   together, keep only the largest measured departure. Add those largest values up. Counting
   the same behaviour several ways does not get several votes.

No signal is weighted. The published 0.104 at 48 alerts is not overwritten by declaring these.

## The result

Run once on 18 October 2026 by `uv run python scripts/lane_a_bet001.py`. The published 6B row
was reproduced first (threshold 13.7006, precision 0.104, 43 false positives) and is not
overwritten. Nothing was added to the experiment log. The second insider is `CCH0959` (42
labelled days); the first is `CSF0929` (11 labelled days). A random 48 of the 210,814
person-days would hold 0.012 malicious days.

| Formula | Second insider in top 48 | Its best day ranked | First insider's days in top 48 | Precision at 48 |
| --- | --- | ---: | ---: | ---: |
| Published 6B (capped sum) | no | 957 | 5 | 0.104 |
| Depth above the bar | no | 1,497 | 6 | 0.125 |
| How rare, under a bell curve | no | 2,689 | 2 | 0.042 |
| One voice per kind of behaviour | no | 1,356 | 0 | 0.000 |

**The bet is lost.** Every formula ranked the second insider's best day lower than the capped
sum already did. Depth above the bar found one more day of the first insider, which the
success test says does not count. One voice per kind of behaviour lost the first insider.

This is what the prediction said would happen. The second insider's behaviour barely moved on
the 34 signals Sentiel counts, so no way of adding those signals up reaches them. The problem
now belongs to what Sentiel measures: which hosts, recipients and machines a person touches,
not only how many. Result file: `eval_runs/build/lane-a/bet-001.json`.
