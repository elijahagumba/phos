# 177. The thing we could not do was never written down

*A piece of Atlas had been finished and merged for a week with nobody marking it. Checking it
turned up something bigger: the list of what Atlas cannot do was missing its most obvious entry.*

Two weeks ago Atlas gained the plumbing that lets it read a conversation rather than a single
packet. Industrial messages do not always arrive whole — they are split across packets, they turn
up out of order, and a question and its answer may be thousands of packets apart. The plumbing
puts them back together, inside strict limits on how much it will ever hold in memory, and when a
conversation exceeds those limits it **refuses the whole conversation** rather than quietly keeping
the first half.

That work was written down in advance, built, tested, and merged. And then nobody wrote the verdict.

## Why an unmarked pass is a problem

The rule in this project is that you say what you are going to measure before you measure it, and
afterwards somebody who did not do the work says whether it passed. Both halves matter. The first
stops you moving the target. The second stops you grading your own homework.

Here the first half happened and the second did not. For a week the plumbing sat in the main branch
as working code with no result attached to it. Nothing was wrong with the code — it is green, and
checking it took an afternoon. The problem is that *nobody could tell from the record*. A piece of
software that works and a piece of software nobody has checked look identical from the outside, and
the entire point of the record is to tell them apart.

It gets slightly worse. Three days ago the whole protocol programme was parked, on the reasonable
ground that it was not moving either of the two targets Atlas still has open. Parking it meant
nobody looked inside it, and nobody noticed that one step of it was finished and unmarked. Parking
a programme does not settle a debt inside it.

So the first thing done this week was the boring thing: check it properly and write the verdict.
Every limit in the code matches the number that was promised. A refusal is handed back as a value,
never thrown as an error. A repeated chunk of data refuses the conversation instead of overwriting
what was there. The one error the code *can* throw turns out to be aimed at a programmer passing a
badly-formed timestamp, not at anything arriving over the wire — so it is written into the verdict
rather than left to be discovered in the source later. **Passed.**

## The bigger thing, found by accident

Atlas keeps a document most products do not: a register of **what it cannot do**, with the evidence
for each limit and what it would take to lift it. Twenty-six entries. It is deliberately unflattering
and it is one of the most valuable things in the repository, because no competitor publishes one.

While writing up the protocol decision, somebody read down the list looking for the entry about
protocols.

There wasn't one.

Atlas speaks exactly one industrial language, Modbus — a plant running Siemens, or a water utility
on DNP3, or a substation on IEC 61850, is a plant Atlas cannot read a word of. That has been true
since the very first version. It is the single most limiting fact about the product. And in a
document whose entire job is to list the limits, it was absent.

Not hidden, not denied — just never written, because it was so obvious to everyone involved that
nobody thought of it as a finding. That is exactly the kind of gap a register is supposed to catch,
and the register's own rules say to write a limit down the moment you notice it. So it is now entry
**R27**.

## And that turned out to be the argument

The protocol work had been parked for a defensible reason: it does not move either open target. One
of those targets asks whether Atlas puts the most likely alerts at the top of the list. The other
asks whether a stranger can re-run every published number. Adding a second language moves neither.

But look at what is actually being asked. Those two targets both ask *is Atlas right when it looks?*
Neither of them asks *can Atlas look at all?* Judging the second question with a ruler built for the
first will always return "moves nothing", no matter what the answer is. The ruler was wrong, not the
work.

With R27 written down, the argument becomes simple. Every language Atlas learns strikes a line
through part of that entry. And — this is the part worth keeping — **a language that turns out to be
unreadable is just as good a result**, because it makes the entry sharper instead of shorter. Some
of these protocols are encrypted, and for those the honest answer is that Atlas can see the shape of
a conversation and not its contents. Writing that down is worth as much as reading one.

So the programme is open again, with a criterion it can genuinely move.

## One sentence of caution, which is in the record

Reading more languages does not make Atlas better at its job. It makes Atlas *applicable* to more
plants. Those are different, and conflating them is the easiest mistake available here: a system
that can read nine protocols and is wrong in all nine is worse than one that reads a single protocol
well. The decision record says in as many words that no protocol work may ever be quoted as a
detection result. The honest sentence stops at *Atlas can now read this language*, and does not
continue.

Nothing else moved. No data was scored, nothing new was claimed, the partner conversation is still
blocked, and the scoreboard still reads eight of twelve.
