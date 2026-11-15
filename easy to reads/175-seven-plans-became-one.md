# 175. Seven plans became one

*There were seven live plans at once. Gathered in one place, the engine turns out to meet five of its
seven targets already, only two questions are left — and the plan that was parked turns out to be the
one worth building.*

Atlas had seven open programmes: a daily improvement contract, a roadmap of questions, two build
briefs, an operating plan, the research-record work, and the blocked partner conversation. Every one
of them was sensible when it started. Together they meant that on any morning there were seven
defensible things to do and none of them visibly moved the scoreboard.

That is worth saying carefully, because it is not a story about losing discipline. Six of the seven
were opened while the partner conversation was blocked — and that conversation is the one thing that
would have put the work in order. Plans accumulated because the thing that orders plans was missing.

## The targets already existed

This is the part that was buried. Atlas has seven targets, **A1 to A7**, written down with their
definitions *before* anything was measured, so they cannot be quietly adjusted to match whatever
happened. They are not vague: "better where it matters" means strictly higher than the best checked
competitor on at least three of five datasets. "One configuration" means no setting differs between
datasets. "Reproduced" means one command regenerates every number and somebody outside the project
has run it.

Nobody had gathered the current standing in one place. Doing that took an afternoon of reading
records, and the answer is:

**Five of the seven are already met.** Measured where others measure, better where it matters,
network against physics, alerts that settle themselves, one configuration. Met, recorded, with the
records to point at.

**Two are not.** And those two are the whole of "make Atlas as good as it can be with what we have".

## The two that are left

**A queue that ranks.** An operator can only read so many alerts in a shift, so the ones most likely
to be real should be at the top. The original target was that half of all attacks have a true alert in
the top tenth of their shift's queue — and that target was **retired**, because it turned out the
queue is shorter than the number of alerts an operator can read, which makes "top tenth" meaningless
rather than difficult. Four replacement measures were written in operator units instead. Separately,
a ranking stage was built, measured, and **refused**.

So this is a question that has already been attacked once and already had its ruler replaced once.
The new roadmap records it as a question, not a job, and says the declaration must state in advance
what result would mean an Atlas queue simply cannot be ranked. If that is the answer, it is a finding
about the product and belongs on the public record.

**Reproduced.** One command must rebuild every published number, and an outsider must have run it. It
fails on three frozen constants and on the outside run, and both permitted attempts are used up.

This one goes first, and the reason is worth understanding. "One configuration" is already met — but a
single configuration nobody outside can execute is a claim about one laptop. Reproduction is what
turns every other met target into something a third party can check. It is also the only one whose
failure is partly plumbing rather than science, which makes it the one where effort reliably turns
into progress.

## The plan that was parked is the one worth building

Here is the thing that only became obvious once all seven were laid side by side. One of the parked
briefs was not a side project at all. It was the product.

It asks a plant for its laws from **three independent directions**.

The first is the **controller's own program** — the code running on the box that opens the valves. Read
it and you can work out what it is *supposed* to do, without asking anyone.

The second is **physics**. Water going into a tank, water coming out, and the level changing: those
three have to agree. They agree whether or not anyone wrote the rule down.

The third is the **engineers' signed list** of rules in force.

A genuine problem has to stay consistent with all three at the same time. That is a much harder thing
to hide inside than any single check, and it covers the nastiest case in this field: a controller
quietly reprogrammed, reporting numbers that match what it *used* to do. The old program, the physics
and the signed list stop agreeing, and you do not need to have seen the attacker before to notice.

Then two steps that nothing else in this industry does.

**Write down the blind spots before the test.** Before generating any attack to measure against,
Atlas states which kinds of departure it can catch and which it cannot. Then the test runs once, and
the score is how well the prediction matched — *in both directions*. A departure it predicted it would
miss, and did miss, counts as a correctly identified blind spot, not as a success. Every competitor's
coverage claim is the other way round: run the test, then report what was caught. A prediction made
first can be wrong, which is exactly what makes it worth something.

**Then look for the attacks that are invisible, and price the fix.** Search for departures that are
consistent with the code *and* the physics and break no signed rule — the ones nobody could catch —
and report each one with **the smallest extra rule or sensor that would make it visible**. The output
is not an attack. It is a sentence like: *this kind of problem cannot be seen on this plant as it is
wired, and one flow meter on this pipe would change that.*

That is a different business from selling alerts. Alerts are a cost. A proof of what you cannot
currently see, with the cheapest fix attached, is something a plant manager takes to a board.

**The fence on that, which is not negotiable:** anything found that way is a working recipe against
the plant it was found on. It stays with that plant. It is not published, not generalised, and not
carried anywhere else. The later steps also stay shut until after 6 January 2027, because the Ofwat
bid comes first.

## What was closed, and what was parked

Named out loud, because an unnamed plan is one a future session will restart. The roadmap of questions
and the daily contract are **absorbed** — a good day's measurement is a useful shape, it just is not a
destination. The protocol brief is **parked**: more industrial protocols is real work but it moves
neither remaining target, and without a plant's own recording a second protocol reader is
specification without evidence. The triangulation brief above is **adopted** as the roadmap's later
acts. The older brief stays closed. Parked means not deleted and not forbidden — only that restarting
it needs a record naming the target it moves.

And the first job on the new list is not building anything. It is a measurement that was **written
down two weeks ago and never taken**. Under the project's own rules, a declared experiment with no
result is the one state the record exists to make visible, so finishing it is the cheapest honest work
available.

## One correction worth making

The page that holds all this was checked against eight requirements and passed all eight. It behaves
exactly as specified. And across thirty-nine runs over the simulated plant, **it never once spoke** —
because that plant never broke a rule.

So the page is proven to behave and is not proven to speak when it should. Earlier notes implied its
checks were still outstanding; they were done, and the records say so. What is missing is not more
checking. It is a plant doing something wrong, which is exactly what the triangulation work above
builds.

## What did not change

Nothing was unlocked. The partner conversation is still blocked, and the dashboard, the interface and
the cross-engine correlation are still closed behind it. Every frozen number is still frozen, and no
target in the new roadmap may be met by moving one. The datasets that may only be read once are still
unread. The scoreboard still says eight of twelve across the whole product, and its freeze date has
not moved.

A roadmap is not permission. It is an order of work — and now there is one of them instead of seven.
