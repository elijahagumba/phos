# ADR 0332 — The plates are set on one spacing scale

- **Status:** Accepted
- **Date:** 2026-10-26
- **PART:** the public record
- **Supersedes:** nothing
- **Depends on:** [ADR 0330](0330-the-public-plates-are-one-canvas-and-the-poster-carries-one-sentence.md),
  [ADR 0331](0331-the-public-page-is-set-for-both-themes-and-the-hero-is-the-page.md)

## Context

ADR 0330 gave the plates one canvas and ADR 0331 gave them two themes and one
header grid. Neither touched the space around the type, and the type was
crowded. Measured on the plates as they stood:

- The side margin was 40 on a 600 canvas, **6.7%**. A set page is usually 8 to
  12%.
- The headline filled **480 of a 520 column** — 20 points of air on each side.
- Leading on prose ran **1.38 to 1.60** times the face. Prose wants about 1.6
  to 1.75; 1.38 is tighter than a dictionary.
- The reading measure was **71 characters** a line, above the 45 to 75 band and
  at the end of it.

Each of those alone is a small thing. Together they are why the plates read as
crowded however carefully the type itself was chosen.

No measurement is in this record. No corpus was generated or scored.
`eval_runs/log.jsonl` was not appended. Held-out data was not opened. No
published figure moved; the plates were rebuilt from the same records. v1 stays
8 of 12. P1 stays blocked.

This record takes **0332** and note **129** (ADR 0292).

## Decision

**One spacing scale, named in the module, used by every plate.**

`MARGIN` is 60, a tenth of the canvas. `TOP_LABEL` 56 and `TOP_TITLE` 104 set
the head of every plate; `LEAD_TITLE` 36, `LEAD_BODY` 26, `LEAD_NOTE` 22 and
`LEAD_TIGHT` 20 set every run of lines; `GAP_BLOCK` 48 separates blocks and
`PAD_BOTTOM` 56 ends the plate. Leading is now 1.73 on body, 1.69 on a note,
1.82 on a tick and 1.38 on a title. The measure is 65 characters.

The headline comes down from 48 to 42, so it sets 420 in a 480 column and the
sentence has room on both sides rather than reaching for the margin.

Where a plate draws as well as sets — the two-node graph on plate 02, the
tied-explanation graph on plate 05, the bars on plate 04, the five objects on
the chain plate — the drawing moved with the type, so the figures sit on the
same rhythm instead of being left where the old margin put them. The horizontal
guard in `Card.text` caught two plates whose figures were right-aligned into the
new margin; both were moved rather than allowed to overflow.

### Options

1. Leave the spacing and change the type. The type was not the problem. Refused.
2. Widen the canvas instead of the margin. Every plate's rendered type would get
   smaller and the measure longer, which is the wrong direction on both.
   Refused.
3. One named scale, applied to every plate, drawings included. Chosen. No number
   moves.

## Consequences

**Gained.** The page has air in it. The scale is in the module as named
constants, so the next plate inherits it instead of being measured by eye.

**Cost.** Every plate is taller, so the page is longer to scroll. The headline
is smaller than it was. This record adds no measurement and moves no number.
v1 stays 8 of 12.

**Ten years.** Spacing is a decision with a number, written down beside the
drawing it governs, not a thing each plate settles for itself.

## What would reverse this

A plate that sets its own margin or leading instead of using the scale. A
headline that reaches the column edge. Prose below 1.6 leading or past 75
characters a line. Changing the scale without saying what was measured.
