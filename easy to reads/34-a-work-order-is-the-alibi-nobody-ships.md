# 34 — The alibi nobody ships

Note 33 ended on a wall. Atlas can tell you a pump left its envelope, but on the readings alone it
cannot tell you whether that was an engineer doing scheduled work or an attacker with valid
credentials. Both look identical in the numbers. We have written this down several times, and each
time the honest conclusion was the same: on process telemetry alone, refuse to pick.

There is a way through, and it isn't cleverer maths. **Ask the maintenance system.**

Every real plant runs one — SAP Plant Maintenance or IBM Maximo, mostly. It is the boring database
where somebody writes down "we're servicing pump P-101 on Tuesday between ten and two." If a pump
misbehaves inside that window, there is a work order covering it. If it misbehaves at two in the
morning with no order open, there isn't. That's the alibi, and no dataset in security research
ships one.

## What already existed, and what didn't

The machinery to *use* a work order has been in the repo since Session E3. A work-order fact
supports the "planned maintenance" explanation and argues **against** "unauthorised control." That
was built and tested.

What was missing is embarrassing in hindsight: there was no way to get a work order *in*. The
function that accepts them takes hand-built objects, so every test wrote its own fake. The inlet
had never seen a real maintenance record in its life.

This is the piece that reads one.

## Four things it refuses to do

The adapter is small. Most of it is refusals, and each exists because the mistake it prevents would
be invisible rather than loud.

**A missing file is not an empty file.** If you point it at an export that isn't there, it stops.
It does not quietly return "no work orders," because that sentence means *"nothing was scheduled,
so nobody has an alibi"* — and a forgotten file would then exonerate nobody and incriminate
everybody. Empty is a finding. Missing is silence. They are not allowed to look alike.

**Columns are declared, never guessed.** It does not sniff which column holds a date by looking at
what's in it. Guess that wrong and every maintenance window silently shifts, and nothing tells you.

**`P-101` is not `P-1010`.** No prefix matching, no fuzzy matching. A near-miss would let one work
order cover a machine it never mentioned. And if the export names a unit the plant didn't declare,
that's an error you get told about — not a row quietly dropped, which would leave that machine
looking permanently unexplained while the file appeared to load fine.

**A cancelled order authorised nothing.** Maximo's `CAN` and SAP's `CRTD` draft are not permission
slips. Only genuinely sanctioning statuses count, and the rest are excluded and counted out loud.

## What it does not claim

A covering work order does **not** mean the change was innocent. An attacker who can read the
maintenance calendar can act inside a window on purpose, and an export can be forged like anything
else. What it does is make maintenance a *live explanation* — weighed against the others, with the
losers still on screen. That is the whole product, not a verdict.

And there is a number here that doesn't exist, which is the honest ending. **We measured nothing.**
There is no maintenance export on disk, because no public dataset ships one — HAI, BATADAL,
distillation and Data4Cyber all label attacks, not scheduled work. So there's a tripwire in the
tests: while no corpus declares a maintenance export, any claim about work-order coverage on public
data is refused outright. The one shortcut available — invent a plausible maintenance calendar for
HAI and show the join lighting up — is exactly the thing the roadmap forbids, and it would be
scoring our own fiction.

So this note ends with a mechanism and no result. What changes is the conversation with a real
plant: instead of asking for "your maintenance data" we can now ask for a Maximo `WORKORDER`
export with six named columns, and it drops into something already built and already tested.

Detail: [ADR 0069](../docs/adr/0069-cmms-exports-reach-the-work-order-inlet.md). Nothing here
changes 646.58, 53.26, or CERT's 0.104.
