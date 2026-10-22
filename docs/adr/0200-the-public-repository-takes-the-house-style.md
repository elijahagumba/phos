# ADR 0200 — The public repository takes the house style, before week 13

- **Status:** Accepted (Elijah's decision, 19 October 2026)
- **Date:** 2026-10-19
- **PART:** the public front page; `docs/v1-roadmap.md`'s branding freeze
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md), [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0148](0148-bet-001-is-scored-once.md), [ADR 0164](0164-the-held-back-maintenance-check-is-declared.md),
  [ADR 0165](0165-kelmarsh-round-2-trains-on-2018.md), [ADR 0170](0170-every-control-coupling-is-a-loop-and-bars-only-its-outputs.md)

## Context

`docs/v1-roadmap.md` freezes branding until week 13: no README, card, film or design work except
to correct something untrue, so that the engine comes first and the front page is rebuilt once from
v1 numbers. On 19 October Elijah asked for the official repository to be rebranded now, in
accordance with the existing logos (`brand/`) and the settled house style written in
`brand/phos_pdf.py`. No new identity was asked for.

The README cards did not follow that house style: they used an amber accent colour, and showed the
black logo on a white sheet.

## Decision

1. **The freeze is lifted for the public repository's front page only**, by Elijah's decision and
   recorded here. The film, the demo video and every other branded surface stay frozen until
   week 13.
2. **The cards follow the house style exactly** (`public/figures/build_figures.py`): monochrome
   palette (`#0D0D0F` ink, greys, `#D5D5DA` rules, `#F3F3F5` panels), no accent colour; the white
   logo once, on a black cover; grey small-caps tags over bold headings; black callouts with white
   italic text for emphasis; light-grey stat panels with a large number over a small grey caption.
3. **What changed in content**, each sized to its record:
   - first, before any number, a card saying what PHOS is: the shared way of reasoning, then
     Atlas (industrial plants: process and network together; naming a lying instrument, so far on
     simulated plants) and Sentiel (people in an organisation; research only);
   - a results card: 146 of 150 held-back simulated runs named right, none wrong (ADR 0170); 0 of
     80 simulated attacks closed as maintenance (ADR 0164); 17 unexplained alerts in four years on
     Kelmarsh, a real wind farm with no attacks (ADR 0165), with the line that simulated plants are
     a diagnosis, not a real-plant result;
   - the Sentiel card records Bet 001 run once and lost (ADR 0148), in place of the open bet;
   - the boundary card adds "names the lying sensor, on simulated plants", and rewords the
     maintenance limit to what is still true: it cannot close a maintenance alert without the
     work order.
4. **The README footer names the company.** Prose carries no em dashes.

> **Correction, 21 October 2026.** Point 4 named a company entity when this record was accepted.
> The name has been removed from the line above rather than struck through beneath it, because
> Elijah directed that it appear in no documentation and this record is exported to the public
> tree. What the decision said is preserved: the footer named the company. What it named does not
> appear here.
>
> Elijah directed that no documentation name a company entity, so the README footer
> carries the project name, `PHOS`, and no legal suffix. `brand/phos_pdf.py`'s footer constant and
> its own house-style rules were changed to match, which applies to every document the builder
> produces from now on, and the entity name was removed from the outreach drafts in
> `docs/data-campaign/outreach.md` as well. The rest of this record stands: the footer still names
> the project at left with an em-dashed page number at right, and prose still carries no em dashes.
>
> **Correction, 22 October 2026.** Elijah asked for the plates to be drawn as a briefing: dark,
> square, and made of charts and graphs. The white logo stays once, on the cover. One blue,
> `#2D72D2`, is data ink only. It marks a recorded count, and the engine that exists. It does not
> colour a heading, and it does not choose between two tied explanations. 131 and 52 share a scale
> of 160. The three marks under that chart are each scaled to their own count, and the plate says
> so. The tied alert is a graph: two solid edges from one fact, an open node with no edge, and a
> dashed edge that stops short of the fact that would decide it. No new measurement. No second logo.

## Consequences

The front page may be rebuilt again from v1 numbers in week 13. Every figure on it still comes from
an ADR, and the "not yet" list stays. The repository stays private until launch.

## What would reverse this

A figure on the front page with no record behind it, a claim of real-plant detection, or an accent
colour or second logo appearing on the cards.
