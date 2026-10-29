# 35 — The facet a sentence should not have been carrying

This one is not a measurement. Nothing got quieter, nothing got louder, no number in the log moved
by a decimal place. It is a repair to how Atlas decides what a piece of evidence *is* — and the
reason it is worth writing down is that the old way had a failure mode nobody would have noticed
until it bit.

## The setup

Atlas's evidence has a `kind`: was this a reading that left its band, or a change in the structure
between devices? Four kinds, that's it.

The trouble is that "a change in the structure between devices" covers several very different
things, and Atlas's explanations hang on telling them apart:

- A workstation that has **never** commanded this PLC starts writing to it. That is not how plant
  engineers work, so it argues *for* an attacker and *against* maintenance.
- A machine that already talks to this PLC every day starts using an unfamiliar function code. A
  commissioning engineer leaves exactly that trace, so it argues for **both** — and this is the
  wall we keep running into.
- A work order says somebody was authorised to be in there on Tuesday. That argues for maintenance
  and against an attacker.

Three different facts. One `kind`. So how did the code tell them apart?

## It read the sentence

Every piece of evidence carries a `summary` — a line of prose written so a human can read it:

> `graph-finding:unknown_command_relationship: 10.0.0.9 issued 5 command(s) to 10.0.0.20 over a
> relationship that is absent from the learned command graph`

See the prefix? Three separate sessions, needing a field the ontology didn't have, each solved it
the same way: write a marker into the front of the human-readable sentence, then parse it back out
later. Graph findings did it. Command behaviour did it. Work orders did it.

And **four matchers** in Atlas's template code read those prefixes to decide which explanation a
fact supports or contradicts.

## Why that is worse than it sounds

Read that again with an engineer's eye. The decision about whether a fact **contradicts**
"this was planned maintenance" — one of exactly two asymmetries Atlas has for separating an
engineer from an attacker — was reached by string-matching the first word of a sentence written
for a human to read.

Which means: tidy up that sentence, make it clearer for an operator, drop the ugly prefix, and the
templates silently stop matching. No type error. No test failure outside the handful of tests that
check the markers themselves. Atlas would just quietly stop being able to tell an unknown master
from a maintenance visit, and the first sign would be an explanation ranking that had gone soft for
reasons nobody could find.

That is a landmine, and it was armed.

## What changed

Evidence now has two proper fields: `facet_kind` (one of three values, checked by the type system)
and `facet` (which feature). The promoters set them. The matchers read them.

The sentence still says the same thing — we did **not** touch the prose, because operators read it
and because changing it would have made this a behaviour change instead of a repair. The prefix is
still there. It is just no longer load-bearing.

Three small guards came with it:

- **Half a facet is refused.** A kind with no feature names nothing; a feature with no kind can't
  be checked against the list of valid ones. You set both or neither.
- **The typed field wins.** If the sentence and the field ever disagreed, the field decides. That
  is the whole point, and it's the only thing a test can actually observe about which one got read.
- **Old evidence still works.** Anything built without a facet falls back to reading the sentence,
  exactly as before. That's what keeps the existing test fixtures honest instead of silently
  changing what they prove.

## How we know nothing moved

This is the part that matters for a repo that has spent this much effort on not fooling itself.

The test takes every fact the three promoters can build, runs it through the whole template library
twice — once as built, once with the typed fields stripped out so the old string-parsing path is
forced — and compares not just *which* explanations matched but *what role* each match played.
Supporting versus contradicting. If a facet had flipped a "supports" into a "contradicts"
anywhere, that comparison fails.

It doesn't. The verdicts are identical, fact for fact, role for role.

There is a separate test that pins the public numbers in the experiment log — 646.58, 53.26,
14071.07 — so that a future edit can't rewrite them in place and call it a refactor.

## The one test that did fail

Worth reporting, because it is the interesting part.

The repo has a guard that says: *the shared ontology package must not have changed since PART 6B.*
It exists to stop the enterprise engine quietly forking the data model that both engines share.
Touching `Evidence` trips it, by design.

That guard was **the only pre-existing test that failed** — 3078 tests before, 22 added, 3099
passed and one failure, and the failure was the tripwire rather than anything about behaviour.
Which is itself the cleanest evidence available that nothing moved.

It also has a documented way through, and two earlier records have already used it: when a later
decision genuinely has to open an ontology file, the file gets named in an allowlist alongside the
record that opened it, rather than the freeze being switched off. `store.py` is in there for ADR
0038; `narratives.py` for ADR 0045. The three files here joined them, named against ADR 0070. The
freeze still holds for everything else in the package.

## What did not change

Worth being blunt, because "we improved the evidence model" is the kind of sentence that invites
people to assume more happened than did:

- **Command-behaviour evidence still matches no explanation at all.** It's been stamped since D1
  and no template reads it. This work typed the stamp; it did not wire it up. That's a separate
  decision that needs its own argument. **That argument is note 36 (ADR 0071);
  the wiring landed there, and the maintenance-vs-attacker tie survived it.**
- **The known-station wall is exactly where it was.** An engineer and an attacker on a link that
  already exists still look the same. 0 of 16. Unchanged.
- **Nothing was measured.** No corpus was run. No row was appended. If you were hoping this note
  ended with a number, it doesn't, and a refactor that produced one would be a refactor that did
  something it shouldn't have.

## The one sentence

A machine-readable fact was living inside a sentence meant for humans, four matchers depended on
it, and now it lives in a typed field where the compiler can see it — with the prose left exactly
as it was and every verdict proved identical.
