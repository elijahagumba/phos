# 77 — The public tests, and the one command

The public copy of PHOS had been failing the same twenty-six tests for days.

Twenty-one of them look for a small file that says what each sensor and valve is.
Those files are notes we wrote, not the plant recordings, so they are meant to
travel with the code. The public copy's ignore list treated them as recordings and
left them out. The ignore list now keeps the notes and still leaves the recordings
out.

Four tests check frozen experiment files that the public copy does not carry.
Those tests wait, and they say why, when the file is not there. On this machine,
where the files are, a changed byte still fails the test. Copying those small
files into the public tree is a choice that has not been taken.

One test checks that the old experiment log has not been edited at the top. The
public copy rewrites the author's own folder path out of that log, so the same
lines have a second fingerprint. Both fingerprints are named. Anything else fails.

The bigger job, one command that rebuilds every version-1 number, is still open.
So is the onboarding timer. Nobody outside the project has run the command.
