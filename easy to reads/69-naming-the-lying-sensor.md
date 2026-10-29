# 69 — Naming the lying sensor

When a reading is faked, Atlas can now usually say which instrument is lying and
what the true value probably was, on the plants this project simulates.

Before, it named the right sensor 96 times out of 156 and skipped whole kinds of
sensor. One mistake in how it read control loops was the reason. Fixed, it named
153 of 156, and on 150 runs it had never seen, 146, with no wrong names. Its guess
of the true value was within 5% of the instrument's range every time.

On a real wind farm, where nobody attacked anything, Atlas stayed quiet: 74 alerts
in four years across six turbines, and the turbines' own logs explained 57 of them.

Sentiel, the people engine, still finds only one of the two insiders in the public
dataset. Five new ideas were tried and none worked. That is written down too.
