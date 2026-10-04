# ADR 0085 — `phos demo` runs one incident end to end and names its misses

- **Status:** Accepted
- **Date:** 2026-10-02
- **PART:** public pre-release
- **Supersedes:** nothing. Moves no frozen row and appends nothing to `eval_runs/log.jsonl`.
- **Superseded in part by:** [ADR 0086](0086-empirical-command-baseline.md) — the recurring
  command-interval false alarm's disposition. The rest of this record stands.
- **Depends on:** [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md),
  [ADR 0079](0079-u4-renders-an-existing-narrative-in-plain-english.md)

## Context

Everything PHOS can show a newcomer was a table or a document. Nothing could be run in one command
and watched. The pieces to do that already existed: the U3 diagnostic environment (ADR 0078) stages
an incident on a simulated water plant with a real control network, the command path reads its
capture, the reasoning engine writes a narrative, and U4 (ADR 0079) renders that narrative in plain
English.

The risk is the usual one for a demo: choosing the run that looks good, or wording the output so a
miss reads as a success.

## Decision

**1. `phos demo` runs the real path.** `src/phos/demo/pipeline.py` simulates the 120 hours Gate 1
requires, stages one U3 scenario (`unauthorised`, `operator` or `attacker`), writes both captures,
learns the baseline, reads the live capture, promotes, reasons and assesses. The terminal shows only
fixed framing and what that run produced. The command is the project's first console entry point,
`phos = "phos.demo.cli:main"`; it is not an API, Intelligence or UI tree (Constitution §3.8).

**2. Two choices are the demo's, both inherited from U3.** Every departure is promoted at full
weight through the same certain calibrator `scripts/diagnose_u3_environment.py` uses, because a
calibrator needs labelled positives the demo does not have. No confidence is printed, but the
weights still feed the belief update, so this choice can change the assessment itself, not only
which facts reach it. *(Corrected 2026-10-02: the first version of this record said it changed
only which facts reach the reasoning.)* Each capture
is dissected once and the frames handed to the same functions `read_command_path` calls, which
produces identical evidence (checked on seed 11: 3 facts, equal summaries) in 9.4 s rather than
15.4 s.

**3. The incident shown is chosen without ground truth.** The demo shows the narrative citing the
most evidence. Ground truth (the writes the plant actually received and its declared write policy)
is read after Atlas finishes and is never an input.

**4. The closing line says how the brief relates to what happened.** A brief *concerns* the truth
when it cites a fact about the writing device, or the link it wrote on, within a minute of the
write. The closing line then reports a tie as a tie, a silence over an unauthorised write as a miss,
and a brief about something else as a false alarm.

## Consequences

**Gained.** One command, about 16 seconds, from simulation to a brief a person can read, with what
actually happened beside it.

**What the three scenarios show on seed 11, stated here so the demo cannot be quoted as more.**

- `unauthorised`: Atlas sees the write (an unexpected function code on a learned link, plus two
  behaviour departures on the SCADA server), cannot separate maintenance from an attack, and names a
  covering work order as the settling fact. This is R1 and R21 shown, not lifted.
- `operator`: the authorised HMI write raises nothing, which is correct. Atlas does raise an
  incident about the SCADA server's command interval, unrelated to any write: a false alarm.
- `attacker`: the catalogue attacker writes in the run's last minute and Atlas raises nothing about
  it: a miss. It raises the same unrelated interval incident.

**Found while building it.** The recurring false alarm in the `operator` and `attacker` runs is the
Gaussian baseline on a discrete feature: in the 120-hour fit, the SCADA server's mean command
interval is exactly 15 s in 36 of 7,197 one-minute windows, and the fitted band (mean plus three
standard deviations, 13.15 s) excludes it. ADR 0086 is the disposition of that alarm: the demo now
fits a separate empirical quantile band, and the twenty-seed count lives there. A write from a
device that has never commanded the target, which contradicts maintenance, still leaves the
residual leading under the placeholder priors and evidence strength (ADR 0008). Those priors were
not tuned in the demo, and ADR 0086 does not tune them either.

**Not gained.** A measurement. One seed, one plant, our adversary (R4, R20). The demo is not a lead
rate, not 0/16 or 1/4, and not a row anywhere.
