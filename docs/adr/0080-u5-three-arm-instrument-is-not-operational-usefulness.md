# ADR 0080 — U5 is an executable three-arm instrument; the crude run is not operational usefulness

- **Status:** Accepted
- **Date:** 2026-09-16
- **PART:** Usefulness Phase item U5
- **Supersedes:** nothing
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0079](0079-u4-renders-an-existing-narrative-in-plain-english.md),
  Gate 1 (2026-09-11), Gate 2 (2026-09-12)

## Context

U4 produced a plain-English `NarrativeBrief`. U5 asks whether plant-literate subjects reach a
correct conclusion faster and raise fewer false escalations when they hold that brief, compared
with raw telemetry and a threshold alert with no explanation.

Plant-literate subjects are not available. Recruiting them is gated on U7's partner conversation,
which this item does not start. The roadmap therefore splits U5 into (1) an executable instrument,
(2) a crude run labelled as such, and (3) the real study written down as a dependency rather than
run. Reporting the crude run as operational usefulness is `success_is_not`.

Sentiel's templates still declare no contradictory patterns (ADR 0079 / refusal register R23).
Settling-fact suggestions for Sentiel cases remain weak. That is a study-design fact, not a gap
the three Atlas arms can repair.

## Decision

1. **Three arms, one incident.** `raw_telemetry` is a small in-range table with no alert.
   `threshold_alert` is a conventional threshold line with no competing explanations.
   `atlas_explanation` is the full U4 markdown from `assess_narrative` /
   `render_narrative_markdown`. The three presentations of each case must differ.

2. **Gold is the incident, not Atlas.** A correct call is the epistemically right conclusion for a
   plant-literate reader of the evidence. Known-station writes without a work order are
   `unresolved` and do not escalate (ADR 0014). Quiet in-range telemetry is ordinary operation.
   An unknown-master write is unauthorised and does escalate. A covering work order over an
   in-window write stays unresolved. Gold is never "whatever Atlas printed."

3. **The run this phase can execute is labelled non-operator.** Every stimulus and every report
   carries `CRUDE_NON_OPERATOR_NOT_A_FIELD_STUDY` before any table. Subjects are not required to
   be plant engineers. `n_human` on the committed artefacts is **0**. A mechanical policy that
   reads only the stimulus (never gold) exercises the instrument: raw → unresolved / no
   escalate; threshold → copy the alert line; Atlas → copy the U4 assessment and request the
   settling paragraph. Copying the Atlas brief is the policy, not a person.

4. **Latin square is the human protocol, not this run.** A future plant-literate subject sees each
   case once; arms rotate so the same incident is never seen three ways by one person. The crude
   run scores every case under every arm as an instrument check, which a human protocol must not
   do.

5. **Sentiel is in the design and out of the primary table.** One Sentiel fixture exists so the
   settling limitation cannot be assumed away. It is scored, reported in its own section, and
   excluded from the Atlas three-arm comparison.

6. **No invented keys, no public log row.** Reports have no `usefulness_score` and no `accuracy`
   key. Nothing is appended to `eval_runs/log.jsonl`. Frozen HAI 646.58 / 53.26, CERT 6B 0.104,
   and command-lead 0/16 and 1/4 are untouched.

7. **The real study is a U7 dependency.** What would lift it: plant-literate subjects, recruited
   through the partner conversation U7 specifies, sitting the Latin-square protocol. U7 is not
   started here.

## The crude run (computed, not transcribed)

Runner: `scripts/run_u5_decision_study.py`. Report:
`eval_runs/usefulness/u5-decision-study.md` and `.json`. Seed 11. Subject kind
`mechanical_non_operator`. SYNTHETIC-DERIVED ontology fixtures of U3 kinds.

Primary Atlas table (n = 6 cases per arm; `n_with_time` = 0 on every arm):

| Arm | correct | incorrect | false escalations | missed uncertainty |
|---|---:|---:|---:|---:|
| `raw_telemetry` | 3 | 3 | 0 | 3 |
| `threshold_alert` | 2 | 4 | 3 | 3 |
| `atlas_explanation` | 4 | 2 | 0 | 1 |

Those Atlas-arm counts are the mechanical policy copying U4. They are not a human result and are
not operational usefulness. Time to correct conclusion was not collected.

## Consequences

- U5's success clauses are met: the exercise is specified and executable; the crude run is
  reported with limitations first; the real study's dependency is in the refusal register
  (R25, R26) and on U7 as a named wait, without starting U7.
- Quoting the Atlas-arm delta as a control-room win is a defect, even though the numbers are
  real counts from the instrument.
- A later session that recruits humans must use the Latin square, label plant-literate vs not,
  and keep Sentiel's settling weakness in the protocol. It does not get to drop the banner.
