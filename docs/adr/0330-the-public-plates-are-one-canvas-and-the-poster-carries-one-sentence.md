# ADR 0330 — The public plates are one canvas, and the poster carries one sentence

- **Status:** Accepted
- **Date:** 2026-10-26
- **PART:** the public record
- **Supersedes:** nothing
- **Depends on:** [ADR 0200](0200-the-public-repository-takes-the-house-style.md),
  [ADR 0327](0327-the-front-door-shows-the-path-and-labels-the-older-engine.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

Every plate on the public front page is an SVG set at `width="100%"`, so the
browser scales it from its own `viewBox` width to the column. The poster was
drawn on an 880 canvas and the numbered plates on a 600 one. The same 15px
face therefore rendered at about 14.7px on the poster and about 21.5px on the
plate beneath it: one page, two type scales. That is what made the page read
as a collage of someone else's artwork rather than one designed thing.

The poster also did four jobs: the mark, the sentence, the speech contract as
a wrapped paragraph, and the six laws as a table. At 0.68 the contract and the
table were the smallest text on the page, and on a phone they were gone. A
paragraph that has to be read was a picture of a paragraph: not selectable,
not translatable, not searchable, and not available to a screen reader except
through one long `alt`.

Four plates sat in the published tree that nothing built: `cover.svg`,
`index.svg`, `page.svg`, and `laws.svg`. `hero_card` names a face that is not
in `FACES`, so it has raised `KeyError` since that face was renamed.
`index_card` is the link row, which is already text in the README. The
numbered sequence a reader sees started at **02**, because plate **01** was
built and never placed.

Every plate also set its text with `tnum`, the tabular-figure feature. Tabular
figures are what a column of counts wants. Applied to prose they also make the
hyphen a tabular minus, so `Research pre-release` set with a visible gap each
side of the dash, on every plate that holds a hyphen.

No measurement is in this record. No corpus was generated or scored.
`eval_runs/log.jsonl` was not appended. Held-out data was not opened. No
published figure moved: the plates were rebuilt from the same records.
v1 stays 8 of 12. P1 stays blocked.

ADR 0328 is in the working tree and ADR 0329 is on an open branch, so this
record takes **0330** and note **127** (ADR 0292).

## Decision

**One canvas for every plate, and the poster carries the sentence alone.**

`COVER` is `WIDTH`. Every plate is 600 wide, so one type size is one size on
the page whichever plate a reader is looking at. The poster holds the mark,
the two headline lines, what the engine is, a rule, and two small labels. Its
headline is set at 48px, the largest size that fits the column.

The speech contract is the README's first paragraph, in text. The six laws are
plate **02**, wrapped to the column. Plate **01**, which was already built, is
placed, so the sequence runs 01 what PHOS is, 02 the six laws, 03 measured,
04 one alert, 05 the boundary. `hero_card` and `index_card` are deleted, and
the three plates nothing builds leave the published tree. `tnum` is set on the
three numeric faces, not on every face, so the counts still line up and a hyphen
in prose is a hyphen.

### Options

1. Keep both canvases and scale each plate's type by its own width. The drawn
   parts of each plate are hand-placed against that canvas, so the type would
   shrink away from the bars and nodes it labels. Refused.
2. Move every plate to the 880 canvas. Seven hand-placed layouts would be
   rebuilt, and a reader gains nothing a 600 canvas does not already give.
   Refused.
3. One canvas at 600, and the poster rebuilt to carry one sentence. Chosen.

## Consequences

**Gained.** One type scale down the whole page. The contract can be selected,
translated, searched and read aloud. The numbered sequence is complete. Three
plates nothing builds are gone, and two dead builders with them.

**Cost.** The six laws are no longer on the first plate; a reader scrolls one
plate to reach them. The poster is shorter, so the page opens with less on it.
This record adds no measurement and moves no number. v1 stays 8 of 12.

**Ten years.** A plate is a picture of a thing that is also written down. The
page does not depend on an image to say what PHOS refuses.

## What would reverse this

A plate at a width the others do not use. A paragraph that has to be read
locked inside an image. A figure on a plate that is not in the record.
Setting prose with the tabular-figure feature. A plate
left in the published tree that the page does not show. Putting a score, a
price, or a date for either on the front door.
