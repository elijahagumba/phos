# 164. The cyber half of the experiment turned out to be possible, and that is the interesting part

*Everyone expected it to fail. It did not fail, and the reason it did not fail is worth more than
the data. ADR 0402.*

There is a simulator called GRFICS that this project has been talking about since October. It is a
fake chemical plant with a real control program, real Modbus traffic, and a real operator screen.
Somebody at the company that made it — Fortiphyd — wrote a design document for an experiment you
could run on it, and the experiment is a good one.

Here is the idea. There are two ways a tank level reading can be wrong.

The first is that the instrument itself broke. A level sensor freezes. It stops moving and reports
the last thing it saw, forever. Everyone downstream is fooled: the control program is fooled, the
operator's screen is fooled, and they are fooled *identically*, because the lie entered the data at
the source. The program and the screen agree with each other and both are wrong.

The second is that somebody intercepted the wire between the control program and the operator's
screen and started serving an old reading over and over. The control program is untouched — it is
still reading the real sensor. Only the screen is lied to. So now the program and the screen
*disagree*.

That difference is the tell. One is a broken instrument, the other is an attack, and you can tell
them apart by asking a single question: do the program and the screen agree?

## Why we expected to fail

The attack half needs someone to sit on the wire. In the company's own setup, that position is
created by poisoning the operator screen's memory of where the gateway is — a technique called ARP
spoofing — so that the screen's traffic comes to the attacker instead of the router.

We cannot run that setup. It needs a kind of Docker network that only works on Linux with a real
network card. This machine is a Mac. So earlier this month the project registered a *different*
corpus — the same simulator, the same runs, but all on one flat Docker network with no router in it
at all.

And that is exactly what should have broken the attack half. ARP spoofing needs a gateway to sit
behind, and a flat network has no gateway. The work order that opened this session said so plainly,
and told us to capture the physical run alone if the cyber half could not be done, because a fake
cyber capture would be worse than none.

## It works, and here is why

The premise was wrong, and the error is a useful one. ARP spoofing does not need a *gateway*. It
needs a **shared wire** — two machines on the same broadcast segment, where one can lie to the other
about where an address lives. A gateway is just the usual thing you want to intercept traffic to.

On a flat Docker network, the attacker and the operator screen are on the same shared wire, and so
are the attacker and the control program. That is *more* shared wire than the company's own design
had. The attack does not need to cross anything.

So we tried it. The attacker poisoned the screen's memory of the control program's address — the
screen's ARP table changed from the control program's hardware address to the attacker's — and a
firewall rule redirected the screen's database traffic to a relay, and the relay started replaying a
frozen reading.

Then we watched.

```
HMI screen:            43.9048   43.9048   43.9048   43.9048   43.9048
engine true value:     44.1262   44.1091   44.0756   44.0333   43.9864
```

The screen held one number while the real tank moved underneath it. That is the tell, live, on a
network that was supposed to make it impossible.

But a frozen number proves nothing on its own. A screen whose polling has simply broken also shows
a frozen number. So we did the check that separates the two: we restarted the relay so it would
capture a *different* value to freeze.

```
HMI screen before restart:   43.9048
HMI screen after restart:    43.8864
```

The screen followed the relay. It was not stale — it was being fed. That distinction is the whole
difference between a capture and a plausible-looking file.

## Two things that changed the design

Two findings came out of doing this by hand before writing any code, and both would have wrecked a
harness built the obvious way.

**The screen only saves a value when it changes.** With the instrument frozen, the operator's
database stopped writing rows for that tag altogether — nothing new arrived for the rest of the
event. A harness that read the screen's history would have reported "no data" at precisely the
moment the event was most interesting, and a reader could easily mistake a stalled archive for a
stalled plant. So the harness reads the screen's *current* value, and records separately whether the
archive is still moving.

**The attack cannot freeze one tag, and the physical fault can.** The screen asks for thirteen
registers in a single request. A relay serving only one of them makes the other twelve read zero,
which is a wildly different event. So the relay serves the whole thirteen-register block.

