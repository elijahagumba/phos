# Lane 1 on the ICSSim development corpus — attribution works; the thesis case is not in this corpus

**Date:** 2026-10-21 · **Development data only.** `phos-icssim-heldout` was not read.
**Not declared, not frozen, not a score against a bar.** A simulated plant, so diagnosis and not
proof (R4, ADR 0143). `eval_runs/log.jsonl` was not appended and no v1 number moved.

Command: `uv run python scripts/lane_e_icssim_baseline.py`
Detector under test: `phos.atlas.command_consistency`, three columns appended to the frozen
engine's score matrix and run through the unchanged `events` and `budget_alerts`, so they compete
for the same 8 alerts a shift. `atlas-v1-consistency` is untouched; a test asserts its own scores
are unchanged.

## Result

| Label | Class | Frozen | Lane 1 | Of | What caught it |
| --- | --- | ---: | ---: | ---: | --- |
| attack | `recon` | 0 | **10** | 10 | `unknown_reader` |
| attack | `replay` | 4 | **10** | 10 | `unknown_writer` |
| attack | `rogue_command` | 7 | **9** | 10 | signal, `unknown_writer` |
| attack | `liar_offset` | 10 | 10 | 10 | signal |
| attack | `liar_freeze` | 3 | 3 | 10 | signal |
| attack | `mimic_maintenance` | 0 | **0** | 10 | — |
| benign | `maintenance` | 4 | 4 | 10 | signal |
| benign | `setpoint` | 0 | 0 | 10 | — |

**Attacks caught: 24 of 60 → 42 of 60. Benign events drawing an alert: 4 of 20 → 4 of 20, unchanged.**

Two columns, kept apart and never pooled, because `command-ranking.md` and ADR 0034 require a
known station and an unknown master to be scored separately. Both are learned from training, not
listed: `unknown_reader` is a poll from a role that never polled, `unknown_writer` a write from a
role that never wrote. Each scores by weight of evidence, so a 4,108-message scan is overwhelming
and one stray poll is weak.

`recon` could only ever have come from the command path: reconnaissance never moves the plant, so
no telemetry-only detector can see it however it is tuned.

## The thesis case is not testable in this corpus, and that is the finding

`mimic_maintenance` is the class the whole claim rests on — an attack whose writes come from the
*operator* station, on the same tag and with the same values as the genuine `maintenance` event in
the same run. A third component, `response_departure`, was built for exactly it, first comparing
the plant's response after a write as one summary number and then as a trajectory.

Neither worked, and the reason is not the comparison:

| | min | median | max |
| --- | ---: | ---: | ---: |
| `mimic_maintenance` | 0.100 | 0.270 | 0.534 |
| genuine `maintenance` | 0.083 | 0.254 | **1.022** |

Fully overlapping, and the only score above the alerting threshold belongs to a **genuine**
maintenance action, which is why that component cost a false alarm rather than catching anything.
Zero of the ten mimics score above all ten genuine events.

Then the corpus itself was measured. Over 39 summary features of the plant's own behaviour during
the two events — mean, spread and range per signal — they differ by a median of **0.17** training
spreads and a maximum of **1.29**, and **not one feature exceeds two spreads.** The two events are
physically indistinguishable. Nothing recoverable from telemetry and commands can separate them,
by any method.

So `mimic_maintenance` is a **provenance** attack, not a physics one: the action is legitimate in
every observable channel and what makes it an attack is that no work order authorised it. That is
the CMMS inlet of ADR 0069 and criterion A5, not this lane. `response_departure` was removed
rather than left in as dead weight; the git history holds it.

**Correction, same day.** An earlier version of this note said the generator should be changed to
give `mimic_maintenance` a different physical effect. That was wrong.
`scripts/icssim/phos_icssim.py:407` shows the two events running the *same code path*, differing
only in whether `_work_order` is called — same station, same tag, same values. The class was built
so that the only thing separating it from legitimate work is that nobody authorised it, which is a
realistic attack and a well-posed test of criterion A5's CMMS inlet (ADR 0069). Changing it would
destroy a good test of A5 to manufacture a worse one of A4. The class is routed to A5 and the
generator is left alone. `docs/build-brief-2026-10-e.md` carries the reasoning.

## Where lane 1 stands

On development, the bar in `docs/build-brief-2026-10-e.md` is met: strictly more attacks caught
within the same budget (42 against 24), no extra false alarms, and a class the frozen engine
misses entirely (`recon`, 0 to 10). A declaration and one held-out score are the next step, and
the declaration has to say plainly that the command path's contribution here is attribution,
which an attacker impersonating the operator station would defeat.
