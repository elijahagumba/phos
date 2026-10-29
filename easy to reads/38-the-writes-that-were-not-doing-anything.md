# 38 — The writes that were not doing anything

Note 34 ended with a piece of machinery that had never been used: Atlas could read a maintenance
system's work orders, but no dataset in the world ships one, so the code sat there untested against
anything real. There is a second piece in the same condition. Atlas can attribute an unauthorised
command — work out that a device wrote to a controller when it had no business doing so — and that
has never been measured either, because no public capture says which writes were the attacker's.

Two capabilities, both built, both wired, both unmeasurable. We have a plant simulator. Why could
it not test them?

The answer turned out to be embarrassing, and finding it is most of what this note is about.

## The writes were pretend

Our simulated plants have a control network. They speak Modbus, the industrial protocol Atlas
reads. Operators change setpoints and those changes show up as writes on the wire. It looks right.

It was not right. Here is what the code actually did, in order:

1. An operator event fires. The setpoint moves from 3.2 metres to 3.6 metres.
2. The physics runs. The tank starts filling toward the new target.
3. *Then* a write is emitted onto the network, carrying the value 3.6.

Read that again. The setpoint had **already moved** before the write existed. The write was a
report of something that had happened, not the cause of it. You could delete the entire network
capture and every single sensor reading in the run would be identical.

That is a serious problem for a harness whose job is to test command attribution. An attacker whose
writes are decorative is an attacker the plant never felt. We could put an intruder on the network,
watch Atlas notice the traffic, and learn precisely nothing about whether the reasoning is sound —
because the "attack" never touched the process.

## The fix, and the test that proves it

Writes now happen **before** the controllers run. A write lands on the setpoint; the control loop
reads that setpoint on its next scan; the loop opens the pump; the tank fills. Cause, then effect,
in that order.

The test that matters is not "does a write appear on the wire." It is the counterfactual:

> Run the plant with the attacker's write. Run it again without. The two runs must end up in
> **different physical states.**

A decorative write passes the first test and fails the second. That is now pinned in the test
suite, so it cannot quietly regress.

## Who is allowed to write

The second missing piece was that nothing recorded whether a write was *permitted*.

You might think the attacker's code should mark its own writes as unauthorised. That is exactly
what we must not do. If the thing generating the attack also assigns the label, the label is just
the author's opinion written twice, and any score measured against it is measuring our own
consistency.

So the **plant** declares the policy instead — which device may write which setpoint — and the
authorisation of any observed write is worked out from that declaration. The attack code has
nowhere to put an opinion. It cannot label itself.

Granting exactly one station the right to write turns out to produce three genuinely different
situations:

| Who writes | Permitted? | How it looks on the network |
|---|---|---|
| The control-room HMI | yes | a familiar device doing a familiar thing |
| The SCADA server | **no** | **also** a familiar device doing a familiar thing |
| The engineering workstation | no | a machine that has never issued a command in its life |

The middle row is the hard one, and it is the one we could not previously build. A compromised
SCADA server is a legitimate host on the network. The command graph has learned that link.
Structurally, nothing is out of place. Only the policy says it should not be writing.

And critically: **an authorised write and an unauthorised write are the same bytes.** They have to
be, because on a real plant they are. The permission lives in a policy document, not in the packet.
We prove this by building two plants that differ *only* in their declared policy, confirming the
recorded truth differs, and then confirming the network captures are byte-for-byte identical.

## A maintenance calendar that cannot see the attacks

The third piece is the work-order calendar from note 34 — now generated, so the inlet finally has
something to read.

The temptation here is enormous and worth naming. If you want to show that maintenance evidence
helps, you generate some attacks, then generate work orders that happen to cover some of them, and
report that the join works. That is not a finding. That is arranging two things to agree and then
being pleased they agree.

So the calendar generator is built so it **cannot see the attack schedule**. It takes the plant's
equipment list and a description of maintenance practice — how often routine servicing happens, how
often something breaks unexpectedly, how long a planned shutdown lasts — and nothing else. There is
no parameter for where the attacks are. The module does not import anything that could tell it.

Which means coverage is a **coincidence**, exactly as it is in a real plant. And the numbers show
it. We ran the same 72-hour scenario on three different random seeds:

