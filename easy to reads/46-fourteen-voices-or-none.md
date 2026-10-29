# 46 — Fourteen voices or none

Sentiel looks at each person on each day through 34 measurements: how many files they touched,
how many thumb drives they plugged in, how many new people they emailed, and so on. Each
measurement that looks unusual adds to that person-day's score. The forty-eight highest scores go
in front of an analyst.

The catch is in how much one measurement may add. However unusual it is, **each one is capped at
1**. A measurement that is a little odd adds about 0.6. One that is wildly odd adds just under 1.
That cap was deliberate: without it, one measurement the model could not size would swamp
everything else, and an earlier version of Sentiel drowned in exactly that.

## What the cap costs

To reach the forty-eight-alert cut, a day has to score about 13.7. If each voice can add at most
1, **at least fourteen of the 34 measurements have to be unusual on the same day**. Depth cannot
make up for it. Thirteen measurements at the most extreme value possible still fall short.

The CERT corpus has two people labelled as insiders.

- The first had almost never used a thumb drive or logged on after hours, and then started doing
  both. That one change moves a lot of related measurements at once, so their days reach fourteen
  voices. Sentiel finds them.
- The second was already a regular thumb-drive user, and they stepped it up gradually over two
  months while job-hunting and emailing a competitor. On **31 of their 42 malicious days, fewer
  than fourteen measurements spoke**. Those days could not have alerted however unusual they were.
  None of the 42 alerted. Their best day ranked 957th.

This was diagnosed in September (ADR 0076). The evidence is in the data. The way Sentiel adds it
up cannot hear it.

## What is opened now

ADR 0084 opens the session that tries a different way of adding up, one where a single
measurement can say "this is very unusual" and be heard. The three formulas are written down
in note 54. None of them has been tried on the insiders. What the record
does is fix the rules **before** anyone looks at a result:

- **Changing the number is not the fix.** Raising the cap from 1 to 2, or lowering the bar, is
  tuning a dial until the answer we already know appears. Only a different way of adding counts.
- **No favourites.** We know which measurements moved for the second insider. None of them may be
  given extra weight.
- **Write it down first.** Up to three candidate methods are fixed and committed before they are
  ever run against the labelled insiders. All three get reported, including the losers.
- **Success is one sentence.** At the same forty-eight alerts, the second insider appears **and**
  the first one is still there. Catching more of the first insider's days would make precision
  look better and is not success.
- **A likely no.** The record says in advance that this probably won't be enough. At the median,
  the second insider's malicious days score lower than their ordinary days, and their biggest
  single signal is modest. If the new method still misses them, that is a real answer: the next
  limit is that Sentiel counts *how many* websites and recipients a person reaches, never *which*
  ones.

---

**The short version.** Sentiel needs fourteen measurements to agree before it will raise a hand,
and the insider it misses never gave it fourteen. We are now allowed to try a way of adding up
that doesn't need fourteen, under rules written before the try. The frozen number, 0.104 at 48
alerts, does not move until something earns it.

*Record: ADR 0084 (opens the session), ADR 0076 (the diagnosis), ADR 0093 (the three
formulas, not scored). Report: `eval_runs/sentiel/cert-failure-classification.md`. No new
measurement.*
