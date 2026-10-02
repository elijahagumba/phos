# Bet 001 — The second insider

**Status: open.** The success test was fixed on 27 September 2026, before any code was written. No
candidate has been run.

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

## What happens next

1. The candidate formulas are published here, in a commit that comes before any result.
2. They are run once, under the rules above.
3. The result is published on this page, whichever way it goes.