| Seed | Attacker writes inside a sanctioned maintenance window |
|---|---|
| 7 | 0 |
| 11 | 0 |
| 23 | 177 |

Two-thirds of the time the schedules simply missed each other. That spread is the construction
working. A rigged calendar would have produced coverage every single time.

Seed 23 is the case notes 34 and the older records both said was the crux: an attacker operating
inside a genuine maintenance window, where the covering work order argues *for* the innocent
explanation while the attacker is right there doing it.

## Five ways we tried to stop ourselves cheating

The whole risk in this exercise is circularity. If the same person writes both "here is what an
attack looks like" and "here is what the detector looks for," then a good score measures the
agreement of two opinions.

PHOS already refuses this one level down — the plant's layout is **declared** rather than guessed
from the data, and colleague groups come from the staff directory rather than from behaviour. These
are the same refusal, one level up. All five are tests that fail the build, not promises:

1. **The generator may not mention the detector.** Every simulator file is parsed and checked for
   imports of Atlas or Sentiel. There is one permitted exception, a shared file-format definition,
   and it is allowed by name — three specific symbols, not a whole package.
2. **Attacks are described by what the attacker wants, never by what a detector would see.** A
   scenario says "drive the clearwell above the level the works is operated to, so treated water
   overflows to waste." It may not say "make this number deviate by that much." The scenario text
   is automatically scanned against Atlas's own published vocabulary.
3. **Every attack cites where it comes from in the real world** — a documented incident, a
   published attack taxonomy, an engineering failure mode, a vendor advisory. The scenario format
   has literally nowhere to record "because it would be interesting for Atlas to catch."
4. **Some attacks must be undetectable.** A generator that only produces catchable attacks is a
   mirror. The build fails if a run contains no attacks below any plausible detection floor, and no
   innocent events shaped to tempt a false alarm.
5. **The method is published including its failures**, and the build fails if the limitations
   section is too short to be honest.

Then we checked the checks. It is easy to write a guard that cannot actually fail, so we broke
things deliberately: added a forbidden import, rewrote an attack goal in detector language, and
gave the calendar a parameter for the attack schedule. Each one turned tests red. A guard that
cannot fail is not a guard.

## What this changes, and what it does not

**Both dead capabilities can now be exercised.** Command attribution can be aimed at an attacker
whose write genuinely moved a tank. The maintenance join can be fed a calendar and asked what it
does. Neither had ever run.

**Neither is measured, and the difference matters.** Everything above happened inside a simulation
we wrote, attacked by an adversary we invented, during maintenance we made up. The frozen public
numbers are untouched: command attribution still leads in **0 of 16** known-station cases on real
data, and nothing here moves that. The long-standing finding that an engineer and an intruder look
identical to the evidence still holds, and its test still passes. We have not solved that. We have
built a place to study it.

**The honest worry.** The number most likely to be wrong is the coverage rate — how often
maintenance genuinely explains an anomaly. Real maintenance registers are far messier than ours:
orders raised after the fact, windows that bear little relation to when work happened, jobs done
with no paperwork at all. And that number is precisely the one the whole maintenance argument
depends on. We have written this at length in the method document rather than leaving it to be
discovered later.

## Two things we deliberately did not do

We generated the messy realism — grade changes, seasonal drift, fouling equipment, sensor faults,
dropped network frames, startups and shutdowns — but **did not wire it into the sensors yet**.
Doing that changes how every existing dataset is produced, and that deserves its own record rather
than being smuggled in alongside this.

We also did not run the comparison that asks whether a work order changes *which* explanation wins.
It needs the full reasoning stack, and reporting a ranking shift across eleven invented windows
would be an anecdote dressed up as a result.

Both are written down as owed, not as done.

## Related

[34](34-a-work-order-is-the-alibi-nobody-ships.md) is the work-order inlet this feeds.
[16](16-the-public-command-capture-we-do-not-have.md) is why command attribution has no real corpus.
[08](08-plants-we-built-to-break-atlas.md) is the simulator this extends.
[14](14-the-dataset-library-is-not-a-public-corpus.md) is the standing rule that none of this is a
public corpus. The full method, with its limitations, is `docs/synthetic-harness-method.md`
(ADR 0073).
