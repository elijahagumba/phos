# 78 — The record the front page could not show

The public copy of PHOS was down to one failing test. It looked for a small file
that pins what the version-1 numbers were when they were written. The file is
here, and the export copies it over, but the public copy's ignore list threw it
away on arrival.

The reason is a single word. Ignore lists usually drop a folder called `build`,
because that is where compiled output goes. PHOS keeps the October build's record
in a folder called `eval_runs/build`. This machine's ignore list was taught the
difference months ago. The public copy's list, a separate file, never was.

So ninety-four files never reached the public copy: the results, the decision
sheets and the pictures of the build, about one and a half megabytes of text.
One of them is the scorecard. The front page says eight of twelve criteria are
met and links to that scorecard, and the link returned "not found". We were
asking people to check a number against a file we had not published.

The ignore list now keeps that folder, the way this machine's list already did.
The failing test was left alone on purpose: making it look away would have turned
the job green and left the broken link standing.

Nothing was measured here. Version 1 still stands at eight of twelve.
