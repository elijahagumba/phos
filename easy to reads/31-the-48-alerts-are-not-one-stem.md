# The 48 alerts are not one family

CERT's public ruler is identity scoring at 48 alerts: five hits, forty-three misses,
precision 0.104. This week we asked which behaviours actually sat at the top of that queue.

The five hits were not one story. Three were led by how many distinct files someone touched.
One was an off-hours logon. One was a logon count. Removable-device connects — the thumb
drive the scenario text talks about — led **thirteen misses and zero hits** in that top 48.

So we did not carve out a "just the USB stem" detector and pretend it was a quieter 6B.
A family has to catch every labelled hit and none of the false alarms before it earns its
own log name. Nothing did. 0.104 stays the number. `:precision` stays a measured loss.
Sequence models wait.

The write-up is `eval_runs/sentiel/6b-autopsy.md`. The detector name on that file is
`autopsy:6b-top-budget`, which is a diagnosis, not a replacement row.
