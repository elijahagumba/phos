# 196 — One quiet plant, two detectors, and what the numbers actually say

**Every number on this page comes from a simulator.** The plant is a model written from public
descriptions of how such a process behaves. It is not a capture of a real plant, and no figure here
is a field detection rate or may be quoted as one.

This note is about a demo. Not a test, not a result, a demo. It exists because a reader asked to
see the referee's baseline beside Atlas on the same evidence, and because "trust us, ours is
better" is not an answer anyone should accept.

## What it runs

One simulated plant, twenty-four hours, nothing injected. A quiet plant. Both detectors are asked
the same question: what do you say about a plant where nothing is going wrong?

That question is the honest one to start with. If a detector is loud when nothing happened, the
rest does not matter.

## What came out

The baseline is the simplest model in the repository: one Gaussian per signal, each signal judged
on its own. It was fitted twice, and that turned out to be the interesting part.

**Fitted on the very plant it is shown**, it raised 322 alerts. That number is flattering. It has
learned that plant's own noise, so it is not surprised by it.

**Fitted on a different plant of the same family**, it raised zero. Not "few". Zero. Each signal's
ordinary range differs enough between two plants that no reading falls outside the bands learned
from the other one.

Neither column is the fair one on its own. Printing only the first would make the baseline look
loud and Atlas look restrained. Printing only the second would make the baseline look broken. Both
are printed, and the reason they disagree is written between them.

**Atlas**, on that quiet plant, raised 2,176 alerts and told one story: a sensor or device has
failed, with one piece of evidence behind it.

## The part that is not flattering

Two thousand alerts on a plant where nothing happened is noise. One story covering two thousand
flagged moments is a page an operator would learn to skip. The demo says this in its own output,
in a paragraph headed "something this comparison shows that is not flattering to Atlas", because a
comparison that only advertises the good half is an advertisement.

The demo does not fix it. Showing it is the first step, and the budget the rest of the project
works to, eight alerts in a shift, exists because of exactly this.

## What the demo is not

It is not an evaluation. There is no ground truth compared against either detector, no recall, no
accuracy, no verdict. Those belong to the referee's exam machinery, where the labels and the
counts are handled properly, and doing them here would put a number in the place most likely to be
screenshotted without its context.

Every figure is labelled simulated at the top and at the foot. The plant is a model written from
public descriptions of how such a process behaves. It is not a capture of a real plant, and neither
number is a field detection rate.

## How to run it yourself

```
uv run python -m phos.referee.side_by_side
```

Add `--seed 771003` for a different plant. The numbers change, which is the point: they are
measured, not written down.
