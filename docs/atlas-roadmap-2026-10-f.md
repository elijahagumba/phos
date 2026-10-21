# Atlas roadmap F — five questions, one evaluation

Declared 21 October 2026 by ADR 0298. This is not a claim that any of the five will work.
Build brief E is closed (ADR 0297). Its reserved numbers 0277–0284 stay unwritten. v1 stays
8 of 12. `atlas-v1-consistency` is never edited.

P1 stays blocked on a human conversation. This roadmap does not start Intelligence, an API,
or a UI, and it does not unblock P1.

## What is already settled

Do not re-run these as if they were open.

- Lane 1 is kept, as attribution, on a simulated plant: 87 of 120 held-out attacks against
  49, reconnaissance 20 of 20 against 0. An attacker at the operator's console defeats it.
  It is not command-against-physics (ADR 0276).
- A running tally caught 53 of 70 against 32 and arrived later. Refused (ADR 0286).
- A bending predictor cut false alarms from 28.00 to 20.00–24.00 a day and caught fewer
  attacks, 32 down to 23–25. Refused (ADR 0288). On distillation, a phase-conditional model
  was louder than the frozen public row. The 2–3 alerts a day claim stays refused (ADR 0048).
- Breadth on the attack this plant can host caught 15 of 32 against the frozen engine's 16.
  The 3–8% band stays (ADR 0296).
- On public HAI, inside 8 alerts a shift, three later editions are 131 of 160 against 52 for
  the best baseline checked. HAI 20.07 is 37 of 38. Those files are seen. There is no labelled
  public command capture (ADR 0040).
- Hypothesis confidence is uncalibrated and is not surfaced. A Kelmarsh confidence test did
  not meet its bar.

## The five capabilities

Each is a question. None is scheduled work until its own declaration is committed, with the
command, the seeds or corpus, and the bar, before any measurement.

### 1. Attacks that stay inside ordinary sensor ranges

A setpoint can change while every sensor stays inside the range it was allowed. A threshold
on one reading can miss that. The question is whether the frozen detector already sees a
break between the command, the conditions at the time, the response that followed, and the
relationships the plant normally holds.

First task, and the only one this roadmap authorises now: name an evaluation set that poses
that question, and score the frozen detector on it once the declaration is committed. Do not
build a new detector in that same step. `mimic_maintenance` stays as it is: same station,
same tag, same values, separated only by a missing work order.

Bar, if a later detector is declared: strictly more of those held-out scenarios caught than
the frozen detector, inside the same alert budget, with false alerts no higher. A tie is not
a pass. Simulated results stay diagnosis.

### 2. Incidents, not a pile of alerts

Ten weak signals in fifteen minutes may be one episode or ten. The frozen engine already
groups episodes into events. A new linker would be a new function beside that grouping, never
an edit of it. It does not inherit the refused 53 of 70.

The risk is the whole question. Loose links invent an incident. Tight links split a real one.
Investigation time is not a number we can report until a person is timed. Until then the bar
is: more labelled incidents caught inside the same count of alerts presented, and not more
alerts. Both halves. Report delay either way.

### 3. Normal that is allowed to change

Equipment ages, loads move, setpoints are changed on purpose, maintenance shifts the regime.
A detector that freezes one normal goes blind or cries wolf. A detector that silently refits
on whatever persists will learn the attack.

Phase-conditional distillation was louder, not quieter (ADR 0048). Any regime model has to
beat that fact, not assume the opposite. An update to the learned normal is a versioned
candidate. It is not promoted because it has been quiet for a while.

Bar: on held-out legitimate changes, false alerts no higher than the frozen detector, and
attack recall inside the same budget no lower. Both halves. One familiar dataset's recall is
not this bar.

### 4. Explanations that can be checked

The report already separates evidence from the story. The question is whether a reader can
tell these apart on a labelled case, and whether they are right:

- a measurement
- a prediction
- an inference the evidence supports
- a rival explanation
- something missing
- a conclusion the record cannot justify

Uncalibrated confidence stays off the page. A claim that a response disagrees with a regime
has to name the measurements, and it has to be checked when those measurements are varied.
The Kelmarsh confidence test is the prior: do not describe this capability as already shown.

Bar: on a labelled set declared first, the stated evidence supports the conclusion at a rate
written down before the run, and a suggested next observation separates rivals more often
than chance on that same set. A better-looking report is not the bar.

### 5. Feedback that cannot silently retrain

An operator's dismissal, confirmation, or missed incident is a record with a provenance.
It is not a training row. Confirmed observations stay separate from uncertain judgments.
A candidate update is scored against a frozen reference and the attack scenarios already
declared. If false alerts rise or a previous catch disappears, the candidate is not promoted.
Promotion is an explicit decision.

This waits on feedback we do not have. A simulated stand-in is a diagnosis, the way U5's
study without operators was not operational usefulness. It does not unblock a live plant.

Bar, when a study is declared: over successive cycles on a suite frozen at the start, the
suite's attack recall inside the budget is no lower and its false alerts are no higher than
the cycle before. Both halves, every cycle.

## The flagship evaluation

One evaluation, not six months of unmeasured components. Its question: on data the detector
was not built on, inside a realistic alert budget, does Atlas catch more labelled incidents
than the alternatives and hand an investigator evidence that holds up?

Nothing here is scored by this roadmap. The evaluation gets its own declaration when a
candidate exists to freeze. Until then there is no flagship number.

**Stage A. Freeze.** Detector, features, preprocessing, thresholds, alert policy, and the
protocol. Version and configuration written down. No change after the final numbers are seen.

**Stage B. Held-out data.** Not the corpora used to build or choose the detector. Seen HAI
editions, BATADAL, `phos-icssim-heldout`, and any other spent one-look stay spent.
`phos-icssim-heldout2` and `phos-icssim-heldout3` stay unopened until a declaration names
them. More than one environment is a partner's plant or a newly declared corpus, not a
reuse of a seen file. Say how development data was kept out.

**Stage C. Alternatives, chosen first.** The frozen Atlas, grouped MinMax, and any further
baseline named in the declaration. A published method is included only if it is named before
the run and can be scored under the same rules. The phrase is "a baseline we checked."

**Stage D. Score once.** The source notes jumped from C to E. This is the missing stage.
Run the frozen command. Report every metric that was listed. Do not drop an unfavourable one.
Do not retune.

**Stage E. Publish.** Method, version, configuration, baselines, limitations, and enough to
repeat the run. Either outcome stands.

### Primary outcome

Written now, so it cannot be chosen after the table:

1. More labelled attacks caught than frozen Atlas, inside the same alert budget.
2. False alerts per operating hour no higher than frozen Atlas.

Both. A gain on one half is not a pass. The budget for the first flagship is 8 alerts a
shift, the same budget v1 used, unless the declaration explains a different budget before
the run.

Reported either way, and not part of the pass: detection delay, unseen attack families,
operating regimes, whether related observations were linked, and whether the stated evidence
supports the conclusion. Investigation time stays off this list until a person is timed.

## What a session may do next

The next record, before any new detector, names the evaluation set for capability 1 and
scores the frozen detector on it. If the frozen detector already catches the class, say so
and stop. If it does not, a new detector is a separate declaration.

No other capability starts ahead of that.
