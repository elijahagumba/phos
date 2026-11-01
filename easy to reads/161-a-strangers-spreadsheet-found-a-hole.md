# 161. A stranger's spreadsheet found a hole in our reader

*Six files arrived from a university pilot plant, with permission to publish and to use the
results commercially provided the department is credited. Pointing the onboarding tool at one of
them did what it is for: it produced a brief in seconds, and it exposed a defect nobody had
noticed. ADR 0394 registers the corpus.*

The onboarding tool reads a plant's historian export and suggests, for every tag, whether it is a
sensor, an actuator or a setpoint, and what it measures — flow, pressure, level, a pump, a valve.
It prints a list. The engineer accepts each line or edits it. A blank cell means the tool would
not guess.

Everything it had been tested on was either hand-written or a corpus whose column names were
already known while it was being built. That is a weak test, and the roadmap says so: the
acceptance bar is that **a corpus not used in development** reaches its first brief in under an
hour of human time. That bar has been sitting open for weeks.

## What arrived

Six exports from the Technical University of Denmark — three runs of a bubble column and three of a
continuous distillation column, taken across July and September 2026. Real pilot plant, real
instruments, real tag names. No attack labels, no declared process map, no statement of units.

And a sentence that matters more than the files: *you are welcome to publish and use the obtained
results commercially as long as appropriate credit is given to our department.* That is wider than
research use, and it is the first permission on this record to publish results commercially.

It is also not a licence. It is a line in a personal email, and three things follow from that which
the registry entry says out loud rather than smoothing over. The department is never named, so the
credit line cannot be written yet and nothing may be published before it is. A staff member's
welcome is not the same as the institution agreeing. And it covers *results*, not handing the raw
spreadsheets to anyone else — so the files stay out of git, as every payload here does.

## What the tool found

The distillation workbook writes its timestamp column `Time Stamp`, with a space. The reader's list
of column names to ignore held `time`, `timestamp`, `datetime`, `date` and `ts` — the unspaced
forms — so the spaced one slipped through and appeared in the brief as a tag called `Time Stamp`,
with no role, no kind, and not one value that parsed as a number.

That is a small bug and an instructive one. It could only be found by a file the tool had never
seen, written by somebody who had never heard of it. The suite was green throughout: the fixtures
had been written by the same hand that wrote the reader, so they spelled things the same way. The
fix folds whitespace and underscores away and lowercases before comparing, while still reporting
the tag name exactly as the plant wrote it.

The same run found a second thing, and this one was **not** fixed. All seventeen temperature tags
came back blank, because the name table knows `TT`, `TIT` and `TE` but not the bare `TI` this plant
writes. Adding it would be one line. Doing it *now* would be tuning the tool on the material that
is supposed to test it, which is exactly the failure the whole exercise is designed to catch. So it
is written down as a finding and left alone.

## What this does not mean

It does not mean onboarding is solved, and it does not mean the acceptance bar is met. The bar is
about **human** time. An agent ran the command and read the list in seconds — that is a smoke test,
and a smoke test is not a trial. The clock starts when a person sits down with the list, and the
sheet that records it is still unfilled.

It also does not mean this is a design partner. A university department that sent six teaching runs
is a source of data, not an operator with a control room and a shift roster. The conversation that
unblocks the product is still the conversation.

And it is not a detection result. Six short runs of two different rigs, with no labels, cannot fit
a baseline and cannot be scored. Nothing here is a rate, a recall figure, or a false-alarm count.

Version 1 still stands at eight of twelve. One of the four open criteria — onboarding in an
afternoon — is now closer: the tool has met a stranger's file, and the stranger's file won.
