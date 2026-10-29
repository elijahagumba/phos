# 41 — Twelve situations Atlas cannot tell apart in advance

Note 38 made the simulator's writes actually do something, so two capabilities that had been
built and never exercised could at last be pointed at *something*. Note 40 then told us why
Atlas cries wolf on HAI: the model, not the plant. What it could not tell us is what Atlas
does when the missing kinds of trouble — a dropped packet, a work order, a genuine operator
move, an attacker using a sanctioned window — are actually present.

Those kinds do not exist in HAI. They exist here only because we built a plant, an adversary,
and a maintenance register. That is the whole warning, and it belongs in the first paragraph:
**nothing below is about a real works.** It is a diagnostic environment. The answers cannot
validate the assumptions they are built from.

## What was built

Twelve seeded situations, from ordinary running through sensor faults, dropped communications,
unauthorised commands, and an attacker acting inside a genuine maintenance window. Atlas is not
told which is which. A quiet day writes the same bytes it wrote before this work. A noisy day
writes a sidecar labelled SYNTHETIC-DERIVED that Atlas is forbidden to read.

Three plants can host the trouble. The batch reactor still has no control network, so the
kinds that need one are refused rather than invented.

Atlas is given 120 hours of declared-normal history before it is asked anything. That number
is the slowest instrument-drift period the plants already declared — not a threshold chosen
because it made the situations look different.

## The four questions, answered as diagnostics

**Does command attribution work when the write is really there?** On ordinary running, zero
unauthorised writes and zero graph findings. On an unauthorised SCADA setpoint, one write and
one finding, and SCADA is classified as a *known station*. The path sees the bytes. That is
not a lead rate, and it is not the frozen 0 of 16.

**Does a work order move the story, and which way?** Withhold the export and nothing is
promoted; the residual leads. Feed a SAP Plant Maintenance export and two facts are promoted;
`engineering_maintenance` uniquely leads. The direction is the one already written into the
templates. No matcher was retuned.

**What happens when an attacker uses a sanctioned window?** The calendar is planned without
seeing the attack. On seed 11 the two schedules miss. On seed 7 they collide: one write lands
inside a covering order. The bytes on the wire are still the same as an engineer's. That case
is now inspectable. It is not solved.

**Does Atlas get more uncertain when evidence is taken away?** This is the sharp test. With
the capture, the unique leader is already `insufficient_evidence` — a known-station write
supports *both* maintenance and an attacker, so the engine refuses to pick. Take the capture
away and the competing set shrinks to the residual. Atlas did not grow more confident with
less evidence. Making the attacker uniquely lead would have been a template cheat, and it was
not done.

## What this is not

Not a detection claim. Not a row in the public experiment log. Not a reason to quote 0/16 or
1/4. Not U4 — the analyst interface is not started.

Reproduce: `uv run python scripts/diagnose_u3_environment.py --seed 11`.
Report: `eval_runs/synth/u3-diagnostic.md`. Record: ADR 0078.
