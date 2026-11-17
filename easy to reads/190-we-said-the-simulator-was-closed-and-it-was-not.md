# 190. We said the simulator was closed, and it was not

*A decision record announced that the simulation engine's source code was not public. Fifty-two
files of it were sitting in the public repository at the time, and the front page said otherwise
directly above a link to them.*

PHOS builds its own simulated industrial plants, because clean labelled data from real plants
barely exists. That generator is real engineering, and in November a reasonable worry came up:
if we hand it to the world, a competitor picks it up and builds on it for free.

Three records were written about that worry in a single day. The first proposed releasing the
engine under the licence PHOS already uses. The second built a programme around that, inviting
outside researchers to audit it. The third reversed both, and went further than either — it said
the code would not be public at all.

**The third record was describing something that had not happened.**

## The export has always carried it

There is one door between the private lab and the public repository, and it is a file listing what
may go through. That list has included the whole `src/` tree since the public repository was
created. So the generator had been published, continuously, for as long as there had been anywhere
to publish it to. Nobody closed it, because closing it would have meant editing that list, and
nothing edited it.

Meanwhile the public front page had been rewritten to say *"The simulator is proprietary. Its
source code is not released."* Eight lines further down, the same page printed a directory listing
that a reader could click straight into and find the generator.

That is the worst kind of error this project can make. Not a number that is slightly off — a
sentence about ourselves that anybody can check in thirty seconds and find false. A project whose
whole argument is *we publish what we refused* cannot afford one.

## What is actually in force

The fix is not to rush out and delete the code. It is to notice that the licence was already doing
the job the closure was supposed to do.

Everything in PHOS, the simulator included, is under the PolyForm Noncommercial License. You can
read it, run it, teach with it and experiment with it. You cannot build a commercial product on it
without a separate licence. That is precisely the competitor worry, already answered, in a file
that has been in the repository the whole time.

And withdrawal would have bought nothing against it. What a competitor would actually want from a
simulator is **how it works** — how a plant is constructed, how attacks are generated, how
randomisation works. The same record that proposed closing the code publishes all of that on
purpose, in full, because a simulator nobody can question is not evidence of anything. Closing the
implementation while publishing the method protects almost nothing and costs the two audiences the
record itself says matter: a researcher cannot critique a generator they are not allowed to read,
and an operator deciding whether to trust us with plant data is not reassured by a black box.

So the licence does the commercial work, and the record does the scientific work. That includes
publishing where the simulator is **known to be wrong**, and shipping example datasets with
fingerprints attached, so somebody who thinks our numbers are flattering can run their own detector
on the identical files and say so.

## The record is corrected, not rewritten

The wrong record is not edited. It keeps its wording, and a new record states what is in force and
why. This is the same treatment given to every record here that turned out to be wrong, and the
reason is that the next person to read the file needs to see what was believed as well as what is
true. A record quietly fixed teaches nobody anything.

Four of its five decisions survive untouched, because only the one about the code was wrong.

## Two other things got put back

Checking this turned up two more, both from the same rewrite.

The front page had been cut to eighty-three lines, and the cut took out the figures, the
mathematics, and the sentence that says the operator's page holds **at most eight** alerts in a
shift. That ceiling is not decoration: there is a test that reads it off the page and compares it,
character for character, with the number in the code. With the sentence gone the test went red, and
a red test is how this repository notices that the page and the product have drifted apart. The
page is rebuilt with its equations and its figures, and the ceiling it states is the code's again.

The other was quieter. Two volumes of the internal encyclopedia had been committed straight into the
public repository — not through the one door, around it. The door's list names `encyclopedia/` as a
thing that must never be published. The volumes brought thirty-four broken links with them, and four
of those links pointed, by name and path, at internal files that are deliberately held back. Nothing
secret escaped: the files themselves never left. But the index announcing them did, and it was
telling a reader exactly what to go looking for.

Both are withdrawn. The lesson is the same in all three cases, and it is the one this project keeps
relearning: **the guard only guards the door you actually walk through.**
