# 93. Five questions, none of them a promise

*The next programme, written down before any of it is measured. ADR 0298.*

The attempt to build a clearly stronger engine is closed. What follows is five questions.
Each one might fail, and the record says so in advance.

The first asks whether a command can be wrong while every sensor still looks ordinary. The
first job is to build a fair test and see if the engine we already have catches it. A new
detector comes only after that, and only if the test says the old one misses.

The second asks whether several weak signals are one incident or several. Linking them
loosely invents a story. Linking them tightly splits a real one. A tally that caught more
attacks and arrived later does not get to count as a pass by being renamed.

The third asks whether normal is allowed to change without the detector either crying wolf
or learning the attack. An earlier attempt to split the day into phases got louder, not
quieter.

The fourth asks whether the explanation is actually supported by the measurements. A
confidence number that has not been checked against outcomes stays off the page. A previous
check of that kind did not pass.

The fifth asks whether an operator's correction can improve the detector without silently
retraining it. There is no such feedback yet. A pretend operator does not make it a field
result.

One evaluation sits over all of this, and it is not running yet. When a candidate is frozen,
it has to catch more attacks than the engine we ship, inside the same eight alerts a shift,
without raising more false alarms. Both, or it is not a pass. The old recordings that have
already been used stay used.

Version 1 still stands at eight of twelve.
