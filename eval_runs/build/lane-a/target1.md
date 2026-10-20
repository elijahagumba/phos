# Target 1 — both insiders in the top 48

Lane A, 2026-10-19. ADR 0149. CERT r3.1 development. Ten loops, none kept.

## Start

Frozen 6B (Bet 001, not recomputed): `CSF0929` in the 48 (5 days, best rank 1),
`CCH0959` absent (best rank 957), precision 0.104 against chance 0.012.

## Why it fails

`CCH0959`'s malicious days are not loud on the six starter counts (own-prefix
z about 1.1) and most of them cannot reach the 6B cut because too few of the
34 features speak. `CSF0929` is the opposite: off-hours, removable device, and
file counts jump. A stream that listens to rare new hosts and declared chains
moves `CCH0959` up and buries `CSF0929`.

## Loops

| Loop | Found | Precision@48 | CCH best rank | Decision |
| --- | --- | ---: | ---: | --- |
| 6B (start) | CSF0929 | 0.104 | 957 | — |
| depth | CSF0929 | 0.125 | 1,094 | revert |
| peer-links | none | 0.000 | 1,203 | revert |
| chains | none | 0.000 | 2,049 | revert |
| role-hours | none | 0.000 | 8,296 | revert |
| peer-links+depth | none | 0.000 | 1,060 | revert |
| peer-links+chains | none | 0.000 | 119 | revert |
| peer-links+role-hours | none | 0.000 | 7,615 | revert |
| all-four | none | 0.000 | 7,977 | revert |
| chains+depth | none | 0.000 | 250 | revert |
| peer-links+chains+depth | none | 0.000 | 136 | revert |

Ten loops with no keep. Stopped. The kept scorer is still 6B.

## Held-back

CERT r4.2 was not fetched and not scored (ADR 0147, ADR 0194).

## Scorecard

| Field | This run |
| --- | --- |
| catches_within_budget | 1 of 2 (unchanged) |
| margin_over_chance | 6B still 5 malicious days in 48 against 0.012 |
| runtime | 65 s of process time for ten identity-stream loops |
| everything else | not applicable |