And here is a correction, because the first version of this note got it wrong. I wrote that the
block relay froze the target and left the other twelve live. It does not. Frozen mode caches the
whole list on its first poll and replays all thirteen forever, so the pressure and the flows freeze
alongside the level. I had taken the "other tags kept moving" observation *before* the redirect was
in the path — at that moment the screen was still reading the real plant, which is precisely the
passthrough I had already learned to distrust. I read it as evidence about the relay when it was
evidence the relay was not yet connected.

So the two runs are **more alike than I said, and the difference between them is in a better place
than I said.** Both freeze what the operator sees for the tank level. What differs is *where the lie
enters*:

- In the physical run it enters at the instrument. The control program is fooled, the registers are
  fooled, the screen is fooled — everyone agrees, and everyone is wrong.
- In the cyber run it enters on the wire to the screen. The control program reads the real sensor the
  whole time and never notices anything, so the screen and the program **disagree**.

That is the tell, stated properly. And it is visible in the captured numbers themselves: the value
the control program saw moved by **0.0000** in the physical run and by **8.29** in the cyber run,
while the screen froze in both.

One thing I cannot claim from the files: the captures record only the level on the screen side, so
"the pressure froze too" is something I measured on the live stack afterwards, not something the
capture contains. That is a gap in the capture, and it is written down as one rather than papered
over.

## So I recaptured it, and it took three goes

The gap was closeable, so I closed it: the harness now records all thirteen tags the operator screen
binds to the plant, on both sides, and both runs were taken again.

It was not a clean second attempt. The first wider run had **no live baseline at all** — I left the
interception running through the quiet phase, so every tag was frozen from the first sample and there
was nothing to compare the event against. The plant had been moving the whole time (34.6 to 38.5)
while the screen sat still at 34.5693. I had built a run with no "before".

Fixing that, I introduced a second bug: a check that refused the run at the ten-minute mark even
though the relay was working perfectly. A refusal that fires when nothing is wrong is just as bad as
one that never fires — it threw away a good run and blamed the mechanism for a fault in my own
condition.

Then the safety check itself was wrong, twice. I had it test whether the gap between the screen and
the plant was large. On a quiet plant, a frozen reading sits *close* to the live one, so a real freeze
looked like no freeze at all: the screen held 43.9719 for a full minute while the plant moved, and the
gap never got past 0.16. I loosened it to look at the whole event instead, and a single sample from
before the freeze took over broke that too.

At that point the honest move was not to loosen it a third time. Loosening a threshold until your
result passes is how a measurement lies to itself. So the check no longer looks at magnitudes at all.
It skips a short settling window — declared in the code before the run, not chosen after — and then
asks whether the screen held **exactly one value** for the rest of the event while the plant kept
moving. Exact, or it refuses.

## What the files now show

| | physical run | cyber run |
| --- | --- | --- |
| tags that were moving, then froze | **1** (level) | **6** (level, pressure, two flows, two valves) |
| pressure during the event | still moving | frozen |
| the plant itself | frozen | **still moving** |

Which is the whole experiment, now readable straight out of the data instead of out of my memory of a
terminal.

And one caution the wider stream taught me, which the narrower one could not: **four of the thirteen
tags never move at all**, even in a perfectly healthy minute. They are pinned by the simulation. They
are not evidence of anything, and a table that counted them as "frozen by the attack" would be
inflating the result by four. They are marked separately for exactly that reason.

## What this is not

It is not a measurement. Nothing here scores anything — no recall, no rate, no confidence. It is six
files per run recording what happened, from one clock, so that a question can be asked later.

It is also not cross-zone evidence. There is no router on this network, so there is no firewall log,
no intrusion detection, no ARP monitor. The company's design leans on those; this corpus cannot
produce them, and claiming otherwise would be exactly the kind of thing this project exists to
refuse.

And it is not a real plant. It is a simulator. Any result from it is a diagnosis, not proof.

But the pair can now be posed — the same freeze, once for a failed instrument and once for an
attacker, with both sides of the comparison recorded at the same instant. A fortnight ago this
corpus had no data at all and its cyber half looked impossible. Now it has the half that mattered.
