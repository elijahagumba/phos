# 171. The sealed dataset would not stay sealed

*The record had a box labelled "how secret is this?" and let the person filling in the form tick it
themselves. ADR 0416.*

Note 170 ended with a confession. The research record asks which tier a dataset belongs to — may it
be used freely, scored exactly once, or never touched — and it took the answer on trust. Here is
what "on trust" cost, and what replaced it.

    10|## The hole, exactly

`docs/rules/data-tiers.md` is the file that says which datasets may be read. Some of them are
sealed: they were set aside as a final exam, and the rule lists them under a heading that reads
**"Never read, score or iterate on"**. `hai-21.03` is one of them.

The audit declared a run on it. The declaration went like this:

```
"corpus": "hai-21.03",
"tier":   "iterate"      ← a lie, and nobody checked
```

and the record accepted it.

The code did have a guard. It refused any declaration with `"tier": "never"`. Read that again: it
    20|refused the *word* `never`. It never looked at the *corpus*. So the check was asking the author
whether they had done something they were not allowed to do, and taking their word for it — which is
not a check, it is a signature. Anyone who typed `iterate` was through.

Worse, the claim had been written down as done. The decision record said, in as many words, that a
sealed dataset stays unread because "the record refuses to declare one". That sentence was false
from the day it was committed, and a whole document repeated it.

## What it does now

The tier is no longer an answer the declaration supplies. It is a fact the record *looks up*. The
    30|declaration names a corpus; the record opens the rule file, finds that name, and reads what the rule
says about it. Three things follow, and each is a refusal:

**A sealed dataset cannot be declared, no matter what the form says.** The lookup happens before the
record is even given a number, so a refused declaration leaves nothing behind. Type `iterate` all you
like — the rule still says never, and the rule is what counts.

**A dataset nobody has heard of cannot be declared.** If the name is not in the rule file and not in
the registry of datasets the project keeps, the answer is no. This matters more than it sounds. The
tempting default — "not mentioned, so probably fine" — is how an unvetted dataset gets a run and a
    40|number attached to it. An unknown thing is unknown, not approved.

**A declaration that states the wrong tier is refused at the gate.** Not refused when it is written —
a record of what someone intended is still a truthful record — but refused when the run is about to
happen, which is the moment the wrong answer would do damage.

The message names the rule and quotes the sentence that did the refusing, so the person reading it
can go and check rather than take the refusal's word for it:

```
refused: hai-21.03 cannot be declared.
  docs/rules/data-tiers.md — Never read, score or iterate on `hai`, `hai-21.03`, …
  the rule names 'hai-21.03' in the never-read tier; the declaration's own `tier`
  field cannot overrule it, and said 'iterate'
```

    50|## A test that reads the rule instead of restating it

The test whose absence this whole episode was does something slightly unusual: it does not contain
a list of sealed datasets. It opens `docs/rules/data-tiers.md`, parses it, and asserts that every
single name the rule puts under "never read" is refused at declaration — and refused again for every
value the tier field is allowed to take.

The difference matters. A test holding its own copy of the list would go stale in the ordinary way:
somebody adds a dataset to the rule, and the test keeps passing against last year's names. This one
cannot. Add a corpus to that sentence and it is covered the moment the sentence lands. **17** names
    60|at the moment of writing, which is more than the five datasets a person would list — the rest are
seed sets and scripts named in the same sentence, and one is a command-line flag the parser has
always read as a name. That last one is a small known wart, disclosed rather than quietly tidied,
because tidying it changes how a different guard behaves and deserves its own record.

Two more tests exist only to stop that table passing while proving nothing: one checks the lists
actually came out non-empty, the other that no name appears in two tiers at once.

## And one check that could not fire

A gate test for "sealed dataset labelled as sealed" would have been satisfying and useless. The
record already refuses that combination before it can be written, so the situation never reaches the
    70|gate — a test for it would pass forever while testing nothing. The gate tests therefore cover the
combinations that *can* reach it (labelled `iterate`, or labelled `once`), and one test asserts that
those two are the only ones reachable. A check that cannot fire is worse than no check, because it
looks like coverage.

## What this does not claim

That any of it ran inside a live Cursor session — the two editors' hooks are driven in tests with
each editor's documented message shape, which checks the contract and not the integration. No dataset
was opened, scored or even listed. No number was produced, no finding exists at any level, and the
next phases of the plan — the wider record kinds, the contradiction detection, the self-measurement —
    80|are untouched.

What is true is narrower and worth having: the sentence in the decision record is now true, and the
way it is kept true is that the rule file is read rather than believed.
