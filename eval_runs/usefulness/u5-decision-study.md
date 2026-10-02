# U5 human-decision usefulness - crude non-operator run

**CRUDE_NON_OPERATOR_NOT_A_FIELD_STUDY**

- Not a field study. Subjects are not required to be plant engineers. Recruiting plant-literate people is gated on U7's partner conversation.
- Not evidence of operational usefulness. A crude first run must not be reported as a control-room result (ADR 0074 success_is_not; refusal register R4).
- Sentiel templates declare no contradictory patterns, so settling-fact suggestions for Sentiel cases are currently weak: the honest ask is a declared sanction record, and no corpus PHOS reads carries one (ADR 0079, refusal register R23). This is a study-design fact, not something the three Atlas arms can repair.
- SYNTHETIC-DERIVED. Cases are ontology fixtures of U3 kinds, not a real plant. Not a detection claim. Nothing is appended to eval_runs/log.jsonl.

## This run

- Subject kind: `mechanical_non_operator`
- Human subjects: **0**
- Mechanical respondents: **1**
- Atlas cases in the primary table: **6**
- Sentiel limitation cases (not in the primary table): **1**
- Seed: `11`
- Commit: `dba5c1c74fbe24d527a27a7acfb22bef1ec7541b`
- Sentiel settling-fact suggestions are weak: **yes**

## Protocol (how a plant-literate human would sit this)

The same six Atlas incidents are presented three ways: raw telemetry, a threshold
alert with no explanation, and Atlas's U4 plain-English brief. A human protocol
assigns one arm per case by Latin square so the same incident is never seen three
times by one person. Measures: correct conclusion, false escalations, evidence
requested, ordinal self-confidence 1-4 (not a hypothesis probability), whether
important uncertainty was noticed, and elapsed milliseconds when a human sat it.
The last measure is the one the roadmap names as easiest to omit.

This crude run does **not** sit that protocol. It scores every case under every arm
with a mechanical non-operator policy that never sees gold. Time to correct
conclusion was not collected (`n_with_time` is 0). Plant-literate recruitment is
the U7 partner conversation and is not started here.

## Primary comparison (Atlas cases only)

The mechanical policy copies the U4 assessment on the Atlas-explanation arm. A
lower false-escalation count on that arm is therefore the policy, not a human
result, and is not operational usefulness.

| Arm | n | correct | incorrect | false escalations | missed uncertainty | evidence requested | overconfident and wrong | n with time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `raw_telemetry` | 6 | 3 | 3 | 0 | 3 | 0 | 0 | 0 |
| `threshold_alert` | 6 | 2 | 4 | 3 | 3 | 0 | 4 | 0 |
| `atlas_explanation` | 6 | 4 | 2 | 0 | 1 | 6 | 1 | 0 |

## Time to correct conclusion

Not collected. `n_with_time` is **0** on every primary arm. Decision time requires a human sitting the protocol.

## Sentiel limitation case (excluded from the primary table)

Sentiel templates declare no contradictory patterns, so settling-fact suggestions for Sentiel cases are currently weak: the honest ask is a declared sanction record, and no corpus PHOS reads carries one (ADR 0079, refusal register R23). This is a study-design fact, not something the three Atlas arms can repair.

| Arm | n | correct | incorrect | false escalations | missed uncertainty | evidence requested | overconfident and wrong | n with time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `raw_telemetry` | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| `threshold_alert` | 1 | 0 | 1 | 1 | 1 | 0 | 1 | 0 |
| `atlas_explanation` | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 |

## What would lift a real study

Plant-literate subjects, recruited through the U7 partner conversation, sitting
the Latin-square protocol on these same (or partner-site) incidents. Until then
U5 has an executable instrument and no operational-usefulness measurement.

Nothing in this report is a detection claim. Frozen HAI 646.58 / 53.26 and CERT
6B 0.104 are untouched. Command-lead 0/16 and 1/4 stay unpooled.
