# The record that should not have been public

PHOS keeps a decision record. Every time something is decided — a bar, a refusal, a method, a
number — somebody writes down what was decided and why, before the thing is measured. There are
over three hundred of them now, and almost all of them are published, on purpose. A project whose
whole argument is "check our reasoning" cannot keep its reasoning private.

The rule for publishing is a single file, a manifest, that lists what leaves the private workspace
and what stays. It already held back the obvious things: the letters to people, the notes on how to
find a partner, anything describing money being raised.

And it published all the decision records. Not some — the rule says `docs/adr/*`, which means
every file in that folder, with no exceptions.

That was right for three hundred records and wrong for one.

## What happened

One of the records is about the company rather than the engine: what the destination is, how long
it would take, how much ownership that costs, how likely it is to work. It was written as an
internal decision, which is what it is. Then it went out with everything else, because it lived in
the same folder as the measurements and nothing was checking.

It had been publicly readable for a day. Nobody is known to have read it.

## The thing worth understanding

It is tempting to fix this by deleting the record. That would be the wrong fix twice over.

First, a decision record is immutable here. Once it is accepted it is not edited and not deleted,
because the point of writing decisions down before the result is that nobody can quietly adjust
them afterwards. A record deleted to tidy up an embarrassment is exactly the behaviour the whole
practice exists to prevent. **The decision was not wrong. Publishing it was.** So the record stays
where it is, and what changes is whether it travels.

Second, deleting one file does not stop the next one. The real fault was not that a particular
record was careless. It was that there was no gate — nothing between writing a record and serving
it to the internet. Fix the file and the same thing happens next time somebody writes about money.

## What changed instead

Two things. The record's path is now on the list of things that never leave. And the manifest gained
a second kind of rule, one it already used for things like personal email addresses: a list of
words and shapes that must not appear in anything published at all. Sums of money in the millions,
growth rates, the language of investment rounds. If any of them turn up in a file that is about to
go out, **the export stops** and a person has to look at it.

That direction of failure is deliberate. A stopped export costs somebody five minutes. A quiet one
costs something you cannot take back.

Each pattern was tried against everything currently published before it was added, to check it
caught nothing it should not. If a real measurement ever trips one — and one day one will — the
answer is to add that exact phrase to a short list of admitted exceptions, with the reason written
next to it. Not to weaken the rule.

## Two things said plainly, because it would be easy not to

The public index of records keeps the number and says the record is held back, rather than letting
it vanish. A missing number in a numbered list is a question a careful reader asks, and refusing to
answer it is worse than answering it.

And removing a file stops it being served, but it does not remove it from the published history,
where it was committed. That is how version control works. Anyone who already has a copy still has
one. Saying so is uncomfortable and leaving it out would be the kind of omission this project is
supposed to be better than.

*Records: ADR 0334, ADR 0342. See also
[the public record must move with the code](17-the-public-record-must-move-with-the-code.md).*
