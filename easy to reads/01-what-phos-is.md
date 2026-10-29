# What PHOS is

**What this is:** the idea the whole project is built on.

**Why it exists:** most cybersecurity tools look for *known bad*. PHOS looks for *meaningful
departures from normal*, then explains them.

## The factory and the office are not the same kind of “quiet”

Imagine two buildings.

In a **chemical plant**, “normal” is a recipe. Pumps, valves, and temperatures follow a process. If
the same valve opens at 2 a.m. every Tuesday, that can be healthy. If it opens at a time the recipe
never uses, that may be a problem even if the command itself is a perfectly legal industrial
message.

In an **office**, “normal” is people. Staff log on, send mail, copy files. Tuesday 2 a.m. logons
might be a night-shift admin — or a stolen password. The same count of emails means different things
for a receptionist and a salesperson.

A single “one model of everything” would smear those two worlds together. PHOS therefore builds
**two engines**, engineered separately, that both write into **one shared language**:

- **Atlas** watches industrial / operational-technology (OT) plants.
- **Sentiel** watches enterprise / cloud organisations (people, hosts, roles).
- **PHOS Intelligence** is the planned layer that would later stitch their stories together. It is
  designed, not built.

## Signatures vs behaviour — the wanted-poster problem

Signature tools are a **wanted poster**: they match faces that have already been photographed. A
novel attack has no poster. An attacker who already holds a valid password and sends well-formed
commands often **breaks no signature at all**. What they change is the *behaviour* of the plant or
the person.

PHOS is closer to a **good night-shift operator**: they know how the plant usually sounds, notice
when it doesn’t, and can say *why they think that* — pump, recipe change, sensor fault, or
something they cannot yet name.

## Honesty is part of the product

A reported “90% confident” must mean, empirically, about 90% on data the system was not allowed to
study while learning. If it cannot say that, the number is not shown.

If the false-alarm load is so high that nobody would trust the queue, PHOS **strikes the detection
claim** even when recall looks perfect. A smoke detector that screams all day is not “highly
sensitive.” It is unusable. If two live explanations sit at the same ceiling, PHOS **stays silent**
rather than picking the story whose name comes first in the alphabet.

## What this is not

- Not a catalogue of known malware or exploits.
- Not a live system hooked to a real plant or a real company network.
- Not general artificial intelligence. Candidate explanations come from **written templates**
  (see [Competing explanations](05-competing-explanations.md)).
- Not finished. There is no public API and no operator UI in this repository.

## Where to read more

- Project front page: `README.md`
- Plain-English walkthroughs: `easy to reads/README.md`
- Running engineering log: `PROGRESS.md`
- Decision index: `docs/adr/README.md`
