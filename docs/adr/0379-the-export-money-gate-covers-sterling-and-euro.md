# ADR 0379 — The export's money gate covers sterling and euro, not only dollars

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Public record and export discipline
- **Supersedes:** nothing. [ADR 0342](0342-commercial-records-are-not-published.md) Decision 2
  stands; this record widens the pattern list that decision created and changes nothing else
  about it
- **Depends on:** [ADR 0342](0342-commercial-records-are-not-published.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

ADR 0342 gave the export a commercial-content gate: `[forbidden].content` in
`public/manifest.toml` holds patterns for the vocabulary of a funding or ownership discussion,
and one hit stops the export rather than publishing quietly.

The money pattern it added is `\$\d[\d,.]*\s*(?:[MB]\b|million|billion)`. It requires a dollar
sign. PHOS is a British company talking to British water companies about a British fund, so
every sum in the material the gate exists to withhold is written in pounds, with the lower-case
suffix British usage prefers. The gate could not fire on any of it.

That was not hypothetical. A record written on 29 October 2026 reasons about a funding bid, and
`docs/adr/*` is a wholesale include, so it was selected for export. The gate passed it. It was
caught by a person reading the diff, and its path was added to `exclude` and to
`[forbidden].paths` by hand under ADR 0342's policy.

**A gate that only catches what someone already noticed is not a gate.** This record widens it.

## Decision

**`[forbidden].content` gains a sterling pattern and a euro pattern, built on the dollar
pattern's shape.** The suffix alternation is wider than the dollar one's, because British usage
writes the suffix in lower case and abbreviates billions as two letters.

```
£\d[\d,.]*\s*(?:[Mm]\b|[Bb]n?\b|million|billion)
€\d[\d,.]*\s*(?:[Mm]\b|[Bb]n?\b|million|billion)
```

### Tested before being added, as ADR 0342 requires

Both were run against the **whole current export** — 1213 files, written to disk and scanned,
not sampled — before they were put in the manifest.

| Pattern | Matches in the current export | Matches where it is meant to |
|---|---|---|
| Sterling | **0** | The withheld record, `docs/ipo-roadmap-2026-2034.md`, `docs/partner-routes.md` |
| Euro | **0** | Nothing in the lab today. It is forward-looking |
| Dollar, re-run as a control | **0** | unchanged |

No `[forbidden].allowed` entry was needed, because neither pattern matched anything in the
export that has to stay.

The gate was then exercised end to end through the exporter's own `violations()`, on the real
bytes of the withheld record: with the path rule in place the path rule stops it, and with the
path rule removed the new sterling pattern stops it on its own. Both arms are proven, so the
path entry is belt and braces rather than the only thing holding.

### What these patterns do not catch, said plainly

- **A sum below a million.** A six-figure sum written in full passes, exactly as a six-figure
  dollar sum passes the pattern ADR 0342 added. This record does not close that gap. Lowering
  the threshold would catch ordinary figures — row counts, byte counts, seeded ranges — across a
  measurement repository, and the cost of that is a stopped export every week until someone
  weakens the pattern, which is the failure ADR 0342 warns against.
- **A sum with no currency symbol**, and a sum written as words before the currency.
- **Commercial reasoning that names no sum at all.** The path rule, a reader, and the other
  patterns in the list are what cover that.

The gate is a backstop for a mistake, not a proof that no commercial material can escape. The
first line is still that a record reasoning about funding is not written into `docs/adr/` without
its path being withheld in the same commit.

## Consequences

**Gained.** The money gate now fires in the currency this company actually uses. The record that
slipped through would be stopped by content alone, not only by the path someone remembered to
add.

**Cost.** A false block is more likely than before, because there are now three money patterns
instead of one. That remains the intended direction of failure: a stopped export is a person
reading a diff. `[forbidden].allowed` takes an exact string with its reason when a match is
genuinely fine, and the pattern is not weakened to clear it (ADR 0342).

## What would reverse this

Weakening or deleting a pattern to clear a match instead of adding the exact string to
`allowed` with its reason. Lowering the million threshold without measuring the false blocks
first. Treating the gate as permission to write commercial reasoning into `docs/adr/` on the
assumption that something downstream will catch it.
