# 152. Three witnesses, and a search for what they miss

*The next Atlas programme is named. It starts after the protocol work closes. Nothing was built or scored. ADR 0368.*

Today Atlas checks six rules that people wrote by hand. One of them was
copied by hand out of the simulated plant's own controller program. On the
simulated plant, none of the six ever broke. The page behaves as promised. It
has not been shown to catch anything.

The next programme asks a harder question. A plant has three independent
witnesses. Its controller program says what the machines should do. Physics
says what the process can do: water in, minus water out, is the change in the
tank. Its engineers say what must never happen. An attacker who wants to stay
hidden has to fool all three at once. Which attacks can do that, and which
cannot?

It goes in four steps, and each waits for the one before.

First, Atlas reads the controller program and writes the rules itself. The
first test is simple. The valve rule it writes must match, number for number,
the one copied by hand. If it does not match, the new rule is refused. The old
one is not changed to agree with it.

Second, physics rules are added, each written down before it is used. An
attack that changes what the controller does while replaying normal readings
is written down before it is generated.

Third, before that attack is run, Atlas writes down which kinds of attack it
expects to catch and which it expects to miss. Then the attack is run once.
The test is whether the prediction was right, both ways. A miss that was
predicted is recorded as a blind spot, not as a win.

Fourth, Atlas searches for attacks that fool all three witnesses, and names
the smallest added rule or sensor that would catch each one.

A found attack is a working recipe against the plant it was found on. So
recipes stay inside this lab, are never exported, and a recipe for a real
plant would never leave that plant.

None of this has started. It waits for the protocol programme to close.
Nothing was scored. Version 1 still stands at eight of twelve.
