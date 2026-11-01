# 162. We moved the alarm and half the problem moved with it

*A detector that catches far more attacks than the engine it competes with was rejected because
it was too slow. The obvious question was whether the slowness belonged to the detector or to where
the engine puts the alarm. We built the alternative and measured it once. Half the problem was the
alarm's position. The other half was the detector, and it did not move. ADRs 0398 and 0399.*

Our industrial engine raises at most eight alarms an operator shift. When more than eight things
depart in a shift it has to choose, and it chooses by strength: the eight loudest departures get an
alarm each. That is a budget, and budgets force trades.

An earlier piece of work — "lane 3" internally — added a second opinion to that engine. Instead of
asking "is this reading wrong right now?", it asks "has this reading been a little wrong for a long
time?" It keeps a running tally per instrument that grows while the reading sits above its own
normal and leaks away when it does not. On our simulated plant it caught **53 of 70** attacks
against the built-in engine's **32**, and lost none. It was rejected anyway, because its alarms
arrived later. At every setting of its one knob, later. That is written up in the record as a
refusal.

The reason was not obvious, and it was already written down. The alarm for a group of departures is
placed at the **first moment something in that group got strong enough** — where "strong enough" is a
level set by the group's single strongest member. So if a quiet, early departure happens to sit in
the same group as a very loud one, the loud one sets the bar, the quiet one cannot reach it, and the
quiet one — which would have raised its own alarm early if it had been alone — is **skipped**. The
alarm slides to the loud one's later moment. The tally detector's columns are sums, so they get very
large, so they are always the loud member, so they always take the alarm and always take it late.

That is a rule about **where the alarm goes**, not about whether the departure was seen. So the
question was worth asking: if we changed only the placement, keeping the detector and the eight-alarm
budget and the thresholds exactly as they were, would the lateness go away?

## What we changed

One thing. The alarm now goes at the **first moment any member of the group clears the threshold it
already had to clear to exist** — no level computed from the loudest member, no skipping of quiet
ones. The score that ranks alarms against each other is still the group's strongest peak, so the same
events win the same eight slots. The new rule has no knob at all: there is nothing in it to tune.

We wrote down all four pass conditions before running anything, in the record, with the command and
the result name: catch strictly more than 32 of 70; lose none of the 32 the engine already catches;
median delay no worse than one second, measured **both** ways; and no more than 5 of 20 harmless
events raising an alarm.

## What happened

Three of the four failed.

| | Built-in engine | Lane 3 | With the new placement |
| --- | ---: | ---: | ---: |
| Attacks caught, of 70 | 32 | 53 | **49** |
| Attacks both catch, of 70 | — | 32 | **30** |
| Median delay, on the attacks both catch | 0.85 s | 5 s | **0.80 s** |
| Median delay, each engine on its own catches | 0.85 s | 13 s | **6.10 s** |
| Harmless events raising an alarm, of 20 | 5 | 8 | **8** |

More attacks: yes, 49 against 32. No attack lost: **no** — two of the 32 went. Delay on the shared
attacks: **yes, and better than the built-in engine**, 0.80 s against 0.85 s, from 5 s. Delay measured
each engine on its own catches: **no**, 6.10 s. Harmless alarms: **no**, 8 against a ceiling of 5.

## What that tells us, which is the actual result

**The original diagnosis was right and incomplete.** Moving the alarm really did fix the delay
problem it was blamed for: on the attacks both engines catch, lane 3 went from 5 seconds to 0.80 —
slightly quicker than the engine it was losing to. Eight alarms moved earlier; none moved later.
That half was the placement's, and it is now measured rather than argued.

The other half was always the detector. Two of the four failures do not move at all when the
placement changes:

- **The harmless alarms.** Eight before, eight after. Moving the alarm re-timed them — one slipped
  from just inside its window to just outside, another came in — but the count never budged. Where an
  alarm goes is not how loud it is. A tally that gets large on ordinary plant behaviour will raise
  alarms on ordinary plant behaviour, and no placement rule can make it quieter.
- **The own-catches delay.** This one reads like a defeat and is partly a trick of the measurement.
  It compares 6.10 seconds over 49 attacks against 0.85 seconds over 32 — different sets of attacks.
  The 17 the built-in engine misses are exactly the slow, creeping ones, and **their** median delay
  is 11 seconds. So the number rises *because* the detector does the thing it was built to do. Any
  detector that catches more of those will look slower on that reading. That is worth knowing, and
  it is not an excuse: the condition said both readings must hold, both were reported, and one did
  not.

And the third failure is a new mistake, not an old one. A rule that only ever moves an alarm
**earlier** will eventually move it earlier than the event. In one run the alarm landed **378 seconds
before** the attack it belonged to, because a faint precursor 6 minutes upstream got chained into the
same group. An alarm that fires before the thing happens still uses up one of the eight slots, and
the attack it was for then has none. The old rule could place an alarm too late; the new one can
place it too early. Fixing that means adding a limit — "don't look back more than *this* far" — and
that is a number, and adding a number *after* seeing where it broke is how you fool yourself. So it
was not added. It is written down as the next thing, to be declared before it is tried.

## Why this is worth the space

The easy move here was to announce a win: 49 is more than 32, and the delay on shared attacks beat
the engine. It would have been false. The hard move, and the useful one, is that we now know exactly
which half of a stubborn failure belonged to the machinery and which to the idea — and the idea's half
is real. That distinction is the whole reason the experiment was run, and it cost one afternoon
rather than another quarter of guessing.

Nothing here was scored on a real plant. The plant is one we generate ourselves, so this is a
diagnosis and not proof of anything about a real factory. No frozen number moved: the built-in
engine is byte-for-byte what it was.
