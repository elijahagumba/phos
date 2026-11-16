# 188. We shortened the front page and named our weakest comparison

The front page of this project had grown to about four thousand words. It opened by defining three
technical words before it said what the thing was. Four lines of mathematics sat near the top. And
the most interesting thing on it — three detectors we built, measured, and then threw away — was
two screens down, past all the machinery.

So it was rewritten. It is now about twelve hundred words, and the order changed: what Atlas is,
what it will not do, the three detectors we refused, how it will be examined, and only then the
mechanism and the caveats.

Nothing about the project changed. No measurement moved. No bar moved. This note is about how it
reads, not about what it does.

## Two things we fixed while we were in there

**We named our own weak comparison.** The strongest number on the page is that the older engine
caught 131 of 160 attacks on three editions of a real industrial testbed, against 52 for the
baseline. The page used to call that baseline "the best baseline checked". That is true, and it was
also doing some quiet work, because the baseline is grouped min-max normalisation — which is about
the simplest thing you could put up against a detector. Anybody in the field who clicked through to
the record would find that out in a minute, and think less of us for making them look.

So the page now says what it is: an elementary opponent, named plainly, because a reader deserves
to know what a comparison is worth. We also say that a proper multivariate baseline was tried and
was worse for us, and that the harder baselines everyone would want are the next measurement and
are not done.

This makes our best number read as less impressive. That is the right direction. A comparison
somebody can judge is worth more than one they discover is thin.

**We said where the idea comes from.** The page had no mention of anyone else's work at all.
Checking declared rules against a process is not a new idea — it has a name in the research
literature and a body of work behind it. A page that cites nobody invites the reader to assume we
have never read any of it.

So there is now one sentence saying which family this belongs to, and claiming that what is new
here is not the checking. It is the custody: the rules come from the plant, not from us.

## Where the mathematics went

The four lines of mathematics were the contract stated exactly — which laws end up where, what the
page cuts at, which five words a sentence may never contain. They were on the front page because
they are precise, and precision is the point of them.

They now live in the paper about what the page refuses, one click away, and the front page links
them.

The important part is that moving them did not loosen anything. There is a test in this repository
whose whole job is to fail if the page and the code ever disagree — if the page claims the operator
sees ten lines while the code allows eight, or lists four forbidden words where the code has five,
the test breaks the build. That test now reads the paper instead of the front page. Two checks were
added to it as well: one that the paper is actually there, so a future tidy-up cannot leave the test
quietly passing against a missing file, and one that the front page still links to it.

That last bit matters more than it sounds. The easy way to ship a prettier page would have been to
delete the test. The whole reason anybody should believe this project is that we do not do that.

Decided in ADR 0443, which also records what is still owed.
