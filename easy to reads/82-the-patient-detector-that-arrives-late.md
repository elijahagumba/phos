# 82. The patient detector that arrives late

*What lane 3 of the stronger-engine programme built, what it caught, and why it was turned down
anyway. ADR 0286, with the numbers in `eval_runs/build/lane-e/lane3-development.md`. Everything
here is on a plant PHOS generated, which makes it diagnosis and not proof.*

## The problem it was built for

Atlas's frozen detector asks one question of every instrument, every second: *does this reading
match what the rest of the plant implies?* If the mismatch is big enough at any single second, it
opens an alert.

That rule has an obvious blind spot, and the blind spot has a name in the corpus: `liar_freeze`. A
sensor is frozen — it keeps reporting the same number while the real tank level drifts away
underneath it. At no single second is the mismatch large. The gap grows slowly, by a little, for
minutes. A detector that only ever asks "is it big *now*?" never says yes.

There is a second, nastier reason it never says yes. The frozen detector deliberately *flattens*
slow changes. It compares each reading's mismatch against the median of its own mismatch over the
previous hour. If the mismatch is creeping up, the trailing median creeps up behind it, and the
difference stays small forever. The engine's own docstring is honest about this: it says the
detrending lets "a slow drift stop alerting". The blind spot is designed in, for a good reason —
without it, every gradual change in the plant would alarm — but it is a blind spot all the same.

Before this work, the frozen engine caught `liar_freeze` **1 time in 10**.

## What was built

A tally. For each instrument, keep a running total of how much it has been wrong. Add today's
excess, let the total leak away slowly so it forgets old news, and never let it go below zero — a
sensor being unusually *well behaved* earns no credit against a later lie.

Three choices, and none of them was picked by looking at the attacks:

- **How much is allowed for free.** Each instrument gets an allowance set at the 99th percentile of
  its own behaviour on quiet, attack-free days. Ordinary wobble, including ordinary spikes, adds
  nothing. Only persistent excess accumulates.
- **How long it remembers.** Exactly as long as the detrender forgets — the same one-hour window the
  frozen engine already uses. That number came from the engine, not from the length of any attack.
- **How loud it is allowed to get.** Capped, for a reason that turns out to be the whole story.

Then the tally is bolted on as extra columns beside the existing ones and the untouched alerting
machinery decides what to do with it. That matters: the operator still gets **eight alerts a
shift**, no more. The tally does not get extra alerts; it has to *win* them from the existing
columns.

## What it caught

| | Frozen engine | With the tally |
|---|---|---|
| `liar_freeze` — the frozen sensor | 1 of 10 | **10 of 10** |
| `rogue_command` | 4 of 10 | **10 of 10** |
| `mimic_maintenance` | 2 of 10 | **6 of 10** |
| `replay` | 5 of 10 | **7 of 10** |
| **All attacks** | **32 of 70** | **53 of 70** |

Twenty-one more attacks caught, within the same eight alerts, and **nothing lost** — not one attack
the old engine found went missing. The thing it was built for, it did perfectly: 1 of 10 to 10 of 10
on the exact blind spot. On `creep_many` it was even 22 seconds *faster*.

That is a large result, and it was turned down.

## Why it was turned down

The bar for this lane, written before any of this ran, had two halves: catch strictly more attacks,
**and** do not take longer to notice them. The second half exists precisely so nobody can trade
timeliness for a bigger number and call it progress.

The tally took longer. On the 32 attacks both versions catch — the same attacks, so it is a fair
comparison — the old engine's median was **1 second** and the tally's was **5 seconds**. Measured
the other way, over everything each one caught, it was 1 second against 13. Worse under either way
of counting, so the verdict does not depend on the choice.

And here is the part worth understanding, because it is not a tuning failure.

When several instruments misbehave around the same time, the engine bundles them into one event and
puts the alert at the *earliest* piece of evidence that is strong enough to count. "Strong enough"
is measured relative to the strongest thing in the bundle. A tally is a sum over time, so it gets
big — much bigger than any single-second reading. When the tally joins a bundle, it becomes the
strongest thing in it, which **raises the bar for what counts as strong enough**, which disqualifies
the modest single-second evidence that would have placed the alert early. The alert slides later.

On its own, that modest evidence would have been fine: the engine compares each piece against the
best in its bundle, and alone, a thing is the best in its own bundle.

So the trap closes from both sides. To win one of the eight alerts, the tally has to score high. But
scoring high is the *same number* that makes it take over the alert's timing. On a budget that is
already full, those cannot be separated. Lowering the cap was tried across its whole range: it buys
the delay back only by giving up catches, it never reaches "no worse", and at the low end it starts
losing attacks the old engine caught. There is no setting that passes both halves.

## What happens to it now

Nothing is declared. The detector was never frozen, no held-out data was opened, and the two ADR
numbers reserved for lane 3's declaration and verdict stay empty — which is the correct reading of
the rule, since the programme says to freeze and declare only *if it wins on development*. It did
not win. The code stays on disk, tested, beside lane 2's column, which is sitting out for its own
reasons.

The real finding is not about the tally at all. It is that **in this engine, a bolted-on column
cannot earn an alert without also moving that alert's timing**. That is now written down as its own
record, because lane 4 bolts on columns too and will hit the same wall the moment anyone asks how
quickly it noticed.

Two honest ways forward, neither of them this session's to take. Write a new alert-placement rule
beside the frozen one — not an edit to it, the frozen detector is never edited — so a patient column
can win a slot while the early evidence keeps the right to time the alert. Or ask a real plant
whether twenty-one more attacks is worth four seconds, which is a question for a design partner and
not a number a build session may quietly change.

The bar refused it. The bar was right to, and the bar stands.
