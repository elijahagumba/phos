# 170. Eight writers, one survivor

*The shared notebook was losing pages. Seven out of eight, silently. ADR 0415.*

The research record this project now keeps is a folder of small files — one per question, one per
experiment, one per finding. The whole point is that both of the editors PHOS is built in read and
write the *same* folder, so work started in one is continuable in the other.

So the audit asked an obvious question: what happens if both write at once?

```
eight requests to add a question  →  one question saved
```

Seven vanished. Not an error, not a warning, nothing in the folder to say anything had gone wrong.
Each of the eight looked at the folder, saw the highest number was zero, decided it would be number
one, and wrote a file called number one. The last one to finish won.

That is the kind of bug that does not announce itself. You would notice weeks later, wondering why
a question you distinctly remember writing down isn't there.

## Three problems wearing one costume

**Nobody was holding the pen.** Working out the next free number and then writing that file were two
separate steps, with nothing stopping somebody else doing the same two steps in between. Those two
steps are now one, and only one process can be inside them at a time — a lock, in the ordinary sense
of the word. The useful property of the kind used here is that the operating system releases it if
the holder dies, so a crashed session cannot leave the record jammed shut.

**A file could be half-written.** The old code wrote straight into the destination. Kill it halfway
and you are left with a file containing the first two-thirds of a record — valid-looking, truncated,
and silently wrong. Now every write goes to a temporary file first and is then *moved* into place,
which on a filesystem is a single indivisible step. A reader sees the old version or the new
version, never a half. Kill it mid-write and you get an abandoned temporary file and an untouched
record, which is the right way round.

**Nothing noticed when it was about to overwrite.** Creating a record now refuses if something is
already there. The only way that situation arises is the numbering and the folder disagreeing, and
in that case overwriting means destroying a record nobody has read.

## And one unreadable file no longer stops everything

Separately: feed the system a truncated record and ask it where the research stands, and it used to
fall over with a stack trace. That command is how a new session works out what has already been
done. It cannot be the thing that breaks when one file is damaged.

Now it prints what it *can* read, then names every file it could not, then reports failure. You get
the state and the bad news, rather than only the bad news.

The direction of that failure got some thought. Skipping a file it cannot read sounds dangerous —
what if the skipped file was the one granting permission for something? The answer is that the
permission check, finding nothing, concludes that *nothing authorises this*, which is a refusal.
A record the system cannot read can never become a record that lets something through. There is a
test whose only job is to hold that true.

## Verified by re-running the original

The honest way to show a fix is to re-run the thing that failed:

```
eight at once  →  8 records, 8 different numbers
thirty-two at once  →  32 records, 32 different numbers
leftover temporary files: 0
```

Twenty new tests, each tied to one of the four defects. The concurrency one launches real separate
programs rather than threads inside one, because threads would share the lock and prove nothing
about two editors.

## What is still broken, and named

The record asks which tier a dataset belongs to — may it be used freely, scored once, or never
touched — and takes the answer on trust. The audit got a sealed dataset accepted by labelling it
"free to use". That is not fixed here. It is the next piece of work, it is written into the record,
and the older warning that speaks up before a sealed dataset is actually read is still there in the
meantime.

Also stated rather than left implicit: the store is safe for the two editors it exists to serve. It
is not a database. If the number of writers ever grows, this is the thing to revisit, not the thing
to assume.
