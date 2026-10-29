# 59 — Grouping is written down before it is scored

The sandbox showed that most of the extra catches came from how alerts are counted,
not from a cleverer detector. Consecutive seconds of one departure were spending a
whole shift's eight slots. Giving each departure one slot is what changed the count.

That rule is now a shared function. The same gaps, the same window, and the same
eight slots apply to every detector, using the alerts that detector already raised.
The numbers in the rule are the ones tried on the first HAI edition: 60 seconds to
join a sensor's own blips, 300 seconds to join neighbouring sensors, and no event
longer than 600 seconds. The alarm is placed where the departure becomes real, not
at the first faint twitch, and not as a second alarm at the top of the same event.

It has not been scored. The two later HAI editions are still waiting for one look.
