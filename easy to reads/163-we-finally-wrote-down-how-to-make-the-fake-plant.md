# 163. We finally wrote down how to make the fake plant we have been describing since October

*Two refused detectors stay in the code, named as refused. And the simulator we registered a
forthcoming-for-a-fortnight has a generator, which means its data can now actually be produced.
ADRs 0400.*

There is a pattern in this project that took a while to see. A detector is built, measured, and
turned down. And then what happens to it?

The tempting thing is to delete it. The code did not work, the record says so, why keep it? The
answer is that a measurement is only worth something if someone can run it again. If the built
detector disappears, the number in the record becomes a claim rather than a result, and the next
person who wants to try a variant has to rebuild the thing from the description. So the refused
modules stay.

Two of them stay now. One catches 53 of 70 attacks against the built-in engine's 32 and was
rejected because its alarms arrived too late. The other re-placed those alarms and was rejected on
three of four conditions anyway. Both remain in the tree, both are imported by nothing that matters,
and a test now fails if anyone tries to quietly wire either of them into the law page. That last
part is the bit worth having: an undeclared detector is harmless, and an undeclared detector that
has quietly become load-bearing is not.

## The more interesting half

Since 17 October this project has referred to a simulator called GRFICS. Its runs are declared,
number by number: twenty of them, ten to develop on and ten sealed. Its address is pinned, its
licence is hashed, and its permission came from the company's chief executive in writing.

None of it had ever been generated. There was no generator. The registration described a corpus that
no command in the repository could produce.

That is now a script, and what it refuses is more interesting than what it does.

It reads the run list from the registration rather than from a copy, so the two cannot drift. It
refuses every sealed seed by name, and the command has no option that can reach one. It checks the
licence file against the digest recorded in October and stops if it has moved, because a different
commit is a different corpus and pretending otherwise is how a measurement stops meaning anything.
And it stops if it cannot find the simulator's own list of devices, because guess the order and every
run is silently mislabelled.

The script generates no data yet. Driving the simulated plant and capturing what it produces is the
next step, and it gets its own record.

## Why this one is worth doing next

Simulators are cheap and real plants are not, so what does a fake plant give you that the one already
here does not?

The existing simulated plant is ours. We wrote it, we know what is in it, and when it misbehaves we
can change it. GRFICS is somebody else's, built by a company that sells simulation, and that
makes it a fairer test of whether any of this generalises past our own assumptions.

But the real reason is one pair of runs out of the twenty. Seed 97201 is a tank level that freezes
because the instrument failed. Seed 97206 is the same tank level, freezing in the same way, because
an attacker froze it. Same signal, same shape, different cause.

The whole claim of this project is that evidence can separate explanations. That pair is the smallest
honest test of it, and no dataset here can pose the question at all.

## What none of this means

It does not mean the simulator will show anything. It is a simulated plant, which makes any result
a diagnosis and not proof, and this project says so in every document that mentions it. A good result
there would mean the idea survives a fair test. It would not mean anything about a real factory.

It is also not a win, a release, or a step towards being finished. It is a generator. The interesting
part comes after, and it may well come back negative.

Version 1 still stands at eight of twelve. The design-partner conversation is still the thing that is
blocked, and two emails went out this weekend towards it.
