# 36 — The evidence we were throwing away

Note 35 ended with a loose thread, and said so:

> **Command-behaviour evidence still matches no explanation at all.** It's been stamped since D1
> and no template reads it. This work typed the stamp; it did not wire it up. That's a separate
> decision that needs its own argument.

This is that argument. Still no measurement — nothing got quieter or louder, no number moved. What
changed is that a fact Atlas had been carefully measuring, promoting, stamping and storing finally
reaches the explanations it bears on, instead of falling on the floor at the last step.

## What was falling on the floor

Atlas watches two different things on a plant network.

**The command graph** is the wiring diagram: which machine talks to which, using which commands. If
a workstation that has never spoken to a PLC suddenly starts writing to it, that shows up here.

**Command behaviour** is how a machine that already talks does its talking. How many commands per
minute. What fraction of them change something rather than just asking. How regular the rhythm is.
Whether it writes to the same handful of addresses it always writes to.

Both were being measured. Both were being turned into evidence properly — scored against a learned
band, weighted, stored with a full trail back to the exact packets. And then reasoning looked at the
second kind and had nothing to say about it.

Not "weighed it lightly". **Nothing.** A pump controller whose write volume tripled overnight and a
pump controller having a completely normal Tuesday produced the same reasoning outcome: no
explanation moved at all. The fact sat in the story where an operator could read it, attached to
nothing.

## Why it was like that, and why that reason expired

The original decision (back in ADR 0014) was honest and, at the time, correct. It said: evidence
records *what kind* of fact it is, and never *which* fact. So no template could ask "was that a
write share or a polling rhythm?" — and a matcher that couldn't ask the question shouldn't pretend
to answer it.

Note 35 is the story of that missing field getting built. The facet. A proper typed field saying
which feature departed.

So the reason had expired. The field existed, the promoter was filling it in, there was even a
function to read it back — and nothing called that function. The gap was one missing consumer.

## The claim, kept deliberately small

Here is the whole of what a command-behaviour departure now says:

> **This device's commanding changed. That is control activity, not a reading.**

That is genuinely worth something, because it is the one thing the plant's sensors cannot tell you.
And two of Atlas's four explanations are about somebody operating a device:

- **A planned engineering or maintenance change.** An engineer commissioning something alters how a
  device commands. That's what the job is.
- **Unauthorised control activity.** So does an attacker.

Both get support from the fact. Neither gets more than the other.

## The tie we refused to break

This is the part worth dwelling on, because breaking it would have been the easy way to make this
work look more impressive.

An engineer and an intruder, both operating the same device, leave behind **the same change in how
that device commands.** A write share of 0.9 is a write share of 0.9 regardless of who produced it.
No command feature carries intent.

So we could have leaned on the attack explanation a little — nudged it so a big enough departure
tipped toward "attacker". Nothing in the tests would have caught that. It would have been a
made-up asymmetry dressed as a finding.

The tie stays. What separates the two explanations is only their starting probabilities: planned
maintenance starts more likely than an attack, because in the real world it *is* more likely. Atlas
has exactly one fact that legitimately breaks the tie — a device that has *never* commanded this
target beginning to — and that works on **identity**, not behaviour. Behaviour alone doesn't do it,
and we didn't pretend it does.

## The refusal that does the real work

The other two explanations — a real process upset, and a broken sensor — get **nothing** from this
evidence. Not a little. Nothing.

That looks like an omission. It's the most considered decision in the whole change.

The tempting move was to copy the argument that already works for the command *graph*. That one
goes: a real process upset moves readings, but it does not make a workstation start commanding a
PLC. True, and it's about physics rather than tuning, which is why it's allowed to be an asymmetry.

**It does not transfer.** A control system's entire job is to respond to disturbances by acting. A
genuine upset makes a controller write more often, write different values, and shift its rhythm
under load. Those are exactly the features being measured. So:

- Saying a command departure argues **against** a process upset would be simply **false**.
- Saying it argues **for** one would be a claim about control-loop dynamics that Atlas has never
  measured on any plant it's been given.

Silence is the only honest answer, and there's a test that fails if anyone quietly adds a relation
there later to make a number move.

## One thing we found by breaking it

There was a test we didn't expect to break, and it turned out to be the interesting part.

It checked that on ordinary plant readings the "process upset" and "attacker" explanations weigh
evidence identically — the limit that's been true since the beginning. It checked it by comparing
lists of matching rules, filtered by evidence type.

That check broke. But the *claim* was still true — the new rule can't match a plant reading at all.
What broke was the shortcut: filtering by evidence type used to mean "plant readings", because
plant readings were the only thing of that type. Once command behaviour shares the type, the
shortcut stops meaning what it used to.

So the test now checks the actual thing: take two real plant readings, and confirm the two
explanations treat them identically. Which is what its own description always said it was doing,
and is a stricter check than the one it replaced.

That's the second time this exact shape of bug has appeared — the same footgun ADR 0014 hit when
command evidence first started sharing a type with sensor evidence. Worth remembering it'll happen
a third time.

## What this cost

Being straight about the bill: there's a known counting problem that just got sharper.

Command evidence isn't bundled per device. A device whose commanding changes in four ways at once
produces four separate pieces of evidence for what is probably one event. That was decided
deliberately — bundling needs a real capture in hand to decide what a "device event" even means —
and until now it was **harmless**, because those four pieces landed on nothing.

They land on something now. Four facts pushing where one should. That's a real cost, it's written
down, and it's first in the queue when a real capture arrives.

## The honest summary

**This is readiness, not a result.**

It makes reasoning *read* evidence Atlas was already producing. It does not detect anything new. No
recall figure, no false-alarm rate, nothing calibrated — because proving this is worth anything
needs a recorded attack where somebody's command actions are labelled, and that recording does not
exist.

Note 16 covers why. Since then we assessed a very good dataset from TU Wien's pilot factory, and it
failed in the mirror-image way: the labels were **fine enough** — per packet, naming the attack tool
— but the pen-tester never touched the industrial network at all, by design. The paper says it
outright: he did not send a single Modbus packet. Perfect labels, nothing to label.

So this is a pipe that has been correctly connected and never had water through it. Worth building,
because when the corpus arrives it's a manifest and a command rather than a project. Not worth
quoting a number about.

## The one sentence

Atlas had been measuring how devices command, stamping it, storing it, and then throwing the
meaning away at the last step — it now reaches the two explanations that involve somebody operating
a device, supports both equally because nothing in the data says which, and stays deliberately
silent about the two it cannot honestly speak to.
