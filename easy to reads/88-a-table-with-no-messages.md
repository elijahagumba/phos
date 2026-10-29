# 88. A table with no messages

*What a look at the already-seen recordings would show, checked without opening them.
ADR 0293.*

## The question

The one kept improvement reads the messages a control system sends: who wrote, and who only
looked. The recordings the shipped engine was scored on are tables of sensor readings and a
flag that says whether that moment was an attack. They are not a log of messages.

So the question, before anyone spends the one look those recordings are still owed, was
whether that look would come back the same as the engine we already shipped.

## What was checked

The message reader is built for one generated plant, and it reads a message log. Nothing
constructs a message from a sensor table. With no messages, the two extra columns it would
add are zeros. An alert is opened only when a column rises above its line. A column of zeros
never does, so the alerts stay on the same rows.

That was shown on a made-up table of numbers, not by opening the recordings. The recordings
were not read. The one look has not been spent.

If a later version invented messages out of the setpoint columns in those tables, this would
no longer hold. The version that exists does not do that.

Nothing was measured. Version 1 still stands at eight of twelve.
