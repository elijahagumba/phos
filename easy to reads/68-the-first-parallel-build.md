# 68 — The first parallel build

Four agents worked side by side for one night, each on its own branch, after the
seeds and data splits were written down first (note 67).

Two branches are now on main. One writes the reports a regulator asks for after an
incident, for the EU's NIS2 rules and the UK's, and refuses any sentence that does
not point at evidence. The other checks commands against the plant: when a valve is
told to move and does not, Atlas now reads that as a fault, not maintenance. On
simulated plants that was right 20 times out of 20, on runs it had built on and on
runs it had never seen.

The same branch lets the plant map say which sensor is lying, without changing which
alerts fire. On nine kinds of sensor it named the right one 96 times out of 156 and
the wrong one once. Three sensors were almost always named; three were mostly left
unnamed. The goal is 70%, so it is not met yet.

It also tried to make Atlas's confidence mean something, and found it does not yet:
right and wrong answers carried the same number. That number is not shown.

All of this is on simulated plants. It says what to build next, not what a real
plant would see.
