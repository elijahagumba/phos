# Lane T — the trusted station turned hostile

Simulated diagnosis. The synthetic command harness was built so its results cannot be believed as field rates (ADR 0073). These numbers are not a field rate, not the frozen known-station **0 of 16**, not the unknown-master **1 of 4**, and not ≥70%. The two issuer kinds are not pooled.

## Diagnosis

A write from a station the learned graph already trusts leaves `unexpected_command_function` or silence on a known link. That fact still supports both `engineering_maintenance` and `unauthorised_control_activity`. Maintenance's prior wins, or the two share the lead. A tie is a refusal. ADR 0034, remeasured in ADR 0037 and ADR 0038: known-station unique lead **0 of 16** (moved up in 6). Unknown-master unique lead **1 of 4**. This lane did not remeasure that battery and did not move those matchers.

The false-alarm bar is ADR 0086's figure, **0.20**. A narrative that does not concern the authorised write counts. Silence is 0. Maintenance about that write does not count. Any other narrative does.

## What was tried

Issuer on every run: the water plant's declared operator (`hmi`), a known station. Not the silent engineering workstation. One hostile write and one authorised unusual write per seed. Writes are applied before the controllers run. Development seeds 97801-97820. Held-back seeds 97901-97920, scored once.

Weight on every new fact: `FittedPlattCalibrator(coefficient=0.0, intercept=0.0)`, a constant one half. It was not tuned. A unique lead means `unauthorised_control_activity` is the narrative lead and `tied_lead_ids` is empty. The residual listed first is not a lead.

| Variant | Development unique leads | Development false alarms | Disposition |
| --- | ---: | ---: | --- |
| H1 toward a limit, against the call | **0 of 20** | **0.00** (0 of 20) | Kept. The fact attached on every hostile write and on no authorised run. |
| H2 jump, or a write outside the mode | **0 of 20** | **1.00** (20 of 20) | **Rejected.** The jump attached to every authorised unusual write. |
| H3 write and hide | **0 of 20** | **0.00** (0 of 20) | Kept. The fact attached on every hostile write and on no authorised run. |
| H1+H3 | **0 of 20** | **0.00** (0 of 20) | Frozen challenger. Two facts, still under the residual prior. |

Reports: `h1-development.md`, `h2-development.md`, `h3-development.md`, `h1-h3-development.md`.

## What the reasoning does now

`FacetKind.COMMAND_EFFECT` is a fact about what the write did, not who sent it.

- `toward_limit_against_state` supports unauthorised control when the setpoint leaves the plant's declared operating band toward a safety limit, against the direction the reported state called for. A covering work order withholds it.
- `write_and_hide` supports unauthorised control when the actuator moves and the controlled reading stays inside three of its own noise standard deviations.
- `setpoint_jump` and `outside_operating_mode` exist and are not enabled. They false-alarm.

None of these match `unexpected_command_function` or `silent_command_relationship`. Those facts still support both maintenance and unauthorised control.

## Held-back

Command, after ADR 0254 was committed (`592d051`):

`uv run python scripts/score_trusted_station.py --split held-back`

Result name: `trusted-station:known-operator-effect`.

Challenger sha256: `981270a8c60a0d4733e739ae182a01af2e040b90a9786406c6b77cbaa718f747`.

Seeds 97901-97920. Report: `eval_runs/build/d/trusted/held-back.md`. A second run was refused and the file was not rewritten.

| Bar | Held-back | |
| --- | --- | --- |
| Hostile known-station writes led in more than 0 of them | 0 of 20 | **not met** |
| False-alarm narratives per authorised run not above 0.20 | 0.00 (0 of 20) | **met** |
| Known-link both-support tests green | 3 passed | **met** |

The lead bar is not met. It stands. Two half-weight facts do not lift unauthorised control above the residual prior of 0.30, so the narrative lead stays `insufficient_evidence`.

## Rule check

Known-link indistinguishability was not weakened. Issuer kinds were not pooled. `(-confidence, template_id)` was not inverted. `EVIDENCE_STRENGTH`, the priors, and the champion detector were not edited. `eval_runs/log.jsonl` was not appended. Validation corpora were not opened. Nothing was written under `data/`. `src/phos/atlas/command_effect.py` is 623 lines, over the 500-line file guide. It was left there because splitting it would change the frozen sha256 after the held-back score.
