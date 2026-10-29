# The fifteen-second gap was ordinary

**What this is:** a separate way to learn "normal" for command behaviour, because a bell curve
was calling a common gap an alarm.

**Why it exists:** on the simulated water plant, the SCADA server often sends a command every
15 seconds exactly. A Gaussian band is an average plus or minus three standard deviations. That
band stopped at about 13 seconds, so the 15-second gap — ordinary on that plant — raised an
incident on a run where the only write was one the operator was allowed to make.

## A pile is not a bell

Think of a platform clock that chimes on the minute. Most chimes are a minute apart. A few are
not. The average gap is a bit under a minute, and three standard deviations of that scatter can
fall short of the minute itself. The clock is then "abnormal" every time it is punctual.

The repair is to read the band off the gaps that actually happened, at the same thinness the
bell curve was claiming: about 0.135% of the gaps on each side, the chance a true bell curve
gives to being more than three standard deviations out. That chance is inherited from the claim
the Gaussian model already made. It was not picked by trying cutoffs until the alarm went away.

Inside that band, the score is zero. Outside it, the score is still "how many standard deviations
from the average," so a real departure still reads the same way. If the fit never varied at all,
any other value is as surprising as the model can say.

Tukey's fence, the other robust thermometer, is the wrong tool here. When a count is 6 almost
every minute, the middle half of the data is also 6, the fence shrinks to a point, and a 5 that
did occur in the fit looks maximally strange.

## What twenty ordinary runs did

The demo's authorised-operator run, seeds 11 through 30, fixed before anyone looked. A false
alarm is an incident that is not about the write the operator was allowed to make.

The Gaussian baseline raised **15** such incidents across the twenty runs, **0.75** per run.
The empirical band raised **4**, **0.20** per run. Ten runs went quiet under both. The figure's
name is `empirical-command-baseline:operator-false-alarms`.

On the same seeds, when the SCADA server makes a write it is not allowed to make, the brief
concerns that write on **19 of 20** Gaussian runs and **20 of 20** empirical runs. The empirical
model does not see the write less often. That figure's name is
`empirical-command-baseline:unauthorised-concerns-write`. The one Gaussian miss is seed 22.

Both figures are a plant we built. They are not a public capture, and they do not move the
frozen command rankings: known-station unique lead **0 of 16**, unknown-master unique lead
**1 of 4**, kept apart.

Seed 11, the one already on record, still raises one incident. The 15-second gap is inside the
new band. What remains is a coefficient of variation that only three of 7,197 training windows
beat, which is inside the inherited 0.135% tail and inside the old three-sigma band. The tail
was left where it was.

The priors on the explanations, and how hard one piece of evidence pushes them, were not
touched. A write from a device that has never commanded that target still leaves
"not enough evidence" in front. Measuring those priors needs labelled plant data.

## What this is not

- Not a quieter public row. The Gaussian baseline that produced the frozen numbers is the same
  code, still used for those rows.
- Not permission to treat 0.20 per run as a control-room budget.
- Not a change to who-commands-whom, or to the tie between maintenance and an attack when a
  known station uses a new function.

## Where to read more

- Decision: [ADR 0086](../docs/adr/0086-empirical-command-baseline.md)
- The demo that found the alarm: [ADR 0085](../docs/adr/0085-phos-demo-runs-one-incident-end-to-end-and-names-its-misses.md)
- Code: `src/phos/models/empirical.py`
- The twenty runs: `eval_runs/sandbox/adr0086-empirical-command-baseline/measurement.md`
